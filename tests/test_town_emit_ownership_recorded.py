import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from town_emit_ownership_recorded import measure


class RecordedEmitOwnershipMeasurementTest(unittest.TestCase):
    @staticmethod
    def _decision(key: str, *, second: int = 0) -> dict:
        return {
            "time": f"2026-08-31T12:00:{second:02d}+09:00",
            "turn": 10,
            "key": key,
            "reason": "shop:test",
            "store_type": None,
            "position": {"y": 1, "x": 1},
            "store_visit": {
                "owner": "shop-one-shot",
                "purpose": "test",
                "store_type": 7,
                "opened_sequence": 1,
                "phase": "entering",
                "operation_posted": True,
                "operation_released": False,
                "operation_effect_observed": False,
                "posted_sequence": 1,
                "posted_turn": 10,
            },
        }

    def _measure(self, decisions: list[dict], ledger: dict):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in decisions),
                encoding="utf-8",
            )
            return measure(path, None, ledger, restrict_to_snapshots=False)

    def test_controls_re_evaluate_wrong_values(self):
        decision = self._decision("5")
        ledger = {(10, "5"): [(1, datetime(2026, 8, 31, 12, 0, 0))]}
        totals = self._measure([decision], ledger)["totals"]

        self.assertEqual(totals["observable_and_target_determined"], 0)
        self.assertEqual(totals["observable_and_undetermined"], 1)
        self.assertEqual(totals["control_force_different_target_before"], 0)
        self.assertEqual(totals["control_force_different_target_after"], 1)
        self.assertEqual(totals["control_force_different_target_determined"], 1)
        self.assertEqual(totals["control_clear_in_flight_before"], 1)
        self.assertEqual(totals["control_clear_in_flight_after"], 0)

    def test_all_escape_design_exception_survives_forced_ambient_target(self):
        decision = self._decision("\x1b")
        ledger = {(10, "\x1b"): [(1, datetime(2026, 8, 31, 12, 0, 0))]}
        totals = self._measure([decision], ledger)["totals"]

        self.assertEqual(totals["control_force_different_target_after"], 0)
        self.assertEqual(totals["control_force_different_target_determined"], 0)

    def test_join_counts_unmatched_decision_in_denominator_classes(self):
        decisions = [self._decision("5"), self._decision("5", second=1), self._decision("6")]
        ledger = {(10, "5"): [(1, datetime(2026, 8, 31, 12, 0, 0))]}
        totals = self._measure(decisions, ledger)["totals"]

        self.assertEqual(totals["recorded_posts"], 1)
        self.assertEqual(totals["unmatched_candidates_consumed"], 1)
        self.assertEqual(totals["unmatched_no_candidate"], 1)


if __name__ == "__main__":
    unittest.main()
