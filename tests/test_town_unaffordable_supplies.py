"""Recorded production-policy pin for unaffordable departure supplies."""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.cli import _parse_items
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STAFF_IDENTIFY_MIN_CHARGES


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "town-unaffordable-supplies-20260915.jsonl.gz"
)
RESTART_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "town-unaffordable-supplies-restart-20260915.jsonl.gz"
)
CONTINUATION_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "town-priority-stage1-live-boards-20260915.jsonl.gz"
)
# Frozen R4 evidence: incident 1714 decision line 865, turn 2911106;
# incident 1953 decision line 4, turn 2911809.
LIVE_ROUTE_CLAIM_UNFULFILLED = ("\x1b", "home:route-claim-unfulfilled")
MONRACE_DEFINITIONS = Path(
    r"C:\hengband\.worktrees\bot-json-output\lib\edit\MonraceDefinitions.jsonc"
)


class TownUnaffordableSuppliesReplay(unittest.TestCase):
    def _replay_restart(self, *, funded: bool = False):
        with gzip.open(RESTART_FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]

        policy = HengbotPolicy()
        snapshots = []
        decisions = []
        measures = None
        for raw in rows:
            if raw["type"] == "knowledge":
                self.assertEqual(
                    (raw["knowledge"]["category"], raw["knowledge"]["menu_key"]),
                    ("home", "9"),
                )
                policy.consume_home_knowledge(
                    tuple(_parse_items(raw["knowledge"]["items"]))
                )
                continue
            snapshot = parse_snapshot(raw, {})
            if funded:
                snapshot = replace(
                    snapshot, player=replace(snapshot.player, gold=10_000)
                )
            if snapshot.turn == 2_911_820:
                conjuncts = policy._recall_town_departure_conjuncts(snapshot)
                supplier = policy._actionable_departure_supplier(snapshot)
                measures = {
                    "mode": policy._fundraising_mode,
                    "gold": snapshot.player.gold,
                    "restock_wait": policy._town_restock_wait_until,
                    "departure_ready": policy._town_departure_ready(snapshot),
                    "fundraising_departure_ready": (
                        policy._fundraising_departure_ready(snapshot)
                    ),
                    "store": snapshot.store,
                    "store_visit_released": (
                        policy._store_visit is None
                        or policy._store_visit.operation_released
                    ),
                    "supplier": supplier,
                    "supplier_attempted": (
                        supplier in policy._town_store_attempted
                        if supplier is not None else False
                    ),
                    "conjuncts": conjuncts,
                    "identify_source": policy._find_identification_source(
                        snapshot, full=True, reliable_only=True
                    ),
                }
            decisions.append((snapshot.turn, policy.choose_key(snapshot), policy.last_reason))
            snapshots.append(snapshot)
        return policy, snapshots[-1], decisions, measures

    def test_restart_recording_finishes_started_calibration_before_fundraising(self):
        """USER: finish a started calibration first."""
        policy, snapshot, decisions, measures = self._replay_restart()

        self.assertEqual(measures["mode"], "prepare")
        self.assertEqual(measures["gold"], 185)
        self.assertIsNone(measures["restock_wait"])
        self.assertFalse(measures["departure_ready"])
        self.assertTrue(measures["fundraising_departure_ready"])
        self.assertIsNone(measures["store"])
        self.assertTrue(measures["store_visit_released"])
        self.assertIsNone(measures["supplier"])
        self.assertFalse(measures["supplier_attempted"])
        self.assertFalse(measures["conjuncts"]["recall_departure_ready"])
        self.assertFalse(measures["conjuncts"]["identify_staff_ready"])
        self.assertFalse(measures["conjuncts"]["home_candidate_resolved"])
        self.assertFalse(measures["conjuncts"]["identification_need_clear"])
        self.assertFalse(
            measures["conjuncts"]["departure_identification_need_clear"]
        )
        self.assertIsNone(measures["identify_source"])
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(decisions[-3:-1], [
            (2_911_809, "5", "home:atomic-deposit"),
            (
                2_911_809,
                "dhdgdf8\rde15\rdd6\rdc11\rdbda5\r\x1b",
                "home:atomic-deposit",
            ),
        ])
        self.assertEqual(
            LIVE_ROUTE_CLAIM_UNFULFILLED,
            ("\x1b", "home:route-claim-unfulfilled"),
        )

    def test_restart_replay_stops_at_the_first_live_key_divergence(self):
        """USER: 「私が指摘しないと退行に気付けないのは重大な欠陥である。」"""
        policy, _snapshot, decisions, _measures = self._replay_restart()

        self.assertEqual(decisions[-3][1:], ("5", "home:atomic-deposit"))
        self.assertEqual(
            LIVE_ROUTE_CLAIM_UNFULFILLED,
            ("\x1b", "home:route-claim-unfulfilled"),
        )
        self.assertEqual(policy._town_order_operation, "calibration")
        self.assertEqual(policy._town_order_expected_observation, "home-deposit")
        self.assertIsNotNone(policy._home_atomic_deposit_pending)

    def test_restart_funded_counterfactual_keeps_identification_owner(self):
        policy, _snapshot, decisions, measures = self._replay_restart(funded=True)

        self.assertEqual(measures["gold"], 10_000)
        self.assertIsNotNone(measures["supplier"])
        self.assertNotEqual(policy._fundraising_mode, "scavenge")
        self.assertTrue(any(reason == "shop:approach" for _, _, reason in decisions))

    def _replay(self, *, funded: bool = False, store_board: bool = False):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]

        policy = HengbotPolicy()
        knowledge = rows.pop(0)
        self.assertEqual(
            (knowledge["type"], knowledge["turn"],
             knowledge["knowledge"]["category"],
             knowledge["knowledge"]["menu_key"]),
            ("knowledge", 2_902_792, "home", "9"),
        )
        policy.consume_home_knowledge(
            tuple(_parse_items(knowledge["knowledge"]["items"]))
        )

        decisions = []
        final_snapshot = None
        final_measures = None
        if store_board:
            rows = [*rows[:3], *rows[-2:]]
        for raw in rows:
            snapshot = parse_snapshot(raw, {})
            if funded:
                # Counterfactual: retain every recorded field except gold.
                snapshot = replace(
                    snapshot, player=replace(snapshot.player, gold=10_000)
                )
            if snapshot.turn == 2_911_111 or store_board and raw is rows[-1]:
                final_measures = {
                    "recall": policy._count_recall_scrolls(snapshot),
                    "recall_required": policy._recall_departure_minimum(snapshot),
                    "identify_charges": policy._total_identify_staff_charges(snapshot),
                    "town_departure_ready": policy._town_departure_ready(snapshot),
                    "fundraising_departure_ready":
                        policy._fundraising_departure_ready(snapshot),
                }
            key = policy.choose_key(snapshot)
            decisions.append((snapshot.turn, key, policy.last_reason))
            final_snapshot = snapshot
            if not store_board and snapshot.turn == 2_911_111:
                break
        assert final_snapshot is not None
        return policy, final_snapshot, decisions, final_measures

    def test_recorded_board_keeps_calibration_owner_before_fundraising(self):
        """USER: a plan/reason-only pin is vacuous; pin exact actions."""
        policy, snapshot, decisions, measures = self._replay()

        self.assertEqual(measures["recall"], 8)
        self.assertEqual(measures["identify_charges"], 1)
        self.assertEqual(measures["recall_required"], 9)
        self.assertEqual(STAFF_IDENTIFY_MIN_CHARGES, 20)
        self.assertFalse(measures["town_departure_ready"])
        self.assertTrue(measures["fundraising_departure_ready"])
        self.assertEqual(decisions[-3:-1], [
            (2_911_106, "5", "home:atomic-deposit"),
            (
                2_911_106,
                "dhdgdf8\rde15\rdd6\rdc11\rdbda5\r\x1b",
                "home:atomic-deposit",
            ),
        ])
        self.assertEqual(
            LIVE_ROUTE_CLAIM_UNFULFILLED,
            ("\x1b", "home:route-claim-unfulfilled"),
        )
        self.assertFalse(policy._dungeon_entry_allowed(
            snapshot, via_recall=False, destination_depth=1
        ))
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_operator_continuation_stops_at_first_key_mismatch(self):
        """USER: a plan/reason-only pin is vacuous; pin exact actions."""
        policy, _snapshot, _decisions, _measures = self._replay()
        knowledge = load_monrace_knowledge(MONRACE_DEFINITIONS)
        policy._monrace_knowledge = knowledge
        with gzip.open(CONTINUATION_FIXTURE, "rt", encoding="utf-8") as stream:
            boards = [json.loads(line) for line in stream]

        self.assertEqual(len(boards), 65)  # bot-state rows 5980-6044 inclusive
        first = parse_snapshot(boards[0], knowledge)
        emitted = policy.choose_key(first)
        operator_key_for_next_board = "\x10"  # cap-04, state_line 5983
        self.assertEqual(
            (emitted, policy.last_reason, operator_key_for_next_board),
            ("~9\x1b\x1b", "home:request-knowledge-scan", "\x10"),
        )

    def test_identical_live_macros_have_board_backed_home_effects(self):
        """USER: finish a started calibration first."""
        with gzip.open(CONTINUATION_FIXTURE, "rt", encoding="utf-8") as stream:
            boards = [json.loads(line) for line in stream]
        # Rows 6028 -> 6036 are the exact effect of cap-66's deposit macro;
        # rows 6036 -> 6044 are the exact effect of cap-67's withdrawal macro.
        self.assertEqual(
            (len(boards[48]["inventory"]), len(boards[56]["inventory"])),
            (16, 8),
        )
        self.assertEqual(
            (len(boards[56]["inventory"]), len(boards[64]["inventory"])),
            (8, 16),
        )

    def test_affordable_counterfactual_keeps_purchase_route(self):
        policy, snapshot, decisions, _measures = self._replay(funded=True)

        approaches = [row for row in decisions if row[2] == "shop:approach"]
        self.assertEqual(approaches[0], (2_911_096, "9", "shop:approach"))
        self.assertEqual(policy._actionable_departure_supplier(snapshot), 7)
        self.assertIsNone(policy._fundraising_mode)

    def test_recorded_low_gold_store_board_leaves_through_store_path(self):
        policy, snapshot, decisions, _measures = self._replay(store_board=True)

        self.assertIsNone(snapshot.store)
        self.assertEqual(snapshot.player.gold, 185)
        self.assertEqual(
            decisions[-2], (2_911_293, "\x1b", "shop:observe-and-leave")
        )
        self.assertEqual(decisions[-1], (2_911_306, "\x1b`n(.", "shop:travel"))
        self.assertEqual(policy._fundraising_mode, "prepare")


if __name__ == "__main__":
    unittest.main()
