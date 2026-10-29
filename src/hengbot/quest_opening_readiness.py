"""Bound the Q34 owner's response to a freshly evaluated entry rejection."""
from hengbot.policy_constants import REST_MACRO, WAIT_KEY


def q34_readiness_rejection_key(policy, snapshot, hostiles, readiness):
    # No verdict this decision: an earlier owner still controls readiness.
    if readiness.get("verdict") is not False:
        policy.last_reason = "opening-q34:wait"
        return WAIT_KEY
    if (readiness.get("reason") in {"not-full-hp", "temporary-status"}
            and not hostiles and snapshot.player.food_state in {"normal", "full", "gorged"}):
        policy.last_reason = "town:recover"
        return REST_MACRO
    # Reuse the bounded supplier/fundraising routes for every rejection,
    # including light/pack/equipment checks with no strategy-force deficit.
    step = policy._shopping_approach_step(snapshot, router_plan_stop=True)
    if step is not None:
        policy.last_reason = "shop:approach"
        key = policy._shopping_approach_key(snapshot, step, "shop:travel")
        if key is not None:
            return key
    if policy._start_fundraising(snapshot):
        step = policy._shopping_approach_step(snapshot, router_plan_stop=True)
        if step is not None:
            policy.last_reason = "shop:approach"
            key = policy._shopping_approach_key(snapshot, step, "shop:travel")
            if key is not None:
                return key
    # The CLI recognizes this reason as a terminal, even though its key is 5.
    policy.last_reason = "livelock:exhausted"
    return WAIT_KEY
