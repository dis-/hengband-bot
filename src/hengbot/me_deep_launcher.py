"""The Magic-Eater's launcher at 50F+: worn for its abilities, ammunition only when it hits hard.

Owner 2026-11-18 (verbatim): 「50F以降の装備優先度について。魔道具術師については射撃威力を評価値
から外し、弓枠は追加能力や耐性のみで評価する。また、射撃威力が100ダメージ/ターンを下回る場合は
矢も持たない。」

Two rules, each with its one reader here:

* ``launcher_power_unscored``: for class 16 at a depth of DEEP_FLOOR_DEPTH (50F) or deeper the
  equipment selection leaves the launcher's shooting power out (equipment_optimizer.
  optimize_loadout: the loadout's ``ranged_dps``, the obtainable-ammunition damage filter and the
  ordinary-Sling-yields-to-Light-Crossbow grade rule).  The bow slot then counts only through what
  every other slot counts through: the abilities and resistances (the depth requirements, the
  survival side, telepathy, speed, ...).  The depth is the band the selection chooses the loadout
  for (the descent's 80F and 81F+ bands, or the depth the caller gave).
* ``ammo_unneeded``: such a Magic-Eater whose shooting power is below ``SHOT_POWER_FLOOR`` (100
  damage per player turn) carries no ammunition: the carry target (policy_home.
  _ammo_procurement_target, which every purchase, Home withdrawal, supply count and retention of
  ammunition reads) is 0, so the existing Home and sale rules treat the rounds as any unneeded
  stack.  The depth is the one the town plans the departure for (``_planned_depth``).

The shooting power is the game's own figure per player turn on the ammunition's name, "(135/shot
101/turn)" (flavor-describer.cpp describe_ammo_detail; attack_expectation._shot_per_turn), the
best of the worn launcher's obtainable stacks (carried, Home and the supplier offers the
optimizer counts: policy_equipment._obtainable_launcher_ammunition).  Without any, the plain
store round's figure for that launcher (launcher_damage), so a newly worn launcher is judged
before its first round is bought.

A quest whose force asks for ranged power (Q2, Q22, Q31's ``launcher``, Q25's ``ranged``, a
``throwing_items.launcher_ammo`` carry) keeps the existing rules: the decision is about the
50F+ dive, not the shallower quests (owner 2026-11-02 Q2's average 25).
"""
from __future__ import annotations

from typing import Any

from hengbot import attack_expectation
from hengbot.launcher_damage import LAUNCHER_PROPERTIES, launcher_average_damage
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.policy_constants import DEEP_FLOOR_DEPTH

# 「射撃威力が100ダメージ/ターンを下回る場合は矢も持たない」
SHOT_POWER_FLOOR = 100.0


def ranged_force(force: Any) -> bool:
    """Whether a quest's required force asks for ranged power."""
    if not isinstance(force, dict):
        return False
    throwing = force.get("throwing_items")
    return bool(force.get("launcher") or force.get("ranged")
                or (isinstance(throwing, dict) and throwing.get("launcher_ammo")))


def quest_force(policy: Any, snapshot: Any) -> dict:
    """The required force of the quest the town prepares for (the optimizer's reading)."""
    strategy = (policy._carry_procurement_strategy(snapshot)
                or policy._quest_strategy_for_errand_or_floor(snapshot))
    force = getattr(strategy, "required_force", {})
    return force if isinstance(force, dict) else {}


def launcher_power_unscored(class_id: int, depth: int | None, *, ranged_quest: bool = False) -> bool:
    """Whether the selection leaves the launcher's shooting power out at ``depth``."""
    return (class_id == PLAYER_CLASS_MAGIC_EATER and depth is not None
            and depth >= DEEP_FLOOR_DEPTH and not ranged_quest)


def shot_power_per_turn(policy: Any, snapshot: Any) -> float:
    """The worn launcher's best obtainable shot: damage per player turn (the name's figure)."""
    launcher = policy._equipped_launcher(snapshot)
    if launcher is None or launcher.sval not in LAUNCHER_PROPERTIES:
        return 0.0
    stacks = [ammo for ammo in policy._obtainable_launcher_ammunition(snapshot)
              if ammo.tval == launcher.ammo_tval and ammo.count > 0]
    if stacks:
        return max(attack_expectation._shot_per_turn(launcher, ammo) for ammo in stacks)
    energy = LAUNCHER_PROPERTIES[launcher.sval][1]
    return launcher_average_damage(launcher) * 10000 / energy


def planned_unscored(policy: Any, snapshot: Any) -> bool:
    """``launcher_power_unscored`` for the departure the town plans (``_planned_depth``)."""
    class_id, depth = snapshot.player.class_id, policy._planned_depth()
    # The quest is read only where it can matter (it is the costly part).
    return (launcher_power_unscored(class_id, depth)
            and launcher_power_unscored(class_id, depth,
                                        ranged_quest=ranged_force(quest_force(policy, snapshot))))


def ammo_unneeded(policy: Any, snapshot: Any) -> bool:
    """Whether the character carries no ammunition (the second half of the decision)."""
    return (planned_unscored(policy, snapshot)
            and shot_power_per_turn(policy, snapshot) < SHOT_POWER_FLOOR)
