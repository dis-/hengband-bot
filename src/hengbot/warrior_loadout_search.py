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

EXACT_PARTIAL_STATE_LIMIT = 10_000
PARTIAL_BEAM_WIDTH = 256
EXACT_HAND_CONFIGURATION_LIMIT = 1_000
HAND_BEAM_WIDTH = 256
LARGE_CATALOG_SIZE = 100
LARGE_EXACT_PARTIAL_STATE_LIMIT = 2_000
LARGE_PARTIAL_BEAM_WIDTH = 32
LARGE_EXACT_HAND_CONFIGURATION_LIMIT = 500
LARGE_HAND_BEAM_WIDTH = 32


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
    force_beam: bool = False,
    exact_limit: int = EXACT_PARTIAL_STATE_LIMIT,
    beam_width: int = PARTIAL_BEAM_WIDTH,
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

    if force_beam or len(equivalent) > exact_limit:
        return (
            _diverse_state_beam(
                tuple(equivalent.values()),
                processed_slots=processed_slots,
                current_by_slot=current_by_slot,
                width=beam_width,
            ),
            True,
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


def _state_scores(loadout: Loadout) -> tuple[int, int, int, int]:
    _, vector = _gear_state(loadout)
    beneficial = loadout.flags.intersection(BENEFICIAL_GEAR_FLAGS)
    offense = (
        20 * vector[0]
        + 10 * vector[1]
        + 5 * (vector[2] + vector[4])
        + 10 * (vector[3] + vector[5])
        + 100 * (vector[6] + vector[7])
    )
    defense = 100 * vector[8] + 5 * vector[9] + 10 * vector[10]
    utility = 50 * len(beneficial)
    utility += 150 * int(69 in beneficial)
    utility += 200 * int(79 in beneficial)
    balanced = offense + defense + utility
    return offense, defense, utility, balanced


def _diverse_state_beam(
    states: tuple[Loadout, ...],
    *,
    processed_slots: tuple[str, ...],
    current_by_slot: dict[str, str],
    width: int,
) -> tuple[Loadout, ...]:
    selected: dict[tuple[tuple[str, str], ...], Loadout] = {}

    def add(state: Loadout) -> None:
        if len(selected) < width:
            key = tuple(sorted((slot, item.id) for slot, item in state.slots))
            selected.setdefault(key, state)

    for state in states:
        if _is_current_partial(state, processed_slots, current_by_slot):
            add(state)

    scored = [(state, _state_scores(state)) for state in states]
    rankings = (
        sorted(scored, key=lambda entry: entry[1][0], reverse=True),
        sorted(scored, key=lambda entry: entry[1][1], reverse=True),
        sorted(scored, key=lambda entry: entry[1][2], reverse=True),
        sorted(scored, key=lambda entry: entry[1][3], reverse=True),
    )
    index = 0
    while len(selected) < width and any(index < len(ranking) for ranking in rankings):
        for ranking in rankings:
            if index < len(ranking):
                add(ranking[index][0])
        index += 1
    return tuple(selected.values())


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
    exact_limit: int = EXACT_PARTIAL_STATE_LIMIT,
    beam_width: int = PARTIAL_BEAM_WIDTH,
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
            force_beam=truncated,
            exact_limit=exact_limit,
            beam_width=beam_width,
        )
        truncated = truncated or stage_truncated
    return states, truncated


def _hand_score(hands) -> int:
    score = 0
    for item in (hands.main, hands.sub):
        if item is None:
            continue
        obj = item.item
        score += obj.damage_dice_num * (obj.damage_dice_sides + 1) * 5
        score += obj.to_h * 5 + obj.to_d * 10
        score += obj.ac + obj.to_a * 5
        score += 30 * len(item.flags.intersection(BENEFICIAL_GEAR_FLAGS))
    return score


def _limit_hand_configurations(
    configurations,
    current_hand_ids,
    *,
    exact_limit=EXACT_HAND_CONFIGURATION_LIMIT,
    beam_width=HAND_BEAM_WIDTH,
):
    configurations = tuple(configurations)
    if len(configurations) <= exact_limit:
        return configurations, False
    current = [
        hands
        for hands in configurations
        if frozenset(
            item.id for item in (hands.main, hands.sub) if item is not None
        ) == current_hand_ids
    ]
    ranked = sorted(configurations, key=_hand_score, reverse=True)
    selected = []
    seen = set()
    for hands in (*current, *ranked):
        key = (
            hands.main.id if hands.main is not None else None,
            hands.sub.id if hands.sub is not None else None,
            hands.mode,
        )
        if key in seen:
            continue
        seen.add(key)
        selected.append(hands)
        if len(selected) >= beam_width:
            break
    return tuple(selected), True


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
        current_by_slot = {
            item.equipped_slot: item.id
            for item in legal
            if item.id in self.current_item_ids and item.equipped_slot is not None
        }
        current_hand_ids = frozenset(
            item.id
            for item in legal
            if item.id in self.current_item_ids
            and item.equipped_slot in {SLOT_MAIN_HAND, SLOT_SUB_HAND}
        )
        large = len(legal) >= LARGE_CATALOG_SIZE
        partial_exact_limit = (
            LARGE_EXACT_PARTIAL_STATE_LIMIT
            if large
            else EXACT_PARTIAL_STATE_LIMIT
        )
        partial_beam_width = (
            LARGE_PARTIAL_BEAM_WIDTH if large else PARTIAL_BEAM_WIDTH
        )
        hand_exact_limit = (
            LARGE_EXACT_HAND_CONFIGURATION_LIMIT
            if large
            else EXACT_HAND_CONFIGURATION_LIMIT
        )
        hand_beam_width = LARGE_HAND_BEAM_WIDTH if large else HAND_BEAM_WIDTH
        configurations_by_mode = defaultdict(list)
        for hands in hand_configurations(legal, self.pinned):
            configurations_by_mode[hands.mode].append(hands)

        gear_by_profile: dict[str, tuple[tuple[Loadout, ...], bool]] = {}
        for mode, configurations in configurations_by_mode.items():
            limited, hands_truncated = _limit_hand_configurations(
                configurations,
                current_hand_ids,
                exact_limit=hand_exact_limit,
                beam_width=hand_beam_width,
            )
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
                    exact_limit=partial_exact_limit,
                    beam_width=partial_beam_width,
                )
                gear_by_profile[profile] = cached
            gear_states, gear_truncated = cached
            self.truncated = self.truncated or hands_truncated or gear_truncated
            for hands in limited:
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
    """Yield exact representatives, with a bounded fallback for large catalogs."""
    return WarriorLoadoutSearch(
        tuple(items), current_item_ids, pinned or {}, excluded_item_ids
    )
