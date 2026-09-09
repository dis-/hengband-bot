import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "town-owner-cluster-20260910.json.gz"


def _captured_rows(start, stop, *, restarted=True):
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        rows = json.load(stream)
    selected = [
        row for row in rows
        if start <= row["decision"]["decision_sequence"] <= stop
        and (row["decision"]["decision_sequence"] < 1000) == restarted
    ]
    return (
        [row["decision"] for row in selected],
        [parse_snapshot(row["snapshot"], {}) for row in selected],
    )


class TownOwnerClusterIncidentTest(unittest.TestCase):
    def _captured_policy_through(self, stop):
        decisions, snapshots = _captured_rows(1, stop)
        policy = HengbotPolicy()
        for snapshot in snapshots:
            key = policy.choose_key(snapshot)
            policy.confirm_key_posted(key)
        return policy

    def test_captured_home_entry_operation_never_becomes_inert_approach(self):
        _, lagged = _captured_rows(165, 165)
        _, matching_home = _captured_rows(47, 47)
        policy = self._captured_policy_through(46)
        visit = policy._store_visit
        self.assertIsNotNone(visit)
        self.assertTrue(visit.operation_posted)
        self.assertEqual(visit.phase, StoreVisitPhase.ENTERING)

        self.assertEqual(policy.choose_key(lagged[0]), "")
        visit = policy._store_visit
        self.assertIsNotNone(visit)
        self.assertTrue(visit.operation_posted)
        self.assertEqual(visit.phase, StoreVisitPhase.ENTERING)
        self.assertIsNotNone(visit.posted_sequence)

        policy.choose_key(matching_home[0])
        visit = policy._store_visit
        self.assertFalse(
            visit is not None
            and visit.phase == StoreVisitPhase.APPROACHING
            and visit.operation_posted
        )

    def test_captured_staged_home_owner_releases_instead_of_wandering(self):
        policy = self._captured_policy_through(46)
        _, wandering_observations = _captured_rows(165, 180)
        reasons = []
        malformed = []
        for snapshot in wandering_observations:
            key = policy.choose_key(snapshot)
            reasons.append(policy.last_reason)
            visit = policy._store_visit
            if (
                visit is not None
                and visit.phase == StoreVisitPhase.APPROACHING
                and visit.operation_posted
            ):
                malformed.append((key, policy.last_reason, visit.store_type))
            policy.confirm_key_posted(key)
        self.assertFalse(malformed, malformed)
        self.assertNotIn("stuck:wander", reasons)
        self.assertNotIn(
            "equipment-transaction:home-route-repeat-terminal", reasons
        )

    def test_captured_foreign_store_entry_await_posts_no_direction(self):
        decisions, snapshots = _captured_rows(4169, 4182, restarted=False)
        policy = HengbotPolicy()
        results = []
        for decision, snapshot in zip(decisions, snapshots):
            key = policy.choose_key(snapshot)
            policy.confirm_key_posted(key)
            results.append((decision["decision_sequence"], key, policy.last_reason))
        first_mismatched_page = next(row for row in results if row[0] == 4172)
        self.assertNotIn(first_mismatched_page[1], "12346789", results)
        self.assertNotEqual(first_mismatched_page[2], "shop:approach", results)


if __name__ == "__main__":
    unittest.main()
