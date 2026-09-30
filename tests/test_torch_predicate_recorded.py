"""The 2026-09-29/30 Home torch takes and immediate reverse deposits."""

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "torch-predicate-20260929-30.json.gz"
FIXTURE_SHA256 = "25d254c015ad03fbe7e7155f05e8db25fa31148791f589b2ab31f8d44edd41f0"


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


if __name__ == "__main__":
    unittest.main()
