"""Quest 25's phase battle (quest25_battle): the phases of the start region and the hall.

The ambush, the wall-passers, the Ipsissimus (the rally on a choke and the restock's Recall) and the
stragglers: the first four rows of quest25_battle ``PHASES``.

Imports quest25_battle_board, _attack and _walk; the running phase is read from quest25_battle at
call time (its phase table imports this module).

Split from quest25_battle.py (maintainability review 2026-11-23 (a)-8, behaviour unchanged).
"""

from __future__ import annotations

from hengbot import (
    once_quest_recall, quest25_geometry as geo, quest_entry_supply, quest_exposure, quest_plan_base,
    quest_room_light,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position
from hengbot.unseen_strike import message_text
from hengbot.quest25_battle_board import (
    _Ctx, _ctx, _escaped_count, _ipsissimus_alive, _killed_name, _LATER_IMMOBILE, _names, _seen_at, _sights,
    CHOKE_BACK_REASON, CLOSE_REASON, ENGAGE_REASON, ENLIGHTEN_REASON, melee_is_fewer, RESTOCK_RECALL_REASON,
    TELEPORT_REASON,
)
from hengbot.quest25_battle_attack import (
    _engage, _fight_targets, _fire_at, _fire_options, _has_piercing, _haste, _hold, _prepare,
)
from hengbot.quest25_battle_walk import (
    _open_key, _path, _refused, _step, _trap_key, _unlatch_stale, _walk, _walk_to_sight,
)


# -- the phases -------------------------------------------------------------------------


def _ambush_done(ctx: _Ctx) -> bool:
    return all(ctx.kills(race) >= geo.ROSTER[race]
               for race in (geo.HOUND, geo.SKELETAL_T, geo.VAMPIRE, geo.SPECTRAL_T))


def _ambush_enlightenment(ctx: _Ctx) -> str | None:
    """Owner 2026-11-07 「Q25の段階1、待ち伏せ中に安全で啓蒙の薬を持っているなら飲むを追加」, 安全 being
    「攻撃が届く範囲に=視界内に敵がいない」: no hostile in view (a detected one out of sight does not
    count), the carried Potion of Enlightenment is drunk, once per floor visit.  The game:
    quaff-effects.cpp wiz_lite maps and lights the whole level and shows no monster."""
    if ctx.battle.enlightened or ctx.seen_hostiles():
        return None
    potion = quest_room_light.carried_potion(ctx.policy, ctx.snapshot, quest_room_light.ROOM_LIGHT_POTION)
    if potion is None:
        return None
    key = reserved_item_command(ctx.policy, ctx.snapshot, "quaff", potion)
    if key is not None:
        ctx.battle.enlightened = True
        ctx.policy.last_reason = ENLIGHTEN_REASON
    return key


def _door_to_close(ctx: _Ctx, door) -> bool:
    """An open door on ``door``, the one ``c`` closes beside the player.

    do_cmd_close (cmd-open-close.cpp) takes the direction itself only when easy_open counts
    exactly one open door around the player (count_doors_traps, GridCountKind::OPEN); with none
    it asks 「方向 (ESCで中断)?」.  n1-c life-207 (2026-11-14 18:49:13): the west door [9,1] was
    gone (the board shows FLOOR there since 17:24), the restarted process began the ambush again
    (its battle record was of a later game turn than the reloaded save, quest25_battle_record),
    keyed 'c' on [10,1], and the direction prompt stopped the bot (stuck-prompt)."""
    grid = ctx.snapshot.grid_at(Position(*door))
    return grid is not None and grid.known and grid.is_door and not grid.is_closed_door


def _ambush(ctx: _Ctx) -> str | None:
    battle = ctx.battle
    if (potion := _ambush_enlightenment(ctx)) is not None:
        return potion
    if battle.style is None:
        battle.style = "melee" if melee_is_fewer(ctx.policy, ctx.snapshot, geo.SPECTRAL_T) else "ranged"
    targets = _fight_targets(ctx)
    if targets and (haste := _haste(ctx)) is not None:
        return haste      # 「どちらにせよ加速を使用する」
    door = geo.WEST_DOOR
    if battle.style == "ranged":
        if (key := _engage(ctx, targets)) is not None:
            return key
        if ctx.door_closed(door):
            if quest_exposure.game_distance(ctx.here, door) <= 1:
                _unlatch_stale(ctx, door)
                return _open_key(ctx, door)
            return _walk(ctx, {(door[0] + 1, door[1])})
        return _walk(ctx, {geo.MEET_RANGED}) or _hold(ctx)
    # Melee: the closed door, met the turn it opens (「相手が開けたターンに接敵」).
    beside = [monster for monster in targets if monster.distance <= 1]
    if beside:
        return _engage(ctx, beside)
    if ctx.here != geo.MEET_MELEE:
        return _walk(ctx, {geo.MEET_MELEE}) or _hold(ctx)
    if not ctx.door_closed(door):
        coming = [monster for monster in targets
                  if quest_exposure.game_distance((monster.position.y, monster.position.x), door) <= 1]
        if coming:
            return _step(ctx, door, ENGAGE_REASON)
        if not targets and _door_to_close(ctx, door):
            # 'c' + direction: observed_input sends the 'c' alone and releases the direction only at
            # the observed question (easy_open closes the one open door beside, asking none).
            return quest_plan_base.plan_door(ctx.policy, ctx.snapshot, door, CLOSE_REASON, close=True)
    return _hold(ctx)


def _wall_passers_done(ctx: _Ctx) -> bool:
    return (ctx.kills(geo.SPECTRE) >= geo.ROSTER[geo.SPECTRE]
            and ctx.kills(geo.SHADOW) >= geo.ROSTER[geo.SHADOW])


def _wall_passers(ctx: _Ctx) -> str | None:
    targets = _fight_targets(ctx)
    if (key := _engage(ctx, targets)) is not None:
        return key
    return _walk(ctx, {geo.WALL_PASSER_STAND}) or _hold(ctx)


def _ipsissimus_done(ctx: _Ctx) -> bool:
    return not _ipsissimus_alive(ctx)


def _match_strong(ctx: _Ctx, entries) -> list:
    """Each remembered (race, cell) with the hostile of its race now in view or sensed nearest to
    the cell (None when none is left): the game's monster index is no name, compact_monsters
    reorders it (monster-compaction.cpp, every turn the floor holds 32 dead slots)."""
    left = list(ctx.hostiles())
    matched = []
    for race, cell in entries:
        same = [monster for monster in left if monster.race_id == race]
        if not same:
            matched.append(None)
            continue
        monster = min(same, key=lambda each: quest_exposure.game_distance(
            (each.position.y, each.position.x), cell))
        left.remove(monster)
        matched.append(monster)
    return matched


def _note_strong(ctx: _Ctx) -> None:
    """Owner 2026-11-11 「隘路で待って倒す」: the summons Teleportation was read from are remembered
    (owner 2026-11-09 「起きた敵も最後の位置を覚える」) until killed or not seen for the plan's wait.

    Each decided board: the cell of one in view or sensed is renewed and the wait starts over; a
    kill line naming its race forgets one of that race; with none of them seen the board counts,
    and ``wait_limits.quiet_actions`` such boards (the phase-2 wait owner 2026-11-06 「50ターン待っ
    ても来なくなったら」 bounds) forget them all: it went elsewhere."""
    battle = ctx.battle
    if not battle.strong:
        battle.strong_quiet = 0
        return
    strong = list(battle.strong)
    for message in ctx.snapshot.messages:
        victim = _killed_name(message_text(message))
        if victim is None:
            continue
        killed = next((entry for entry in strong if victim in _names(ctx.policy, entry[0])), None)
        if killed is not None:
            strong.remove(killed)
    matched = _match_strong(ctx, strong)
    strong = [(race, cell if monster is None else (monster.position.y, monster.position.x))
              for (race, cell), monster in zip(strong, matched)]
    seen = any(monster is not None for monster in matched)
    battle.strong_quiet = 0 if seen else battle.strong_quiet + 1
    if battle.strong_quiet >= ctx.values.quiet_actions:
        strong, battle.strong_quiet = [], 0
    battle.strong = tuple(strong)


def _remember_strong(ctx: _Ctx, summons) -> None:
    """The summons in view join the remembered ones; one of a race already remembered is it."""
    kept = list(ctx.battle.strong)
    for monster in summons:
        same = [entry for entry in kept if entry[0] == monster.race_id]
        if same:
            kept.remove(same[0])
    ctx.battle.strong = tuple(kept) + tuple(
        (monster.race_id, (monster.position.y, monster.position.x)) for monster in summons)
    ctx.battle.strong_quiet = 0


def _rally(ctx: _Ctx) -> str | None:
    """After the teleport: 「接敵する前に移動できるなら、なるべく隘路に陣取る」.

    Owner 2026-11-11 「隘路で待って倒す」 (n1-c life-195): 「仕切り直しの隘路（召喚を受けないマス）で、最後に
    見えた強敵が来るのを待って迎え撃つ。倒してから立ち位置へ戻る。HP の線を切ったら今の決まりで立て直す。」
    While a summons Teleportation was read from is remembered (``_note_strong``), the choke holds
    and does not end when no enemy is in view; the walk to it never goes toward one: no choke
    within two cells of where one is (or was last seen), no cell beside one crossed, and with one
    in view no step onto a cell nearer to it than the player stands.  The rally ends on the choke
    with none remembered and none in view; the phase then rests to full HP again before its walk
    to [7,1] (phase2 「全快して(7,1)に移動」).  The HP line and the instant death answer above the
    plan, as before."""
    battle = ctx.battle
    targets = _fight_targets(ctx)
    summons = geo.summon_cells(ctx.terrain)
    chokes = {cell for cell in ctx.navigator.battlefield.chokepoints if cell not in summons}
    if any(monster.distance <= 1 for monster in targets):
        # Owner 2026-11-16 「隘路で迎え撃ち」: with one beside, the walk back to the nearest choke a
        # free way reaches (owner 2026-11-17 「空いている道で一番近い隘路まで下がる」) and the fight
        # is there, not on a cell the summons reaches (n1-a life-528 fought on [4,1] beside the
        # choke [3,1] and was summoned on, board after board; n1-a life-529 on [5,2], two steps
        # from [7,1]).
        return _choke_step_back(ctx, chokes) or _engage(ctx, targets)
    if ctx.here in chokes:
        if targets:
            return _engage(ctx, targets) or _hold(ctx)
        if battle.strong:
            return _hold(ctx)
        battle.rallying = False
        battle.ready = False
        return None
    cells = [cell for _, cell in battle.strong]
    seen = [cell for (_, cell), monster in zip(battle.strong, _match_strong(ctx, battle.strong))
            if monster is not None]
    near = {(y + dy, x + dx) for (y, x) in cells for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
    near |= {cell for cell in ctx.terrain
             if any(quest_exposure.game_distance(cell, each) < quest_exposure.game_distance(ctx.here, each)
                    for each in seen)}
    # Never toward it (owner 2026-11-11, n1-c life-195 walked west into the dracolich's breaths).
    goals = {cell for cell in chokes
             if all(quest_exposure.game_distance(cell, each) > 2 for each in cells)
             and all(quest_exposure.game_distance(cell, each) >= quest_exposure.game_distance(ctx.here, each)
                     for each in seen)}
    return (_walk(ctx, goals, taken=frozenset(near - {ctx.here})) or _engage(ctx, targets)
            or (_hold(ctx) if battle.strong else None))


def _choke_step_back(ctx: _Ctx, chokes) -> str | None:
    """Off the chokes, the next step toward the nearest free choke a walk over free cells reaches
    (the fewest steps of ``_path``'s walk; among equals the phase's own stand [7,1], phase2
    「(7,1)に移動」; then the grid's order), else None: the fight is where the player stands.

    Owner 2026-11-17 (n1-a life-529, 「隘路が2歩以上先の時はどうしますか？」 → 「空いている道で一番近い
    隘路まで下がる」): on the look-out [5,2] the summons came beside; the nearest choke [7,1] was two
    steps away by [6,1] (a cell the summons reaches), both free at decisions 36485-36486, and the
    fight stayed on [5,2] until the death.  Asked again each board: a way that closes (a monster
    on it) leaves the fight where the player stands."""
    if ctx.here in chokes:
        return None
    occupied = frozenset((monster.position.y, monster.position.x) for monster in ctx.hostiles())
    free = sorted(cell for cell in chokes if cell not in occupied and cell not in _refused(ctx))
    walks = [(len(path), cell != geo.PHASE2_WALK[0], cell, path)
             for cell in free for path in (_path(ctx, {cell}, occupied),) if len(path) >= 2]
    if not walks:
        return None
    nxt = min(walks)[3][1]
    if (trap := _trap_key(ctx, nxt)) is not None:
        return trap
    return _step(ctx, nxt, CHOKE_BACK_REASON)


# Owner 2026-11-16 (n1-a life-528, answer A 「隘路で迎え撃ち尽きる前に帰還」): in phase 2, three
# look-outs in a row summoned on and back to the choke with no shot at the pen, or the Healing
# potions (Healing and stronger, quest_plan_base ``healing_potion_count``) down to two, and Word
# of Recall is read to restock -- the quest fails; survival first (owner 2026-11-09).
# 2026-11-27 (supervisor, n1-c life-223): the potions count only when this quest spent them down
# to the floor (quest_entry_supply ``spent_to_floor``): the row asks as few as two
# (``required_force.over_match``), and a character entering with exactly two read Recall on phase
# 2's first board at full HP, none drunk.
LOOKOUT_LIMIT = 3
HEALING_FLOOR = 2


def healing_spent(policy, snapshot) -> bool:
    """The restock's potion arm: this quest drank its Healing potions down to ``HEALING_FLOOR``."""
    return quest_entry_supply.spent_to_floor(
        policy, snapshot, quest_entry_supply.HEALING,
        quest_plan_base.healing_potion_count(policy, snapshot), HEALING_FLOOR)


def _restock_recall(policy, snapshot) -> str | None:
    """Phase 2's leave to restock (``LOOKOUT_LIMIT`` / ``HEALING_FLOOR``): Word of Recall, read past
    the ONCE floor's hold (once_quest_recall ``read_key`` ``deliberate``); then, Recall active,
    the plan's own wait (``_recall_wait``: the start stair, else out of the casters' fire).  None
    off phase 2, within both counts (``healing_spent``), or with Recall already active."""
    from hengbot import quest25_battle  # its phase table (``PHASES``) imports this module

    ctx = _ctx(policy, snapshot)
    if ctx is None or snapshot.player.recalling:
        return None
    phase = quest25_battle.current_phase(ctx)
    if phase is None or phase.name != "ipsissimus":
        return None
    if ctx.battle.lookouts < LOOKOUT_LIMIT and not healing_spent(policy, snapshot):
        return None
    return once_quest_recall.read_key(policy, snapshot, RESTOCK_RECALL_REASON, deliberate=True)


def _ipsissimus(ctx: _Ctx) -> str | None:
    battle, policy, snapshot = ctx.battle, ctx.policy, ctx.snapshot
    if battle.rallying or battle.strong:
        if (key := _rally(ctx)) is not None:
            return key
        if not battle.rallying:
            # The rally ended on the choke on this board: one look-out came back (``lookouts``,
            # set back to 0 by a shot at the pen, ``_pen_shot``).
            battle.lookouts += 1
            if (key := _restock_recall(policy, snapshot)) is not None:
                return key
        # The rally ended on the choke on this board (``_rally``): the phase's preparation rests
        # there first (phase2 「全快して(7,1)に移動」), on a cell no summons reaches, not one step on.
        # n1-a life-528 (2026-11-16 13:12:42-13:13:10): the walk to the pen's sight left the choke
        # [3,1] short of full HP (784/1056 at 13:13:00) and rested on [4,1] the next board; each
        # of those five rests was answered by an Ipsissimus summons, the last one the fight it
        # died in.  ``_prepare`` answers None while the rally owns the board, so it is read once.
        from hengbot import quest25_battle  # its phase table (``PHASES``) imports this module

        if (key := _prepare(ctx, quest25_battle.current_phase(ctx))) is not None:
            return key
    seen = [monster for monster in ctx.hostiles() if monster.race_id == geo.IPSISSIMUS
            and (monster.position.y, monster.position.x) in geo.IPSISSIMUS_PEN]
    aim = (seen[0].position.y, seen[0].position.x) if seen else geo.IPSISSIMUS_AIM
    # Owner 2026-11-09 「Q25 の全部の段に広げる」 (``_unseen_fire``): no arrow at the pen it does not
    # see.  With no attack aimed at the grid, the walk goes to a cell that sees the pen instead of
    # [5,1]; seen there, the fire is from there.  Every such cell reached with none seen: they are
    # out of the pen (the pen's 「当たらない撃ちで補う」 reads the same: counted escaped).
    in_sight = bool(_seen_at(ctx, geo.IPSISSIMUS, geo.IPSISSIMUS_PEN))
    from_stand = in_sight or bool(_fire_options(ctx, aim, geo.IPSISSIMUS, missiles=False))
    walk = geo.PHASE2_WALK
    walking = from_stand and ((ctx.here not in walk and not in_sight)
                              or (ctx.here in walk and ctx.here != walk[-1]))
    others = [monster for monster in ctx.seen_hostiles() if monster.race_id != geo.IPSISSIMUS]
    summons = _summons_in_view(ctx, others)
    # Owner 2026-11-11 (n1-c life-195): the summons are weighed before the walk to the stand, not
    # after it -- a walk never goes on toward a summons the threat would teleport from.  A low
    # threat on the walk lets it go on (the summons are answered on [5,1] as before).
    threat = bool(summons) and policy._is_material_threat(snapshot, policy._physical_hostiles(snapshot))
    if summons and (threat or not walking):
        piercing = _has_piercing(ctx, geo.IPSISSIMUS, aim)
        # 「貫通可能な攻撃かつ脅威度が高くない場合は先にイプシシマスを倒し増援を断つ」, the threat read as the
        # 11-05 summon rule reads it (summon_response ``counter_shot_key``): 「見えている敵の3ターンの
        # 想定被害が今の HP の半分以上なら高い」.
        if not threat and piercing:
            return _pen_shot(ctx, _fire_at(ctx, aim, geo.IPSISSIMUS, piercing=True))
        # 「それ以外の場合はテレポートで仕切り直す。接敵する前に移動できるならなるべく隘路に陣取る」; what it is
        # read from is remembered and waited for on the choke (``_rally``, owner 2026-11-11).
        _remember_strong(ctx, summons)
        battle.rallying = True
        scroll = policy._find_teleport_scroll(snapshot) if policy._can_read_scrolls(snapshot) else None
        if scroll is not None:
            policy.last_reason = TELEPORT_REASON
            return policy._read_key(snapshot, scroll)
        # No Teleportation (owner 2026-11-12: none read up to phase 3): the rally's choke first
        # (owner 2026-11-16 「隘路で迎え撃ち」), the fight where the player stands only without one.
        return _rally(ctx) or _engage(ctx, summons)
    if from_stand:
        if ctx.here not in walk and not in_sight:
            return _walk(ctx, {walk[0]})
        if ctx.here == walk[0] and (haste := _haste(ctx)) is not None:
            return haste    # 「事前に加速して(6,1)(5,1)と移動」
        if ctx.here in walk and ctx.here != walk[-1]:
            return _step(ctx, walk[walk.index(ctx.here) + 1])
    if summons:
        # A low threat in the way of the walk: fought where the player stands, not teleported from.
        return _engage(ctx, summons) or _hold(ctx)
    piercing = bool(others) and _has_piercing(ctx, geo.IPSISSIMUS, aim)
    # The wall-passers' stragglers (the spectres and shadow demons the quiet wait of the
    # wall-passers' phase left alive) are no reinforcements and no reason to teleport: owner
    # 2026-11-09 「ここでテレポートすると以降の段取りが全て崩れるので逃走回数は最小にしたい。」  They are
    # ignored, beside the player or not (owner 2026-11-09 「無視して囲いを撃つ」, phase2 「イプシシマスとの
    # 戦闘中に出会った残党は無視する。イプシシマスを全て倒すかテレポートさせたあとで対処。」): the fire stays on
    # the pen, through them when it can; the stragglers' phase fights them on [5,1] afterwards.  The
    # survival rungs above the plan (the 1-turn 即死, the HP line) still answer first.
    if not from_stand:
        return _pen_sight(ctx, aim)
    return _pen_shot(ctx, _fire_at(ctx, aim, geo.IPSISSIMUS, piercing=piercing, missiles=in_sight))


def _pen_sight(ctx: _Ctx, aim) -> str | None:
    """Unseen, no attack aimed at the grid: to a cell that sees the pen's ``aim``; none left (each
    reached with no Ipsissimus seen), the ones not killed nor seen out nor sensed in the pen are
    counted escaped.

    Owner 2026-11-06 phase2: escaped is read from 「〜がテレポートした。」 (「テレポートしたメッセージで
    判断」) and, with neither telepathy nor evil ESP, from ten shots at [7,17] without a hit
    (「当たらない撃ちで補う」); this count is the walk's version of the latter.  So it is counted only
    when every cell that sees the pen was reached: with cells left and no way to them (a refused
    cell, the shunned movers; ``battle.no_way``) the phase holds, its attacks recharging, and an
    Ipsissimus telepathy or evil ESP senses in the pen is not escaped (n1-c life-207 tests,
    2026-11-14: with no way on from [10,1] all three were counted escaped at once and phase 2
    ended with them in the pen).  The hold with no way is the phase-2 wait (owner 2026-11-06
    「50ターン待っても来なくなったら」, ``wait_limits.quiet_actions``): that many holds in a row and
    the count is made as when every cell was reached (the same life's wall-passers held on [10,1]
    for over 5,300 decisions with no way on)."""
    battle = ctx.battle
    if (key := _walk_to_sight(ctx, aim, _sights(ctx, aim))) is not None:
        battle.pen_no_way = 0
        return key
    if _sights(ctx, aim) - {ctx.here} and battle.pen_no_way < ctx.values.quiet_actions:
        battle.pen_no_way += 1
        return _hold(ctx)
    sensed = sum(1 for monster in ctx.hostiles() if monster.race_id == geo.IPSISSIMUS
                 and (monster.position.y, monster.position.x) in geo.IPSISSIMUS_PEN)
    battle.assumed_escaped = max(0, geo.ROSTER[geo.IPSISSIMUS] - ctx.kills(geo.IPSISSIMUS)
                                 - _escaped_count(ctx, assumed=False) - sensed)
    return _hold(ctx) if sensed else None


def _summons_in_view(ctx: _Ctx, others) -> list:
    """Of the non-Ipsissimus in view on phase 2, the summoned ones; the rest are stragglers.

    A straggler (owner 2026-11-06 phase1_wall_passers / phase2) is a spectre or shadow demon of
    the roster that the wall-passers' phase left alive: it was on the floor before the phase, so
    it is not first seen on a board carrying a summon cast (summon_response's reading of the
    game's cast lines; ``Battle.summoned``), and there are no more of a race than the roster less
    the kills read.  Anything else -- another race, one first seen with a cast, one over that
    count -- is a summons.  The nearest are counted as stragglers first."""
    left = {race: max(0, geo.ROSTER[race] - ctx.kills(race)) for race in (geo.SPECTRE, geo.SHADOW)}
    summons = []
    for monster in sorted(others, key=lambda monster: monster.distance):
        if left.get(monster.race_id, 0) > 0 and monster.index not in ctx.battle.summoned:
            left[monster.race_id] -= 1
        else:
            summons.append(monster)
    return summons


def _pen_shot(ctx: _Ctx, key: str | None) -> str | None:
    ctx.battle.pen_shot = key is not None
    if key is not None:
        ctx.battle.lookouts = 0   # a look-out that shot at the pen is no fruitless one
    return key


def _stragglers_done(ctx: _Ctx) -> bool:
    left = (ctx.kills(geo.SPECTRE) < geo.ROSTER[geo.SPECTRE]
            or ctx.kills(geo.SHADOW) < geo.ROSTER[geo.SHADOW]
            or ctx.kills(geo.IPSISSIMUS) < geo.ROSTER[geo.IPSISSIMUS])
    return not left


def _stragglers(ctx: _Ctx) -> str | None:
    targets = [monster for monster in ctx.seen_hostiles()
               if monster.race_id not in _LATER_IMMOBILE - {geo.IPSISSIMUS} and not monster.can_multiply]
    if (key := _engage(ctx, targets)) is not None:
        return key
    return _walk(ctx, {geo.STRAGGLER_STAND}) or _hold(ctx)
