"""Pure transaction planning from one complete loadout to another."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from hengbot.equipment_optimizer import (
    Loadout,
    OwnedEquipment,
    SLOT_MAIN_HAND,
    SLOT_MAIN_RING,
    SLOT_LIGHT,
    SLOT_SUB_HAND,
    SLOT_SUB_RING,
    equipment_identity,
    equipment_move_identity,
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
    move_identity: str = ""


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
    retain_item_identities: frozenset[str] = frozenset(),
    preserve_worn_light: bool = False,
    home_deposit_available: bool = True,
) -> EquipmentTransactionPlan:
    """Build a batched, fail-closed Home/equipment transaction plan."""
    catalog = {item.id: item for item in items}
    current_slots = _slots(current)
    target_slots = _slots(target)
    # Restoration-owned worn items are loadout members, not Home surplus.  A
    # temporarily incomplete optimizer view must not turn them into an
    # implicit takeoff-and-shelve transaction while restoration still owns
    # their physical identity.
    for slot, item in current_slots.items():
        if item.id in preserve_pack_item_ids:
            target_slots.setdefault(slot, item)
    # An excluded refuel candidate is absent from the optimizer pool, but that
    # must never turn the worn source into an implicit takeoff transaction.
    if (
        preserve_worn_light
        and SLOT_LIGHT not in target_slots
        and SLOT_LIGHT in current_slots
    ):
        target_slots[SLOT_LIGHT] = current_slots[SLOT_LIGHT]
    current_ids = current.item_ids
    target_ids = frozenset(item.id for item in target_slots.values())
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
            move_identity=equipment_move_identity(item.item),
        )
        for item in prepare_deposits
    )
    actions.extend(
        EquipmentTransaction(
            PHASE_HOME_PREPARE,
            "withdraw",
            item.id,
            item_identity=equipment_identity(item.item),
            move_identity=equipment_move_identity(item.item),
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
        - (len(prepare_deposits) if home_deposit_available else 0)
        + len(target_home)
        + len(takeoffs)
    )
    actions.extend(
        EquipmentTransaction(
            PHASE_EQUIP,
            "takeoff",
            item.id,
            slot,
            equipment_identity(item.item),
            equipment_move_identity(item.item),
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
                equipment_move_identity(item.item),
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
            move_identity=equipment_move_identity(item.item),
        )
        for item in displaced
        if equipment_identity(item.item) not in retain_item_identities
    )
    if peak_pack_items > pack_capacity:
        # Keep the all-at-once plan above when it fits. Otherwise build one
        # capacity-safe batch from complete slot changes; each rebuilt batch
        # must include at least one observable slot change.  A full Home never
        # removes a planned deposit (its refusal is the step-1.5a record); it
        # only stops the deposit from being counted as freed pack space.
        deposit_credit = 1 if home_deposit_available else 0
        pack = current_pack_items
        staged = []
        for action in actions:
            if action.phase == PHASE_HOME_PREPARE and action.kind == "deposit":
                staged.append(action)
                pack -= deposit_credit
        original = {
            (action.kind, action.target_slot or action.item_id): action
            for action in actions
        }
        emitted = set(staged)
        changed = sorted(
            (
                slot for slot in set(current_slots) | set(target_slots)
                if current_slots.get(slot) is None
                or target_slots.get(slot) is None
                or current_slots[slot].id != target_slots[slot].id
            ),
            key=lambda slot: (_EQUIP_ORDER.get(slot, 1_000), slot),
        )
        completed_slots = set()
        staged_peak = pack
        minimum_shortfall = None
        target_item_ids = {item.id for item in target_slots.values()}
        finalize_deposits = {
            action.item_id: action for action in actions
            if action.phase == PHASE_HOME_FINALIZE
            and action.item_identity not in retain_item_identities
        }
        for slot in changed:
            if slot in completed_slots:
                continue
            target = target_slots.get(slot)
            old = current_slots.get(slot)
            withdrawal = None
            if target is not None and target.origin == "home":
                candidate = original.get(("withdraw", target.id))
                if candidate is not None and candidate not in emitted:
                    withdrawal = candidate
            source_slot = current_positions.get(target.id) if target is not None else None
            takeoff_items = []
            if source_slot is not None and source_slot != slot:
                takeoff_items.append((source_slot, current_slots[source_slot]))
            if old is not None and (target is None or old.id != target.id):
                takeoff_items.append((slot, old))
            takeoff_items.sort(
                key=lambda entry: (_EQUIP_ORDER.get(entry[0], 1_000), entry[1].id),
                reverse=True,
            )
            takeoff_actions = []
            for takeoff_slot, item in takeoff_items:
                candidate = original.get(("takeoff", takeoff_slot))
                if candidate is not None and candidate not in emitted:
                    takeoff_actions.append((item, candidate))
            equip_action = None
            if target is not None and (old is None or old.id != target.id):
                kind = "reposition" if target.id in current_positions else "equip"
                candidate = original.get((kind, slot))
                if candidate is not None and candidate not in emitted:
                    equip_action = candidate

            deposits = []
            for item, _action in takeoff_actions:
                deposit = finalize_deposits.get(item.id)
                if (item.id not in target_item_ids and deposit is not None
                        and deposit not in emitted):
                    deposits.append((item.id, deposit))
            deposit_by_item = dict(deposits)
            # Preferred order keeps every slot worn until its replacement is in
            # the pack: withdraw, take off, wield, then store the old item.
            in_place = []
            if withdrawal is not None:
                in_place.append(withdrawal)
            in_place.extend(action for _item, action in takeoff_actions)
            if equip_action is not None:
                in_place.append(equip_action)
            in_place.extend(deposit for _item_id, deposit in deposits)
            # Fallback when that does not fit and Home has room: store each
            # displaced occupant before fetching the replacement.
            deposit_first = []
            if home_deposit_available and deposits:
                for item, action in takeoff_actions:
                    deposit_first.append(action)
                    if item.id in deposit_by_item:
                        deposit_first.append(deposit_by_item[item.id])
                if withdrawal is not None:
                    deposit_first.append(withdrawal)
                if equip_action is not None:
                    deposit_first.append(equip_action)
            group = None
            group_peak = next_pack = pack
            for candidate_group in (in_place, deposit_first):
                if not candidate_group:
                    continue
                count = peak = pack
                for action in candidate_group:
                    if action.kind in {"withdraw", "takeoff"}:
                        count += 1
                    elif action.kind in {"equip", "reposition"}:
                        count -= 1
                    elif action.kind == "deposit":
                        count -= deposit_credit
                    peak = max(peak, count)
                if peak <= pack_capacity:
                    group, group_peak, next_pack = candidate_group, peak, count
                    break
                shortfall = peak - pack_capacity
                minimum_shortfall = (shortfall if minimum_shortfall is None
                                     else min(minimum_shortfall, shortfall))
            if group is None:
                continue
            staged.extend(group)
            emitted.update(group)
            pack = next_pack
            staged_peak = max(staged_peak, group_peak)
            completed_slots.add(slot)
            if (target is not None and source_slot is not None
                    and target_slots.get(source_slot) is None):
                completed_slots.add(source_slot)

        if any(action.kind in {"takeoff", "equip", "reposition"} for action in staged):
            return EquipmentTransactionPlan(tuple(staged), tuple(blockers), staged_peak)
        blockers.append(f"pack-space-required:{minimum_shortfall or 1}")
    return EquipmentTransactionPlan(
        tuple(actions), tuple(dict.fromkeys(blockers)), peak_pack_items
    )
