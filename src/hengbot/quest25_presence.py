"""Quest 25: a roster race the board shows is not on the floor is not waited for.

n1-c life-208 / life-211 (2026-11-15, Quest 25 『幽霊屋敷』, Magic-Eater Lv33 with telepathy): the
spectral tyrannosaurus (705) was burnt to death by the character's fire aura at turn 3965900
(「幽体ティラノサウルスは灰の山になった。」, combat/aura-counterattack.cpp), a line the kill reader did not
know, so it was never counted killed.  The ambush (phase 1, ``long_wait_actions`` 5000: owner
2026-11-06 「事実上上限無し」) had already held 4,995 decisions on [10,1] for it (04:32-04:42).  The
resumed life-211 reloaded the save of turn 4034788, older than the battle record (4035146), so the
record kept only its kills (quest25_battle_record._before_the_save) and the phases began again at
the ambush, which waited for the dead tyrannosaurus again: 1,167 quiet holds on [10,1] when the
owner stopped it (06:53).  A full detection at turn 4027956 had shown only the two Nexus
quylthulgs left on the floor.

Owner rules: 「可能なら感知して存在を確認する」 (2026-11-13, phase 5), 「感知が使えるなら使って処理する」
(phase 6), 「また、長時間何を待っているのかも確認」 (2026-11-15).  So a phase never waits for a roster
race the board shows is gone, in every phase:

 * ``note_absent`` (every board the plan reads): a roster race no hostile of which is shown, and
   every cell of the map it could stand on is within what this board's telepathy shows of it, or
   within the detection the plan cast just before this board (its first board after the cast,
   the player still on the cell it was cast from; one that showed nothing counts) --
   that race is absent: none of it is left on the floor.  ``Battle.absent`` keeps it (race ->
   game turn), and ``quest25_battle._Ctx.kills`` counts such a race as its whole roster, so every
   phase that waits for it, counts it, or shoots it is over for it.
 * ``presence_key`` (a waiting phase: ``Phase.waits_for``): the phase is ready, no hostile is in
   view, none of the races it waits for is shown, and the wait has run ``quiet_actions`` more
   quiet actions (the owner's 50-action measure of 「来ない」, wait_limits) since the last check:
   the plan's detection (``quest25_battle._detect_key``: the absorbed Rod of Detection, else the
   Staff of Detect Evil, else a carried one), cast where it reaches every cell those races could
   be on, else after a walk to the nearest such cell.  The ambush keeps its own wait otherwise:
   a race the detection shows is waited for as before.  A battle restored from an older save
   (quest25_battle_record ``_before_the_save``: the phases run again from the first, the kills
   read before the save kept) checks at once (``Battle.recheck``): what the board holds is what
   the save holds, and the phase it starts in is the one the board says is left.  Only a wait
   with more than ``quiet_actions`` still to run is checked (the ambush's and the dreadmaster's
   ``long_wait_actions``): the wall-passers' 100 and the stragglers' 50 end on their own within
   the window, as the owner set them (2026-11-06, 2026-11-09).

The game (C++ source, the reach of each):

 * Telepathy (monster/monster-update.cpp decide_sight_invisible_monster): a monster within
   MAX_PLAYER_SIGHT (20, Grid::calc_distance) is sensed -- halved, and the telepathy only within
   MAX_PLAYER_SIGHT / 4, in a DARKNESS dungeon -- unless its race is EMPTY_MIND (never) or
   WEIRD_MIND (one game turn in ten: not on every board).  Blindness does not stop it; a
   hallucination hides the race (``hallucinated`` entries), so it proves nothing then.  The Q25
   roster: 202, 439, 466, 480 and 557 are EMPTY_MIND (MonraceDefinitions), the others are shown.
 * Detection (spell-kind/spells-detection.cpp detect_monsters_normal / _invis / _evil): every
   monster within the radius (Grid::calc_distance <= DETECT_RAD_DEFAULT 30, a third in a DARKNESS
   dungeon); detect_all (the Rod of Detection, cmd-item/cmd-zaprod.cpp) is both the normal and the
   invisible detection, Detect Evil only the EVIL races (hunt_target.REVEALS; 480 is not evil).
   The detected monsters stay shown on the next board (MonsterConstantFlagType::MARK / SHOW).
 * The floor: Q25 is a 22 x 66 floor holding the 15 x 31 map (dungeon 0, Wilderness: no
   DARKNESS); the map's outer ring is permanent wall, nothing stands outside it.  A monster
   stands on the map's ground; a wall-passer (PASS_WALL, KILL_WALL) also in a wall the board does
   not show permanent.  From the melee ambush stand [10,1] a detection (30) reaches every cell
   inside the ring; from the ranged one [13,1] all but [1,29] and [2,29]; telepathy (20) from no
   cell of the start corridor covers the map, from a cell of the north corridor ([1,14]-[1,16],
   [2,13]-[2,17]) and a few of the hall all of it.
"""

from __future__ import annotations

from hengbot import hunt_target, me_powers, search_coverage
from hengbot import quest25_battle as battle_mod
from hengbot import quest25_geometry as geo
from hengbot.model import Position, game_distance

# monster/monster-update.cpp update_telepathy_sight: never sensed, or sensed one turn in ten.
_UNSENSED_MINDS = frozenset({"EMPTY_MIND", "WEIRD_MIND"})
_WALL_PASSING = frozenset({"PASS_WALL", "KILL_WALL"})
WALK_REASON = f"{battle_mod.REASON}:walk-to-presence-check"
CAST_REASON = f"{me_powers.REASON}:quest25-presence"


def _flags(ctx, race: int) -> frozenset:
    return hunt_target.race_flags(ctx.policy, race)


def _map_inside(ctx) -> dict:
    """The map's cells inside its outer ring (terrain kind each)."""
    terrain = ctx.terrain
    height = max(y for y, _x in terrain) + 1
    width = max(x for _y, x in terrain) + 1
    return {cell: kind for cell, kind in terrain.items()
            if 0 < cell[0] < height - 1 and 0 < cell[1] < width - 1}


def possible_cells(ctx, race: int) -> frozenset:
    """Where a monster of ``race`` can be on the floor: the map's ground inside its ring, and for a
    wall-passer also its walls the board does not show permanent (the module docstring)."""
    passes = bool(_flags(ctx, race) & _WALL_PASSING)
    cells = set()
    for cell, kind in _map_inside(ctx).items():
        if kind != "wall":
            cells.add(cell)
        elif passes:
            grid = ctx.snapshot.grid_at(Position(*cell))
            if grid is None or not grid.known or not grid.permanent:
                cells.add(cell)
    return frozenset(cells)


def telepathy_radius(ctx) -> int:
    """How far this board's telepathy shows a monster (0 without it, or hallucinating)."""
    if ctx.snapshot.player.hallucinated:
        return 0
    return search_coverage.walk_radius(ctx.policy, ctx.snapshot)


def detect_radius(ctx) -> int:
    """DETECT_RAD_DEFAULT, a third in a DARKNESS dungeon (spells-detection.cpp)."""
    radius = me_powers.DETECT_RAD
    return radius // 3 if search_coverage.darkness(ctx.policy, ctx.snapshot) else radius


def _distance(a, b) -> int:
    """Grid::calc_distance (the Newton-Raphson one both reaches use; model.game_distance)."""
    return game_distance(Position(*a), Position(*b))


def _within(centre, radius: int, cells) -> bool:
    return all(_distance(centre, cell) <= radius for cell in cells)


def shown_by(effect: str, flags) -> bool:
    """The detection ``effect`` shows a race of these flags (hunt_target.REVEALS)."""
    reveals = hunt_target.REVEALS.get(effect)
    return reveals is not None and reveals(flags)


# -- the plan's detection ----------------------------------------------------------------


def note_cast(ctx, effect: str) -> None:
    """``quest25_battle._detect_key`` keyed a detection of ``effect`` on this board."""
    battle = ctx.battle
    battle.cast = (int(ctx.snapshot.turn), ctx.here, effect, battle.presence_quiet, battle.recheck)


def cast_board(ctx) -> bool:
    """This board is the first one after the plan's detection went off (the game's time passed)."""
    cast = ctx.battle.cast
    return cast is not None and ctx.snapshot.turn > cast[0]


def _settle_cast(ctx):
    """(origin, radius, effect) of the detection this board shows the result of, else None.

    The first board after the cast settles it: one of the same game turn is a cast that did not go
    off (the menu walk closed a charging power's prompt: no game time passed, kill_all_patrol
    ``_settle_detection``), one with a failure line failed (``_detection_failed``); either is
    forgotten and the check may be made again.  Else the detection went off, and what it shows is
    on this board -- nothing at all when it found nothing: spells-detection.cpp prints
    「…の存在を感じとった！」 only for what it found (should_notify; detect_monsters_evil prints
    nothing with no evil monster in reach), so an empty board is the strongest sign of absence
    (n1-c life-211, 2026-11-15 09:03-09:07: 51 empty Detect Evil casts on the ambush read as
    nothing, and the wait for the dead tyrannosaurus went on).  The detection does not move the
    player: a board that shows the player off the cell the cast was keyed on is not its result (a
    monster's teleport-to in between, or a replayed recording whose next board followed another
    key), and is not read as one; the check then waits its next window."""
    battle = ctx.battle
    cast = battle.cast
    if cast is None:
        return None
    battle.cast = None
    turn, origin, effect, quiet_before, recheck_before = cast
    if ctx.snapshot.turn <= turn or battle_mod._detection_failed(ctx, turn):
        battle.presence_quiet, battle.recheck = quiet_before, recheck_before
        return None
    if ctx.here != tuple(origin):
        return None
    flags_shown = {monster.race_id for monster in ctx.hostiles()
                   if shown_by(effect, _flags(ctx, monster.race_id))}
    battle.presence_shown = battle.presence_shown | flags_shown
    return tuple(origin), detect_radius(ctx), effect


def note_absent(ctx) -> None:
    """Every roster race this board shows is not on the floor (the module docstring)."""
    detection = _settle_cast(ctx)
    if ctx.snapshot.player.hallucinated:
        return
    battle = ctx.battle
    shown = {monster.race_id for monster in ctx.hostiles()}
    telepathy = telepathy_radius(ctx)
    absent = dict(battle.absent)
    for race in geo.ROSTER:
        if race in absent or race in shown:
            continue
        flags = _flags(ctx, race)
        cells = possible_cells(ctx, race)
        if telepathy and not flags & _UNSENSED_MINDS:
            cells = {cell for cell in cells
                     if _distance(ctx.here, cell) > telepathy}
        if cells and detection is not None and shown_by(detection[2], flags):
            origin, radius, _effect = detection
            cells = {cell for cell in cells
                     if _distance(origin, cell) > radius}
        if not cells:
            absent[race] = int(ctx.snapshot.turn)
    battle.absent = absent


# -- the check while a phase waits ------------------------------------------------------


def detector_effect(found) -> str:
    """The effect of a ``quest25_battle._detector`` answer."""
    if found[0] == "power":
        return found[1].effect
    return me_powers.BY_KEY[(found[1], found[2].sval)].effect


def _checked(ctx, phase) -> list:
    """The races the phase waits for that are left: not killed, not absent."""
    return [race for race in phase.waits_for if ctx.kills(race) < geo.ROSTER[race]]


def presence_key(ctx, phase) -> str | None:
    """The waiting phase's presence check (the module docstring), else None."""
    battle = ctx.battle
    if phase.wait_limit is None or not phase.waits_for or not battle.ready or battle.cast is not None:
        return None
    if ctx.in_view() or battle.rallying or battle.strong:
        return None
    left = _checked(ctx, phase)
    if not left or any(monster.race_id in left for monster in ctx.hostiles()):
        return None
    if set(left) & battle.presence_shown:
        # A check showed one it waits for on the floor: the wait for it is the plan's own, and no
        # further check (nor the walk to a covering cell and back) is made this phase.  n1-b
        # life-399 (2026-11-15 16:46): from the ranged stand [13,1] the ambush walked to [12,2],
        # cast, saw the spectral tyrannosaurus present and walked back, every 50 quiet actions,
        # until the loop guard read the walks as no progress.
        return None
    window = ctx.values.quiet_actions
    if battle_mod._wait_limit(ctx, phase) - battle.quiet <= window:
        return None   # a short wait ends on its own within the window (the module docstring)
    if not battle.recheck and battle.quiet < battle.presence_quiet + window:
        return None
    found = battle_mod._detector(ctx)
    if found is None:
        return None
    effect = detector_effect(found)
    races = [race for race in left if shown_by(effect, _flags(ctx, race))]
    if not races:
        return None
    radius = detect_radius(ctx)
    cells = frozenset().union(*(possible_cells(ctx, race) for race in races))
    if _within(ctx.here, radius, cells):
        key = battle_mod._detect_key(ctx, CAST_REASON)
        if key is not None:
            # note_cast kept the ones before, for a cast that did not go off.
            battle.presence_quiet, battle.recheck = battle.quiet, False
        return key
    stands = {cell for cell, kind in ctx.terrain.items()
              if kind in geo.STANDABLE and _within(cell, radius, cells)}
    key = battle_mod._walk(ctx, stands, WALK_REASON)
    if key is None:   # no way to such a cell: the next check is the next window
        battle.presence_quiet, battle.recheck = battle.quiet, False
    return key
