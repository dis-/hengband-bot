"""Former home of the ladder; it lives in town_terminal now.

Structure stage 2 B slice 4 moved the ladder next to the town hold that reads it.
This module only re-exports it under the old names for the record-only
readers that step 3 of the slice deletes.
"""

from hengbot.town_terminal import (  # noqa: F401
    BAR_GATED_RUNGS,
    CLAIM_LADDER,
    FALLBACK_RANK,
    GOAL_OBSERVE,
    GOAL_REACH,
    PREEMPTION,
    Rung,
    SCOPE_IN,
    SCOPE_S3,
    SECTION_DECIDE,
    SECTION_FALLBACK,
    SECTION_REWRITE,
    SECTION_TOWN,
    SURVIVAL_DISPLACED,
    TOWN_ERRAND_FAMILIES,
    TOWN_OWNER_FAMILIES as S3_FAMILIES,
    TOWN_RANK,
    TRIGGER_FAMILIES,
    VIOLATION,
    is_s3_rung,
    nests_over,
    never_suspended,
    ordinary_rung,
    owner_change,
    pair_scope,
    resumable_index,
    rung_named,
    rung_of,
    rung_of_claim,
)
