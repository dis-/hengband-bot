from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from hengbot.cli import _write_decision
from hengbot.emit_ownership import emit_ownership_verdict
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"


class EmitOwnershipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with CAPTURE.open(encoding="utf-8") as stream:
            cls.snapshot = parse_snapshot(json.loads(next(stream)), {})

    def _visit(self, **changes):
        visit = StoreVisit(
            owner="town-plan", purpose="test", store_type=7,
            phase=StoreVisitPhase.LEAVING, posted_sequence=12,
        )
        return replace(visit, **changes)

    def test_different_store_is_shadow_blocked_and_control_disarms_clause(self):
        inside_store = SimpleNamespace(store=SimpleNamespace(store_type=3))
        verdict = emit_ownership_verdict(self._visit(), inside_store, "6", None)
        self.assertTrue(verdict.blocked)
        self.assertEqual("leaving-with-posted-sequence", verdict.in_flight_clause)
        control = emit_ownership_verdict(
            self._visit(phase=StoreVisitPhase.CLOSED, posted_sequence=None),
            inside_store, "6", None,
        )
        self.assertFalse(control.blocked)

    def test_decision_log_records_populated_shadow_verdict_without_changing_key(self):
        policy = HengbotPolicy()
        verdict = {
            "blocked": True, "target_store": 3, "visit_store": 7,
            "phase": "leaving", "in_flight_clause": "leaving-with-posted-sequence",
            "target_source": "snapshot.store.store_type",
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bot-decisions.jsonl"
            _write_decision(
                path, self.snapshot, "6", "shop:observe-and-leave", policy,
                town_emit_ownership=verdict,
            )
            row = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("6", row["key"])
        self.assertEqual(verdict, row["town_emit_ownership"])


if __name__ == "__main__":
    unittest.main()
