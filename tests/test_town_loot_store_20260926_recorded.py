"""The Morivant gold/store-4 handoff, pinned to recorded decision boards.

The input to decision 33899 is state row 1455.  Its next three state rows
follow the recorded travel macro; they are evidence only after divergence.
"""

import tests  # noqa: F401 -- isolate runtime files

import gzip
import hashlib
import json
import unittest
from unittest.mock import patch
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, StoreVisit, LEAVE_STORE_KEY


FIXTURE = Path(__file__).parent / "fixtures" / "town-loot-store-20260926.jsonl.gz"
FIXTURE_SHA256 = "6cf18440b200d73a1e84265a987fa8302f82332cfeae9f8bfe85f81bc530a4af"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")
GOLD = Position(27, 94)


class TownLootStoreRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        cls.monraces = load_monrace_knowledge(MONRACES)
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = {row["sequence"]: row for row in map(json.loads, stream)}

    def board(self, sequence):
        return parse_snapshot(self.rows[sequence]["state"], self.monraces)

    def test_replay_stops_at_first_changed_key_and_keeps_loot_owner(self):
        board = self.board(33899)
        self.assertEqual(board.player.position, Position(28, 93))
        self.assertIsNone(board.store)
        self.assertTrue(board.grid_at(GOLD).currently_observed)
        self.assertEqual(board.grid_at(GOLD).object_count, 1)
        policy = HengbotPolicy(monrace_knowledge=self.monraces)
        policy._build_grid_index(board)
        policy._known_loot.add(GOLD)
        policy._loot_target = GOLD
        policy._shopping_approach_goal = Position(32, 90)
        # Replay the captured floor-loot proposal through the actual downstream
        # town seam.  The recording's next board is a store reached by its
        # rewritten travel macro, so it cannot be replayed after this key differs.
        proposed = policy._normal_loot_key(board, [])
        self.assertEqual((policy.last_reason, proposed), ("seek-loot", "9"))
        policy._town_progress_history().append(
            policy._town_progress_fingerprint(self.board(33898))
        )
        self.assertTrue(policy._town_result_makes_progress(board, proposed))
        key = policy._town_procurement_decision(board, proposed)
        self.assertEqual((policy.last_reason, key), ("seek-loot", "9"))
        self.assertNotEqual(key, self.rows[33899]["recorded"]["key"])
        self.assertNotIn("town-progress-invariant:defect", policy.last_reason)

    def test_open_wanted_store_keeps_store_owner_at_selection(self):
        board = self.board(33900)
        self.assertEqual(board.store.store_type, 4)
        policy = HengbotPolicy(monrace_knowledge=self.monraces)
        policy._build_grid_index(self.board(33899))
        policy._known_loot.add(GOLD)
        policy._loot_target = GOLD
        policy._store_visit = StoreVisit("town-errand", "shopping", 4)
        policy.last_reason = "shop:observe-and-leave"
        key = policy._town_procurement_decision(board, LEAVE_STORE_KEY)
        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "town-progress-invariant:continue-observed-shop")
        self.assertIsNotNone(policy._store_visit)

    def test_remembered_loot_has_same_owner_at_both_seams(self):
        board = self.board(33899)
        remembered = replace(board, grids={
            **board.grids,
            GOLD: replace(board.grid_at(GOLD), currently_observed=False, object_count=0),
        })
        policy = HengbotPolicy(monrace_knowledge=self.monraces)
        policy._loot_target = GOLD
        policy._known_loot.add(GOLD)
        policy.last_reason = "seek-loot"
        policy._town_progress_history().append(
            policy._town_progress_fingerprint(remembered)
        )
        self.assertTrue(policy._town_result_makes_progress(remembered, "9"))
        policy._shopping_approach_store_type = 4
        with patch.object(policy, "_normal_loot_key", return_value="9") as loot:
            self.assertEqual(policy._town_procurement_decision(remembered, "\x1b`n%."), "9")
            loot.assert_called_once()
        policy._deferred_loot.add(GOLD)
        self.assertFalse(policy._town_committed_loot())
        with patch.object(policy, "_normal_loot_key", return_value="9") as loot:
            policy._town_procurement_decision(remembered, "\x1b`n%.")
            self.assertEqual(loot.call_count, 0)


if __name__ == "__main__":
    unittest.main()
