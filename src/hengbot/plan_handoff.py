"""Shared record-only classification of an interrupted town errand."""

from hengbot.claim_ladder import TOWN_ERRAND_FAMILIES


def is_plan_handoff(*, holder_family, next_family, holder_kind,
                    holder_non_discardable, same_rank, plan_changed):
    return (
        holder_family in TOWN_ERRAND_FAMILIES
        and next_family in TOWN_ERRAND_FAMILIES
        and holder_family != next_family
        and holder_kind in {"Reach", "Observe"}
        and not holder_non_discardable
        and same_rank
        and plan_changed
    )
