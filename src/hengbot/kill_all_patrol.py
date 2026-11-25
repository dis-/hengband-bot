"""A KILL_ALL quest whose plan has ended with the quest not won: detect, patrol, fight.

Owner 2026-11-13 (n1-b life-378, Quest 25): 「全滅クエストで作戦を完了しても終了しない場合、周回して
敵を探す。感知を持っていれば感知して敵を探す。」  Every fixed KILL_ALL quest (QuestKindType
KILL_ALL, type 6: lib/edit/quests 1, 2, 10-13, 16, 19-23, 25, 27, 29-34) is won only when every
monster on the floor is dead (quest.cpp check_quest_completion).  When the approved plan of such a
floor has ended -- no step left (``_quest_execute_key`` answered None, the navigator's
``quest:blocked:execute``) and no phase of it still running (``_plan_running``) -- this rung takes
over:

 1. a hostile known (seen, detected, or by telepathy, ESP shows it as detected): beside the player
    the blow, else a shot at one in view (quest_plan_base._shot, as the plans shoot), else the walk
    to it.  On an approved quest floor the navigator's answer ends the ladder (dungeon_ladder's
    plan-approved-quest layer), so no ordinary combat rung fights for this rung; else the walk to
    the cell a hostile was last seen or detected at (``_remember``: a detection shows it for one
    board only), forgotten when reached empty, the detection then asked again;
 2. a monster detection the character holds, once per round (asked again after a cast that failed,
    and after one whose prompt the menu walk closed, the list showing it charging or empty):
    the absorbed Rod of Detection, then the absorbed Staff of Detect Evil, then a carried rod or
    staff of them (detection.cpp detect_all shows every monster, Detect Evil only the evil); a
    rod list remembered charging from an earlier time is read again first (``_rod_read_key``);
 3. else the round: the nearest remembered floor cell no stand of this round came within
    ``COVER`` of, walked to; the round over, the next one starts with a new detection, up to
    ``ROUNDS`` rounds, then the named stop ``STOP_REASON``.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from hengbot import combat_answer, me_absorbed_substitutes, me_capability
from hengbot.item_reservation import reserved_item_command
from hengbot.model import (
    Position, SV_ROD_DETECTION, SV_STAFF_DETECT_EVIL, TVAL_ROD, TVAL_STAFF)
from hengbot.quest_knowledge import QUEST_TYPE_KILL_ALL

REASON = "quest-patrol"   # no word of the breeder window's attack guess (reasons)
WALK_REASON = f"{REASON}:walk"
HUNT_REASON = f"{REASON}:hunt"
MELEE_REASON = "quest-strategy:melee"   # the quest plans' blow
DETECT_REASON = f"{REASON}:detect"
# The absorbed detection's owner: me_device_attacks_input answers its kind question and power prompt
# from the game's list, and closes the prompt with ESC when the list shows the power charging or
# empty (me_absorbed_substitutes.cast).
ABSORBED_DETECT_REASON = DETECT_REASON + me_absorbed_substitutes.CAST_SUFFIX
POWERED_DETECT_REASON = f"{DETECT_REASON}:powerful"   # the rod through Powerful Activation
STOP_REASON = "quest:blocked:quest-patrol-rounds"
COVER = 4        # a cell within this many steps of a stand is looked at by the round
ROUNDS = 5       # rounds before the named stop
FAILED_LINES = ("うまく唱えられなかった", "うまく使えなかった", "failed to use", "You failed")
SENSED_LINES = ("の存在を感じとった", "sense the presence")


@dataclass
class Patrol:
    floor: tuple
    round: int = 0
    covered: set = field(default_factory=set)
    detected_round: int = -1
    detect_turn: int | None = None
    # monster index -> the cell a hostile was last seen or detected at (``_remember``)
    targets: dict = field(default_factory=dict)
    # the round whose detection read the rod list again (``_rod_read_key``)
    rod_read_round: int = -1


def applies(policy, snapshot) -> bool:
    quest = snapshot.quests.get(snapshot.floor_key[2]) if snapshot.floor_key[2] else None
    if quest is None or quest.status == 2:
        return False
    info = policy._quest_knowledge.get(quest.id)
    kind = info.type if info is not None else quest.type
    return kind == QUEST_TYPE_KILL_ALL


def _memory(policy, snapshot) -> Patrol:
    patrol = getattr(policy, "_kill_all_patrol", None)
    if patrol is None or patrol.floor != tuple(snapshot.floor_key):
        patrol = Patrol(tuple(snapshot.floor_key))
        policy._kill_all_patrol = patrol
    return patrol


def _plan_running(policy, snapshot) -> bool:
    """A plan of this floor with a phase still running owns every move of it: its own step, else
    none, never this patrol's (the patrol is the owner's 「作戦を完了しても終了しない場合」).

    n1-b life-382 (2026-11-13 05:38-05:39, Quest 25): the tome phase answered one board ('8' from
    [7,6], '4' from [4,8]) and nothing on the next, this rung walked that one back ('2' from [6,6],
    '6' from [4,7]), and the two alternated until the loop guard stopped the bot twice.  Q25 asks
    this rung itself once its last phase ended (quest25_battle._after_the_phases)."""
    from hengbot import quest25_battle   # the plan imports this module

    return quest25_battle.phases_left(policy, snapshot)


def key(policy, snapshot) -> str | None:
    """The rung's key on a KILL_ALL floor whose plan has ended; None elsewhere."""
    if not applies(policy, snapshot) or _plan_running(policy, snapshot):
        return None
    patrol = _memory(policy, snapshot)
    _settle_detection(patrol, snapshot)
    here = snapshot.player.position
    patrol.covered |= {(here.y + dy, here.x + dx) for dy in range(-COVER, COVER + 1)
                       for dx in range(-COVER, COVER + 1)}
    hostiles = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                if monster.hostile]
    _remember(patrol, snapshot, hostiles)
    # One no walk reaches is passed for the others remembered, the detection and the round (a None
    # here ended the room sweep by name, quest_room_sweep NOTHING_LEFT_REASON); it is asked again
    # on every board that shows it.
    if hostiles and (hunted := _hunt(policy, snapshot, hostiles)) is not None:
        return hunted
    if patrol.targets:
        hunted = _hunt_remembered(policy, snapshot, patrol)
        if hunted is not None:
            return hunted
    if patrol.detected_round < patrol.round and (read := _rod_read_key(policy, snapshot, patrol)) is not None:
        return read
    if patrol.detected_round < patrol.round and (detect := _detect_key(policy, snapshot)) is not None:
        patrol.detected_round, patrol.detect_turn = patrol.round, snapshot.turn
        return detect
    step = _toward(policy, snapshot, lambda cell: cell not in patrol.covered)
    if step is not None:
        policy.last_reason = WALK_REASON
        return policy._step_toward(snapshot, step)
    if patrol.round + 1 >= ROUNDS:
        policy.last_reason = STOP_REASON
        return "5"
    patrol.round += 1
    patrol.covered = set()
    policy.last_reason = WALK_REASON
    return "5"


def _settle_detection(patrol: Patrol, snapshot) -> None:
    """The board after a cast: one that failed is asked again this round, and so is one the menu
    walk closed: the game's list on the board shows the power charging or empty and no game time
    passed (cmd-magiceat.cpp select_magic_eater returns nullopt on ESC and do_cmd_magic_eater
    resets the energy), so the next detection is chosen from that list."""
    if patrol.detect_turn is None:
        return
    if snapshot.turn == patrol.detect_turn:
        if getattr(snapshot, "magic_eater_power_list", None) is not None:
            patrol.detected_round = patrol.round - 1
            patrol.detect_turn = None
        return
    texts = [str(getattr(message, "text", message)) for message in snapshot.messages]
    if any(line in text for text in texts for line in FAILED_LINES) and not any(
            line in text for text in texts for line in SENSED_LINES):
        patrol.detected_round = patrol.round - 1
    patrol.detect_turn = None


def _remember(patrol: Patrol, snapshot, hostiles) -> None:
    """Keep the cell each hostile was last seen or detected at, and forget one whose cell the
    player reached without it showing there.

    A detection marks a monster for that board only (spells-detection.cpp detect_monsters_normal
    sets MFLAG2_MARK and SHOW; the next player turn clears them), so the board after the cast no
    longer lists one that neither the eye nor telepathy shows.  n1-b life-413 (2026-11-22 01:47,
    Quest 25, every phase over): the absorbed Rod of Detection showed the Nexus quylthulg left
    (MonraceDefinitions 480: NEVER_MOVE, INVISIBLE, EMPTY_MIND, BLINK) at [5,17] (turn 2585620),
    the patrol stepped once toward it, and from the next board on walked its round elsewhere; the
    other four rounds' detections were the Staff of Detect Evil (the quylthulg is not evil) and
    the named stop came at turn 2589517.  The owner's 「感知して敵を探す」 (2026-11-13) finds the
    enemy to kill it, so the found cell is walked to as the owner's 「起きた敵も最後の位置を覚える」
    (2026-11-09) keeps an awake enemy's last cell.  A cell reached empty (the quylthulg blinks
    when the player comes in view) is forgotten and the detection is asked again this round."""
    for monster in hostiles:
        patrol.targets[monster.index] = (monster.position.y, monster.position.x)
    known = {monster.index for monster in hostiles}
    here = snapshot.player.position
    lost = [index for index, (y, x) in patrol.targets.items()
            if index not in known and max(abs(y - here.y), abs(x - here.x)) <= 1]
    for index in lost:
        del patrol.targets[index]
    if lost:
        patrol.detected_round = min(patrol.detected_round, patrol.round - 1)


def _hunt_remembered(policy, snapshot, patrol: Patrol) -> str | None:
    """The step toward the nearest remembered hostile's cell; one no remembered walk reaches is
    forgotten."""
    here = snapshot.player.position
    for index, (y, x) in sorted(patrol.targets.items(),
                                key=lambda item: max(abs(item[1][0] - here.y), abs(item[1][1] - here.x))):
        step = _toward(policy, snapshot, lambda cell, y=y, x=x: max(abs(cell[0] - y), abs(cell[1] - x)) <= 1)
        if step is not None:
            policy.last_reason = HUNT_REASON
            return policy._step_toward(snapshot, step)
        del patrol.targets[index]
    return None


def _hunt(policy, snapshot, hostiles) -> str | None:
    """The blow beside, else the shot in view, else the step toward the nearest.

    n1-c life-208 (2026-11-15 04:48, Quest 25, every phase over): the Nexus quylthulg left
    (MonraceDefinitions 480: NEVER_MOVE, INVISIBLE, BLINK and TELE_AWAY 1_IN_1; the player sees
    invisible) was in view at 3, 2 and 6 grids and this rung only walked toward it; each time it
    teleported the player away, the five rounds ran out and ``STOP_REASON`` repeated until the
    loop guard stopped the bot (twice, then the escalation)."""
    here = snapshot.player.position
    beside = [monster for monster in hostiles if max(abs(monster.position.y - here.y),
                                                     abs(monster.position.x - here.x)) <= 1]
    if beside:
        answer = combat_answer.adjacent_attack(policy, snapshot, beside[:1], MELEE_REASON)
        if answer is not None and answer.key is not None:
            return answer.key
    from hengbot import quest_plan_base   # it imports the navigator, which imports this module

    in_view = sorted((monster for monster in snapshot.visible_monsters
                      if monster.hostile and monster not in beside),
                     key=lambda monster: here.distance_to(monster.position))
    for target in in_view:
        shot = quest_plan_base._shot(policy, snapshot, target)
        if shot is not None:
            return shot
    nearest = min(hostiles, key=lambda monster: here.distance_to(monster.position))
    target = nearest.position
    step = _toward(policy, snapshot, lambda cell: max(abs(cell[0] - target.y),
                                                      abs(cell[1] - target.x)) <= 1)
    if step is None:
        return None
    policy.last_reason = HUNT_REASON
    return policy._step_toward(snapshot, step)


def _toward(policy, snapshot, goal) -> Position | None:
    """The first step of the shortest remembered walk to a cell ``goal`` accepts, never into a
    cell the walks' one veto holds (``policy._walk_veto``: the cells an owner left, the
    engagement areas, an unseen attacker's area), as the explore (owner 2026-11-15,
    maintainability review Q3 「全部読ませる」; it read the left cells only before)."""
    start = snapshot.player.position
    refused = policy._walk_veto(snapshot)
    seen, queue = {start}, deque([(start, None)])
    while queue:
        cell, first = queue.popleft()
        if first is not None and goal((cell.y, cell.x)):
            return first
        for neighbor in policy._walkable_neighbors(snapshot, cell):
            if neighbor not in seen and neighbor not in refused:
                seen.add(neighbor)
                queue.append((neighbor, first if first is not None else neighbor))
    return None


def _rod_read_key(policy, snapshot, patrol: Patrol) -> str | None:
    """Browse the rod list (``bC``, no game time: me_powers_refresh) once a round when the
    remembered list shows the absorbed Rod of Detection not ready and game time has passed since
    the game displayed it.

    The rods recharge every regeneration tick (hp-mp-regenerator.cpp regenmagic), but the
    remembered row is the one the game last displayed.  n1-b life-413 (2026-11-22, Quest 25): the
    rod list shown charging at turn 2586235 stayed the remembered one, so the next three rounds'
    detections (turns 2587075, 2587878, 2588757) were the Staff of Detect Evil, which never shows
    the Nexus quylthulg left (not evil; the owner 2026-11-13: 邪悪感知だけでは邪悪でない敵が映らない)."""
    ident = me_absorbed_substitutes.DETECTION[0]
    kind, sval = ident
    if (patrol.rod_read_round >= patrol.round
            or not me_capability.has(policy, snapshot, kind, sval)
            or me_capability.charges(policy, snapshot, kind, sval) > 0):
        return None
    shown = (getattr(policy, "_me_device_lists", None) or {}).get(kind)
    if shown is None or shown[0] >= snapshot.turn:
        return None
    if snapshot.player.confused or snapshot.player.paralyzed:
        return None
    from hengbot import me_powers_refresh

    patrol.rod_read_round = patrol.round
    browse = "b" + me_powers_refresh.KIND_LETTER[kind]
    policy.last_reason = me_powers_refresh.REFRESH_REASON
    policy._offer_execution(
        browse, producer="bookkeeping", work_id="quest-patrol-rod-read",
        next_step="magic-eater.browse.send", arguments=(kind,),
        expected_effect="magic-eater-power-list-observed")
    return browse


def _powered_detect_all_key(policy, snapshot) -> str | None:
    """The absorbed Rod of Detection through Powerful Activation (``U`` + rod + its letter) when it
    is ready and 「安全なら」 (me_powers._when_safe: no hostile in view, not just hit, the HP cost
    above the ladder's low-HP rungs).

    Owner 2026-11-01 「全感知が使用可能なら...安全なら強力発動で使う」, and 2026-11-22 (n1-b life-413,
    Quest 25) 「全感知の強力発動ならクエスト全域をカバーできるはずだが」: rod_effect's powerful
    detect_rad is DETECT_RAD_DEFAULT * 3 / 2 = 45 (cmd-item/cmd-zaprod.cpp:50; 30 unpowered,
    spells-detection.cpp detect_monsters_normal measures Grid::calc_distance, the rounded
    Euclidean distance), so one cast reaches the whole of a fixed quest map from any cell of it
    with room to spare (Quest 25's corners [1,1] and [13,29] are 30 apart; a DARKNESS dungeon
    divides the radius by 3).
    me_powerful_activation_input answers the racial, kind and power prompts (a power the list shows
    charging is closed with ESC, no HP paid)."""
    player = snapshot.player
    if player.blind or player.confused or player.hallucinated or player.paralyzed:
        return None
    kind, sval = me_absorbed_substitutes.DETECTION[0]
    from hengbot import me_powerful_activation   # it imports the device tables

    if (not me_capability.has(policy, snapshot, kind, sval)
            or me_capability.charges(policy, snapshot, kind, sval) <= 0
            or me_powerful_activation.activatable(kind, sval) is None
            or any(monster.hostile for monster in snapshot.visible_monsters)
            or getattr(policy, "_took_damage", False)
            or not me_powerful_activation.pays_safely(policy, snapshot)):
        return None
    policy.last_reason = POWERED_DETECT_REASON
    return me_powerful_activation.racial_key(kind, sval)


def _detect_key(policy, snapshot) -> str | None:
    """The absorbed detection under its menu owner (``ABSORBED_DETECT_REASON``), else a carried one.

    The remembered list is the one the game last displayed, so after a cast it still shows the
    rod ready while it charges.  n1-c life-208 (2026-11-15 04:48 and 04:49, Quest 25): this rung
    sent ``mCg`` under its bare reason, no table of me_device_attacks_input owned it, and with the
    Rod of Detection charging the game kept 「('*'で一覧, ESCで中断) どの魔力を使いますか？」 over
    「g) 全感知 充填: 1/ 1」 unanswered (``stuck-prompt owner=quest-patrol:detect ... reason=unowned``)
    twice; the Anaguma pocket had stopped the same way (n1-c life-187/191)."""
    player = snapshot.player
    if (powered := _powered_detect_all_key(policy, snapshot)) is not None:
        return powered
    for ident in me_absorbed_substitutes.DETECTION:
        # The game refuses the ``m`` command only while confused (cmd-magiceat.cpp
        # do_cmd_magic_eater cmd_limit_confused): a blind or hallucinating player casts it too.
        cast = me_absorbed_substitutes.cast(policy, snapshot, ident, DETECT_REASON,
                                            blind_ok=True, hallucination_ok=True)
        if cast is not None:
            return cast
    if player.blind or player.confused:
        return None
    for tval, sval, verb in ((TVAL_ROD, SV_ROD_DETECTION, "rod"),
                             (TVAL_STAFF, SV_STAFF_DETECT_EVIL, "staff")):
        item = next((item for item in snapshot.inventory if item.tval == tval and item.sval == sval
                     and item.known and not item.charging and (tval == TVAL_ROD or item.charges > 0)),
                    None)
        if item is not None:
            used = reserved_item_command(policy, snapshot, verb, item)
            if used is not None:
                policy.last_reason = DETECT_REASON
                return used
    return None
