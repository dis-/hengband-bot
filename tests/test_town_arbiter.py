import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import _decision_record
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURES = Path(__file__).parent / "fixtures"
DECISION_CAPTURES = (
    "incident-equipment-abandon-loop-20260822.jsonl",
    "incident-alchemist-repetition-20260823.jsonl",
    "incident-launcher-repetition-20260823.jsonl",
    "incident-calibration-entry-await-20260823.jsonl",
    "incident-magic-abandon-cycle-20260823.jsonl",
)


class TownTurnArbiterAcceptanceTest(unittest.TestCase):
    @staticmethod
    def _postlevel_snapshot():
        fixture = FIXTURES / "incident-postlevel-repetition-turn-1006064.jsonl.gz"
        with gzip.open(fixture, "rt", encoding="utf-8-sig") as stream:
            return parse_snapshot(json.loads(next(stream)), {})

    def test_pin_vacuity_postlevel_public_choose_key_consumes_retirement_budget(self):
        snapshot = self._postlevel_snapshot()
        policy = HengbotPolicy()
        rows = []
        budget = policy._town_turn_arbiter.registry["home-scan"].budget
        for _ in range(budget + 1):
            key = policy.choose_key(snapshot)
            rows.append(_decision_record(
                snapshot,
                key,
                policy.last_reason,
                decision_sequence=policy._decision_sequence,
                arbiter=policy._town_turn_arbiter.telemetry,
            ))

        self.assertTrue(rows)
        for row in rows:
            with self.subTest(sequence=row["decision_sequence"]):
                self.assertIsNotNone(row["arbiter"]["owner"])
                self.assertEqual(
                    {
                        "owner", "tenure", "progress",
                        "budget_remaining_estimate", "would_retire",
                    },
                    set(row["arbiter"]),
                )
        self.assertFalse(rows[0]["arbiter"]["would_retire"])
        self.assertTrue(any(row["arbiter"]["would_retire"] for row in rows[:budget + 1]))

    def test_pin_vacuity_registered_owner_consumes_golden_and_capture_reasons(self):
        from test_golden_trajectory import GoldenOpeningTrajectoryTest

        policy = HengbotPolicy()
        arbiter = policy._town_turn_arbiter
        registered = set(arbiter.registry)
        reasons = []
        for name in DECISION_CAPTURES:
            with (FIXTURES / name).open(encoding="utf-8-sig") as stream:
                reasons.extend(
                    json.loads(line).get("reason", "")
                    for line in stream if line.strip()
                )

        golden_policy, world = GoldenOpeningTrajectoryTest().build()
        for decision in range(1, 21):
            world.deliver_events(golden_policy)
            key = golden_policy.choose_key(world.snapshot(decision))
            reasons.append(golden_policy.last_reason)
            golden_policy.confirm_key_posted(key)
            world.apply(key)

        self.assertTrue(reasons)
        owners = [arbiter.owner_for_reason(reason) for reason in reasons]
        self.assertTrue(all(owner in registered for owner in owners))
        self.assertNotIn(None, owners)


if __name__ == "__main__":
    unittest.main()
