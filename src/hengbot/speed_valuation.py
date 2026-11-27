"""How the equipment selection values speed: the one reader of a loadout's speed.

Owner 2026-11-17 (verbatim): 「装備最適化のスピードの評価を上げて。特にspeed+20までは生存に
大きく寄与する」, and on what to raise: 「時間あたりの打撃＋+20までを強く」.

Speed buys more player turns per game turn: ``speed_energy`` (Hengband
core/speed-table.cpp) is the energy one game turn gives, 10 at +0, 20 at +10,
30 at +20, 38 at +30.  Before this module the selection saw it only on the
survival side (warrior_loadout_evaluator divides the incoming damage by the
player's energy) and then threw it away: every set surviving 30 player turns was
"safe enough", the 95% melee cut compared damage per player ACTION, and speed
was the fifth tie-break.  So n1-c life-216 kept ダメージの指輪 (+16) and 追加攻撃の指輪
at +2 with スピードの指輪 (+7) and 活力のスピードの指輪 (+6) in the Home.

Two rules, both here:

* Damage per game time (「時間あたりの打撃」): every damage the selection compares
  (melee, the absorbed devices, the launcher) is per player action times
  ``loadout_energy / NORMAL_ENERGY``: damage per 10 game turns, the unit every attack-power
  judgement reads since 2026-11-19 (``per_10_game_turns_at``; attack_expectation
  ``per_10_game_turns``).  At +0 the value is unchanged.  The loadout's speed is counted
  here once: the survival weight below is a separate rule, not a second damage scaling.
* Speed up to +20 strongly (「+20までを強く」): the survival / kill ratio is
  weighted by ``speed_energy(min(speed, +20))`` relative to the field's best
  capped speed (``weighted_margin``).  Survival already grows with the energy,
  so below +20 a speed point counts squared; above +20 the weight is 1 and the
  energy table alone applies.  Relative to the field, so a field where every set
  has the same speed is compared exactly as before.  Monotone: more speed never
  lowers the damage, the survival or the weight.  The 30-turn survival floor
  keeps the player turns survived (energy counted once): a field-relative
  weight on that absolute floor let one slow-damage fast set push a good set
  under it (equipment_optimizer._stable_operational_best).

The 91F speed +25 requirement reads the same fact (``meets_speed_gate``): the
permanent speed, base plus gear, without a temporary haste or slowness.
"""

from __future__ import annotations

from typing import Iterable

from hengbot import haste_read
from hengbot.policy_constants import SPEED_GATE_MINIMUM, speed_energy

# The +0 player speed of the game (player-status.cpp: speed 110 is +0).
BASE_SPEED = 110
# The energy of one game turn at +0: the damage scale of this module.
NORMAL_ENERGY = speed_energy(BASE_SPEED)
# 「特にspeed+20までは生存に大きく寄与する」: the speed counted squared.
STRONG_SPEED_CAP = BASE_SPEED + 20
# A haste (set_acceleration) or a slowness (set_deceleration) is 10 speed.
TIMED_SPEED_STEP = 10


def loadout_speed(metrics) -> int:
    """The player's permanent speed with the evaluated loadout worn.

    ``player_speed`` is set by the evaluator (base speed without gear plus the
    loadout's gear speed); a metrics without it (a test fake) is +0 plus its
    ``speed_bonus``.
    """
    speed = getattr(metrics, "player_speed", None)
    return BASE_SPEED + metrics.speed_bonus if speed is None else speed


def loadout_energy(metrics) -> int:
    """The game energy per game turn of the loadout's speed."""
    return speed_energy(loadout_speed(metrics))


def per_10_game_turns_at(value: float, speed: int) -> float:
    """A per-action damage ``value`` at ``speed`` as damage per 10 game turns (one +0 turn).

    The arithmetic of every attack-power figure (owner 2026-11-19 「攻撃力の判定を1行動あたり
    ではなく、10ゲームターンあたりのダメージで評価して」): a game turn gives ``speed_energy``,
    an action costs 100, so 10 game turns hold ``speed_energy(speed) / NORMAL_ENERGY`` actions.
    The judgements read it through attack_expectation.per_10_game_turns; the loadout
    comparison through ``per_game_time``."""
    return value * speed_energy(speed) / NORMAL_ENERGY


def per_game_time(value: float, metrics) -> float:
    """A per-action damage ``value`` as damage per game time (+0 scale): per 10 game turns at
    the loadout's permanent speed (``per_10_game_turns_at``)."""
    return per_10_game_turns_at(value, loadout_speed(metrics))


def time_melee(metrics) -> float:
    return per_game_time(metrics.expected_dps, metrics)


def time_ranged(metrics) -> float:
    return per_game_time(metrics.ranged_dps, metrics)


def time_device(metrics) -> float:
    return per_game_time(metrics.device_dps, metrics)


def strong_speed_energy(metrics) -> int:
    """The energy of the loadout's speed capped at +20."""
    return speed_energy(min(loadout_speed(metrics), STRONG_SPEED_CAP))


def field_strong_speed_energy(metrics: Iterable) -> int:
    """The best capped energy of a field (NORMAL_ENERGY for an empty one)."""
    return max((strong_speed_energy(entry) for entry in metrics), default=NORMAL_ENERGY)


def strong_speed_weight(metrics, field_energy: int) -> float:
    """The survival weight of the loadout's speed up to +20 within its field (<= 1)."""
    return strong_speed_energy(metrics) / field_energy


def weighted_margin(metrics, field_energy: int) -> float:
    return metrics.combat_margin * strong_speed_weight(metrics, field_energy)


def meets_speed_gate(speed: int) -> bool:
    """The 91F requirement 「speed+25」 on a permanent speed."""
    return speed >= SPEED_GATE_MINIMUM


def permanent_player_speed(snapshot) -> int:
    """The board's player speed without a timed haste or slowness.

    The speed field adds a haste's +10 when it is yellow and a slowness's -10
    when it is violet (haste_read); the plain colour is neither or both, which
    cancel.  While riding the field is the mount's and the value is used as is.
    """
    speed = snapshot.player.speed
    if haste_read.adds_speed(snapshot):
        return speed - TIMED_SPEED_STEP
    if haste_read.subtracts_speed(snapshot):
        return speed + TIMED_SPEED_STEP
    return speed
