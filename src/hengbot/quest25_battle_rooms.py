"""Quest 25's phase battle (quest25_battle): the phases beyond the hall.

The quylthulgs, the tome, the corpse masses, the dreadmaster, the sweep, the stairway and the druj:
the last seven rows of quest25_battle ``PHASES``.

Imports quest25_battle_board, _attack and _walk.

Split from quest25_battle.py (maintainability review 2026-11-23 (a)-8, behaviour unchanged).
"""

from __future__ import annotations

from typing import Callable

from hengbot import (
    attack_expectation, hunt_target, left_cells, me_capability, me_device_attacks, me_powers,
    quest25_druj_gear, quest25_geometry as geo, quest_exposure, quest_firing_cells, quest_plan_base,
    quest_room_light, quest_wait_placement,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.me_absorbed_substitutes import carry_cast_key
from hengbot.model import Position, SV_ROD_DETECTION, SV_STAFF_DETECT_EVIL, TVAL_ROD, TVAL_STAFF
from hengbot.policy_constants import FIXED_QUEST_TOUGHEST_KILL_TURNS, RANGED_MAX_DISTANCE, WAIT_KEY
from hengbot.quest_plan_base import HOLD_REASON
from hengbot.unseen_strike import message_text
from hengbot.quest25_battle_board import (
    _Ctx, _detection_failed, _IDLE_REASONS, _immobile_gone, _ipsissimus_alive, _placed, _seen_at, _sights,
    _TELEPORTED_LINES, _TELEPORTED_LINES_EN, BLOCKED_REASON, DETECT_REASON, ENGAGE_REASON, MASS_CELL_REASON,
    melee_is_fewer, MELT_REASON, RECHARGE_REST_LIMIT,
)
from hengbot.quest25_battle_attack import (
    _ball_powers, _balls, _breeders_in_line_key, _carried_grid_key, _engage, _fight_targets, _fire_at,
    _fire_options, _haste, _hold, _reaches_grid, _recharge_key,
)
from hengbot.quest25_battle_walk import (
    _damaged, _fire, _leave_fire, _open_key, _path, _refused, _step, _unseen_fire, _walk, _walk_to_sight,
    _withdraw,
)


# -- phase 3 to 5: the quylthulgs, the tome, the corpse masses, the dreadmaster -----------


def _quyl_plan(ctx: _Ctx):
    """(quyl cell, stand, centre) of the next quylthulg a ball catches from a safe stand; then,
    with balls that catch none from there (owner 2026-11-06 「加速して直接撃つ」), (quyl cell,
    None, None): it is shot directly from a cell with a line to it."""
    radii = sorted({row[1] for row in _balls(ctx, geo.QUYL)}, reverse=True)
    left = [cell for cell, race in ctx.navigator.battlefield.monster_placements
            if race == geo.QUYL and cell not in ctx.battle.quyls_done
            and geo.QUYL not in ctx.battle.absent]
    for cell in left:
        for radius in radii:
            for stand in geo.QUYL_STANDS:
                found = geo.ball_centre(ctx.terrain, stand, cell, radius)
                if found is not None:
                    return cell, stand, found[1]
    if radii and left:
        return left[0], None, None
    return None


def _quyl_line_cells(ctx: _Ctx, cell) -> set:
    """Dry cells with a line of fire to ``cell`` (the projection port), within a shot's reach."""
    return {spot for spot in geo.line_cells(ctx.terrain, cell)
            if ctx.terrain.get(spot) == "floor"
            and quest_exposure.game_distance(spot, cell) <= quest_exposure.MAX_SPELL_RANGE}


def _note_quyls(ctx: _Ctx) -> None:
    """A quylthulg seen off its cell has moved; one killed is done (in placement order)."""
    placed = [cell for cell, race in ctx.navigator.battlefield.monster_placements if race == geo.QUYL]
    seen = {(monster.position.y, monster.position.x) for monster in ctx.hostiles()
            if monster.race_id == geo.QUYL}
    done = set(ctx.battle.quyls_done)
    if seen - set(placed):
        done |= {cell for cell in placed if cell not in seen}
    ctx.battle.quyls_done = frozenset(done)


def _quyls_done(ctx: _Ctx) -> bool:
    _note_quyls(ctx)
    return _quyl_plan(ctx) is None and not _recharging_area_attack(ctx)


def _area_attack_held(ctx: _Ctx, race: int) -> bool:
    """An area attack on ``race`` the character holds whatever its charges now (``_held_against``)."""
    return _held_against(ctx, race, lambda power: power.shape in me_device_attacks.TARGETABLE_SHAPES)


def _held_against(ctx: _Ctx, race: int, reaches: Callable) -> bool:
    """An attack ``reaches`` admits that the character holds whatever its charges now -- an
    absorbed power (the Magic-Eater's wands regain charges and its rods recharge,
    hpmp/hp-mp-regenerator.cpp regenmagic, twice as fast resting) or a carried rod (it recharges)
    -- and that ``race``'s known flags do not cancel (me_device_attacks.expected_damage)."""
    policy, snapshot = ctx.policy, ctx.snapshot
    flags = me_device_attacks.race_id_flags(policy, race)
    for (kind, sval), power in me_device_attacks.POWERS.items():
        if (power.group_only or not reaches(power)
                or me_device_attacks.expected_damage(power, snapshot.player.level, flags) <= 0):
            continue
        if me_capability.has(policy, snapshot, kind, sval):
            return True
        if kind == "rod" and any(item.tval == TVAL_ROD and item.sval == sval and item.known
                                 for item in snapshot.inventory):
            return True
    return False


def _recharging_area_attack(ctx: _Ctx) -> bool:
    """A quylthulg is left and the area attack is only spent, not missing.

    n1-b life-378 (2026-11-13 01:45:05-01:45:14): from [5,2] the balls at [7,14] (for [9,13]) spent
    every charge -- the absorbed rods of Acid and Thunder Ball, the wands of Ice Ball, Acid Ball
    and Stinking Cloud -- and with no ball usable the phase counted as 「範囲攻撃が無ければ 1) を
    とばして」 and ended; the recharge rest that followed (the tome's preparation) refilled them.
    Owner 2026-11-13 「範囲攻撃がないというのは本当か？休憩すれば回復するとかでもなく？」: spent is
    not missing, so the phase rests to refill them (the 11-06 「攻撃に使うものを全快させる」 rest,
    ``_recharge_key``) and shoots again."""
    left = [cell for cell, race in ctx.navigator.battlefield.monster_placements
            if race == geo.QUYL and cell not in ctx.battle.quyls_done]
    return (bool(left) and ctx.kills(geo.QUYL) < geo.ROSTER[geo.QUYL]
            and not _balls(ctx, geo.QUYL) and _area_attack_held(ctx, geo.QUYL)
            and ctx.battle.recharge_rests < RECHARGE_REST_LIMIT)


_FACED = frozenset({geo.IPSISSIMUS, geo.DREADMASTER})


def _refill_key(ctx: _Ctx, *before: Callable[[], str | None]) -> str | None:
    """Spent, not missing: refill them (the between-phases rest, ``_recharge_key``), fighting
    what comes first; ``before``: the phase's own steps ahead of the rest, in order."""
    targets = _fight_targets(ctx)
    if targets:
        return _engage(ctx, targets) or _hold(ctx)
    for step in before:
        if (key := step()) is not None:
            return key
    return _recharge_key(ctx)


def _quyls(ctx: _Ctx, plan=None) -> str | None:
    plan = _quyl_plan(ctx) if plan is None else plan
    if plan is None:
        if not _recharging_area_attack(ctx):
            return None
        return _refill_key(ctx)
    # 「テレポート・アウェイを受けるとイプシシマスの残党やドリードマスターと相対する可能性がある。
    # その場合は加速して討伐を試みる。」
    faced = [monster for monster in ctx.seen_hostiles() if monster.race_id in _FACED]
    if faced:
        return _haste(ctx) or _engage(ctx, faced) or _hold(ctx)
    cell, stand, centre = plan
    ctx.battle.aimed_quyl = cell
    if stand is None:
        lines = _quyl_line_cells(ctx, cell)
        # Owner 2026-11-09 「Q25 の全部の段に広げる」 (``_unseen_fire``): unseen, no arrow; the ball at
        # its grid, else a cell of its line that sees it.
        seen = bool(_seen_at(ctx, geo.QUYL, {cell}))
        if not seen and not _fire_options(ctx, cell, geo.QUYL, missiles=False):
            return _walk_to_sight(ctx, cell, _sights(ctx, cell, lines))
        if ctx.here not in lines:
            return _walk(ctx, lines)   # 「飛ばされたら戻って撃ち直す」
        return _haste(ctx) or _unseen_fire(ctx, cell, geo.QUYL, seen=seen)
    if ctx.here != stand:
        return _walk(ctx, {stand})
    return _fire_at(ctx, centre, geo.QUYL, area_only=True, covers=cell)


def _tome(ctx: _Ctx) -> str | None:
    tome = next(cell for cell, race in ctx.navigator.battlefield.monster_placements if race == geo.TOME)
    for _damage, radius, _shape, _make in _balls(ctx, geo.TOME):
        for stand in geo.QUYL_STANDS:   # 「半径3の球を先に使う」: from out of its lines first
            found = geo.ball_centre(ctx.terrain, stand, tome, radius)
            if found is None:
                continue
            if ctx.here != stand:
                return _walk(ctx, {stand})
            return _haste(ctx) or _fire_at(ctx, found[1], geo.TOME, area_only=True, covers=tome)
    # Owner 2026-11-09 Q1 「見えない時は矢を撃たない。マスを狙う範囲の攻撃（取り込んだボール・ブレス
    # など）で削り、無ければ相手が見えるマスへ移って撃つ。」 and 「1に加え、倒しきれなければ下がる。
    # 生存を優先させたはず」 (「数行動で倒しきる見込みが無ければ、射線の外へ下がって休み、やり直す。」).
    # From [5,5] the tome is not in view (n1-c life-178: arrows at half the hit chance, ``geo.los``);
    # an attack aimed at its grid does not need the sight, the launcher does.  The plan with the
    # larger expected damage is taken: the near stands with the grid-aimed attacks, or a cell
    # that sees it with the launcher too.  Damaged, a plan that needs more actions than the
    # quest's kill horizon (FIXED_QUEST_TOUGHEST_KILL_TURNS) withdraws out of the fire and rests.
    seen = any(monster.race_id == geo.TOME for monster in ctx.seen_hostiles())
    hp = _tome_hp(ctx)
    stands = [stand for stand in geo.TOME_NEAR_STANDS if _path(ctx, {stand}) or ctx.here == stand]
    near = _near_damage(ctx, tome, stands)
    sights = _sights(ctx, tome)
    far = 0.0
    if sights:
        distance = min(quest_exposure.game_distance(cell, tome) for cell in sights)
        far = max(near, attack_expectation.launcher_against(ctx.policy, ctx.snapshot, geo.TOME, distance))
    if stands and near > 0 and near >= far:
        if _hopeless(ctx, hp, near):
            return _withdraw(ctx)
        if ctx.here not in stands:
            return _walk(ctx, {stands[0]})
        return _haste(ctx) or _fire_at(ctx, tome, geo.TOME, missiles=seen)
    if far <= 0:
        return _tome_unarmed(ctx, tome)
    if _hopeless(ctx, hp, far):
        return _withdraw(ctx)
    if seen:
        return _haste(ctx) or _fire_at(ctx, tome, geo.TOME)
    return _walk_to_sight(ctx, tome, sights)


def _near_damage(ctx: _Ctx, tome, stands) -> float:
    """The near plan's damage: the strongest grid-aimed attack at the tome from one of the near
    ``stands`` -- a ball or a breath from any of them, a beam only along a stand's own ray
    (``_fire_options`` ``origin``) -- never one that only the player's present cell has.

    n1-c life-222 (2026-11-25 00:30, decisions 41220-41234): the balls spent, the near value was
    the bolt-or-beam along the ray from where the player stood; on [4,8] and [5,8] the ray down
    column 8 reaches [9,8] (33 a use against the launcher's 29 in the replay), so the near plan won and walked
    toward [5,5]; one step west, on [4,7] or [5,7], no ray reached it, the far plan won and walked
    to a sight back east.  The two walks alternated every board to ``livelock:exhausted``.  No near
    stand has a ray to [9,8], and the near plan's attack is made from its stand, so a ray of the
    present cell is not the near plan's."""
    if not stands:   # no stand to weigh a ray from: the balls and breaths alone (no ray needed)
        return max((row[0] for row in _ball_powers(ctx, geo.TOME, tome)), default=0.0)
    return max((damage for stand in stands
                for damage, _make in _fire_options(ctx, tome, geo.TOME, missiles=False, origin=stand)),
               default=0.0)


def _tome_unarmed(ctx: _Ctx, tome) -> str | None:
    """No attack reaches the tome and it may still be there (cells that see it are left).

    Owner 2026-11-13 (the open question of n1-b life-382): 「休んで充填を待つ。また、可能なら感知して
    存在を確認する。」  Out of the casters' fire first (the formation's 「クイル・破壊集大成・ドルジの
    射線のマスでは待たず、休まない」), a detection that shows its race from where it reaches the
    tome's grid (``_confirm_tome_key``; one not showing it there ends the phase, ``_tome_absent``),
    then the between-phases rest (``_recharge_key``) until a charge is back and the phase's attack
    answers again."""
    return _refill_key(ctx, lambda: _leave_fire(ctx), lambda: _confirm_tome_key(ctx, tome))


def _confirm_tome_key(ctx: _Ctx, tome) -> str | None:
    """「可能なら感知して存在を確認する」: once per phase until it shows the tome (a cast that failed
    is cast again), the sweep's detection (``_detect_key``) when its effect shows the tome's race
    (hunt_target.REVEALS: the Rod of Detection every monster, Detect Evil the evil; 557 is EVIL)
    and the tome's grid is within its reach (spells-detection.cpp detect_monsters_*:
    Grid::calc_distance to the player within DETECT_RAD_DEFAULT)."""
    battle = ctx.battle
    if battle.tome_shown or battle.tome_detect is not None:
        return None
    found = _detector(ctx)
    if found is None or quest_exposure.game_distance(ctx.here, tuple(tome)) > me_powers.DETECT_RAD:
        return None
    effect = (found[1] if found[0] == "power"
              else me_powers.BY_KEY[(found[1], found[2].sval)]).effect
    if not hunt_target.REVEALS[effect](hunt_target.race_flags(ctx.policy, geo.TOME)):
        return None
    key = _detect_key(ctx)
    if key is not None:
        battle.tome_detect = int(ctx.snapshot.turn)
    return key


# The health bar's length (system/monster-entity.cpp get_hp_bar_data: clamp(percent / 10 + 1, 1, 10))
# bounds the percent from above: 10 * length - 1 below the full bar.
def _bar_percent(length: int) -> int:
    return 100 if length >= 10 else max(1, 10 * int(length) - 1)


def _note_tome_health(ctx: _Ctx) -> None:
    """Owner 2026-11-09 「見えた傷の具合で見込む」: the tome's HP from its health when seen -- the
    board's band (bot-json-output.cpp monster_health_band: unhurt ... almost dead, MonsterState
    ``hp`` its upper bound on the race's maximum) and, when the health bar tracks it, the bar's
    length -- the lower of the two; kept while it is not seen."""
    for monster in ctx.seen_hostiles():
        if monster.race_id != geo.TOME:
            continue
        hp = monster.hp
        bar = ctx.snapshot.health_bar
        if bar is not None and bar[0] and bar[1] == monster.index and bar[2] is not None:
            hp = min(hp, max(1, (monster.max_hp * _bar_percent(bar[2]) + 99) // 100))
        ctx.battle.tome_hp = int(hp)
        return


def _tome_hp(ctx: _Ctx) -> float:
    """The tome's HP for the kill estimate: its last seen health (``_note_tome_health``), else
    (never seen) the race's maximum (owner 2026-11-09 「見えていなければ最後に見えた状態、一度も見えて
    いなければ最大の500」: 50d10)."""
    if ctx.battle.tome_hp is not None:
        return float(ctx.battle.tome_hp)
    knowledge = attack_expectation.race_knowledge(ctx.policy, geo.TOME)
    return float(knowledge.max_hp) if knowledge is not None else 0.0


def _hopeless(ctx: _Ctx, hit_points: float, per_action: float) -> bool:
    return _damaged(ctx) and attack_expectation.actions_to_kill(
        hit_points, per_action) > FIXED_QUEST_TOUGHEST_KILL_TURNS


def _masses_seen(ctx: _Ctx) -> list:
    return [monster for monster in ctx.hostiles() if monster.race_id == geo.MASS]


def _mass_reached(ctx: _Ctx, cell, monster) -> bool:
    """A shot from ``cell`` reaches ``monster`` (quest_firing_cells ``reach``: two grids or more away,
    the player's bolt path ends on it before a grid that stops it)."""
    return quest_firing_cells.reach(ctx.policy, ctx.snapshot, Position(*cell), [monster]) == 1


def _phase_masses(ctx: _Ctx) -> list:
    """The masses phase 4 is for (owner 2026-11-06 「北の通路に移動して増えている死体の塊を処理する」,
    phase6_sweep 「[1,6] から見て通路に1体もいないことで判定して良い」): those in the north corridor, and
    those a shot reaches from here or from a cell the plan may stand on (``_mass_stand_cells``).

    n1-b life-399 (2026-11-15 16:47): the masses had bred into the east room ([2,19]-[2,25],
    [1,26], [1,27]), seen through the open door [1,18] along row 1; no cell out of the dreadmaster's
    vision reaches them, and from [1,7] the bolt's path to [2,20] ends on the wall [2,18].  The
    phase shot arrows at [2,20] 36 times with no hit or miss line until the loop guard stopped it."""
    masses = _masses_seen(ctx)
    if not masses:
        return []
    stands = {ctx.here} | _mass_stand_cells(ctx, masses)
    return [monster for monster in masses
            if (monster.position.y, monster.position.x) in geo.NORTH_CORRIDOR
            or any(_mass_reached(ctx, cell, monster) for cell in stands)]


def _masses_done(ctx: _Ctx) -> bool:
    if geo.MASS in ctx.battle.absent:
        return True   # none left on the floor (quest25_presence)
    return (ctx.here == geo.MASS_STAND and not ctx.door_closed(geo.MASS_DOOR) and ctx.battle.lit
            and not _phase_masses(ctx))


def _masses(ctx: _Ctx) -> str | None:
    opening = ctx.door_closed(geo.MASS_DOOR) or not ctx.battle.lit
    if opening and ctx.here != geo.MASS_STAND:
        return _walk(ctx, {geo.MASS_STAND})
    if ctx.door_closed(geo.MASS_DOOR):
        door = geo.MASS_DOOR
        return _open_key(ctx, door)
    if not ctx.battle.lit:
        ctx.battle.lit = True
        light = quest_room_light.light_room_key(
            ctx.policy, ctx.snapshot, ctx.navigator, ctx.open_terrain(), quest_room_light.LIGHT_REASON)
        if light is not None:
            return light
    if (key := _walk_to_widest(ctx)) is not None:
        return key
    if (key := _breeders_in_line_key(ctx)) is not None:
        return key   # owner 2026-11-08: the aim with the most kills when it catches two or more
    for monster in sorted(_masses_seen(ctx), key=lambda each: each.distance):
        if not _mass_reached(ctx, ctx.here, monster):
            continue   # its shot ends on a wall short of it (``_phase_masses``)
        key = _fire_at(ctx, (monster.position.y, monster.position.x), geo.MASS)
        if key is not None:
            return key
    if ctx.here != geo.MASS_STAND:
        return _walk(ctx, {geo.MASS_STAND})   # none to shoot from here: the plan's cell looks again
    return None


def _mass_firing_cells(ctx: _Ctx, *, dread_range: bool = False) -> dict:
    """reach -> the cells a shot at the masses in view reaches that many from (owner 2026-11-09
    「一番多く届く位置へ」, quest_firing_cells ``reach``, the Q2 fix's measure), of the cells the plan
    may stand on: floor through the doors as the board shows them, no trap not answered, out of
    the casters' fire (``_fire``: the tome, the quylthulgs, the druj), out of the summons while the
    Ipsissimus live, out of the dreadmaster's vision while it lives (phase4 「[1,6] には罠が無く、
    ドリードマスターの感知範囲の外で、召喚も受けない」), not beside a mass (they drain by touch) nor on a
    monster.  The plan's [1,6] is one of them."""
    masses = _masses_seen(ctx)
    if not masses:
        return {}
    cells = {Position(*cell) for cell in _mass_stand_cells(ctx, masses, dread_range=dread_range)}
    by_reach: dict = {}
    for cell in cells:
        count = quest_firing_cells.reach(ctx.policy, ctx.snapshot, cell, masses)
        if count:
            by_reach.setdefault(count, set()).add((cell.y, cell.x))
    return by_reach


def _mass_stand_cells(ctx: _Ctx, masses, *, dread_range: bool = False) -> set:
    """The cells ``_mass_firing_cells`` may shoot the masses from (its docstring), (y, x) each.
    ``dread_range``: the dreadmaster's sensing range is not shunned (owner 2026-11-19 「ドリード
    マスターを優先撃破する決まりのとき、邪魔なら死体の塊を倒して良い」)."""
    bf = ctx.navigator.battlefield
    avoid = set(_fire(ctx)) | {cell for cell in (*bf.trap_cells, *bf.maybe_trap_cells)
                               if cell not in ctx.battle.cleared}
    if _ipsissimus_alive(ctx):
        avoid |= geo.summon_cells(ctx.terrain)
    if not _dreadmaster_done(ctx) and not dread_range:
        dreadmaster = next((cell for cell, race in bf.monster_placements if race == geo.DREADMASTER), None)
        if dreadmaster is not None:
            avoid |= geo.vision_cells(ctx.terrain, dreadmaster, geo.DREADMASTER_VISION)
    occupied = {(monster.position.y, monster.position.x) for monster in ctx.hostiles()}
    near = {cell for cell, kind in ctx.open_terrain().items() if kind == "floor"
            and any(quest_exposure.game_distance(cell, (monster.position.y, monster.position.x))
                    <= RANGED_MAX_DISTANCE for monster in masses)}
    cells = {Position(*cell) for cell in near - avoid - occupied}
    cells -= quest_firing_cells.touching_cells(ctx.policy, ctx.snapshot, cells)
    return {(cell.y, cell.x) for cell in cells}


def _walk_to_widest(ctx: _Ctx, *, dread_range: bool = False) -> str | None:
    """To the cells that reach the most masses (``_mass_firing_cells``), the most first among the
    reachable; None when no cell reaches more than this one (a cell the plan may not stand on
    reaches none) or none that does can be walked to."""
    by_reach = _mass_firing_cells(ctx, dread_range=dread_range)
    here = next((count for count, cells in by_reach.items() if ctx.here in cells), 0)
    for count in sorted(by_reach, reverse=True):
        if count <= here:
            return None
        if (key := _walk(ctx, by_reach[count], MASS_CELL_REASON)) is not None:
            return key
    return None


def _dreadmaster_done(ctx: _Ctx) -> bool:
    return ctx.kills(geo.DREADMASTER) >= geo.ROSTER[geo.DREADMASTER]


def _dread_vision(ctx: _Ctx) -> set:
    """The cells within the living dreadmaster's sensing range (phase4's 「感知範囲」), else empty."""
    if _dreadmaster_done(ctx):
        return set()
    dreadmaster = _placed(ctx, geo.DREADMASTER)
    if dreadmaster is None:
        return set()
    return set(geo.vision_cells(ctx.terrain, dreadmaster, geo.DREADMASTER_VISION))


def _teleported(ctx: _Ctx) -> bool:
    """This board says a monster moved the player (``_TELEPORTED_LINES``)."""
    for message in ctx.snapshot.messages:
        text = message_text(message)
        if text.endswith(_TELEPORTED_LINES) or any(line in text for line in _TELEPORTED_LINES_EN):
            return True
    return False


def _note_dread_teleport(ctx: _Ctx) -> None:
    """Owner 2026-11-19: a monster's teleport that leaves the player in the living dreadmaster's
    sensing range makes killing it the plan's first step (``_teleported_dreadmaster_key``)."""
    if _teleported(ctx) and ctx.here in _dread_vision(ctx):
        ctx.battle.dread_teleported = True


def _teleported_dreadmaster_key(ctx: _Ctx) -> str | None:
    """Owner 2026-11-19 「テレポートで飛ばされてドリードマスターの感知範囲内に行ってしまったら優先して
    ドリードマスターを倒す」: the dreadmaster phase's fight (``_dreadmaster``: haste, the engage, its
    stand) ahead of the running phase, until it is dead or the player is out of its range; the
    phase's own order then goes on.  The survival rungs above the plan still come first.

    n1-c life-217 (2026-11-19 05:24): the nexus quylthulg teleported the Lv38 Magic-Eater into the
    east room, inside the dreadmaster's range; the way back west, [1,18], was a corpse mass every
    line to which lay in that range too (phase4 shoots masses only from outside it), and the tome's
    phase had no step: 32 ``quest:blocked:execute`` waits to the loop guard."""
    battle = ctx.battle
    if not battle.dread_teleported:
        return None
    if ctx.here not in _dread_vision(ctx):
        battle.dread_teleported, battle.dread_style = False, None
        return None
    style, battle.style = battle.style, battle.dread_style
    try:
        key = _dreadmaster(ctx)
    finally:
        battle.dread_style, battle.style = battle.style, style
    if key is not None and ctx.policy.last_reason in _IDLE_REASONS:
        # Walking to its stand or holding there, the breeders in line are shot first (owner
        # 2026-11-08 「射線にいれば範囲で撃つ」, as the phases' own walks and waits, ``_act``).
        reason = ctx.policy.last_reason
        if (shot := _breeders_in_line_key(ctx)) is not None:
            return shot
        if reason == HOLD_REASON and battle.no_way == ctx.here:
            # Owner 2026-11-19 「ドリードマスターを優先撃破する決まりのとき、邪魔なら死体の塊を倒して
            # 良い」: the way to its stand is shut (a mass on it): to the cell that reaches the most
            # masses in view, its sensing range not shunned (phase4's rule yields here); the shot
            # above then opens the way.  n1-c life-217's restart (2026-11-19 05:59): [1,18] shut
            # the corridor and the fight held on [8,20].
            if (walk := _walk_to_widest(ctx, dread_range=True)) is not None:
                return walk
        ctx.policy.last_reason = reason
    return key


def _dreadmaster(ctx: _Ctx) -> str | None:
    battle = ctx.battle
    if battle.style is None:
        battle.style = "melee" if melee_is_fewer(ctx.policy, ctx.snapshot, geo.DREADMASTER) else "ranged"
    targets = _fight_targets(ctx)
    if any(monster.race_id == geo.DREADMASTER for monster in targets):
        if (haste := _haste(ctx)) is not None:
            return haste     # 「どちらにせよ戦闘時は加速する」
    if (key := _engage(ctx, targets) if (battle.style == "ranged" or any(
            monster.distance <= 1 for monster in targets)) else None) is not None:
        return key
    stand = _dread_wait_cell(ctx)
    if stand is None:
        return None
    return (_walk(ctx, {stand}) if ctx.here != stand else None) or _hold(ctx)


def _dread_wait_cell(ctx: _Ctx):
    """Where phase 5 waits for the dreadmaster, both styles.

    Owner 2026-11-22 (it replaces 2026-11-06 「感知範囲ギリギリで待つ。近接なら17,1で待機」): 「敵の行動
    アルゴリズムを確認して待つ場所を精査する必要がある。立ち位置が悪いと幾ら待っても来ない」, and for phase 5
    the east big room, on the cells its deterministic movement brings it to ([1,19]-[1,22],
    [2,19]-[2,22], [7,21]-[8,25] ...), chosen by the existing rules.  The movement is
    quest_wait_placement's (``come_cells``: the flow, get_moves_val, PASS_WALL through doors but not
    the permanent inner walls); from [1,17], [1,9] and [2,9] it goes back and forth and only its
    random moves (RAND_25) bring it (n1-b life-413: about 9,650 game turns on [1,17]).

    The room's cells out of the plan's refusals (an uncleared or possible trap, the never-moving
    casters' fire, the Ipsissimus' summon cells while they live, a refused or occupied cell), the
    nearest to the room's door [1,18] first (the walk in from the north corridor); the first the
    dreadmaster comes to, else the first of them (the map says it comes there)."""
    bf = ctx.navigator.battlefield
    traps = {cell for cell in (*bf.trap_cells, *bf.maybe_trap_cells) if cell not in ctx.battle.cleared}
    unsafe = (traps | set(_fire(ctx)) | set(_refused(ctx)) | set(left_cells.refused_yx(ctx.policy, ctx.snapshot))
              | {(monster.position.y, monster.position.x) for monster in ctx.hostiles()})
    if _ipsissimus_alive(ctx):
        unsafe |= geo.summon_cells(ctx.terrain)
    cells = sorted((quest_exposure.game_distance(cell, geo.EAST_ROOM_DOOR), cell)
                   for cell in geo.east_room_cells(ctx.terrain)
                   if ctx.terrain.get(cell) == "floor" and cell not in unsafe)
    if not cells:
        return None
    ordered = [cell for _distance, cell in cells]
    seen = next((monster for monster in ctx.hostiles() if monster.race_id == geo.DREADMASTER), None)
    origin = ((seen.position.y, seen.position.x) if seen is not None else _placed(ctx, geo.DREADMASTER))
    if origin is None:
        return ordered[0]
    come = quest_wait_placement.will_come(ctx.policy, ctx.snapshot, ctx.navigator, geo.DREADMASTER,
                                          origin, ordered, seen, first=True)
    return come[0] if come else ordered[0]


# -- phase 6: the sweep -----------------------------------------------------------------


_SWEPT_RACES = tuple(race for race in geo.ROSTER if race not in {geo.DRUJ, geo.STAIRWAY, geo.MASS})


def _short(ctx: _Ctx) -> bool:
    return any(ctx.kills(race) < geo.ROSTER[race] for race in _SWEPT_RACES)


def _detector(ctx: _Ctx):
    """「感知が使えるなら」: the absorbed Rod of Detection or Staff of Detect Evil with a charge
    (("power", row)), else a carried one (("item", verb, item)); None without one."""
    policy, snapshot = ctx.policy, ctx.snapshot
    if me_device_attacks.can_use_powers(snapshot):
        for ident in (("rod", SV_ROD_DETECTION), ("staff", SV_STAFF_DETECT_EVIL)):
            if (me_capability.has(policy, snapshot, *ident)
                    and me_capability.charges(policy, snapshot, *ident) > 0):
                return ("power", me_powers.BY_KEY[ident])
    if snapshot.player.blind or snapshot.player.confused:
        return None
    for tval, sval, verb in ((TVAL_ROD, SV_ROD_DETECTION, "rod"),
                             (TVAL_STAFF, SV_STAFF_DETECT_EVIL, "staff")):
        item = next((item for item in snapshot.inventory if item.tval == tval and item.sval == sval
                     and item.known and not item.charging and (tval == TVAL_ROD or item.charges > 0)),
                    None)
        if item is not None:
            return ("item", verb, item)
    return None


def _detect_key(ctx: _Ctx, reason: str = DETECT_REASON) -> str | None:
    """The plan's detection (``_detector``) under ``reason``; the next board reads what it showed
    (quest25_presence ``note_cast``)."""
    from hengbot import quest25_presence

    found = _detector(ctx)
    if found is None:
        return None
    effect = quest25_presence.detector_effect(found)
    if found[0] == "power":
        ctx.policy.last_reason = f"{reason}:{effect}"
        key = found[1].key
    else:
        key = reserved_item_command(ctx.policy, ctx.snapshot, found[1], found[2])
        if key is not None:
            ctx.policy.last_reason = reason
    if key is not None:
        quest25_presence.note_cast(ctx, effect)
    return key


def _sweep_targets(ctx: _Ctx) -> list:
    return [monster for monster in ctx.hostiles()
            if monster.race_id not in {geo.DRUJ, geo.STAIRWAY}]


def _sweep_done(ctx: _Ctx) -> bool:
    battle = ctx.battle
    if _sweep_targets(ctx):
        return False
    if battle.detected is not None:
        return not battle.detected
    if battle.detect_turn < 0 and _detector(ctx) is not None:
        return False
    return not _short(ctx)


def _around(cell) -> set:
    """``cell`` and the 8 cells beside it (a goal reached within one step of a monster's cell)."""
    return {(cell[0] + dy, cell[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)}


def _sweep_reachable(ctx: _Ctx, cell) -> bool:
    """A walk reaches ``cell`` or a cell beside it (``_path``), or the player stands beside it.

    n1-c life-211 (2026-11-15 09:25): the sweep's detection showed the two Nexus quylthulgs on
    [7,4] -- the sealed pocket of the map's 『Z』 (rows 6-9, columns 2-5: permanent walls and the
    granite [9,3]) -- and on [1,15].  The sweep walked toward [7,4] only, the first one shown, found
    no way and held for eleven minutes; the quylthulg on [1,15] was never gone for.

    The cell the pocket's plan is opening (``battle.pocket``, quest25_pocket) is no reach: once its
    granite is melted a walk would reach it, and the sweep would walk beside it and look again
    while the shot is the plan's (n1-b life-416 2026-11-23: the quylthulg on [8,3], shot from the
    melted [9,3] beside it)."""
    if ctx.battle.pocket is not None and tuple(cell) == tuple(ctx.battle.pocket[0]):
        return False
    if quest_exposure.game_distance(ctx.here, cell) <= 1:
        return True
    return len(_path(ctx, _around(cell) - {ctx.here})) >= 2


def _sweep(ctx: _Ctx, *, patrol: bool = False) -> str | None:
    """``patrol``: the round is walked whatever the kill count says (``_after_the_phases``)."""
    battle = ctx.battle
    targets = _sweep_targets(ctx)
    if battle.detect_turn >= 0 and battle.detected is None:
        if _detection_failed(ctx):
            # n1-b life-378 (01:45:48): 「呪文をうまく唱えられなかった！」 was read as a detection that
            # showed nothing, and the sweep ended with both quylthulgs alive.  Cast again.
            battle.detect_turn = -1
        else:
            battle.detected = tuple((monster.position.y, monster.position.x) for monster in targets)
    if targets:
        visible = [monster for monster in targets if monster.perception != "detected"]
        if (key := _engage(ctx, visible)) is not None:
            return key
        # The nearest one a walk reaches (``_sweep_reachable``); one in a sealed pocket is no goal.
        cells = [(monster.position.y, monster.position.x)
                 for monster in sorted(targets, key=lambda monster: monster.distance)]
        reachable = [cell for cell in cells if _sweep_reachable(ctx, cell)]
        if reachable:
            return _walk(ctx, _around(reachable[0]) - {reachable[0]}) or _hold(ctx)
    if battle.detected:
        # What the detection showed is gone from sight: walk where it was, the nearest cell a walk
        # reaches first, then look again (that cell is forgotten, the detection cast again).
        reachable = sorted((cell for cell in battle.detected if _sweep_reachable(ctx, cell)),
                           key=lambda cell: quest_exposure.game_distance(ctx.here, cell))
        if not reachable:
            # Only sealed cells are left (n1-c life-211, 2026-11-15: [7,4]): the owner's
            # 「溶かして撃つ・無ければ帰還」 (quest25_pocket); a cell no melt opens, a named stop.  A
            # cell the pocket's shots say is empty is forgotten, and the detection comes next.
            from hengbot import quest25_pocket

            key = quest25_pocket.key(ctx, battle.detected)
            if key is not None:
                return key
            if battle.detected and all(quest25_pocket.plan(ctx, cell) is None for cell in battle.detected):
                # n1-b life-416 (2026-11-23): no wall of the map opens a line to any of them --
                # the hold had no end (owner 2026-11-19 「来ないなら待ち続けない」): a named stop.
                return quest25_pocket.no_line_key(ctx)
            if battle.detected:
                return _hold(ctx)
        else:
            cell = reachable[0]
            if quest_exposure.game_distance(ctx.here, cell) > 1:
                return _walk(ctx, _around(cell)) or _hold(ctx)
            left = tuple(spot for spot in battle.detected if spot != cell)
            battle.detected, battle.detect_turn = (left or None), -1
    if battle.detect_turn < 0 and (detect := _detect_key(ctx)) is not None:
        battle.detect_turn = ctx.snapshot.turn
        return detect
    if not _short(ctx) and not patrol:
        return None
    # 「撃破カウントに不足があれば巡回して探す」: the room sweep's stands as the round.
    stands = ctx.profile.engagement_plan["room_sweep"]["stands"]
    if battle.patrol_round >= int(ctx.profile.engagement_plan["room_sweep"]["max_rounds"]):
        ctx.policy.last_reason = BLOCKED_REASON
        return WAIT_KEY
    goal = tuple(stands[battle.patrol_stage]["cell"])
    if ctx.here == goal or not _path(ctx, {goal}):
        battle.patrol_stage += 1
        if battle.patrol_stage >= len(stands):
            battle.patrol_stage, battle.patrol_round = 0, battle.patrol_round + 1
        return _hold(ctx)
    return _walk(ctx, {goal})


# -- phase 6 and 7: the stairway and the druj --------------------------------------------


def _stairway_done(ctx: _Ctx) -> bool:
    return ctx.kills(geo.STAIRWAY) >= geo.ROSTER[geo.STAIRWAY] or _immobile_gone(ctx, geo.STAIRWAY)


def _stairway(ctx: _Ctx) -> str | None:
    battle = ctx.battle
    stairway = next(cell for cell, race in ctx.navigator.battlefield.monster_placements
                    if race == geo.STAIRWAY)
    door, stand = geo.STAIRWAY_DOOR, geo.STAIRWAY_STAND
    if battle.style is None:
        battle.style = ("melee" if melee_is_fewer(ctx.policy, ctx.snapshot, geo.STAIRWAY, steps=1)
                        else "ranged")
    if ctx.here not in {stand, door} and not _stands_looked_from(ctx, stairway, door, stand):
        return _walk(ctx, {stand})
    if ctx.here == stand and ctx.door_closed(door) and (haste := _haste(ctx)) is not None:
        return haste      # 「全快し、加速して階段の前の扉を開ける」
    if ctx.door_closed(door):
        return _open_key(ctx, door)
    seen = [monster for monster in ctx.seen_hostiles() if monster.race_id == geo.STAIRWAY]
    if battle.style == "melee":
        if ctx.here != door:
            return _step(ctx, door, ENGAGE_REASON)
        if seen:
            return _engage(ctx, seen)
        return quest_plan_base.plan_walk(ctx.policy, ctx.snapshot, stairway)
    # Owner 2026-11-09 「Q25 の全部の段に広げる」 (``_unseen_fire``): unseen from [13,27], no arrow; the
    # door [13,28] beside it when nothing is aimed at the grid.
    if (rest := _stairway_spent(ctx, stairway, bool(seen))) is not None:
        return rest
    return _unseen_fire(ctx, stairway, geo.STAIRWAY, seen=bool(seen), among={stand, door})


def _stairway_spent(ctx: _Ctx, stairway, seen: bool) -> str | None:
    """No attack that hurts the stairway is ready, one is held: the refill rest (``_refill_key``).

    Owner 2026-11-13 「休んで充填を待つ」 (the tome's ``_tome_unarmed``) with 2026-11-12 「射撃と
    取り込んだ魔法道具は常に期待値で比べて高い方（耐性・命中率・成功率まで）」: the stairway to hell
    (lib/edit MonraceDefinitions 439) is immune to acid, lightning, fire and poison and the weak
    light leaves it unhurt (``attack_expectation.effective``), so with its cold and missiles spent
    none of those is fired; the rest refills what does hurt it.  n1-b life-384 (2026-11-13
    08:30-08:42): from [13,27] 235 uses at it, the cold 28 and the Magic Missile 6 of them.  None
    (the walk to a sight, ``_unseen_fire``) when nothing hurting it is held or the rest is refused."""
    if _fire_options(ctx, stairway, geo.STAIRWAY, missiles=seen):
        return None
    if not _held_against(ctx, geo.STAIRWAY, _reaches_grid):
        return None
    return _refill_key(ctx)


def _stands_looked_from(ctx: _Ctx, stairway, door, stand) -> bool:
    """The door is open and both stands were reached with the stairway unseen: the walk to
    another cell that sees it owns the move (``_unseen_fire``'s 「撃つマスは段の立ち位置の中から選び、
    無ければどこでもよい」), not the walk back to the stand.

    n1-b life-384 (2026-11-13 08:42, Quest 25 phase 9): every attack spent, [13,27] and [13,28]
    reached unseen, the walk to a sight stepped '7' to [12,26] and this phase's own approach
    stepped '3' back to [13,27], board after board, until the loop guard stopped the bot three
    times."""
    return (ctx.battle.style == "ranged" and not ctx.door_closed(door)
            and not _sights(ctx, stairway, {stand, door}))


def _melt_key(ctx: _Ctx, grid) -> str | None:
    """Stone to Mud aimed at ``grid``: the absorbed power, else a carried wand."""
    cast = carry_cast_key(ctx.policy, ctx.snapshot, "utility_tools", "wall_breach",
                          direction=f"@{grid[0]},{grid[1]}")
    if cast is not None:
        ctx.policy.last_reason = MELT_REASON
        return cast
    wand = ctx.policy._stone_to_mud_wand(ctx.snapshot)
    return None if wand is None else _carried_grid_key(ctx, "wand", wand, grid)


def _can_melt(ctx: _Ctx) -> bool:
    return (carry_cast_key(ctx.policy, ctx.snapshot, "utility_tools", "wall_breach", direction="@0,0")
            is not None or ctx.policy._stone_to_mud_wand(ctx.snapshot) is not None)


def _druj(ctx: _Ctx) -> str | None:
    battle, druj = ctx.battle, next(cell for cell, race in ctx.navigator.battlefield.monster_placements
                                    if race == geo.DRUJ)
    # 「反テレポート付きで他のデメリットがない装備…この戦闘でのみ使用する」
    worn = quest25_druj_gear.wear_key(ctx.policy, ctx.snapshot, ctx.profile)
    if worn is not None:
        return worn
    door = geo.DRUJ_DOOR
    grid = ctx.snapshot.grid_at(Position(*door))
    if grid is not None and grid.known and not grid.is_door:
        battle.melted = True     # Stone to Mud leaves floor (effect-feature.cpp KILL_WALL)
    lines = geo.line_cells(ctx.open_terrain(), druj)
    # 「魔道具術師は加速する」 out of the druj's line only (「眼の前で欠け直すわけではない」).
    if (ctx.snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER and ctx.here not in lines
            and (haste := _haste(ctx)) is not None):
        return haste
    # The door already open (not melted) needs no melt: [13,20] is out of the druj's line either
    # way and the ball aimed at [11,19] reaches [11,18] (owner 2026-11-23 「立ち位置を守れば一切の
    # 反撃を受けずに倒せた」; n1-c life-221 fought it from its line [12,24] with the door open).
    opened = battle.melted or not ctx.door_closed(door)
    if _balls(ctx, geo.DRUJ) and (opened or _can_melt(ctx)):
        # 「ドアを開けずに13,20に移動して、11,19を岩石溶解して11,19に範囲攻撃を撃つ」
        if ctx.here != geo.DRUJ_AREA_STAND:
            return _walk(ctx, {geo.DRUJ_AREA_STAND})
        if not opened:
            return _melt_key(ctx, door)
        # Nothing charged: the refill rest on the stand, not a shot from elsewhere.
        return (_fire_at(ctx, door, geo.DRUJ, area_only=True) or _refill_key(ctx) or _hold(ctx))
    if ctx.door_closed(door):
        if quest_exposure.game_distance(ctx.here, door) <= 1:
            return _open_key(ctx, door)
        beside = {(door[0] + dy, door[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
        return _walk(ctx, {cell for cell in beside if ctx.terrain.get(cell) == "floor"})
    trapless = sorted(cell for cell in lines if ctx.terrain.get(cell) == "floor"
                      and cell not in ctx.navigator.battlefield.trap_cells)
    if ctx.here not in trapless:
        return _walk(ctx, set(trapless)) or _hold(ctx)
    # Owner 2026-11-09 「Q25 の全部の段に広げる」 (``_unseen_fire``): unseen, no arrow; a trapless cell
    # of its line that sees it when nothing is aimed at the grid.
    return _unseen_fire(ctx, druj, geo.DRUJ, seen=bool(_seen_at(ctx, geo.DRUJ, {druj})), among=trapless)
