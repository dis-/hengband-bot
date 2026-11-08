"""q2-crocodile-kill-1107: a killed white crocodile clears its placement's phase.

Recorded: n1-b life-338 (Magic-Eater Lv22) in Q2 下水道, 2026-11-07 17:00:5x-17:01:56
(tests/fixtures/q2-crocodile-kill-20261107.json.gz, tests/extract_q2_crocodile_kill_1107_fixture.py).
At turn 1160275 the white crocodile (race 1044, the quest's one 'm' placement at [19,11])
died in melee beside [15,23] (「白ワニを葬り去った。」).  From turn 1161077 the phase
quest-strategy:q2-phase-1044 still walked the vantages of [19,11], a deep-water cell
(002_TheSewer.jsonc) no allowed cell certifies at light radius 1, and from turn 1162706 it
waited at [21,21] (quest:blocked:q2-phase-1044) until the loop detector stopped the bot.
Replayed on the pre-fix code from the entry, 531 of the 544 decision rows give the recorded
reason (the others are the recorded absorbed-power casts and one speed potion, see below), and
the replay waits at [21,21] from the same board.

Now the kill line of a race whose kills reach its placements on the map credits them
(hengbot.q2_kill_credit): a quest floor allocates no new monsters
(world-turn-processor.cpp decide_alloc_monster).  And before a phase waits with every
vantage spent, it lights the room once if the plan's area reading is still due.

DECLARED CONSTRUCTED: the skill row is the n1-c life-098 row of the breeder-swarm fixture (the
capture keeps player boards only), so this replay has no absorbed Light: where the recorded
run cast it (17:01:00 at [3,43], 17:01:19 at [16,27]) the replay shoots, and every plan area
stays unread.  Boards do not follow from any key the replay decides differently from the
record; every key is decided by the public ``choose_key``, and the asserted ones go through the
production executor port.
DECLARED COUNTERFACTUAL (light case only): the kill line is taken off its board, and a Scroll
of Light (the plan's light means, QUEST_2 required_scrolls) is put in the pack of the first
waiting board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position
from hengbot.quest_knowledge import load_quest_knowledge
from tests import test_breeder_swarm_1102_recorded as swarm
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "q2-crocodile-kill-20261107.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
BOARDS = CASE["boards"]
RECORDED = {}
for _row in CASE["decisions"]:  # the stop's loop-detected row repeats the last turn
    RECORDED.setdefault(_row["turn"], (_row["key"], _row["reason"]))
QUEST_DEFINITIONS = Path("C:/hengband/lib/edit/quests")
CROCODILE = 1044
PLACEMENT = Position(19, 11)
KILL_TURN = 1160275
KILL_LINE = "白ワニを葬り去った。"
BLOCKED = "quest:blocked:q2-phase-1044"
FIRST_WAIT = next(index for index, raw in enumerate(BOARDS)
                  if RECORDED.get(raw["turn"], (None, None))[1] == BLOCKED)


def new_policy():
    policy = loops.new_policy({"boards": [BOARDS[0]], "home": None}, swarm.CASE["skill"],
                              monraces=CASE["monraces"])
    policy._quest_knowledge = load_quest_knowledge(QUEST_DEFINITIONS)
    # Entered from town (the boards begin at the entry), not a reconnect.
    policy._q2_reconnect_recovery_floor = None
    return policy


def replay(policy, boards):
    for raw in boards:
        key = loops.decide(policy, copy.deepcopy(raw))
        if key:
            policy.confirm_key_posted(key)


def with_light_scroll(raw):
    """The first waiting board with a Scroll of Light after the Recall scrolls."""
    raw = copy.deepcopy(raw)
    inventory = raw["inventory"]
    recall = next(index for index, item in enumerate(inventory)
                  if item["tval"] == 70 and item["sval"] == 11)
    scroll = dict(copy.deepcopy(inventory[recall]), sval=24, count=2, name="光の巻物",
                  inscription="")
    inventory.insert(recall + 1, scroll)
    for index, item in enumerate(inventory):
        item["slot"] = chr(ord("a") + index)
    return raw


class Q2CrocodileKillRecordedTest(swarm.PostedSwarmKey):
    def test_recorded_kill_then_the_phase_waited(self):
        kill = next(raw for raw in BOARDS if raw["turn"] == KILL_TURN)
        self.assertIn(KILL_LINE, kill["messages"])
        placements = [
            Position(*position)
            for position, race in load_quest_knowledge(QUEST_DEFINITIONS)[2].battlefield.monster_placements
            if race == CROCODILE
        ]
        self.assertEqual(placements, [PLACEMENT])
        raw = BOARDS[FIRST_WAIT]
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (21, 21))
        self.assertEqual(RECORDED[raw["turn"]], ("5", BLOCKED))
        self.assertEqual(RECORDED[BOARDS[-1]["turn"]], ("5", BLOCKED))
        last = CASE["decisions"][-1]
        self.assertEqual((last["turn"], last["reason"]), (BOARDS[-1]["turn"], "loop-detected"))

    def test_the_kill_clears_the_crocodile_phase(self):
        policy = new_policy()
        replay(policy, BOARDS[:FIRST_WAIT])
        self.assertIn(PLACEMENT, policy._q2_surveyed_placements)
        raw = BOARDS[FIRST_WAIT]
        key = loops.decide(policy, copy.deepcopy(raw))
        self.assertIn(CROCODILE, policy._q2_cleared_races)
        self.assertNotEqual(policy.last_reason, BLOCKED)
        self.assertFalse(policy.last_reason.startswith("quest:blocked:"), policy.last_reason)
        self.assertNotEqual(key, "5", policy.last_reason)
        self.post(policy, raw, key)

    def test_without_the_kill_the_spent_phase_lights_once_then_waits(self):
        # DECLARED COUNTERFACTUAL (module docstring).
        boards = copy.deepcopy(BOARDS)
        for raw in boards:
            raw["messages"] = [message for message in raw["messages"] if message != KILL_LINE]
        policy = new_policy()
        replay(policy, boards[:FIRST_WAIT])
        self.assertNotIn(PLACEMENT, policy._q2_surveyed_placements)
        raw = with_light_scroll(boards[FIRST_WAIT])
        key = loops.decide(policy, copy.deepcopy(raw))
        self.assertEqual(policy.last_reason, "quest-strategy:q2-light-phase-1044")
        self.assertTrue(key.startswith("r"), key)
        self.post(policy, raw, key)
        policy.confirm_key_posted(key)
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        key = loops.decide(policy, following)
        self.assertEqual((key, policy.last_reason), ("5", BLOCKED))


if __name__ == "__main__":
    unittest.main()
