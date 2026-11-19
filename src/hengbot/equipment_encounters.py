"""Depth-weighted monster encounters used by equipment evaluation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Mapping

from hengbot.monrace_knowledge import MonraceKnowledge


@dataclass(frozen=True)
class EncounterTarget:
    race_id: int
    weight: float
    knowledge: MonraceKnowledge


# Weapon flag, monster kind flag, source multiplier in tenths.
SLAYS = (
    (16, "ANIMAL", 25),
    (96, "ANIMAL", 40),
    (17, "EVIL", 20),
    (97, "EVIL", 35),
    (75, "GOOD", 20),
    (95, "GOOD", 35),
    (66, "HUMAN", 25),
    (103, "HUMAN", 40),
    (18, "UNDEAD", 30),
    (98, "UNDEAD", 50),
    (19, "DEMON", 30),
    (99, "DEMON", 50),
    (20, "ORC", 30),
    (100, "ORC", 50),
    (21, "TROLL", 30),
    (101, "TROLL", 50),
    (22, "GIANT", 30),
    (102, "GIANT", 50),
    (23, "DRAGON", 30),
    (24, "DRAGON", 50),
)

# Weapon flag, monster immunity, monster vulnerability.
BRANDS = (
    (28, "IM_ACID", None),
    (29, "IM_ELEC", None),
    (30, "IM_FIRE", "HURT_FIRE"),
    (31, "IM_COLD", "HURT_COLD"),
    (27, "IM_POIS", None),
)

EXCLUDED_NORMAL_FLAGS = frozenset(
    {"QUESTOR", "GUARDIAN", "WILD_ONLY", "FRIENDLY"}
)


def normal_encounters(
    knowledge: Mapping[int, MonraceKnowledge],
    depth: int,
    *,
    permitted: Callable[[MonraceKnowledge], bool] | None = None,
) -> tuple[EncounterTarget, ...]:
    """Approximate get_mon_num's ordinary pool using its exact base weights.

    Dungeon-specific terrain and theme restrictions can be supplied through
    ``permitted``. Out-of-depth selection is intentionally excluded: the agreed
    policy values common enemies, while rare exceptional enemies are avoided.

    The draw (owner 2026-11-20 「吸血も評価に入れて直す」 with the population by
    depth): get_mon_num (src/monster/monster-list.cpp) draws 1 race (40%), 2
    (50%) or 3 (10%) from the pool and keeps the highest level, so a race's
    chance is its level's share of P(max level = L) split by base weight
    (``draw_weights``), not its base weight alone.
    """
    weighted: list[tuple[int, int, MonraceKnowledge]] = []
    for race_id, monster in knowledge.items():
        if race_id == 0 or monster.rarity <= 0 or monster.level > depth:
            continue
        if monster.flags.intersection(EXCLUDED_NORMAL_FLAGS):
            continue
        if permitted is not None and not permitted(monster):
            continue
        probability = 100 // monster.rarity
        if probability > 0:
            weighted.append((race_id, probability, monster))
    total = sum(weight for _, weight, _ in weighted)
    if total == 0:
        return ()
    shares = draw_weights(
        [(race_id, weight, monster.level) for race_id, weight, monster in weighted])
    return tuple(
        EncounterTarget(race_id, shares[race_id], monster)
        for race_id, _, monster in weighted
    )


# get_mon_num's draw count: 40% one, 50% two, 10% three (p < 60 adds one, p < 10 another).
DRAW_COUNT_PROBABILITIES = ((1, 0.4), (2, 0.5), (3, 0.1))


def draw_weights(pool: list[tuple[int, int, int]]) -> dict[int, float]:
    """{race: chance} of get_mon_num's highest-level-of-n draw over ``pool``.

    ``pool`` holds (race, base weight, level).  With F(L) the base-weight share
    of the levels up to L, the kept race's level is L with probability
    sum_n p_n (F(L)^n - F(L-1)^n); within a level the first drawn of that level
    is kept (std::max_element), so the level's chance splits by base weight.
    """
    total = sum(weight for _, weight, _ in pool)
    by_level: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for race_id, weight, level in pool:
        by_level[level].append((race_id, weight))
    shares: dict[int, float] = {}
    below = 0.0
    for level in sorted(by_level):
        members = by_level[level]
        level_weight = sum(weight for _, weight in members)
        upto = below + level_weight / total
        level_chance = sum(
            probability * (upto ** count - below ** count)
            for count, probability in DRAW_COUNT_PROBABILITIES
        )
        for race_id, weight in members:
            shares[race_id] = level_chance * weight / level_weight
        below = upto
    return shares


def ordinary_encounters(
    encounters: tuple[EncounterTarget, ...],
) -> tuple[EncounterTarget, ...]:
    """The non-unique encounters, their weights summing to 1 (the sample's pool)."""
    ordinary = [encounter for encounter in encounters
                if "UNIQUE" not in encounter.knowledge.flags]
    total = sum(encounter.weight for encounter in ordinary)
    if total <= 0:
        return ()
    return tuple(EncounterTarget(encounter.race_id, encounter.weight / total,
                                 encounter.knowledge) for encounter in ordinary)


def representative_encounters(
    encounters: tuple[EncounterTarget, ...],
    *,
    max_count: int = 64,
) -> tuple[EncounterTarget, ...]:
    """Sample the non-unique enemies while preserving depth-band mass.

    This is the explicit terminal-scale model simplification: rare exceptional
    enemies are handled by avoidance policy, while equipment is optimized for a
    deterministic, frequency-weighted sample of ordinary enemies.
    """
    ordinary = tuple(
        encounter
        for encounter in encounters
        if "UNIQUE" not in encounter.knowledge.flags
    )
    if max_count <= 0:
        return ()
    if len(ordinary) <= max_count:
        total = sum(encounter.weight for encounter in ordinary)
        return tuple(
            EncounterTarget(
                encounter.race_id,
                encounter.weight / total,
                encounter.knowledge,
            )
            for encounter in ordinary
        ) if total > 0 else ()

    bands: dict[int, list[EncounterTarget]] = defaultdict(list)
    for encounter in ordinary:
        bands[encounter.knowledge.level // 10].append(encounter)
    total_weight = sum(encounter.weight for encounter in ordinary)
    exact_quotas = {
        band: max_count
        * sum(encounter.weight for encounter in members)
        / total_weight
        for band, members in bands.items()
    }
    quotas = {
        band: min(len(bands[band]), max(1, int(quota)))
        for band, quota in exact_quotas.items()
    }
    while sum(quotas.values()) < max_count:
        candidates = [
            band for band in bands if quotas[band] < len(bands[band])
        ]
        if not candidates:
            break
        band = max(candidates, key=lambda value: exact_quotas[value] - quotas[value])
        quotas[band] += 1
    while sum(quotas.values()) > max_count:
        candidates = [band for band in bands if quotas[band] > 1]
        if not candidates:
            break
        band = min(candidates, key=lambda value: exact_quotas[value] - quotas[value])
        quotas[band] -= 1

    selected: list[EncounterTarget] = []
    for band, members in bands.items():
        band_weight = sum(encounter.weight for encounter in members)
        selected.extend(
            EncounterTarget(encounter.race_id, band_weight / quotas[band], encounter.knowledge)
            for encounter in _systematic_sample(members, quotas[band])
        )
    selected_total = sum(encounter.weight for encounter in selected)
    return tuple(
        EncounterTarget(
            encounter.race_id,
            encounter.weight / selected_total,
            encounter.knowledge,
        )
        for encounter in selected
    )


def _systematic_sample(
    members: list[EncounterTarget], count: int,
) -> list[EncounterTarget]:
    """``count`` distinct members at even steps of the band's cumulative weight.

    Each carries an equal share of the band (representative_encounters), so
    the sample keeps the band's mix of kinds.  Taking the heaviest members
    instead (before 2026-11-20) kept the races of rarity 1, many of them
    dragons: n1-b life-411's 95F sample held 30% dragons against 12.5% of the
    pool, and ★アイシングデス's dragon slaying decided the weapon.  Members are
    ordered by level and race; a step landing on a member already taken takes
    the next one not taken.
    """
    ordered = sorted(members, key=lambda encounter: (encounter.knowledge.level, encounter.race_id))
    total = sum(encounter.weight for encounter in ordered)
    taken: list[int] = []
    cumulative = 0.0
    index = 0
    for step in range(count):
        target = (step + 0.5) * total / count
        while index < len(ordered) - 1 and cumulative + ordered[index].weight < target:
            cumulative += ordered[index].weight
            index += 1
        pick = index
        while pick in taken:
            pick = (pick + 1) % len(ordered)
        taken.append(pick)
    return [ordered[pick] for pick in sorted(taken)]


def melee_multiplier(
    weapon_flags: frozenset[int], monster: MonraceKnowledge
) -> int:
    """Port mult_slaying() and mult_brand() for an ordinary Warrior attack."""
    multiplier = 10
    for weapon_flag, monster_flag, value in SLAYS:
        if weapon_flag in weapon_flags and monster_flag in monster.flags:
            multiplier = max(multiplier, value)
    for weapon_flag, immunity, vulnerability in BRANDS:
        if weapon_flag not in weapon_flags:
            continue
        if "RES_ALL" in monster.flags or immunity in monster.flags:
            continue
        value = 50 if vulnerability is not None and vulnerability in monster.flags else 25
        multiplier = max(multiplier, value)
    return multiplier
