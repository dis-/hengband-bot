"""Single observation-driven owner for every equipment mutation command."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from hengbot.model import (
    TVAL_CAPTURE,
    TVAL_CARD,
    TVAL_DIGGING,
    TVAL_HAFTED,
    TVAL_POLEARM,
    TVAL_RING,
    TVAL_SHIELD,
    TVAL_SWORD,
)
from hengbot.policy_constants import (
    EQUIPMENT_MUTATION_RELEASE_LIMIT,
    EQUIPMENT_SLOT_KEY,
)


WIELD_KEY = "w"
TAKEOFF_KEY = "t"


class EquipmentMutationState(str, Enum):
    IDLE = "idle"
    PREPARED = "prepared"
    POSTED = "posted"


@dataclass(frozen=True)
class EquipmentMutationResult:
    key: str | None
    report: str | None = None


def equipment_signature(snapshot) -> tuple:
    """Observed worn state; count is retained because a worn stack can split."""
    return tuple(sorted((
        (
            getattr(item, "slot", None), getattr(item, "tval", None),
            getattr(item, "sval", None), getattr(item, "name", None),
            getattr(item, "count", None), getattr(item, "is_equipment", None),
        )
        for item in snapshot.equipment
    ), key=repr))


_SLOT_BY_KEY = {key: slot for slot, key in EQUIPMENT_SLOT_KEY.items()}
_EFFECT = "requested-item"


def stable_identity(item) -> tuple | None:
    """What identifies this very item across boards, and nothing mutable.

    Base kind (tval, and sval once the flavor is aware), weight, and the
    ego/artifact class once the item is known.  Bonuses (disenchantment),
    charges, fuel, inscription, learned flags and the display name all change
    without any equipment command and are never part of it.  Knowledge-gated
    fields are None while unknown, so wearing an item that identifies it on
    the spot still matches (``same_item``).
    """
    if item is None:
        return None
    aware = getattr(item, "aware", True)
    known = getattr(item, "known", True)
    return (
        getattr(item, "tval", None),
        getattr(item, "weight", None),
        getattr(item, "sval", None) if aware else None,
        (
            bool(getattr(item, "is_ego", False)),
            bool(getattr(item, "is_artifact", False)),
        ) if known else None,
    )


def same_item(identity: tuple | None, item) -> bool:
    """Whether ``item`` can be the item ``identity`` was taken from."""
    other = stable_identity(item)
    if identity is None or other is None:
        return identity is None and other is None
    tval, weight, sval, grade = identity
    o_tval, o_weight, o_sval, o_grade = other
    return (
        tval == o_tval
        and weight == o_weight
        and (sval is None or o_sval is None or sval == o_sval)
        and (grade is None or o_grade is None or grade == o_grade)
    )


def _worn(snapshot, slot: str | None):
    return next(
        (item for item in snapshot.equipment if getattr(item, "slot", None) == slot),
        None,
    )


def _worn_count(snapshot, identity: tuple | None) -> int:
    return sum(1 for item in snapshot.equipment if same_item(identity, item))


def _pack_count(snapshot, identity: tuple | None) -> int:
    return sum(
        int(getattr(item, "count", 1) or 1)
        for item in snapshot.inventory
        if same_item(identity, item)
    )


def worn_instance(item) -> tuple | None:
    """Which physical item occupies a slot, for telling two of a kind apart.

    Everything that is fixed for one physical item while it stays worn: its
    kind and knowledge state and its bonuses.  The display name, fuel, the
    recharge timeout and the inscription change on the same item without any
    equipment command and are left out (fuel is compared separately, see
    ``_effect_observed``).  Identification of the worn item itself or a
    disenchantment changes this record too, so it only ever completes a
    wield together with the requested item's stable identity.
    """
    if item is None:
        return None
    return tuple(getattr(item, name, None) for name in (
        "tval", "sval", "weight", "count", "aware", "known", "is_ego",
        "is_artifact", "to_h", "to_d", "to_a", "ac", "pval",
        "damage_dice_num", "damage_dice_sides",
    ))


def _fuel(item) -> int:
    return int(getattr(item, "fuel", 0) or 0) if item is not None else 0


def _requested_effect(snapshot, kind: str, slot: str | None, item) -> tuple:
    """The observation that completes this one command (see ``observe``)."""
    identity = stable_identity(item)
    occupant = _worn(snapshot, slot)
    return (
        _EFFECT, kind, slot, identity,
        same_item(identity, occupant),
        _worn_count(snapshot, identity),
        _pack_count(snapshot, identity),
        worn_instance(occupant),
        _fuel(occupant),
    )


def _slot_kinds(entries) -> dict:
    """Slot -> base kind of a worn-state record (old signature or board)."""
    kinds = {}
    for entry in entries:
        if isinstance(entry, tuple) and len(entry) >= 3:
            kinds[entry[0]] = (entry[1], entry[2])
    return kinds


def _effect_observed(snapshot, expected: tuple | None) -> bool:
    if (
        isinstance(expected, tuple)
        and len(expected) == 6
        and expected[0] == "requested-effect"
    ):
        # A local f8dfa6e2 expectation (never pushed): its requested slot is
        # known; an item leaving or entering that slot is the effect.
        slot_before = expected[3]
        occupant = _worn(snapshot, expected[2])
        now = (
            (getattr(occupant, "tval", None), getattr(occupant, "sval", None))
            if occupant is not None else None
        )
        return now != (tuple(slot_before[:2]) if slot_before else None)
    if not (
        isinstance(expected, tuple)
        and len(expected) in (7, 9)
        and expected[0] == _EFFECT
    ):
        # A pre-rule expectation restored from a checkpoint: the whole worn
        # signature at post time, without the requested slot or item.  Only a
        # change of some slot's base kind (an item left or entered it) is the
        # command's effect; a name-only change (fuel, recharge, inscription)
        # keeps it in flight.
        current = _slot_kinds(
            (
                getattr(item, "slot", None), getattr(item, "tval", None),
                getattr(item, "sval", None),
            )
            for item in snapshot.equipment
        )
        return current != _slot_kinds(expected or ())
    _marker, kind, slot, identity, held_before, worn_before, pack_before = (
        expected[:7]
    )
    # A 7-field expectation (local af2cbf3c) has no occupant record: a
    # same-kind swap is then left to the bounded release.
    instance_before, fuel_before = (
        expected[7:9] if len(expected) == 9 else (None, None)
    )
    if kind == "wield":
        occupant = _worn(snapshot, slot)
        if _worn_count(snapshot, identity) > worn_before:
            # One more of the requested item is worn where the game put it.
            return True
        if not same_item(identity, occupant):
            return False
        # The requested item occupies the requested slot.  When the slot
        # already held one of the same kind, it must be another physical
        # item: the requested one left the pack, the occupant's instance
        # record changed, or its fuel rose (a worn light only burns down).
        return (
            not held_before
            or _pack_count(snapshot, identity) < pack_before
            or (
                len(expected) == 9
                and (
                    worn_instance(occupant) != instance_before
                    or _fuel(occupant) > fuel_before
                )
            )
        )
    # Takeoff: the slot no longer holds that item, and the item is in the pack.
    return (
        not same_item(identity, _worn(snapshot, slot))
        and _pack_count(snapshot, identity) > pack_before
    )


def _item_identity(item) -> tuple:
    # Count and location deliberately do not identify a physical item kind.
    return tuple(getattr(item, name, None) for name in (
        "tval", "sval", "name", "charges", "inscription", "known",
        "fully_known",
    ))


def progress_core(snapshot) -> tuple:
    """Gold/experience plus a stack-normalized total per item identity."""
    totals: dict[tuple, int] = {}
    for item in (*snapshot.inventory, *snapshot.equipment):
        identity = _item_identity(item)
        totals[identity] = totals.get(identity, 0) + int(getattr(item, "count", 1))
    return (
        getattr(snapshot.player, "gold", 0),
        getattr(snapshot.player, "exp", 0),
        tuple(sorted(totals.items(), key=repr)),
    )


@dataclass
class EquipmentMutationExecutor:
    """Compose, serialize, and observe all wield/takeoff operations."""

    state: EquipmentMutationState = EquipmentMutationState.IDLE
    goal: str | None = None
    prepared_key: str | None = None
    expected_signature: tuple | None = None
    prepared_core: tuple | None = None
    refusals: int = 0
    last_report: str | None = None
    last_posted_goal: str | None = None
    last_posted_core: tuple | None = None
    observed_changes: int = 0
    # True once the per-board observation counted this board as fruitless,
    # so a request on the same board does not count it a second time.
    board_counted: bool = False

    _OPPOSING = frozenset({"mining-loadout", "combat-loadout"})

    def observe(self, snapshot, *, count_fruitless: bool = False) -> str | None:
        """Complete a posted command only on its own effect.

        A wield is complete when the requested item occupies the requested
        slot; a takeoff when the slot no longer holds the item that was there
        and that item is in the pack.  Items are matched by their stable
        identity: a bonus change (disenchantment), fuel, recharge, inscription
        or learned flags complete nothing.
        """
        if self.state != EquipmentMutationState.POSTED:
            return None
        if _effect_observed(snapshot, self.expected_signature):
            self.observed_changes += 1
            self.state = EquipmentMutationState.IDLE
            self.goal = None
            self.expected_signature = None
            self.refusals = 0
            self.board_counted = False
            self.last_report = None
            return None
        if not count_fruitless:
            return None
        # The per-board observation (the policy's decision entry): one refusal
        # per fruitless board, and the established loud release at LIMIT, so
        # a missed effect (a full-pack takeoff dropping the item, a swap the
        # board cannot tell apart) is bounded without another request.
        self.refusals += 1
        self.board_counted = True
        if self.refusals >= EQUIPMENT_MUTATION_RELEASE_LIMIT:
            self._release_unobserved()
            return self.last_report
        return None

    def _release_unobserved(self) -> None:
        self.state = EquipmentMutationState.IDLE
        self.goal = None
        self.expected_signature = None
        self.refusals = 0
        self.board_counted = False
        self.last_report = "posting-contract:equipment-mutation-released"

    def _begin(self, snapshot, goal: str) -> EquipmentMutationResult | None:
        self.observe(snapshot)
        if self.state == EquipmentMutationState.POSTED:
            # Match the sender's established terminal recovery allowance: one
            # refusal per fruitless observation, then a loud release at LIMIT.
            # A board the per-board observation already counted is not
            # counted again by requests on it (the flag lasts until the next
            # per-board observation, a post or a release).
            if not getattr(self, "board_counted", False):
                self.refusals += 1
            if self.refusals >= EQUIPMENT_MUTATION_RELEASE_LIMIT:
                self._release_unobserved()
            else:
                self.last_report = "posting-contract:equipment-mutation-unobserved"
            return EquipmentMutationResult(None, self.last_report)
        core = progress_core(snapshot)
        if (
            goal in self._OPPOSING
            and self.last_posted_goal in self._OPPOSING
            and goal != self.last_posted_goal
            and core == self.last_posted_core
        ):
            self.last_report = "goal-already-superseded"
            return EquipmentMutationResult(None, self.last_report)
        return None

    def _prepare(
        self, snapshot, goal: str, key: str, effect: tuple | None = None
    ) -> EquipmentMutationResult:
        refusal = self._begin(snapshot, goal)
        if refusal is not None:
            return refusal
        self.state = EquipmentMutationState.PREPARED
        self.goal = goal
        self.prepared_key = key
        self.expected_signature = (
            effect if effect is not None else equipment_signature(snapshot)
        )
        self.prepared_core = progress_core(snapshot)
        self.last_report = None
        return EquipmentMutationResult(key)

    def request_takeoff(self, snapshot, goal: str, slot_key: str) -> EquipmentMutationResult:
        slot = _SLOT_BY_KEY.get(slot_key)
        return self._prepare(
            snapshot, goal, TAKEOFF_KEY + slot_key,
            _requested_effect(snapshot, "takeoff", slot, _worn(snapshot, slot)),
        )

    def request_wield(
        self, snapshot, goal: str, item, target_slot: str, slot_keys: dict[str, str]
    ) -> EquipmentMutationResult:
        if target_slot not in slot_keys:
            return EquipmentMutationResult(None, "unknown-equipment-slot")
        main = next((it for it in snapshot.equipment if it.slot == "main_hand"), None)
        sub = next((it for it in snapshot.equipment if it.slot == "sub_hand"), None)
        suffix = ""
        tval = getattr(item, "tval", None)
        if tval in {TVAL_DIGGING, TVAL_HAFTED, TVAL_POLEARM, TVAL_SWORD}:
            if main is None and sub is None and target_slot == "sub_hand":
                # do_cmd_wield initializes an empty pair with wield_slot(),
                # which selects INVEN_MAIN_HAND, and asks no follow-up prompt.
                # There is therefore no suffix capable of selecting the left
                # hand.  Refuse the impossible direct mutation; callers must
                # restore main_hand before sub_hand.
                return EquipmentMutationResult(None, "sub-hand-requires-main-hand")
            if main is not None and sub is not None:
                suffix = slot_keys[target_slot]
            elif main is not None:
                suffix = "y" if target_slot == "sub_hand" else "n"
            elif sub is not None and (sub.is_melee_weapon or sub.is_digging_tool):
                suffix = "y" if target_slot == "main_hand" else "n"
        elif tval in {TVAL_SHIELD, TVAL_CAPTURE, TVAL_CARD}:
            main_melee = main is not None and (main.is_melee_weapon or main.is_digging_tool)
            sub_melee = sub is not None and (sub.is_melee_weapon or sub.is_digging_tool)
            # cmd-equipment.cpp checks the sub-melee-first case before the
            # capture-device two-hand chooser.
            if not main_melee and sub_melee:
                suffix = ""
            elif main_melee and sub_melee:
                suffix = slot_keys[target_slot]
            elif main is not None and sub is not None and (
                tval == TVAL_CAPTURE or not main_melee and not sub_melee
            ):
                suffix = slot_keys[target_slot]
        elif tval == TVAL_RING:
            suffix = "(" if target_slot == "main_ring" else ")"
        return self._prepare(
            snapshot, goal, WIELD_KEY + item.slot + suffix,
            _requested_effect(snapshot, "wield", target_slot, item),
        )

    def confirm_posted(self, key: str) -> bool:
        if self.state != EquipmentMutationState.PREPARED or key != self.prepared_key:
            return False
        self.state = EquipmentMutationState.POSTED
        if self.goal in self._OPPOSING:
            self.last_posted_goal = self.goal
            self.last_posted_core = self.prepared_core
        self.prepared_key = None
        self.prepared_core = None
        self.refusals = 0
        self.board_counted = False
        return True

    def release(self, report: str = "posting-contract:equipment-mutation-released") -> None:
        """Loudly release an operation whose owning observation bound fired."""
        self.state = EquipmentMutationState.IDLE
        self.goal = None
        self.prepared_key = None
        self.prepared_core = None
        self.expected_signature = None
        self.refusals = 0
        self.last_report = report

    def bind_post_snapshot(self, snapshot) -> None:
        """Record alternation progress at post time, never at goal selection time."""
        if self.state == EquipmentMutationState.PREPARED:
            self.prepared_core = progress_core(snapshot)
