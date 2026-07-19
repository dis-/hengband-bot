"""Hengband-source-compatible Warrior melee arithmetic.

This module is intentionally a formula layer, not a policy heuristic.  It ports
the integer operations used by Hengband for stats, blows, hit chance, and normal
weapon criticals.  Encounter weighting and survival are added by the caller;
until those inputs are complete this module must not drive equipment changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping

from hengbot.equipment_optimizer import (
    Loadout,
    OwnedEquipment,
    SLOT_MAIN_HAND,
    SLOT_MAIN_RING,
    SLOT_SUB_HAND,
    SLOT_SUB_RING,
)
from hengbot.equipment_encounters import BRANDS, EncounterTarget, melee_multiplier


TR_STR = 0
TR_DEX = 3
TR_BLOWS = 13
TR_IMPACT = 151
TR_SUPPORTIVE = 147

AC_REFERENCE = 100
BEGINNER_WEAPON_EXP = 4000

ADJ_STR_BLOW = (
    3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 20, 30,
    40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160,
    170, 180, 190, 200, 210, 220, 230, 240,
)
ADJ_DEX_BLOW = (
    0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3,
    4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12,
    12, 13,
)
BLOWS_TABLE = (
    (1, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 4),
    (1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4),
    (1, 1, 2, 2, 3, 3, 4, 4, 4, 5, 5, 5),
    (1, 1, 2, 3, 3, 4, 4, 4, 5, 5, 5, 5),
    (1, 1, 2, 3, 3, 4, 4, 5, 5, 5, 5, 5),
    (1, 1, 2, 3, 4, 4, 4, 5, 5, 5, 5, 6),
    (1, 1, 2, 3, 4, 4, 4, 5, 5, 5, 5, 6),
    (1, 2, 2, 3, 4, 4, 4, 5, 5, 5, 5, 6),
    (1, 2, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6),
    (1, 2, 3, 4, 4, 4, 5, 5, 5, 5, 6, 6),
    (2, 2, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6),
    (2, 2, 3, 4, 4, 4, 5, 5, 6, 6, 6, 6),
)
ADJ_STR_TO_D = (
    -2, -2, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 2, 3,
    3, 3, 3, 3, 4, 5, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
    18, 20,
)
ADJ_DEX_TO_H = (
    -3, -2, -2, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 3, 3,
    3, 3, 4, 4, 4, 4, 5, 6, 7, 8, 9, 9, 10, 11, 12, 13, 14, 15,
    15, 16,
)
ADJ_STR_TO_H = (
    -3, -2, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1,
    1, 1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
    15, 16,
)
ADJ_STR_HOLD = (
    4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
    20, 21, 22, 23, 24, 25, 26, 27, 28, 30, 31, 32, 33, 34, 35,
    37, 40, 44, 48, 50, 50, 50,
)


@dataclass(frozen=True)
class WarriorCombatInputs:
    level: int
    natural_str: int
    natural_dex: int
    melee_skill: int
    shooting_skill: int = 0
    two_weapon_skill: int = 0
    valour_hit_bonus: int = 0
    lazy_personality: bool = False


@dataclass(frozen=True)
class HandMeleeResult:
    blows: int
    to_hit: int
    to_damage: int
    hit_reliability: int
    hit_chance_ac100: float
    expected_damage_per_hit: float

    @property
    def expected_damage_per_round(self) -> float:
        return self.blows * self.hit_chance_ac100 * self.expected_damage_per_hit


@dataclass(frozen=True)
class WarriorMeleeResult:
    stat_str: int
    stat_dex: int
    stat_str_index: int
    stat_dex_index: int
    hands: tuple[HandMeleeResult, ...]
    weighted_average_target_hp: float = 0.0

    @property
    def expected_dps_ac100(self) -> float:
        return sum(hand.expected_damage_per_round for hand in self.hands)

    @property
    def expected_kill_turns(self) -> float:
        if self.expected_dps_ac100 <= 0 or self.weighted_average_target_hp <= 0:
            return float("inf")
        return self.weighted_average_target_hp / self.expected_dps_ac100


def trunc_div(value: int, divisor: int) -> int:
    """C++ integer division (truncate toward zero), including negative values."""
    return abs(value) // abs(divisor) * (-1 if (value < 0) != (divisor < 0) else 1)


def modify_stat_value(value: int, amount: int) -> int:
    """Port of player-status.cpp modify_stat_value()."""
    for _ in range(abs(amount)):
        if amount > 0:
            value = value + 1 if value < 18 else value + 10
        elif value >= 28:
            value -= 10
        elif value > 18:
            value = 18
        elif value > 3:
            value -= 1
    return value


def stat_index(value: int) -> int:
    if value <= 18:
        return max(0, value - 3)
    if value <= 237:
        return 15 + (value - 18) // 10
    return 37


def hit_chance(reliability: int, ac: int = AC_REFERENCE, *, lazy: bool = False) -> float:
    """Port of hit_chance(); returns a probability rather than an integer percent."""
    if reliability <= 0:
        return 0.05
    chance_left = 90
    if lazy:
        chance_left = (chance_left * 19 + 9) // 20
    chance = 5 + (100 - (ac * 75) // reliability) * chance_left // 100
    return max(5, chance) / 100.0


def _critical_damage(k: int, damage: int) -> int:
    if k < 400:
        return 2 * damage + 5
    if k < 700:
        return 2 * damage + 10
    if k < 900:
        return 3 * damage + 15
    if k < 1300:
        return 3 * damage + 20
    return trunc_div(7 * damage, 2) + 25


def expected_critical_damage(
    *, weight: int, weapon_to_h: int, hand_to_h: int, melee_skill: int,
    base_damage: int, impact: bool = False,
) -> float:
    """Expected normal critical damage using the source's exact trigger odds."""
    power = 2500 if impact else 5000
    critical_power = weight + hand_to_h * 3 + weapon_to_h * 5 + melee_skill
    probability = max(0.0, min(1.0, critical_power / power))
    if impact:
        total = 0.0
        outcomes = 650 * 650
        for roll in range(2, 1301):
            count = roll - 1 if roll <= 651 else 1301 - roll
            total += _critical_damage(weight + roll, base_damage) * count
        critical_mean = total / outcomes
    else:
        critical_mean = sum(
            _critical_damage(weight + roll, base_damage) for roll in range(1, 651)
        ) / 650
    return base_damage * (1.0 - probability) + critical_mean * probability


def _dice_distribution(number: int, sides: int) -> dict[int, int]:
    distribution = {0: 1}
    for _ in range(number):
        next_distribution: dict[int, int] = {}
        for subtotal, count in distribution.items():
            for roll in range(1, sides + 1):
                next_distribution[subtotal + roll] = (
                    next_distribution.get(subtotal + roll, 0) + count
                )
        distribution = next_distribution
    return distribution


@lru_cache(maxsize=None)
def expected_weapon_dice_damage(
    *, number: int, sides: int, weight: int, weapon_to_h: int,
    hand_to_h: int, melee_skill: int, impact: bool = False,
    slay_multiplier: int = 10,
) -> float:
    """Average critical-adjusted damage over every result of the weapon dice."""
    distribution = _dice_distribution(number, sides)
    outcomes = sides**number
    return sum(
        expected_critical_damage(
            weight=weight,
            weapon_to_h=weapon_to_h,
            hand_to_h=hand_to_h,
            melee_skill=melee_skill,
            base_damage=damage * slay_multiplier // 10,
            impact=impact,
        )
        * count
        for damage, count in distribution.items()
    ) / outcomes


def _pval_total(loadout: Loadout, flag: int) -> int:
    return sum(owned.item.pval for _, owned in loadout.slots if flag in owned.flags)


def _distributed_bonus(loadout: Loadout, hand_slot: str, attribute: str) -> int:
    """Port Warrior to-hit/to-damage equipment distribution between hands."""
    dual = loadout.hand_mode == "dual_wield"
    result = 0
    for slot, owned in loadout.slots:
        if slot in {SLOT_MAIN_HAND, SLOT_SUB_HAND}:
            continue
        value = int(getattr(owned.item, attribute))
        if not dual:
            if hand_slot == SLOT_MAIN_HAND and slot != SLOT_SUB_RING:
                result += value
            elif hand_slot == SLOT_SUB_HAND and slot != SLOT_MAIN_RING:
                result += value
            continue
        if hand_slot == SLOT_MAIN_HAND:
            if slot == SLOT_MAIN_RING:
                result += value
            elif slot != SLOT_SUB_RING:
                result += (value + 1) // 2 if value > 0 else value
        elif slot == SLOT_SUB_RING:
            result += value
        elif slot != SLOT_MAIN_RING:
            result += value // 2 if value > 0 else value
    return result


def _warrior_blows(
    weapon: OwnedEquipment, *, str_idx: int, dex_idx: int, level: int,
    two_hand_bonus: bool, extra_blows: int,
) -> int:
    if ADJ_STR_HOLD[str_idx] < weapon.item.weight // 10:
        return 1
    strength_index = ADJ_STR_BLOW[str_idx] * 5 // max(70, weapon.item.weight)
    if two_hand_bonus:
        strength_index += level // 23 + 1
    strength_index = min(11, strength_index)
    dexterity_index = min(11, ADJ_DEX_BLOW[dex_idx])
    blows = min(6, BLOWS_TABLE[strength_index][dexterity_index])
    return max(1, blows + extra_blows + level // 40)


def _extra_blows(loadout: Loadout, hand_slot: str) -> int:
    total = 0
    two_handed = loadout.hand_mode == "two_handed"
    for slot, owned in loadout.slots:
        if TR_BLOWS not in owned.flags:
            continue
        if two_handed:
            total += owned.item.pval
        elif slot in {SLOT_MAIN_HAND, SLOT_MAIN_RING}:
            if hand_slot == SLOT_MAIN_HAND:
                total += owned.item.pval
        elif slot in {SLOT_SUB_HAND, SLOT_SUB_RING}:
            if hand_slot == SLOT_SUB_HAND:
                total += owned.item.pval
        else:
            total += owned.item.pval
    return total


def _dual_wield_penalty(
    inputs: WarriorCombatInputs,
    weapon: OwnedEquipment,
    sub: OwnedEquipment,
) -> int:
    penalty = (100 - inputs.two_weapon_skill // 160) - trunc_div(130 - weapon.item.weight, 8)
    if TR_SUPPORTIVE in sub.flags:
        penalty = max(0, penalty - 10)
    if weapon.item.tval == 22:  # ItemKindType::POLEARM
        penalty += 10
    return penalty


def warrior_melee_signature(loadout: Loadout) -> tuple[object, ...]:
    """Return every loadout-dependent input consumed by melee evaluation."""
    main = loadout.item_at(SLOT_MAIN_HAND)
    sub = loadout.item_at(SLOT_SUB_HAND)
    return (
        loadout.hand_mode,
        main.id if main is not None else None,
        sub.id if sub is not None else None,
        _pval_total(loadout, TR_STR),
        _pval_total(loadout, TR_DEX),
        _distributed_bonus(loadout, SLOT_MAIN_HAND, "to_h"),
        _distributed_bonus(loadout, SLOT_MAIN_HAND, "to_d"),
        _distributed_bonus(loadout, SLOT_SUB_HAND, "to_h"),
        _distributed_bonus(loadout, SLOT_SUB_HAND, "to_d"),
        _extra_blows(loadout, SLOT_MAIN_HAND),
        _extra_blows(loadout, SLOT_SUB_HAND),
    )


def evaluate_warrior_melee(
    loadout: Loadout,
    inputs: WarriorCombatInputs,
    encounters: tuple[EncounterTarget, ...] = (),
    *,
    multiplier_weights_by_item: Mapping[
        str, tuple[tuple[int, float], ...]
    ] | None = None,
    average_target_hp: float | None = None,
    target_ac: int = AC_REFERENCE,
    neutral_target_brands: bool = False,
) -> WarriorMeleeResult:
    """Evaluate source-compatible melee damage against the requested AC."""
    strength = modify_stat_value(inputs.natural_str, _pval_total(loadout, TR_STR))
    dexterity = modify_stat_value(inputs.natural_dex, _pval_total(loadout, TR_DEX))
    str_idx = stat_index(strength)
    dex_idx = stat_index(dexterity)
    main = loadout.item_at(SLOT_MAIN_HAND)
    sub = loadout.item_at(SLOT_SUB_HAND)
    hands: list[HandMeleeResult] = []
    for hand_slot, weapon in ((SLOT_MAIN_HAND, main), (SLOT_SUB_HAND, sub)):
        if weapon is None or weapon.item.tval not in {20, 21, 22, 23}:
            continue
        two_handed = loadout.hand_mode == "two_handed"
        two_hand_bonus = two_handed and ADJ_STR_HOLD[str_idx] >= weapon.item.weight // 5
        extra_blows = _extra_blows(loadout, hand_slot)
        blows = _warrior_blows(
            weapon, str_idx=str_idx, dex_idx=dex_idx, level=inputs.level,
            two_hand_bonus=two_hand_bonus, extra_blows=extra_blows,
        )
        to_hit = ADJ_DEX_TO_H[dex_idx] + ADJ_STR_TO_H[str_idx]
        to_damage = ADJ_STR_TO_D[str_idx]
        if hand_slot == SLOT_MAIN_HAND and two_hand_bonus:
            two_hand_bonus = ADJ_STR_TO_H[str_idx] + ADJ_DEX_TO_H[dex_idx]
            to_hit += max(two_hand_bonus, 1)
            to_damage += max(trunc_div(ADJ_STR_TO_D[str_idx], 2), 1)
        to_hit += trunc_div(weapon.item.weapon_proficiency - BEGINNER_WEAPON_EXP, 200)
        if ADJ_STR_HOLD[str_idx] < weapon.item.weight // 10:
            to_hit += 2 * (ADJ_STR_HOLD[str_idx] - weapon.item.weight // 10)
        to_hit += _distributed_bonus(loadout, hand_slot, "to_h")
        to_damage += _distributed_bonus(loadout, hand_slot, "to_d")
        if loadout.hand_mode == "dual_wield" and sub is not None:
            to_hit -= _dual_wield_penalty(inputs, weapon, sub)
        reliability = (
            inputs.melee_skill
            + (to_hit + weapon.item.to_h) * 3
            + inputs.valour_hit_bonus
        )
        chance = hit_chance(reliability, target_ac, lazy=inputs.lazy_personality)
        damage_arguments = {
            "number": weapon.item.damage_dice_num,
            "sides": weapon.item.damage_dice_sides,
            "weight": weapon.item.weight,
            "weapon_to_h": weapon.item.to_h,
            "hand_to_h": to_hit,
            "melee_skill": inputs.melee_skill,
            "impact": TR_IMPACT in weapon.flags,
        }
        if encounters:
            precomputed = (
                multiplier_weights_by_item.get(weapon.id)
                if multiplier_weights_by_item is not None
                else None
            )
            if precomputed is None:
                multiplier_weights: dict[int, float] = {}
                for encounter in encounters:
                    multiplier = melee_multiplier(weapon.flags, encounter.knowledge)
                    multiplier_weights[multiplier] = (
                        multiplier_weights.get(multiplier, 0.0) + encounter.weight
                    )
                weighted_multipliers = tuple(multiplier_weights.items())
            else:
                weighted_multipliers = precomputed
            damage = sum(
                weight
                * expected_weapon_dice_damage(
                    **damage_arguments,
                    slay_multiplier=multiplier,
                )
                for multiplier, weight in weighted_multipliers
            )
        else:
            neutral_multiplier = (
                25
                if neutral_target_brands
                and any(flag in weapon.flags for flag, _, _ in BRANDS)
                else 10
            )
            damage = expected_weapon_dice_damage(
                **damage_arguments, slay_multiplier=neutral_multiplier
            )
        damage += weapon.item.to_d + to_damage
        hands.append(
            HandMeleeResult(
                blows,
                to_hit,
                to_damage,
                reliability,
                chance,
                max(0.0, damage),
            )
        )
    average_hp = (
        average_target_hp
        if average_target_hp is not None
        else sum(
            encounter.weight * encounter.knowledge.average_hp
            for encounter in encounters
        )
    )
    return WarriorMeleeResult(
        strength,
        dexterity,
        str_idx,
        dex_idx,
        tuple(hands),
        average_hp,
    )
