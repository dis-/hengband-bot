"""Quest 25 『幽霊屋敷』 fought phase by phase: ``engagement_plan.revised_plan_draft``.

Owner 2026-11-06 「作り直すまで外す」: n1-b life-323 walked into the hall and took 25 summons.
The redone plan is the draft's owner decisions (strategy/quests/QUEST_25.jsonc, every one
quoted there with its date); this module is their executor.  The phases, in order
(``PHASES``, one row each):

 1. ``ambush`` (phase1): the hound, the skeletal and spectral tyrannosaurs and the vampire
    lord are met in the start region.  「DPSで比較…行動回数で計測」: the actions to kill the
    spectral tyrannosaur by ranged attacks and by melee (attack_expectation, slays and hit
    chance in, the torch out) decide the stand: ranged waits on [10,1] with the door [9,1]
    open (owner 2026-11-22; it was [13,1], beyond the game's flow of 32 steps from the spectral
    tyrannosaur), melee waits on [10,1] with it closed and closes in the turn it is opened.
    「どちらにせよ加速を使用する」: hasted while a target is in view.  With no hostile in view, a carried
    Potion of Enlightenment is drunk first, once (owner 2026-11-07, ``_ambush_enlightenment``).
 2. ``wall-passers`` (phase1_wall_passers): full HP, then [7,1]; what comes is fought; 100
    player actions without a new arrival end it (owner 2026-11-09 「待つターンを倍にしてみる」).
 3. ``ipsissimus`` (phase2): full HP, [7,1], haste, [6,1], [5,1], then the strongest attack
    at the pen's [7,17] (the monster's own cell when it is seen).  Summons in view: a piercing
    attack (a beam, or a ball or breath aimed at the grid) and a low threat keep the fire on
    the pen; otherwise Teleportation, then a choke before contact (``_rally``), weighed before the
    walk to the stand.  What it teleported from is remembered and waited for on the choke until
    killed or unseen for the stragglers' 50 actions, then full HP and the walk again (owner
    2026-11-11 「隘路で待って倒す」); the walk never goes toward it.  The wall-passers
    the phase before left alive are no summons (``_summons_in_view``): they are ignored and the
    fire stays on the pen, never teleported from (owner 2026-11-09, n1-b life-359).  It ends when each of the three is
    killed or seen out of the pen.
 4. ``stragglers`` (phase1_wall_passers / phase2): on [5,1], the spectres and shadow demons
    that did not come and the Ipsissimus that teleported away are fought as they come; 50
    actions without a new arrival end it.
 5. ``quylthulgs`` (phase3 step 1): with a ball, each quylthulg a ball can catch from a cell
    out of the casters' lines ([5,2], [5,1]; quest25_geometry.ball_centre) is shot until it is
    killed or seen moved.  Without a ball it is skipped.
 6. ``tome`` (phase3 step 2): full HP, haste, then a ball from [5,1]/[5,2] where one reaches
    the tome, else the strongest ranged attack from [5,5], [4,5] or [5,6].
 7. ``corpse-masses`` (phase4): [1,6] by the walk that crosses no corridor trap, the door
    [1,7] opened, the corridor lit when dark (the 11-05 rule), and every mass in view shot --
    from the cell that reaches the most of them (owner 2026-11-09 「一番多く届く位置へ」,
    ``_walk_to_widest``), back to [1,6] when none is left to shoot.
 8. ``dreadmaster`` (phase5): both styles wait in the east big room, on the cell nearest its door
    [1,18] the dreadmaster's own movement brings it to (owner 2026-11-22, ``_dread_wait_cell``);
    hasted while it is in view.
 9. ``sweep`` (phase6_sweep): detection when the character has it, else the kill count
    against the roster and, when short, the old room-sweep stands walked as the patrol.
10. ``stairway`` (phase6): full HP, [13,27], haste, the door [13,28], then ranged or a step
    and melee by the actions to kill.  A summons that is not lethal does not stop it.
11. ``druj`` (phase7_druj, after the stairway: the draft orders it last): with a ball and
    Stone to Mud, [13,20], the door [11,19] melted and the ball burst on it; else the door
    opened and the druj shot from a trapless cell in its line.  Teleported away, the walk
    comes back; the Magic-Eater hastes out of the druj's line only.

In every phase (owner 2026-11-07 「隣に来たら倒す」, widened the same day 「全部の段に広げる」), a corpse
mass beside the player is struck (else shot) before the phase's own step (``_adjacent_mass_key``).
Owner 2026-11-08 「射線にいれば範囲で撃つ」 (it replaces 「離れた塊は今のまま相手にしない」): 「どの段でも、
もっと危ない敵が動いていなければ、射線にいる増える敵を撃つ。範囲攻撃は一番多く倒せるマスを狙い、2体
以上巻き込めるなら単体攻撃より先に使う。道をふさがれたら待たずに撃って開ける。」  Where the phase's own
step would wait or walk (or has none), the masses in the line of fire are shot instead
(``_breeders_in_line_key``, breeder_area_attack ``line_of_fire_key``): the aim with the most kills
when it catches two or more, else the phase's strongest shot at the nearest.  A more dangerous
hostile that acts keeps the phase's step; the phase's own fights and every survival rung come first.

Owner 2026-11-09 「見えない時は矢を撃たない。マスを狙う範囲の攻撃で削り、無ければ相手が見えるマスへ移って
撃つ。」 (the tome first), widened 「Q25 の全部の段に広げる」: the pen, the quylthulgs, the tome, the
stairway and the druj are shot with the launcher only when seen (``_unseen_fire``); a seen cell is
the player's light, or out to MAX_PLAYER_SIGHT on a glowing grid (「照らされた所も入れる」, ``_sight_radius``).

Between phases (between_phases): a Magic-Eater rests a counted rest until every absorbed
attack power is full, reading the lists turn-free (``b``) to decide (R& does not wait for
them, player-processor.cpp is_fully_healthy).  While a sensed moving hostile cuts that rest
short, the phase walks to its post instead and the rest goes on once none is sensed (owner
2026-11-09, ``_prepare``).

Traps (phase4, phase5): a corridor cell the map always traps is settled by a trap detection
when the character has one, else searched from beside it ten times (owner 2026-11-09), a cell
that may hold one (``!``) ten times; a disarming power or
device is aimed first when there is one, the disarm command (``_step_toward``) answers a
found trap.  A disarming beam that went off (the game's flash) answers every trap cell of its
line, and a cell that holds an item holds no trap (``_settle_beam``, ``_trap_key``).  Walks cross
the fewest summon cells while the Ipsissimus live and the fewest uncleared traps.

Kills are read from the game's kill lines (monster-damage.cpp): the seen ones by the race's
name, an unseen one (何か) as the race the last grid shot was aimed at.

Survival and the summons answer first (dungeon_ladder FLOOR_PLANS): the room sweep's own
survival rungs, then ``_summons`` -- the phase-2 and stairway rules on those phases, the
shared rules (summon_response) elsewhere.  The Resistance potion's drink stands there too, but
its no-chance leave (Teleportation or *Destruction*) comes after the phase's own step (owner
2026-11-07 「Q25内部でのテレポートの優先度を下げる」: n1-c life-159 read six Scrolls of Teleportation
in phase 1, the first beside the spectral tyrannosaurus on [10,1]).
The modules (maintainability review 2026-11-23 (a)-8, split with the behaviour unchanged), each
importing only those above it: quest25_battle_board (the reasons, the memory, the board read),
quest25_battle_attack (the attacks, the rests between phases), quest25_battle_walk (the walks, the
fire, the doors and traps), quest25_battle_hall and quest25_battle_rooms (the phases), and this one:
who runs the floor, the phase table, the rung (``key``).  The names other modules and the tests read
through ``quest25_battle`` are imported here from where they live.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from hengbot import (
    me_powers, once_quest_recall, quest25_druj_gear, quest25_geometry as geo, quest_exposure, quest_plan_base,
    quest_room_sweep, quest_wait_placement, resist_potion, summon_response, threat_tiers,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.me_absorbed_substitutes import item_cast_key
from hengbot.model import Position, SV_POTION_HEALING, TVAL_POTION
from hengbot.policy_constants import REST_MACRO, UP_STAIRS_KEY, WAIT_KEY
from hengbot.quest_plan_base import HOLD_REASON, MELEE_REASON
from hengbot.unseen_strike import message_text
# The plan's modules: the names read here, and the ones other modules and the tests read through
# ``quest25_battle`` (``battle._walk``, ``battle.WALK_REASON`` ...).
from hengbot.quest25_battle_board import (
    _Ctx, _ctx, _detection_failed, _druj_done, _HIT_LINES, _HIT_LINES_EN, _IDLE_REASONS, _ipsissimus_alive,
    _killed_name, _memory, _names, _next_phase, _note_arrivals, _note_glow, _note_kills, _note_pen_shot,
    _pain_of, _profile, _seen_at, _sight_radius, _tome_done, ABSORBED_HEAL_REASON, Battle, CHOKE_BACK_REASON,
    CLOSE_REASON, DETECT_REASON, DISARM_REASON, ENGAGE_REASON, ENLIGHTEN_REASON, FIRE_HOLD_REASON,
    FIRE_REST_REASON, FULL_HP_REASON, FULL_HP_REST_KEY, HASTE_REASON, MASS_CELL_REASON, melee_is_fewer,
    MELT_REASON, OPEN_REASON, OUT_OF_FIRE_REASON, REASON, RECALL_EXIT_REASON, RECALL_EXIT_WALK_REASON,
    RECALL_OUT_REASON, RECALL_WAIT_REASON, RECHARGE_REASON, RECHARGE_REST_KEY, RECHARGE_REST_LIMIT,
    RESTOCK_RECALL_REASON, RETREAT_HEAL_REASON, RETREAT_REASON, RETREAT_REST_REASON, SEARCH_REASON,
    SHOT_REASON, SIGHT_REASON, TELEPORT_REASON, WALK_REASON, WITHDRAW_REASON,
)
from hengbot.quest25_battle_attack import (
    _adjacent_mass_key, _balls, _beam_key, _breeders_in_line_key, _engage, _fight_targets, _fire_at,
    _full_hp_key, _haste, _hold, _note_rest_cut, _prepare, _recharge_key, _sensed_movers,
)
from hengbot.quest25_battle_walk import (
    _avoided, _damaged, _direction, _fire, _open_key, _out_of_fire_key, _path, _refused, _rest_out_of_fire,
    _safe_cells, _settle_beam, _settle_detection, _shunned, _step, _trap_key, _unseen_fire, _walk,
    _walk_to_sight, _withdraw, contract,
)
from hengbot.quest25_battle_hall import (
    _ambush, _ambush_done, _ipsissimus, _ipsissimus_done, _note_strong, _pen_shot, _rally, _restock_recall,
    _stragglers, _stragglers_done, _wall_passers, _wall_passers_done,
)
from hengbot.quest25_battle_rooms import (
    _can_melt, _detect_key, _detector, _dread_vision, _dread_wait_cell, _dreadmaster, _dreadmaster_done,
    _druj, _mass_reached, _masses, _masses_done, _masses_seen, _melt_key, _note_dread_teleport, _note_quyls,
    _note_tome_health, _phase_masses, _quyls, _quyls_done, _stairway, _stairway_done, _sweep, _sweep_done,
    _sweep_reachable, _sweep_targets, _teleported_dreadmaster_key, _tome, _tome_hp, _walk_to_widest,
)


# -- who runs the floor -----------------------------------------------------------------


_PLANNED_STEPS = frozenset({WALK_REASON, ENGAGE_REASON, RETREAT_REASON, SIGHT_REASON, WITHDRAW_REASON,
                            CHOKE_BACK_REASON,
                            OUT_OF_FIRE_REASON, quest_room_sweep.EXIT_WALK_REASON,
                            RECALL_EXIT_WALK_REASON, RECALL_OUT_REASON, MASS_CELL_REASON})
# The plan's own '<' on the start stair: Recall active (_recall_wait) or Healing used up (_leave_by_exit).
_START_STAIR_LEAVES = frozenset({RECALL_EXIT_REASON, quest_room_sweep.EXIT_REASON})


def applies(policy, snapshot) -> bool:
    """This plan runs the floor (quest_room_sweep steps aside for it)."""
    return _profile(policy, snapshot) is not None


def holds(policy, snapshot) -> bool:
    return policy.last_reason == HOLD_REASON and applies(policy, snapshot)


def planned_step(policy, snapshot) -> bool:
    return policy.last_reason in _PLANNED_STEPS and applies(policy, snapshot)


def owns_leave_confirmation(policy, snapshot) -> bool:
    """The plan's start-stair step owns 「本当にこの階を去りますか？」 (the quest is left unfinished).

    Owner 2026-11-04 「体力回復を使い切り HP 20% 以下で開始の階段まで5歩以内なら踏む」 and 2026-11-09
    「段をやめ射線外で待つ」 (「開始の階段へ行ければ踏み」) decided the leave; the '<' they post must
    answer the question cmd-move.cpp confirm_leave_level asks on the taken ONCE quest floor.  n1-c
    life-181 (2026-11-09 19:18) posted quest25:recall-exit's '<' on [13,1] three times into the
    unowned confirm and retired on the stuck prompts."""
    return policy.last_reason in _START_STAIR_LEAVES and applies(policy, snapshot)


def walks_over_traps(policy, snapshot) -> bool:
    """The plan answers its own traps (trap_warning leaves the step to it)."""
    return applies(policy, snapshot)


# -- the table --------------------------------------------------------------------------


@dataclass(frozen=True)
class Phase:
    name: str
    spec_key: str          # the draft's key that says it
    full_hp: bool          # 「全快にして」 before its first step
    done: Callable
    act: Callable          # the phase's own step
    wait_at: tuple | None = None   # where its wait is counted (None: anywhere, once ready; else also ``no_way``)
    wait_limit: str | int | None = None  # the wait_limits item (or a number): actions without an arrival that end it
    waits_for: tuple = ()  # the roster races the wait is for (quest25_presence ``presence_key``)


PHASES = (
    Phase("ambush", "phase1", False, _ambush_done, _ambush, None, "long_wait_actions",
          (geo.HOUND, geo.SKELETAL_T, geo.VAMPIRE, geo.SPECTRAL_T)),
    Phase("wall-passers", "phase1_wall_passers", True, _wall_passers_done, _wall_passers,
          geo.WALL_PASSER_STAND, "wall_passer_quiet_actions", (geo.SPECTRE, geo.SHADOW)),
    Phase("ipsissimus", "phase2", True, _ipsissimus_done, _ipsissimus),
    Phase("stragglers", "phase1_wall_passers", False, _stragglers_done, _stragglers,
          geo.STRAGGLER_STAND, "quiet_actions", (geo.SPECTRE, geo.SHADOW, geo.IPSISSIMUS)),
    Phase("quylthulgs", "phase3", False, _quyls_done, _quyls),
    Phase("tome", "phase3", True, _tome_done, _tome),
    Phase("corpse-masses", "phase4", False, _masses_done, _masses),
    Phase("dreadmaster", "phase5", False, _dreadmaster_done, _dreadmaster, None, "long_wait_actions",
          (geo.DREADMASTER,)),
    Phase("sweep", "phase6_sweep", False, _sweep_done, _sweep),
    Phase("stairway", "phase6", True, _stairway_done, _stairway),
    Phase("druj", "phase7_druj", False, _druj_done, _druj),
)
PHASE_NAMES = tuple(phase.name for phase in PHASES)


def _act(ctx: _Ctx, phase: Phase) -> str | None:
    """The phase's own step; where it waits or walks (or has none), the breeders in line first.

    A step that names no reason of its own keeps the previous one, so the reason is read only
    when the step set it."""
    entry = ctx.policy.last_reason
    ctx.policy.last_reason = ""
    key = phase.act(ctx)
    own = ctx.policy.last_reason
    if not own:
        ctx.policy.last_reason = entry
    if key is None or own in _IDLE_REASONS:
        if (shot := _breeders_in_line_key(ctx)) is not None:
            return shot
        if key is None and (walk := _walk_to_widest(ctx)) is not None:
            # Owner 2026-11-08 「道をふさがれたら待たずに撃って開ける」: the phase has no step (its
            # way is shut, a mass on it) and no mass is in the line from here: to the cell that
            # reaches the most of them in view (``_mass_firing_cells``), then the shot above.
            # n1-c life-217 (2026-11-19 05:24): the tome's phase on [8,20], the north corridor's
            # only cell [1,18] a mass out of every line from there, 32 waits to the loop guard.
            return walk
        if not own:
            ctx.policy.last_reason = entry
        elif key is not None:
            ctx.policy.last_reason = own
    return key


def _finished(ctx: _Ctx, phase: Phase) -> bool:
    """Its own end, or its wait limit (wait_limits, phase1_wall_passers, phase2)."""
    return phase.done(ctx) or (phase.wait_limit is not None
                               and ctx.battle.quiet >= _wait_limit(ctx, phase))


def _wait_limit(ctx: _Ctx, phase: Phase) -> int:
    """The phase's wait in player actions: its ``wait_limits`` item, or a number a row carries
    itself (a recorded process's own wait, as tests/test_n1c_174_q25_loops_1109_recorded
    replays the 50 actions that process ran)."""
    limit = phase.wait_limit
    return limit if isinstance(limit, int) else ctx.values.wait_limit(limit)


def current_phase(ctx: _Ctx) -> Phase | None:
    """Advance over every finished phase; the one running, else None (all done)."""
    while ctx.battle.phase < len(PHASES) and _finished(ctx, PHASES[ctx.battle.phase]):
        _next_phase(ctx.battle)
    return PHASES[ctx.battle.phase] if ctx.battle.phase < len(PHASES) else None


def _note_room_kill(ctx: _Ctx) -> None:
    from hengbot import quest25_sealed_room

    quest25_sealed_room.note_kill(ctx)


def _observe(ctx: _Ctx) -> None:
    """Once per board (``key`` and ``walk_key`` may both read it).

    A phase's wait counts on its stand (``wait_at``), and where the phase's last walk to it held
    with no way on (``battle.no_way``): the owner's 「道が無ければ今いる召喚を受けないマスで迎え撃つ」
    (2026-11-12, ``_shunned_hold``) meets them there, and the wait for arrivals 「50回来なければ
    終える」 (2026-11-06) is the same wait wherever it is held, so it ends instead of holding on.
    n1-c life-207 (2026-11-14): with no way to [7,1] the wall-passers' wait never counted, and the
    phase held on [10,1] for over 5,300 decisions.

    The wait counts too while the phase's preparation waits for a sensed mover that cut its
    recharge rest (``_prepare``: owner 2026-11-09 「持ち場へ歩き静まれば休む」, treated as a hostile in
    view, the phase's step runs): a straggler sensed in the walls that never comes is an arrival
    that does not come, and 「50回来なければ終える」.  n1-c life-207 (2026-11-14 20:49-21:24): the
    stragglers' rest on [5,1] was cut at turn 8011366, a shadow demon stayed sensed on [11,4], the
    phase was never ready and held there 35 minutes to the stall stop, its wait never counted."""
    from hengbot import quest25_pocket, quest25_presence

    board = (ctx.snapshot.turn, id(ctx.snapshot))
    if ctx.battle.observed == board:
        return
    ctx.battle.observed = board
    _settle_beam(ctx)
    _settle_detection(ctx)
    _note_rest_cut(ctx)
    _note_kills(ctx)
    _note_room_kill(ctx)
    _note_pen_shot(ctx)
    quest25_pocket.note_shot(ctx)
    _note_arrivals(ctx)
    _note_strong(ctx)
    _note_glow(ctx)
    _note_tome_health(ctx)
    _note_dread_teleport(ctx)
    quest25_presence.note_absent(ctx)
    phase = current_phase(ctx)
    waiting = ctx.battle.ready or (ctx.battle.rest_cut and bool(_sensed_movers(ctx)))
    if (phase is not None and phase.wait_limit is not None and waiting
            and (phase.wait_at in (None, ctx.here) or ctx.battle.no_way == ctx.here)):
        ctx.battle.quiet += 1


def observe_board(policy, snapshot) -> None:
    """Read a board the plan does not decide (a turn-free list read takes it): its kill lines
    and arrivals count as on a decided board."""
    ctx = _ctx(policy, snapshot)
    if ctx is not None:
        _observe(ctx)


def _phase_key(policy, snapshot) -> str | None:
    """The running phase's own order: its preparation, then its step.  On a room whose only way
    out is a great-hall door while the hall is dangerous, the room's plan first (owner 2026-11-12,
    quest25_sealed_room)."""
    ctx = _ctx(policy, snapshot)
    if ctx is None:
        return None
    phase = current_phase(ctx)
    if phase is None:
        # The druj is dead: the anti-teleport piece's slot returns to the target (slot_lending).
        return (quest25_druj_gear.restore_key(policy, snapshot)
                or _after_the_phases(ctx))
    from hengbot import quest25_presence, quest25_sealed_room

    return (_adjacent_mass_key(ctx) or _teleported_dreadmaster_key(ctx)
            or quest25_sealed_room.key(ctx)
            or _prepare(ctx, phase) or quest25_presence.presence_key(ctx, phase) or _act(ctx, phase)
            or _stranded_in_dread_range_key(ctx))


def _stranded_in_dread_range_key(ctx: _Ctx) -> str | None:
    """The running phase has no step and the player stands in the living dreadmaster's range: the
    owner's 2026-11-19 rule as after the teleport line (``_note_dread_teleport``).

    No phase before the dreadmaster's own stops in that range by its plan (phase4 「ドリードマスター
    の感知範囲の外」; the walks only pass through it), so a standstill there is a displacement the
    teleport line may no longer show: n1-c life-217's restart (2026-11-19 05:59) found the player on
    [8,20] with the line long gone and a battle record that predated the mark, and waited 35 times
    to the loop guard."""
    if ctx.battle.dread_teleported or ctx.here not in _dread_vision(ctx):
        return None
    ctx.battle.dread_teleported = True
    return _teleported_dreadmaster_key(ctx)


def _after_the_phases(ctx: _Ctx) -> str | None:
    """Every phase ended and the quest (KILL_ALL) is not complete: what is left is found and killed.

    n1-b life-378 (2026-11-13 01:46, build bot-68c820fd6): the quylthulgs' phase found no ball then
    (owner 2026-11-06 phase3 「範囲攻撃が無ければ 1) をとばして」), the sweep's Detect Evil showed
    nothing (a quylthulg is not evil), the stairway and the druj fell, and with the quest still
    taken the plan had no step: ``quest:blocked:execute`` waits on [12,24] until the loop guard
    stopped the bot, three times.  The draft's order puts the quylthulgs before the druj (owner
    2026-11-05 「最後ドルジの前に処理する」) and the quest is won only with every monster dead, so
    the plan goes on: each quylthulg still on its cell is shot directly from a cell of its line
    (phase3 「加速して直接撃つ」, ``_quyls``), then the sweep's round is walked for what is left
    (phase6_sweep 「巡回して探す」), bounded by ``room_sweep.max_rounds`` as there."""
    left = [cell for cell, race in ctx.navigator.battlefield.monster_placements
            if race == geo.QUYL and cell not in ctx.battle.quyls_done]
    if left and ctx.kills(geo.QUYL) < geo.ROSTER[geo.QUYL]:
        _note_quyls(ctx)
        left = [cell for cell in left if cell not in ctx.battle.quyls_done]
    if left and ctx.kills(geo.QUYL) < geo.ROSTER[geo.QUYL]:
        key = _quyls(ctx, (left[0], None, None))
        if key is not None:
            return key
    # Owner 2026-11-13 「全滅クエストで作戦を完了しても終了しない場合、周回して敵を探す。感知を持って
    # いれば感知して敵を探す。」: the KILL_ALL patrol every such quest walks (kill_all_patrol).
    from hengbot import kill_all_patrol

    return kill_all_patrol.key(ctx.policy, ctx.snapshot)


def phases_left(policy, snapshot) -> bool:
    """This floor is the plan's and a phase of it is still running: the plan owns every move
    (kill_all_patrol ``_plan_running``; the patrol is asked from ``_after_the_phases``)."""
    ctx = _ctx(policy, snapshot)
    return ctx is not None and current_phase(ctx) is not None


def phase_index(name: str) -> int:
    """The index of the phase named ``name`` in ``PHASES``."""
    return next(index for index, phase in enumerate(PHASES) if phase.name == name)


# -- the summons ------------------------------------------------------------------------


def _druj_retreat(policy, snapshot, *, line=True) -> str | None:
    """Owner 2026-11-07 (phase7_druj) 「歩いてドルジの射線から外れる。安全に休憩可能なはずである。
    必要なら歩いて射線から外れた後薬を飲む。」

    With the anti-teleport piece worn on the druj phase, Teleportation cannot be read
    (teleport_player refuses under NO_TELE), so below the plan's line (``abort_conditions.hp_ratio``,
    the line ``_below_line`` reads Teleportation at) the walk leaves the druj's direct line (it never
    moves and every spell of it needs that line), then rests there until HP is full.  A rest that
    did not raise HP (refused or broken off) is followed by a Healing potion -- out of the line only.
    Back at full HP the phase walks back to its stand.  ``line=False``: the plan's escape asked by
    its 即死 rung, whatever the HP (threat_tiers.instant_death_key).
    """
    ctx = _ctx(policy, snapshot)
    if (ctx is None or ctx.battle.phase >= len(PHASES) or PHASES[ctx.battle.phase].name != "druj"
            or quest25_druj_gear.worn_piece(snapshot) is None):
        if ctx is not None:
            ctx.battle.retreating, ctx.battle.retreat_rest_hp = False, None
        return None
    battle, player = ctx.battle, snapshot.player
    if not battle.retreating:
        if line and player.hp_ratio > float(ctx.profile.abort_conditions["hp_ratio"]):
            return None
        battle.retreating = True
    if player.hp >= player.max_hp:
        battle.retreating, battle.retreat_rest_hp = False, None
        return None
    druj = next(cell for cell, race in ctx.navigator.battlefield.monster_placements if race == geo.DRUJ)
    lines = geo.line_cells(ctx.open_terrain(), druj) | {druj}
    if ctx.here in lines:
        battle.retreat_rest_hp = None
        out = {cell for cell, kind in ctx.terrain.items()
               if kind in {"floor", "door"} and cell not in lines}
        return _walk(ctx, out, RETREAT_REASON)
    if battle.retreat_rest_hp is not None and player.hp <= battle.retreat_rest_hp:
        potion = quest_plan_base._healing_potion(policy, snapshot)
        if potion is not None:
            battle.retreat_rest_hp = None
            policy.last_reason = RETREAT_HEAL_REASON
            return reserved_item_command(policy, snapshot, "quaff", potion)
    battle.retreat_rest_hp = player.hp
    policy.last_reason = RETREAT_REST_REASON
    return REST_MACRO


def _summons(policy, snapshot) -> str | None:
    """Owner 2026-11-06: on phase 2 the reinforcements are answered by the phase's own rule
    (its fire on the pen or the teleport, ``_ipsissimus``); on the stairway 「致死的でなければ
    階段の処理を優先する」.  Elsewhere the shared rules (summon_response)."""
    ctx = _ctx(policy, snapshot)
    if ctx is not None and ctx.battle.phase < len(PHASES):
        name = PHASES[ctx.battle.phase].name
        if name == "ipsissimus":
            return None
        if name == "stairway" and not policy._is_material_threat(
                snapshot, policy._physical_hostiles(snapshot)):
            return None
    return summon_response.key(policy, snapshot)


# -- the rung ---------------------------------------------------------------------------


def key(policy, snapshot) -> str | None:
    """The board on the Q25 floor while the revised plan runs; None leaves it shared."""
    ctx = _ctx(policy, snapshot)
    if (ctx is None or quest_plan_base.steps_aside_for_food(policy, snapshot)
            or once_quest_recall._deliberate_leave(policy, snapshot)):
        return None
    _observe(ctx)
    profile, navigator = ctx.profile, ctx.navigator
    plan = profile.engagement_plan["room_sweep"]
    board = quest_room_sweep._Board(policy, snapshot, profile, navigator, {**plan, "left_alone_races": ()})
    board.contract = contract(ctx, plan)
    if not board.enemy:
        return (
            _druj_retreat(policy, snapshot)
            or _leave_by_exit(policy, snapshot, board)
            or _summons(policy, snapshot)
            or resist_potion.drink_key(policy, snapshot)
            # The shared survival stage of a quiet board: the plan's restore (``_restore``).
            or quest_plan_base.survival_stage(policy, snapshot, profile, board, restore=_restore)
            or _out_of_fire_key(policy, snapshot)
            or _restock_recall(policy, snapshot)
            or _recall_wait(policy, snapshot)
            or _phase_key(policy, snapshot)
            or resist_potion.leave_key(policy, snapshot)
        )
    return (
        # Owner 2026-11-07 「作戦が先・即死だけ例外」: only the 1-turn 即死 pre-empts the plan.
        # The plan's escape: with the druj's anti-teleport piece worn the walk out of its line
        # (owner 2026-11-07 phase7_druj), else the below-line Teleportation.
        threat_tiers.instant_death_key(policy, snapshot, lambda: (
            _druj_retreat(policy, snapshot, line=False)
            or quest_plan_base._below_line(policy, snapshot, profile, navigator, line=False)))
        or quest_plan_base._cure(policy, snapshot)
        or _druj_retreat(policy, snapshot)
        or _leave_by_exit(policy, snapshot, board)
        or quest_plan_base._give_up(policy, snapshot, profile)
        or quest_plan_base._below_line(policy, snapshot, profile, navigator)
        or _absorbed_heal(policy, snapshot, profile)
        or quest_plan_base._heal(policy, snapshot, profile)
        or _restock_recall(policy, snapshot)
        # The shared survival stage: the cure and the Healing (asked above already), the haste.
        or quest_plan_base.survival_stage(policy, snapshot, profile, board)
        or _summons(policy, snapshot)
        or resist_potion.drink_key(policy, snapshot)
        or _out_of_fire_key(policy, snapshot)
        or _recall_wait(policy, snapshot)
        or _phase_key(policy, snapshot)
        or resist_potion.leave_key(policy, snapshot)
    )


def _restore(policy, snapshot) -> str | None:
    """The plan's 「敵がいない時に下がっていれば飲む」 (QUEST_25 consumable_plan): not while a summons
    Teleportation was read from is remembered (``_note_strong``, owner 2026-11-09 「起きた敵も最後の
    位置を覚える」).  n1-c life-195 (2026-11-11 game 05:37): on [2,2] the dracolich seen on the board
    before stood out of the light, the board showed no enemy, and the Restore Life Levels was
    drunk; it was beside the player on the next board."""
    ctx = _ctx(policy, snapshot)
    if ctx is not None and ctx.battle.strong:
        return None
    return (quest_plan_base._restore(policy, snapshot)
            # Owner 2026-11-23 「数マス以内なら拾って飲む」 (quest_plan_base.floor_restore_key).
            or quest_plan_base.floor_restore_key(policy, snapshot))


def _absorbed_heal(policy, snapshot, profile) -> str | None:
    """Owner 2026-11-09 Q3 「成功率が80%以上なら体力回復は使っても良い。テレポートは許可しない」, and the
    same day 「即死の危険がないときは薬より優先する」 / 「ロッドも同じ」: at the plan's heal line (where a
    Healing potion is drunk), the absorbed Healing -- the staff's, else the rod's -- whose displayed
    success rate is at least 80% (me_capability ``reliable``, the owner's one number for absorbed
    powers in place of an item) comes before the potion, unless the instant death holds
    (threat_tiers ``instant_death``: the next action's p95 reaches the HP); then a carried potion,
    which does not fail, goes first.  Without a potion it is cast either way.  n1-c life-178 had
    4 charges at 32%: none."""
    threshold = profile.consumable_plan.get("heal_threshold_ratio")
    if threshold is None or snapshot.player.hp_ratio >= float(threshold):
        return None
    if (quest_plan_base._healing_potion(policy, snapshot) is not None
            and threat_tiers.instant_death(policy, snapshot).holds):
        return None
    key = item_cast_key(policy, snapshot, (TVAL_POTION, SV_POTION_HEALING))
    if key is not None:
        policy.last_reason = ABSORBED_HEAL_REASON
    return key


def _recall_wait(policy, snapshot) -> str | None:
    """Owner 2026-11-09 Q2 「段をやめ射線外で待つ」: 「段の動きをやめる。開始の階段へ行ければ踏み、
    行けなければ動かない敵の射線の外へ下がって発動を待つ。」

    Once Recall is active (read when the supplies ran out, once_quest_recall), no phase step: the
    start stair when a walk reaches it without entering the casters' fire, taken there; else out
    of the fire and the wait (the blow at an enemy beside; a rest while damaged).  n1-c life-178:
    after the Recall of decision 5205 the phase walked back toward the tome twice at HP 14-18% and
    died before it took effect."""
    ctx = _ctx(policy, snapshot)
    if ctx is None or not snapshot.player.recalling:
        return None
    fire = _fire(ctx)
    goal = tuple(ctx.navigator.battlefield.exit)
    if ctx.here == goal:
        policy.last_reason = RECALL_EXIT_REASON
        return UP_STAIRS_KEY
    occupied = frozenset((monster.position.y, monster.position.x) for monster in ctx.seen_hostiles())
    terrain = quest_plan_base._terrain_of(ctx.navigator, snapshot, water=False)
    terrain[ctx.here] = "floor"
    path = quest_exposure.least_exposed_path(terrain, geo.exposure_of(fire | _avoided(ctx)),
                                             ctx.here, {goal}, (occupied - {goal}) | _refused(ctx))
    if len(path) >= 2 and not set(path[1:]) & fire:
        return _trap_key(ctx, path[1]) or _step(ctx, path[1], RECALL_EXIT_WALK_REASON, guard=False)
    if ctx.here in fire:
        return _withdraw(ctx, RECALL_OUT_REASON)
    # The wait stops the phase's steps, not the blow at an enemy beside: a rest (cmd-move.cpp
    # do_cmd_rest spends the turn's 100 energy) with one beside is a turn given to its blows.
    # n1-a life-529 (2026-11-17 00:10:44-00:10:49, decisions 36516-36530): Recall read on [5,2]
    # with eight beside, five of the next fifteen turns were rests (HP 732 -> 479), and it died
    # 3-23 game ticks before the Recall would have taken it (spells-world.cpp: 15-35 ticks).
    if (beside := [monster for monster in _fight_targets(ctx) if monster.distance <= 1]) and (
            key := _engage(ctx, beside)) is not None:
        return key
    if _damaged(ctx):
        return _rest_out_of_fire(ctx)
    policy.last_reason = RECALL_WAIT_REASON
    return WAIT_KEY


def _leave_by_exit(policy, snapshot, board) -> str | None:
    """Owner 2026-11-04 (QUEST_25 room_sweep ``exit_when_out_of_healing``, 「薬を使い切っていたら
    踏んで良い」): the Healing used up, HP at the panic line (PANIC_HP_RATIO) and the start stair
    within a few steps: walk there and take it (quest_room_sweep ``_leave_by_exit``).  The room
    sweep's own order holds it; the phase battle that replaced the sweep on this floor dropped it
    (n1-c life-178 decision 5216: HP 81 of 503 on [11,1], no Healing, the stair [13,1] two steps
    off, and the phase walked back to the tome).  On the quiet board too: the tome that hits
    from out of sight leaves no enemy on the board between its breaths."""
    ctx = _ctx(policy, snapshot)
    plan = {**ctx.profile.engagement_plan["room_sweep"], "left_alone_races": ()}
    return quest_room_sweep._leave_by_exit(policy, snapshot, ctx.navigator, plan, board)


def walk_key(policy, snapshot) -> str | None:
    """A quiet board reached through the navigator: the phase's step."""
    ctx = _ctx(policy, snapshot)
    if ctx is None:
        return None
    _observe(ctx)
    return _phase_key(policy, snapshot)


def describe(policy, snapshot) -> dict | None:
    """The running phase and the kill ledger (for a test or a decision log)."""
    ctx = _ctx(policy, snapshot)
    if ctx is None:
        return None
    phase = current_phase(ctx)
    return {"phase": None if phase is None else phase.name, "kills": dict(ctx.battle.kills),
            "ready": ctx.battle.ready, "absent": dict(ctx.battle.absent)}
