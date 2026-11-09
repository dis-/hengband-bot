"""Where a hostile was last shown, remembered once it is out of sight.

Several owners judge a hostile out of sight at its last shown cell for a while (the routes'
veto of a strong sleeper or an awake threat, sleeper_reach_memory; the avoided disenchanter's
area, disenchant_avoid; the loot block of a sleeping group, sleeper_loot_block).  Each grew its
own copy of the same store (maintainability review 2026-11-09, problem 1: the third recurrence
of one shape is fixed at its root).  This module is that store, once:

    policy.<Kind.attribute> = (floor_key, {(index, race): (MonsterState, last shown turn)})

The attribute names are the owners' old ones, so a policy pickled before this module (the
town-arrival checkpoints, the recorded tests' fixtures) still loads into the same memory.

A monster is the game's own (index, race): the floor's monster list index the board reports
(MonsterState.index) with its race.  The window is the retreat veto's (UNSEEN_GAME_TURNS, the
hunt's redetect window, owner 2026-11-02 「1,000ゲームターン」): a hostile not shown for as long is
no longer where it was shown.  No new number.

What differs between the owners is a parameter here, not a copy: which hostiles are remembered
and which are gone (the callers' predicates), whether the window also ends an entry whose index
is shown on the board (``Kind.window_while_shown``), and how an older pickled shape reads
(``Kind.legacy``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from hengbot.me_powers import HUNT_REDETECT_GAME_TURNS

UNSEEN_GAME_TURNS = HUNT_REDETECT_GAME_TURNS


@dataclass(frozen=True)
class Kind:
    """One owner's memory.

    ``attribute``: the policy attribute holding it (the owner's old name, kept for pickles).
    ``window_while_shown``: the window ends an entry even while its index is on the board
    (else only an entry not shown expires; a shown one is judged by the owner's ``gone``).
    ``legacy``: reads an older pickled value into (floor_key, entries), or None."""
    attribute: str
    window_while_shown: bool = True
    legacy: Callable | None = None


def _one_turn_group(memory):
    """sleeper_loot_block's shape before this module: (floor_key, {key: MonsterState}, turn)."""
    if len(memory) == 3:
        floor, blockers, turn = memory
        return floor, {key: (monster, turn) for key, monster in blockers.items()}
    return memory


# The owners' memories.  Their predicates stay in the owners' modules.
SLEEPER_REACH = Kind("_sleeper_reach_memory")
# A group remembered together: every entry has the board that stored the group.
LOOT_BLOCK = Kind("_sleeper_loot_block", legacy=_one_turn_group)


def _stored(policy, kind: Kind):
    memory = getattr(policy, kind.attribute, None)  # restored checkpoints may predate it
    if memory is not None and kind.legacy is not None:
        memory = kind.legacy(memory)
    return memory


def entries(policy, snapshot, kind: Kind) -> dict:
    """{(index, race): (MonsterState, last shown turn)} remembered on this floor."""
    memory = _stored(policy, kind)
    return memory[1] if memory is not None and memory[0] == snapshot.floor_key else {}


def forget_floor(policy, kind: Kind) -> None:
    setattr(policy, kind.attribute, None)


def put(policy, snapshot, kind: Kind, seen: dict) -> None:
    """Set this floor's entries to ``seen`` ({(index, race): (MonsterState, turn)})."""
    setattr(policy, kind.attribute, (snapshot.floor_key, seen))


def store(policy, snapshot, kind: Kind, monsters) -> None:
    """Remember exactly ``monsters`` at their cells on this board (what was remembered before
    is replaced)."""
    put(policy, snapshot, kind, {
        (monster.index, monster.race_id): (monster, snapshot.turn) for monster in monsters})


def expired(snapshot, turn: int) -> bool:
    """The window passed since the board of ``turn``."""
    return snapshot.turn - turn > UNSEEN_GAME_TURNS


def observe(policy, snapshot, kind: Kind, remember: Callable, gone: Callable) -> None:
    """Every board: forget the remembered hostiles that are gone, remember the new ones.

    In town or on the surface the memory is forgotten.  An entry ends after the window (also
    while shown when ``kind.window_while_shown``) or when ``gone(policy, snapshot, monster)``;
    then each of ``remember(policy, snapshot)`` is (re)remembered at its cell on this board."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        forget_floor(policy, kind)
        return
    shown = {monster.index for monster in snapshot.visible_monsters}
    seen = {key: (monster, turn) for key, (monster, turn) in entries(policy, snapshot, kind).items()
            if not (expired(snapshot, turn)
                    and (kind.window_while_shown or key[0] not in shown))
            and not gone(policy, snapshot, monster)}
    for monster in remember(policy, snapshot):
        seen[(monster.index, monster.race_id)] = (monster, snapshot.turn)
    setattr(policy, kind.attribute, (snapshot.floor_key, seen))


def remembered(policy, snapshot, kind: Kind, keep: Callable | None = None) -> list:
    """The remembered hostiles out of sight (their index not on the board), at their last
    shown cell with the distance from the player's cell; ``keep`` filters them."""
    shown = {monster.index for monster in snapshot.visible_monsters}
    here = snapshot.player.position
    return [replace(monster, distance=here.distance_to(monster.position))
            for (index, _race), (monster, _turn) in entries(policy, snapshot, kind).items()
            if index not in shown and (keep is None or keep(policy, snapshot, monster))]
