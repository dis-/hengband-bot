"""n1-c life-217, Quest 33 resumed (2026-11-19 19:25-20:00): the stands of 段1 walked round and round.

The run (tests/fixtures/n1c-217-q33-stage-loop-1119.json.gz, extracted by
tests/extract_n1c_217_q33_stage_loop_1119_fixture.py) walked [13,39] [11,39] [2,46] [2,30] [5,10]
[14,10] [15,38] and again, holding each stand's meet_turns, until the server's floor-dwell watcher
halted it.  The 段2 stand [14,47] was never reached: the Queens (vision 30) and the Dagons (vision 12)
both act there (quest_alignment_split ``contact_cells``), and it opens only once the Dagons are dead.
The plan waits for the Dagons at [15,38], expecting them to come up the central column, but they did
not: the three stood at the mouth of their room, [24,45] [25,45] [25,44] ([23,44] [25,45] [25,44] on
the recorded board), and from [15,38] only the nearest is within its vision of 12 (the game moves a
monster only while the player is within its vision or in his line within 20,
monster-processor.cpp decide_process_continue); the two others stood still and blocked it.

The top of the central column, [18,39], is within the vision of all three Dagons and out of every
Queen's (31 from [20,69]): only the EVIL side acts there, so the owner's rule (no stand where a GOOD
and an EVIL summoner both act) holds.  The plan now waits there for them after [15,38].

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, with the shipped strategies and this tree's quest
data, tests/test_quest33_alignment_split ``recorded``); the board is the recorded one on [15,38]; the
navigator is set on the [15,38] stand with its wait spent and the three Its' kill lines read (the run
killed 『それ』 three times at 18:30, quest_alignment_split counts them by the race's name).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot import quest_alignment_split, quest_exposure, quest_room_sweep
from hengbot.model import Position, parse_snapshot
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import DAGON, IT, QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-q33-stage-loop-1119.json.gz"
COLUMN_TOP = (18, 39)


class N1c217Q33StageLoopTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            self.case = json.load(stream)
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.board = parse_snapshot(self.case["board"], self.policy._monrace_knowledge)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.navigator = _navigator(self.policy, self.board, QUEST)
        self.navigator.split_kills = {IT: 3}

    def dagons(self):
        return [(m.position.y, m.position.x) for m in self.board.detected_monsters if m.race_id == DAGON]

    def test_the_recorded_round_never_reached_the_queen_stand(self):
        held = {tuple(run["cell"]) for run in self.case["runs"] if run["reason"] == "quest-strategy:hold"}
        self.assertTrue({(13, 39), (11, 39), (2, 46), (2, 30), (5, 10), (14, 10), (15, 38)} <= held)
        self.assertNotIn((14, 47), held)
        self.assertFalse(any(run["cell"][0] >= 16 for run in self.case["runs"]))

    def test_the_column_top_is_where_only_the_dagons_act(self):
        self.assertEqual(self.board.player.position, Position(15, 38))
        self.assertEqual(sorted(self.dagons()), [(23, 44), (25, 44), (25, 45)])
        vision = self.policy._monrace_knowledge[DAGON].vision
        near = [cell for cell in self.dagons() if quest_exposure.game_distance(cell, (15, 38)) <= vision]
        self.assertEqual(near, [(23, 44)])
        self.assertTrue(all(quest_exposure.game_distance(cell, COLUMN_TOP) <= vision for cell in self.dagons()))
        contact = quest_alignment_split.contact_cells(self.policy, self.board, self.navigator, self.plan)
        self.assertIn((14, 47), contact)
        self.assertNotIn(COLUMN_TOP, contact)

    def test_after_the_corridor_stand_the_plan_walks_to_the_column_top(self):
        stops = quest_room_sweep._stops(self.plan)
        stage = next(index for index, stop in enumerate(stops) if stop.get("cell") == [15, 38])
        self.navigator.sweep_stage = stage
        self.navigator.sweep_meet_turns = int(stops[stage]["meet_turns"])
        key = quest_room_sweep.key(self.policy, self.board) or quest_room_sweep.walk_key(self.policy, self.board)
        self.assertIsNotNone(key)
        self.assertEqual(stops[self.navigator.sweep_stage]["cell"], list(COLUMN_TOP))
        self.assertIn(self.policy.last_reason, {quest_room_sweep.WALK_REASON, quest_room_sweep.OPEN_REASON})


if __name__ == "__main__":
    unittest.main()
