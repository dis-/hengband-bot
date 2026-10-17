from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime state for standalone module runs
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import STORE_ALCHEMIST, STORE_HOME
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
BOARDS = FIXTURES / "weight-deposit-loop-20261018.boards.jsonl.gz"
DECISIONS = FIXTURES / "weight-deposit-loop-20261018.decisions.jsonl.gz"
WEIGHT_LIMIT = 1650


class WeightDepositLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(BOARDS, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream]
        with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
            cls.decisions = [json.loads(line) for line in stream]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _policy_for(self, board):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        snapshot = parse_snapshot(board, self.monrace)
        policy.prime(snapshot)
        return policy, snapshot

    def test_capture_pins_repeated_deposit_posts_and_unsatisfied_stop(self):
        self.assertEqual(
            [(row["decision_sequence"], row["key"], row["reason"])
             for row in self.decisions],
            [
                (4853, "du2\rdtdsdr2\rdqdpdo\x1b", "home:weight-overload-deposit"),
                (4877, "dpdo2\rdg\x1b", "home:weight-overload-deposit"),
                (7, "5", "home:weight-overload-deposit"),
                (8, "do15\rde3\r\x1b", "home:weight-overload-deposit"),
                (13, "5", "home:weight-overload-deposit"),
                (14, "dp50\r\x1b", "home:weight-overload-deposit"),
                (19, "5", "home:weight-overload-deposit"),
                (20, "dq32\r\x1b", "home:weight-overload-deposit"),
                (4, "5", "home:weight-overload-deposit"),
                (5, "de3\r\x1b", "home:weight-overload-deposit"),
                (14, "1", "town:blocked:departure-unsatisfiable"),
            ],
        )
        self.assertEqual(
            sum(row["reason"] == "home:weight-overload-deposit" for row in self.decisions),
            10,
        )
        self.assertEqual(
            [self._weight(row) for row in self.boards], [1718, 1703, 1703]
        )
        home_before, home_after = self.boards[:2]
        self.assertEqual(home_before["store"]["store_type"], STORE_HOME)
        self.assertEqual(
            (home_before["store"]["stock_num"], home_before["store"]["capacity"]),
            (155, 240),
        )
        self.assertEqual(
            (home_after["store"]["stock_num"], home_after["store"]["capacity"]),
            (156, 240),
        )

    def test_deposit_remains_first_when_it_can_reduce_weight(self):
        policy, snapshot = self._policy_for(self.boards[0])
        deposit = policy._overweight_home_deposit(snapshot)
        self.assertIsNotNone(deposit)
        self.assertEqual((deposit.name, deposit.count, deposit.weight),
                         ("\u5e30\u9084\u306e\u8a54\u306e\u5dfb\u7269", 10, 5))
        deposited_weight = deposit.weight * policy._retention_surplus(snapshot, deposit)
        self.assertGreater(deposited_weight, 0)
        self.assertLess(policy._inventory_weight(snapshot) - deposited_weight,
                        policy._inventory_weight(snapshot))
        needs = policy._town_need_candidates(snapshot)
        self.assertIn("weight-overload", {need.category for need in needs})
        self.assertIsNone(policy._overweight_surplus_disposal)

    def test_no_deposit_candidate_admits_existing_surplus_sale_route(self):
        policy, snapshot = self._policy_for(self.boards[2])
        self.assertEqual(
            (policy._inventory_weight(snapshot), policy._inventory_weight_limit(snapshot)),
            (1703, WEIGHT_LIMIT),
        )
        self.assertIsNone(policy._overweight_home_deposit(snapshot))
        # CONSTRUCTED from the captured Home pages: this process had observed
        # stock 156/240 before the later departure board.
        policy._home_capacity_observation = (
            156, 240, policy._effective_town_id(snapshot)
        )
        needs = policy._town_need_candidates(snapshot)
        self.assertIn("overweight-surplus", {need.category for need in needs})
        self.assertIsNotNone(policy._overweight_surplus_disposal)
        self.assertTrue(any(
            need.category == "overweight-surplus" and need.store_type == STORE_ALCHEMIST
            for need in needs
        ))

        # The public decision path takes the route to the existing sale owner.
        policy._skill_exp_cache = (0, 0, snapshot.player.level,
                                   policy._town_visit_epoch)
        key = policy.choose_key(snapshot)
        self.assertEqual((str(key), policy.last_reason), ("\x1b`n%.", "shop:travel"))

    def test_reserved_departure_supplies_never_enter_surplus_disposal(self):
        policy, snapshot = self._policy_for(self.boards[2])
        reserved = next(item for item in snapshot.inventory
                        if item.name == "\u5e30\u9084\u306e\u8a54\u306e\u5dfb\u7269")
        self.assertGreater(policy._retention_reservation(snapshot, reserved), 0)
        candidates = policy._overweight_surplus_candidates(snapshot)
        candidate_signatures = {entry[1] for entry in candidates}
        self.assertNotIn(policy._item_signature(reserved), candidate_signatures)
        self.assertTrue(all(
            policy._retention_reservation(snapshot, item) == 0
            for _, _, item, _, _ in candidates
        ))

    @staticmethod
    def _weight(board):
        return sum(item["weight"] * item["count"]
                   for item in (*board["inventory"], *board["equipment"]))


if __name__ == "__main__":
    unittest.main()
