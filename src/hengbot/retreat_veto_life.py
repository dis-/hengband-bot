"""Which monster a retreat's veto was set for, and the veto's end once that monster is gone.

A retreat's veto (policy ``_claim_engagement_avoid_cells``) stayed for the floor visit.
n1-b life-317 (Angband 50F, RANDOM quest 40, 2026-11-05): five retreats from a half-giant left
a column of vetoes across a hall; the half-giant later changed shape, and the column walled the
hunt off from its target for 81,000 game turns (retreat_enclosure).

Owner 2026-11-06 「脅威が見えなくなったら消す」: a veto set for a monster is lifted when that
monster died, changed shape, or has not been seen for a while.  A retreat names the monsters it
fled (``claim``); a cell keeps its veto while any of them is still there.  A veto claimed with no
monster (the breeder give-up plan's cells, and any claim of a restored checkpoint that predates
this memory) stays for the floor visit as before, and so does a cell that also has such a claim.

A monster is the game's own (index, race): the floor's monster list index the board reports
(MonsterState.index) with its race.  ``observe`` reads each board:

- seen: the index on the board (in view, or shown by a detection) with the same race; the
  detection's cell is what the game displayed (fair play).
- changed shape or died: the index on the board with another race.  A chameleon keeps its
  index and takes a new race (monster/monster-list.cpp choose_chameleon_polymorph); a dead
  monster's index can be reused by a new one.
- died, or changed shape, in view: the monster was on the previous observed board, is gone
  from this one, and this board prints its kill line (breeder_stalemate ``shows_kill``: 「…は死んだ。」,
  「…を葬り去った。」, 「…を倒した。」) or a shape-change line by its name: 「…が変身した！」
  (effect/effect-monster.cpp effect_damage_makes_polymorph; polymorph_monster deletes the monster
  and places the new race, spell-kind/spells-polymorph.cpp), 「突然…が変身した。」
  (monster/monster-processor.cpp, a chameleon) and 「…は変化した！」
  (melee/melee-switcher.cpp, player-attack/attack-chaos-effect.cpp).
- not seen for a while: no board showed it for UNSEEN_GAME_TURNS game turns.  The window is the
  hunt's (me_powers.HUNT_REDETECT_GAME_TURNS, owner 2026-11-02 「1,000ゲームターン」): after it
  the hunted target's last shown cell is stale and the search is cast again, so a monster not
  shown for as long is no longer where its retreat left it.  No new number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Who a monster is and when it ended are read in monster_memory, shared with the never-moving
# monster memory, the threat tiers and the one-shot breath; the names stay importable here.
from hengbot.monster_memory import (  # noqa: F401 -- re-exported
    SHAPE_CHANGE_LINES, UNSEEN_GAME_TURNS, gone, seen_or_ended, shown_by_index)

MEMORY = "_retreat_veto_life"
ANONYMOUS = None  # the owner of a veto claimed with no monster: never lifted here


@dataclass
class Threat:
    """A monster's name and the last board that showed it (monster_memory.seen_or_ended).
    It stays in this module: pickled policies name it here."""
    name: str
    last_seen: int


@dataclass
class Life:
    owners: dict = field(default_factory=dict)    # Position -> {(index, race) | ANONYMOUS}
    threats: dict = field(default_factory=dict)   # (index, race) -> Threat
    last_turn: int | None = None                  # the previous observed board


def _life(policy) -> Life:
    life = getattr(policy, MEMORY, None)  # restored checkpoints predate it
    if life is None:
        life = Life()
        setattr(policy, MEMORY, life)
    return life


def claim(policy, snapshot, cells, threats=()) -> None:
    """Record who a veto claim of ``cells`` was set for (none: ANONYMOUS)."""
    life = _life(policy)
    keys = {(monster.index, monster.race_id) for monster in threats} or {ANONYMOUS}
    for monster in threats:
        life.threats[(monster.index, monster.race_id)] = Threat(monster.name, snapshot.turn)
        life.last_turn = snapshot.turn  # the claim's board is an observed one
    for cell in cells:
        life.owners.setdefault(cell, set()).update(keys)


def observe(policy, snapshot) -> None:
    """Lift the vetoes whose every monster is gone (once per board, before the routes)."""
    life = getattr(policy, MEMORY, None)
    if life is None or not life.threats:
        return
    shown = shown_by_index(snapshot)
    ended = {key for key, threat in life.threats.items()
             if gone(snapshot, key, threat, shown, life.last_turn)}
    life.last_turn = snapshot.turn
    _lift(policy, snapshot, life, ended)


def release(policy, snapshot, keys) -> None:
    """Lift the vetoes set for the monsters ``keys`` (index, race), as if they were gone: the
    threat tiers' decided side for them turned from leave to fight (threat_tiers.decided)."""
    life = getattr(policy, MEMORY, None)
    if life is not None:
        _lift(policy, snapshot, life, set(keys) & set(life.threats))


def _lift(policy, snapshot, life: Life, ended: set) -> None:
    if not ended:
        return
    for key in ended:
        del life.threats[key]
    lifted = set()
    for cell, keys in list(life.owners.items()):
        keys -= ended
        if not keys:
            del life.owners[cell]
            lifted.add(cell)
    lifted &= policy._engagement_owned_avoid_cells
    if lifted:
        policy._engagement_owned_avoid_cells -= lifted
        policy._refresh_warning_avoidance(snapshot, released_cells=lifted)


def forget_floor_visit(policy) -> None:
    setattr(policy, MEMORY, None)
