"""Loot the player saw with no known way to it steers the explore to the frontier nearest it.

Owner 2026-11-13 (answer to 「感知だけで見えて既知のマスから行けない品」, verbatim): 「その品の方へ探索
を寄せる。また、経路が見つからない時に周辺感知を使う処理を検討する。」.  n1-c life-205 (Angband 30F,
2026-11-12 21:10:31-21:11:55): two items at (16,147) and (19,136), remembered from the floor's
detection, had no route over the known floor; the explore went elsewhere for a minute and a half
and the floor was left with them.

The loot walk (``_normal_loot_key``) notes the board when it has candidates, no blocker and no
route (``note``).  The explore itself (``_explore_step``), when it plans a new goal, then plans
it to the reachable remembered frontier nearest such a candidate (ties by cell) instead of the
nearest frontier (``explore_path``) once that loot has been without a route on
STEER_AFTER_BOARDS boards (the nearest frontier often opens the way first); everything that
outranks the explore (holds, chokes, rest, descent) still does, and a committed explore route is followed as before.  A frontier chosen
FRONTIER_TRIES times is spent for the floor.  The note also asks the Magic-Eater's absorbed area
mapping (me_powers trigger ``loot-unreachable``), the 周辺感知 the owner named.
"""

from __future__ import annotations

from collections import deque

from hengbot.model import game_distance

FRONTIER_TRIES = 3
# The ordinary nearest-frontier explore keeps the first boards: it often opens the way itself.
# Only loot the loot walk found without a route on STEER_AFTER_BOARDS boards steers it.
STEER_AFTER_BOARDS = 20
# The note stays fresh for a few boards: the explore that plans next reads it.
NOTE_GAME_TURNS = 30
NOTE = "_loot_unreachable_note"  # (floor_key, game turn, frozenset of candidates, boards)
TRIED = "_loot_frontier_tried"  # (floor_key, {frontier: times chosen})


def note(policy, snapshot, candidates) -> None:
    """The loot walk found ``candidates`` and no route on this board: count the boards it has,
    on this floor, for the same loot (a candidate in common)."""
    floor_key = getattr(snapshot, "floor_key", None)
    if not candidates or floor_key is None:
        return
    candidates = frozenset(candidates)
    noted = getattr(policy, NOTE, None)
    boards = 1
    if noted is not None and noted[0] == snapshot.floor_key and noted[2] & candidates:
        boards = noted[3] + (1 if snapshot.turn != noted[1] else 0)
    setattr(policy, NOTE, (snapshot.floor_key, snapshot.turn, candidates, boards))


def _fresh(policy, snapshot, game_turns: int):
    noted = getattr(policy, NOTE, None)
    if (noted is not None and noted[0] == snapshot.floor_key
            and 0 <= snapshot.turn - noted[1] <= game_turns):
        return noted[2]
    return None


def unreachable_recently(policy, snapshot, game_turns: int) -> bool:
    """Whether the loot walk found candidates without a route within ``game_turns``."""
    return bool(_fresh(policy, snapshot, game_turns))


def explore_path(policy, snapshot, avoided) -> list:
    """[first step, ..., frontier] toward the noted loot, or [] (the explore's own plan)."""
    candidates = _fresh(policy, snapshot, NOTE_GAME_TURNS)
    if not candidates or getattr(policy, NOTE)[3] < STEER_AFTER_BOARDS:
        return []
    tried = getattr(policy, TRIED, None)
    if tried is None or tried[0] != snapshot.floor_key:
        tried = (snapshot.floor_key, {})
    counts = tried[1]
    start = snapshot.player.position
    closed = set(avoided) | set(policy._walk_veto(snapshot))
    parent = {start: None}
    queue = deque([start])
    frontiers = []
    while queue:
        position = queue.popleft()
        if (position != start and counts.get(position, 0) < FRONTIER_TRIES
                and policy._is_remembered_frontier(snapshot, position)):
            frontiers.append(position)
        for neighbor in policy._walkable_neighbors(snapshot, position):
            if neighbor in parent or neighbor in closed:
                continue
            parent[neighbor] = position
            queue.append(neighbor)
    if not frontiers:
        return []
    goal = min(frontiers, key=lambda cell: (
        min(game_distance(cell, loot) for loot in candidates), cell.y, cell.x))
    counts[goal] = counts.get(goal, 0) + 1
    setattr(policy, TRIED, tried)
    path = []
    cell = goal
    while cell != start:
        path.append(cell)
        cell = parent[cell]
    return list(reversed(path))
