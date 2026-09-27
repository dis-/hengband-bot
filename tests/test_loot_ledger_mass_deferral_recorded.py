"""Recorded Orc cave 23F loot ledger regression, 2026-09-27."""

import tests  # noqa: F401 -- isolate live runtime files

from collections import deque
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import Position
from hengbot.navigation import NAV_TARGET_STALL_LIMIT
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures/loot-ledger-mass-deferral-20260927.jsonl.gz"
SHA256 = "031a5b515f97803270c5cc8ae9de125f2755a8f1b1b34da21a0c80f189846dcb"


class LootLedgerMassDeferralRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assert_fixture = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = {row["sequence"]: row for row in map(json.loads, stream)}

    def setUp(self):
        self.assertEqual(self.assert_fixture, SHA256)

    def _policy(self):
        policy = HengbotPolicy()
        policy._guarded_paralyzers = lambda snapshot, hostiles: []
        policy._strategic_hostiles = lambda snapshot: []
        policy._release_claim_goal = lambda *args, **kwargs: None
        return policy

    def _observe(self, policy, position, reason):
        policy.last_reason = reason
        policy._recent = deque([position, position], maxlen=20)
        policy._observe_navigation_commitments(
            SimpleNamespace(player=SimpleNamespace(position=position))
        )

    def test_capture_shows_owner_handoff_and_mass_deferral(self):
        rows = self.rows
        self.assertEqual(rows[983]["reason"], "summoner:retreat")
        self.assertEqual(rows[984]["reason"], "seek-loot")
        self.assertEqual(rows[1015]["loot"]["deferred"], [{"y": 23, "x": 178}])
        self.assertEqual(rows[1023]["reason"], "emergency:teleport")
        self.assertEqual(rows[1024]["position"], {"y": 41, "x": 107})
        self.assertEqual(rows[1040]["loot"]["blocker"], "navigation-ledger:loot")
        self.assertEqual(rows[1040]["loot"]["target"], None)
        self.assertEqual(rows[1040]["reason"], "explore")
        self.assertEqual([len(rows[n]["loot"]["deferred"]) for n in (1040, 1100, 1300, 1800)], [1, 3, 6, 15])

    def test_exploration_does_not_spend_looming_loot_budget(self):
        policy = self._policy()
        target = Position(23, 178)
        other = Position(15, 106)
        policy._known_loot = {target, other}
        policy._loot_target = target
        position = Position(22, 177)
        for _ in range(NAV_TARGET_STALL_LIMIT * 2):
            self._observe(policy, position, "explore")
        self.assertEqual(policy._deferred_loot, set())
        self.assertFalse(policy._nav_ledger.is_expired("loot", target))
        for _ in range(NAV_TARGET_STALL_LIMIT + 1):
            self._observe(policy, position, "seek-loot")
        self.assertEqual(policy._deferred_loot, {target})
        self.assertNotIn(other, policy._deferred_loot)
        self.assertIsNone(policy._loot_target)
        self.assertIsNone(policy._loot_defer_blocker)
        policy._walkable_neighbors = lambda snapshot, pos: [other] if pos == position else []
        policy._engagement_avoid_cells = set()
        self.assertEqual(
            policy._loot_step(SimpleNamespace(player=SimpleNamespace(position=position))),
            other,
        )
        self.assertEqual(policy._loot_target, other)

        unclaimed = self._policy()
        unclaimed._known_loot = {target, other}
        for _ in range(NAV_TARGET_STALL_LIMIT * 2):
            self._observe(unclaimed, position, "explore")
        self.assertEqual(unclaimed._deferred_loot, set())

    def test_teleport_restarts_route_budget_and_checkpoint_restores_safety(self):
        policy = self._policy()
        target = Position(23, 178)
        policy._known_loot.add(target)
        policy._loot_target = target
        for _ in range(NAV_TARGET_STALL_LIMIT - 1):
            self._observe(policy, Position(22, 177), "seek-loot")
        policy.last_reason = "emergency:teleport"
        policy._recent = deque([Position(22, 177), Position(41, 107)], maxlen=20)
        policy._observe_navigation_commitments(
            SimpleNamespace(player=SimpleNamespace(position=Position(41, 107)))
        )
        self.assertFalse(policy._nav_ledger.is_expired("loot", target))
        self._observe(policy, Position(41, 107), "seek-loot")
        self.assertFalse(policy._nav_ledger.is_expired("loot", target))
        policy._safety_deferred_loot.add(target)
        del policy._guarded_paralyzers
        del policy._strategic_hostiles
        del policy._release_claim_goal
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertEqual(restored._safety_deferred_loot, {target})

    def test_safety_deferral_rearms_when_threat_disappears(self):
        policy = self._policy()
        target = Position(23, 178)
        policy._known_loot.add(target)
        policy._loot_target = target
        policy._nav_ledger.observe("loot", target, 1)
        policy._loot_block_reason = lambda snapshot, hostiles: "summoner-visible"
        board = SimpleNamespace()
        self.assertIsNone(policy._normal_loot_key(board, []))
        self.assertEqual(policy._safety_deferred_loot, {target})
        self.assertEqual(policy._deferred_loot, {target})
        policy._loot_block_reason = lambda snapshot, hostiles: None
        policy._current_floor_item_key = lambda *args, **kwargs: None
        policy._loot_step = lambda *args, **kwargs: None
        self.assertIsNone(policy._normal_loot_key(board, []))
        self.assertEqual(policy._safety_deferred_loot, set())
        self.assertEqual(policy._deferred_loot, set())
        self.assertNotIn(("loot", target), policy._nav_ledger._progress)

    def test_fundraising_loot_walk_still_spends_a_real_stall_budget(self):
        policy = self._policy()
        target = Position(23, 178)
        policy._known_loot.add(target)
        policy._loot_target = target
        for _ in range(NAV_TARGET_STALL_LIMIT + 1):
            self._observe(policy, Position(22, 177), "fundraise:seek-loot")
        self.assertEqual(policy._deferred_loot, {target})

    def test_avoided_loot_rearms_after_safety_cells_clear(self):
        policy = self._policy()
        target = Position(23, 178)
        policy._known_loot.add(target)
        policy._engagement_avoid_cells = {target}
        policy._paralyzer_avoid_cells = {target}
        board = SimpleNamespace(player=SimpleNamespace(position=Position(22, 177)))
        self.assertIsNone(policy._loot_step(board))
        self.assertEqual(policy._safety_deferred_loot, {target})
        self.assertEqual(policy._loot_defer_blocker, "paralyzer-ring")
        policy._engagement_avoid_cells.clear()
        policy._paralyzer_avoid_cells.clear()
        policy._loot_block_reason = lambda snapshot, hostiles: None
        policy._current_floor_item_key = lambda *args, **kwargs: None
        policy._loot_step = lambda *args, **kwargs: None
        self.assertIsNone(policy._normal_loot_key(board, []))
        self.assertEqual(policy._deferred_loot, set())
        self.assertIsNone(policy._loot_defer_blocker)


if __name__ == "__main__":
    unittest.main()
