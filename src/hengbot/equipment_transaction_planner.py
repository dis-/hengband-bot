"""Pure transaction planning from one complete loadout to another."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from hengbot.equipment_optimizer import (
    Loadout,
    OwnedEquipment,
    SLOT_MAIN_HAND,
    SLOT_MAIN_RING,
    SLOT_SUB_HAND,
    SLOT_SUB_RING,
    equipment_identity,
)


PHASE_HOME_PREPARE = "home_prepare"
PHASE_EQUIP = "equip"
PHASE_HOME_FINALIZE = "home_finalize"


@dataclass(frozen=True)
class EquipmentTransaction:
    phase: str
    kind: str
    item_id: str
    target_slot: str | None = None
    item_identity: str = ""


@dataclass(frozen=True)
class EquipmentTransactionPlan:
    actions: tuple[EquipmentTransaction, ...]
    blockers: tuple[str, ...]
    peak_pack_items: int

    @property
    def executable(self) -> bool:
        return not self.blockers

    def phase(self, name: str) -> tuple[EquipmentTransaction, ...]:
        return tuple(action for action in self.actions if action.phase == name)


_EQUIP_ORDER = {
    "bow": 10,
    "neck": 20,
    "light": 30,
    "body": 40,
    "outer": 50,
    "head": 60,
    "arms": 70,
    "feet": 80,
    SLOT_MAIN_RING: 90,
    SLOT_SUB_RING: 100,
    SLOT_MAIN_HAND: 110,
    SLOT_SUB_HAND: 120,
}


def _slots(loadout: Loadout) -> dict[str, OwnedEquipment]:
    return dict(loadout.slots)


def plan_equipment_transactions(
    items: Iterable[OwnedEquipment],
    current: Loadout,
    target: Loadout,
    *,
    current_pack_items: int,
    home_scan_complete: bool,
    pack_capacity: int = 23,
    preserve_pack_item_ids: frozenset[str] = frozenset(),
) -> EquipmentTransactionPlan:
    """Build a batched, fail-closed Home/equipment transaction plan."""
    catalog = {item.id: item for item in items}
    current_slots = _slots(current)
    target_slots = _slots(target)
    current_ids = current.item_ids
    target_ids = target.item_ids
    blockers: list[str] = []

    missing = sorted(target_ids.difference(catalog))
    blockers.extend(f"missing-item:{item_id}" for item_id in missing)
    retained_in_place = {
        item.id
        for slot, item in current_slots.items()
        if target_slots.get(slot) is not None and target_slots[slot].id == item.id
    }
    for item_id in sorted(target_ids.intersection(catalog)):
        if item_id not in retained_in_place and not catalog[item_id].exploration_legal:
            blockers.append(f"illegal-target:{item_id}")

    target_home = sorted(
        (
            catalog[item_id]
            for item_id in target_ids.intersection(catalog)
            if catalog[item_id].origin == "home"
        ),
        key=lambda item: item.id,
    )
    if target_home and not home_scan_complete:
        blockers.append("home-scan-incomplete")

    changed_current = {
        item.id
        for slot, item in current_slots.items()
        if target_slots.get(slot) is None
        or target_slots[slot].id != item.id
    }
    for item_id in sorted(changed_current):
        item = catalog.get(item_id)
        if item is not None and item.item.is_cursed:
            blockers.append(f"cursed-equipped:{item_id}")

    prepare_deposits = sorted(
        (
            item
            for item in catalog.values()
            if item.origin == "pack"
            and item.id not in target_ids
            and item.id not in preserve_pack_item_ids
        ),
        key=lambda item: item.id,
    )
    actions: list[EquipmentTransaction] = []
    actions.extend(
        EquipmentTransaction(
            PHASE_HOME_PREPARE,
            "deposit",
            item.id,
            item_identity=equipment_identity(item.item),
        )
        for item in prepare_deposits
    )
    actions.extend(
        EquipmentTransaction(
            PHASE_HOME_PREPARE,
            "withdraw",
            item.id,
            item_identity=equipment_identity(item.item),
        )
        for item in target_home
    )

    current_positions = {item.id: slot for slot, item in current_slots.items()}
    takeoffs = sorted(
        (
            (slot, item)
            for slot, item in current_slots.items()
            if target_slots.get(slot) is None
            or target_slots[slot].id != item.id
        ),
        key=lambda entry: (_EQUIP_ORDER.get(entry[0], 1_000), entry[1].id),
        reverse=True,
    )
    # All explicit takeoffs run before any wield command.  They temporarily add
    # one pack item each, which is the true high-water mark for shield removal,
    # ring repositioning, and deliberately empty target slots.
    peak_pack_items = (
        current_pack_items
        - len(prepare_deposits)
        + len(target_home)
        + len(takeoffs)
    )
    if peak_pack_items > pack_capacity:
        blockers.append(f"pack-space-required:{peak_pack_items - pack_capacity}")
    actions.extend(
        EquipmentTransaction(
            PHASE_EQUIP,
            "takeoff",
            item.id,
            slot,
            equipment_identity(item.item),
        )
        for slot, item in takeoffs
    )
    equip_changes = sorted(
        (
            (slot, item)
            for slot, item in target_slots.items()
            if current_slots.get(slot) is None
            or current_slots[slot].id != item.id
        ),
        key=lambda entry: (_EQUIP_ORDER.get(entry[0], 1_000), entry[1].id),
    )
    for slot, item in equip_changes:
        kind = "reposition" if item.id in current_positions else "equip"
        actions.append(
            EquipmentTransaction(
                PHASE_EQUIP,
                kind,
                item.id,
                slot,
                equipment_identity(item.item),
            )
        )

    displaced = sorted(
        (
            catalog[item_id]
            for item_id in current_ids.difference(target_ids)
            if item_id in catalog
        ),
        key=lambda item: item.id,
    )
    actions.extend(
        EquipmentTransaction(
            PHASE_HOME_FINALIZE,
            "deposit",
            item.id,
            item_identity=equipment_identity(item.item),
        )
        for item in displaced
    )
    return EquipmentTransactionPlan(
        tuple(actions), tuple(dict.fromkeys(blockers)), peak_pack_items
    )
