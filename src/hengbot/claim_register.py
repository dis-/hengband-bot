"""Former home of the claim types; they live in town_terminal and town_arbiter now.

Structure stage 2 B slice 4 moved the claim records into the town hold
(``town_terminal``) and the owner enum into ``town_arbiter``.  This module
only re-exports them under their old names for the record-only readers that
step 3 of the slice deletes, and for checkpoints pickled with these paths.
"""

from hengbot.town_arbiter import (  # noqa: F401
    CLAIM_OWNER_ATTRIBUTE,
    ClaimOwner,
    claims,
    owner_of,
)
from hengbot.town_terminal import (  # noqa: F401
    BAR_ERRAND,
    BAR_THREAT,
    CLOSED_BY_COMPLETE,
    CLOSED_BY_EXPIRED,
    CLOSED_BY_RELEASE,
    CLOSED_BY_RETIRED,
    CLOSING_EVENTS,
    GOAL_OBSERVE,
    GOAL_REACH,
    GOAL_TERMINAL,
    SUSPENDED_EXPIRED,
    Bar,
    Claim,
    ClaimRegister,
    ClaimState,
    ExecutionDeclaration,
    Goal,
    bar_after_board,
    observe_goal as observe,
    reach_goal as reach,
    reach_monster_goal as reach_monster,
    reach_place_goal as reach_place,
    terminal_goal as terminal,
)
