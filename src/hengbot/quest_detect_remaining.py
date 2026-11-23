"""A room-sweep plan looks for the remaining enemies with its detection before it waits or closes in.

Owner 2026-11-20 (verbatim): 「残りの敵を探す時は感知を使うこと」, and earlier for every KILL_ALL quest
(2026-11-13, kill_all_patrol): 「全滅クエストで作戦を終えても終わらない時は周回して探す・感知があれば感知して
探す」.  QUEST_33 (n1-c life-217, 2026-11-19): the Queens were never on the board (placed beyond the
telepathy's 20), the Gachapins only while within it, and the plan chose its waits and its approach
from the map's placements.

What the game shows (C:/hengband/src):

* ``detect_all`` (the Rod of Detection, cmd-item/cmd-zaprod.cpp; spell-kind/spells-detection.cpp:622)
  and ``detect_monsters_evil`` (the Staff of Detect Evil) mark every monster within
  DETECT_RAD_DEFAULT 30 (spell/spells-util.h:3; a third in a DARKNESS dungeon; the rod's Powerful
  Activation 45, cmd-zaprod.cpp:50) with MARK and SHOW (spells-detection.cpp:376-377, 422-423);
  Detect Evil only the EVIL races (hunt_target.REVEALS: the Queens are GOOD).  ``detect_all`` runs
  ``detect_monsters_invis`` and ``detect_monsters_normal`` both: the invisible and the EMPTY_MIND
  monsters (no telepathy shows them) are marked too.
* The board shows a marked monster ("detected", bot/bot-json-output.cpp:524); the player's turn
  after the detection drops SHOW, the next one MARK and the monster leaves the board
  (core/player-processor.cpp:410-418).  So a detection shows the positions for the next board or
  two; the plan keeps them (``observe``: the last cell and game turn of every tracked monster the
  board showed, seen, sensed or detected).
* How long a kept cell holds: a monster gains speed_to_energy(speed) a game turn and moves at 100
  (monster-processor.cpp sweep_monster_process :676-683; core/speed-table.cpp), so in
  ``STALE_MOVES`` x 100 / energy game turns it may have made ``STALE_MOVES`` moves.  STALE_MOVES is 10,
  the Gachapins' vision: further than that it may have left the ground the wait reader judged it on
  (quest_wait_placement ``acts``).  A Queen (+10, 20 energy) holds 50 game turns, a +0 monster 100.

So (``missing``): a tracked race of the plan (``alignment_split.tracked_races``) has fewer members
known -- on the board, or kept and not stale -- than living (quest_alignment_split ``living``).  Then,
before the plan chooses where to wait or where to go (quest_room_sweep ``_advance``, quest_lure_approach),
the detection (``key``): the Magic-Eater's absorbed rows through me_powers (occasion ``QUEST_REMAINING``,
trigger ``quest-remaining-unseen``: the Detect Evil row, the absorbed Rod of Detection in its place when
usable, and the rod's own row, through Powerful Activation when safe -- owner 2026-11-01 「安全なら
強力発動で使う」), else a carried rod or staff (kill_all_patrol ``_detect_key``'s list), only for an
effect that reveals a missing race (``due``).  The wait reader then reads the kept cells in place of
the placements (quest_wait_placement ``awaited``).

The whole floor (owner 2026-11-22, verbatim: 「感知したというが、テレパシーだけに頼っていないか？全感知の
強力発動ならクエスト全域をカバーできるはずだが」; kill-all patrol 「テレパシーだけで「いない」と決めない」).
n1-c life-221 (Quest 33, 2026-11-23 12:56-12:59): the kill lines credited two of the three Its and two
of the three Bokrugs; the others died unnamed (「何かは死んだ。」 at 4485506, an unseen kill; the race is
in no line, q2_kill_credit ``_killed`` reads none) and no later detection showed them (from [1,19],
[2,20], [1,17] and [1,16] at radius 45, every placement of theirs inside).  ``living`` still read one
of each, so the 段2 lure (``after_races_dead`` [393, 595, 489]) never began, every stand of 段1 had
nothing coming and the 段3 stands waited for the Queens: after a teleport to [7,72] and one detection
there (45 short of the west rooms) the sweep stopped by name, quest:blocked:sweep-nothing-comes.

So a missing member is looked for over the whole floor.  The plan's detections (cell, game turn,
radius -- 45 through Powerful Activation -- and effect) that reveal the race and are fresh for it
(``stale_turns``) cover the floor when every non-wall cell of the quest map is within one of them
(Grid::calc_distance).  ``_Cover.steps`` are the floor's casts, greedily: the cell covering most of
the map, then the cell nearest it covering most of what is left (Quest 33 at 45: [15,39], then a
neighbour for the two far corners [1,78] and [29,78]).  The first detection is cast where the player
stands, as before; when its result board still misses a race, the plan walks to a cell of the next
cast that adds what the fresh detections leave (``walk_key``, the plan's own named walk,
maint-all-1123 (b)-3) and casts there (``due``).  A board after the fresh detections covered the
whole floor, with fewer members known than ``living``: the rest are dead, credited on the floor's
kill count as the kill lines are (``observe``), so the restart record keeps them (quest_sweep_record).
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache

from hengbot import quest_alignment_split, quest_exposure
from hengbot.model import Position
from hengbot.policy_constants import speed_energy

STALE_MOVES = 10
DETECT_REASON = "quest-strategy:detect-remaining"
WALK_REASON = "quest-strategy:detect-remaining-walk"
DETECT_RAD = 30  # DETECT_RAD_DEFAULT
POWERFUL_RAD = DETECT_RAD * 3 // 2  # cmd-item/cmd-zaprod.cpp:50, the rod's Powerful Activation
POWERFUL_SUFFIX = ":powerful"  # me_powers.POWERFUL_SUFFIX (me_powers imports this module's callers)
# The quest map's kinds no monster stands on (a flier crosses the pits, the lavas and the water; a
# tree is passable).
_WALL_KINDS = frozenset({"wall"})
# The kinds a detection is cast from.
_CAST_KINDS = frozenset({"floor", "passage", "exit"})


def _tracked(plan) -> tuple:
    split = quest_alignment_split.split_of(plan)
    return tuple(split["tracked_races"]) if split else ()


def stale_turns(policy, race: int) -> int:
    knowledge = policy._monrace_knowledge.get(race)
    energy = speed_energy(int(getattr(knowledge, "speed", 110) or 110))
    return STALE_MOVES * 100 // max(1, energy)


def observe(policy, snapshot, navigator, plan) -> None:
    """Every board: the last cell and game turn of each tracked monster the board shows; the races
    none of which lives are dropped; then the members no detection of the whole floor showed are
    written off (``_write_off``)."""
    races = _tracked(plan)
    if not races:
        return
    kept = dict(navigator.remain_seen)
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if monster.hostile and monster.race_id in races:
            kept[monster.index] = (monster.race_id, (monster.position.y, monster.position.x), int(snapshot.turn))
    living = {race: quest_alignment_split.living(policy, snapshot, navigator, plan, race) for race in races}
    for race, alive in living.items():
        entries = sorted((entry[2], index) for index, entry in kept.items() if entry[0] == race)
        for _turn, index in entries[:max(0, len(entries) - alive)]:
            del kept[index]   # more kept than living: the oldest are the dead ones
    navigator.remain_seen = kept
    _write_off(policy, snapshot, navigator, plan)


def kept_rows(policy, snapshot, navigator, plan) -> dict:
    """index -> (race, cell, turn) of the kept tracked monsters not on the board now and not stale."""
    shown = {monster.index for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)}
    return {index: entry for index, entry in navigator.remain_seen.items()
            if index not in shown and snapshot.turn - entry[2] <= stale_turns(policy, entry[0])}


def _known(snapshot, kept, race) -> int:
    """The members of ``race`` on the board, and kept fresh."""
    on_board = sum(1 for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                   if monster.hostile and monster.race_id == race)
    return on_board + sum(1 for entry in kept.values() if entry[0] == race)


def missing(policy, snapshot, navigator, plan) -> list:
    """The tracked races with members living whose cells are neither on the board nor kept fresh."""
    races = []
    kept = kept_rows(policy, snapshot, navigator, plan)
    for race in _tracked(plan):
        alive = quest_alignment_split.living(policy, snapshot, navigator, plan, race)
        if alive > _known(snapshot, kept, race):
            races.append(race)
    return races


def _write_off(policy, snapshot, navigator, plan) -> None:
    """The members of a missing race that the fresh detections over the whole floor did not show
    are dead (module docstring): credited on the kill count at this game turn."""
    cover = _cover(navigator)
    if cover is None:
        return
    for race in missing(policy, snapshot, navigator, plan):
        casts = _fresh_casts(policy, snapshot, navigator, (race,))
        if not casts or max(cast[1] for cast in casts) >= snapshot.turn:
            continue  # nothing covers yet, or the last detection's board is not read yet
        if cover.targets & ~_union(cover, casts):
            continue  # a part of the floor no fresh detection covered
        dead = (quest_alignment_split.living(policy, snapshot, navigator, plan, race)
                - _known(snapshot, kept_rows(policy, snapshot, navigator, plan), race))
        if dead <= 0:
            continue
        kills = Counter(navigator.split_kills)
        kills[race] += dead
        navigator.split_kills = dict(kills)
        navigator.split_kill_turns = (*navigator.split_kill_turns, *[(race, int(snapshot.turn))] * dead)


# -- the casts and the floor they cover ------------------------------------------------------


def _casts(navigator) -> tuple:
    """(cell, turn, radius, effect) of the plan's detections; a checkpoint's (cell, turn) is read as
    the plain Detect Evil, the narrowest."""
    return tuple((tuple(entry[0]), int(entry[1]), int(entry[2]), str(entry[3])) if len(entry) == 4
                 else (tuple(entry[0]), int(entry[1]), DETECT_RAD, "detect-evil")
                 for entry in navigator.remain_detections)


def _reveals(policy, effect: str, race: int) -> bool:
    from hengbot import hunt_target

    reveals = hunt_target.REVEALS.get(effect)
    return reveals is not None and reveals(hunt_target.race_flags(policy, race))


def _fresh_casts(policy, snapshot, navigator, races) -> list:
    """The detections that show every race of ``races``, within the fastest one's ``stale_turns``."""
    if not races:
        return []
    bound = min(stale_turns(policy, race) for race in races)
    return [cast for cast in _casts(navigator)
            if snapshot.turn - cast[1] <= bound and all(_reveals(policy, cast[3], race) for race in races)]


@lru_cache(maxsize=None)
def _reach(radius: int) -> tuple[int, ...]:
    """Grid::calc_distance: the widest dx within ``radius`` at each dy."""
    return tuple(max(dx for dx in range(radius + 1) if quest_exposure.game_distance((0, 0), (dy, dx)) <= radius)
                 for dy in range(radius + 1))


class _Cover:
    """The quest map's non-wall cells as bits (``targets``), the area a cast covers from a cell at a
    radius, and the floor's casts at the planned radius (``steps``: (cast cell, the cells it adds))."""

    def __init__(self, terrain: dict, radius: int):
        self.radius = radius
        self.width = 1 + max(cell[1] for cell in terrain)
        rows: dict[int, int] = {}
        for (y, x), kind in terrain.items():
            if kind not in _WALL_KINDS:
                rows[y] = rows.get(y, 0) | (1 << (y * self.width + x))
        self.rows = rows
        self.targets = 0
        for bits in rows.values():
            self.targets |= bits
        self.cells = sorted(cell for cell, kind in terrain.items() if kind in _CAST_KINDS)
        self._areas: dict = {}
        self.steps = self._plan()

    def area(self, cell, radius: int | None = None) -> int:
        radius = self.radius if radius is None else radius
        key = (tuple(cell), radius)
        if key not in self._areas:
            reach = _reach(radius)
            y, x = key[0]
            bits = 0
            for row, row_bits in self.rows.items():
                dy = abs(row - y)
                if dy > radius:
                    continue
                low = max(0, x - reach[dy])
                high = min(self.width - 1, x + reach[dy])
                bits |= row_bits & (((1 << (high - low + 1)) - 1) << (row * self.width + low))
            self._areas[key] = bits
        return self._areas[key]

    def _plan(self) -> tuple:
        steps = []
        left = self.targets
        previous = None
        while left and self.cells:
            gain, _near, cell = max(
                ((self.area(cell) & left).bit_count(),
                 -(0 if previous is None else quest_exposure.game_distance(previous, cell)),
                 tuple(-part for part in cell))
                for cell in self.cells)
            if gain == 0:
                break  # what is left no cast cell reaches
            cell = tuple(-part for part in cell)
            steps.append((cell, self.area(cell) & left))
            left &= ~self.area(cell)
            previous = cell
        return tuple(steps)


_COVERS: dict = {}


def _cover(navigator) -> _Cover | None:
    """The floor's cover at the planned radius: the widest this floor's detections reached (45 once
    cast through Powerful Activation), else the plain 30."""
    terrain = getattr(getattr(navigator, "battlefield", None), "terrain", None)
    if not terrain:
        return None
    radius = max((cast[2] for cast in _casts(navigator)), default=DETECT_RAD)
    key = (navigator.quest_id, radius, len(terrain))
    if key not in _COVERS:
        _COVERS[key] = _Cover(terrain, radius)
    return _COVERS[key]


def _union(cover: _Cover, casts) -> int:
    bits = 0
    for cell, _turn, radius, _effect in casts:
        bits |= cover.area(cell, radius)
    return bits


def _pending(policy, snapshot, navigator, races) -> frozenset | None:
    """The cells of the floor's first cast whose cells the fresh detections of ``races`` do not all
    cover: every cast cell covering all the cells that cast adds (the plan's own cast, not a cell
    covering only what is left of it, which would send a walk after each stale detection in turn);
    None when nothing is left that a cast reaches."""
    cover = _cover(navigator)
    if cover is None:
        return None
    covered = _union(cover, _fresh_casts(policy, snapshot, navigator, races))
    for _cell, adds in cover.steps:
        if adds & ~covered:
            return frozenset(cell for cell in cover.cells if cover.area(cell) & adds == adds)
    return None


def _results_pending(snapshot, navigator) -> bool:
    """The latest detection was sent on this board: its result is not on the board yet."""
    casts = _casts(navigator)
    return bool(casts) and max(cast[1] for cast in casts) >= snapshot.turn


def due(policy, snapshot, navigator, plan, reveals) -> bool:
    """A missing race this effect (``reveals``: flags -> bool) shows, the last detection's board read,
    and either no fresh detection of those races (cast where the player stands) or this cell is one
    the floor's next cast is made from (module docstring)."""
    from hengbot import hunt_target

    races = tuple(race for race in missing(policy, snapshot, navigator, plan)
                  if reveals(hunt_target.race_flags(policy, race)))
    if not races or _results_pending(snapshot, navigator):
        return False
    here = (snapshot.player.position.y, snapshot.player.position.x)
    if (not _fresh_casts(policy, snapshot, navigator, races)
            and getattr(policy, "_decision_entry_reason", None) != WALK_REASON):
        return True  # as it lands; not on the walk to the next cast's cell (an earlier one gone stale)
    pending = _pending(policy, snapshot, navigator, races)
    return pending is not None and here in pending


def _note_cast(policy, snapshot, navigator, effect: str | None = None) -> None:
    """The detection just sent: its cell, game turn, radius and effect (from the me_powers reason
    ``me-power:<trigger>:<effect>[:powerful]``, or given)."""
    reason = policy.last_reason or ""
    if effect is None:
        parts = reason.split(":")
        effect = parts[2] if len(parts) > 2 else "detect-evil"
    radius = POWERFUL_RAD if reason.endswith(POWERFUL_SUFFIX) else DETECT_RAD
    here = (snapshot.player.position.y, snapshot.player.position.x)
    navigator.remain_detections = (*navigator.remain_detections, (here, int(snapshot.turn), radius, effect))


def walk_key(policy, snapshot, navigator, plan) -> str | None:
    """Toward a cell of the floor's next cast while a missing race is not covered (module docstring);
    None with nothing pending, on such a cell (the cast is ``due``), or with no walk of the plan there."""
    from hengbot import quest_plan_base, quest_room_sweep

    races = tuple(missing(policy, snapshot, navigator, plan))
    if not races or _results_pending(snapshot, navigator) or not _casts(navigator):
        return None  # no detection yet: the first is cast where the player stands
    pending = _pending(policy, snapshot, navigator, races)
    here = (snapshot.player.position.y, snapshot.player.position.x)
    if pending is None or here in pending:
        return None
    path = quest_room_sweep._path(policy, navigator, plan, snapshot, {Position(*cell) for cell in pending})
    return quest_plan_base._path_step(policy, snapshot, path, WALK_REASON)


def key(policy, snapshot, navigator, plan) -> str | None:
    """The detection of the missing races, else the walk to where the next one covers the floor,
    else None (module docstring)."""
    from hengbot import hunt_target, kill_all_patrol, me_powers
    from hengbot.model import SV_ROD_DETECTION, SV_STAFF_DETECT_EVIL, TVAL_ROD, TVAL_STAFF

    if not _tracked(plan) or not missing(policy, snapshot, navigator, plan):
        return None
    if any(monster.hostile for monster in snapshot.visible_monsters):
        return None  # a fight on the board: its own rungs answer it
    cast = me_powers.power_key(policy, snapshot, me_powers.QUEST_REMAINING)
    if cast is not None:
        _note_cast(policy, snapshot, navigator)
        return cast
    if snapshot.player.class_id != me_powers.PLAYER_CLASS_MAGIC_EATER:
        # Another class: a carried rod or staff as kill_all_patrol uses it, for an effect that shows a
        # missing race (the rod any, the staff the EVIL ones).
        rod = any(item.tval == TVAL_ROD and item.sval == SV_ROD_DETECTION and not item.charging
                  for item in snapshot.inventory)
        effects = ["detect-all"] + (["detect-evil"] if any(
            item.tval == TVAL_STAFF and item.sval == SV_STAFF_DETECT_EVIL for item in snapshot.inventory) else [])
        if any(due(policy, snapshot, navigator, plan, hunt_target.REVEALS[effect]) for effect in effects):
            used = kill_all_patrol._detect_key(policy, snapshot)
            if used is not None:
                policy.last_reason = DETECT_REASON
                _note_cast(policy, snapshot, navigator, "detect-all" if rod else "detect-evil")
                return used
    # The Magic-Eater's absorbed rows answer the cast above through me_powers (its hostile and charge
    # rules); the walk to the next cast's cell is the plan's own.
    return walk_key(policy, snapshot, navigator, plan)


def trigger_due(ctx, power) -> bool:
    """me_powers' ``quest-remaining-unseen`` trigger: the quest floor's plan misses a race this row's
    effect reveals (``due``)."""
    from hengbot import hunt_target

    policy, snapshot = ctx.policy, ctx.snapshot
    quest_id = policy._active_fixed_quest_id(snapshot)
    profile = None if quest_id is None else policy.approved_quest_strategy(quest_id)
    plan = None if profile is None else profile.engagement_plan.get("room_sweep")
    navigator = None if plan is None else policy._quest_navigators.get(quest_id)
    reveals = hunt_target.REVEALS.get(power.effect)
    if navigator is None or reveals is None:
        return False
    return due(policy, snapshot, navigator, plan, reveals)
