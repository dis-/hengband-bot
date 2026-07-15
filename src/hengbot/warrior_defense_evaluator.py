"""Source-compatible Warrior AC and monster melee HP-damage evaluation.

The result deliberately reports unmodelled blow side effects.  Callers must not
activate equipment changes until both that set and ranged threats are complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from hengbot.equipment_encounters import EncounterTarget
from hengbot.equipment_optimizer import Loadout, SLOT_MAIN_HAND, SLOT_SUB_HAND
from hengbot.monrace_knowledge import MonsterBlow
from hengbot.warrior_equipment_evaluator import modify_stat_value, stat_index


TR_DEX = 3
TR_MAGIC_MASTERY = 6
TR_SPEED = 12
TR_SUST_STR = 32
TR_SUST_INT = 33
TR_SUST_WIS = 34
TR_SUST_DEX = 35
TR_SUST_CON = 36
TR_SUST_CHR = 37
TR_EASY_SPELL = 39
TR_IM_ACID = 40
TR_IM_ELEC = 41
TR_IM_FIRE = 42
TR_IM_COLD = 43
TR_RES_ACID = 48
TR_RES_ELEC = 49
TR_RES_FIRE = 50
TR_RES_COLD = 51
TR_RES_POIS = 52
TR_RES_FEAR = 53
TR_RES_BLIND = 56
TR_RES_CONF = 57
TR_RES_SOUND = 58
TR_RES_NETHER = 60
TR_RES_CHAOS = 62
TR_RES_DISEN = 63
TR_FREE_ACT = 46
TR_HOLD_EXP = 47
TR_DEC_MANA = 70
TR_IGNORE_ACID = 84
TR_LOW_AC = 134
TR_NO_AC = 141
TR_SUPPORTIVE = 147
TR_VUL_ACID = 152
TR_VUL_COLD = 153
TR_VUL_ELEC = 154
TR_VUL_FIRE = 155
TR_RES_TIME = 143

PROTECTOR_TVALS = frozenset({30, 31, 32, 33, 34, 35, 36, 37, 38})

ADJ_DEX_TO_AC = (
    -4, -3, -2, -1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 2, 2,
    2, 2, 3, 3, 3, 4, 5, 6, 7, 8, 9, 9, 10, 11, 12, 13, 14, 15,
    15, 16,
)

BLOW_POWER = {
    "HURT": 60,
    "POISON": 5,
    "UN_BONUS": 20,
    "UN_POWER": 15,
    "EAT_GOLD": 5,
    "EAT_ITEM": 5,
    "EAT_FOOD": 5,
    "EAT_LITE": 5,
    "ACID": 0,
    "ELEC": 10,
    "FIRE": 10,
    "COLD": 10,
    "BLIND": 2,
    "CONFUSE": 10,
    "TERRIFY": 10,
    "PARALYZE": 2,
    "LOSE_STR": 0,
    "LOSE_INT": 0,
    "LOSE_WIS": 0,
    "LOSE_DEX": 0,
    "LOSE_CON": 0,
    "LOSE_CHR": 0,
    "LOSE_ALL": 2,
    "SHATTER": 60,
    "EXP_10": 5,
    "EXP_20": 5,
    "EXP_40": 5,
    "EXP_80": 5,
    "DISEASE": 5,
    "TIME": 5,
    "EXP_VAMP": 5,
    "DR_MANA": 5,
    "SUPERHURT": 60,
    "INERTIA": 5,
    "STUN": 5,
    # monster-attack-table.cpp currently initializes HUNGRY at the FLAVOR
    # index and leaves CHAOS value-initialized.  These are the compiled lookup
    # results, even though the adjacent comments suggest power 5 for HUNGRY.
    "HUNGRY": 0,
    "CHAOS": 0,
    "FLAVOR": 0,
}

SIDE_EFFECT_FREE = frozenset({"HURT", "SUPERHURT", "FLAVOR"})
MODELLED_HP_EFFECTS = frozenset(BLOW_POWER)


@dataclass(frozen=True)
class WarriorDefenseInputs:
    level: int
    natural_dex: int
    shield_skill: int = 0
    base_ac_bonus: int = 0
    base_speed: int = 110
    saving_skill: int = 0
    intrinsic_flags: frozenset[int] = frozenset()


@dataclass(frozen=True)
class WarriorDefenseResult:
    armor_class: int
    expected_melee_damage: float
    unsupported_effects: frozenset[str]
    status_turn_exposure: tuple[tuple[str, float], ...] = ()
    resource_event_exposure: tuple[tuple[str, float], ...] = ()

    @property
    def melee_complete(self) -> bool:
        return not self.unsupported_effects


def _pval_total(loadout: Loadout, flag: int) -> int:
    return sum(item.item.pval for _, item in loadout.slots if flag in item.flags)


def loadout_armor_class(loadout: Loadout, inputs: WarriorDefenseInputs) -> int:
    flags = loadout.flags | inputs.intrinsic_flags
    if TR_NO_AC in flags:
        return 0
    if TR_LOW_AC in flags:
        raise ValueError("LOW_AC curse magnitude is not present in bot telemetry")

    dexterity = modify_stat_value(inputs.natural_dex, _pval_total(loadout, TR_DEX))
    armor_class = inputs.base_ac_bonus + ADJ_DEX_TO_AC[stat_index(dexterity)]
    armor_class += sum(item.item.ac + item.item.to_a for _, item in loadout.slots)

    main = loadout.item_at(SLOT_MAIN_HAND)
    sub = loadout.item_at(SLOT_SUB_HAND)
    if any(item is not None and item.item.tval in PROTECTOR_TVALS for item in (main, sub)):
        armor_class += inputs.shield_skill * (1 + inputs.level // 22) // 2000
    if sub is not None and TR_SUPPORTIVE in sub.flags:
        armor_class += 5
    return armor_class


def monster_melee_hit_chance(effect: str, level: int, armor_class: int) -> float:
    if effect == "FLAVOR":
        return 1.0
    power = BLOW_POWER.get(effect)
    if power is None:
        return 0.0
    reliability = power + level * 3
    if reliability <= 0:
        return 0.05
    threshold = armor_class * 3 // 4
    normal_hit = min(1.0, max(0, reliability - threshold) / reliability)
    return 0.05 + 0.90 * normal_hit


@lru_cache(maxsize=None)
def _dice_distribution(number: int, sides: int) -> tuple[tuple[int, int], ...]:
    if number <= 0 or sides <= 0:
        return ((0, 1),)
    distribution = {0: 1}
    for _ in range(number):
        following: dict[int, int] = {}
        for subtotal, count in distribution.items():
            for roll in range(1, sides + 1):
                following[subtotal + roll] = following.get(subtotal + roll, 0) + count
        distribution = following
    return tuple(distribution.items())


def _element_rate(flags: frozenset[int], effect: str) -> int:
    immunity, resistance, vulnerability = {
        "ACID": (TR_IM_ACID, TR_RES_ACID, TR_VUL_ACID),
        "ELEC": (TR_IM_ELEC, TR_RES_ELEC, TR_VUL_ELEC),
        "FIRE": (TR_IM_FIRE, TR_RES_FIRE, TR_VUL_FIRE),
        "COLD": (TR_IM_COLD, TR_RES_COLD, TR_VUL_COLD),
    }[effect]
    if immunity in flags:
        return 0
    rate = 100
    if vulnerability in flags:
        rate += rate // 3
    if resistance in flags:
        rate = (rate + 2) // 3
    return rate


def _acid_armor_probability(loadout: Loadout) -> float:
    # acid_minus_ac() chooses uniformly from both hands and five armor slots.
    affected = 0
    for slot in ("main_hand", "sub_hand", "body", "outer", "arms", "head", "feet"):
        item = loadout.item_at(slot)
        if item is None or item.item.tval not in PROTECTOR_TVALS:
            continue
        if item.item.ac + item.item.to_a > 0 or TR_IGNORE_ACID in item.flags:
            affected += 1
    return affected / 7.0


def warrior_defense_signature(
    loadout: Loadout, inputs: WarriorDefenseInputs
) -> tuple[object, ...]:
    """Return every loadout-dependent input consumed by defense evaluation."""
    flags = loadout.flags | inputs.intrinsic_flags
    return (
        loadout_armor_class(loadout, inputs),
        flags,
        inputs.base_speed + _pval_total(loadout, TR_SPEED),
        _acid_armor_probability(loadout),
    )


def _superhurt_critical_chance(level: int, armor_class: int) -> float:
    sides = level * 2 + 300
    first = min(1.0, max(0, sides - (armor_class + 200)) / sides)
    return first + (1.0 - first) / 13.0


def _random_scaled_damage(damage: int, offset: int, divisor: int) -> float:
    return sum(damage * (roll + offset) // divisor for roll in range(1, 5)) / 4


def _chaos_resisted_damage(damage: int) -> float:
    rates = tuple(60_000 // denominator for denominator in (800, 900, 1000, 1100))
    return sum(damage * rate // 100 for rate in rates) / 4


def _saving_throw_failure(level: int, saving_skill: int) -> float:
    sides = 100 + level // 2
    success = min(sides, max(0, saving_skill)) / sides
    return 1.0 - success


def _earthquake_probability(blow: MonsterBlow, armor_class: int) -> float:
    if blow.method == "EXPLODE":
        return 1.0
    distribution = _dice_distribution(blow.dice_num, blow.dice_sides)
    outcomes = sum(count for _, count in distribution)
    triggering = sum(
        count
        for damage, count in distribution
        if damage - damage * min(armor_class, 150) // 250 > 23
    )
    return triggering / outcomes


def _blow_side_effect_exposure(
    blow: MonsterBlow,
    *,
    monster_level: int,
    armor_class: int,
    flags: frozenset[int],
    saving_skill: int,
) -> tuple[dict[str, float], dict[str, float]]:
    status: dict[str, float] = {}
    resource: dict[str, float] = {}
    effect = blow.effect

    if effect == "POISON" and blow.method != "EXPLODE" and TR_RES_POIS not in flags:
        status["poison"] = 5 + (monster_level + 1) / 2
    elif effect == "BLIND" and TR_RES_BLIND not in flags:
        status["blind"] = 10 + (monster_level + 1) / 2
    elif effect == "CONFUSE" and blow.method != "EXPLODE" and TR_RES_CONF not in flags:
        status["confused"] = 3 + (monster_level + 1) / 2
    elif effect == "TERRIFY" and TR_RES_FEAR not in flags:
        status["afraid"] = (
            3 + (monster_level + 1) / 2
        ) * _saving_throw_failure(monster_level, saving_skill)
    elif effect == "PARALYZE" and TR_FREE_ACT not in flags:
        status["paralyzed"] = (
            3 + (monster_level + 1) / 2
        ) * _saving_throw_failure(monster_level, saving_skill)
    elif effect == "DISEASE":
        if TR_RES_POIS not in flags:
            status["poison"] = 5 + (monster_level + 1) / 2
        resource["constitution-drain"] = 0.04 if TR_RES_POIS in flags else 0.10
    elif effect == "TIME" and blow.method != "EXPLODE" and TR_RES_TIME not in flags:
        resource["time-drain"] = 1.0
    elif effect == "INERTIA":
        status["slowed"] = 4 + max(0, monster_level // 10 - 1) / 2
    elif effect == "STUN" and TR_RES_SOUND not in flags:
        status["stunned"] = 10 + (max(1, monster_level // 4) + 1) / 2
    elif effect == "CHAOS" and TR_RES_CHAOS not in flags:
        resource["chaos-effect"] = 1.0

    if effect == "UN_BONUS" and blow.method != "EXPLODE" and TR_RES_DISEN not in flags:
        resource["equipment-disenchant"] = 1.0
    elif effect == "UN_POWER":
        resource["device-charge-drain"] = 1.0
    elif effect in {"EAT_GOLD", "EAT_ITEM", "EAT_FOOD", "EAT_LITE"}:
        resource[effect.lower().replace("_", "-")] = 1.0
    elif effect in {"ACID", "ELEC", "FIRE", "COLD"} and blow.method != "EXPLODE":
        immunity = {
            "ACID": TR_IM_ACID,
            "ELEC": TR_IM_ELEC,
            "FIRE": TR_IM_FIRE,
            "COLD": TR_IM_COLD,
        }[effect]
        if immunity not in flags:
            resource[f"{effect.lower()}-item-damage"] = 1.0
    elif effect.startswith("LOSE_"):
        stat_flags = {
            "LOSE_STR": (("strength-drain", TR_SUST_STR),),
            "LOSE_INT": (("intelligence-drain", TR_SUST_INT),),
            "LOSE_WIS": (("wisdom-drain", TR_SUST_WIS),),
            "LOSE_DEX": (("dexterity-drain", TR_SUST_DEX),),
            "LOSE_CON": (("constitution-drain", TR_SUST_CON),),
            "LOSE_CHR": (("charisma-drain", TR_SUST_CHR),),
            "LOSE_ALL": (
                ("strength-drain", TR_SUST_STR),
                ("intelligence-drain", TR_SUST_INT),
                ("wisdom-drain", TR_SUST_WIS),
                ("dexterity-drain", TR_SUST_DEX),
                ("constitution-drain", TR_SUST_CON),
                ("charisma-drain", TR_SUST_CHR),
            ),
        }[effect]
        for name, sustain in stat_flags:
            if sustain not in flags:
                resource[name] = 1.0
    elif effect == "SHATTER":
        resource["earthquake"] = _earthquake_probability(blow, armor_class)
    elif effect in {"EXP_10", "EXP_20", "EXP_40", "EXP_80"}:
        hold_probability = {"EXP_10": 0.95, "EXP_20": 0.90, "EXP_40": 0.75, "EXP_80": 0.50}[effect]
        resource["experience-drain"] = 1.0 - hold_probability if TR_HOLD_EXP in flags else 1.0
    elif effect == "EXP_VAMP":
        resource["experience-drain"] = 0.5 if TR_HOLD_EXP in flags else 1.0
    elif effect == "DR_MANA":
        resource["mana-drain"] = 1.0
    elif effect == "HUNGRY":
        resource["food-drain"] = 1.0
    return status, resource


def expected_blow_hp_damage(
    blow: MonsterBlow,
    *,
    monster_level: int,
    armor_class: int,
    flags: frozenset[int],
    acid_armor_probability: float = 0.0,
    speed: int = 110,
) -> float:
    if blow.method == "EXPLODE" or blow.effect in {"FLAVOR", "DR_MANA", "HUNGRY"}:
        return 0.0
    distribution = _dice_distribution(blow.dice_num, blow.dice_sides)
    outcomes = sum(count for _, count in distribution)
    critical_chance = _superhurt_critical_chance(monster_level, armor_class)

    total = 0.0
    for damage, count in distribution:
        if blow.effect in {"HURT", "SUPERHURT"}:
            reduced = damage - damage * min(armor_class, 150) // 250
            if blow.effect == "SUPERHURT":
                reduced *= 1.0 + critical_chance
            adjusted = reduced
        elif blow.effect in {"ACID", "ELEC", "FIRE", "COLD"}:
            adjusted = damage * _element_rate(flags, blow.effect) // 100
            if blow.effect == "ACID":
                halved = (adjusted + 1) // 2
                adjusted = (
                    adjusted * (1.0 - acid_armor_probability)
                    + halved * acid_armor_probability
                )
        elif blow.effect == "POISON":
            rate = 40 if TR_RES_POIS in flags else 100
            adjusted = damage * rate // 100
        elif blow.effect == "UN_BONUS" and TR_RES_DISEN in flags:
            adjusted = _random_scaled_damage(damage, 4, 9)
        elif blow.effect == "UN_POWER":
            reductions = sum(
                flag in flags for flag in (TR_DEC_MANA, TR_EASY_SPELL, TR_MAGIC_MASTERY)
            )
            adjusted = damage * (1000 - reductions * 75) // 1000
        elif blow.effect in {"BLIND", "CONFUSE", "TERRIFY", "PARALYZE"}:
            protecting_flag = {
                "BLIND": TR_RES_BLIND,
                "CONFUSE": TR_RES_CONF,
                "TERRIFY": TR_RES_FEAR,
                "PARALYZE": TR_FREE_ACT,
            }[blow.effect]
            adjusted = (
                _random_scaled_damage(damage, 3, 8)
                if protecting_flag in flags
                else damage
            )
        elif blow.effect == "SHATTER":
            adjusted = damage - damage * min(armor_class, 150) // 250
        elif blow.effect in {"EXP_10", "EXP_20", "EXP_40", "EXP_80"}:
            reductions = int(TR_HOLD_EXP in flags) + int(TR_RES_NETHER in flags)
            adjusted = damage * (1000 - reductions * 75) // 1000
        elif blow.effect == "EXP_VAMP":
            adjusted = damage * 9 // 10 if TR_HOLD_EXP in flags else damage
        elif blow.effect == "DISEASE" and TR_RES_POIS in flags:
            adjusted = _random_scaled_damage(damage, 4, 9)
        elif blow.effect == "TIME" and TR_RES_TIME in flags:
            adjusted = _random_scaled_damage(damage, 4, 9)
        elif blow.effect == "INERTIA" and speed >= 130:
            adjusted = _random_scaled_damage(damage, 4, 9)
        elif blow.effect == "CHAOS" and TR_RES_CHAOS in flags:
            adjusted = _chaos_resisted_damage(damage)
        elif blow.effect == "LOSE_ALL":
            sustain_flags = {
                TR_SUST_STR, TR_SUST_INT, TR_SUST_WIS,
                TR_SUST_DEX, TR_SUST_CON, TR_SUST_CHR,
            }
            adjusted = damage * (100 - 3 * len(flags.intersection(sustain_flags))) // 100
        else:
            adjusted = damage
        total += adjusted * count
    return total / outcomes


def evaluate_warrior_defense(
    loadout: Loadout,
    inputs: WarriorDefenseInputs,
    encounters: tuple[EncounterTarget, ...],
) -> WarriorDefenseResult:
    armor_class = loadout_armor_class(loadout, inputs)
    flags = loadout.flags | inputs.intrinsic_flags
    speed = inputs.base_speed + _pval_total(loadout, TR_SPEED)
    acid_probability = _acid_armor_probability(loadout)
    expected = 0.0
    unsupported: set[str] = set()
    status_exposure: dict[str, float] = {}
    resource_exposure: dict[str, float] = {}
    for encounter in encounters:
        race = encounter.knowledge
        for blow in race.blows:
            if blow.effect not in MODELLED_HP_EFFECTS:
                unsupported.add(blow.effect or "NONE")
            hit_probability = monster_melee_hit_chance(
                blow.effect, race.level, armor_class
            )
            expected += encounter.weight * hit_probability * expected_blow_hp_damage(
                blow,
                monster_level=race.level,
                armor_class=armor_class,
                flags=flags,
                acid_armor_probability=acid_probability,
                speed=speed,
            )
            status, resource = _blow_side_effect_exposure(
                blow,
                monster_level=race.level,
                armor_class=armor_class,
                flags=flags,
                saving_skill=inputs.saving_skill,
            )
            occurrence_weight = encounter.weight * hit_probability
            for name, value in status.items():
                status_exposure[name] = status_exposure.get(name, 0.0) + occurrence_weight * value
            for name, value in resource.items():
                resource_exposure[name] = resource_exposure.get(name, 0.0) + occurrence_weight * value
    return WarriorDefenseResult(
        armor_class,
        expected,
        frozenset(unsupported),
        tuple(sorted(status_exposure.items())),
        tuple(sorted(resource_exposure.items())),
    )
