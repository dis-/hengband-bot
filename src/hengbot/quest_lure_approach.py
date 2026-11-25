"""A room-sweep phase that lures one side's summoners out of the other's range, then closes on the
other side: ``room_sweep.lure_approach``.

QUEST_33 段2, owner 2026-11-19 (verbatim): 「ガチャピンを先に女王アリの範囲外まで誘導して処理。終わったら
森側からなるべく射線を通さないように女王アリに近づいて処理。壁を溶かすことも考慮に入れること。」  Asked
whether the lure may start where the Queens act too (no cell on the map lets a Gachapin act and no
Queen act, quest_wait_placement's ``acts``, even with every inner wall melted), the owner chose
「射線の外なら許す」: at the start only, on a cell no Queen has a line of fire to; as soon as a Gachapin is
seen, step back out of the Queens' range (vision 30 and their line within 20) and kill the Gachapins that
follow; a Queen and a Gachapin come to the same place: disengage.

The data (``lure_approach``): ``after_races_dead`` (the phase begins once these are dead: QUEST_33's 段1
summoners), ``lure_races`` (the Gachapins), ``approach_races`` (the Queens, whose range the lure leaves
and who are closed on afterwards).  The phase runs while an approach race lives.

1. The lure, while a lure race lives (``_lure``):

   * A lure race and an approach race on the board (seen or sensed) with a line between them within
     the spell range (melee-spell.cpp ``monst_spell_monst``: a monster casts at a hostile-aligned one it
     can ``projectable`` to; check_melee_spell_projection, MAX_RANGE 18): the disengage of
     quest_summon_answer (out of every awake hostile's lines, else the teleport); its steps after follow.
   * A lure race seen and an approach race acting on the player where he stands: a step back to the
     nearest cell where none acts (quest_wait_placement ``acts``: decide_process_continue,
     monster-processor.cpp:701-722), one where a seen lure race comes first.  A step that would leave every seen
     lure race not acting is held instead (it follows only while it acts), unless an approach race has
     a line of fire to the player there, up to the plan's ``enemy_wait_turns``.
   * A lure race seen with no approach race acting here: the plan's own fight (the shot, the blow, the
     wait for what comes).
   * None seen: to the lure's start, the reachable cell where a lure race acts and comes
     (quest_wait_placement ``comes``) and no approach race has a line of fire to the player (within
     MAX_PLAYER_SIGHT, the sight map: pits and lava pass, a tree or a closed door does not), the fewest
     approach races acting there, then the fewest steps.  The walks there may cross cells where both
     sides act and no approach race has a line (the owner's allowance), none other the split refuses.
     Held there until a lure race is seen, up to ``enemy_wait_turns``; then the cell is spent.

1b. The way opened (``_open_way``), owner 2026-11-19 (verbatim) for a lure with no cell a Gachapin
   walks to: 「壁を溶かして道を作る。邪魔なら木もファイアボルトなどで燃やして良い」.  With no start, or a lure
   race seen out of the approach races' range that neither comes nor can be shot: the fewest trees and
   granite walls (at most ``MAX_OPENINGS``) whose opening lets one walk, as the game moves it
   (quest_wait_placement ``walks``: the cells its moves were refused, else headed for), to a cell where
   it acts and no approach race has a line of fire, the map opened counted too (an opening changes the
   Queens' lines as well).  From the nearest cell out of every approach race's line of fire that reaches
   the first of them, it is opened: a tree by a burning power or device aimed at it (effect-feature.cpp
   affect_feature: FIRE, ELEC and PLASMA 「燃えた」, the tree becoming GRASS, or BRAKE one time in three;
   a bolt stops on the tree, the first grid without PROJECTION on its path), a granite wall by Stone to Mud
   along a ray every grid of which passes the beam (sealed_pocket ``melt_at_key``).  ``OPEN_TRIES`` uses
   per tree, sealed_pocket's own count per wall.  The map the plan reads is the board's where a tree is
   burnt or a wall melted (quest_alignment_split ``board_terrain``).

2. The approach, the lure races dead (``_approach``): nothing of the approach races in view, a walk to
   the cell from which exactly one approach race has a line to the player (where only one sees him),
   counting a granite wall beside it melted from there, on the forest side (a tree beside it) first,
   else the fewest of them; over the fewest cells in their lines, then the fewest walls melted, then
   the fewest steps.  The walk goes over the trees (the forest side: TREE has MOVE for the player and
   neither LOS nor PROJECTION, TerrainDefinitions.jsonc, so it blocks lines, floor/line-of-sight.cpp
   ``los`` via ``has_los_terrain_at``) and through granite: a quest map's inner '%' is GRANITE
   (QuestPreferences.jsonc), whose STONE flag Stone to Mud turns to floor (effect/effect-feature.cpp
   KILL_WALL :232-244, system/dungeon/dungeon-definition.cpp ``convert_terrain_id`` :38-53); the outer
   'X' is PERMANENT and never changes (:47-49), nor does a tree (not STONE; disintegration is refused,
   owner 2026-11-16).  A wall next on the walk is melted (sealed_pocket ``melt_at_key``: the wand, else
   the absorbed power); with no means the walk keeps to open ground.  In view, the plan's fight answers;
   on the cell with nothing come within ``enemy_wait_turns`` the cell is spent and the next chosen.
   QUEST_33's split stays in force for any EVIL summoner alive (the walks never enter where both act).

The sides already mixed (owner 2026-11-23, asked 「善と悪の召喚持ちがすでに同じ部屋に混ざって互いに召喚し合って
いる時、どうしますか？」, verbatim 「加速して向かい、強引に邪悪側を排除する。」): while quest_mixed_assault holds
its latch the lure gives way (no lure start, no step back, no disengage when a Queen and a Gachapin face
each other); the assault kills the Gachapins.  The approach to the Queens follows their death as before.
"""

from __future__ import annotations

import heapq

from hengbot import (
    quest_alignment_split,
    quest_exposure,
    quest_mixed_assault,
    quest_plan_base,
    quest_wait_placement,
)
from hengbot.model import Position
from hengbot.policy_constants import WAIT_KEY

FIELD = "lure_approach"
LURE_WALK_REASON = "quest-strategy:lure-walk"
LURE_BACK_REASON = "quest-strategy:lure-back"
APPROACH_WALK_REASON = "quest-strategy:queen-approach"
MELT_REASON = "quest-strategy:queen-approach-melt"
OPEN_WALK_REASON = "quest-strategy:lure-open-walk"
OPEN_BURN_REASON = "quest-strategy:lure-burn-tree"
OPEN_MELT_REASON = "quest-strategy:lure-melt-wall"
# The openings one way may need (the fewest are chosen; a way needing more is not opened).
MAX_OPENINGS = 3
# The uses aimed at one tree before it is given up (the wand's or the power's failures).
OPEN_TRIES = 3
# effect-feature.cpp affect_feature: the elements a tree 「燃えた」 to (owner 2026-11-19
# 「木もファイアボルトなどで燃やして良い」); disintegration stays refused (owner 2026-11-16).
BURNING_ELEMENTS = frozenset({"FIRE", "ELEC", "PLASMA"})
SPELL_RANGE = 18  # AngbandSystem::get_max_range
MAX_PLAYER_SIGHT = 20
_NEIGHBOURS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
_STAND = quest_exposure.STAND_KINDS
_APPROACH_WALK = quest_exposure.MAP_STAND_KINDS


def config(plan) -> dict | None:
    value = plan.get(FIELD) if isinstance(plan, dict) else None
    return value if isinstance(value, dict) else None


def valid(value) -> bool:
    """The schema (quest_strategies reads it at load)."""
    def races(item) -> bool:
        return isinstance(item, list) and all(isinstance(race, int) and not isinstance(race, bool)
                                              and race > 0 for race in item)

    return (isinstance(value, dict) and races(value.get("after_races_dead", []))
            and races(value.get("lure_races")) and races(value.get("approach_races"))
            and bool(value["lure_races"]) and bool(value["approach_races"]))


def _cell(position) -> tuple[int, int]:
    return position.y, position.x


def _living(policy, snapshot, navigator, plan, races) -> bool:
    return any(quest_alignment_split.living(policy, snapshot, navigator, plan, race) > 0 for race in races)


def active(policy, snapshot, navigator, plan) -> bool:
    """The phase runs: its ``after_races_dead`` dead, an approach race alive."""
    value = config(plan)
    return (value is not None
            and not _living(policy, snapshot, navigator, plan, value.get("after_races_dead", ()))
            and _living(policy, snapshot, navigator, plan, value["approach_races"]))


def _rows(policy, snapshot, navigator, plan, read, races) -> list:
    """The reader's rows of ``races`` (awake on the board, or placed and not accounted for), with
    those asleep on the board added: they act (and wake) by the same test."""
    rows = [row for row in read.rows if row.race in races]
    keys = {row.key for row in rows}
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if monster.hostile and monster.race_id in races and ("seen", monster.index) not in keys:
            rows.append(quest_wait_placement.Awaited(
                ("seen", monster.index), monster.race_id, _cell(monster.position),
                policy._monrace_knowledge.get(monster.race_id), monster))
    return rows


def _line_of_fire(read, row, spot) -> bool:
    from hengbot import quest_summon_answer as answer

    return (quest_exposure.game_distance(row.cell, spot) <= MAX_PLAYER_SIGHT
            and answer._sight_line(read.open_cells, row.cell, spot))


def _taken(policy, snapshot, navigator, plan, read, approach) -> frozenset:
    """The cells no walk of the lure enters: the warning's refusals, the plan's split refusals except
    those (the lure's allowance) no approach race has a line of fire to.  Each walker adds an owner's
    left cells (left_cells ``refused_yx``) itself."""
    from hengbot import quest_room_sweep

    refused = {_cell(cell) for cell in quest_room_sweep._refused_cells(policy, snapshot, navigator)}
    split = {spot for spot in quest_alignment_split.refused_cells(policy, snapshot, navigator, plan)
             if any(_line_of_fire(read, row, spot) for row in approach)}
    return frozenset(refused | split)


def _walk_from(navigator, snapshot, start, taken, limit=80) -> dict:
    """Cell -> (steps, previous) over the plan's walking map from ``start``."""
    terrain = quest_plan_base._terrain_of(navigator, snapshot, water=False)
    walkable = quest_exposure.DRY_WALK_KINDS
    seen = {start: (0, None)}
    frontier = [start]
    while frontier:
        nxt_frontier = []
        for cell in frontier:
            steps = seen[cell][0]
            if steps >= limit:
                continue
            for dy, dx in _NEIGHBOURS:
                nxt = (cell[0] + dy, cell[1] + dx)
                if nxt not in seen and nxt not in taken and terrain.get(nxt) in walkable:
                    seen[nxt] = (steps + 1, cell)
                    nxt_frontier.append(nxt)
        frontier = nxt_frontier
    return seen


def _path_to(seen, goal) -> list[Position]:
    path = []
    while goal is not None:
        path.append(Position(*goal))
        goal = seen[goal][1]
    return path[::-1]


def _hold(policy, navigator) -> str:
    navigator.lure_hold += 1
    policy.last_reason = quest_plan_base.HOLD_REASON
    return WAIT_KEY


# -- 1. the lure ------------------------------------------------------------------------------


def _facing(read, lure, approach) -> bool:
    """A lure race and an approach race on the board with a line between them in spell range."""
    lure_seen = [row for row in lure if row.monster is not None]
    approach_seen = [row for row in approach if row.monster is not None]
    sight = read.open_terrain()
    return any(quest_exposure.game_distance(one.cell, other.cell) <= quest_exposure.MAX_SPELL_RANGE
               and quest_exposure.projectable(sight, one.cell, other.cell)
               for one in lure_seen for other in approach_seen)


def _back(policy, snapshot, navigator, plan, read, lure_seen, approach, taken) -> str | None:
    """A step out of every approach race's range, holding while the step would lose them all."""
    from hengbot import left_cells

    here = _cell(snapshot.player.position)
    seen = _walk_from(navigator, snapshot, here, taken | left_cells.refused_yx(policy, snapshot))
    out = [cell for cell in seen if not any(read.acts(row, cell) for row in approach)]
    if not out:
        return None
    goal = min(out, key=lambda cell: (not any(read.comes(row, cell) for row in lure_seen), seen[cell][0], cell))
    path = _path_to(seen, goal)
    nxt = _cell(path[1])
    loses = not any(read.acts(row, nxt) for row in lure_seen)
    fired_on = any(_line_of_fire(read, row, here) for row in approach)
    if loses and not fired_on and navigator.lure_hold < int(plan.get("enemy_wait_turns", 0)):
        return _hold(policy, navigator)
    navigator.lure_hold = 0
    return quest_plan_base._path_step(policy, snapshot, path, LURE_BACK_REASON)


def _lure_start(policy, snapshot, navigator, plan, read, lure, approach, taken) -> str | None:
    from hengbot import left_cells

    here = _cell(snapshot.player.position)
    seen = _walk_from(navigator, snapshot, here, taken | left_cells.refused_yx(policy, snapshot))
    kinds = navigator.battlefield.terrain
    ranked = sorted(
        (sum(1 for row in approach if read.acts(row, cell)), steps, cell)
        for cell, (steps, _previous) in seen.items()
        if kinds.get(cell) in _STAND and cell not in navigator.lure_spent
        and any(read.comes(row, cell) for row in lure)
        and not any(_line_of_fire(read, row, cell) for row in approach))
    if not ranked:
        return None
    goal = ranked[0][2]
    if goal != here:
        navigator.lure_hold = 0
        return quest_plan_base._path_step(policy, snapshot, _path_to(seen, goal), LURE_WALK_REASON)
    if navigator.lure_hold >= int(plan.get("enemy_wait_turns", 0)):
        navigator.lure_spent = navigator.lure_spent | {here}
        navigator.lure_hold = 0
        return None
    return _hold(policy, navigator)


# -- 1b. opening the way (owner 2026-11-19 「壁を溶かして道を作る。邪魔なら木もファイアボルトなどで燃やして良い」)


def _openable(policy, snapshot, navigator, read, cell, burn: bool, melt: bool) -> bool:
    if cell in navigator.opened_cells or dict(navigator.open_tries).get(cell, 0) >= OPEN_TRIES:
        return False
    if read.terrain.get(cell) == "tree":
        return burn
    return melt and _meltable(snapshot, navigator, cell)


def _openings(policy, snapshot, navigator, read, row, spot, burn, melt):
    """The fewest trees and walls whose opening lets ``row`` walk to a player on ``spot`` as the game
    moves it (quest_wait_placement ``walks``): each time its walk stops or goes round, the first of the
    cells of the move that found none free, else of the cells its moves headed for, that can be opened.
    None beyond MAX_OPENINGS or with nothing to open."""
    opened: list = []
    current = read
    for _ in range(MAX_OPENINGS + 1):
        if current.walks(row, spot, current._blocked(row, spot) - {spot}):
            return opened
        candidates = [*current.last_refused, *reversed(current.last_headed)]
        cell = next((cell for cell in candidates if cell not in opened
                     and _openable(policy, snapshot, navigator, current, cell, burn, melt)), None)
        if cell is None or len(opened) >= MAX_OPENINGS:
            return None
        opened.append(cell)
        current = read.with_opened(opened)
    return None


# One successful burn opens the tree: the expected value of a burning use is capped at this.
TREE_BURN_HP = 1


def _fire_key(policy, snapshot, cell) -> str | None:
    """A burning power or device aimed at ``cell`` (me_device_attacks ``device_target_key``; a carried
    wand or rod through get_aim_dir's free cursor, as quest25_battle aims at a grid)."""
    from hengbot import me_device_attacks
    from hengbot.item_reservation import reserved_item_command
    from hengbot.model import TVAL_ROD, TVAL_WAND

    if snapshot.player.blind or snapshot.player.confused:
        return None
    best = None
    if me_device_attacks.can_use_powers(snapshot):
        level = snapshot.player.level
        for power, success in me_device_attacks.attack_uses(policy, snapshot, powerful=False):
            if not (power.element in BURNING_ELEMENTS and power.aimed):
                continue
            # The shared expected value of one use (me_device_attacks ``use_value``, owner 2026-11-23
            # 「期待値で攻撃手段を選ぶ」; whole-bot maintainability review 2026-11-23 K1, (a)-5): one
            # successful burn opens the tree, so the value is capped at one hit point -- the success
            # rate of a power that burns at all, as the choice by the success rate was.
            value = me_device_attacks.use_value(power, success, level, frozenset(), TREE_BURN_HP)
            if value > 0 and (best is None or value > best[0]):
                best = (value, power)
    if best is not None:
        key = me_device_attacks.device_target_key(policy, best[1], Position(*cell), snapshot)
        policy.last_reason = OPEN_BURN_REASON
        return key
    for item in snapshot.inventory:
        kind = {TVAL_WAND: "wand", TVAL_ROD: "rod"}.get(item.tval)
        power = me_device_attacks.POWERS.get((kind, item.sval)) if kind else None
        if (power is None or power.element not in BURNING_ELEMENTS or not item.known or item.charging
                or (kind == "wand" and item.charges <= 0)):
            continue
        suffix = "*p" + policy._cursor_delta_keys(snapshot.player.position, Position(*cell)) + "t5\x1b"
        key = reserved_item_command(policy, snapshot, kind, item, suffix=suffix)
        if key is not None:
            policy.last_reason = OPEN_BURN_REASON
            return key
    return None


def _can_burn(policy, snapshot) -> bool:
    from hengbot import me_device_attacks
    from hengbot.model import TVAL_ROD, TVAL_WAND

    if me_device_attacks.can_use_powers(snapshot) and any(
            power.element in BURNING_ELEMENTS and power.aimed
            for power, _success in me_device_attacks.attack_uses(policy, snapshot, powerful=False)):
        return True
    for item in snapshot.inventory:
        kind = {TVAL_WAND: "wand", TVAL_ROD: "rod"}.get(item.tval)
        power = me_device_attacks.POWERS.get((kind, item.sval)) if kind else None
        if (power is not None and power.element in BURNING_ELEMENTS and item.known and not item.charging
                and (kind != "wand" or item.charges > 0)):
            return True
    return False


def _reaches(policy, snapshot, read, origin, cell, tree: bool) -> bool:
    """From ``origin`` a bolt aimed at ``cell`` stops on it (its first grid without PROJECTION, within
    the spell range: projection-path-calculator.cpp), or a Stone to Mud beam along a ray meets it."""
    from hengbot import me_powers
    from hengbot.projection_path import projection_path

    if tree:
        if quest_exposure.game_distance(origin, cell) > SPELL_RANGE:
            return False
        path = projection_path(Position(*origin), Position(*cell), SPELL_RANGE,
                               lambda pos: (pos.y, pos.x) not in read.open_cells)
        return bool(path) and path[-1] == Position(*cell)
    dy, dx = cell[0] - origin[0], cell[1] - origin[1]
    if (dy, dx) == (0, 0) or not (dy == 0 or dx == 0 or abs(dy) == abs(dx)) or max(abs(dy), abs(dx)) > SPELL_RANGE:
        return False
    step = ((dy > 0) - (dy < 0), (dx > 0) - (dx < 0))
    # Every grid before the wall passes the beam on the map as it is (a tree does not: it would
    # stop the beam and Stone to Mud leaves it, effect-feature.cpp KILL_WALL needs STONE).
    for index in range(1, max(abs(dy), abs(dx))):
        if (origin[0] + step[0] * index, origin[1] + step[1] * index) not in read.open_cells:
            return False
    return me_powers.beam_direction(policy, snapshot, Position(*origin), Position(*cell)) is not None


def _open_way(policy, snapshot, navigator, plan, read, lure, approach, taken) -> str | None:
    """No cell brings a Gachapin: the fewest openings that make one walk to a cell where it acts and no
    Queen has a line of fire (counted over the map opened too); then, from the nearest cell out of the
    Queens' lines of fire that reaches it, the first of them burnt or melted."""
    from hengbot import left_cells, sealed_pocket

    burn, melt = _can_burn(policy, snapshot), sealed_pocket.can_melt(policy, snapshot)
    if not (burn or melt):
        return None
    here = _cell(snapshot.player.position)
    seen = _walk_from(navigator, snapshot, here, taken | left_cells.refused_yx(policy, snapshot))
    kinds = navigator.battlefield.terrain
    best = None
    for cell, (steps, _previous) in seen.items():
        if kinds.get(cell) not in _STAND or cell in navigator.lure_spent:
            continue
        acting = [row for row in lure if read.acts(row, cell)]
        if not acting or any(_line_of_fire(read, row, cell) for row in approach):
            continue
        for row in acting:
            openings = _openings(policy, snapshot, navigator, read, row, cell, burn, melt)
            if not openings:
                continue
            opened = read.with_opened(openings)
            if any(_line_of_fire(opened, other, cell) for other in approach):
                continue  # the opening would give a Queen a line to the player there
            rank = (len(openings), sum(1 for other in approach if read.acts(other, cell)), steps)
            if best is None or rank < best[0]:
                best = (rank, cell, openings)
    if best is None:
        return None
    _rank, _stand, openings = best
    target = openings[0]
    tree = read.terrain.get(target) == "tree"
    origins = [(steps, cell) for cell, (steps, _previous) in seen.items()
               if kinds.get(cell) in _STAND and not any(_line_of_fire(read, row, cell) for row in approach)
               and _reaches(policy, snapshot, read, cell, target, tree)]
    if not origins:
        return None
    _steps, origin = min(origins)
    if origin != here:
        return quest_plan_base._path_step(policy, snapshot, _path_to(seen, origin), OPEN_WALK_REASON)
    tries = dict(navigator.open_tries)
    key = (_fire_key(policy, snapshot, target) if tree
           else sealed_pocket.melt_at_key(policy, snapshot, Position(*target), OPEN_MELT_REASON))
    if key is not None:
        tries[target] = tries.get(target, 0) + 1
        navigator.open_tries = tuple(sorted(tries.items()))
    return key


def _lure(policy, snapshot, navigator, plan, board, value, read) -> str | None:
    from hengbot import quest_summon_answer as answer

    lure = _rows(policy, snapshot, navigator, plan, read, value["lure_races"])
    approach = _rows(policy, snapshot, navigator, plan, read, value["approach_races"])
    if _facing(read, lure, approach):
        return answer._disengage(policy, snapshot, navigator, plan, board)
    in_view = {monster.index for monster in board.in_view}
    lure_seen = [row for row in lure if row.monster is not None and row.monster.index in in_view]
    here = _cell(snapshot.player.position)
    taken = _taken(policy, snapshot, navigator, plan, read, approach)
    if lure_seen:
        if any(read.acts(row, here) for row in approach):
            return _back(policy, snapshot, navigator, plan, read, lure_seen, approach, taken)
        navigator.lure_hold = 0
        if (any(read.comes(row, here) for row in lure_seen)
                or any(quest_plan_base._shot(policy, snapshot, row.monster) is not None for row in lure_seen)):
            return None  # out of their range: the plan's fight (the shot, the wait for what comes)
        return _open_way(policy, snapshot, navigator, plan, read, lure_seen, approach, taken)
    return (_lure_start(policy, snapshot, navigator, plan, read, lure, approach, taken)
            or _open_way(policy, snapshot, navigator, plan, read, lure, approach, taken))


# -- 2. the approach ---------------------------------------------------------------------------


def _meltable(snapshot, navigator, cell) -> bool:
    """A granite wall of the quest map (QuestBattlefield ``stone_walls``) the board does not show
    gone or permanent."""
    if cell not in getattr(navigator.battlefield, "stone_walls", ()):
        return False
    grid = snapshot.grid_at(Position(*cell))
    return grid is None or not grid.known or (grid.wall and not grid.permanent)


def _approach_walk(snapshot, navigator, read, approach, start, taken, melt: bool):
    """Dijkstra over (cells in an approach race's line, walls melted, steps): cell -> (cost, previous)."""
    terrain = navigator.battlefield.terrain
    best = {start: ((0, 0, 0), None)}
    queue = [((0, 0, 0), start)]
    while queue:
        cost, cell = heapq.heappop(queue)
        if cost != best[cell][0]:
            continue
        for dy, dx in _NEIGHBOURS:
            nxt = (cell[0] + dy, cell[1] + dx)
            if nxt in taken:
                continue
            wall = melt and _meltable(snapshot, navigator, nxt)
            if terrain.get(nxt) not in _APPROACH_WALK and not wall:
                continue
            lined = any(_line_of_fire(read, row, nxt) for row in approach)
            step = (cost[0] + int(lined), cost[1] + int(wall), cost[2] + 1)
            if nxt not in best or step < best[nxt][0]:
                best[nxt] = (step, cell)
                heapq.heappush(queue, (step, nxt))
    return best


def _lines_at(read, approach, cell, open_cells) -> int:
    """How many approach races have a line of fire to ``cell`` over ``open_cells``."""
    from hengbot import quest_summon_answer as answer

    return sum(1 for row in approach if quest_exposure.game_distance(row.cell, cell) <= MAX_PLAYER_SIGHT
               and answer._sight_line(open_cells, row.cell, cell))


def _approach(policy, snapshot, navigator, plan, board, value, read) -> str | None:
    from hengbot import left_cells, quest_room_sweep, sealed_pocket

    approach = _rows(policy, snapshot, navigator, plan, read, value["approach_races"])
    if not approach or any(monster.race_id in value["approach_races"] for monster in board.in_view):
        return None  # in view: the plan's fight
    here = _cell(snapshot.player.position)
    taken = (frozenset(_cell(cell) for cell in quest_room_sweep._refused_cells(policy, snapshot, navigator))
             | quest_alignment_split.refused_cells(policy, snapshot, navigator, plan)
             | left_cells.refused_yx(policy, snapshot))
    melt = sealed_pocket.can_melt(policy, snapshot)
    best = _approach_walk(snapshot, navigator, read, approach, here, taken, melt)
    kinds = navigator.battlefield.terrain
    ranked = []
    for cell, (cost, _previous) in best.items():
        if kinds.get(cell) not in _STAND or cell in navigator.lure_spent:
            continue
        forest = any(kinds.get((cell[0] + dy, cell[1] + dx)) == "tree" for dy, dx in _NEIGHBOURS)
        lines = _lines_at(read, approach, cell, read.open_cells)
        if lines:
            ranked.append((lines != 1, not forest, lines, cost, cell, None))
        if not melt:
            continue
        # A wall beside it melted from there: where it would let one of them see the player.
        for dy, dx in _NEIGHBOURS:
            wall = (cell[0] + dy, cell[1] + dx)
            if _meltable(snapshot, navigator, wall):
                opened = _lines_at(read, approach, cell, read.open_cells | {wall})
                if opened > lines:
                    ranked.append((opened != 1, not forest, opened, (cost[0], cost[1] + 1, cost[2]), cell, wall))
    if not ranked:
        return None
    *_, goal, wall = min(ranked)
    if goal == here:
        if wall is not None and _meltable(snapshot, navigator, wall) and not sealed_pocket.worn_out(
                policy, snapshot, Position(*wall)):
            melted = sealed_pocket.melt_at_key(policy, snapshot, Position(*wall), MELT_REASON)
            if melted is not None:
                return melted
        if navigator.lure_hold >= int(plan.get("enemy_wait_turns", 0)):
            navigator.lure_spent = navigator.lure_spent | {here}
            navigator.lure_hold = 0
            return None
        return _hold(policy, navigator)
    path, cell = [], goal
    while cell is not None:
        path.append(cell)
        cell = best[cell][1]
    path.reverse()
    nxt = path[1]
    navigator.lure_hold = 0
    if _meltable(snapshot, navigator, nxt):
        if sealed_pocket.worn_out(policy, snapshot, Position(*nxt)):
            return None
        return sealed_pocket.melt_at_key(policy, snapshot, Position(*nxt), MELT_REASON)
    return quest_plan_base._path_step(policy, snapshot, [Position(*spot) for spot in path], APPROACH_WALK_REASON)


# -- the entry ---------------------------------------------------------------------------------


def key(policy, snapshot, navigator, plan, board) -> str | None:
    """The phase's step on this board, else None (the plan's own rungs answer it)."""
    value = config(plan)
    if (value is None or snapshot.player.blind or snapshot.player.confused
            or not active(policy, snapshot, navigator, plan)):
        return None
    if _living(policy, snapshot, navigator, plan, value["lure_races"]):
        if quest_mixed_assault.active(policy, snapshot, navigator, plan):
            return None  # the sides already mixed: no lure, the assault (owner 2026-11-23)
        read = quest_wait_placement.reader(policy, snapshot, navigator, plan)
        return _lure(policy, snapshot, navigator, plan, board, value, read)
    read = quest_wait_placement.reader(policy, snapshot, navigator, plan)
    return _approach(policy, snapshot, navigator, plan, board, value, read)
