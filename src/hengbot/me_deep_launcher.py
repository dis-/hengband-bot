"""The Magic-Eater's launcher at 50F+: worn for its abilities, ammunition only when it hits hard.

Owner 2026-11-18 (verbatim): 「50F以降の装備優先度について。魔道具術師については射撃威力を評価値
から外し、弓枠は追加能力や耐性のみで評価する。また、射撃威力が100ダメージ/ターンを下回る場合は
矢も持たない。」

Two rules (their data in equipment_rules), each with its one reader here:

* ``launcher_power_unscored``: for class 16 at a depth of DEEP_FLOOR_DEPTH (50F) or deeper the
  equipment selection leaves the launcher's shooting power out (equipment_optimizer.
  optimize_loadout: the loadout's ``ranged_dps``, the obtainable-ammunition damage filter and the
  ordinary-Sling-yields-to-Light-Crossbow grade rule).  The bow slot then counts only through what
  every other slot counts through: the abilities and resistances (the depth requirements, the
  survival side, telepathy, speed, ...).  The depth is the band the selection chooses the loadout
  for (the descent's 80F, 81-90F and 91F+ bands, or the depth the caller gave).
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

Per stack (n1-c life-222, 2026-11-26, owner 「弱い矢を撃つ仕様に戻っているようだ。魔法道具優先は
どこかにいったらしい。」): ``ammo_unneeded`` alone read the best obtainable stack, so one strong Home
stack (追尾の矢 143/turn) lifted the carry target back to 99 and the shared carry plan filled it with
the plain store arrows (67/turn) -- bought every visit and fired at 95F.  ``weak_round`` is the one
verdict on a stack: under the rule (``judged``) a round below the floor is not ammunition at all.
Its readers: the carry plan every count, retention, Home top-up and purchase read (policy
``_ammo_plan``, scripts/ammo_plan_lint.py keeps the plan's callers on it), the carry target
(policy_home ``_ammo_procurement_target``: 0 for a weak stack, and no more than the strong rounds
carried -- nothing is procured for the shot) and the round the launcher fires out of town (policy
``_matching_ammo``).

A pending quest is no exception (owner 2026-11-18 「魔道具術師は矢の威力ではなく魔法道具の攻撃力で
評価する。装備優先度の例外にはしない。」): the rules hold whatever quest the town prepares for.
"""
from __future__ import annotations

from typing import Any

from hengbot import attack_expectation, equipment_rules
from hengbot.equipment_rules import SHOT_POWER_FLOOR
from hengbot.launcher_damage import LAUNCHER_PROPERTIES, launcher_average_damage

# The two rules' data and ``launcher_power_unscored`` are equipment_rules' (the one table of the
# owner's equipment rules, equipment review stage E1); this module reads them for the town.


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
    return equipment_rules.launcher_power_unscored(snapshot.player.class_id, policy._planned_depth())


def ammo_unneeded(policy: Any, snapshot: Any) -> bool:
    """Whether the character carries no ammunition (the second half of the decision).

    Read per player action, the one attack-power reading left out of the 2026-11-19 rule
    「攻撃力の判定を1行動あたりではなく、10ゲームターンあたりのダメージで評価して」: the owner, asked
    whether a fast Magic-Eater should then carry its arrows at 50F+, answered (verbatim)
    「矢の件だけ違う。魔法道具が充実してくるタイミングなので単に弱い矢はいらない」.  So the shot is
    weighed per action against the floor, and speed does not bring weak rounds back
    (scripts/attack_time_lint_baseline.json records this comparison).

    The finale too (owner 2026-11-23 「魔道具術師は決戦で矢は撃たない。全て自宅に預ける。」,
    angband_finale ``no_ammunition``): whatever the shot's power."""
    from hengbot import angband_finale  # import cycle
    if angband_finale.no_ammunition(policy, snapshot):
        return True
    return (planned_unscored(policy, snapshot)
            and shot_power_per_turn(policy, snapshot) < SHOT_POWER_FLOOR)


def judged(policy: Any, snapshot: Any) -> bool:
    """Whether each round is weighed against the floor: the rule's Magic-Eater (``planned_unscored``)
    or the finale (angband_finale ``no_ammunition``: every round)."""
    from hengbot import angband_finale  # import cycle
    return planned_unscored(policy, snapshot) or angband_finale.no_ammunition(policy, snapshot)


def weak_round(policy: Any, snapshot: Any, item: Any) -> bool:
    """The one per-stack verdict: a round of the worn launcher's type the rule leaves at Home and
    never fires -- its shot under ``SHOT_POWER_FLOOR`` per player action (the name's figure,
    attack_expectation._shot_per_turn), or any round in the finale.

    Owner 2026-11-18 「射撃威力が100ダメージ/ターンを下回る場合は矢も持たない」, and on speed
    (``ammo_unneeded``) 「魔法道具が充実してくるタイミングなので単に弱い矢はいらない」: the floor is the
    stack's own, not the best stack's (n1-c life-222 2026-11-26: one 143/turn Home stack kept 99
    plain 67/turn arrows bought and fired)."""
    if not getattr(item, "is_ammo", False) or not judged(policy, snapshot):
        return False
    from hengbot import angband_finale  # import cycle
    if angband_finale.no_ammunition(policy, snapshot):
        return True
    launcher = policy._equipped_launcher(snapshot)
    if launcher is None or launcher.sval not in LAUNCHER_PROPERTIES or item.tval != launcher.ammo_tval:
        return False
    return attack_expectation._shot_per_turn(launcher, item) < SHOT_POWER_FLOOR


def plan_admits(policy: Any, snapshot: Any):
    """The carry plan's stack filter (ammo_carry.ammo_carry_plan ``admits``): None while no round
    is judged, else the rounds ``weak_round`` keeps."""
    if not judged(policy, snapshot):
        return None
    return lambda item: not weak_round(policy, snapshot, item)
