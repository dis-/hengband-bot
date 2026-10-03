"""Fail-closed confirmation state for an equipment transaction plan."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256

from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.model import STORE_HOME, Snapshot


@dataclass(frozen=True)
class EquipmentTransactionObservation:
    in_home: bool
    pack: tuple[tuple[str, int], ...]
    equipped: tuple[tuple[str, str], ...]
    home: tuple[tuple[str, int], ...] = ()
    barrier_generation: int | None = None
    operation_outcome: str | None = None
    pack_moves: tuple[tuple[str, int], ...] = ()
    home_moves: tuple[tuple[str, int], ...] = ()
    equipped_moves: tuple[tuple[str, str], ...] = ()

    @classmethod
    def create(
        cls,
        *,
        in_home: bool,
        pack_identities: tuple[str, ...] = (),
        equipped_identities: tuple[tuple[str, str], ...] = (),
        home_identities: tuple[str, ...] = (),
        barrier_generation: int | None = None,
        operation_outcome: str | None = None,
        pack_move_identities: tuple[str, ...] = (),
        home_move_identities: tuple[str, ...] = (),
        equipped_move_identities: tuple[tuple[str, str], ...] = (),
    ) -> "EquipmentTransactionObservation":
        return cls(
            in_home,
            tuple(sorted(Counter(pack_identities).items())),
            tuple(sorted(equipped_identities)),
            tuple(sorted(Counter(home_identities).items())),
            barrier_generation,
            operation_outcome,
            tuple(sorted(Counter(
                pack_move_identities or pack_identities
            ).items())),
            tuple(sorted(Counter(
                home_move_identities or home_identities
            ).items())),
            tuple(sorted(equipped_move_identities)),
        )

    def pack_count(self, identity: str) -> int:
        return dict(self.pack).get(identity, 0)

    def equipped_identity(self, slot: str | None) -> str | None:
        if slot is None:
            return None
        return dict(self.equipped).get(slot)

    def home_count(self, identity: str) -> int:
        return dict(self.home).get(identity, 0)

    def pack_move_count(self, identity: str) -> int:
        return dict(self.pack_moves).get(identity, 0)

    def home_move_count(self, identity: str) -> int:
        return dict(self.home_moves).get(identity, 0)


class EquipmentTransactionSession:
    """Advance only after the last requested operation is visible in a snapshot."""

    # Older checkpoints supply the class default until the first claim records
    # this session. The plan is immutable for that claim's lifetime.
    opened_sequence: int | None = None

    def __init__(
        self,
        plan: EquipmentTransactionPlan,
        *,
        max_unconfirmed_observations: int = 2,
        physical_context: str = "legacy",
    ) -> None:
        self.plan = plan
        self.index = 0
        self.blockers = list(plan.blockers)
        self.max_unconfirmed_observations = max_unconfirmed_observations
        if physical_context not in {"legacy", "home"}:
            raise ValueError("physical_context must be 'legacy' or 'home'")
        self.physical_context = physical_context
        self._dispatched: EquipmentTransaction | None = None
        self._before: EquipmentTransactionObservation | None = None
        self._unconfirmed = 0
        self._posted_command_id: str | None = None
        self._posted_context_identity: tuple[object, ...] | None = None
        self._prepared: tuple[
            EquipmentTransaction,
            EquipmentTransactionObservation,
            str,
            tuple[object, ...],
        ] | None = None
        target = "\n".join(
            f"{action.phase}|{action.kind}|{action.item_id}|"
            f"{action.target_slot or ''}|{action.item_identity}"
            for action in plan.actions
        )
        self.target_loadout_id = sha256(target.encode("utf-8")).hexdigest()[:16]

    @property
    def complete(self) -> bool:
        return self.index >= len(self.plan.actions) and self._dispatched is None

    @property
    def executable(self) -> bool:
        return not self.blockers

    def block(self, reason: str) -> None:
        if reason not in self.blockers:
            self.blockers.append(reason)

    @property
    def required_context(self) -> str | None:
        action = self.current_action
        if action is None:
            return None
        if self.physical_context == "home":
            return "home"
        return "outside_home" if action.phase == PHASE_EQUIP else "home"

    @property
    def current_action(self) -> EquipmentTransaction | None:
        if self._dispatched is not None or self.index >= len(self.plan.actions):
            return None
        return self.plan.actions[self.index]

    @property
    def pending_action(self) -> EquipmentTransaction | None:
        return self._dispatched

    @property
    def prepared_action(self) -> EquipmentTransaction | None:
        return None if self._prepared is None else self._prepared[0]

    @property
    def unconfirmed_observations(self) -> int:
        return self._unconfirmed

    @property
    def posted_command_id(self) -> str | None:
        return self._posted_command_id

    @property
    def posted_context_identity(self) -> tuple[object, ...] | None:
        return self._posted_context_identity

    def discard_prepared(self) -> None:
        self._prepared = None

    def reconcile_carried(self, snapshot: Snapshot) -> bool:
        """Reconcile an unposted target from the observed pack and worn slots.

        A withdrawal is redundant only when every remaining equip of that
        physical item is already worn or has a distinct available pack copy.
        This keeps a second identical ring from borrowing the first copy.
        Deposits and posted operations still require their own observed effect.
        """
        if not self.executable or self.pending_action or self.prepared_action:
            return False
        action = self.current_action
        if action is None or action.kind != "withdraw":
            return False

        def matches(item):
            return item.is_equipment and (
                equipment_move_identity(item) == action.move_identity
                if action.move_identity else equipment_identity(item) == action.item_identity
            )

        def worn(target):
            return any(item.slot == target.target_slot and matches(item)
                       for item in snapshot.equipment)

        if action.kind == "withdraw":
            targets = [target for target in self.plan.actions[self.index + 1:]
                       if target.kind in {"equip", "reposition"}
                       and ((action.move_identity and target.move_identity == action.move_identity)
                            or (not action.move_identity and target.item_identity == action.item_identity))]
            if not targets:
                return False
            if any((target.kind == "takeoff" and any(
                    equip.target_slot == target.target_slot for equip in targets))
                   or (target.kind == "deposit" and (
                       target.move_identity == action.move_identity if action.move_identity
                       else target.item_identity == action.item_identity))
                   for target in self.plan.actions[self.index + 1:]):
                return False
            needed = sum(not worn(target) for target in targets)
            available = sum(max(1, item.count) for item in snapshot.inventory if matches(item))
            if available < needed:
                return False
        self.index += 1
        # Only the equips made redundant by this already-satisfied withdrawal
        # are reconciled. Unrelated planned equip operations retain their own
        # prepare/post/observation protocol, including Home's existing phases.
        while (next_action := self.current_action) is not None:
            if (next_action.kind not in {"equip", "reposition"}
                    or ((next_action.move_identity != action.move_identity)
                        if action.move_identity
                        else (next_action.item_identity != action.item_identity))
                    or not worn(next_action)):
                break
            self.index += 1
        return True

    def prepare(
        self,
        action: EquipmentTransaction,
        observation: EquipmentTransactionObservation,
        command_id: str,
        context_identity: tuple[object, ...],
    ) -> bool:
        """Bind a command to observed context without claiming it was posted."""
        if not self.executable or action != self.current_action:
            return False
        needs_home = self.physical_context == "home" or action.phase != PHASE_EQUIP
        if observation.in_home != needs_home:
            return False
        candidate = (action, observation, command_id, context_identity)
        if self._prepared is not None and self._prepared != candidate:
            return False
        self._prepared = candidate
        return True

    def confirm_posted(self, command_id: str) -> bool:
        """Commit the prepared transition only after the transport posted it."""
        if self._prepared is None or self._prepared[2] != command_id:
            return False
        action, observation, _, _ = self._prepared
        self._posted_command_id = command_id
        self._posted_context_identity = self._prepared[3]
        self._prepared = None
        return self.dispatch(action, observation)

    def dispatch(
        self,
        action: EquipmentTransaction,
        observation: EquipmentTransactionObservation,
    ) -> bool:
        """Record one emitted command; reject stale or wrong-context dispatches."""
        if not self.executable or action != self.current_action:
            return False
        needs_home = self.physical_context == "home" or action.phase != PHASE_EQUIP
        if observation.in_home != needs_home:
            return False
        self._dispatched = action
        self._before = observation
        self._unconfirmed = 0
        return True

    def observe(self, observation: EquipmentTransactionObservation) -> bool:
        """Confirm the in-flight action. Return True only when it completed."""
        if self.blockers:
            return False
        action = self._dispatched
        before = self._before
        if action is None or before is None:
            return False
        if (
            before.barrier_generation is not None
            and observation.barrier_generation is not None
            and observation.barrier_generation <= before.barrier_generation
        ):
            return False
        if observation.operation_outcome in {"refused", "cancelled", "failed"}:
            self.block(f"{action.kind}-{observation.operation_outcome}")
            return False
        if self._confirmed(action, before, observation):
            self.index += 1
            self._dispatched = None
            self._before = None
            self._unconfirmed = 0
            self._posted_command_id = None
            self._posted_context_identity = None
            return True
        # An observation counter is not evidence that the physical item is
        # impossible.  Retain the durable target and the posted action until a
        # terminal postcondition or explicit item-specific evidence arrives.
        self._unconfirmed += 1
        return False

    @staticmethod
    def _confirmed(
        action: EquipmentTransaction,
        before: EquipmentTransactionObservation,
        after: EquipmentTransactionObservation,
    ) -> bool:
        pack_count = (
            lambda observation: observation.pack_move_count(action.move_identity)
        ) if action.move_identity else (
            lambda observation: observation.pack_count(action.item_identity)
        )
        home_count = (
            lambda observation: observation.home_move_count(action.move_identity)
        ) if action.move_identity else (
            lambda observation: observation.home_count(action.item_identity)
        )
        if action.kind == "deposit":
            return pack_count(after) < pack_count(before)
        if action.kind == "withdraw":
            return pack_count(after) > pack_count(before)
        if action.kind == "takeoff":
            slot_cleared = (
                after.equipped_identity(action.target_slot) != action.item_identity
            )
            reached_pack = pack_count(after) > pack_count(before)
            shelved_by_home = (
                before.in_home
                and after.in_home
                and home_count(after) > home_count(before)
            )
            return slot_cleared and (reached_pack or shelved_by_home)
        if action.kind in {"equip", "reposition"}:
            if action.move_identity and getattr(after, "equipped_moves", ()):
                return (dict(after.equipped_moves).get(action.target_slot) == action.move_identity
                        and dict(getattr(before, "equipped_moves", ())).get(action.target_slot)
                        != action.move_identity)
            return (
                after.equipped_identity(action.target_slot) == action.item_identity
                and before.equipped_identity(action.target_slot) != action.item_identity
            )
        return False


def observe_equipment_transactions(
    snapshot: Snapshot,
    *,
    barrier_generation: int | None = None,
    operation_outcome: str | None = None,
) -> EquipmentTransactionObservation:
    pack: list[str] = []
    pack_moves: list[str] = []
    for item in snapshot.inventory:
        if item.is_equipment:
            pack.extend([equipment_identity(item)] * max(1, item.count))
            pack_moves.extend([equipment_move_identity(item)] * max(1, item.count))
    equipped = tuple(
        (item.slot, equipment_identity(item))
        for item in snapshot.equipment
        if item.is_equipment
    )
    home: list[str] = []
    home_moves: list[str] = []
    if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
        for item in getattr(snapshot.store, "items", ()):
            if item.is_equipment:
                home.extend([equipment_identity(item)] * max(1, item.count))
                home_moves.extend([equipment_move_identity(item)] * max(1, item.count))
    return EquipmentTransactionObservation.create(
        in_home=(
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
        ),
        pack_identities=tuple(pack),
        equipped_identities=equipped,
        equipped_move_identities=tuple(
            (item.slot, equipment_move_identity(item)) for item in snapshot.equipment
            if item.is_equipment),
        home_identities=tuple(home),
        barrier_generation=barrier_generation,
        operation_outcome=operation_outcome,
        pack_move_identities=tuple(pack_moves),
        home_move_identities=tuple(home_moves),
    )
