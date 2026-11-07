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
from hengbot.warrior_equipment_evaluator import modify_stat_value, stat_index, trunc_div


TR_INT = 1
TR_EASY_SPELL = 39
TR_DEC_MANA = 70
TR_HARD_SPELL = 135

# player/player-status-table.cpp adj_mag_stat / adj_mag_fail, indexed by stat_index.
ADJ_MAG_STAT = (
    0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3, 3,
    4, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
)
ADJ_MAG_FAIL = (
    99, 99, 99, 99, 99, 50, 30, 20, 15, 12, 11, 10, 9, 8, 7, 6, 6, 5, 5, 5,
    4, 4, 4, 4, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0,
)

# player/player-personality-types.h and calc_to_magic_chance.
PERSONALITY_TO_M_CHANCE = {1: 1, 2: -3, 7: 10, 10: 1, 12: 5}


@dataclass(frozen=True)
class MagicEaterOffenseInputs:
    """Worn-independent inputs of the absorbed-power offense of one character."""

    level: int
    natural_int: int
    intrinsic_int: int = 0
    personality_id: int = 0
    # (kind, sval) of every held attack power (me_device_attacks.POWERS keys).
    powers: tuple[tuple[str, int], ...] = ()


def absorbed_power_fail_percent(
    kind: str,
    base_level: int,
    player_level: int,
    intelligence: int,
    *,
    personality_id: int = 0,
    flags: frozenset[int] = frozenset(),
) -> int:
    """The displayed fail% of an absorbed power (cmd-magiceat.cpp)."""
    index = stat_index(intelligence)
    level = trunc_div(base_level * 5, 6) - 5 if kind == "rod" else base_level
    chance = trunc_div(level * 4, 5) + 20
    chance -= 3 * (ADJ_MAG_STAT[index] - 1)
    level = trunc_div(level, 2)
    if player_level > level:
        chance -= 3 * (player_level - level)
    hard = TR_HARD_SPELL in flags
    easy = TR_EASY_SPELL in flags
    dec_mana = TR_DEC_MANA in flags
    # mod_spell_chance_1
    chance += PERSONALITY_TO_M_CHANCE.get(personality_id, 0)
    if hard:
        chance += 20
    if dec_mana and easy:
        chance -= 4
    elif easy:
        chance -= 3
    elif dec_mana:
        chance -= 2
    chance = max(chance, ADJ_MAG_FAIL[index])
    chance = min(chance, 95)
    # mod_spell_chance_2
    if dec_mana:
        chance -= 1
    if hard:
        chance += 5
    return max(chance, 0)


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


def offense_inputs(class_id: int, level: int, natural_int: int, intrinsic_int: int,
                   personality_id: int, powers) -> MagicEaterOffenseInputs | None:
    """The evaluator's input for class 16, None for every other class."""
    if class_id != PLAYER_CLASS_MAGIC_EATER:
        return None
    return MagicEaterOffenseInputs(
        level=level, natural_int=natural_int, intrinsic_int=intrinsic_int,
        personality_id=personality_id, powers=tuple(powers))
