"""Quest 25's phase battle (quest25_battle): the walks, the casters' fire, the doors and the traps.

Every step of the plan goes through ``_step`` (quest_plan_base.plan_walk; the cells no walk passes,
``_no_pass``, and the plan's contract), every walk through ``_walk`` (never toward a shunned mover);
out of the never-moving casters' fire and the rest there; the doors (quest_plan_base.plan_door) and
the trap cells of the map; the walk to a cell that sees an unseen target (``_unseen_fire``).

Imports quest25_battle_board and quest25_battle_attack.

Split from quest25_battle.py (maintainability review 2026-11-23 (a)-8, behaviour unchanged).
"""

from __future__ import annotations

from hengbot import (
    left_cells, me_powers, quest25_geometry as geo, quest_exposure, quest_plan_base, threat_tiers,
    trap_warning,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.model import (
    Position, SV_ROD_DISARMING, SV_SCROLL_DETECT_TRAP, SV_STAFF_DETECT_TRAP, SV_WAND_DISARMING,
    SV_WAND_TRAP_DOOR_DEST, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND,
)
from hengbot.policy_constants import DIRECTION_KEYS, REST_MACRO, SEARCH_KEY, WAIT_KEY
from hengbot.unseen_strike import message_text
from hengbot.quest25_battle_board import (
    _Ctx, _ctx, _druj_done, _ipsissimus_alive, _sights, _tome_done, DISARM_REASON, FIRE_HOLD_REASON,
    FIRE_REST_REASON, OPEN_REASON, OUT_OF_FIRE_REASON, SEARCH_REASON, SIGHT_REASON, TRAP_DETECT_REASON,
    WALK_REASON, WITHDRAW_REASON,
)
from hengbot.quest25_battle_attack import (
    _engage, _fight_targets, _fire_at, _hold,
)


# -- walking ----------------------------------------------------------------------------


def _avoided(ctx: _Ctx) -> set:
    """The cells a walk crosses as few of as it can."""
    bf = ctx.navigator.battlefield
    cells = {cell for cell in (*bf.trap_cells, *bf.maybe_trap_cells) if cell not in ctx.battle.cleared}
    if _ipsissimus_alive(ctx):
        cells |= geo.summon_cells(ctx.terrain)
    return cells


def _refused(ctx: _Ctx) -> frozenset:
    """The cells a weapon warning was refused on (``_warning_refused_cells``): never walked onto.

    n1-c life-200 (2026-11-12 12:03): after the refusal of (6,29)->(5,29) the walk aimed at
    (5,29) again on every decision; the gate turned the step into a wait and the wait into a
    flee, so the plan went back and forth.  The plan's walks go round them like an occupied cell,
    and a walk with no way round holds (``_step``).

    Only while a known monster could still raise that warning (trap_warning ``_monster_could_warn``,
    the test that latched it: awake, hostile, within the game's 12 cells, beside the cell or with a
    line to it; warning.cpp process_warning).  n1-c life-207 (2026-11-14 17:23:53): the ambush's
    step onto [9,1] was warned of the spectral tyrannosaur beside it and refused; it was killed two
    decisions later, and the latch stayed for the floor.  [9,1] is the only way from [10,1] to the
    wall-passers' stand [7,1], so the phase held on [10,1] for over 5,300 decisions with nothing in
    reach of [9,1].  A latch whose monsters are gone is the stale one ``_unlatch_stale`` lifts when
    the plan steps onto it; a trap's latch (``_trap_warning_cells``) stays as it was."""
    policy, snapshot = ctx.policy, ctx.snapshot
    traps = getattr(policy, "_trap_warning_cells", {})
    return frozenset((cell.y, cell.x) for cell in getattr(policy, "_warning_refused_cells", ())
                     if cell in traps or trap_warning._monster_could_warn(policy, snapshot, cell))


def _unlatch_stale(ctx: _Ctx, cell) -> None:
    """Before the plan steps onto ``cell``: a refusal's latch no known monster could raise again
    (not in ``_refused``) is lifted, so the step gate (``_warning_step_refused``) lets the step
    through.  Should the game warn again (a monster the board does not show), the prompt is
    refused and latched as on any step (trap_warning ``note_warned``)."""
    target = Position(*cell)
    if target in getattr(ctx.policy, "_warning_refused_cells", ()) and tuple(cell) not in _refused(ctx):
        ctx.policy._release_warning_refusal(target)


def _druj_shut(ctx: _Ctx) -> frozenset:
    """The druj's door [11,19] while the druj lives: no walk of the plan opens or crosses it.

    Owner (phase7, ``revised_plan_draft``): 「ドアを開けずに13,20に移動して、11,19を岩石溶解して
    11,19に範囲攻撃」, and 2026-11-23 「立ち位置を守れば一切の反撃を受けずに倒せた」.  n1-c life-221
    (2026-11-23 05:03:15): the stairway phase's walk to a sight cell (``_walk_to_sight``) went to
    [11,19], keyed ``o4`` from [11,20] and stepped into the doorway beside the druj; the door stood
    open for the druj's phase, which then fought it from its line ([11,25], [12,24]) and was cursed
    (HP 672 -> 389).  [11,19] leads nowhere but the druj's own cell [11,18]."""
    return frozenset() if _druj_done(ctx) else frozenset({geo.DRUJ_DOOR})


def _no_pass(ctx: _Ctx) -> frozenset:
    """The plan's cells no walk passes (quest_plan_base ``Contract.no_pass``): the warning's refused
    cells (``_refused``), the cells an owner left (left_cells), and the druj's door while it lives
    (``_druj_shut``).  ``_path`` routes round them and ``_step`` steps onto none of them."""
    return _refused(ctx) | left_cells.refused_yx(ctx.policy, ctx.snapshot) | _druj_shut(ctx)


def contract(ctx: _Ctx, plan) -> quest_plan_base.Contract:
    """The phase battle's contract: the owner's named stands, the cells no walk passes
    (``_no_pass``), the room sweep plan's rest line."""
    return quest_plan_base.Contract(stand_cells=geo.PLAN_STANDS, no_pass=_no_pass(ctx),
                                    recovery_line=quest_plan_base.recovery_line_of(plan))


def _path(ctx: _Ctx, goals, taken=frozenset()) -> list[tuple[int, int]]:
    refused = _no_pass(ctx)
    goals = {tuple(goal) for goal in goals} - refused
    if not goals:
        return []
    start = ctx.here
    occupied = (frozenset((monster.position.y, monster.position.x) for monster in ctx.seen_hostiles())
                | taken | refused)
    exposure = geo.exposure_of(_avoided(ctx))
    return quest_plan_base._least_exposed_walk(
        ctx.navigator, ctx.snapshot, exposure, start, goals, occupied - goals)


def _step(ctx: _Ctx, cell, reason: str = WALK_REASON, *, guard: bool = True) -> str:
    no_pass = _no_pass(ctx)
    if tuple(cell) in no_pass:
        return _hold(ctx)   # a cell not to pass is not stepped onto: the plan holds where it is
    if guard and (held := _fire_guard(ctx, cell)) is not None:
        return held
    _unlatch_stale(ctx, cell)
    return quest_plan_base.plan_walk(ctx.policy, ctx.snapshot, cell, reason, no_pass=no_pass)


# Owner 2026-11-12: a race this many strong among the awake movers is a pack the walk shuns.
PACK_SIZE = 3


def _shunned(ctx: _Ctx) -> list:
    """The awake movers no walk goes toward (owner 2026-11-11 「召喚された強敵や T1 の敵の方へは歩かない」,
    widened 2026-11-12 to every phase, 第0段・第1段 included): one that alone is T1 (threat_tiers
    ``alone_t1``: ``cannot_win``, owner 2026-11-17 maintainability review Q6 「含める」; until then
    only ``tier == "T1"``), a summons the phase-2 teleport was read from (``battle.strong``), a pack
    (``PACK_SIZE`` of a race)."""
    movers = [monster for monster in ctx.hostiles()
              if not monster.asleep and not monster.can_multiply
              and not quest_plan_base._never_moves(ctx.policy, monster)]
    if not movers:
        return []
    counts = {}
    for monster in movers:
        counts[monster.race_id] = counts.get(monster.race_id, 0) + 1
    strong = {race for race, _cell in ctx.battle.strong}
    shunned = []
    for monster in movers:
        if (counts[monster.race_id] >= PACK_SIZE or monster.race_id in strong
                or threat_tiers.alone_t1(ctx.policy, ctx.snapshot, monster)):
            shunned.append(monster)
    return shunned


def _toward_cells(ctx: _Ctx, shunned) -> frozenset:
    """The cells beside each shunned mover and, of those in view, every cell nearer to it than the
    player stands (``_rally``'s rule)."""
    cells = [(monster.position.y, monster.position.x) for monster in shunned]
    seen = {monster.index for monster in ctx.seen_hostiles()}
    near = {(y + dy, x + dx) for (y, x) in cells for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
    looked = [(monster.position.y, monster.position.x) for monster in shunned if monster.index in seen]
    near |= {cell for cell in ctx.terrain
             if any(quest_exposure.game_distance(cell, each) < quest_exposure.game_distance(ctx.here, each)
                    for each in looked)}
    return frozenset(near - {ctx.here})


def _shunned_hold(ctx: _Ctx, toward) -> str:
    """No way that does not go toward them: 「道が無ければ今いる召喚を受けないマスで迎え撃つ」 (owner
    2026-11-12, the 11-11 choke hold).  Off a summon-safe cell, a walk to the nearest one first."""
    targets = _fight_targets(ctx)
    summons = geo.summon_cells(ctx.terrain)
    if ctx.here in summons:
        safe = {cell for cell, kind in ctx.terrain.items()
                if kind in {"floor", "door"} and cell not in summons}
        path = _path(ctx, safe, toward)
        if len(path) >= 2:
            ctx.policy._declare_reach(Position(*path[-1]))
            return _step(ctx, path[1], WALK_REASON, guard=False)
    ctx.battle.no_way = ctx.here
    return _engage(ctx, targets) or _hold(ctx)


def _walk(ctx: _Ctx, goals, reason: str = WALK_REASON, *, taken=frozenset()) -> str | None:
    """The next step toward ``goals`` (the trap rule first); None there or with no way.
    ``taken``: cells the walk does not cross besides the monsters in view.  Never toward a shunned
    mover (``_shunned``): with no other way, the hold where the player stands.

    ``battle.no_way``: the cell this walk found no way on from (none at all, or only toward the
    shunned, ``_shunned_hold``'s hold), else None; a phase's wait counts there as on its stand
    (``_observe``)."""
    ctx.battle.no_way = None
    goals = {tuple(goal) for goal in goals}
    if ctx.here in goals:
        return None
    shunned = _shunned(ctx)
    toward = _toward_cells(ctx, shunned) if shunned else frozenset()
    path = _path(ctx, goals, frozenset(taken) | toward)
    if len(path) < 2 and toward and len(_path(ctx, goals, taken)) >= 2:
        return _shunned_hold(ctx, toward)
    if len(path) < 2:
        ctx.battle.no_way = ctx.here
        return None
    nxt = path[1]
    trap = _trap_key(ctx, nxt)
    if trap is not None:
        return trap
    if (held := _fire_guard(ctx, nxt)) is not None:
        return held
    ctx.policy._declare_reach(Position(*path[-1]))
    return _step(ctx, nxt, reason, guard=False)


# -- the casters' fire (owner 2026-11-09) ------------------------------------------------
#
# Owner 2026-11-09 (n1-c life-178): 「第二に一歩で安全圏に移動して休息できるのに愚かにも戦闘を継続した
# こと。」, the formation's 「傷ついて敵がいなければ射線の外まで歩いて休む」 and 「クイル・破壊集大成・
# ドルジの射線のマスでは待たず、休まない」.  The fire is where a never-moving caster's spell reaches
# (phase3_spell_ranges): the tome's and the druj's own lines and the cells beside them their balls
# and breaths are aimed at, the quylthulgs' lines (their teleports need one).  Damaged is below the
# plan's rest line (room_sweep ``rest_below_ratio``).  With no enemy in view, a damaged player
# steps out of the fire when one step does it, and does not walk back into it: it rests first.


def _fire(ctx: _Ctx) -> frozenset:
    terrain = ctx.open_terrain()
    quyls_left = ctx.kills(geo.QUYL) < geo.ROSTER[geo.QUYL]
    cells = set()
    for cell, race in ctx.navigator.battlefield.monster_placements:
        if (race == geo.TOME and not _tome_done(ctx)) or (race == geo.DRUJ and not _druj_done(ctx)):
            cells |= geo.fire_cells(terrain, (cell,))
        elif race == geo.QUYL and quyls_left and cell not in ctx.battle.quyls_done:
            cells |= geo.line_cells(terrain, cell)
    return frozenset(cells)


def _damaged(ctx: _Ctx) -> bool:
    plan = ctx.profile.engagement_plan["room_sweep"]
    return ctx.snapshot.player.hp_ratio < float(plan["rest_below_ratio"])


def _rest_out_of_fire(ctx: _Ctx) -> str:
    """Rest on a cell out of the fire; a rest keyed on the decision before that did not raise HP
    is followed by one turn held (the game time passes either way)."""
    battle, player = ctx.battle, ctx.snapshot.player
    decision = int(getattr(ctx.policy, "_decision_sequence", 0))
    last = battle.fire_rest
    if ((last is not None and last[0] == decision - 1 and player.hp <= last[1]) or player.confused
            or player.food_state not in {"normal", "full", "gorged", "hungry"}):
        battle.fire_rest = None
        ctx.policy.last_reason = FIRE_HOLD_REASON
        return WAIT_KEY
    battle.fire_rest = (decision, player.hp)
    ctx.policy.last_reason = FIRE_REST_REASON
    return REST_MACRO


def _fire_guard(ctx: _Ctx, cell) -> str | None:
    """A damaged player with no enemy in view does not step from out of the fire into it."""
    if not _damaged(ctx) or ctx.seen_hostiles():
        return None
    fire = _fire(ctx)
    if tuple(cell) not in fire or ctx.here in fire:
        return None
    return _rest_out_of_fire(ctx)


def _safe_cells(ctx: _Ctx, fire) -> set:
    cells = {cell for cell, kind in ctx.terrain.items() if kind in {"floor", "door"} and cell not in fire}
    if _ipsissimus_alive(ctx):
        cells -= geo.summon_cells(ctx.terrain)
    return cells


def _withdraw(ctx: _Ctx, reason: str = WITHDRAW_REASON) -> str | None:
    """Out of the fire by the least exposed walk, then the rest there."""
    if ctx.here not in _fire(ctx):
        return _rest_out_of_fire(ctx)
    return _leave_fire(ctx, reason)


def _leave_fire(ctx: _Ctx, reason: str = WITHDRAW_REASON) -> str | None:
    """In the fire: the first step of the least exposed walk out of it; else None."""
    fire = _fire(ctx)
    if ctx.here not in fire:
        return None
    refused = _refused(ctx)
    safe = _safe_cells(ctx, fire) - refused
    occupied = frozenset((monster.position.y, monster.position.x) for monster in ctx.seen_hostiles())
    terrain = quest_plan_base._terrain_of(ctx.navigator, ctx.snapshot, water=False)
    terrain[ctx.here] = "floor"
    path = quest_exposure.least_exposed_path(terrain, geo.exposure_of(fire | _avoided(ctx)),
                                             ctx.here, safe, (occupied - safe) | refused)
    if len(path) < 2:
        return None
    trap = _trap_key(ctx, path[1])
    if trap is not None:
        return trap
    return _step(ctx, path[1], reason, guard=False)


def _out_of_fire_key(policy, snapshot) -> str | None:
    """「一歩で安全圏に移動して休息できる」: damaged in the fire with no enemy in view, one step out."""
    ctx = _ctx(policy, snapshot)
    if ctx is None or not _damaged(ctx) or ctx.seen_hostiles():
        return None
    fire = _fire(ctx)
    if ctx.here not in fire:
        return None
    occupied = {(monster.position.y, monster.position.x) for monster in ctx.hostiles()}
    traps = {cell for cell in (*ctx.navigator.battlefield.trap_cells,
                               *ctx.navigator.battlefield.maybe_trap_cells)
             if cell not in ctx.battle.cleared}
    beside = sorted(cell for cell in _safe_cells(ctx, fire) - occupied - traps - _refused(ctx)
                    if quest_exposure.game_distance(cell, ctx.here) == 1)
    if not beside:
        return None
    return _step(ctx, beside[0], OUT_OF_FIRE_REASON, guard=False)


def _direction(origin, cell) -> str:
    return DIRECTION_KEYS[((cell[0] > origin[0]) - (cell[0] < origin[0]),
                           (cell[1] > origin[1]) - (cell[1] < origin[1]))]


def _open_key(ctx: _Ctx, door) -> str:
    """The key that opens ``door`` beside the player (quest_plan_base ``plan_door``: ``o`` +
    direction, the lock and jam counts), under the open's reason.

    do_cmd_open (cmd-action/cmd-open-close.cpp) with easy_open takes the direction itself when the
    player has exactly one closed door around him, and the composed ``o`` + direction then left the
    direction key to the next command, a step onto the opened door.  n1-c life-221 (2026-11-23
    05:00:39, Quest 25 phase 「stairway」): ``o6`` on the stand [13,27] opened [13,28] and the ``6``
    walked onto it, beside the stairway to hell [13,29] (owner 「[13,27] から階段までは距離2」).
    The key keeps its direction: observed_input sends the ``o`` alone and releases the direction
    only at the observed direction question, for every producer (EASY_DIRECTION_COMMANDS)."""
    return quest_plan_base.plan_door(ctx.policy, ctx.snapshot, door, OPEN_REASON)


# -- traps (phase4, phase5) -------------------------------------------------------------


def _disarm_device_key(ctx: _Ctx, cell) -> str | None:
    """「トラップ解除手段があるなら使う」: an absorbed disarming power, else a carried one."""
    key = me_powers.power_key(ctx.policy, ctx.snapshot, me_powers.TRAP, Position(*cell))
    if key is not None:
        return key
    player = ctx.snapshot.player
    if player.blind or player.confused:
        return None
    for tval, svals, verb in ((TVAL_ROD, (SV_ROD_DISARMING,), "rod"),
                              (TVAL_WAND, (SV_WAND_DISARMING, SV_WAND_TRAP_DOOR_DEST), "wand")):
        item = next((item for item in ctx.snapshot.inventory if item.tval == tval and item.known
                     and item.sval in svals and not item.charging
                     and (tval == TVAL_ROD or item.charges > 0)), None)
        if item is not None:
            key = reserved_item_command(ctx.policy, ctx.snapshot, verb, item,
                                        suffix=_direction(ctx.here, cell))
            if key is not None:
                ctx.policy.last_reason = DISARM_REASON
                return key
    return None


def _trap_key(ctx: _Ctx, cell) -> str | None:
    """Before stepping onto a trap cell of the map: what the owner's rule asks there."""
    bf, battle = ctx.navigator.battlefield, ctx.battle
    always, maybe = cell in bf.trap_cells, cell in bf.maybe_trap_cells
    if not (always or maybe) or cell in battle.cleared:
        return None
    grid = ctx.snapshot.grid_at(Position(*cell))
    if grid is not None and grid.trap:
        battle.found = battle.found | {cell}
        _note_beam(ctx, cell)
        ctx.policy.last_reason = DISARM_REASON
        return quest_plan_base.plan_walk(ctx.policy, ctx.snapshot, cell)   # the disarm command
    if cell in battle.found:   # seen with its trap, now without: disarmed
        battle.cleared = battle.cleared | {cell}
        return None
    if grid is not None and grid.object_count:
        # An item lies there, so no trap does: a trap terrain has no DROP (TerrainDefinitions),
        # an item is dropped only where Grid::can_drop_item, and a trap is placed only on a
        # clean grid (FloorType::place_trap_at, Grid::is_clean).  Searching would never find one.
        battle.cleared = battle.cleared | {cell}
        return None
    if _settled_on_board(ctx, grid):
        battle.cleared = battle.cleared | {cell}
        return None
    device = _disarm_device_key(ctx, cell)
    if device is not None:
        battle.cleared = battle.cleared | {cell}
        _note_beam(ctx, cell)
        return device
    if cell not in battle.detect_asked:
        detect = _trap_detect_key(ctx)
        if detect is not None:
            battle.detect_asked = battle.detect_asked | {cell}
            battle.detection = (int(ctx.snapshot.turn), ctx.here)
            return detect
    searched = battle.searches.get(cell, 0)
    limit = ctx.values.maybe_trap_searches if maybe and not always else ctx.values.trap_searches
    if searched >= limit:
        battle.cleared = battle.cleared | {cell}   # 「罠は無いとみなして通る」
        return None
    battle.searches = {**battle.searches, cell: searched + 1}
    ctx.policy.last_reason = SEARCH_REASON
    return SEARCH_KEY


def _settled_on_board(ctx: _Ctx, grid) -> bool:
    """The board's own record that the grid holds no hidden trap: known, no trap shown, and no
    longer CAVE_UNSAFE (grid_map.unsafe_rows).  Every grid of a dungeon floor starts unsafe
    (floor-generator.cpp wipe_generate_random_floor_flags); a trap detection clears it within its
    range after disclosing every trap there (spells-detection.cpp detect_feat_flag), KILL_TRAP and
    KILL_DOOR clear it on the grids of their path in sight after destroying the trap
    (effect-feature.cpp), and a step clears it only in light or where no trap is (player-move.cpp
    move_player_effect).  The flag is the game's, so it outlives a restart of the bot."""
    return (grid is not None and grid.known and not grid.trap
            and ctx.snapshot.unsafe_rows is not None and not ctx.snapshot.unsafe_rows_malformed
            and not ctx.snapshot.unsafe_rows[grid.position.y][grid.position.x])


def _trap_detect_key(ctx: _Ctx) -> str | None:
    """Owner 2026-11-09 「罠探知があるなら使用することで確定」: the absorbed Detect Traps power,
    else a carried Staff or Scroll of Detect Traps (detect_traps, DETECT_RAD_DEFAULT)."""
    key = me_powers.power_key(ctx.policy, ctx.snapshot, me_powers.TRAP_CELL)
    if key is not None:
        return key
    player = ctx.snapshot.player
    if player.blind or player.confused or player.hallucinated:
        return None
    for tval, sval, verb in ((TVAL_STAFF, SV_STAFF_DETECT_TRAP, "staff"),
                             (TVAL_SCROLL, SV_SCROLL_DETECT_TRAP, "read")):
        item = next((item for item in ctx.snapshot.inventory if item.tval == tval and item.known
                     and item.sval == sval and (tval != TVAL_STAFF or item.charges > 0)), None)
        if item is not None:
            key = reserved_item_command(ctx.policy, ctx.snapshot, verb, item)
            if key is not None:
                ctx.policy.last_reason = TRAP_DETECT_REASON
                return key
    return None


# The lines of a use that went off without its effect (cmd-magiceat.cpp, use-execution.cpp).
_USE_FAILED_LINES = ("呪文をうまく唱えられなかった！", "You failed to get the magic off!",
                     "杖をうまく使えなかった。", "You failed to use the staff properly.")


def _settle_detection(ctx: _Ctx) -> None:
    """The board after a trap detection keyed for a cell: unless the use failed, every trap
    within the detected area is shown (detect_feat_flag discloses each), so each map trap cell
    within ``DETECT_RAD - 1`` of where it was used is answered: found when its trap is shown,
    else cleared (no trap)."""
    battle = ctx.battle
    if battle.detection is None or ctx.snapshot.turn <= battle.detection[0]:
        return
    _turn, origin = battle.detection
    battle.detection = None
    if any(message_text(message) in _USE_FAILED_LINES for message in ctx.snapshot.messages):
        return
    bf = ctx.navigator.battlefield
    for cell in {*bf.trap_cells, *bf.maybe_trap_cells}:
        if quest_exposure.game_distance(origin, cell) > me_powers.DETECT_RAD - 1:
            continue
        grid = ctx.snapshot.grid_at(Position(*cell))
        if grid is None:
            continue
        if grid.trap:
            battle.found = battle.found | {cell}
        else:
            battle.cleared = battle.cleared | {cell}


# The line KILL_TRAP prints for each trap it destroys on a known grid (effect-feature.cpp).
_FLASH_LINES = ("まばゆい閃光が走った！", "There is a bright flash of light!")


def _note_beam(ctx: _Ctx, cell) -> None:
    """An answer aimed from beside at the trap cell ``cell``: a disarming power or device goes
    on along the line past it (spells-beam.cpp disarm_trap, PROJECT_BEAM)."""
    here = ctx.here
    step = ((cell[0] > here[0]) - (cell[0] < here[0]), (cell[1] > here[1]) - (cell[1] < here[1]))
    ctx.battle.beam = (int(ctx.snapshot.turn), here, step)


def _settle_beam(ctx: _Ctx) -> None:
    """The board after the aimed answer: when the game printed KILL_TRAP's flash, the beam went
    off, and every trap on its line is gone (cave_alter_feat DISARM on each grid of the path, the
    hidden ones too: has_trap_at reads the terrain, not the mimic).  n1-c life-174 (2026-11-09):
    one beam from [1,18] destroyed the ten traps of [1,8]-[1,17] (「まばゆい閃光が走った！ <x10>」),
    the plan counted only [1,17] answered, and searched [1,10] for a trap that was gone until the
    loop guard stopped it."""
    battle = ctx.battle
    if battle.beam is None or ctx.snapshot.turn <= battle.beam[0]:
        return
    _turn, origin, step = battle.beam
    battle.beam = None
    if not any(message_text(message) in _FLASH_LINES for message in ctx.snapshot.messages):
        return
    terrain = ctx.open_terrain()
    bf = ctx.navigator.battlefield
    traps = {*bf.trap_cells, *bf.maybe_trap_cells}
    line = set()
    cell = tuple(origin)
    for _ in range(geo.MAX_SPELL_RANGE):
        cell = (cell[0] + step[0], cell[1] + step[1])
        if terrain.get(cell) not in geo.PROJECTING_KINDS:
            break
        line.add(cell)
    battle.cleared = battle.cleared | (line & traps)


# -- unseen immobile targets (owner 2026-11-09) ------------------------------------------
#
# Owner 2026-11-09 Q1 「見えない時は矢を撃たない。マスを狙う範囲の攻撃（取り込んだボール・ブレスなど）で
# 削り、無ければ相手が見えるマスへ移って撃つ。」 (the tome first), widened the same day 「Q25 の全部の段に
# 広げる」: every phase that shoots a never-moving target it may not see -- the Ipsissimus pen [7,17],
# the quylthulgs, the stairway to hell, the druj.  An unseen monster is hit at half the chance
# (shoot.cpp test_hit_fire with ``monster.ml`` false); an attack aimed at the grid (a ball or a
# breath, spells-launcher.cpp fire_ball drops PROJECT_STOP) or a beam along its ray needs no sight.


def _walk_to_sight(ctx: _Ctx, target, sights) -> str | None:
    """To the nearest cell of ``sights``; this cell is one of them and the target was not seen
    here: the line was there, the target was not (not this cell again)."""
    target = tuple(target)
    if ctx.here in sights:
        ctx.battle.blind_sights = ctx.battle.blind_sights | {(target, ctx.here)}
        sights = sights - {ctx.here}
    return _walk(ctx, sights, SIGHT_REASON)


def _unseen_fire(ctx: _Ctx, grid, race: int, *, seen: bool, piercing: bool = False,
                 among=None) -> str | None:
    """The strongest attack at ``grid``: the launcher too when the target is seen; unseen, an
    attack aimed at the grid or along a ray, else the walk to a cell that sees it (of ``among``,
    the phase's stands, when one does; else any)."""
    if seen:
        return _fire_at(ctx, grid, race, piercing=piercing)
    key = _fire_at(ctx, grid, race, piercing=piercing, missiles=False)
    if key is not None:
        return key
    return _walk_to_sight(ctx, grid, _sights(ctx, grid, among) or _sights(ctx, grid))
