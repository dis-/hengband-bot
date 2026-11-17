"""A non-urgent *Destruction* keeps the remembered floor items out of its circle first (1117).

Owner 2026-11-17 (the 50F+ efficiency study's 第2位, 「価値の高い品は先に拾ってから撃つ」;
destruction_loot's docstring): from a place none of the remembered items lies within the circle
of (17, the worst radius), else after the potions, scrolls, devices, rings and amulets inside it
are picked up while no hostile is in view; else the use as before.

Recorded (tests/fixtures/deep-efficiency-1117-destruction-loot.jsonl.gz, see
tests/extract_deep_efficiency_1117_fixtures.py): n1-b life-411 (Magic-Eater), the Castle's 64F,
turns 5162650-5162719: ``sensed-t1:approach-destruction`` toward the sensed T1s (a 火龍 13 cells
off, awake), then on turn 5162719 the use ``mA3``.  Fifteen detected items lay within 17 of it, every
one on ground the map did not show: no clean place within reach and no walk to them, so the use is
made as recorded (the realistic case of the study's 64F approaches).  DECLARED RECONSTRUCTED: the
absorbed *Destruction* list row (22 charges at 95%).  DECLARED CONSTRUCTED: on the use's board, the
found items replaced by one potion pile on mapped floor -- 2 cells off (45,86) (no clean place can
exist within 8: the fetch), or 17 cells north (30,86) (a step south clears it: the place).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, TVAL_POTION, Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "deep-efficiency-1117-destruction-loot.jsonl.gz"
USE = 5162719
NEAR_PILE = (45, 86)
FAR_PILE = (30, 86)


def _one_pile(raw, cell):
    raw = copy.deepcopy(raw)
    grid_map = raw["grid_map"]
    grid_map["found_items"] = [[cell[0], cell[1], 1, TVAL_POTION]]
    grid_map["found_item_names"] = [[cell[0], cell[1], "体力回復の薬"]]
    grid_map["found_item_ids"] = [[cell[0], cell[1], {"sval": 30}]]
    return raw


class DestructionLootRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, pile=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        for raw in self.boards:
            if raw["turn"] == USE and pile is not None:
                raw = _one_pile(raw, pile)
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            key = policy.choose_key(board)
            if board.turn == USE:
                return board, key, policy.last_reason
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError("no use board")

    def test_the_recorded_use_with_no_way_to_its_items_is_made(self):
        board, key, reason = self.replay()
        self.assertEqual(key, "mA3", reason)
        self.assertTrue(reason.startswith("emergency:destruction"), reason)

    def test_a_valuable_pile_beside_is_fetched_first(self):
        board, key, reason = self.replay(NEAR_PILE)
        self.assertEqual(reason, "destruction-loot:fetch", key)
        here = board.player.position
        step = Position(here.y + {"7": -1, "8": -1, "9": -1, "1": 1, "2": 1, "3": 1}.get(key, 0),
                        here.x + {"7": -1, "4": -1, "1": -1, "9": 1, "6": 1, "3": 1}.get(key, 0))
        self.assertLess(game_distance(step, Position(*NEAR_PILE)),
                        game_distance(here, Position(*NEAR_PILE)))

    def test_a_far_pile_is_kept_out_by_a_step_away(self):
        board, key, reason = self.replay(FAR_PILE)
        self.assertEqual(reason, "destruction-loot:place", key)
        self.assertIn(key, {"1", "2", "3"})


if __name__ == "__main__":
    unittest.main()
