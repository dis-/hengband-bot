"""A weapon warning no monster could have raised: a trap to deal with, not a cell to refuse.

Owner 2026-11-05 「罠があるので対応する」, and on ordinary floors 「避けられれば避ける」.
warning.cpp process_warning asks the same question
(「本当にこのまま進むか？」) for two causes:

 * monsters: awake and hostile, within 12 cells of the step, a powerful spell with a line to
   the step or a blow when beside it, together over half the current HP (:336-516);
 * a trap on the step: hidden (``grid.mimic``) under easy_disarm, 12 times in 13 (:522-538).

The export shows a hidden trap as its floor (bot-json-output.cpp, TerrainKind::MIMIC), so the
board cannot name the trap until it is found.  What the player knows is the monsters in sight
or detected: when none of them counts, the warning is the trap's.  A monster the player cannot
know of counts in the game too, and nothing on the board tells it from a trap.

A floor walked by a room-sweep plan keeps its way over the cell and answers at once.  Every
other floor latches the cell as before, so every walker goes round it, and answers only from
``last_way_key``, the idle rung every walker has fallen through to on this very decision: a way
that opens (a search can find a door) takes the next decision back from the answer.

The answer, in ``_step_toward``'s order: the prompt was refused (input_executor answers it);
search from beside it (cmd-others.cpp do_cmd_search, player-move.cpp search), at most
SEARCH_LIMIT times and only with no awake enemy known; a found trap goes the existing way (an
absorbed power, or CHEST_DISARM_KEY up to CHEST_DISARM_BUDGET); then the walk across with its
'y', the forced walk's form (traps are walkable, 2026-10-23).  A stray 'y', after the 1-in-13
skip or under easy_disarm's walk-to-disarm on a found trap, falls into the illegal-command
default.  A monster the warning can be blamed on keeps the latch (``_latch_warning_refusal``),
then and on every later step.
"""

from __future__ import annotations

from collections import deque

from hengbot import quest_room_sweep
from hengbot.model import Position
from hengbot.policy_constants import NEIGHBOR_OFFSETS
from hengbot.policy_constants import SEARCH_KEY, SEARCH_LIMIT
from hengbot.quest_exposure import game_distance

SEARCH_REASON = "warning:trap-search"
LAST_WAY_REASON = "warning:trap-last-way"
WARNING_RANGE = 12  # warning.cpp warning_aware_range


def _awake_hostiles(snapshot) -> list:
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
            if monster.hostile and not monster.asleep]


def _monster_could_warn(policy, snapshot, cell: Position) -> bool:
    """A known monster the game's forecast for a step onto ``cell`` would count."""
    for monster in _awake_hostiles(snapshot):
        spot = monster.position
        if game_distance((spot.y, spot.x), (cell.y, cell.x)) > WARNING_RANGE:
            continue
        if spot.distance_to(cell) <= 1 or policy._line_of_sight_over_known_grids(snapshot, spot, cell):
            return True
    return False


def note_warned(policy, snapshot, cell: Position) -> None:
    """The warning for a step onto ``cell``: a monster's latches, a trap's is answered."""
    if _monster_could_warn(policy, snapshot, cell):
        policy._trap_warning_cells.pop(cell, None)
        policy._latch_warning_refusal(cell)
        return
    policy._trap_warning_cells.setdefault(cell, 0)
    if not quest_room_sweep.walks_over_traps(policy, snapshot):
        policy._latch_warning_refusal(cell)


def forget_crossed(policy, snapshot) -> None:
    """Standing on it, it is dealt with: disarmed, sprung, or known from now on."""
    here = snapshot.player.position
    if policy._trap_warning_cells.pop(here, None) is not None:
        policy._release_warning_refusal(here)


def _answered(policy, snapshot, step: Position) -> bool:
    """A trap's cell that no monster now in the game's reach of it can be blamed for."""
    return step in policy._trap_warning_cells and not _monster_could_warn(policy, snapshot, step)


def search_key(policy, snapshot, step: Position, *, last_way: bool = False) -> str | None:
    """Beside a warned cell whose trap is still hidden, with a search left to spend on it.  Off
    a plan, only ``last_way_key`` asks: the walk with no supplies left keeps its forced walk."""
    if not _answered(policy, snapshot, step) or not (
            last_way or quest_room_sweep.walks_over_traps(policy, snapshot)):
        return None
    grid = snapshot.grids.get(step)
    searches = policy._trap_warning_cells[step]
    if (searches >= SEARCH_LIMIT or (grid is not None and grid.trap) or snapshot.player.blind
            or _awake_hostiles(snapshot)):
        return None
    policy._trap_warning_cells[step] = searches + 1
    policy.last_reason = SEARCH_REASON
    return SEARCH_KEY


def walk_across(policy, snapshot, step: Position) -> bool:
    """Nothing left to try on a warned cell: the walk answers its own prompt."""
    return _answered(policy, snapshot, step)


def _beside(cell: Position) -> list[Position]:
    return [Position(cell.y + dy, cell.x + dx) for dy, dx in NEIGHBOR_OFFSETS]


def _toward_warned(policy, snapshot, cells: set[Position]) -> tuple[Position, bool] | None:
    """The first step of the shortest walk to a warned cell, over no refused one; True when
    it is the warned cell itself.  A found trap is out of the routing index, hence ``_beside``."""
    start = snapshot.player.position
    seen, queue = {start}, deque([(start, None)])
    while queue:
        cell, first = queue.popleft()
        warned = next((spot for spot in _beside(cell) if spot in cells), None)
        if warned is not None:
            return (warned, True) if first is None else (first, False)
        for neighbor in policy._walkable_neighbors(snapshot, cell):
            if neighbor not in seen and not policy._warning_step_refused(snapshot, neighbor):
                seen.add(neighbor)
                queue.append((neighbor, neighbor if first is None else first))
    return None


def last_way_key(policy, snapshot) -> str | None:
    """Every walker has run out of routes on this decision: the trap in the way is answered."""
    cells = {cell for cell in policy._trap_warning_cells if _answered(policy, snapshot, cell)}
    found = _toward_warned(policy, snapshot, cells) if cells else None
    if found is None:
        return None
    step, is_warned = found
    policy.last_reason = LAST_WAY_REASON
    policy._declare_reach(step)
    return policy._step_toward(snapshot, step, trap_last_way=is_warned)
