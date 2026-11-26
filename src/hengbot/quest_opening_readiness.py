"""Bound the Q34 owner's response to a freshly evaluated entry rejection.

The Q34-first opening (``_opening_q34_active``) owns the town of a fresh character until it
takes Q34.  Its own errands are the throwing torches and a weapon; what else the acceptance
asks (the force's DPS and HP floors, the three-turn threat, the Speed and healing potions)
the opening cannot provide.  A character that misses one of those once the opening's shop
and fundraising routes are spent is released from the opening (``RELEASED``): the ordinary town (fundraising, the first dungeon levels) goes on and
Q34 is taken later through the ordinary fixed-quest order once its requirements are met.
Supervisor 2026-11-26 (owner delegation 「自由なキャラクタと戦略で勝利を目指すこと」), n1-a life-541:
a Lv1 Amberite Rogue (DPS 5.6-5.8 against the floor 8) stood in town with 1 gold until
``livelock:exhausted`` three times; an unmet opening requirement is no longer a stop.
"""
from hengbot import approach_answer, fundraising_route
from hengbot.policy_constants import REST_MACRO, WAIT_KEY

# The policy attribute: why the opening released this character (None: not released).  A
# restart rebuilds it from the board: the next opening decision evaluates the same readiness.
RELEASED = "_q34_opening_released"
RELEASED_REASON = "opening-q34:released"
# Readiness rejections no purchase of the opening answers: the character itself (its damage,
# its hit points against the fixed monsters) has to grow.
_UNBUYABLE_REJECTIONS = frozenset({"three-turn-threat", "toughest-kill-time"})
_UNBUYABLE_FORCE_ROWS = frozenset({"dps", "hp"})


def released(policy) -> bool:
    """Whether the opening released this character to the ordinary town."""
    return getattr(policy, RELEASED, None) is not None


def unbuyable_cause(readiness: dict) -> str | None:
    """The rejection's part the character itself has to grow into (the release's name), or None."""
    reason = readiness.get("reason")
    if reason in _UNBUYABLE_REJECTIONS:
        return str(reason)
    if reason == "strategy-force":
        force = readiness.get("strategy_force")
        failed = force.get("failed", ()) if isinstance(force, dict) else ()
        rows = sorted(_UNBUYABLE_FORCE_ROWS.intersection(failed))
        if rows:
            return "strategy-force:" + "+".join(rows)
    return None


def release(policy, cause: str) -> None:
    """End the opening's ownership of the town for this life (module docstring)."""
    setattr(policy, RELEASED, cause)
    policy.last_reason = RELEASED_REASON


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
    if policy._start_fundraising(snapshot, fundraising_route.DEPARTURE_SHORTAGE):
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
    if verdict:
        # The CLI recognizes this reason as a terminal, even though its key is 5.
        policy.last_reason = verdict
        return WAIT_KEY
    # Neither the opening's shops (a weapon a rich character buys may still lift its DPS) nor
    # its fundraising route meets the requirement now: the ordinary town takes over (module
    # docstring) and the rungs below answer this board.
    release(policy, unbuyable_cause(readiness) or "unaffordable:" + str(readiness.get("reason")))
    return None
