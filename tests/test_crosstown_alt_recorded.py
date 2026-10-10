"""Recorded boundary pin for the 2026-10-06 alternating-owner cycle.

This is a boundary replay, not a process-lifetime replay: the supplied state
tail starts mid-session. Raw input segments and decision diagnostics are frozen
for 1497..1504. The visit, exhausted Magic Shop plan, sale signature, expedition
and fresh Home knowledge are explicit boundary seeds. The actual shop selector,
IST fallback, outside composition, router and cross-town/progress seams run unpatched.
After the first changed key, subsequent boards are counterfactual positions on
the same recorded map/inventory; we never pretend the old cycle is their effect.
Store 5 is STORE_MAGIC in the emitter (called Alchemist in the incident brief).
"""
from __future__ import annotations

import tests  # noqa: F401 -- runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import (
    Position, STORE_ALCHEMIST, STORE_HOME, STORE_MAGIC,
    SV_STAFF_IDENTIFY, TVAL_STAFF, parse_snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import CrossTownShoppingExpedition, StoreVisit, TownErrandPlan
from hengbot.town_maps import find_town_map, parse_town_map

FIXTURE = Path(__file__).parent / "fixtures/crosstown-alt-20261006.jsonl.gz"
METADATA = FIXTURE.with_suffix("").with_suffix(".boundaries.json")
SHA256 = "9db9172afbcf1d6a633939313e864ad0408cf640238123576e8a1afa1d3d09fe"
REASON = "town:cross-town-shopping:travel-2"
ENTRANCE = Position(38, 106)
TARGET = Position(37, 119)
DELTAS = {"7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
          "4": (0, -1), "6": (0, 1), "1": (1, -1),
          "2": (1, 0), "3": (1, 1)}


class CrosstownAltRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        assert hashlib.sha256(METADATA.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == (
            "5cde1db624e034ebf873ddd0120b10a9f77c59a9198be0d2a3010e13abb27868"
        )
        cls.metadata = json.loads(METADATA.read_text(encoding="utf-8"))
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            lines = stream.readlines()
        cls.boards = {}
        offset = 0
        for count, decision in zip(cls.metadata["input_rows"], cls.metadata["decisions"]):
            segment = lines[offset:offset + count]
            offset += count
            board = parse_snapshot(json.loads(segment[-1]))
            assert board.turn == decision["turn"]
            assert board.player.position == Position(**decision["position"])
            assert (board.store.store_type if board.store else None) == decision["store_type"]
            cls.boards[decision["decision_sequence"]] = board
        assert offset == len(lines)
        cls.town_map = parse_town_map(find_town_map(1, Path("C:/hengband/lib/edit")))

    def _policy(self):
        policy = HengbotPolicy(town_map=self.town_map)
        policy._observe(self.boards[1497])  # includes recorded depth/quest progress
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._town_errand_plan = TownErrandPlan([STORE_MAGIC], index=1)
        policy._store_visit = StoreVisit(
            "town-errand", "shopping", STORE_MAGIC, goal=ENTRANCE,
            opened_sequence=1495, visit_origin="acquire",
        )
        policy._town_visit_sale_signatures.add((TVAL_STAFF, SV_STAFF_IDENTIFY))
        expedition = dict(self.metadata["decisions"][1]["cross_town_shopping"])
        expedition["blocking_categories"] = tuple(expedition["blocking_categories"])
        expedition["candidate_order"] = tuple(expedition["candidate_order"])
        expedition["tried_towns"] = list(expedition["tried_towns"])
        policy._cross_town_shopping = CrossTownShoppingExpedition(**expedition)
        policy._decision_sequence = 1497
        policy._build_grid_index(self.boards[1498])
        return policy

    def _observe_refusal(self, policy):
        page = self.boards[1497]
        selected = policy._in_store_selection(page)
        # Decided F2 behavior: pure preflight filters the confirmed-sale class, leaving no safe page successor.
        self.assertIsNone(selected)
        self.assertEqual(policy._shop(page), "\x1b")
        self.assertEqual(policy.last_reason, "shop:sell-rebuy-churn-defect")
        self.assertFalse(policy._store_visit.operation_posted)
        policy._shop_observation = (page.store, 1497)
        policy._town_supplier_stock[STORE_MAGIC] = page.store
        policy._decision_sequence = 1498

    def test_recorded_before_cycle_and_actual_refusal(self):
        decisions = self.metadata["decisions"][1:]
        self.assertEqual([d["key"] for d in decisions],
                         ["9", "1", "\x1b", "7", "3", "\x1b", "9"])
        self.assertEqual(decisions[0]["reason"], REASON)
        self.assertEqual([d["reason"] for d in decisions], [
            REASON, f"town-progress-invariant:defect:{REASON}=>{REASON}",
            "town-progress-invariant:continue-observed-shop", "shop:approach",
            "shop:approach", "town-progress-invariant:continue-observed-shop", REASON,
        ])
        self.assertEqual(decisions[1]["town_emit_ownership"]["target_source"],
                         "stepped-onto-store-grid")
        self.assertEqual(decisions[1]["position"], {"y": 37, "x": 107})
        for index in (2, 5):
            self.assertEqual(decisions[index]["store_type"], STORE_MAGIC)
            self.assertFalse(decisions[index]["store_visit"]["operation_posted"])
        self._observe_refusal(self._policy())

    def test_no_operation_settles_observed_shelf_even_after_plan_advanced(self):
        # Current/exhausted cursor, a different stop, and no plan describe
        # the same observed result. None may reopen this shelf's no-op visit.
        for plan in (TownErrandPlan([STORE_MAGIC]),
                     TownErrandPlan([STORE_MAGIC], index=1),
                     TownErrandPlan([STORE_ALCHEMIST]), None):
            with self.subTest(plan=plan):
                policy = self._policy()
                self._observe_refusal(policy)
                policy._town_errand_plan = plan
                self.assertIsNone(policy._atomic_shop_transaction_key(self.boards[1498]))
                self.assertEqual(policy.last_reason, "shop:observed-operation-uncomposable")
                self.assertIsNone(policy._store_visit)
                self.assertEqual(policy._store_visit_last_closed.outcome,
                                 "observed-operation-uncomposable")
                self.assertIn(STORE_MAGIC, policy._town_visit_ledger.nonhome_attempted_without_effect)
                self.assertIsNone(policy._shop_observation)
                self.assertEqual(policy._shop_selector_diagnostics["observed_stop_settlement"], {
                    "store_type": STORE_MAGIC,
                    "reason": "shop:observed-operation-uncomposable",
                    "decision_sequence": 1498,
                })
                if plan is not None:
                    self.assertIn(STORE_MAGIC, plan.blocked_this_visit)
                    self.assertEqual(plan.index, 1 if plan.stops == [STORE_MAGIC] else 0)
                # Both the ordinary router and the invariant's saved-shelf
                # supplier path must respect the same visit evidence.
                self.assertNotEqual(policy._next_required_store_type(self.boards[1498]), STORE_MAGIC)
                self.assertIsNone(policy._town_procurement_progress_key(self.boards[1498]))
                if plan is not None:
                    # The durable stop survives a refresh of transient effect
                    # evidence; the saved supplier must still not re-acquire it.
                    policy._town_visit_ledger.nonhome_attempted_without_effect.clear()
                    self.assertIsNone(policy._town_procurement_progress_key(self.boards[1498]))

    def test_cross_town_declared_reach_overrides_stale_store_goal(self):
        policy = self._policy()
        board = self.boards[1499]  # (37,107), where live output returned '1'
        key = policy._town_teleport_dispatch_key(
            board, 2, producer="cross-town", reason=REASON)
        self.assertEqual(key, "9")
        self.assertEqual(policy._decision_goal[1].cell, (37, 119))
        self.assertTrue(policy._town_result_makes_progress(board, key))
        self.assertEqual(policy._town_procurement_decision(board, key), "9")
        self.assertEqual(policy.last_reason, REASON)

    def test_after_refusal_travel_reaches_recorded_target_without_reentry(self):
        policy = self._policy()
        self._observe_refusal(policy)
        board = self.boards[1498]
        self.assertIsNone(policy._atomic_shop_transaction_key(board))
        # Counterfactual travel: only position/turn change. The recorded map,
        # inventory, gold and shelf remain fixed; every next step is the real
        # teleport route and must survive the actual progress invariant.
        visited = set()
        while board.player.position != TARGET:
            self.assertNotIn(board.player.position, visited)
            visited.add(board.player.position)
            policy._decision_sequence += 1
            policy._observe(board)
            policy._build_grid_index(board)
            key = policy._cross_town_shopping_key(board)
            self.assertIsNotNone(key)
            self.assertEqual(policy._town_procurement_decision(board, key), key)
            dy, dx = DELTAS[key[0]]
            position = Position(board.player.position.y + dy, board.player.position.x + dx)
            self.assertNotEqual(position, ENTRANCE)
            self.assertIsNone(policy._store_visit)
            board = replace(board, player=replace(board.player, position=position),
                            turn=board.turn + 1)
        self.assertEqual(len(visited), 13)

    def test_terminal_refusal_is_not_reclassified_by_stale_home_knowledge(self):
        policy = self._policy()
        self._observe_refusal(policy)
        policy._equipment_catalog.home_scan_complete = False
        policy._home_knowledge_current = False
        self.assertIsNone(policy._atomic_shop_transaction_key(self.boards[1498]))
        self.assertIsNone(policy._store_visit)
        self.assertIn(STORE_MAGIC, policy._town_visit_ledger.nonhome_attempted_without_effect)


if __name__ == "__main__":
    unittest.main()
