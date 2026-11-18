"""Angband is explored no deeper than 95F until the 99F/100F tactics exist.

Owner 2026-11-19 (verbatim): 「99F 100Fの戦い方をまだ作っていない。n1-bは次回潜行時に95Fまで登り階段で
戻ること。以降、準備ができるまで鉄獄95Fで探索すること。」  n1-b life-411 (Angband recall depth 99, the
guardian bounce valve's Angband) recalled to 99F and straight back to town, dive after dive.  The rule
is every character's: the tactics are missing for all of them.

- The cap: ``ANGBAND_DEPTH_CAP`` (95).  ``None`` lifts it (the owner's 「準備ができるまで」).
- No stair down past the cap (``capped``): read by ``dive_floor.capped`` (the descent targets, the
  remembered downstairs, explored_floor's dead end) and by the descent-target and the underfoot
  escape stairs' refusals in policy, the no-depth-progress judgement (a dive at the cap is at its
  ceiling).  At the cap the floor is explored as any floor whose descent is refused: explored, it is
  a dead end (explored_floor) and the dive returns by Word of Recall.
- Below the cap (a recall landing deeper, n1-b's 99) the up stairs are the stairs taken
  (``climbing``): the climb of dive_floor (owner 2026-11-17 「49Fに帰還して上り階段を探して適正階層まで
  行く」, ladder_descent's climb rung) under this rule's reasons ``angband-cap-95:*`` (ladder_descent.climb_key, reasons.py).  The
  existing safety rules still come first (the rungs above the climb).
- The recall depth: Word of Recall read in Angband on a floor at or below the cap and shallower than
  the saved depth asks 「ここは最深到達階より浅い階です。この階に戻って来ますか？」
  (src/spell-kind/spells-world.cpp recall_player, ``set_max_level(floor.dun_level)`` on y).  The
  executor answers y there (``reset_recall_depth``), so the next dive lands on the cap's floor
  instead of climbing again; everywhere else it still refuses (the deepest floor is kept).
"""

from __future__ import annotations

from collections.abc import Mapping

from hengbot.model import DUNGEON_ANGBAND

# Owner 2026-11-19 「準備ができるまで鉄獄95Fで探索」.  None lifts the cap.
ANGBAND_DEPTH_CAP: int | None = 95


def cap(dungeon_id: int) -> int | None:
    """The deepest floor of ``dungeon_id`` the character may stand on, or None (no cap)."""
    return ANGBAND_DEPTH_CAP if dungeon_id == DUNGEON_ANGBAND else None


def capped_at(dungeon_id: int, destination: int) -> bool:
    """A floor ``destination`` of ``dungeon_id`` lies past the cap."""
    deepest = cap(dungeon_id)
    return deepest is not None and destination > deepest


def capped(snapshot, destination: int) -> bool:
    """A stair down from this dungeon floor to ``destination`` would pass the cap."""
    return (not snapshot.in_town and snapshot.dungeon_level > 0
            and capped_at(snapshot.floor_key[0], destination))


def climbing_floor(floor_key) -> bool:
    """``floor_key`` is a dungeon floor (no quest floor) deeper than the cap."""
    return (floor_key is not None and floor_key[1] > 0 and not floor_key[2]
            and capped_at(floor_key[0], floor_key[1]))


def climbing(snapshot) -> bool:
    """On a floor deeper than the cap: the up stairs are the way on."""
    return not snapshot.in_town and climbing_floor(snapshot.floor_key)


def reset_recall_depth(observation) -> bool:
    """The answer to recall_player's reset-recall-depth question on the board ``observation``
    (the raw state the operation was posted on): y in Angband on a floor at or below the cap
    while the saved depth is deeper than the cap; n everywhere else."""
    if not isinstance(observation, Mapping):
        return False
    floor = observation.get("floor")
    progress = observation.get("progress")
    if not isinstance(floor, Mapping):
        return False
    try:
        dungeon_id = int(floor.get("dungeon_id", 0))
        level = int(floor.get("level", 0))
    except (TypeError, ValueError):
        return False
    deepest = cap(dungeon_id)
    if deepest is None or level < deepest or int(floor.get("quest_id", 0) or 0):
        return False
    depths = progress.get("dungeon_recall_depths") if isinstance(progress, Mapping) else None
    saved = depths.get(str(dungeon_id), depths.get(dungeon_id)) if isinstance(depths, Mapping) else None
    try:
        return saved is None or int(saved) > deepest
    except (TypeError, ValueError):
        return False
