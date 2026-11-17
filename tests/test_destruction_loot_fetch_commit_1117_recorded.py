"""The fetch before a *Destruction* goes on where the use is not due (n1-c life-216, 1117).

Recorded (tests/fixtures/n1c-216-glass-loop-1117.jsonl.gz: the capture
~/hengbot-soak/n1-c/life-216/captures/20261117-184130-loop-detected/state.jsonl, turns
5808244-5808259, copied to C:/hengband-backups/pdca/captures/n1c-216-glass-loop-1117): the Glass
castle's 59F, build f6a432c8e.  ``sensed-t1:approach-destruction`` walked east toward the sensed
T1s around (35,49)-(37,52); at (37,37) the ブルー・デイドラゴン at (35,49) was 13 off, the use due,
and destruction_loot fetched west toward the potions at (42,24) (inside the worst radius 17);
at (37,36) it was 14 off, the use not due, and the approach stepped back east: 40 alternations
until the loop detector (18:41:30).  Now the fetch started at (37,37) is committed and goes on at
(37,36).  DECLARED RECONSTRUCTED: the absorbed *Destruction* list row (22 charges at 95%).
DECLARED CONSTRUCTED: on the (37,36) board, the found items without a valuable class (the
committed walk ends: the approach as before).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-glass-loop-1117.jsonl.gz"
FETCH_BEGINS = 5808256   # (37,37): the use due, the fetch west
STEPPED_BACK = 5808259   # (37,36): recorded sensed-t1:approach-destruction '6'
POTIONS = Position(42, 24)
STEPS = {"7": (-1, -1), "8": (-1, 0), "9": (-1, 1), "4": (0, -1), "6": (0, 1),
         "1": (1, -1), "2": (1, 0), "3": (1, 1)}


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


class DestructionLootFetchCommitRecordedTest(unittest.TestCase):
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
        self.assertEqual(board.player.position, Position(37, 37))
        self.assertEqual((key, reason), ("4", "destruction-loot:fetch"))

    def test_the_fetch_goes_on_where_the_use_is_not_due(self):
        board, key, reason = self.replay()[STEPPED_BACK]
        self.assertEqual(board.player.position, Position(37, 36))
        self.assertEqual(reason, "destruction-loot:fetch", key)
        dy, dx = STEPS[key]
        step = Position(board.player.position.y + dy, board.player.position.x + dx)
        self.assertLess(game_distance(step, POTIONS), game_distance(board.player.position, POTIONS))

    def test_with_no_valuable_left_the_approach_goes_on(self):
        board, key, reason = self.replay(_no_valuables)[STEPPED_BACK]
        self.assertEqual((key, reason), ("6", "sensed-t1:approach-destruction"))


if __name__ == "__main__":
    unittest.main()
