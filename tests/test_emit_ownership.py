from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot.cli import _build_argument_parser, _run_follow, _write_decision, main
from hengbot.emit_ownership import derive_target_store, emit_ownership_verdict
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from tests.test_cli import _snap_line


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"


class EmitOwnershipTest(unittest.TestCase):
    @staticmethod
    def _capture_snapshot():
        with CAPTURE.open(encoding="utf-8") as stream:
            return parse_snapshot(json.loads(next(stream)), {})

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

    def test_specific_key_target_precedes_stale_ambient_approach(self):
        snapshot = self._movement_snapshot({
            Position(9, 20): SimpleNamespace(store_number=3),
        })
        self.assertEqual(
            (3, "stepped-onto-store-grid"),
            derive_target_store(snapshot, "8", 7),
        )

    def test_native_travel_target_precedes_inside_store_context(self):
        snapshot = SimpleNamespace(store=SimpleNamespace(store_type=7))
        self.assertEqual(
            (3, "native-travel-key"),
            derive_target_store(snapshot, "\x1b`n$.", 6),
        )

    def test_escape_inside_store_has_no_store_target_and_fails_open(self):
        snapshot = SimpleNamespace(store=SimpleNamespace(store_type=0))
        for key in ("\x1b", "\x1b\x1b", "\x1b" * 8):
            with self.subTest(length=len(key)):
                self.assertEqual(
                    (None, "store-exit-key"),
                    derive_target_store(snapshot, key, 3),
                )
                verdict = emit_ownership_verdict(self._visit(), snapshot, key, 3)
                self.assertFalse(verdict.blocked)
                self.assertIsNone(verdict.target_store)

    def test_direction_inside_store_is_not_treated_as_town_movement(self):
        snapshot = SimpleNamespace(
            store=SimpleNamespace(store_type=0),
            player=SimpleNamespace(position=Position(y=10, x=20)),
            grid_at=lambda _position: SimpleNamespace(store_number=3),
        )
        self.assertEqual(
            (0, "snapshot.store.store_type"),
            derive_target_store(snapshot, "8", 7),
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

    @unittest.skipUnless(CAPTURE.is_file(), "frozen capture is not present")
    def test_decision_log_records_populated_shadow_verdict_without_changing_key(self):
        snapshot = self._capture_snapshot()
        policy = HengbotPolicy()
        verdict = {
            "blocked": True, "target_store": 3, "visit_store": 7,
            "phase": "leaving", "in_flight_clause": "leaving-with-posted-sequence",
            "target_source": "snapshot.store.store_type",
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bot-decisions.jsonl"
            _write_decision(
                path, snapshot, "6", "shop:observe-and-leave", policy,
                town_emit_ownership=verdict,
            )
            row = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("6", row["key"])
        self.assertEqual(verdict, row["town_emit_ownership"])

    @unittest.skipUnless(CAPTURE.is_file(), "frozen capture is not present")
    def test_once_cli_emit_site_computes_and_logs_the_production_verdict(self):
        policy = HengbotPolicy()
        policy._store_visit = self._visit()
        policy._shopping_approach_store_type = 3
        def prime(_snapshot):
            policy._store_visit = self._visit()
            policy._shopping_approach_store_type = 3

        policy.prime = unittest.mock.Mock(side_effect=prime)
        policy.choose_key = unittest.mock.Mock(return_value="\x1b`n$.")
        policy.validate_read_key = unittest.mock.Mock(return_value="\x1b`n$.")
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
        self.assertEqual("\x1b`n$.", written[0][0][2])
        verdict = written[0][1]["town_emit_ownership"]
        self.assertEqual(7, verdict["visit_store"])
        self.assertTrue(verdict["blocked"], verdict)
        self.assertEqual(3, verdict["target_store"])
        self.assertEqual("native-travel-key", verdict["target_source"])

    def test_follow_and_retry_sites_log_their_own_populated_verdicts(self):
        class RefuseFirstPosting:
            def __init__(self):
                self.last_incident = None
                self.calls = 0

            def allow(self, _snapshot, key, owner, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    self.last_incident = {
                        "marker": "posting-contract:test-refusal",
                        "owner": owner,
                        "key": key,
                    }
                    return False
                self.last_incident = None
                return True

            def posted(self, *_args):
                pass

        line = _snap_line(1, 52, 48)
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.jsonl"
            state_path.write_text(line, encoding="utf-8")
            args = _build_argument_parser().parse_args([
                "--state-file", str(state_path), "--poll-interval", "0.001",
            ])
            args.wait_telemetry = unittest.mock.Mock()
            policy = HengbotPolicy()
            policy._store_visit = self._visit()
            policy._shopping_approach_store_type = 3
            policy.prime = unittest.mock.Mock()
            choices = iter(("\x1b`n$.", "\x1b`n$.", ""))

            def choose(_snapshot):
                key = next(choices)
                policy.last_reason = (
                    "equipment-transaction:restore-blocked-terminal"
                    if not key else "shop:observe-and-leave"
                )
                return key

            policy.choose_key = unittest.mock.Mock(side_effect=choose)
            written = []

            def append_rows():
                time.sleep(0.5)
                with state_path.open("a", encoding="utf-8") as stream:
                    stream.write(line)
                    stream.flush()
                    time.sleep(0.5)
                    stream.write(line.replace('"turn":', '"turn":'))
                    stream.flush()

            producer = threading.Thread(target=append_rows)
            producer.start()
            try:
                with (
                    patch("hengbot.cli._write_decision", side_effect=lambda *a, **k: written.append((a, k))),
                    patch("hengbot.cli._append_capture_ledger"),
                    patch("hengbot.cli._freeze_incident_safely"),
                ):
                    result = _run_follow(
                        args, policy, lambda *_a, **_k: True, {},
                        posting_contract=RefuseFirstPosting(),
                    )
            finally:
                producer.join()

        self.assertEqual(0, result)
        verdicts = [entry[1]["town_emit_ownership"] for entry in written[:2]]
        self.assertEqual(2, len(verdicts))
        for verdict in verdicts:
            self.assertTrue(verdict["blocked"], verdict)
            self.assertEqual(3, verdict["target_store"])
            self.assertEqual(7, verdict["visit_store"])


if __name__ == "__main__":
    unittest.main()
