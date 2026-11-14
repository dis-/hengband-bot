"""The Magic-Eater's absorbed attack powers in the loadout evaluator (owner 2026-11-08).

Owner decision 2026-11-08: 「魔道具術師の装備の評価に、知能（取り込んだ力の失敗率）を
入れますか？」 -> 「失敗率を評価に入れる」 (「魔道具術師では、知能の上がり下がりで変わる
取り込んだ力の失敗率を評価に加え、知能を上げる装備を高く見る。」).  n1-b life-339
(Lv29) kept ☆『ラバー・コート』 and shelved ★『ホルヘンネス』 (+2 INT): the shared
warrior evaluator scored melee, AC, resistances and survival but never INT.

The fail chance of an absorbed power is cmd-item/cmd-magiceat.cpp
do_cmd_magic_eater (and the identical list display, :255-275)::

    level  = rod ? baseitem.level * 5 / 6 - 5 : baseitem.level
    chance = level * 4 / 5 + 20
    chance -= 3 * (adj_mag_stat[stat_index[spell_stat]] - 1)
    level /= 2
    if (plev > level) chance -= 3 * (plev - level)
    chance = mod_spell_chance_1(chance)          spell/spell-info.cpp
    chance = max(chance, adj_mag_fail[stat_index[spell_stat]])
    chance += stun penalty                       (none: an equipment comparison)
    chance = min(chance, 95)
    chance = mod_spell_chance_2(chance)

The Magic-Eater's spell_stat is INT (lib/edit/ClassMagicDefinitions.jsonc
MAGIC_EATER "magic_status": "INT").  mod_spell_chance_1 adds to_m_chance
(player-status.cpp calc_to_magic_chance: the personality part below; the
HARD_SPELL curse of a wielded item is a curse flag the catalog does not carry
and is left out), +20 for TR_HARD_SPELL, and -4 / -3 / -2 for
TR_DEC_MANA with TR_EASY_SPELL / TR_EASY_SPELL / TR_DEC_MANA;
mod_spell_chance_2 is -1 for TR_DEC_MANA, +5 for TR_HARD_SPELL, floored at 0.

The offense is the expected damage of one use per player turn (a use costs
100 energy, cmd-magiceat.cpp:502), the best held attack power per encounter
scored as me_device_attacks scores a target: success x min(average damage after
the race's known resistances, the race's average hp).  It enters the
LoadoutMetrics as ``device_dps``, beside the launcher's ``ranged_dps``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from hengbot import me_device_attacks
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
# The fail chance and its tables live with the one owner of an absorbed power's rate
# (me_power_success); the names stay importable from here.
from hengbot.me_power_success import (  # noqa: F401
    ADJ_MAG_FAIL, ADJ_MAG_STAT, PERSONALITY_TO_M_CHANCE, TR_DEC_MANA, TR_EASY_SPELL, TR_HARD_SPELL,
    fail_percent_at_index,
)
from hengbot.warrior_equipment_evaluator import modify_stat_value, stat_index


TR_INT = 1


@dataclass(frozen=True)
class MagicEaterOffenseInputs:
    """Worn-independent inputs of the absorbed-power offense of one character."""

    level: int
    natural_int: int
    intrinsic_int: int = 0
    personality_id: int = 0
    # (kind, sval) of every held attack power (me_device_attacks.POWERS keys).
    powers: tuple[tuple[str, int], ...] = ()
    # (kind, sval) of every held SURVIVAL_POWERS power.
    survival_powers: tuple[tuple[str, int], ...] = ()


# The absorbed powers the bot casts to survive (owner 2026-11-08 「魔法成功率は生存に
# 貢献する別枠で評価」), by category, with the BaseitemDefinitions.jsonc level and
# the power-list names.  Escape: Teleport Other (me_powers THREAT), Teleportation,
# *Destruction* (destruction_use); recovery: Cure Light Wounds (the blindness cure,
# status_cure), Curing, Healing (arena); speed: Speed (me_capability's Speed-potion
# row, me_powers FIGHT).
ESCAPE, RECOVERY, SPEED, ATTACK = "escape", "recovery", "speed", "attack"
SURVIVAL_POWERS = {
    ("staff", 4): (ESCAPE, 20, ("テレポート", "Teleportation")),
    ("wand", 3): (ESCAPE, 20, ("テレポート・アウェイ", "Teleport Other")),
    ("rod", 13): (ESCAPE, 45, ("テレポート・アウェイ", "Teleport Other")),
    ("staff", 29): (ESCAPE, 50, ("*破壊*", "*Destruction*")),
    ("staff", 16): (RECOVERY, 5, ("軽傷の治癒", "Cure Light Wounds")),
    ("staff", 17): (RECOVERY, 25, ("癒し", "Curing")),
    ("staff", 18): (RECOVERY, 70, ("体力回復", "Healing")),
    ("rod", 8): (RECOVERY, 65, ("癒し", "Curing")),
    ("rod", 9): (RECOVERY, 80, ("体力回復", "Healing")),
    ("staff", 22): (SPEED, 40, ("スピード", "Speed")),
    ("rod", 11): (SPEED, 60, ("スピード", "Speed")),
}
_SURVIVAL_BY_NAME = {(key[0], name): key for key, (_c, _l, names) in SURVIVAL_POWERS.items()
                     for name in names}

# Weight of the escape-reliability term (owner 2026-11-08 「盲目耐性は逃走手段の確実化
# ということで別枠で評価。点数の付け方は任せるが、AC3という微差よりは大きく評価すること。」).
# A blinded character cannot read Teleportation, Word of Recall or *Destruction*
# scrolls (cmd-item/cmd-read.cpp:37 refuses reading while blind), so against a
# monster that can blind it the loadout's scroll escape is unreliable.  The
# modelled blind turns themselves are tiny (n1-b life-339: 0.0023 status turns
# per turn), so the weight is the owner's
# judgement, not a derived rate: an unprotected loadout loses 10% of its survival
# per unit share of the encounter set that can blind it.  On the recorded n1-b
# visit (30% of the set can blind) that is 3.0% of the main score, about three
# times the 3-AC difference (1.05%) the owner named as the floor.
BLIND_ESCAPE_WEIGHT = 0.10
TR_RES_LITE = 54
TR_RES_DARK = 55
TR_RES_BLIND = 56
TR_IM_DARK = 157


def absorbed_power_fail_percent(
    kind: str,
    base_level: int,
    player_level: int,
    intelligence: int,
    *,
    personality_id: int = 0,
    flags: frozenset[int] = frozenset(),
) -> int:
    """The displayed fail% of an absorbed power (cmd-magiceat.cpp), unstunned: an
    equipment comparison (me_power_success.fail_percent_at_index)."""
    return fail_percent_at_index(kind, base_level, player_level, stat_index(intelligence),
                                 personality_id=personality_id, flags=flags)


def held_attack_powers(device_lists) -> tuple[tuple[str, int], ...]:
    """(kind, sval) of the attack powers in the last displayed power lists.

    The game lists only absorbed powers (count > 0, cmd-magiceat.cpp), so a
    listed row is held whatever its charge; town recharges it before the
    departure the loadout is chosen for.
    """
    held = set()
    for kind, (_turn, rows) in (device_lists or {}).items():
        for row in rows:
            power = me_device_attacks._BY_NAME.get((kind, row.get("name")))
            if power is not None and not power.group_only:
                held.add((power.kind, power.sval))
    return tuple(sorted(held))


def loadout_intelligence(inputs: MagicEaterOffenseInputs, int_pval: int) -> int:
    return modify_stat_value(inputs.natural_int, inputs.intrinsic_int + int_pval)


def magic_eater_device_dps(
    inputs: MagicEaterOffenseInputs | None,
    int_pval: int,
    flags: frozenset[int],
    encounters: Iterable,
) -> float:
    """Encounter-weighted best absorbed attack per player turn under this loadout's INT."""
    if inputs is None or not inputs.powers:
        return 0.0
    intelligence = loadout_intelligence(inputs, int_pval)
    powers = [me_device_attacks.POWERS[key] for key in inputs.powers if key in me_device_attacks.POWERS]
    success = {
        (power.kind, power.sval): (100 - absorbed_power_fail_percent(
            power.kind, power.level, inputs.level, intelligence,
            personality_id=inputs.personality_id, flags=flags)) / 100
        for power in powers
    }
    total = 0.0
    weight = 0.0
    for encounter in encounters:
        knowledge = encounter.knowledge
        hp = max(knowledge.average_hp, 0)
        best = max(
            (success[(power.kind, power.sval)]
             * min(me_device_attacks.expected_damage(power, inputs.level, knowledge.flags), hp)
             for power in powers),
            default=0.0,
        )
        total += encounter.weight * best
        weight += encounter.weight
    return total / weight if weight > 0 else 0.0


def held_survival_powers(device_lists) -> tuple[tuple[str, int], ...]:
    """(kind, sval) of the SURVIVAL_POWERS in the last displayed power lists."""
    held = set()
    for kind, (_turn, rows) in (device_lists or {}).items():
        for row in rows:
            key = _SURVIVAL_BY_NAME.get((kind, row.get("name")))
            if key is not None:
                held.add(key)
    return tuple(sorted(held))


def held_magic_eater_powers(device_lists) -> tuple[tuple[str, int], ...]:
    """The held attack and survival powers the loadout evaluator reads (sorted)."""
    return tuple(sorted(set(held_attack_powers(device_lists))
                        | set(held_survival_powers(device_lists))))


def _success(inputs: MagicEaterOffenseInputs, kind: str, level: int,
             intelligence: int, flags: frozenset[int]) -> float:
    return (100 - absorbed_power_fail_percent(
        kind, level, inputs.level, intelligence,
        personality_id=inputs.personality_id, flags=flags)) / 100


def _representative_powers(inputs: MagicEaterOffenseInputs) -> tuple[tuple[str, int, int], ...]:
    """(kind, sval, level) of the one power each held category is scored by.

    Chosen at the worn-independent INT (no equipment), so every loadout is
    scored by the same powers: in escape / recovery / speed the most reliable
    held power (the lowest fail%, the one the bot can count on), in attack the
    largest success x average damage (me_device_attacks's choice against a
    race without known flags).
    """
    base = loadout_intelligence(inputs, 0)
    chosen = []
    for category in (ESCAPE, RECOVERY, SPEED):
        held = [(key, level) for key, (cat, level, _names) in SURVIVAL_POWERS.items()
                if cat == category and key in inputs.survival_powers]
        if held:
            (kind, sval), level = max(
                held, key=lambda entry: (_success(inputs, entry[0][0], entry[1], base, frozenset()),
                                         -entry[1]))
            chosen.append((kind, sval, level))
    attacks = [me_device_attacks.POWERS[key] for key in inputs.powers if key in me_device_attacks.POWERS]
    if attacks:
        power = max(attacks, key=lambda power: (
            _success(inputs, power.kind, power.level, base, frozenset())
            * me_device_attacks.expected_damage(power, inputs.level, frozenset()), -power.level))
        chosen.append((power.kind, power.sval, power.level))
    return tuple(chosen)


def power_success_ratio(inputs: MagicEaterOffenseInputs | None, int_pval: int,
                        flags: frozenset[int]) -> float:
    """Mean success of the representative powers under this loadout / without equipment.

    Owner 2026-11-08 「魔法成功率は生存に貢献する別枠で評価」.  A turn spent on an
    escape, a heal, Speed or an attack that fails is a turn of incoming damage
    for nothing, so the turns the loadout survives are scaled by how much more
    (or less) often the powers work than at the character's own INT: survival x
    mean(success with this loadout) / mean(success with no equipment).  The
    weight is this plain ratio (exponent 1).  On the recorded n1-b visit (INT 16
    -> 18/00 with Holhenneth: Teleport Other / Cure Light Wounds 92 -> 94%,
    Dragon's Flame 54 -> 57%) it is +2.9%, nearly three times the 3-AC
    difference (1.05%) the owner named as the floor; one stat step (+1 INT at
    16) is about +1%, so a lone +1 INT cannot outweigh a real AC or resist loss.
    1.0 for a character without held survival or attack powers.
    """
    if inputs is None:
        return 1.0
    powers = _representative_powers(inputs)
    if not powers:
        return 1.0
    worn = loadout_intelligence(inputs, int_pval)
    base = loadout_intelligence(inputs, 0)
    with_loadout = sum(_success(inputs, kind, level, worn, flags) for kind, _sval, level in powers)
    without = sum(_success(inputs, kind, level, base, frozenset()) for kind, _sval, level in powers)
    return with_loadout / without if without > 0 else 1.0


def _blinds_unprotected(knowledge, flags: frozenset[int]) -> bool:
    """Whether a race can blind a player with ``flags`` (game: spell_RF5_BLIND and
    Brain Smash need resist blindness; light needs it or resist light,
    effect-player-resist-hurt.cpp:411; darkness needs it, resist dark or immune
    dark, :447-450; a BLIND blow needs it, monster-attack-status.cpp:24)."""
    if TR_RES_BLIND in flags:
        return False
    from hengbot.monster_ranged_evaluator import ABILITY_ATTRIBUTE

    for ability in knowledge.abilities:
        if ability in {"BLIND", "BRAIN_SMASH"}:
            return True
        attribute = ABILITY_ATTRIBUTE.get(ability)
        if attribute == "LITE" and TR_RES_LITE not in flags:
            return True
        if attribute == "DARK" and not flags & {TR_RES_DARK, TR_IM_DARK}:
            return True
    return any(blow.effect == "BLIND" for blow in knowledge.blows)


def unprotected_blind_share(flags: frozenset[int], encounters: Iterable) -> float:
    """Weight share of the encounter set that can blind a player with ``flags``."""
    total = 0.0
    blinding = 0.0
    for encounter in encounters:
        total += encounter.weight
        if _blinds_unprotected(encounter.knowledge, flags):
            blinding += encounter.weight
    return blinding / total if total > 0 else 0.0


def survival_factor(inputs: MagicEaterOffenseInputs | None, int_pval: int,
                    flags: frozenset[int], encounters: Iterable) -> float:
    """Class 16's survival multiplier: power success and escape reliability."""
    if inputs is None:
        return 1.0
    encounters = tuple(encounters)
    return power_success_ratio(inputs, int_pval, flags) * (
        1.0 - BLIND_ESCAPE_WEIGHT * unprotected_blind_share(flags, encounters))


def offense_inputs(class_id: int, level: int, natural_int: int, intrinsic_int: int,
                   personality_id: int, powers) -> MagicEaterOffenseInputs | None:
    """The evaluator's input for class 16, None for every other class.

    ``powers`` are held_magic_eater_powers: split here into the attack powers
    (device_dps and the attack category) and the SURVIVAL_POWERS.
    """
    if class_id != PLAYER_CLASS_MAGIC_EATER:
        return None
    powers = tuple(powers)
    return MagicEaterOffenseInputs(
        level=level, natural_int=natural_int, intrinsic_int=intrinsic_int,
        personality_id=personality_id,
        powers=tuple(key for key in powers if key in me_device_attacks.POWERS),
        survival_powers=tuple(key for key in powers if key in SURVIVAL_POWERS))
