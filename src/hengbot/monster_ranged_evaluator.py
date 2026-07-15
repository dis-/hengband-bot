"""Pre-resistance monster ability damage ported from Hengband source."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import comb

from hengbot.equipment_encounters import EncounterTarget
from hengbot.monrace_knowledge import MonraceKnowledge, SUMMON_ABILITIES


TR_IM_ACID = 40
TR_IM_ELEC = 41
TR_IM_FIRE = 42
TR_IM_COLD = 43
TR_REFLECT = 45
TR_FREE_ACT = 46
TR_RES_ACID = 48
TR_RES_ELEC = 49
TR_RES_FIRE = 50
TR_RES_COLD = 51
TR_RES_POIS = 52
TR_RES_FEAR = 53
TR_RES_LITE = 54
TR_RES_DARK = 55
TR_RES_BLIND = 56
TR_RES_CONF = 57
TR_RES_SOUND = 58
TR_RES_SHARDS = 59
TR_RES_NETHER = 60
TR_RES_NEXUS = 61
TR_RES_CHAOS = 62
TR_RES_DISEN = 63
TR_NO_TELE = 68
TR_LEVITATION = 76
TR_RES_TIME = 143
TR_RES_WATER = 144
TR_INVULN_ARROW = 145
TR_IM_DARK = 157
TR_IM_LITE = 163


@dataclass(frozen=True)
class RangedAbilityResult:
    expected_hp_damage: float
    status_turn_exposure: tuple[tuple[str, float], ...] = ()
    resource_event_exposure: tuple[tuple[str, float], ...] = ()
    unsupported_effects: frozenset[str] = frozenset()


@dataclass(frozen=True)
class WarriorRangedDefenseResult:
    expected_ranged_damage: float
    status_turn_exposure: tuple[tuple[str, float], ...] = ()
    resource_event_exposure: tuple[tuple[str, float], ...] = ()
    unsupported_effects: frozenset[str] = frozenset()

    @property
    def ranged_complete(self) -> bool:
        return not self.unsupported_effects


@dataclass(frozen=True)
class SpellSelectionContext:
    distance: int = 5
    clean_shot: bool = True
    summon_possible: bool = True
    raise_possible: bool = False
    player_has_mana: bool = True
    player_invulnerable: bool = False
    dispel_useful: bool = False
    monster_hp_fraction: float = 1.0
    monster_afraid: bool = False
    monster_invulnerable: bool = False
    monster_hasted: bool = False
    timewalk_active: bool = False
    special_forced: bool = False
    special_selection_probability: float = 0.5


@dataclass(frozen=True)
class CauseDamagePercentile:
    ability: str
    per_action_probability: float
    successful_casts: int
    damage_per_cast: int
    total_damage: int


@dataclass(frozen=True)
class RangedDamagePercentile:
    total_damage: int
    expected_damage: float
    probability_any_damage: float
    single_hit_floor: int
    floor_applied: bool


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


def _expected_roll(
    base: int,
    number: int = 0,
    sides: int = 0,
    *,
    multiplier: int = 1,
    divisor: int = 1,
) -> float:
    distribution = _dice_distribution(number, sides)
    outcomes = sum(count for _, count in distribution)
    return max(
        1.0,
        sum(
            (base + roll * multiplier // divisor) * count
            for roll, count in distribution
        ) / outcomes,
    )


def _roll_probability_distribution(
    base: int,
    number: int = 0,
    sides: int = 0,
    *,
    multiplier: int = 1,
    divisor: int = 1,
) -> dict[int, float]:
    distribution = _dice_distribution(number, sides)
    outcomes = sum(count for _, count in distribution)
    result: dict[int, float] = {}
    for roll, count in distribution:
        damage = max(1, base + roll * multiplier // divisor)
        result[damage] = result.get(damage, 0.0) + count / outcomes
    return result


BREATH = {
    "BR_ACID": (3, 1600), "BR_ELEC": (3, 1600),
    "BR_FIRE": (3, 1600), "BR_COLD": (3, 1600),
    "BR_POIS": (3, 800), "BR_NETH": (6, 550),
    "BR_LITE": (6, 400), "BR_DARK": (6, 400),
    "BR_CONF": (6, 450), "BR_SOUN": (6, 450),
    "BR_CHAO": (6, 600), "BR_DISE": (6, 500),
    "BR_NEXU": (3, 250), "BR_TIME": (3, 150),
    "BR_INER": (6, 200), "BR_GRAV": (6, 200),
    "BR_SHAR": (6, 500), "BR_PLAS": (6, 150),
    "BR_FORC": (6, 200), "BR_MANA": (3, 250),
    "BR_NUKE": (3, 800), "BR_DISI": (6, 150),
    # These two reproduce the source's asymmetric conditional expression.
    "BR_VOID": (6, 250), "BR_ABYSS": (6, 250),
}

NO_DAMAGE = frozenset({
    "SHRIEK", "DISPEL", "SCARE", "BLIND", "CONF", "SLOW", "HOLD",
    "HASTE", "HEAL", "INVULNER", "BLINK", "TPORT", "WORLD", "SPECIAL",
    "TELE_TO", "TELE_AWAY", "TELE_LEVEL", "DARKNESS", "TRAPS", "FORGET",
    "RAISE_DEAD", "ANIM_DEAD", "S_KIN", "S_CYBER", "S_MONSTER", "S_MONSTERS", "S_ANT",
    "S_SPIDER", "S_HOUND", "S_HYDRA", "S_ANGEL", "S_DEMON", "S_UNDEAD",
    "S_DRAGON", "S_HI_UNDEAD", "S_HI_DRAGON", "S_AMBERITES", "S_UNIQUE",
    "S_DEAD_UNIQUE",
})

REFLECTABLE = frozenset({
    "BO_ACID", "BO_ELEC", "BO_FIRE", "BO_COLD", "BO_NETH",
    "BO_WATE", "BO_MANA", "BO_PLAS", "BO_ICEE", "BO_VOID",
    "BO_ABYSS", "BO_METEOR", "BO_LITE", "MISSILE",
})

INNATE_ABILITIES = frozenset({
    "SHRIEK", "ROCKET", "SHOOT", "SPECIAL",
    *(ability for ability in BREATH),
})

ATTACK_ABILITIES = frozenset({
    *BREATH,
    "ROCKET", "SHOOT", "BA_NUKE", "BA_CHAO", "BA_VOID", "BA_ABYSS",
    "BA_ACID", "BA_ELEC", "BA_FIRE", "BA_COLD", "BA_POIS", "BA_NETH",
    "BA_WATE", "BA_MANA", "BA_DARK", "BA_LITE", "BA_METEOR",
    "BO_ACID", "BO_ELEC", "BO_FIRE", "BO_COLD", "BO_NETH", "BO_WATE",
    "BO_MANA", "BO_PLAS", "BO_ICEE", "BO_VOID", "BO_ABYSS",
    "BO_METEOR", "BO_LITE", "MISSILE",
    "CAUSE_1", "CAUSE_2", "CAUSE_3", "CAUSE_4", "HAND_DOOM",
    "PSY_SPEAR",
})
ANNOY_ABILITIES = frozenset({
    "SHRIEK", "DRAIN_MANA", "MIND_BLAST", "BRAIN_SMASH",
    "CAUSE_1", "CAUSE_2", "CAUSE_3", "CAUSE_4", "SCARE", "BLIND",
    "CONF", "SLOW", "HOLD", "TELE_TO", "TELE_LEVEL", "TRAPS",
    "FORGET", "RAISE_DEAD",
})


def _add_uniform(
    result: dict[str, float],
    abilities: tuple[str, ...],
    probability: float,
) -> None:
    if not abilities or probability <= 0:
        return
    share = probability / len(abilities)
    for ability in abilities:
        result[ability] = result.get(ability, 0.0) + share


def _smart_selection_pass(
    abilities: frozenset[str], context: SpellSelectionContext
) -> tuple[dict[str, float], float]:
    """Port one choose_attack_spell() pass; return choices and MAX chance."""
    categories = {
        "world": tuple(sorted(abilities.intersection({"WORLD"}))),
        "special": tuple(sorted(abilities.intersection({"SPECIAL"}))),
        "heal": tuple(sorted(abilities.intersection({"HEAL"}))),
        "escape": tuple(sorted(abilities.intersection(
            {"BLINK", "TPORT", "TELE_AWAY", "TELE_LEVEL"}
        ))),
        "tactic": tuple(sorted(abilities.intersection({"BLINK"}))),
        "summon": tuple(sorted(abilities.intersection(SUMMON_ABILITIES))),
        "dispel": tuple(sorted(abilities.intersection({"DISPEL"}))),
        "raise": tuple(sorted(abilities.intersection({"RAISE_DEAD"}))),
        "attack": tuple(sorted(abilities.intersection(ATTACK_ABILITIES))),
        "psy": tuple(sorted(abilities.intersection({"PSY_SPEAR"}))),
        "invul": tuple(sorted(abilities.intersection({"INVULNER"}))),
        "haste": tuple(sorted(abilities.intersection({"HASTE"}))),
        "annoy": tuple(sorted(abilities.intersection(ANNOY_ABILITIES))),
    }
    selected: dict[str, float] = {}
    remaining = 1.0

    def branch(name: str, chance: float, condition: bool = True) -> None:
        nonlocal remaining
        choices = categories[name]
        if not condition or not choices or chance <= 0:
            return
        chance = min(1.0, chance)
        _add_uniform(selected, choices, remaining * chance)
        remaining *= 1.0 - chance

    branch("world", 0.15, not context.timewalk_active)
    branch("special", 1.0, context.special_forced)
    branch("heal", 0.5, context.monster_hp_fraction < 1 / 3)
    branch(
        "escape", 0.5,
        context.monster_hp_fraction < 1 / 3 or context.monster_afraid,
    )
    branch(
        "special", context.special_selection_probability,
        not context.special_forced,
    )
    branch(
        "tactic", 0.75,
        context.distance < 4
        and (bool(categories["attack"]) or "TRAPS" in abilities)
        and not context.timewalk_active,
    )
    branch("summon", 0.40, context.summon_possible)
    branch("dispel", 0.50, context.dispel_useful)
    branch("raise", 0.40, context.raise_possible)
    if context.player_invulnerable:
        branch("psy", 0.50)
        branch("attack", 0.40)
    else:
        branch("attack", 0.85)
    branch("tactic", 0.50, not context.timewalk_active)
    branch("invul", 0.50, not context.monster_invulnerable)
    branch("heal", 0.25, context.monster_hp_fraction < 0.75)
    branch("haste", 0.20, not context.monster_hasted)
    branch("annoy", 0.80)
    return selected, remaining


def _selection_for_available(
    monster: MonraceKnowledge,
    abilities: frozenset[str],
    context: SpellSelectionContext,
) -> dict[str, float]:
    if not abilities:
        return {}
    if "STUPID" in monster.flags:
        share = 1.0 / len(abilities)
        return {ability: share for ability in abilities}
    one_pass, retry = _smart_selection_pass(abilities, context)
    retry_multiplier = sum(retry ** attempt for attempt in range(10))
    return {
        ability: probability * retry_multiplier
        for ability, probability in one_pass.items()
    }


def ability_selection_probabilities(
    monster: MonraceKnowledge,
    context: SpellSelectionContext,
) -> dict[str, float]:
    """Return source-order ability probabilities for one spell attempt."""
    abilities = set(monster.abilities)
    if not context.clean_shot:
        abilities.difference_update(
            ability for ability in abilities
            if ability in REFLECTABLE or ability in {"ROCKET", "SHOOT"}
        )
    if not context.summon_possible:
        abilities.difference_update(SUMMON_ABILITIES)
    if not context.raise_possible:
        abilities.discard("RAISE_DEAD")
    if not context.player_has_mana:
        abilities.discard("DRAIN_MANA")
    all_abilities = frozenset(abilities)
    innate = all_abilities.intersection(INNATE_ABILITIES)
    full_probability = min(1.0, monster.spell_frequency * 2 / 100.0)
    distributions = (
        (full_probability, _selection_for_available(monster, all_abilities, context)),
        (1.0 - full_probability, _selection_for_available(monster, innate, context)),
    )
    result: dict[str, float] = {}
    for scenario_probability, distribution in distributions:
        for ability, probability in distribution.items():
            result[ability] = result.get(ability, 0.0) + scenario_probability * probability
    return result

ABILITY_ATTRIBUTE = {
    "ROCKET": "ROCKET",
    "SHOOT": "SHOOT",
    "BA_NUKE": "NUKE", "BR_NUKE": "NUKE",
    "BA_POIS": "POIS", "BR_POIS": "POIS",
    "BA_NETH": "NETHER", "BO_NETH": "NETHER", "BR_NETH": "NETHER",
    "BA_WATE": "WATER", "BO_WATE": "WATER",
    "BA_CHAO": "CHAOS", "BR_CHAO": "CHAOS",
    "BA_DARK": "DARK", "BR_DARK": "DARK",
    "BA_LITE": "LITE", "BO_LITE": "LITE", "BR_LITE": "LITE",
    "BO_PLAS": "PLASMA", "BR_PLAS": "PLASMA",
    "BO_ICEE": "ICE",
    "BA_VOID": "VOID", "BO_VOID": "VOID", "BR_VOID": "VOID",
    "BA_ABYSS": "ABYSS", "BO_ABYSS": "ABYSS", "BR_ABYSS": "ABYSS",
    "BR_CONF": "CONFUSION", "BR_SOUN": "SOUND", "BR_SHAR": "SHARDS",
    "BR_DISE": "DISENCHANT", "BR_NEXU": "NEXUS", "BR_TIME": "TIME",
    "BR_INER": "INERTIA", "BR_GRAV": "GRAVITY", "BR_FORC": "FORCE",
}
for _element in ("ACID", "ELEC", "FIRE", "COLD"):
    for _form in ("BA", "BO", "BR"):
        ABILITY_ATTRIBUTE[f"{_form}_{_element}"] = _element


def _expected_rate_damage(damage: float, rates: tuple[int, ...]) -> float:
    """Apply the game's integer percentage operation for each random rate."""
    if rates == (100,):
        return damage
    return sum(int(damage * rate) // 100 for rate in rates) / len(rates)


def _attribute_rates(attribute: str, flags: frozenset[int]) -> tuple[int, ...]:
    elemental = {
        "ACID": (TR_IM_ACID, TR_RES_ACID),
        "ELEC": (TR_IM_ELEC, TR_RES_ELEC),
        "FIRE": (TR_IM_FIRE, TR_RES_FIRE),
        "COLD": (TR_IM_COLD, TR_RES_COLD),
        "ICE": (TR_IM_COLD, TR_RES_COLD),
    }
    if attribute in elemental:
        immunity, resistance = elemental[attribute]
        if immunity in flags:
            return (0,)
        return (34,) if resistance in flags else (100,)
    if attribute in {"POIS", "NUKE"}:
        return (34,) if TR_RES_POIS in flags else (100,)
    if attribute == "LITE":
        if TR_IM_LITE in flags:
            return (0,)
        return (50, 44, 40, 36) if TR_RES_LITE in flags else (100,)
    if attribute == "DARK":
        if TR_IM_DARK in flags:
            return (0,)
        return (50, 44, 40, 36) if TR_RES_DARK in flags else (100,)
    high_resistance = {
        "SHARDS": (TR_RES_SHARDS, (75, 66, 60, 54)),
        "SOUND": (TR_RES_SOUND, (62, 55, 50, 45)),
        "CONFUSION": (TR_RES_CONF, (62, 55, 50, 45)),
        "CHAOS": (TR_RES_CHAOS, (75, 66, 60, 54)),
        "DISENCHANT": (TR_RES_DISEN, (75, 66, 60, 54)),
        # This intentionally reproduces calc_nexus_damage_rate(), which checks
        # disenchantment resistance for HP damage in the current game source.
        "NEXUS": (TR_RES_DISEN, (75, 66, 60, 54)),
        "NETHER": (TR_RES_NETHER, (75, 66, 60, 54)),
        "TIME": (TR_RES_TIME, (50, 44, 40, 36)),
        "WATER": (TR_RES_WATER, (50, 44, 40, 36)),
    }
    if attribute in high_resistance:
        resistance, rates = high_resistance[attribute]
        return rates if resistance in flags else (100,)
    if attribute == "ROCKET":
        return (50,) if TR_RES_SHARDS in flags else (100,)
    if attribute == "GRAVITY":
        return (66,) if TR_LEVITATION in flags else (100,)
    if attribute == "VOID":
        if TR_NO_TELE in flags:
            return (50, 44, 40, 36)
        return (66,) if TR_LEVITATION in flags else (100,)
    if attribute == "ABYSS":
        if TR_RES_DARK in flags:
            return (50, 44, 40, 36)
        if TR_NO_TELE in flags and TR_LEVITATION not in flags:
            return (125,)
    return (100,)


def expected_ability_base_damage(
    ability: str,
    monster: MonraceKnowledge,
    *,
    player_hp: int | None = None,
) -> float | None:
    """Return expected DAM_ROLL before projection resistance, or None if non-HP."""
    level = monster.level
    powerful = monster.powerful
    hp = monster.average_hp

    if ability in NO_DAMAGE:
        return None
    if ability == "ROCKET":
        return float(max(1, min(hp // 4, 800)))
    if ability == "SHOOT":
        return _expected_roll(
            0, monster.shoot_dice_num, monster.shoot_dice_sides
        )
    if ability in BREATH:
        divisor, cap = BREATH[ability]
        if ability in {"BR_VOID", "BR_ABYSS"}:
            return float(max(1, cap if hp // 3 > cap else hp // divisor))
        return float(max(1, min(hp // divisor, cap)))

    multiplier = 2 if powerful else 1
    if ability == "BA_NUKE":
        return _expected_roll(level * multiplier, 10, 6, multiplier=multiplier)
    if ability in {"BA_CHAO", "BA_VOID", "BA_ABYSS"}:
        return _expected_roll(level * (3 if powerful else 2), 10, 10)
    if ability in {"BA_ACID", "BA_ELEC", "BA_FIRE", "BA_COLD"}:
        if powerful:
            return _expected_roll(level * 4 + 50, 10, 10)
        base, sides = {
            "BA_ACID": (15, level * 3),
            "BA_ELEC": (8, level * 3 // 2),
            "BA_FIRE": (10, level * 7 // 2),
            "BA_COLD": (10, level * 3 // 2),
        }[ability]
        return _expected_roll(base, 1, sides)
    if ability == "BA_POIS":
        return _expected_roll(0, 12, 2, multiplier=multiplier)
    if ability == "BA_NETH":
        return _expected_roll(50 + level * multiplier, 10, 10)
    if ability == "BA_WATE":
        return _expected_roll(50, 1, level * (3 if powerful else 2))
    if ability in {"BA_MANA", "BA_DARK", "BA_LITE"}:
        return _expected_roll(level * 4 + 50, 10, 10)
    if ability == "BA_METEOR":
        return _expected_roll(50 + level * 5 // 2, 3, level)
    if ability == "DRAIN_MANA":
        return None
    if ability == "MIND_BLAST":
        return _expected_roll(0, 7, 7)
    if ability == "BRAIN_SMASH":
        return _expected_roll(0, 12, 12)
    if ability.startswith("CAUSE_"):
        number, sides = {
            "CAUSE_1": (3, 8), "CAUSE_2": (8, 8),
            "CAUSE_3": (10, 15), "CAUSE_4": (15, 15),
        }[ability]
        return _expected_roll(0, number, sides)
    if ability in {"BO_ACID", "BO_ELEC", "BO_FIRE", "BO_COLD"}:
        number, sides = {
            "BO_ACID": (7, 8), "BO_ELEC": (4, 8),
            "BO_FIRE": (9, 8), "BO_COLD": (6, 8),
        }[ability]
        return _expected_roll(level // 3 * multiplier, number, sides, multiplier=multiplier)
    if ability == "BO_NETH":
        return _expected_roll(30 + level * 4 // (2 if powerful else 3), 5, 5)
    if ability == "BO_WATE":
        return _expected_roll(level * 3 // (2 if powerful else 3), 10, 10)
    if ability == "BO_MANA":
        return _expected_roll(50, 1, level * 7 // 2)
    if ability == "BO_PLAS":
        return _expected_roll(10 + level * 3 // (2 if powerful else 3), 8, 7)
    if ability == "BO_ICEE":
        return _expected_roll(level * 3 // (2 if powerful else 3), 6, 6)
    if ability in {"BO_VOID", "BO_ABYSS"}:
        return _expected_roll(10 + level * 3 // (2 if powerful else 3), 13, 14)
    if ability == "BO_METEOR":
        return _expected_roll(30 + level * 2, 1, level)
    if ability == "BO_LITE":
        return _expected_roll(60 if powerful else 40, 1, level * (4 if powerful else 2))
    if ability == "MISSILE":
        return _expected_roll(level // 3, 2, 6)
    if ability == "HAND_DOOM":
        if player_hp is None:
            raise ValueError("HAND_DOOM requires current player HP")
        return _expected_roll(40 * (player_hp // 100), 1, 20, multiplier=player_hp, divisor=100)
    if ability == "PSY_SPEAR":
        return _expected_roll(
            150 if powerful else 100,
            1,
            level * 2 if powerful else level * 3 // 2,
        )
    raise ValueError(f"unsupported monster ability: {ability}")


def maximum_ability_base_damage(
    ability: str,
    monster: MonraceKnowledge,
    *,
    player_hp: int | None = None,
) -> int | None:
    """Return the maximum pre-resistance HP damage of one ability use."""
    level = monster.level
    powerful = monster.powerful
    hp = monster.max_hp

    if ability in NO_DAMAGE:
        return None
    if ability == "ROCKET":
        return max(1, min(hp // 4, 800))
    if ability == "SHOOT":
        return max(1, monster.shoot_dice_num * monster.shoot_dice_sides)
    if ability in BREATH:
        divisor, cap = BREATH[ability]
        if ability in {"BR_VOID", "BR_ABYSS"}:
            return max(1, cap if hp // 3 > cap else hp // divisor)
        return max(1, min(hp // divisor, cap))

    multiplier = 2 if powerful else 1
    if ability == "BA_NUKE":
        return max(1, level * multiplier + 60 * multiplier)
    if ability in {"BA_CHAO", "BA_VOID", "BA_ABYSS"}:
        return max(1, level * (3 if powerful else 2) + 100)
    if ability in {"BA_ACID", "BA_ELEC", "BA_FIRE", "BA_COLD"}:
        if powerful:
            return max(1, level * 4 + 150)
        base, sides = {
            "BA_ACID": (15, level * 3),
            "BA_ELEC": (8, level * 3 // 2),
            "BA_FIRE": (10, level * 7 // 2),
            "BA_COLD": (10, level * 3 // 2),
        }[ability]
        return max(1, base + sides)
    if ability == "BA_POIS":
        return 24 * multiplier
    if ability == "BA_NETH":
        return max(1, 150 + level * multiplier)
    if ability == "BA_WATE":
        return max(1, 50 + level * (3 if powerful else 2))
    if ability in {"BA_MANA", "BA_DARK", "BA_LITE"}:
        return max(1, level * 4 + 150)
    if ability == "BA_METEOR":
        return max(1, 50 + level * 11 // 2)
    if ability == "DRAIN_MANA":
        return None
    if ability == "MIND_BLAST":
        return 49
    if ability == "BRAIN_SMASH":
        return 144
    if ability.startswith("CAUSE_"):
        number, sides = {
            "CAUSE_1": (3, 8), "CAUSE_2": (8, 8),
            "CAUSE_3": (10, 15), "CAUSE_4": (15, 15),
        }[ability]
        return number * sides
    if ability in {"BO_ACID", "BO_ELEC", "BO_FIRE", "BO_COLD"}:
        number, sides = {
            "BO_ACID": (7, 8), "BO_ELEC": (4, 8),
            "BO_FIRE": (9, 8), "BO_COLD": (6, 8),
        }[ability]
        return max(1, level // 3 * multiplier + number * sides * multiplier)
    if ability == "BO_NETH":
        return max(1, 55 + level * 4 // (2 if powerful else 3))
    if ability == "BO_WATE":
        return max(1, 100 + level * 3 // (2 if powerful else 3))
    if ability == "BO_MANA":
        return max(1, 50 + level * 7 // 2)
    if ability == "BO_PLAS":
        return max(1, 66 + level * 3 // (2 if powerful else 3))
    if ability == "BO_ICEE":
        return max(1, 36 + level * 3 // (2 if powerful else 3))
    if ability in {"BO_VOID", "BO_ABYSS"}:
        return max(1, 192 + level * 3 // (2 if powerful else 3))
    if ability == "BO_METEOR":
        return max(1, 30 + level * 3)
    if ability == "BO_LITE":
        return max(1, (60 if powerful else 40) + level * (4 if powerful else 2))
    if ability == "MISSILE":
        return max(1, level // 3 + 12)
    if ability == "HAND_DOOM":
        if player_hp is None:
            raise ValueError("HAND_DOOM requires current player HP")
        return max(1, 60 * player_hp // 100)
    if ability == "PSY_SPEAR":
        return max(
            1,
            (150 if powerful else 100)
            + (level * 2 if powerful else level * 3 // 2),
        )
    raise ValueError(f"unsupported monster ability: {ability}")


@lru_cache(maxsize=4096)
def _ability_base_damage_distribution(
    ability: str,
    monster: MonraceKnowledge,
    player_hp: int | None,
) -> tuple[tuple[int, float], ...] | None:
    """Return the operational pre-resistance damage distribution for one use.

    Breath and rocket damage use maximum race HP, matching the conservative
    operational model. Dice retain their complete distribution instead of
    collapsing to either their mean or maximum.
    """
    level = monster.level
    powerful = monster.powerful
    hp = monster.max_hp

    if ability in NO_DAMAGE:
        return None
    if ability == "ROCKET":
        result = {max(1, min(hp // 4, 800)): 1.0}
    elif ability == "SHOOT":
        result = _roll_probability_distribution(
            0, monster.shoot_dice_num, monster.shoot_dice_sides
        )
    elif ability in BREATH:
        divisor, cap = BREATH[ability]
        if ability in {"BR_VOID", "BR_ABYSS"}:
            damage = cap if hp // 3 > cap else hp // divisor
        else:
            damage = min(hp // divisor, cap)
        result = {max(1, damage): 1.0}
    else:
        multiplier = 2 if powerful else 1
        if ability == "BA_NUKE":
            result = _roll_probability_distribution(
                level * multiplier, 10, 6, multiplier=multiplier
            )
        elif ability in {"BA_CHAO", "BA_VOID", "BA_ABYSS"}:
            result = _roll_probability_distribution(
                level * (3 if powerful else 2), 10, 10
            )
        elif ability in {"BA_ACID", "BA_ELEC", "BA_FIRE", "BA_COLD"}:
            if powerful:
                result = _roll_probability_distribution(level * 4 + 50, 10, 10)
            else:
                base, sides = {
                    "BA_ACID": (15, level * 3),
                    "BA_ELEC": (8, level * 3 // 2),
                    "BA_FIRE": (10, level * 7 // 2),
                    "BA_COLD": (10, level * 3 // 2),
                }[ability]
                result = _roll_probability_distribution(base, 1, sides)
        elif ability == "BA_POIS":
            result = _roll_probability_distribution(
                0, 12, 2, multiplier=multiplier
            )
        elif ability == "BA_NETH":
            result = _roll_probability_distribution(
                50 + level * multiplier, 10, 10
            )
        elif ability == "BA_WATE":
            result = _roll_probability_distribution(
                50, 1, level * (3 if powerful else 2)
            )
        elif ability in {"BA_MANA", "BA_DARK", "BA_LITE"}:
            result = _roll_probability_distribution(level * 4 + 50, 10, 10)
        elif ability == "BA_METEOR":
            result = _roll_probability_distribution(
                50 + level * 5 // 2, 3, level
            )
        elif ability == "MIND_BLAST":
            result = _roll_probability_distribution(0, 7, 7)
        elif ability == "BRAIN_SMASH":
            result = _roll_probability_distribution(0, 12, 12)
        elif ability.startswith("CAUSE_"):
            number, sides = {
                "CAUSE_1": (3, 8),
                "CAUSE_2": (8, 8),
                "CAUSE_3": (10, 15),
                "CAUSE_4": (15, 15),
            }[ability]
            result = _roll_probability_distribution(0, number, sides)
        elif ability in {"BO_ACID", "BO_ELEC", "BO_FIRE", "BO_COLD"}:
            number, sides = {
                "BO_ACID": (7, 8),
                "BO_ELEC": (4, 8),
                "BO_FIRE": (9, 8),
                "BO_COLD": (6, 8),
            }[ability]
            result = _roll_probability_distribution(
                level // 3 * multiplier,
                number,
                sides,
                multiplier=multiplier,
            )
        elif ability == "BO_NETH":
            result = _roll_probability_distribution(
                30 + level * 4 // (2 if powerful else 3), 5, 5
            )
        elif ability == "BO_WATE":
            result = _roll_probability_distribution(
                level * 3 // (2 if powerful else 3), 10, 10
            )
        elif ability == "BO_MANA":
            result = _roll_probability_distribution(50, 1, level * 7 // 2)
        elif ability == "BO_PLAS":
            result = _roll_probability_distribution(
                10 + level * 3 // (2 if powerful else 3), 8, 7
            )
        elif ability == "BO_ICEE":
            result = _roll_probability_distribution(
                level * 3 // (2 if powerful else 3), 6, 6
            )
        elif ability in {"BO_VOID", "BO_ABYSS"}:
            result = _roll_probability_distribution(
                10 + level * 3 // (2 if powerful else 3), 13, 14
            )
        elif ability == "BO_METEOR":
            result = _roll_probability_distribution(30 + level * 2, 1, level)
        elif ability == "BO_LITE":
            result = _roll_probability_distribution(
                60 if powerful else 40,
                1,
                level * (4 if powerful else 2),
            )
        elif ability == "MISSILE":
            result = _roll_probability_distribution(level // 3, 2, 6)
        elif ability == "HAND_DOOM":
            if player_hp is None:
                raise ValueError("HAND_DOOM requires current player HP")
            result = _roll_probability_distribution(
                40 * (player_hp // 100),
                1,
                20,
                multiplier=player_hp,
                divisor=100,
            )
        elif ability == "PSY_SPEAR":
            result = _roll_probability_distribution(
                150 if powerful else 100,
                1,
                level * 2 if powerful else level * 3 // 2,
            )
        else:
            raise ValueError(f"unsupported monster ability: {ability}")
    return tuple(sorted(result.items()))


@lru_cache(maxsize=4096)
def _resisted_ability_damage_distribution(
    ability: str,
    monster: MonraceKnowledge,
    flags: frozenset[int],
    player_hp: int | None,
    blind: bool,
) -> tuple[tuple[int, float], ...] | None:
    base = _ability_base_damage_distribution(ability, monster, player_hp)
    if base is None:
        return None
    if ability == "SHOOT" and TR_INVULN_ARROW in flags and not blind:
        return ((0, 1.0),)

    rates = _attribute_rates(ABILITY_ATTRIBUTE.get(ability, "RAW"), flags)
    result: dict[int, float] = {}
    for damage, probability in base:
        for rate in rates:
            resisted = damage * rate // 100
            result[resisted] = result.get(resisted, 0.0) + probability / len(rates)
    return tuple(sorted(result.items()))


def _distribution_percentile(
    distribution: tuple[tuple[int, float], ...] | dict[int, float],
    percentile: int,
) -> int:
    items = distribution.items() if isinstance(distribution, dict) else distribution
    cumulative = 0.0
    for damage, probability in sorted(items):
        cumulative += probability
        if cumulative + 1e-12 >= percentile / 100.0:
            return damage
    return max(damage for damage, _ in items)


def _convolve_damage_distributions(
    left: dict[int, float], right: tuple[tuple[int, float], ...]
) -> dict[int, float]:
    result: dict[int, float] = {}
    for left_damage, left_probability in left.items():
        for right_damage, right_probability in right:
            damage = left_damage + right_damage
            result[damage] = (
                result.get(damage, 0.0)
                + left_probability * right_probability
            )
    return result


def aggregate_ranged_damage_percentile(
    monster: MonraceKnowledge,
    *,
    actions: int,
    selection_probabilities: dict[str, float],
    flags: frozenset[int] = frozenset(),
    player_hp: int | None = None,
    blind: bool = False,
    saving_skill: int = 0,
    percentile: int = 95,
) -> RangedDamagePercentile:
    """Return the p95 total from the complete per-action damage mixture."""
    if not 1 <= percentile <= 100:
        raise ValueError(f"percentile must be in [1, 100]: {percentile}")

    per_action: dict[int, float] = {0: 1.0}
    single_hit_floor = 0
    for ability, selection_probability in selection_probabilities.items():
        selected_probability = min(
            1.0,
            max(
                0.0,
                monster.spell_frequency / 100.0 * selection_probability,
            ),
        )
        if selected_probability <= 0.0:
            continue
        resisted = _resisted_ability_damage_distribution(
            ability, monster, flags, player_hp, blind
        )
        if resisted is None:
            continue

        throughput = _effect_throughput(
            ability,
            monster,
            flags=flags,
            saving_skill=saving_skill,
            blind=blind,
        )
        conditional: dict[int, float] = {0: 1.0 - throughput}
        for damage, probability in resisted:
            conditional[damage] = (
                conditional.get(damage, 0.0) + throughput * probability
            )

        per_action[0] -= selected_probability
        for damage, probability in conditional.items():
            per_action[damage] = (
                per_action.get(damage, 0.0)
                + selected_probability * probability
            )

        if any(damage > 0 for damage, _ in resisted) and throughput > 0.0:
            single_hit_floor = max(
                single_hit_floor,
                _distribution_percentile(resisted, percentile),
            )

    per_action = {
        damage: probability
        for damage, probability in per_action.items()
        if probability > 1e-15
    }
    per_action_items = tuple(sorted(per_action.items()))
    aggregate = {0: 1.0}
    for _ in range(max(0, actions)):
        aggregate = _convolve_damage_distributions(aggregate, per_action_items)

    total_damage = _distribution_percentile(aggregate, percentile)
    probability_any_damage = 1.0 - aggregate.get(0, 0.0)
    floor_applied = (
        total_damage == 0
        and probability_any_damage > 0.0
        and single_hit_floor > 0
    )
    if floor_applied:
        total_damage = single_hit_floor
    expected_damage = sum(
        damage * probability for damage, probability in aggregate.items()
    )
    return RangedDamagePercentile(
        total_damage=total_damage,
        expected_damage=expected_damage,
        probability_any_damage=probability_any_damage,
        single_hit_floor=single_hit_floor,
        floor_applied=floor_applied,
    )


def maximum_ability_hp_damage(
    ability: str,
    monster: MonraceKnowledge,
    *,
    flags: frozenset[int] = frozenset(),
    player_hp: int | None = None,
    blind: bool = False,
) -> int | None:
    """Return a resistance-aware worst case for one successful ability use."""
    damage = maximum_ability_base_damage(ability, monster, player_hp=player_hp)
    if damage is None:
        return None
    if ability == "SHOOT" and TR_INVULN_ARROW in flags and not blind:
        return 0
    rates = _attribute_rates(ABILITY_ATTRIBUTE.get(ability, "RAW"), flags)
    return max(damage * rate // 100 for rate in rates)


def expected_ability_hp_damage(
    ability: str,
    monster: MonraceKnowledge,
    *,
    flags: frozenset[int] = frozenset(),
    player_hp: int | None = None,
    blind: bool = False,
    saving_skill: int | None = None,
) -> float | None:
    """Return expected HP damage after permanent equipment defenses.

    Temporary opposition, race-only traits, wraith form, multishadow and
    invulnerability are intentionally outside this static loadout evaluator.
    """
    damage = expected_ability_base_damage(ability, monster, player_hp=player_hp)
    if damage is None:
        return None
    if ability == "SHOOT" and TR_INVULN_ARROW in flags and not blind:
        return 0.0

    attribute = ABILITY_ATTRIBUTE.get(ability, "RAW")
    damage = _expected_rate_damage(damage, _attribute_rates(attribute, flags))
    if ability in REFLECTABLE and TR_REFLECT in flags:
        damage *= 0.1
    if saving_skill is not None and (
        ability in {"MIND_BLAST", "BRAIN_SMASH", "HAND_DOOM"}
        or ability.startswith("CAUSE_")
    ):
        effective_save = (
            max(5, saving_skill)
            if ability in {"MIND_BLAST", "BRAIN_SMASH"}
            else saving_skill
        )
        sides = 100 + monster.level // 2
        save_probability = min(sides, max(0, effective_save)) / sides
        damage *= 1.0 - save_probability
    return damage


def _saving_failure(ability: str, monster_level: int, saving_skill: int) -> float:
    effective_save = (
        max(5, saving_skill)
        if ability in {"MIND_BLAST", "BRAIN_SMASH"}
        else saving_skill
    )
    sides = 100 + monster_level // 2
    return 1.0 - min(sides, max(0, effective_save)) / sides


@lru_cache(maxsize=None)
def _dice_percentile(number: int, sides: int, percentile: int) -> int:
    counts = [1]
    for _ in range(number):
        next_counts = [0] * (len(counts) + sides)
        for subtotal, count in enumerate(counts):
            for face in range(1, sides + 1):
                next_counts[subtotal + face] += count
        counts = next_counts

    total = sides ** number
    threshold = (percentile * total + 99) // 100
    cumulative = 0
    for damage, count in enumerate(counts):
        cumulative += count
        if cumulative >= threshold:
            return damage
    return number * sides


def _binomial_percentile(trials: int, probability: float, percentile: int) -> int:
    if trials <= 0 or probability <= 0.0:
        return 0
    if probability >= 1.0:
        return trials
    target = percentile / 100.0
    cumulative = 0.0
    for successes in range(trials + 1):
        cumulative += (
            comb(trials, successes)
            * probability ** successes
            * (1.0 - probability) ** (trials - successes)
        )
        if cumulative >= target:
            return successes
    return trials


def cause_damage_percentile(
    ability: str,
    monster: MonraceKnowledge,
    *,
    actions: int,
    selection_probability: float,
    saving_skill: int,
    percentile: int = 95,
) -> CauseDamagePercentile:
    """Conservative percentile damage for a CAUSE spell over several actions."""
    if not ability.startswith("CAUSE_"):
        raise ValueError(f"not a CAUSE ability: {ability}")
    if not 1 <= percentile <= 100:
        raise ValueError(f"percentile must be in [1, 100]: {percentile}")

    number, sides = {
        "CAUSE_1": (3, 8),
        "CAUSE_2": (8, 8),
        "CAUSE_3": (10, 15),
        "CAUSE_4": (15, 15),
    }[ability]
    per_action_probability = min(
        1.0,
        max(
            0.0,
            monster.spell_frequency
            / 100.0
            * selection_probability
            * _saving_failure(ability, monster.level, saving_skill),
        ),
    )
    successful_casts = _binomial_percentile(
        actions, per_action_probability, percentile
    )
    damage_per_cast = _dice_percentile(number, sides, percentile)
    return CauseDamagePercentile(
        ability=ability,
        per_action_probability=per_action_probability,
        successful_casts=successful_casts,
        damage_per_cast=damage_per_cast,
        total_damage=successful_casts * damage_per_cast,
    )


def _effect_throughput(
    ability: str,
    monster: MonraceKnowledge,
    *,
    flags: frozenset[int],
    saving_skill: int,
    blind: bool,
) -> float:
    if ability == "SHOOT" and TR_INVULN_ARROW in flags and not blind:
        return 0.0
    probability = 0.1 if ability in REFLECTABLE and TR_REFLECT in flags else 1.0
    if (
        ability in {"MIND_BLAST", "BRAIN_SMASH", "HAND_DOOM"}
        or ability.startswith("CAUSE_")
        or ability in {"SCARE", "BLIND", "CONF", "SLOW", "HOLD"}
    ):
        probability *= _saving_failure(ability, monster.level, saving_skill)
    return probability


def evaluate_ability_effect(
    ability: str,
    monster: MonraceKnowledge,
    *,
    flags: frozenset[int] = frozenset(),
    player_hp: int = 1,
    blind: bool = False,
    saving_skill: int = 0,
) -> RangedAbilityResult:
    """Evaluate one successful monster ability selection against a loadout."""
    hp = expected_ability_hp_damage(
        ability,
        monster,
        flags=flags,
        player_hp=player_hp,
        blind=blind,
        saving_skill=saving_skill,
    )
    expected_hp = 0.0 if hp is None else hp
    probability = _effect_throughput(
        ability,
        monster,
        flags=flags,
        saving_skill=saving_skill,
        blind=blind,
    )
    if probability == 0:
        return RangedAbilityResult(expected_hp)

    attribute = ABILITY_ATTRIBUTE.get(ability, "RAW")
    conditional_damage = expected_hp / probability
    status: dict[str, float] = {}
    resource: dict[str, float] = {}

    def add_status(name: str, turns: float) -> None:
        status[name] = status.get(name, 0.0) + probability * turns

    def add_resource(name: str, events: float = 1.0) -> None:
        resource[name] = resource.get(name, 0.0) + probability * events

    tactical_events = {
        "SHRIEK": "monster-alert",
        "DISPEL": "buff-dispel",
        "HASTE": "monster-haste",
        "HEAL": "monster-heal",
        "INVULNER": "monster-invulnerability",
        "BLINK": "monster-reposition",
        "TPORT": "monster-escape",
        "WORLD": "time-stop",
        "SPECIAL": "special-ability",
        "TELE_TO": "forced-teleport-to",
        "TELE_AWAY": "forced-teleport-away",
        "TELE_LEVEL": "forced-level-teleport",
        "DARKNESS": "darkness",
        "TRAPS": "trap-creation",
        "FORGET": "map-forgetting",
        "RAISE_DEAD": "raise-dead",
        "ANIM_DEAD": "raise-dead",
    }
    if ability in SUMMON_ABILITIES:
        add_resource("summoning")
    elif ability in tactical_events:
        add_resource(tactical_events[ability])
    elif ability in {"SCARE", "BLIND", "CONF", "SLOW", "HOLD"}:
        protecting_flag = {
            "SCARE": TR_RES_FEAR,
            "BLIND": TR_RES_BLIND,
            "CONF": TR_RES_CONF,
            # This reproduces spell_RF5_SLOW(), which checks confusion resist.
            "SLOW": TR_RES_CONF,
            "HOLD": TR_FREE_ACT,
        }[ability]
        if protecting_flag not in flags:
            name, turns = {
                "SCARE": ("afraid", 5.5),
                "BLIND": ("blind", 13.5),
                "CONF": ("confused", 5.5),
                "SLOW": ("slowed", 5.5),
                "HOLD": ("paralyzed", 5.5),
            }[ability]
            add_status(name, turns)
    elif ability == "DRAIN_MANA":
        add_resource("mana-drain")
    elif ability == "MIND_BLAST":
        if TR_RES_CONF not in flags:
            add_status("confused", 5.5)
        if TR_RES_CHAOS not in flags:
            add_status("hallucinating", 91.5)
        add_resource("mana-drain")
    elif ability == "BRAIN_SMASH":
        if TR_RES_BLIND not in flags:
            add_status("blind", 11.5)
        if TR_RES_CONF not in flags:
            add_status("confused", 5.5)
        if TR_FREE_ACT not in flags:
            add_status("paralyzed", 5.5)
        add_status("slowed", 5.5)
        if TR_RES_CHAOS not in flags:
            add_status("hallucinating", 274.5)
        add_resource("mana-drain")
        add_resource("intelligence-drain")
        add_resource("wisdom-drain")
    elif ability.startswith("CAUSE_"):
        if ability == "CAUSE_4":
            add_status("bleeding", 55.0)
        else:
            add_resource("equipment-curse")
    elif ability == "HAND_DOOM":
        add_resource("equipment-curse")
    elif attribute in {"POIS", "NUKE"} and TR_RES_POIS not in flags:
        add_status("poison", max(0.0, (conditional_damage - 1) / 2) + 10)
        if attribute == "NUKE":
            add_resource("mutation-or-polymorph", 0.2)
            add_resource("acid-item-damage", 1 / 6)
    elif attribute == "PLASMA":
        if TR_RES_SOUND not in flags:
            limit = 35 if conditional_damage > 40 else conditional_damage * 3 // 4 + 5
            add_status("stunned", (limit + 1) / 2)
        if not flags.intersection({TR_RES_FIRE, TR_IM_FIRE}):
            add_resource("acid-item-damage")
    elif attribute == "NETHER" and TR_RES_NETHER not in flags:
        add_resource("experience-drain")
    elif attribute == "WATER" and TR_RES_WATER not in flags:
        if TR_RES_SOUND not in flags:
            add_status("stunned", 20.5)
        if TR_RES_CONF not in flags:
            add_status("confused", 8.0)
        add_resource("cold-item-damage", 0.2)
    elif attribute == "CHAOS":
        if TR_RES_CHAOS not in flags:
            if TR_RES_CONF not in flags:
                add_status("confused", 19.5)
            add_status("hallucinating", 5.5)
            add_resource("mutation", 1 / 3)
            if TR_RES_NETHER not in flags:
                add_resource("experience-drain")
        add_resource("elemental-item-damage", 1 / 9 if TR_RES_CHAOS in flags else 1)
    elif attribute == "SHARDS":
        if TR_RES_SHARDS not in flags:
            add_status("bleeding", conditional_damage)
        add_resource("cold-item-damage", 1 / 13 if TR_RES_SHARDS in flags else 1)
    elif attribute == "SOUND":
        if TR_RES_SOUND not in flags:
            limit = 35 if conditional_damage > 90 else conditional_damage // 3 + 5
            add_status("stunned", (limit + 1) / 2)
        add_resource("cold-item-damage", 1 / 13 if TR_RES_SOUND in flags else 1)
    elif attribute == "CONFUSION" and TR_RES_CONF not in flags:
        add_status("confused", 20.5)
    elif attribute == "DISENCHANT" and TR_RES_DISEN not in flags:
        add_resource("equipment-disenchant")
    elif attribute == "NEXUS" and TR_RES_NEXUS not in flags:
        add_resource("nexus-effect")
    elif attribute == "FORCE" and TR_RES_SOUND not in flags:
        add_status("stunned", 10.5)
    elif attribute == "ROCKET":
        if TR_RES_SOUND not in flags:
            add_status("stunned", 10.5)
        if TR_RES_SHARDS not in flags:
            add_status("bleeding", conditional_damage / 2)
        add_resource("cold-item-damage", 1 / 12 if TR_RES_SHARDS in flags else 1)
    elif attribute == "INERTIA":
        add_status("slowed", 5.5)
    elif attribute == "LITE":
        if not blind and not flags.intersection({TR_RES_LITE, TR_RES_BLIND, TR_IM_LITE}):
            add_status("blind", 5.0)
    elif attribute == "DARK":
        if not blind and not flags.intersection({TR_RES_DARK, TR_RES_BLIND, TR_IM_DARK}):
            add_status("blind", 5.0)
    elif attribute == "TIME" and TR_RES_TIME not in flags:
        add_resource("time-effect")
    elif attribute == "GRAVITY":
        add_resource("passive-teleport")
        if TR_LEVITATION not in flags:
            add_status("slowed", 5.5)
            if TR_RES_SOUND not in flags:
                base = expected_ability_base_damage(ability, monster, player_hp=player_hp) or 0
                limit = 35 if base > 90 else base // 3 + 5
                add_status("stunned", (limit + 1) / 2)
        add_resource("cold-item-damage", 1 / 13 if TR_LEVITATION in flags else 1)
    elif attribute == "ICE":
        if TR_RES_SHARDS not in flags:
            add_status("bleeding", 22.5)
        if TR_RES_SOUND not in flags:
            add_status("stunned", 8.0)
        if TR_IM_COLD not in flags:
            add_resource(
                "cold-item-damage",
                1 / 12 if TR_RES_COLD in flags else 1,
            )
    elif attribute == "VOID":
        if TR_LEVITATION not in flags and TR_NO_TELE not in flags:
            add_status("slowed", 5.5)
        add_resource("cold-item-damage", 1 / 13 if TR_LEVITATION in flags else 1)
    elif attribute == "ABYSS":
        if TR_LEVITATION not in flags:
            add_status("slowed", 5.5)
        if not blind:
            if TR_RES_CHAOS not in flags:
                add_status("hallucinating", 5.5)
            if TR_RES_CONF not in flags:
                add_status("confused", 5.5)
            if TR_RES_FEAR not in flags:
                add_status("afraid", 5.5)
    elif ability in {"BA_METEOR", "BO_METEOR"}:
        add_resource("elemental-item-damage", 1 / 13 if TR_RES_SHARDS in flags else 1)

    return RangedAbilityResult(
        expected_hp,
        tuple(sorted(status.items())),
        tuple(sorted(resource.items())),
    )


def evaluate_warrior_ranged_defense(
    flags: frozenset[int],
    *,
    saving_skill: int,
    player_hp: int,
    encounters: tuple[EncounterTarget, ...],
    blind: bool = False,
    selection_context: SpellSelectionContext | None = None,
) -> WarriorRangedDefenseResult:
    """Aggregate static ranged exposure over ordinary depth encounters.

    Ability choice is uniform because the exact smart-monster selector depends
    on runtime distance, terrain, monster HP and learned player defenses.  The
    result remains explicitly incomplete until that context is supplied.
    """
    expected_damage = 0.0
    status: dict[str, float] = {}
    resource: dict[str, float] = {}
    unsupported: set[str] = set()
    for encounter in encounters:
        monster = encounter.knowledge
        abilities = tuple(sorted(monster.abilities))
        if not abilities or monster.spell_frequency <= 0:
            continue
        if selection_context is None and "STUPID" not in monster.flags:
            unsupported.add("smart-spell-selection-context")
        selection = (
            ability_selection_probabilities(monster, selection_context)
            if selection_context is not None
            else {ability: 1.0 / len(abilities) for ability in abilities}
        )
        attempt_probability = monster.spell_frequency / 100.0
        fail_rate = max(0, 25 - (monster.level + 3) // 4)
        for ability, selection_probability in selection.items():
            spell_success = (
                1.0
                if ability in INNATE_ABILITIES or "STUPID" in monster.flags
                else 1.0 - fail_rate / 100.0
            )
            occurrence = (
                encounter.weight
                * attempt_probability
                * selection_probability
                * spell_success
            )
            result = evaluate_ability_effect(
                ability,
                monster,
                flags=flags,
                player_hp=player_hp,
                blind=blind,
                saving_skill=saving_skill,
            )
            expected_damage += occurrence * result.expected_hp_damage
            unsupported.update(result.unsupported_effects)
            for name, value in result.status_turn_exposure:
                status[name] = status.get(name, 0.0) + occurrence * value
            for name, value in result.resource_event_exposure:
                resource[name] = resource.get(name, 0.0) + occurrence * value
    return WarriorRangedDefenseResult(
        expected_damage,
        tuple(sorted(status.items())),
        tuple(sorted(resource.items())),
        frozenset(unsupported),
    )
