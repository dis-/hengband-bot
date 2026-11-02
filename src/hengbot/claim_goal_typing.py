"""Former home of the goal typing; it lives in town_terminal now.

Structure stage 2 B slice 4 moved the goal typing next to the town hold that reads it.
This module only re-exports it under the old names for the record-only
readers that step 3 of the slice deletes.
"""

from hengbot.town_terminal import (  # noqa: F401
    EFFECT,
    ENTRANCE,
    ENTRANCE_OWNERS,
    EXPLORE_GOAL_OWNERS,
    FLOOR_CHANGE,
    FLOOR_EXPECTATION,
    GOAL_OBSERVE,
    GOAL_REACH,
    GOAL_TERMINAL,
    GOAL_TYPING,
    GoalTypingRow,
    HOME_EFFECT_OWNERS,
    HOME_EFFECT_SOURCES,
    KNOWLEDGE,
    LOOT_OWNERS,
    MONSTER_CHASE_OWNERS,
    OBSERVE_WITHIN,
    STORE_ENTRY,
    STORE_OPERATION,
    STORE_OPERATION_OWNERS,
    SURVIVAL_REASON_PREFIXES,
    SURVIVAL_RETURN_PREFIX,
    SURVIVAL_RETURN_TRIGGERS,
    SURVIVAL_RETURN_TRIGGER_PREFIX,
    TELEPORT_WALK_NOTE,
    TRANSACTION,
    WALK_TARGET,
    goal_typing,
    is_survival,
    is_survival_return_trigger,
    owners_with,
)
