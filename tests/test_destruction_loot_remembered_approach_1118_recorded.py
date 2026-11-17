"""The fetch before a *Destruction* holds while the remembered approach goes on (n1-b life-411, 1118).

Recorded (tests/fixtures/n1b-411-dloot-approach-1118.jsonl.gz: the capture
~/hengbot-soak/n1-b/life-411/captures/20261118-015222-loop-detected/state.jsonl, turns
6265521-6265569): Angband 80F, build fd4ae7222, the Magic-Eater Lv49.  The sensed-T1 approach
walked west toward the sleeping T1 (index 199, race 1306) at (12,90); at (8,102) it was 12 off,
the use due, and destruction_loot fetched east toward the staff, potion and ring at
(8,110)-(10,111) (inside the worst radius 17), the fetch committed.  At (8,109) the T1 was 21 off
by the game's cdis, outside the telepathy's MAX_PLAYER_SIGHT 20 (monster-update.cpp), no longer
shown: the sensed leave fell to ``remembered_approach_key``, which did not ask destruction_loot,
and stepped back west; at (8,108) the T1 was shown again and the committed fetch stepped east,
until the loop detector (2026-11-18 01:52:22).  Now the target the remembered approach still goes
to holds the committed fetch.  DECLARED RECONSTRUCTED: the absorbed *Destruction* list row (22
charges at 95%; the capture carries no list).  DECLARED CONSTRUCTED: on the (8,109) board, the
found items without a valuable class (the committed fetch ends: the approach as before).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-dloot-approach-1118.jsonl.gz"
FETCH_BEGINS = 6265530   # (8,102): the use due, the fetch east
LAST_SHOWN = 6265562     # (8,108): the T1 shown, the committed fetch east
STEPPED_BACK = 6265569   # (8,109): the T1 lost; recorded sensed-t1:approach-destruction '4'
T1_INDEX = 199


def _no_valuables(raw):
    raw = copy.deepcopy(raw)
    grid_map = raw["grid_map"]
    keep = [row for row in grid_map["found_items"]
            if not any(tval in (40, 45, 55, 65, 66, 70, 75) for tval in row[3:])]
    cells = {(row[0], row[1]) for row in keep}
    grid_map["found_items"] = keep
    grid_map["found_item_names"] = [row for row in grid_map["found_item_names"]
                                    if (row[0], row[1]) in cells]
    grid_map["found_item_ids"] = [row for row in grid_map["found_item_ids"]
                                  if (row[0], row[1]) in cells]
    return raw


class DestructionLootRememberedApproachRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, last_board=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        answers = {}
        for raw in self.boards:
            if raw["turn"] == STEPPED_BACK and last_board is not None:
                raw = last_board(raw)
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            key = policy.choose_key(board)
            answers[board.turn] = (board, key, policy.last_reason)
            if board.turn == STEPPED_BACK:
                return answers
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError("no stepped-back board")

    def test_the_fetch_begins_where_the_use_is_due(self):
        board, key, reason = self.replay()[FETCH_BEGINS]
        self.assertEqual(board.player.position, Position(8, 102))
        self.assertEqual((key, reason), ("9", "destruction-loot:fetch"))

    def test_the_t1_is_lost_from_detection_on_the_stepped_back_board(self):
        answers = self.replay()
        shown = answers[LAST_SHOWN][0]
        lost = answers[STEPPED_BACK][0]
        self.assertIn(T1_INDEX, {monster.index for monster in shown.detected_monsters})
        self.assertNotIn(T1_INDEX, {monster.index for monster in lost.detected_monsters})
        self.assertEqual(answers[LAST_SHOWN][1:], ("6", "destruction-loot:fetch"))

    def test_the_fetch_goes_on_while_the_remembered_approach_goes_on(self):
        board, key, reason = self.replay()[STEPPED_BACK]
        self.assertEqual(board.player.position, Position(8, 109))
        # East, onto the staff at (8,110); recorded: sensed-t1:approach-destruction '4'.
        self.assertEqual((key, reason), ("6", "destruction-loot:fetch"))

    def test_with_no_valuable_left_the_remembered_approach_goes_on(self):
        board, key, reason = self.replay(_no_valuables)[STEPPED_BACK]
        self.assertEqual((key, reason), ("4", "sensed-t1:approach-destruction"))


if __name__ == "__main__":
    unittest.main()
