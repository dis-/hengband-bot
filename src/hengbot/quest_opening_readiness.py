"""Bound the Q34 owner's response to a freshly evaluated entry rejection."""
from hengbot import approach_answer
from hengbot.policy_constants import REST_MACRO, WAIT_KEY


def q34_readiness_rejection_key(policy, snapshot, hostiles, readiness):
    # No verdict this decision: an earlier owner still controls readiness.
    if readiness.get("verdict") is not False:
        if policy._physical_adjacent_hostiles(snapshot):
            # _fixed_quest_key declines while a monster stands beside the
            # player; waiting here kept the town kill-mob rung below from
            # ever answering it (D33 2026-10-30 n1-a life-426: a Lv1 stood
            # for 377 decisions while Merry and a beggar touched it).
            return None
        policy.last_reason = "opening-q34:wait"
        return WAIT_KEY
    if (readiness.get("reason") in {"not-full-hp", "temporary-status"}
            and not hostiles and snapshot.player.food_state in {"normal", "full", "gorged"}):
        policy.last_reason = "town:recover"
        return REST_MACRO
    # Reuse the bounded supplier/fundraising routes for every rejection,
    # including light/pack/equipment checks with no strategy-force deficit.
    before = approach_answer.answer_stamp(policy)
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
    # Owner 2026-11-18 Q2: the latest approach yielded to the town's holder: wait for it
    # (None this board, the rungs below and the holder go on), then stop named after it.
    verdict = approach_answer.after_empty(policy, "livelock:exhausted",
                                          approach_answer.since(policy, before))
    if verdict == approach_answer.WAIT:
        return None
    # The CLI recognizes this reason as a terminal, even though its key is 5.
    policy.last_reason = verdict or "livelock:exhausted"
    return WAIT_KEY
