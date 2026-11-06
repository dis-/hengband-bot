"""The route a goal walk follows: nearest-goal search and route commitment.

``SupplyMixin._nearest_goal_route`` (and ``_nearest_goal_step`` on top of it)
answers "first step toward the nearest cell the predicate accepts" for about
forty walks (stairs, stores, quest entrances, loot, shelters).  It used to be
a fresh BFS on every board, and live monster cells are not walkable
(``_refresh_terrain_index``), so a goal walk past moving monsters re-chose its
route every board: n1-b life-285 (2026-11-01, Yeek cave 1F, decisions
1119-1136) walked fundraise:seek-upstairs back and forth between two cells
13 times while giant mice stepped in and out of the corridor to the stairs,
and lost about 20 HP doing it.

The walk now keeps the route it chose while that route stays valid, as the
exploration walk keeps ``_explore_path`` (``_explore_step``): the player
stands on the committed first step (or, on the board that chose the route,
still on its origin), the target still satisfies the predicate, and every
remaining step is still walkable under the same search pass.  A committed route is never kept over a fresh route found
in a stricter pass (it never walks a hazard or a store entrance the fresh
search would avoid).  One commitment is kept per goal kind (the predicate's
function), so walks toward different goals do not overwrite each other.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from hengbot.model import Position
from hengbot.policy_types import TownMapRoute

# Search passes in the order the walk tries them: (store entrances other than
# the goal blocked, damaging/trap cells allowed).
SEARCH_PASSES = ((True, False), (True, True), (False, False), (False, True))


@dataclass(frozen=True)
class GoalRouteCommitment:
    floor_key: tuple
    turn: int
    origin: Position
    path: tuple[Position, ...]
    pass_index: int


def goal_kind(predicate) -> str:
    """A picklable name for the predicate's function (lambdas by their code)."""
    function = getattr(predicate, "__func__", predicate)
    code = getattr(function, "__code__", None)
    if code is None:
        return repr(type(predicate))
    qualname = getattr(function, "__qualname__", code.co_name)
    return f"{code.co_filename}:{code.co_firstlineno}:{qualname}"


def _commitments(policy) -> dict[str, GoalRouteCommitment]:
    # Restored checkpoints rebuild __dict__ without __init__.
    return policy.__dict__.setdefault("_goal_route_commitments", {})


def _admitted_steps(policy, snapshot, position, predicate, blocked, allow_damaging):
    for neighbor in policy._walkable_neighbors(
        snapshot, position, allow_damaging=allow_damaging, goal=predicate
    ):
        if neighbor in policy._engagement_avoid_cells or neighbor in blocked:
            continue
        yield neighbor


def _blocked(pass_index: int, entrance_cells: set[Position]) -> set[Position]:
    return entrance_cells if SEARCH_PASSES[pass_index][0] else set()


def _is_goal(snapshot, position, predicate) -> bool:
    """The board's grid satisfies ``predicate``; a cell the board does not show is a goal
    when the predicate names it among its remembered goals (``with_remembered_goals``)."""
    grid = snapshot.grids.get(position)
    if grid is None:
        return position in getattr(predicate, REMEMBERED_GOALS, ())
    return predicate(grid)


REMEMBERED_GOALS = "remembered_goals"


def with_remembered_goals(predicate, cells):
    """``predicate`` that also accepts ``cells`` while the board does not show them.

    A forgetting maze (MAZE + FORGET) drops every cell out of view from the board, so a
    stair remembered there is never a grid the predicate can read (n1-c life-156)."""
    setattr(predicate, REMEMBERED_GOALS, frozenset(cells))
    return predicate


def nearest_goal_path(policy, snapshot, predicate, entrance_cells):
    """BFS over the search passes: (path to the nearest goal, pass index)."""
    start = snapshot.player.position
    for pass_index, (_, allow_damaging) in enumerate(SEARCH_PASSES):
        blocked = _blocked(pass_index, entrance_cells)
        parent: dict[Position, Position | None] = {start: None}
        queue: deque[Position] = deque([start])
        while queue:
            position = queue.popleft()
            if position != start and _is_goal(snapshot, position, predicate):
                path = []
                node: Position | None = position
                while node is not None and node != start:
                    path.append(node)
                    node = parent[node]
                path.reverse()
                return tuple(path), pass_index
            for neighbor in _admitted_steps(
                policy, snapshot, position, predicate, blocked, allow_damaging
            ):
                if neighbor not in parent:
                    parent[neighbor] = position
                    queue.append(neighbor)
    return None


def _remaining(commitment, snapshot) -> tuple[Position, ...] | None:
    here = snapshot.player.position
    if commitment.floor_key != snapshot.floor_key:
        return None
    if here == commitment.origin and snapshot.turn == commitment.turn:
        return commitment.path  # another walk of the same kind on this board
    if here == commitment.path[0]:
        return commitment.path[1:]
    return None


def _still_valid(policy, snapshot, predicate, path, pass_index, entrance_cells):
    """The remaining route up to its first goal cell, or None if it broke."""
    blocked = _blocked(pass_index, entrance_cells)
    allow_damaging = SEARCH_PASSES[pass_index][1]
    previous = snapshot.player.position
    for index, step in enumerate(path):
        if step not in set(_admitted_steps(
            policy, snapshot, previous, predicate, blocked, allow_damaging
        )):
            return None
        if _is_goal(snapshot, step, predicate):
            return path[:index + 1]
        previous = step
    return None


def follow(policy, snapshot, predicate, fresh_path, fresh_pass, entrance_cells):
    """The route to walk: the committed one while valid, else the fresh one."""
    commitments = _commitments(policy)
    kind = goal_kind(predicate)
    commitment = commitments.get(kind)
    path, pass_index = fresh_path, fresh_pass
    if commitment is not None and commitment.pass_index <= fresh_pass:
        remaining = _remaining(commitment, snapshot)
        if remaining:
            kept = _still_valid(
                policy, snapshot, predicate, remaining,
                commitment.pass_index, entrance_cells,
            )
            if kept is not None:
                path, pass_index = kept, commitment.pass_index
    commitments[kind] = GoalRouteCommitment(
        snapshot.floor_key, snapshot.turn, snapshot.player.position, path, pass_index
    )
    return TownMapRoute(path[-1], path[0], len(path))


def forget(policy, predicate) -> None:
    _commitments(policy).pop(goal_kind(predicate), None)
