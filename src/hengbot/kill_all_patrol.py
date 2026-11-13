"""A KILL_ALL quest whose plan has ended with the quest not won: detect, patrol, fight.

Owner 2026-11-13 (n1-b life-378, Quest 25): 「全滅クエストで作戦を完了しても終了しない場合、周回して
敵を探す。感知を持っていれば感知して敵を探す。」  Every fixed KILL_ALL quest (QuestKindType
KILL_ALL, type 6: lib/edit/quests 1, 2, 10-13, 16, 19-23, 25, 27, 29-34) is won only when every
monster on the floor is dead (quest.cpp check_quest_completion).  When the approved plan of such a
floor has ended -- no step left (``_quest_execute_key`` answered None, the navigator's
``quest:blocked:execute``) and no phase of it still running (``_plan_running``) -- this rung takes
over:

 1. a hostile known (seen, detected, or by telepathy, ESP shows it as detected): beside the player
    the blow, else the walk to it (the fight then goes by the floor's ordinary combat rungs);
 2. a monster detection the character holds, once per round (re-read after a cast that failed):
    the absorbed Rod of Detection, then the absorbed Staff of Detect Evil, then a carried rod or
    staff of them (detection.cpp detect_all shows every monster, Detect Evil only the evil);
 3. else the round: the nearest remembered floor cell no stand of this round came within
    ``COVER`` of, walked to; the round over, the next one starts with a new detection, up to
    ``ROUNDS`` rounds, then the named stop ``STOP_REASON``.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from hengbot import combat_answer, left_cells, me_capability, me_powers
from hengbot.item_reservation import reserved_item_command
from hengbot.model import (
    Position, SV_ROD_DETECTION, SV_STAFF_DETECT_EVIL, TVAL_ROD, TVAL_STAFF)
from hengbot.quest_knowledge import QUEST_TYPE_KILL_ALL

REASON = "quest-patrol"   # no word of the breeder window's attack guess (reasons)
WALK_REASON = f"{REASON}:walk"
HUNT_REASON = f"{REASON}:hunt"
MELEE_REASON = "quest-strategy:melee"   # the quest plans' blow
DETECT_REASON = f"{REASON}:detect"
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
    if hostiles:
        return _hunt(policy, snapshot, hostiles)
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
    """The board after a cast: one that failed is asked again this round."""
    if patrol.detect_turn is None or snapshot.turn == patrol.detect_turn:
        return
    texts = [str(getattr(message, "text", message)) for message in snapshot.messages]
    if any(line in text for text in texts for line in FAILED_LINES) and not any(
            line in text for text in texts for line in SENSED_LINES):
        patrol.detected_round = patrol.round - 1
    patrol.detect_turn = None


def _hunt(policy, snapshot, hostiles) -> str | None:
    here = snapshot.player.position
    beside = [monster for monster in hostiles if max(abs(monster.position.y - here.y),
                                                     abs(monster.position.x - here.x)) <= 1]
    if beside:
        answer = combat_answer.adjacent_attack(policy, snapshot, beside[:1], MELEE_REASON)
        if answer is not None and answer.key is not None:
            return answer.key
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
    cell an owner left (left_cells)."""
    start = snapshot.player.position
    refused = left_cells.refused(policy, snapshot)
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


def _detect_key(policy, snapshot) -> str | None:
    player = snapshot.player
    for ident in (("rod", SV_ROD_DETECTION), ("staff", SV_STAFF_DETECT_EVIL)):
        if (not player.confused and me_capability.has(policy, snapshot, *ident)
                and me_capability.charges(policy, snapshot, *ident) > 0):
            power = me_powers.BY_KEY.get(ident)
            if power is not None:
                policy.last_reason = DETECT_REASON
                return power.key
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
