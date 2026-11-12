"""The idle layer of the dungeon ladder (dungeon_ladder.LADDER, layer "idle").

``HengbotPolicy._decide`` asks this layer last, below the descent (ladder_descent).  Eating,
the hunt, the stuck escape and the sealed pocket, the oscillation probe, searching and the
breakout's frontier, the exploration and its probes, the secret-wall search, the kill quest's
regeneration, the way up when stuck, the blocking never-moving monster, and the idle fallback.
The rungs are asked top-down and the first answer wins, as in ``_decide``; the last layer, it
always answers (the idle fallback's entry, None included), and ``_decide`` returns that answer.
scripts/dungeon_ladder_lint.py reads the rows here (dungeon_ladder.LAYER_MODULES), so the table
still states this order.

``here`` is ``_decide``'s cell under the player, computed once above the rest layer and passed
in unchanged, by name.
"""
from __future__ import annotations

from hengbot import damaging_ground, engagement_avoid_seal, goal_route, immobile_ranged_kill, me_powers, quest_target_search, sealed_pocket
from hengbot.item_reservation import reserved_item_command
from hengbot.policy_constants import NEIGHBOR_OFFSETS, SEARCH_KEY, SEARCH_LIMIT, STUCK_ESCAPE_LIMIT, UP_STAIRS_KEY
from hengbot.town_terminal import town_end_key


def key(policy, snapshot, *, strategic_hostiles, physical_hostiles, here):
    """The idle layer's answer: the last layer, it always answers."""
    player = snapshot.player
    # 7. Eat when hungry and it is safe to do so.
    if player.hungry and not physical_hostiles:
        food = policy._find_edible(snapshot)
        if food is not None:
            policy.last_reason = "eat"
            return reserved_item_command(policy, snapshot, "eat", food)

    # 7. Opportunistic hunt for easy XP while no downstairs is in sight.
    step = policy._town_producer_entry("_hunt_step#3", lambda: policy._hunt_step(snapshot, strategic_hostiles))
    if step is not None:
        policy.last_reason = "hunt"
        policy._declare_monster(getattr(policy, "_hunt_step_target", None))
        return policy._town_producer_entry("_step_toward:hunt", lambda: policy._step_toward(snapshot, step), family="hunt")

    # 7b. Escape a walled-off floor. If we have spent STUCK_ESCAPE_LIMIT turns
    #     running only searching / breaking out / wandering here (no combat, no
    #     stairs, no new frontier — the streak is counted in _observe), the
    #     down-stairs are unreachable and supplies are fine, so the town-return
    #     never fires. Word-of-Recall out; the next dive regenerates the floor
    #     with reachable stairs. Checked BEFORE the search/explore cluster so it
    #     actually runs (those steps return before the old step-10 fallback).
    forgetting_maze = policy._is_forgetting_maze(snapshot)
    completed_forgetting_maze = policy._is_completed_forgetting_maze(snapshot)
    if (
        (
            policy._stuck_escape_streak >= STUCK_ESCAPE_LIMIT
            or policy._breakout_dig_floor == snapshot.floor_key
        )
        and policy._stuck_escape_permitted(
            snapshot, forgetting_maze, completed_forgetting_maze)
    ):
        escape = policy._stuck_escape_key(snapshot)
        if escape is not None:
            return escape

    # Sealed by the player's own *Destruction*: no search comes first (sealed_pocket).
    destroyed_pocket = sealed_pocket.after_destruction_key(policy, snapshot)
    if destroyed_pocket is not None:
        return destroyed_pocket

    # 8. If we are circling the same few tiles (frontiers whose unknown side
    #    the pathfinder can't reach), break out by stepping directly into an
    #    adjacent unknown tile to reveal it. Only when actually oscillating,
    #    so normal directed exploration is unaffected. Wall bumps are harmless
    #    and bounded by PROBE_LIMIT.
    if policy._is_oscillating():
        step = policy._town_producer_entry(
            "oscillating-probe", lambda: policy._probe_unknown_step(snapshot),
            family="explore")
        if step is not None:
            policy._release_explore_walk("explore-oscillating:probe")
            policy.last_reason = "probe"
            return policy._town_producer_entry("_step_toward", lambda: policy._step_toward(snapshot, step), family="explore")
        # A dead-end may be a SECRET door/passage the map can't show until we
        # search for it. Search this spot a few times before treating it as
        # truly closed — it is what breaks an otherwise-unescapable circle
        # (verified live: 's' a few times reveals the hidden corridor).
        # Secret doors/passages only exist in the dungeon; searching in town
        # is wasted turns, so never 's' there — fall straight through to a
        # move instead.
        here_key = (player.position.y, player.position.x)
        if (
            not snapshot.in_town
            and not forgetting_maze
            and policy._search_counts[here_key] < SEARCH_LIMIT
            and not damaging_ground.hurts_here(policy, snapshot)
        ):
            policy._search_counts[here_key] += 1
            policy._release_explore_walk("explore-oscillating:search")
            policy.last_reason = "search"
            return SEARCH_KEY
        # Once local probes and searches are exhausted, resume the committed
        # exploration planner. It can route across remembered, off-screen
        # floor to an older reachable frontier; choosing a local least-visited
        # neighbour first traps us in a fully-known room forever.
        step = policy._town_producer_entry("_explore_step#1", lambda: policy._explore_step(snapshot))
        if step is not None:
            # A valid committed route means the oscillation was escaped. Drop
            # the stale stationary/search history now; otherwise it remains
            # "oscillating" for several more decisions and searches at every
            # waypoint until the recall escape threshold is reached.
            policy._recent.clear()
            policy._stuck_escape_streak = 0
            policy.last_reason = "breakout:seek-frontier"
            policy._declare_explore_goal()
            return policy._town_producer_entry("_step_toward:detectors", lambda: policy._step_toward(snapshot, step), family="detectors")
        # No reachable unexplored floor or frontier remains: the ladder
        # below owns the floor (secret walls, known stairs, the wander), and
        # the stuck streak reaches its escape.  A local wander here hid all
        # of that while the two-square confinement kept this branch alive
        # until the loop guard stopped the bot (n1-a life-474).  Town has no
        # wander: no owner answered, so the visit takes its declared end
        # (owner 2026-11-02).
        if snapshot.in_town:
            return town_end_key(policy, snapshot)
        # The engagement retreats' own vetoes (and the areas they guard)
        # enclose what is left of the floor: leave it now instead of
        # wandering among them until the loop detector stops the bot
        # (owner 2026-11-02 「避ける判断になるのであればループではなく迂回する
        # べき」; n1-c life-103).  Only when they do enclose it: a veto left
        # anywhere on the floor by an earlier retreat is no enclosure while
        # a walk avoiding every veto still reaches a frontier or a stair
        # (engagement_avoid_seal.encloses).  n1-c life-205 (dungeon 12 49F,
        # 2026-11-12 22:13): two vetoes 25+ cells away, 295 open frontiers
        # and two known down stairs, the explore found nothing at a searched
        # dead end and this read Recall at full HP with nothing in sight;
        # 16 of the life's ~105 returns that evening left this way.  The
        # ladder below (secret walls, known stairs, the wander and the
        # stuck streak) owns such a floor.
        if (policy._engagement_owned_avoid_cells
                and engagement_avoid_seal.encloses(policy, snapshot)
                and policy._stuck_escape_permitted(
                    snapshot, forgetting_maze, completed_forgetting_maze)):
            escape = policy._stuck_escape_key(snapshot)
            if escape is not None:
                return escape

    # Search a corridor dead-end before ordinary exploration routes us away.
    # This is opportunistic only: never detour toward a remote dead-end.
    if (
        not snapshot.in_town
        and snapshot.dungeon_level > 0
        and not forgetting_maze
        and policy._open_neighbor_count(snapshot, player.position) <= 1
        and policy._undersearched_walls(player.position)
        and not damaging_ground.hurts_here(policy, snapshot)
    ):
        policy._record_wall_search(player.position)
        policy.last_reason = "search"
        return SEARCH_KEY

    # A released immobile-breeder plan is only an exploration fallback.
    # Ordinary combat, threat, loot, descent, and hunting owners above must
    # retain their normal priority when another mobile hostile is present.
    immobile_breeder_giveup = policy._town_producer_entry("_immobile_breeder_giveup_key", lambda: policy._immobile_breeder_giveup_key(snapshot))
    if immobile_breeder_giveup is not None:
        return immobile_breeder_giveup

    # 9. Explore toward the unknown (door- and edge-aware).
    step = policy._town_producer_entry("_explore_step#2", lambda: policy._explore_step(snapshot))
    if step is not None:
        policy.last_reason = "explore"
        policy._declare_explore_goal()
        return policy._town_producer_entry("_step_toward", lambda: policy._step_toward(snapshot, step), family="explore")
    # Exploration outside an avoided immobile summoner's zone is spent:
    # leave by that owner's exits (its zone stays out of every route).
    summoner_exit = policy._town_producer_entry(
        "_immobile_summoner_exit_key",
        lambda: policy._immobile_summoner_exit_key(snapshot))
    if summoner_exit is not None:
        return summoner_exit

    # The planner deliberately excludes the current tile as a destination.
    # When this tile is the floor's sole remaining frontier, probe through
    # its unknown edge instead of concluding that exploration is complete.
    # If those probes hit an unseen wall, search here for a secret passage
    # before falling back to stairs.
    frontier_here = here is not None and policy._is_frontier(snapshot, here)
    probed_wall_here = any(
        (player.position.y + dy, player.position.x + dx)
        in policy._blocked_unknown
        for dy, dx in NEIGHBOR_OFFSETS
    )
    if frontier_here or probed_wall_here:
        step = policy._town_producer_entry(
            "frontier-probe", lambda: policy._probe_unknown_step(snapshot),
            family="explore")
        if step is not None:
            policy.last_reason = "probe"
            return policy._town_producer_entry("_step_toward", lambda: policy._step_toward(snapshot, step), family="explore")
        # No secret passages in town — do not waste turns searching there.
        here_key = (player.position.y, player.position.x)
        if (
            not snapshot.in_town
            and not forgetting_maze
            and policy._search_counts[here_key] < SEARCH_LIMIT
            and not damaging_ground.hurts_here(policy, snapshot)
        ):
            policy._search_counts[here_key] += 1
            policy.last_reason = "search"
            return SEARCH_KEY

    # Nothing is left to explore and a random quest's target is unfound: the floor is
    # circled for it, not walked cell by cell (quest_target_search).
    target_loop = quest_target_search.loop_key(policy, snapshot)
    if target_loop is not None:
        return target_loop

    if (
        snapshot.dungeon_level > 0
        and not forgetting_maze
        and not policy._known_downstairs_reachable(snapshot)
    ):
        if (power := me_powers.power_key(policy, snapshot, me_powers.SECRET_SEARCH)):
            return power
        # A search on ground that hurts would only be replaced by the step off it
        # (damaging_ground.leave_first), uncounted rounds walked back to for ever:
        # n1-a life-492 (Orc cave 23F, 11-06 23:55), HEAVY_ELECTRICAL_ZONE.
        if (policy._undersearched_walls(player.position)
                and not damaging_ground.hurts_here(policy, snapshot)):
            policy._record_wall_search(player.position)
            policy.last_reason = "search"
            return SEARCH_KEY
        policy._claim_target_capture = []
        try:
            step = policy._secret_wall_search_step(snapshot)
        finally:
            step_target = policy._take_claim_target()
        if step is not None:
            policy.last_reason = "seek-secret-wall"
            policy._declare_reach(step_target)
            return policy._town_producer_entry("_step_toward", lambda: policy._step_toward(snapshot, step), family="explore")

    # 9. Nothing to explore: take any known stairs to reach a fresh floor.
    quest_regen = policy._town_producer_entry("_start_kill_quest_regeneration", lambda: policy._start_kill_quest_regeneration(snapshot))
    if quest_regen is not None:
        return quest_regen
    floor_exit_locked = policy._floor_navigation_exit_locked(snapshot)
    allow_descent = not policy._descent_is_blocked(snapshot)
    stair_goal = (
        lambda g: not floor_exit_locked
        and (
            policy._is_upstairs_target(g)
            or (allow_descent and policy._is_descent_target(snapshot, g))
        )
    )
    if forgetting_maze and not floor_exit_locked:
        # The maze forgets every cell out of view, so a remembered stair is no
        # grid on the board: it is a goal by its cell (n1-c life-156, Labyrinth 10F).
        goal_route.with_remembered_goals(
            stair_goal, policy._remembered_stair_goals(snapshot, allow_descent))
    policy._claim_target_capture = []
    try:
        step = policy._nearest_goal_step(snapshot, stair_goal)
    finally:
        step_target = policy._take_claim_target()
    # The stair underfoot comes first: the route never ends on this cell, so
    # with a second stair known it walked on between the two until the stuck
    # bound read a Recall (n1-c life-139, Angband 5F [14,51] and [24,80]).
    if not floor_exit_locked and here is not None and policy._is_upstairs_target(here):
        policy._defer_descent(snapshot)
        policy.last_reason = "stuck:ascend"
        return UP_STAIRS_KEY
    if step is not None:
        policy.last_reason = "stuck:seek-stairs"
        policy._declare_reach(step_target)
        return policy._town_producer_entry("_step_toward:detectors", lambda: policy._step_toward(snapshot, step), family="detectors")
    # Owner 2026-11-06 「先にその敵を倒す」: a never-moving monster's ring is what
    # blocks the way in a maze -- shoot it, else the enclosure ladder.
    blocking = immobile_ranged_kill.blocking_key(policy, snapshot)
    if blocking is not None:
        return blocking

    return policy._town_producer_entry(
        "idle-fallback", lambda: policy._town_idle_key(snapshot), family="idle")
