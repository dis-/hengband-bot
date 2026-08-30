from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot.cli import _write_decision, main
from hengbot.emit_ownership import derive_target_store, emit_ownership_verdict
from hengbot.model import Position, parse_snapshot
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

    @staticmethod
    def _movement_snapshot(grids):
        return SimpleNamespace(
            store=None,
            player=SimpleNamespace(position=Position(y=10, x=20)),
            grid_at=lambda position: grids.get(position),
        )

    def test_direction_fallback_projects_y_x_for_every_movement_key(self):
        destinations = {
            "7": Position(9, 19), "8": Position(9, 20), "9": Position(9, 21),
            "4": Position(10, 19), "6": Position(10, 21),
            "1": Position(11, 19), "2": Position(11, 20), "3": Position(11, 21),
        }
        for store_number, (key, destination) in enumerate(destinations.items()):
            with self.subTest(key=key):
                snapshot = self._movement_snapshot({
                    destination: SimpleNamespace(store_number=store_number),
                })
                self.assertEqual(
                    (store_number, "stepped-onto-store-grid"),
                    derive_target_store(snapshot, key, None),
                )

    def test_direction_fallback_plain_floor_is_not_a_store_and_fails_open(self):
        snapshot = self._movement_snapshot({
            Position(9, 20): SimpleNamespace(store_number=-1),
        })
        self.assertEqual((None, "undetermined"), derive_target_store(snapshot, "8", None))
        verdict = emit_ownership_verdict(self._visit(), snapshot, "8", None)
        self.assertFalse(verdict.blocked)
        self.assertIsNone(verdict.target_store)
        self.assertEqual("undetermined", verdict.target_source)

    def test_direction_fallback_store_grid_returns_its_number(self):
        snapshot = self._movement_snapshot({
            Position(9, 20): SimpleNamespace(store_number=3),
        })
        self.assertEqual(
            (3, "stepped-onto-store-grid"),
            derive_target_store(snapshot, "8", None),
        )

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

    def test_once_cli_emit_site_computes_and_logs_the_production_verdict(self):
        policy = HengbotPolicy()
        policy._store_visit = self._visit()
        policy._shopping_approach_store_type = 3
        policy.prime = unittest.mock.Mock()
        policy.choose_key = unittest.mock.Mock(return_value="6")
        policy.validate_read_key = unittest.mock.Mock(return_value="6")
        policy.last_reason = "shop:observe-and-leave"
        written = []

        def observe(*args, **kwargs):
            written.append((args, kwargs))

        with TemporaryDirectory() as directory:
            decision_path = Path(directory) / "decisions.jsonl"
            with (
                patch("hengbot.cli.ConservativePolicy", return_value=policy),
                patch("hengbot.cli._capture_decision_facts", return_value={}),
                patch("hengbot.cli._write_decision", side_effect=observe),
                patch("hengbot.cli._bot_play_macros_ready", return_value=True),
            ):
                result = main([
                    "--once", "--state-file", str(CAPTURE),
                    "--decision-log", str(decision_path),
                ])

        self.assertEqual(0, result)
        self.assertEqual(1, len(written))
        self.assertEqual("6", written[0][0][2])
        verdict = written[0][1]["town_emit_ownership"]
        self.assertEqual(7, verdict["visit_store"])
        self.assertIn("blocked", verdict)
        self.assertIn("target_source", verdict)


if __name__ == "__main__":
    unittest.main()
