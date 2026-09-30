"""The 2026-09-29/30 Home torch takes and immediate reverse deposits."""

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.claim_register import observe
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.policy import HengbotPolicy
from policy_fixtures import grid


FIXTURE = Path(__file__).parent / "fixtures" / "torch-predicate-20260929-30.json.gz"
FIXTURE_SHA256 = "91a2bdff6260ed1735b18b37ed4e5209de92c8b087d9dc5312b94718f4d76d2b"


class TorchPredicateRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def test_recorded_reverse_deposits_share_one_carry_requirement(self):
        expected = (
            ((4, "home:atomic-withdraw", "5pl5\r\x1b"),
             (5, "home:atomic-deposit", "5"),
             (6, "home:atomic-deposit", "dk5\r\x1b"),
             (7, "town:entrance-step-off:home:atomic-deposit", "6"),
             (8, "ownership:declaration-stale:home-visit", None)),
            ((7666, "home:atomic-withdraw", "5pn5\r\x1b"),
             (7667, "equipment-transaction:atomic-deposit", "5"),
             (7668, "home:weight-overload-deposit", "dh15\r\x1b")),
            ((2178, "home:atomic-withdraw", "5pn5\r\x1b"),
             (2179, "equipment-transaction:atomic-deposit", "5"),
             (2180, "home:atomic-deposit", "dk5\r\x1b")),
        )
        strategy = SimpleNamespace(required_force={"throwing_items": {"lit_torch": 5}})
        for case, rows in zip(self.cases, expected):
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    [(row["decision_sequence"], row["reason"], row["key"])
                     for row in case["rows"]], list(rows))
                take = case["rows"][0]["home_atomic_withdraw"]
                self.assertEqual(take["quantity"], 5)
                self.assertEqual(take["selected_signature"][1:], [39, 0])
                snapshot = parse_snapshot(case["state"])
                torch = next(item for item in snapshot.inventory if item.is_torch)
                policy = HengbotPolicy()
                with patch.object(policy, "_carry_procurement_strategy", return_value=strategy):
                    target, carried = policy._torch_carry_requirement(snapshot, torch, strategy)
                    self.assertEqual(target, 5)
                    self.assertEqual(carried, torch.count)
                    self.assertEqual(policy._procurement_missing_amount(snapshot, torch), 0)
                    self.assertEqual(policy._retention_reservation(snapshot, torch), 5)
                    self.assertEqual(policy._retention_surplus(snapshot, torch),
                                     max(0, torch.count - 5))
                    if torch.count == 5:
                        self.assertIsNone(policy._overweight_home_deposit(snapshot))
                        self.assertFalse(policy._home_deposit_candidate(torch, snapshot))
                        # The former matching-ammo early return made the
                        # whole just-withdrawn stack eligible for deposit.
                        with patch.object(policy, "_retention_reservation_detail",
                                          return_value=(0, None)):
                            self.assertTrue(policy._home_deposit_candidate(torch, snapshot))
                if "before_state" in case:
                    before = parse_snapshot(case["before_state"])
                    prior = next(item for item in before.inventory if item.is_torch)
                    self.assertEqual(prior.count, 10)
                    with patch.object(policy, "_carry_procurement_strategy", return_value=strategy):
                        self.assertEqual(policy._procurement_missing_amount(before, prior), 0)

    def test_recorded_step_off_completes_home_visit_declaration(self):
        case = self.cases[0]
        step, stopped = case["rows"][-2:]
        self.assertEqual(step["claim"]["execution"]["next_step"],
                         "departure.step-off-entrance")
        awaiting = stopped["claim"]["execution"]
        self.assertEqual((awaiting["state"], awaiting["continuation"],
                          awaiting["arguments"]),
                         ("awaiting", "departure.step-off-entrance", [45, 124]))
        snapshot = parse_snapshot(case["after_step_state"])
        self.assertEqual((snapshot.player.position.y, snapshot.player.position.x),
                         (45, 124))
        policy = HengbotPolicy()
        claim = policy._claim_register.declare(
            "home-visit", observe(("store-operation",), 8, "store-operation")
        )
        policy._claim_register.declare_execution(
            claim.claim_id, work_id=awaiting["work_id"],
            producer="home-visit", state="awaiting",
            arguments=tuple(awaiting["arguments"]),
            operation_ref=awaiting["operation_ref"],
            expected_effect=awaiting["expected_effect"],
            continuation=awaiting["continuation"],
        )
        self.assertIsNone(policy._town_holder_declared_key(
            policy._claim_register.current, snapshot))
        self.assertTrue(policy._decision_no_step_release)
        self.assertEqual(policy.last_reason, "ownership:holder-released:home-visit")
        self.assertEqual(policy._claim_register.current.closed_reason,
                         "no-step:entrance-cell-cleared")

    def test_recorded_ten_torch_board_cancels_stale_home_take(self):
        case = self.cases[1]
        before = parse_snapshot(case["before_state"])
        position = before.player.position
        entrance = replace(grid(position.y, position.x), store_number=STORE_HOME)
        before = replace(before, store=None,
                         grids={**before.grids, position: entrance})
        torch = next(item for item in before.inventory if item.is_torch)
        self.assertEqual(torch.count, 10)
        policy = HengbotPolicy()
        signature = policy._item_signature(torch)
        policy._shopping_approach_store_type = STORE_HOME
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [torch]
        policy._home_knowledge_valid_before = 1
        policy._home_page_size = 52
        policy._home_pending_item = signature
        policy._home_pending_quantity = 5
        policy._home_pending_quantities[signature] = 5
        policy._home_withdrawal_queued = True
        strategy = SimpleNamespace(required_force={"throwing_items": {"lit_torch": 5}})
        with (patch.object(policy, "_carry_procurement_strategy", return_value=strategy),
              patch.object(policy, "_town_entrance_step_off_key", return_value="6")
              as step_off):
            self.assertEqual(policy._atomic_home_withdraw_key(before, position), "6")
        step_off.assert_called_once_with(
            before, "home:atomic-withdraw-no-longer-needed")
        self.assertIsNone(policy._home_pending_item)
        self.assertNotIn(signature, policy._home_pending_quantities)
        self.assertFalse(policy._home_withdrawal_queued)


if __name__ == "__main__":
    unittest.main()
