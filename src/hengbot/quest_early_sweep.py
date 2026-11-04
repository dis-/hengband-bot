"""What a plan's first phases leave alone on the way: ``engagement_plan.early_sweep``.

Owner 2026-11-05: 「作戦序盤のグレムリン、青ベトベト、冥界イモムシの処理を確実に行う工夫が欲しい」;
the approved formation (QUEST_2) orders the moving breeders first and the Undead masses last
(P8), the puddles shot from dry ground and never in melee (P7).

``stages`` are rows ``{"race", "goal"}``, in the plan's order; a stage ends when the phase owner
has cleared its race.  ``deferred_races`` are never-moving monsters: until the last stage ends
no owner of the plan targets, hunts or walks to one, unless it stands on the walk to the
current stage's goal, which it would otherwise block.

n1-a life-482, turn 522980: at [2,19] on the way to the gremlin one Undead mass came into view
at [12,34]; the residual-multiplier rung walked the player to [7,27], off the north route.
Undead masses act from the moment the player enters (race vision 70 over this 69-wide map,
monster-processor.cpp decide_process_continue), so they are in view early.

The survival rungs above the plan are not touched, and neither is the 20-action rule
(breeder_stalemate): its count still includes every perceived breeder.
"""

from __future__ import annotations

from hengbot.model import Position

PLAN_KEY = "early_sweep"


def _stage(policy, plan) -> dict | None:
    return next(
        (row for row in plan["stages"] if row["race"] not in policy._q2_cleared_races),
        None,
    )


def _walk(policy, snapshot, profile, stage) -> set[Position]:
    navigator = policy._quest_navigators.get(profile.quest_id)
    if navigator is None:
        return set()
    return set(navigator._static_path(snapshot.player.position, {Position(*stage["goal"])}))


def engaged(policy, snapshot, profile, monsters: list) -> list:
    """``monsters`` without the deferred ones off the walk to the current stage's goal."""
    plan = profile.engagement_plan.get(PLAN_KEY)
    stage = None if plan is None else _stage(policy, plan)
    if stage is None:
        return monsters
    deferred = set(plan["deferred_races"])
    if not any(monster.race_id in deferred for monster in monsters):
        return monsters
    walk = _walk(policy, snapshot, profile, stage)
    return [
        monster for monster in monsters
        if monster.race_id not in deferred or monster.position in walk
    ]
