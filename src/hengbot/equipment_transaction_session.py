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
from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import STORE_HOME, Snapshot


@dataclass(frozen=True)
class EquipmentTransactionObservation:
    in_home: bool
    pack: tuple[tuple[str, int], ...]
    equipped: tuple[tuple[str, str], ...]

    @classmethod
    def create(
        cls,
        *,
        in_home: bool,
        pack_identities: tuple[str, ...] = (),
        equipped_identities: tuple[tuple[str, str], ...] = (),
    ) -> "EquipmentTransactionObservation":
        return cls(
            in_home,
            tuple(sorted(Counter(pack_identities).items())),
            tuple(sorted(equipped_identities)),
        )

    def pack_count(self, identity: str) -> int:
        return dict(self.pack).get(identity, 0)

    def equipped_identity(self, slot: str | None) -> str | None:
        if slot is None:
            return None
        return dict(self.equipped).get(slot)


class EquipmentTransactionSession:
    """Advance only after the last requested operation is visible in a snapshot."""

    def __init__(
        self,
        plan: EquipmentTransactionPlan,
        *,
        max_unconfirmed_observations: int = 2,
    ) -> None:
        self.plan = plan
        self.index = 0
        self.blockers = list(plan.blockers)
        self.max_unconfirmed_observations = max_unconfirmed_observations
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
        needs_home = action.phase != PHASE_EQUIP
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
        needs_home = action.phase != PHASE_EQUIP
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
        if action.kind == "deposit":
            return after.pack_count(action.item_identity) < before.pack_count(
                action.item_identity
            )
        if action.kind == "withdraw":
            return after.pack_count(action.item_identity) > before.pack_count(
                action.item_identity
            )
        if action.kind == "takeoff":
            return (
                after.equipped_identity(action.target_slot) != action.item_identity
                and after.pack_count(action.item_identity)
                > before.pack_count(action.item_identity)
            )
        if action.kind in {"equip", "reposition"}:
            return (
                after.equipped_identity(action.target_slot) == action.item_identity
                and before.equipped_identity(action.target_slot) != action.item_identity
            )
        return False


def observe_equipment_transactions(
    snapshot: Snapshot,
) -> EquipmentTransactionObservation:
    pack: list[str] = []
    for item in snapshot.inventory:
        if item.is_equipment:
            pack.extend([equipment_identity(item)] * max(1, item.count))
    equipped = tuple(
        (item.slot, equipment_identity(item))
        for item in snapshot.equipment
        if item.is_equipment
    )
    return EquipmentTransactionObservation.create(
        in_home=(
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
        ),
        pack_identities=tuple(pack),
        equipped_identities=equipped,
    )
