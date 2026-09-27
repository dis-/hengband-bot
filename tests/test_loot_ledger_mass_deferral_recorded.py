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
from hengbot.cli import _cell_loop_guard_applies, _is_looping
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

    def test_replay_983_to_1040_expires_before_cli_guard_and_keeps_other_loot(self):
        policy = self._policy()
        target = Position(23, 178)
        policy._loot_target = target
        recent_cells = deque(maxlen=40)
        expiry = guard = None
        previous = None
        for sequence in range(980, 1041):
            row = self.rows[sequence]
            position = Position(**row["position"])
            policy._known_loot = {Position(**cell) for cell in row["loot"]["known"]}
            policy._recent = deque([previous or position, position], maxlen=20)
            if sequence >= 983:
                policy._observe_navigation_commitments(
                    SimpleNamespace(player=SimpleNamespace(position=position))
                )
                if expiry is None and policy._nav_ledger.is_expired("loot", target):
                    expiry = sequence
            board = SimpleNamespace(
                player=SimpleNamespace(position=position), in_town=False
            )
            if sequence <= 1014 and _cell_loop_guard_applies(board, row["reason"], previous):
                recent_cells.append(("orc-23", position.y, position.x))
                if guard is None and _is_looping(recent_cells):
                    guard = sequence
            previous = position
        for sequence in range(1015, 1023):
            # Counterfactual without ledger expiry: continue the recorded
            # 983-1014 two-cell owner handoff until the CLI would stop it.
            row = self.rows[983 + (sequence - 983) % 2]
            position = Position(**row["position"])
            board = SimpleNamespace(player=SimpleNamespace(position=position), in_town=False)
            if _cell_loop_guard_applies(board, row["reason"]):
                recent_cells.append(("orc-23", position.y, position.x))
                if guard is None and _is_looping(recent_cells):
                    guard = sequence
                    break
        self.assertEqual(expiry, 1015)
        self.assertEqual(guard, 1019)
        self.assertLess(expiry, guard)
        self.assertEqual(policy._deferred_loot, {target})
        other = Position(41, 109)
        self.assertIn(other, policy._known_loot - policy._deferred_loot)
        policy._engagement_avoid_cells = set()
        policy._walkable_neighbors = lambda snapshot, pos: [other] if pos == previous else []
        self.assertEqual(
            policy._loot_step(SimpleNamespace(player=SimpleNamespace(position=previous))),
            other,
        )
        self.assertEqual(policy._loot_target, other)

    def test_only_committed_loot_spends_ledger_budget(self):
        policy = self._policy()
        target = Position(23, 178)
        other = Position(15, 106)
        policy._known_loot = {target, other}
        position = Position(22, 177)
        for _ in range(NAV_TARGET_STALL_LIMIT * 2):
            self._observe(policy, position, "explore")
        self.assertEqual(policy._deferred_loot, set())
        self.assertFalse(policy._nav_ledger.is_expired("loot", target))
        policy._loot_target = target
        for _ in range(NAV_TARGET_STALL_LIMIT + 1):
            self._observe(policy, position, "explore")
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
        entry = policy._nav_ledger._progress[("loot", target)]
        policy.last_reason = "emergency:teleport"
        policy._recent = deque([Position(22, 177), Position(41, 107)], maxlen=20)
        policy._observe_navigation_commitments(
            SimpleNamespace(player=SimpleNamespace(position=Position(41, 107)))
        )
        self.assertIs(policy._nav_ledger._progress[("loot", target)], entry)
        self.assertEqual(entry.stall, 0)
        self.assertFalse(policy._nav_ledger.is_expired("loot", target))
        self._observe(policy, Position(41, 107), "seek-loot")
        self.assertFalse(policy._nav_ledger.is_expired("loot", target))
        entry = policy._nav_ledger._progress[("loot", target)]
        policy._recent = deque([Position(22, 177), Position(41, 107)], maxlen=20)
        policy._observe_navigation_commitments(
            SimpleNamespace(player=SimpleNamespace(position=Position(41, 107)))
        )
        self.assertIs(policy._nav_ledger._progress[("loot", target)], entry)
        self.assertEqual(policy._loot_ledger_rearmed, {target})
        policy._safety_deferred_loot.add(target)
        del policy._guarded_paralyzers
        del policy._strategic_hostiles
        del policy._release_claim_goal
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertEqual(restored._safety_deferred_loot, {target})
        self.assertEqual(restored._loot_ledger_rearmed, {target})

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
        self.assertIn(("loot", target), policy._nav_ledger._progress)

    def test_jump_uses_the_one_rearm_allowed_before_recall(self):
        policy = self._policy()
        target = Position(23, 178)
        start = Position(22, 177)
        landing = Position(41, 107)
        policy._known_loot.add(target)
        policy._loot_target = target
        self._observe(policy, start, "seek-loot")
        policy._recent = deque([start, landing], maxlen=20)
        policy._observe_navigation_commitments(
            SimpleNamespace(player=SimpleNamespace(position=landing))
        )
        self.assertEqual(policy._loot_ledger_rearmed, {target})
        for _ in range(NAV_TARGET_STALL_LIMIT):
            self._observe(policy, landing, "seek-loot")
        self.assertEqual(policy._nav_ledger_deferred_loot, {target})
        policy._rearm_navigation_ledger_loot()
        self.assertEqual(policy._nav_ledger_deferred_loot, {target})
        self.assertTrue(policy._nav_ledger.is_expired("loot", target))

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

    def test_sleeping_summoner_doorway_rearms_only_once(self):
        policy = self._policy()
        target = Position(23, 178)
        doorway = Position(22, 177)
        behind_wall = Position(22, 176)
        policy._known_loot.add(target)
        policy._loot_target = target
        policy._nav_ledger.observe("loot", target, 1)
        entry = policy._nav_ledger._progress[("loot", target)]
        policy._physical_adjacent_hostiles = lambda board: []
        policy._current_floor_item_key = lambda *args, **kwargs: None
        policy._loot_step = lambda *args, **kwargs: None
        at_door = SimpleNamespace(player=SimpleNamespace(position=doorway), inventory=[])
        hidden = SimpleNamespace(player=SimpleNamespace(position=behind_wall), inventory=[])
        sleeping_summoner = SimpleNamespace(can_summon=True, can_multiply=False, asleep=True)
        self.assertEqual(policy._loot_block_reason(at_door, [sleeping_summoner]), "summoner-visible")
        self.assertIsNone(policy._normal_loot_key(at_door, [sleeping_summoner]))
        self.assertEqual(policy._safety_deferred_loot, {target})
        self.assertIsNone(policy._normal_loot_key(hidden, []))
        self.assertEqual(policy._deferred_loot, set())
        self.assertEqual(policy._loot_safety_rearmed, {target})
        self.assertIs(policy._nav_ledger._progress[("loot", target)], entry)
        policy._loot_target = target
        self.assertIsNone(policy._normal_loot_key(at_door, [sleeping_summoner]))
        self.assertIsNone(policy._normal_loot_key(hidden, []))
        self.assertEqual(policy._deferred_loot, {target})
        self.assertEqual(policy._safety_deferred_loot, {target})


if __name__ == "__main__":
    unittest.main()
