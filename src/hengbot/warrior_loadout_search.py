"""State-compressed loadout generation for Warrior optimization."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Mapping

from hengbot.equipment_optimizer import (
    FIXED_SLOTS,
    SLOT_LIGHT,
    SLOT_MAIN_HAND,
    SLOT_MAIN_RING,
    SLOT_SUB_HAND,
    SLOT_SUB_RING,
    Loadout,
    OwnedEquipment,
    hand_configurations,
    slot_for,
)
from hengbot.warrior_defense_evaluator import PROTECTOR_TVALS, TR_SPEED
from hengbot.warrior_equipment_evaluator import warrior_melee_signature


GEAR_STAGES = (
    SLOT_MAIN_RING,
    SLOT_SUB_RING,
    *FIXED_SLOTS,
)

# Only flags whose addition is monotonic in the current Warrior model may
# participate in superset dominance. Unknown, neutral, and adverse flags remain
# in the exact group key, so this compression cannot silently reinterpret them.
BENEFICIAL_GEAR_FLAGS = frozenset(
    {
        0, 3, 6, 12, 13,  # STR, DEX, device skill, speed, blows (pval in vector)
        32, 33, 34, 35, 36, 37,  # sustains
        39, 40, 41, 42, 43, 45, 46, 47,
        48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63,
        69, 70, 76, 79, 84,  # anti-magic, mana reduction, levitation, telepathy
        143, 144, 145, 157, 163,
    }
)

def _loadout_value_signature(item: OwnedEquipment) -> tuple[object, ...]:
    """Return every item field observed by the Warrior loadout evaluator.

    Physical copies with this exact signature are interchangeable in a loadout.
    Names, origin, stack count, and light fuel deliberately do not participate:
    none changes combat, defense, requirements, or transaction feasibility.
    """
    obj = item.item
    return (
        slot_for(obj),
        obj.tval,
        obj.sval,
        obj.to_h,
        obj.to_d,
        obj.to_a,
        obj.ac,
        obj.damage_dice_num,
        obj.damage_dice_sides,
        obj.pval,
        obj.weight,
        obj.weapon_proficiency,
        item.flags,
        item.exploration_legal,
    )


def _item_dominance_parts(
    item: OwnedEquipment,
) -> tuple[tuple[object, ...], tuple[int, ...], frozenset[int]]:
    """Split the evaluator signature into exact and monotonic components."""
    signature = _loadout_value_signature(item)
    flags = item.flags
    return (
        (
            signature[0],  # slot
            signature[1],  # tval (weapon handling and armour type)
            signature[10],  # weight changes blows and dual-wield penalties
            flags - BENEFICIAL_GEAR_FLAGS,
            signature[13],
        ),
        (
            int(signature[3]),
            int(signature[4]),
            int(signature[5]),
            int(signature[6]),
            int(signature[7]),
            int(signature[8]),
            int(signature[9]),
            int(signature[11]),
        ),
        flags.intersection(BENEFICIAL_GEAR_FLAGS),
    )


def _catalog_dominates(left: OwnedEquipment, right: OwnedEquipment) -> bool:
    left_exact, left_vector, left_flags = _item_dominance_parts(left)
    right_exact, right_vector, right_flags = _item_dominance_parts(right)
    return (
        left_exact == right_exact
        and left_flags.issuperset(right_flags)
        and all(a >= b for a, b in zip(left_vector, right_vector))
        and (left_flags > right_flags or left_vector != right_vector)
    )


def _prune_dominated_catalog(
    items: tuple[OwnedEquipment, ...],
    protected_ids: frozenset[str] = frozenset(),
) -> tuple[OwnedEquipment, ...]:
    """Remove same-slot candidates that cannot improve any Warrior metric."""
    return tuple(
        item
        for item in items
        if item.id in protected_ids
        or not any(
            other.id != item.id and _catalog_dominates(other, item)
            for other in items
        )
    )


def _weapon_contribution_signature(item: OwnedEquipment) -> tuple[object, ...]:
    """Return all per-weapon inputs consumed by melee and defense evaluation."""
    obj = item.item
    return (
        obj.tval,
        obj.to_h,
        obj.to_d,
        obj.to_a,
        obj.ac,
        obj.damage_dice_num,
        obj.damage_dice_sides,
        obj.pval,
        obj.weight,
        obj.weapon_proficiency,
        item.flags,
        item.exploration_legal,
    )


def _deduplicate_melee_weapons(
    items: tuple[OwnedEquipment, ...],
    protected_ids: frozenset[str] = frozenset(),
) -> tuple[OwnedEquipment, ...]:
    """Keep at most the two melee-equivalent copies a loadout can consume."""
    groups: dict[tuple[object, ...], list[OwnedEquipment]] = defaultdict(list)
    non_weapons: list[OwnedEquipment] = []
    for item in items:
        if item.item.tval not in {21, 22, 23}:
            non_weapons.append(item)
            continue
        groups[_weapon_contribution_signature(item)].append(item)
    kept = list(non_weapons)
    for copies in groups.values():
        copies.sort(key=lambda item: (item.id not in protected_ids, item.id))
        kept.extend(copies[:2])
    return tuple(kept)


def _deduplicate_slot_copies(
    items: tuple[OwnedEquipment, ...],
    current_item_ids: frozenset[str],
    pinned: Mapping[str, OwnedEquipment],
) -> tuple[OwnedEquipment, ...]:
    """Keep only the physical copies that a single loadout can consume.

    Fixed slots consume one copy. Rings and melee weapons can consume two, so
    two exact-stat representatives remain. This is lossless state compression,
    not a quality cap: every removed item has an interchangeable kept copy.
    """
    groups: dict[tuple[object, ...], list[OwnedEquipment]] = defaultdict(list)
    for item in items:
        groups[_loadout_value_signature(item)].append(item)

    kept: list[OwnedEquipment] = []
    pinned_ids = frozenset(item.id for item in pinned.values())
    for copies in groups.values():
        order = {item.id: index for index, item in enumerate(copies)}
        copies.sort(
            key=lambda item: (
                item.id not in pinned_ids,
                item.id not in current_item_ids,
                item.origin == "home",
                order[item.id],
            )
        )
        slot = slot_for(copies[0].item)
        capacity = 2 if slot in {SLOT_MAIN_HAND, SLOT_MAIN_RING} else 1
        kept.extend(copies[:capacity])
    return tuple(kept)


def _pval_total(loadout: Loadout, flag: int) -> int:
    return sum(item.item.pval for _, item in loadout.slots if flag in item.flags)


def _acid_armor_count(loadout: Loadout) -> int:
    count = 0
    for slot in ("body", "outer", "arms", "head", "feet"):
        item = loadout.item_at(slot)
        if item is None or item.item.tval not in PROTECTOR_TVALS:
            continue
        if item.item.ac + item.item.to_a > 0 or 84 in item.flags:
            count += 1
    return count


def _gear_state(loadout: Loadout) -> tuple[tuple[object, ...], tuple[int, ...]]:
    melee = warrior_melee_signature(loadout)
    vector = (
        int(melee[3]),
        int(melee[4]),
        int(melee[5]),
        int(melee[6]),
        int(melee[7]),
        int(melee[8]),
        int(melee[9]),
        int(melee[10]),
        _pval_total(loadout, TR_SPEED),
        sum(item.item.ac + item.item.to_a for _, item in loadout.slots),
        _acid_armor_count(loadout),
    )
    key = (
        loadout.hand_mode,
        loadout.flags,
        loadout.item_at(SLOT_LIGHT) is not None,
        vector,
    )
    return key, vector


def _prefer_representative(
    candidate: Loadout,
    incumbent: Loadout,
    current_item_ids: frozenset[str],
) -> bool:
    candidate_overlap = len(candidate.item_ids.intersection(current_item_ids))
    incumbent_overlap = len(incumbent.item_ids.intersection(current_item_ids))
    if candidate_overlap != incumbent_overlap:
        return candidate_overlap > incumbent_overlap
    return tuple(sorted(candidate.item_ids)) < tuple(sorted(incumbent.item_ids))


def _is_current_partial(
    loadout: Loadout,
    processed_slots: tuple[str, ...],
    current_by_slot: dict[str, str],
) -> bool:
    for slot in processed_slots:
        actual = loadout.item_at(slot)
        if (actual.id if actual is not None else None) != current_by_slot.get(slot):
            return False
    return True


def _compress_states(
    states: Iterable[Loadout],
    *,
    processed_slots: tuple[str, ...],
    current_by_slot: dict[str, str],
    current_item_ids: frozenset[str],
) -> tuple[tuple[Loadout, ...], bool]:
    equivalent: dict[tuple[object, ...], Loadout] = {}
    vectors: dict[tuple[object, ...], tuple[int, ...]] = {}
    for state in states:
        key, vector = _gear_state(state)
        incumbent = equivalent.get(key)
        if incumbent is None or _prefer_representative(
            state, incumbent, current_item_ids
        ):
            equivalent[key] = state
            vectors[key] = vector

    groups: dict[
        tuple[object, ...],
        list[tuple[Loadout, tuple[int, ...], frozenset[int]]],
    ] = (
        defaultdict(list)
    )
    for key, state in equivalent.items():
        flags = key[1]
        groups[(key[0], flags - BENEFICIAL_GEAR_FLAGS, key[2])].append(
            (state, vectors[key], flags.intersection(BENEFICIAL_GEAR_FLAGS))
        )

    result: list[Loadout] = []
    for entries in groups.values():
        # If A dominates B, A has either more beneficial flags or the same flag
        # set and a lexicographically no-worse numeric vector. This order therefore
        # guarantees every possible dominator is visited first; no later entry can
        # invalidate an existing frontier member.
        entries.sort(
            key=lambda entry: (
                -len(entry[2]),
                tuple(-value for value in entry[1]),
            )
        )
        frontier: list[tuple[Loadout, tuple[int, ...], frozenset[int]]] = []
        for state, vector, beneficial in entries:
            is_current = _is_current_partial(state, processed_slots, current_by_slot)
            if not is_current and any(
                other_beneficial.issuperset(beneficial)
                and all(left >= right for left, right in zip(other_vector, vector))
                and (
                    other_beneficial > beneficial
                    or any(
                        left > right for left, right in zip(other_vector, vector)
                    )
                )
                for _, other_vector, other_beneficial in frontier
            ):
                continue
            frontier.append((state, vector, beneficial))
        result.extend(state for state, _, _ in frontier)
    return tuple(result), False


def _slot_choices(
    slot: str,
    legal: tuple[OwnedEquipment, ...],
    pinned: Mapping[str, OwnedEquipment],
) -> tuple[OwnedEquipment | None, ...]:
    if slot in pinned:
        return (pinned[slot],)
    if slot in {SLOT_MAIN_RING, SLOT_SUB_RING}:
        candidates = tuple(item for item in legal if item.item.tval == 45)
    else:
        candidates = tuple(item for item in legal if slot_for(item.item) == slot)
    return (None, *candidates)


def _gear_states(
    legal: tuple[OwnedEquipment, ...],
    *,
    hand_mode: str,
    current_by_slot: dict[str, str],
    current_item_ids: frozenset[str],
    pinned: Mapping[str, OwnedEquipment],
) -> tuple[tuple[Loadout, ...], bool]:
    states = (Loadout((), hand_mode),)
    processed: tuple[str, ...] = ()
    truncated = False
    for slot in GEAR_STAGES:
        expanded: list[Loadout] = []
        for state in states:
            main_ring = state.item_at(SLOT_MAIN_RING)
            for candidate in _slot_choices(slot, legal, pinned):
                if (
                    slot == SLOT_SUB_RING
                    and candidate is not None
                    and main_ring is not None
                    and candidate.id == main_ring.id
                ):
                    continue
                slots = state.slots
                if candidate is not None:
                    slots = (*slots, (slot, candidate))
                expanded.append(Loadout(slots, hand_mode))
        processed = (*processed, slot)
        states, stage_truncated = _compress_states(
            expanded,
            processed_slots=processed,
            current_by_slot=current_by_slot,
            current_item_ids=current_item_ids,
        )
        truncated = truncated or stage_truncated
    return states, truncated


@dataclass
class WarriorLoadoutSearch:
    items: tuple[OwnedEquipment, ...]
    current_item_ids: frozenset[str] = frozenset()
    pinned: Mapping[str, OwnedEquipment] = field(default_factory=dict)
    excluded_item_ids: frozenset[str] = frozenset()
    truncated: bool = field(default=False, init=False)

    def __iter__(self) -> Iterator[Loadout]:
        legal_items = [
            item for item in self.items
            if item.exploration_legal and item.id not in self.excluded_item_ids
        ]
        protected_ids = self.current_item_ids.union(
            item.id for item in self.pinned.values()
        )
        legal = _deduplicate_slot_copies(
            tuple(
                [
                    *legal_items,
                    *(
                        item
                        for item in self.pinned.values()
                        if item not in legal_items
                    ),
                ]
            ),
            self.current_item_ids,
            self.pinned,
        )
        legal = _prune_dominated_catalog(legal, protected_ids)
        legal = _deduplicate_melee_weapons(legal, protected_ids)
        current_by_slot = {
            item.equipped_slot: item.id
            for item in legal
            if item.id in self.current_item_ids and item.equipped_slot is not None
        }
        configurations_by_mode = defaultdict(list)
        for hands in hand_configurations(legal, self.pinned):
            configurations_by_mode[hands.mode].append(hands)

        gear_by_profile: dict[str, tuple[tuple[Loadout, ...], bool]] = {}
        for mode, configurations in configurations_by_mode.items():
            profile = (
                mode
                if mode in {"two_handed", "dual_wield"}
                else "one_handed"
            )
            cached = gear_by_profile.get(profile)
            if cached is None:
                cached = _gear_states(
                    legal,
                    hand_mode=profile,
                    current_by_slot=current_by_slot,
                    current_item_ids=self.current_item_ids,
                    pinned=self.pinned,
                )
                gear_by_profile[profile] = cached
            gear_states, gear_truncated = cached
            self.truncated = self.truncated or gear_truncated
            for hands in configurations:
                for gear in gear_states:
                    slots = list(gear.slots)
                    if hands.main is not None:
                        slots.append((SLOT_MAIN_HAND, hands.main))
                    if hands.sub is not None:
                        slots.append((SLOT_SUB_HAND, hands.sub))
                    yield Loadout(tuple(slots), hands.mode)


def enumerate_warrior_loadouts(
    items: Iterable[OwnedEquipment],
    *,
    current_item_ids: frozenset[str] = frozenset(),
    pinned: Mapping[str, OwnedEquipment] | None = None,
    excluded_item_ids: frozenset[str] = frozenset(),
) -> WarriorLoadoutSearch:
    """Yield the exact nondominated Warrior loadout representatives."""
    return WarriorLoadoutSearch(
        tuple(items), current_item_ids, pinned or {}, excluded_item_ids
    )
