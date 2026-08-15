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

    _OPPOSING = frozenset({"mining-loadout", "combat-loadout"})

    def observe(self, snapshot) -> None:
        if (
            self.state == EquipmentMutationState.POSTED
            and equipment_signature(snapshot) != self.expected_signature
        ):
            self.state = EquipmentMutationState.IDLE
            self.goal = None
            self.expected_signature = None
            self.refusals = 0
            self.last_report = None

    def _begin(self, snapshot, goal: str) -> EquipmentMutationResult | None:
        self.observe(snapshot)
        if self.state == EquipmentMutationState.POSTED:
            self.refusals += 1
            if self.refusals >= 8:
                self.state = EquipmentMutationState.IDLE
                self.goal = None
                self.expected_signature = None
                self.refusals = 0
                self.last_report = "posting-contract:equipment-mutation-released"
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

    def _prepare(self, snapshot, goal: str, key: str) -> EquipmentMutationResult:
        refusal = self._begin(snapshot, goal)
        if refusal is not None:
            return refusal
        self.state = EquipmentMutationState.PREPARED
        self.goal = goal
        self.prepared_key = key
        self.expected_signature = equipment_signature(snapshot)
        self.prepared_core = progress_core(snapshot)
        self.last_report = None
        return EquipmentMutationResult(key)

    def request_takeoff(self, snapshot, goal: str, slot_key: str) -> EquipmentMutationResult:
        return self._prepare(snapshot, goal, TAKEOFF_KEY + slot_key)

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
            if main is not None and sub is not None:
                suffix = slot_keys[target_slot]
            elif main is not None:
                suffix = "y" if target_slot == "sub_hand" else "n"
            elif sub is not None and (sub.is_melee_weapon or sub.is_digging_tool):
                suffix = "y" if target_slot == "main_hand" else "n"
        elif tval in {TVAL_SHIELD, TVAL_CAPTURE, TVAL_CARD}:
            main_melee = main is not None and (main.is_melee_weapon or main.is_digging_tool)
            sub_melee = sub is not None and (sub.is_melee_weapon or sub.is_digging_tool)
            if main_melee and sub_melee:
                suffix = slot_keys[target_slot]
            elif main is not None and sub is not None and (
                tval == TVAL_CAPTURE or not main_melee and not sub_melee
            ):
                suffix = slot_keys[target_slot]
        elif tval == TVAL_RING:
            suffix = "(" if target_slot == "main_ring" else ")"
        return self._prepare(snapshot, goal, WIELD_KEY + item.slot + suffix)

    def confirm_posted(self, key: str) -> bool:
        if self.state != EquipmentMutationState.PREPARED or key != self.prepared_key:
            return False
        self.state = EquipmentMutationState.POSTED
        self.last_posted_goal = self.goal
        self.last_posted_core = self.prepared_core
        self.prepared_key = None
        self.prepared_core = None
        self.refusals = 0
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
