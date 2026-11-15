"""After a teleport, the Q22 opening walks to the hold nearest the new landing (n1-b life-398).

n1-b life-398 (zombie Magic-Eater Lv19, build 3b52c43f0) took Q22 (Orc Camp) at
Angwil on 2026-11-15 11:25.  The reviewed opening (QUEST_22 engagement_plan
opening_reposition) quaffs Speed, reads Teleport once, and walks from the landing
to the nearest of the three one-entry holds [8,3], [9,58], [15,2]
(「着地点から3か所の1対1保持点のうち最短経路の地点へ移動」).  The bot landed at
(19,23) and picked [15,2] (26 static steps; [8,3] 32, [9,58] 46), was caught in
the open by the camp, and the emergency teleport put it at (17,61): [9,58] 20
steps away, [15,2] 64.  The opening kept the hold of the first landing and
walked west across the camp; so after every later emergency teleport, (9,53)
six steps from [9,58] included.  It never reached a hold, read all fifteen
Teleport scrolls in about 115 player turns, read Recall surrounded by six orcs
and died.

Fix (policy_quest ``_quest_execute_key`` phase 2): until a hold is reached, the
nearest hold is measured again from the current cell on every board.

Recorded: the death's incident-capture town-arrival checkpoint (rows 0-88, the
Angwil visit up to the quest entrance) and the stop capture's quest-floor boards
(tests/extract_n1b_398_q22_hold_1115_fixture.py), decided through the public
choose_key and compared with the decision log up to the first emergency teleport;
the new steps are sent through the production executor (``_ExecutorInputPort``).

DECLARED CONSTRUCTED: the third test decides the recorded (9,53) landing board
(turn 879618) on the policy as it stood after the first emergency teleport (the
boards in between were decided by a policy that walked elsewhere).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from support.town_arrival_fixture import load
from tests.test_me_nokey_1031_recorded import PostedKey

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-398-q22-hold-1115"
QUEST = 22
REPOSITION = "quest-strategy:q22-opening-reposition"
FIRST_LANDING = Position(19, 23)
SECOND_LANDING = Position(17, 61)
WEST_HOLD = Position(15, 2)
EAST_HOLD = Position(9, 58)


class N1b398Q22Hold1115RecordedTest(PostedKey):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.town = []
        for recorded, supply in steps:
            key = policy.choose_key(supply())
            cls.town.append((recorded["row"], (key, policy.last_reason),
                             (recorded["key"], recorded["reason"])))
            policy.confirm_key_posted(recorded["key"])
        data = json.loads(lzma.decompress((FIXTURE / "quest-boards.json.xz").read_bytes()))
        cls.grid_maps = data["grid_maps"]
        cls.decisions = data["decisions"]
        cls.boards = data["boards"]
        cls.landing = data["landing"]
        cls.quest = []
        cls.holds = []
        for recorded, raw in zip(cls.decisions[:-1], cls.boards[:-1]):
            board = policy.with_known_skill_exp(
                parse_snapshot(cls.raw(raw), policy._monrace_knowledge))
            key = policy.choose_key(board)
            cls.quest.append((recorded["turn"], (key, policy.last_reason),
                              (recorded["key"], recorded["reason"])))
            cls.holds.append((board.player.position,
                              policy._quest_strategy_hold_positions.get(QUEST)))
            policy.confirm_key_posted(recorded["key"])
        cls.checkpoint = checkpoint_bytes(policy)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    @classmethod
    def raw(cls, board):
        board = copy.deepcopy(board)
        board["grid_map"] = copy.deepcopy(cls.grid_maps[board["grid_map"]])
        return board

    def setUp(self):
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        self.addCleanup(lambda: self.policy._home_disposal.history_path.unlink(missing_ok=True))

    def decide(self, raw):
        board = self.policy.with_known_skill_exp(
            parse_snapshot(self.raw(raw), self.policy._monrace_knowledge))
        key = self.policy.choose_key(board)
        return board, key, self.policy.last_reason

    def test_the_visit_and_the_opening_decide_as_recorded(self):
        for row, decided, recorded in self.town:
            self.assertEqual(decided, recorded, row)
        for turn, decided, recorded in self.quest:
            self.assertEqual(decided, recorded, turn)
        self.assertEqual(self.quest[-1][2], ("rd", "emergency:teleport"))
        # The opening teleport's landing picks the nearest hold, [15,2].
        self.assertEqual(self.holds[2], (FIRST_LANDING, WEST_HOLD))

    def test_the_emergency_landing_walks_to_the_hold_nearest_it(self):
        raw = self.boards[-1]
        self.assertEqual(self.decisions[-1]["position"], [SECOND_LANDING.y, SECOND_LANDING.x])
        self.assertEqual((self.decisions[-1]["key"], self.decisions[-1]["reason"]),
                         ("4", REPOSITION))  # recorded: west, toward [15,2]
        board, key, reason = self.decide(raw)
        self.assertEqual(board.player.position, SECOND_LANDING)
        self.assertEqual(self.policy._quest_strategy_hold_positions[QUEST], EAST_HOLD)
        self.assertEqual((key, reason), ("8", REPOSITION))  # north, toward [9,58]
        self.post(self.policy, self.raw(raw), key)

    def test_a_landing_six_steps_from_the_east_hold_walks_east(self):
        board, key, reason = self.decide(self.landing)
        self.assertEqual(board.player.position, Position(9, 53))
        self.assertEqual(self.policy._quest_strategy_hold_positions[QUEST], EAST_HOLD)
        self.assertEqual((key, reason), ("6", REPOSITION))
        self.post(self.policy, self.raw(self.landing), key)


if __name__ == "__main__":
    unittest.main()
