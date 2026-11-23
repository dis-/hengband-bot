"""Quest 25's phase battle (quest25_battle): the attacks and the rests between the phases.

The attack aimed at a grid or a target (``_fire_options``: every row me_device_attacks.use_value's),
the blow and the haste of a fight (``_engage``), the corpse mass beside and the breeders in the line
of fire every phase answers (``_adjacent_mass_key``, ``_breeders_in_line_key``), and the preparation
between the phases: the counted rests that recharge the attacks and the rest to full HP (``_prepare``).

Imports quest25_battle_board only.

Split from quest25_battle.py (maintainability review 2026-11-23 (a)-8, behaviour unchanged).
"""

from __future__ import annotations

from typing import Callable

from hengbot import (
    attack_expectation, breeder_area_attack, combat_answer, me_capability, me_device_attacks, me_powers,
    me_powers_refresh, quest25_geometry as geo, quest_exposure, quest_plan_base, speed_dose, summon_response,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import Position, TVAL_ROD, TVAL_WAND, UNKNOWN_MONSTER_HP
from hengbot.policy_constants import WAIT_KEY
from hengbot.quest_plan_base import HOLD_REASON, MELEE_REASON
from hengbot.quest25_battle_board import (
    _Ctx, _LATER_IMMOBILE, FULL_HP_REASON, FULL_HP_REST_KEY, HASTE_REASON, RECHARGE_REASON,
    RECHARGE_REST_KEY, RECHARGE_REST_LIMIT, REST_CUT_GAME_TURNS, SHOT_REASON,
)


# -- attacks ----------------------------------------------------------------------------


def _target_hp(ctx: _Ctx, race: int, grid=None) -> int | None:
    """The hit points a shot at ``race`` (on ``grid``) can take: the board's estimate of a monster
    of that race on the grid (model ``_estimated_monster_hp``: its race's maximum scaled by its
    health), else the race's maximum (an unseen target: the stairway to hell, 15d8 FORCE_MAXHP,
    is 120), else None (an unknown race: no cap)."""
    if grid is not None:
        cell = tuple(grid)
        for monster in ctx.hostiles():
            if (monster.race_id == race and (monster.position.y, monster.position.x) == cell
                    and monster.hp != UNKNOWN_MONSTER_HP):
                return monster.hp
    knowledge = ctx.policy._monrace_knowledge.get(race)
    return knowledge.max_hp if knowledge is not None else None


def _ball_powers(ctx: _Ctx, race: int, grid=None):
    """(expected damage, radius, shape, key maker) of each ball or breath the character can aim
    at a grid: absorbed powers and carried wands and rods, strongest first; none that ``race``'s
    known flags cancel (``attack_expectation.effective``).

    Owner 2026-11-19 「3つとも広げる」 (Powerful Activation in the Q25 battle too): an absorbed
    power is offered a second time cast powerfully while me_device_attacks.powerful_ready holds
    (me_device_attacks.attack_uses: the same success, the doubled level, a ball's radius 3); of
    equal damage the ordinary use, listed first, stays first (the sort is stable).  Every row is
    me_device_attacks.use_value's (owner 2026-11-23 「期待値で攻撃手段を選ぶ」): the success times
    the damage, capped by the target's hit points (``_target_hp``)."""
    snapshot, policy = ctx.snapshot, ctx.policy
    flags = me_device_attacks.race_id_flags(policy, race)
    level = snapshot.player.level
    hp = _target_hp(ctx, race, grid)
    found = []
    if me_device_attacks.can_use_powers(snapshot):
        for power, success in me_device_attacks.attack_uses(policy, snapshot):
            if power.shape in me_device_attacks.TARGETABLE_SHAPES and not power.group_only:
                found.append((me_device_attacks.use_value(power, success, level, flags, hp),
                              power.area_radius, power.shape,
                              lambda grid, power=power: me_device_attacks.device_target_key(
                                  policy, power, Position(*grid), snapshot)))
    if not (snapshot.player.blind or snapshot.player.confused):
        for item in snapshot.inventory:
            kind = {TVAL_WAND: "wand", TVAL_ROD: "rod"}.get(item.tval)
            power = me_device_attacks.POWERS.get((kind, item.sval)) if kind else None
            if (power is None or power.shape not in me_device_attacks.TARGETABLE_SHAPES
                    or not item.known or item.charging or (kind == "wand" and item.charges <= 0)):
                continue
            chance = (attack_expectation.device_use_success if kind == "wand"
                      else attack_expectation.rod_use_success)(snapshot.player.device_skill, power.level)
            found.append((me_device_attacks.use_value(power, chance, level, flags, hp),
                          me_device_attacks.AREA_RADIUS[power.shape], power.shape,
                          lambda grid, item=item, kind=kind: _carried_grid_key(ctx, kind, item, grid)))
    return sorted(attack_expectation.effective(found), key=lambda row: -row[0])


def _cursor_suffix(ctx: _Ctx, grid) -> str:
    """get_aim_dir's free-cursor walk to ``grid`` (policy_combat ``ranged:fire-offset``)."""
    return "*p" + ctx.policy._cursor_delta_keys(ctx.snapshot.player.position, Position(*grid)) + "t5\x1b"


def _carried_grid_key(ctx: _Ctx, kind: str, item, grid) -> str | None:
    key = reserved_item_command(ctx.policy, ctx.snapshot, kind, item, suffix=_cursor_suffix(ctx, grid))
    if key is not None:
        ctx.policy.last_reason = SHOT_REASON
    return key


def _launcher_grid_key(ctx: _Ctx, grid) -> str | None:
    ammo = ctx.policy._matching_ammo(ctx.snapshot)
    if ammo is None or ctx.snapshot.player.blind or ctx.snapshot.player.confused:
        return None
    key = reserved_item_command(ctx.policy, ctx.snapshot, "fire", ammo, suffix=_cursor_suffix(ctx, grid))
    if key is not None:
        ctx.policy.last_reason = SHOT_REASON
    return key


def _beam_key(ctx: _Ctx, race: int, grid) -> tuple[float, Callable] | None:
    """The best absorbed beam along a ray to ``grid`` (a bolt-or-beam counts at its beam chance);
    none that ``race``'s known flags cancel."""
    snapshot = ctx.snapshot
    direction = me_powers.beam_direction(ctx.policy, snapshot, snapshot.player.position, Position(*grid))
    if direction is None or not me_device_attacks.can_use_powers(snapshot):
        return None
    flags = me_device_attacks.race_id_flags(ctx.policy, race)
    hp = _target_hp(ctx, race, grid)
    best = None
    for power, success in me_device_attacks.attack_uses(ctx.policy, snapshot):
        share = _beam_share(power)
        if share <= 0 or power.group_only:
            continue
        damage = me_device_attacks.use_value(power, success, snapshot.player.level, flags, hp, share=share)
        if damage > 0 and (best is None or damage > best[0]):   # a tie keeps the ordinary use
            best = (damage, lambda power=power: me_device_attacks.device_key(
                ctx.policy, power, direction, snapshot))
    return best


def _beam_share(power) -> float:
    """The share of ``power``'s uses that pass the bodies along its ray: a beam's all, a
    bolt-or-beam's beam chance (fire_bolt_or_beam), a bolt's none."""
    return 1.0 if power.shape == "beam" else power.beam_percent / 100


def _reaches_grid(power) -> bool:
    """``power`` hits a grid it need not see: a ball or a breath aimed at it, a beam along its ray
    (``_ball_powers``, ``_beam_key``)."""
    return power.shape in me_device_attacks.TARGETABLE_SHAPES or _beam_share(power) > 0


def _fire_options(ctx: _Ctx, grid, race: int, *, piercing: bool = False, area_only: bool = False,
                  missiles: bool = True, covers=None) -> list:
    """(expected damage, key maker) of every attack aimed at ``grid``; ``piercing``: only one that
    passes the bodies on the way (a beam, a ball or a breath aimed at the grid); ``missiles``:
    the launcher too; ``covers``: only a ball or breath whose radius reaches that cell from
    ``grid`` (a burst planned off the target with a Powerful Activation's radius 3, which a
    radius-2 ball aimed there would miss)."""
    reach = None if covers is None else quest_exposure.game_distance(tuple(grid), tuple(covers))
    options = [(damage, lambda make=make: make(grid))
               for damage, radius, shape, make in _ball_powers(ctx, race, grid)
               if (not area_only or shape == "ball") and (reach is None or radius >= reach)]
    if not area_only:
        if (beam := _beam_key(ctx, race, grid)) is not None:
            options.append(beam)
        if not piercing and missiles:
            distance = quest_exposure.game_distance(ctx.here, tuple(grid))
            launcher = attack_expectation.launcher_against(ctx.policy, ctx.snapshot, race, distance)
            if (hp := _target_hp(ctx, race, grid)) is not None:
                launcher = min(launcher, max(hp, 0))
            if launcher > 0:
                options.append((launcher, lambda: _launcher_grid_key(ctx, grid)))
    return options


def _fire_at(ctx: _Ctx, grid, race: int, *, piercing: bool = False, area_only: bool = False,
             missiles: bool = True, covers=None) -> str | None:
    """The strongest attack aimed at ``grid`` (「一番ダメージの出る攻撃」), of ``_fire_options``."""
    options = _fire_options(ctx, grid, race, piercing=piercing, area_only=area_only, missiles=missiles,
                            covers=covers)
    for _damage, make in sorted(options, key=lambda row: -row[0]):
        key = make()
        if key is not None:
            ctx.battle.aimed_race = race
            return key
    return None


def _has_piercing(ctx: _Ctx, race: int, grid) -> bool:
    return bool(_ball_powers(ctx, race)) or _beam_key(ctx, race, grid) is not None


def _balls(ctx: _Ctx, race: int) -> list:
    return [row for row in _ball_powers(ctx, race) if row[2] == "ball"]


def _engage(ctx: _Ctx, targets) -> str | None:
    """Beside the player, the blow; else a shot at the first that can be shot."""
    policy, snapshot = ctx.policy, ctx.snapshot
    beside = [monster for monster in targets if monster.distance <= 1]
    if beside:
        struck = summon_response.named_casters_first(policy, beside)[:1]
        answer = combat_answer.adjacent_attack(policy, snapshot, struck, MELEE_REASON)
        if answer is not None and answer.key is not None:
            return answer.key
    for target in targets:
        if target.distance > 1 and (shot := quest_plan_base._shot(policy, snapshot, target)) is not None:
            ctx.battle.aimed_race = None
            return shot
    return None


def _fight_targets(ctx: _Ctx) -> list:
    """What this phase fights in view: every mover, not the immobile casters of later phases
    nor the breeders (``_breeders_in_line_key``)."""
    return [monster for monster in ctx.seen_hostiles()
            if monster.race_id not in _LATER_IMMOBILE and not monster.can_multiply]


def _hold(ctx: _Ctx) -> str:
    ctx.policy.last_reason = HOLD_REASON
    return WAIT_KEY


def _haste(ctx: _Ctx) -> str | None:
    if ctx.policy._player_hasted(ctx.snapshot):
        return None
    return speed_dose.key(ctx.policy, ctx.snapshot, HASTE_REASON)


# -- between phases ---------------------------------------------------------------------


def _attack_kinds(ctx: _Ctx) -> set[str]:
    return {kind for (kind, sval) in me_device_attacks.POWERS
            if me_capability.has(ctx.policy, ctx.snapshot, kind, sval)}


def _full(power, row) -> bool:
    if power.kind == "rod":
        return row.get("charging") == 0
    return isinstance(row.get("current"), int) and row.get("current") == row.get("max")


def _recharge_key(ctx: _Ctx) -> str | None:
    """「攻撃に使うものを全快させる」: browse a stale list, else a counted rest while one is short."""
    if ctx.snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
        return None
    lists = getattr(ctx.policy, "_me_device_lists", None) or {}
    for kind in sorted(_attack_kinds(ctx)):
        if kind not in lists or kind not in ctx.battle.browsed:
            ctx.battle.browsed = ctx.battle.browsed | {kind}
            browse = "b" + me_powers_refresh.KIND_LETTER[kind]
            ctx.policy.last_reason = me_powers_refresh.REFRESH_REASON
            ctx.policy._offer_execution(
                browse, producer="bookkeeping", work_id="quest25-recharge-read",
                next_step="magic-eater.browse.send", arguments=(kind,),
                expected_effect="magic-eater-power-list-observed")
            return browse
    short = any(not _full(power, row)
                for kind in _attack_kinds(ctx) for row in lists[kind][1]
                if (power := me_device_attacks._BY_NAME.get((kind, row.get("name")))) is not None)
    if not short or ctx.battle.recharge_rests >= RECHARGE_REST_LIMIT:
        return None
    ctx.battle.browsed = frozenset()
    ctx.battle.recharge_rests += 1
    ctx.battle.recharge_rest_turn = int(ctx.snapshot.turn)
    ctx.policy.last_reason = RECHARGE_REASON
    return RECHARGE_REST_KEY


def _sensed_movers(ctx: _Ctx) -> list:
    """Awake hostiles known only by sensing (ESP, detection) whose race can move."""
    seen = {monster.index for monster in ctx.seen_hostiles()}
    found = []
    for monster in ctx.hostiles():
        if monster.index in seen or monster.asleep:
            continue
        knowledge = attack_expectation.race_knowledge(ctx.policy, monster.race_id)
        if knowledge is None or "NEVER_MOVE" not in knowledge.flags:
            found.append(monster)
    return found


def _note_rest_cut(ctx: _Ctx) -> None:
    """The board after a counted recharge rest: cut short while a sensed hostile moves.

    A sensed (ml) hostile that moves disturbs the player when it is of the player's level or
    above, or of a race never killed (monster-move.cpp, disturb_high and disturb_unknown on by
    default in option-types-table.cpp), and a disturbance ends the rest.  ``R100`` is 100 player
    turns, at least 200 game turns even at the fastest speed (speed_to_energy caps at 49 of the
    100 a turn needs), so a rest that ended in fewer than ``REST_CUT_GAME_TURNS`` was cut.
    n1-c life-174 (2026-11-09 03:16:46): on [2,24] every rest ended after 3-13 game turns while
    the Dreadmaster, sensed undead, came through the walls, and the read-and-rest cycle repeated
    until the loop guard stopped the bot."""
    battle = ctx.battle
    if battle.recharge_rest_turn is None or ctx.snapshot.turn <= battle.recharge_rest_turn:
        return
    elapsed = int(ctx.snapshot.turn) - battle.recharge_rest_turn
    battle.recharge_rest_turn = None
    if elapsed < REST_CUT_GAME_TURNS and _sensed_movers(ctx):
        battle.rest_cut = True


def _full_hp_key(ctx: _Ctx) -> str | None:
    player = ctx.snapshot.player
    if player.hp >= player.max_hp:
        return None
    ctx.policy.last_reason = FULL_HP_REASON
    return FULL_HP_REST_KEY


def _prepare(ctx: _Ctx, phase) -> str | None:
    """On a quiet board, before the phase's first step: the recharge, then full HP.

    Owner 2026-11-09 「持ち場へ歩き静まれば休む」: 「感知した動く敵が休みを切る間は、見えている敵が
    いる時と同じに扱い、その段の持ち場へ歩いて備える。静かになったら充填の休みを続ける。」  After a
    recharge rest a sensed moving hostile cut short (``_note_rest_cut``), the board is not quiet
    while such a hostile is sensed: the phase's step runs, as with a hostile in view; once none
    is sensed the preparation goes on."""
    if ctx.battle.ready:
        return None
    if ctx.seen_hostiles() or ctx.battle.rallying or ctx.battle.strong:
        return None   # phase 2's rally owns the board (``_rally``); it rests again when it ends
    if ctx.battle.rest_cut:
        if _sensed_movers(ctx):
            return None
        ctx.battle.rest_cut = False
    key = (_recharge_key(ctx) if ctx.battle.phase else None) or (
        _full_hp_key(ctx) if phase.full_hp else None)
    if key is None:
        ctx.battle.ready = True
    return key


def _adjacent_mass_key(ctx: _Ctx) -> str | None:
    """Owner 2026-11-07 「全部の段に広げる」: 「第1段から最後の段まで、隣のマスの死体の塊は殴るか撃って
    倒す。離れた塊は今のまま相手にしない。」: the blow (``_engage``'s adjacent attack), else the
    strongest shot at it.

    The masses breed (MULTIPLY) along the north corridor and drain CON by touch (n1-c life-159
    2026-11-07: max HP 766 -> 446 while the ambush held on [1,18] beside them)."""
    beside = sorted((monster for monster in ctx.seen_hostiles()
                     if monster.race_id == geo.MASS and monster.distance <= 1),
                    key=lambda monster: monster.index)
    if not beside:
        return None
    if (key := _engage(ctx, beside)) is not None:
        return key
    for monster in beside:
        if (key := _fire_at(ctx, (monster.position.y, monster.position.x), geo.MASS)) is not None:
            return key
    return None


def _breeders_in_line_key(ctx: _Ctx) -> str | None:
    """Owner 2026-11-08 「射線にいれば範囲で撃つ」: the breeders in the line of fire, when no more
    dangerous hostile acts (breeder_area_attack ``line_of_fire_key``); the one-target answer is
    the phase's strongest shot at the nearest (``_fire_at``)."""
    def single(target):
        return _fire_at(ctx, (target.position.y, target.position.x), target.race_id)
    key = breeder_area_attack.line_of_fire_key(ctx.policy, ctx.snapshot, single)
    if key is not None:
        ctx.battle.aimed_race = geo.MASS
    return key
