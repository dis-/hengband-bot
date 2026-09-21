"""Percentile melee damage over a threat-prediction horizon.

User-confirmed specification 2026-09-22 (topic melee-threat-p95-adjacency):
the operational melee value of one monster is the TRUE 95th percentile of its
melee damage over the horizon, mirroring the approved ranged model
(``aggregate_ranged_damage_percentile``): one exact damage distribution per
monster action, convolved over the action count, read at the percentile, with
the ranged model's single-hit lower bound when the aggregate percentile is zero
despite a positive chance of damage.  No sampling: the distributions are exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from hengbot.monster_ranged_evaluator import (
    _dense_damage_distribution,
    _dice_distribution,
    _distribution_percentile,
)


# One blow: (hit probability, reduced damage distribution given a hit).
MeleeBlowDistribution = tuple[float, tuple[tuple[int, float], ...]]


@dataclass(frozen=True)
class MeleeDamagePercentile:
    total_damage: int
    expected_per_action: float
    probability_any_damage: float
    single_hit_floor: int
    floor_applied: bool


def reduced_dice_distribution(
    number: int, sides: int, reduce
) -> tuple[tuple[int, float], ...]:
    """Distribution of ``reduce(roll)`` for an ``number``d``sides`` roll."""
    distribution = _dice_distribution(number, sides)
    outcomes = sum(count for _, count in distribution)
    result: dict[int, float] = {}
    for roll, count in distribution:
        damage = reduce(roll)
        result[damage] = result.get(damage, 0.0) + count / outcomes
    return tuple(sorted(result.items()))


@lru_cache(maxsize=4096)
def melee_damage_percentile(
    blows: tuple[MeleeBlowDistribution, ...],
    attacks: int,
    percentile: int = 95,
) -> MeleeDamagePercentile:
    """Return the percentile total of ``attacks`` monster actions.

    Every action attempts every blow; a blow hits with its own probability and
    then deals a value drawn from its (already reduced) dice distribution.
    """
    if not 1 <= percentile <= 100:
        raise ValueError(f"percentile must be in [1, 100]: {percentile}")
    per_action = np.ones(1, dtype=np.float64)
    expected_per_action = 0.0
    single_hit_floor = 0
    for hit_probability, damage_distribution in blows:
        hit_probability = min(1.0, max(0.0, hit_probability))
        conditional: dict[int, float] = {0: 1.0 - hit_probability}
        for damage, probability in damage_distribution:
            conditional[damage] = (
                conditional.get(damage, 0.0) + hit_probability * probability
            )
            expected_per_action += hit_probability * probability * damage
        per_action = np.convolve(
            per_action, _dense_damage_distribution(conditional)
        )
        if hit_probability > 0.0 and any(
            damage > 0 for damage, _ in damage_distribution
        ):
            single_hit_floor = max(
                single_hit_floor,
                _distribution_percentile(damage_distribution, percentile),
            )
    aggregate = np.ones(1, dtype=np.float64)
    for _ in range(max(0, attacks)):
        aggregate = np.convolve(aggregate, per_action)
    cumulative = np.cumsum(aggregate)
    total_damage = min(
        int(
            np.searchsorted(
                cumulative, percentile / 100.0 - 1e-12, side="left"
            )
        ),
        aggregate.size - 1,
    )
    probability_any_damage = max(0.0, 1.0 - float(aggregate[0]))
    floor_applied = (
        total_damage == 0
        and probability_any_damage > 1e-12
        and single_hit_floor > 0
    )
    if floor_applied:
        total_damage = single_hit_floor
    return MeleeDamagePercentile(
        total_damage=total_damage,
        expected_per_action=expected_per_action,
        probability_any_damage=probability_any_damage,
        single_hit_floor=single_hit_floor,
        floor_applied=floor_applied,
    )
