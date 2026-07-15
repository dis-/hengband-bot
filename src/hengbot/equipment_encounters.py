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
    return tuple(
        EncounterTarget(race_id, weight / total, monster)
        for race_id, weight, monster in weighted
    )


def representative_encounters(
    encounters: tuple[EncounterTarget, ...],
    *,
    max_count: int = 64,
) -> tuple[EncounterTarget, ...]:
    """Keep common non-unique enemies while preserving depth-band mass.

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
        members.sort(
            key=lambda encounter: (
                encounter.weight,
                encounter.knowledge.level,
                encounter.knowledge.average_hp,
            ),
            reverse=True,
        )
        chosen = members[: quotas[band]]
        band_weight = sum(encounter.weight for encounter in members)
        chosen_weight = sum(encounter.weight for encounter in chosen)
        selected.extend(
            EncounterTarget(
                encounter.race_id,
                band_weight * encounter.weight / chosen_weight,
                encounter.knowledge,
            )
            for encounter in chosen
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
