"""Q2 (下水道): the game's kill line of a placed race counts toward its placements.

Recorded n1-b life-338 (Magic-Eater Lv22, 2026-11-07 17:01): the white crocodile
(race 1044, one placement at [19,11]) came out of its pool and was killed in melee
beside [15,23] (「白ワニを葬り去った。」).  Its phase still asked to see [19,11] empty.
That cell is deep water (lib/edit/quests/002_TheSewer.jsonc 'm'), deep water is
barred once the blue icky things are cleared, the cells around it are granite or
deep water, and the light radius was 1, so no cell the route may stand on certifies
it.  With every vantage visited the phase waited (quest:blocked:q2-phase-1044)
until the loop detector stopped the bot.

The quest's monsters are only the placed ones: a quest floor never allocates new
monsters (world-turn-processor.cpp decide_alloc_monster: ``!floor.is_in_quest()``).
So once the kill lines of a race reach the number of its placements on the map, every
one of them is dead and each placement counts as cleared (``_q2_surveyed_placements``).
Multipliers (Q2_BREEDER_RACES, or a race that can multiply) are left out: their
offspring die with the same line.

The kill lines are the player's attack (monster-damage.cpp: 「…を殺した。」,
「…を葬り去った。」, 「…を倒した。」, each also after 「せっかくだから」) and the
died message (monrace-definition.cpp get_died_message: 「…は死んだ。」), by the race's
name; a line repeated on one board carries the game's 「 <xN>」 counter.  An unseen
victim (何か) names no race and does not count.
"""
from __future__ import annotations

import re
from collections import Counter

from hengbot.game_messages import ECHIZEN_PREFIX, ECHIZEN_PREFIX_EN, KILL_LINES, KILL_LINES_EN
from hengbot.model import Position
from hengbot.policy_constants import Q2_BREEDER_RACES

QUEST_ID = 2
_RECORD = "_q2_kill_credit"
_KILL_LINES = KILL_LINES
_KILL_LINES_EN = KILL_LINES_EN
_ECHIZEN = (ECHIZEN_PREFIX, ECHIZEN_PREFIX_EN)
_REPEAT = re.compile(r" <x([1-9]\d*)>$")


def _killed(message: str) -> tuple[str, int] | None:
    """(victim's name, times) of a kill line, else None."""
    times = 1
    repeat = _REPEAT.search(message)
    if repeat is not None:
        times = int(repeat.group(1))
        message = message[:repeat.start()]
    for prefix in _ECHIZEN:
        message = message.removeprefix(prefix)
    for line in _KILL_LINES:
        if message.endswith(line):
            return message[:-len(line)], times
    for line in _KILL_LINES_EN:
        if message.lower().startswith(line.lower()) and message.endswith("."):
            name = message[len(line):-1]
            return name.removeprefix("the ").removeprefix("The "), times
    if message.endswith(" dies.") or message.endswith(" is destroyed."):
        name = message.rsplit(" ", 2 if message.endswith(" is destroyed.") else 1)[0]
        return name.removeprefix("the ").removeprefix("The "), times
    return None


def observe(policy, snapshot) -> None:
    """Count this board's kill lines on Q2; credit a race whose placements are all dead."""
    info = policy._quest_knowledge.get(QUEST_ID)
    battlefield = info.battlefield if info is not None else None
    if snapshot.floor_key[2] != QUEST_ID or battlefield is None:
        setattr(policy, _RECORD, None)
        return
    record = getattr(policy, _RECORD, None)
    if record is None or record[0] != snapshot.floor_key:
        record = (snapshot.floor_key, Counter(), None)
    floor, kills, last_board = record
    board = (snapshot.turn, tuple(snapshot.messages))
    if board == last_board:
        # The same board decided again (prime, then choose_key): counted once.
        return
    placements: dict[int, list[Position]] = {}
    for raw_position, race_id in battlefield.monster_placements:
        knowledge = policy._monrace_knowledge.get(race_id)
        if race_id in Q2_BREEDER_RACES or (knowledge is not None and knowledge.can_multiply):
            continue
        placements.setdefault(race_id, []).append(Position(*raw_position))
    names = {
        name: race_id
        for race_id in placements
        for name in getattr(policy._monrace_knowledge.get(race_id), "names", ())
        if name
    }
    for message in snapshot.messages:
        killed = _killed(message)
        if killed is None or killed[0] not in names:
            continue
        kills[names[killed[0]]] += killed[1]
    for race_id, cells in placements.items():
        if kills[race_id] >= len(cells):
            policy._q2_surveyed_placements.update(cells)
    setattr(policy, _RECORD, (floor, kills, board))
