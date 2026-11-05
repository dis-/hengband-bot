"""A weapon warning no monster could have raised: a trap to deal with, not a cell to refuse.

Owner 2026-11-05 「罠があるので対応する」.  warning.cpp process_warning asks the same question
(「本当にこのまま進むか？」) for two causes:

 * monsters: awake and hostile, within 12 cells of the step, a powerful spell with a line to
   the step or a blow when beside it, together over half the current HP (:336-516);
 * a trap on the step: hidden (``grid.mimic``) under easy_disarm, 12 times in 13 (:522-538).

The export shows a hidden trap as its floor (bot-json-output.cpp, TerrainKind::MIMIC), so the
board cannot name the trap until it is found.  What the player knows is the monsters in sight
or detected: when none of them counts, the warning is the trap's.  A monster the player cannot
know of counts in the game too, and nothing on the board tells it from a trap.

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

from hengbot.model import Position
from hengbot.policy_constants import SEARCH_KEY, SEARCH_LIMIT
from hengbot.quest_exposure import game_distance

SEARCH_REASON = "warning:trap-search"
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
    else:
        policy._trap_warning_cells.setdefault(cell, 0)


def forget_crossed(policy, snapshot) -> None:
    """Standing on it, it is dealt with: disarmed, sprung, or known from now on."""
    policy._trap_warning_cells.pop(snapshot.player.position, None)


def _answered(policy, snapshot, step: Position) -> bool:
    return step in policy._trap_warning_cells and not _monster_could_warn(policy, snapshot, step)


def search_key(policy, snapshot, step: Position) -> str | None:
    """Beside a warned cell whose trap is still hidden, with a search left to spend on it."""
    if not _answered(policy, snapshot, step):
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
