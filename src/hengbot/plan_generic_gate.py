"""On a floor plan's floor, the generic walk, pickup and exploration act only where the plan names them.

Whole-bot maintainability review 2026-11-23, K1 / (b)-3, owner 2026-11-23 「作戦が名指しで許した時だけ」:
on a floor a fixed-quest plan runs (dungeon_ladder FLOOR_PLANS: quest_find_exit, quest25_battle,
quest_room_sweep), the shared ladder's generic walks, pickups and explorations -- the rungs below a plan
that answered nothing -- act only when the plan allows them by name (``ALLOWED``).  The survival rungs
still come first: none of their reasons is generic here (``GENERIC``).  A generic action the plan does
not allow is not taken quietly: its reason becomes the named stop ``quest-plan:generic-refused:<the
reason>`` (policy_constants.POLICY_FINAL_STOP_PREFIXES), the driver ends the run there, and the owner is
told which action the plan would have needed (「許していない場面で要りそうなら名指しで止めて報告」).

``GENERIC`` is the generic vocabulary, by the reasons the generic rungs send (fnmatch patterns): the
floor's exploration (ladder_idle ``explore``, its probes and breakouts), the walks to loot and its
pickups (``seek-loot``, ``loot:*``, ``pickup``, the chests' approach), and the walks for stairs or a
hunt (ladder_descent, ladder_combat's hunt, the sensed-threat hunt).  ``ALLOWED`` is each walk, pickup
or search off a plan's own order that a plan or the owner named, with the owner's words; a row there is
never refused (scripts/dungeon_ladder_lint.py checks each row against the source).

Nothing here is persisted: the gate reads the board and the decided reason.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import NamedTuple

from hengbot.policy_constants import PLAN_GENERIC_REFUSED_STOP_PREFIX

STOP_PREFIX = PLAN_GENERIC_REFUSED_STOP_PREFIX

# The generic walk, pickup and exploration reasons of the shared ladder (fnmatch patterns).
GENERIC = (
    # exploration (ladder_idle)
    "explore", "explore:*", "explore-oscillating:*", "probe", "breakout:seek-frontier",
    "seek-secret-wall",
    # loot (ladder_objectives _normal_loot_key, the chests)
    "seek-loot", "seek-loot:*", "loot:*", "pickup", "pickup:*", "chest:approach",
    "chest:collect-contents",
    # stairs and hunts (ladder_descent, ladder_combat's hunt, ladder_summoner_shots' sensed hunt)
    "descend", "clear-descent", "seek-downstairs", "stuck:seek-stairs", "stuck:wander", "hunt",
    "hunt:*", "esp-threat:hunt-*",
)


class Allowance(NamedTuple):
    pattern: str        # the reason (or an fnmatch pattern of the reasons) allowed
    plans: tuple        # the plan modules whose floors allow it
    producer: str       # the module that sends it
    rule: str           # the owner's words that name it


_SWEEP_PLANS = ("quest25_battle", "quest_room_sweep")

ALLOWED = (
    Allowance("quest-strategy:floor-restore-walk", _SWEEP_PLANS, "quest_plan_base",
              "owner 2026-11-23 「数マス以内なら拾って飲む」: a drained ability's restore potion on the "
              "floor within FLOOR_RESTORE_MAX_STEPS, walked to on the plan's quiet board"),
    Allowance("quest-strategy:floor-restore-pickup", _SWEEP_PLANS, "quest_plan_base",
              "owner 2026-11-23 「数マス以内なら拾って飲む」: its pickup"),
    Allowance("quest-strategy:detect-remaining-walk", ("quest_room_sweep",), "quest_detect_remaining",
              "owner 2026-11-20 「残りの敵を探す時は感知を使うこと」: the walk to the cell a detection of the "
              "remaining enemies is cast from"),
    Allowance("quest-strategy:mixed-assault-walk", ("quest_room_sweep",), "quest_mixed_assault",
              "QUEST_33, owner 2026-11-23 「加速して向かい、強引に邪悪側を排除する。」: the walk toward the "
              "EVIL side once the sides mixed"),
    Allowance("quest-patrol*", _SWEEP_PLANS, "kill_all_patrol",
              "owner 2026-11-13 「全滅クエストで作戦を終えても終わらない時は周回して探す・感知があれば感知して"
              "探す」: the KILL_ALL plan ended with the quest not won (quest_navigator EXECUTE)"),
)


def generic(reason: str | None) -> bool:
    """``reason`` is one of the shared ladder's generic walks, pickups or explorations."""
    return bool(reason) and any(fnmatchcase(reason, pattern) for pattern in GENERIC)


def allowed(reason: str | None, plan: str) -> bool:
    """``reason`` is named by an ``ALLOWED`` row for the floor of ``plan``."""
    return bool(reason) and any(plan in row.plans and fnmatchcase(reason, row.pattern)
                                for row in ALLOWED)


def running_plan(policy, snapshot) -> str | None:
    """The module of the floor plan that runs this floor (dungeon_ladder FLOOR_PLANS), else None."""
    if getattr(snapshot, "in_town", False) or getattr(snapshot, "store", None) is not None:
        return None
    from hengbot import quest25_battle, quest_find_exit, quest_room_sweep  # they import the ladder

    if quest25_battle.applies(policy, snapshot):
        return "quest25_battle"
    if quest_room_sweep._plan(policy, snapshot) is not None:
        return "quest_room_sweep"
    if quest_find_exit._plan(policy, snapshot) is not None:
        return "quest_find_exit"
    return None


def stop_reason(reason: str) -> str:
    return STOP_PREFIX + reason


def stop_message(reason: str) -> str:
    """The driver's banner for ``quest-plan:generic-refused:<reason>``."""
    return (f"<{reason}> the generic action '{reason[len(STOP_PREFIX):]}' on a quest plan's floor is "
            "not allowed by the plan (plan_generic_gate.ALLOWED, owner 2026-11-23 (b)-3); stopping the "
            "bot for investigation")


def after_ladder(policy, snapshot, key):
    """``key`` as decided; a generic reason the running plan does not allow becomes the named stop."""
    reason = policy.last_reason
    if key is None or not generic(reason):
        return key
    plan = running_plan(policy, snapshot)
    if plan is None or allowed(reason, plan):
        return key
    policy.last_reason = stop_reason(reason)
    return key
