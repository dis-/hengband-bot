"""destruction_loot walks toward the valuables no known way leads to before the use (1123).

The loot yield study C:/hengband-backups/pdca/loot-yield-1123 (owner goal 2026-11-23
「アイテム回収率を上げること」): n1-b life-416 and n1-c life-221 lost the valuables of many
non-urgent *Destruction* uses although the owner's 2026-11-17 rule picks them up first
(「価値の高い品は先に拾ってから撃つ」, destruction_loot).  Every use replayed that deleted known
valuables with no hostile in view in the scene had the fetch refuse for want of a known way: the
piles the absorbed detection showed lay on floor the map did not hold.  Since 2026-11-23 the fetch
walks to the reachable remembered frontier nearest them (destruction_loot ``_frontier_step``, the
2026-11-13 rule's way to loot with no known route, 「その品の方へ探索を寄せる」), within the
scene's bound.

Recorded (tests/extract_loot_yield_1123_fixtures.py):

- n1-c life-221 (Angband 80F, turn 4392698): ``sensed-t1:approach-destruction`` toward the
  sensed インパクト・ハウンド pack, then the use at (49,88); 器用さの薬 and *鑑定*の巻物 six cells
  west on unknown floor were deleted.
- n1-b life-416 (Angband 95F, turn 4038441): the approach toward a sensed T1, then the use at
  (20,11); two スピードの指輪 {未鑑定} and a potion in a walled room five cells off were deleted.

DECLARED RECONSTRUCTED: the Magic-Eater's device lists (the snapshot files carry none): one staff
row of *Destruction*, 22 charges at 95% (as tests/test_destruction_loot_livelock_1123_recorded.py).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import destruction_loot, destruction_use, me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, TVAL_POTION, Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
N1C = FIXTURES / "loot-yield-1123-fetch-frontier-n1c-221.jsonl.gz"
N1B = FIXTURES / "loot-yield-1123-fetch-frontier-n1b-416.jsonl.gz"
N1C_USE = 4392698
N1B_USE = 4038441
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def _boards(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


class DestructionLootFrontierRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def drive(self, path, *, last_board=None):
        """Drive every board; ``last_board`` may change the policy before the last one."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        boards = _boards(path)
        first = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(boards[0]), self.monrace))
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        for index, raw in enumerate(boards):
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            policy._me_device_lists = {"staff": (board.turn, ({
                "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
                "max": 22, "fail": 5, "success": 95},))}
            if index == len(boards) - 1 and last_board is not None:
                last_board(policy, board)
            policy._decision_sequence = index + 1
            key = policy.choose_key(board)
            if index == len(boards) - 1:
                return policy, board, key, policy.last_reason
            if key:
                policy.confirm_key_posted(key)

    def assert_walks_toward_the_frontier(self, policy, board, key, reason):
        self.assertEqual(reason, destruction_loot.FRONTIER_REASON, key)
        memory = getattr(policy, destruction_loot.MEMORY)
        goal = memory["frontier"]
        self.assertIsNotNone(goal)
        dy, dx = STEPS[key]
        here = board.player.position
        step = Position(here.y + dy, here.x + dx)
        self.assertLess(game_distance(step, goal), game_distance(here, goal))
        # The fetch is committed where the use was due: the next boards continue it.
        self.assertEqual(memory["fetch"], here)

    def test_n1c_the_use_with_no_known_way_walks_toward_the_valuables(self):
        # Recorded: emergency:destruction:absorbed-power 'mA3' at (49,88).
        policy, board, key, reason = self.drive(N1C)
        self.assertEqual(board.turn, N1C_USE)
        self.assert_walks_toward_the_frontier(policy, board, key, reason)

    def test_n1b_the_use_with_no_known_way_walks_toward_the_valuables(self):
        # Recorded: emergency:destruction:absorbed-power 'mA3' at (20,11).
        policy, board, key, reason = self.drive(N1B)
        self.assertEqual(board.turn, N1B_USE)
        self.assert_walks_toward_the_frontier(policy, board, key, reason)

    def test_past_the_bound_the_use_is_made_and_recorded(self):
        """DECLARED CONSTRUCTED: the scene's bound spent before the use's board
        (``DECISIONS_MAX``): the use goes ahead as before, and the decision log's
        ``destruction`` field names the rung, the hostiles it leaves and why no fetch came."""
        def spent(policy, board):
            memory = destruction_loot._memory(policy, board)
            memory["decisions"] = destruction_loot.DECISIONS_MAX

        policy, board, key, reason = self.drive(N1C, last_board=spent)
        self.assertEqual(key, "mA3", reason)
        record = destruction_use.use_report(policy)
        self.assertEqual(record["reason"], reason)
        self.assertEqual(record["rung"], "threat_tiers.sensed_t1_destruction_key")
        self.assertTrue(record["leaving"])
        self.assertEqual(record["loot"], {"asked": True, "declined": "bound"})

    def test_the_powered_circle_counts_items_to_22(self):
        """DECLARED CONSTRUCTED: one potion pile 20 cells off on the use's board.  The circle of a
        use through Powerful Activation (destruction_use ``worst_radius``) reaches it; the
        ordinary one does not."""
        policy, board, key, reason = self.drive(N1C)
        here = board.player.position
        cell = Position(here.y, here.x - 20)
        raw = copy.deepcopy(_boards(N1C)[-1])
        raw["grid_map"]["found_items"] = [[cell.y, cell.x, 1, TVAL_POTION]]
        snapshot = parse_snapshot(raw, self.monrace)
        self.assertEqual(game_distance(here, cell), 20)
        self.assertNotIn(cell, destruction_loot.exposed(policy, snapshot, radius=destruction_use.WORST_RADIUS))
        self.assertIn(cell, destruction_loot.exposed(policy, snapshot,
                                                     radius=destruction_use.POWERED_WORST_RADIUS))


if __name__ == "__main__":
    unittest.main()
