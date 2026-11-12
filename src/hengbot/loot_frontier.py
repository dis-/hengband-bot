"""Loot the player saw with no known way to it draws the walk to the frontier nearest it.

Owner 2026-11-13 (answer to 「感知だけで見えて既知のマスから行けない品」, verbatim): 「その品の方へ探索
を寄せる。また、経路が見つからない時に周辺感知を使う処理を検討する。」.  n1-c life-205 (Angband 30F,
2026-11-12 21:10:31-21:11:55): two items at (16,147) and (19,136), remembered from the floor's
detection, had no route over the known floor; the explore went elsewhere for a minute and a half
and the floor was left with them.

When the loot walk (``_normal_loot_key``) has candidates, no blocker and no route, the walk goes
to the reachable remembered frontier nearest a candidate (ties by cell, so the target does not
change with the player's step), over the cells every walker keeps off (``_walk_veto``).  A target
not reached within its budget (twice its path length plus FRONTIER_SLACK boards) is spent for the
floor.  The board is noted (``unreachable_turn``) for the Magic-Eater's absorbed area mapping
(me_powers trigger ``loot-unreachable``), the 周辺感知 the owner named.
"""

from __future__ import annotations

from collections import deque

from hengbot.model import game_distance

REASON = "seek-loot:frontier"
FRONTIER_SLACK = 10
STATE = "_loot_frontier_state"  # (floor_key, target, boards, budget, spent frozenset)
UNREACHABLE = "_loot_unreachable_turn"  # (floor_key, game turn)


def _state(policy, snapshot):
    state = getattr(policy, STATE, None)
    if state is None or state[0] != snapshot.floor_key:
        state = (snapshot.floor_key, None, 0, 0, frozenset())
    return state


def unreachable_recently(policy, snapshot, game_turns: int) -> bool:
    """Whether the loot walk found candidates without a route within ``game_turns``."""
    noted = getattr(policy, UNREACHABLE, None)
    return (noted is not None and noted[0] == snapshot.floor_key
            and 0 <= snapshot.turn - noted[1] <= game_turns)


def key(policy, snapshot, candidates) -> str | None:
    if not candidates:
        return None
    setattr(policy, UNREACHABLE, (snapshot.floor_key, snapshot.turn))
    floor, target, boards, budget, spent = _state(policy, snapshot)
    start = snapshot.player.position
    veto = policy._walk_veto(snapshot)
    seen = {start: (None, 0)}
    queue = deque([start])
    frontiers = {}
    while queue:
        position = queue.popleft()
        first, distance = seen[position]
        if position != start and position not in spent and policy._is_remembered_frontier(
                snapshot, position):
            frontiers[position] = (first, distance)
        for neighbor in policy._walkable_neighbors(snapshot, position):
            if neighbor in seen or neighbor in veto:
                continue
            seen[neighbor] = (neighbor if first is None else first, distance + 1)
            queue.append(neighbor)
    if target is not None and target in frontiers:
        boards += 1
        if boards > budget:
            spent = spent | {target}
            frontiers.pop(target, None)
            target = None
    else:
        target = None
    if target is None:
        if not frontiers:
            setattr(policy, STATE, (floor, None, 0, 0, spent))
            return None
        target = min(frontiers, key=lambda cell: (
            min(game_distance(cell, loot) for loot in candidates), cell.y, cell.x))
        boards, budget = 0, frontiers[target][1] * 2 + FRONTIER_SLACK
    setattr(policy, STATE, (floor, target, boards, budget, spent))
    policy.last_reason = REASON
    policy._declare_reach(target)
    return policy._step_toward(snapshot, frontiers[target][0])
