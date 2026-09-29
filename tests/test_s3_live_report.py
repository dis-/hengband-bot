import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.s3_live_report import format_report, summarize, timestamp


class S3LiveReportTest(unittest.TestCase):
    def test_window_and_counts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            decisions = root / "decisions.jsonl"
            states = root / "states.jsonl"
            metrics = root / "ownership-metrics.jsonl"

            def write(path, rows):
                path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

            write(decisions, [
                {"time": "2026-09-29T09:59:59+09:00", "reason": "old"},
                {"time": "2026-09-29T10:01:00+09:00", "decision_sequence": 11,
                 "reason": "shop:one-shot-in-flight", "key": "",
                 "claim": {"violation": {"scope": "S3"},
                           "claim_verdict_conflict": {"kind": "test"},
                           "errand_deferred": [{"owner": "shop"}]}},
                {"time": "2026-09-29T10:02:00+09:00", "decision_sequence": 12,
                 "reason": "ownership:holder-silent:shop", "key": None},
                {"time": "2026-09-29T10:03:00+09:00", "decision_sequence": 13,
                 "reason": "town:blocked:owner-retired", "key": None},
                {"time": "2026-09-29T10:04:00+09:00", "decision_sequence": 14,
                 "reason": "shop:barrier-provenance-missing", "key": None},
            ])
            write(states, [{"time": "2026-09-29T10:01:30+09:00"}])
            write(metrics, [{"time": "2026-09-29T10:05:00+09:00",
                             "kind": "stop", "shape": "no-exit"}])
            result = summarize(decisions, states,
                               timestamp("2026-09-29T10:00:00+09:00"),
                               timestamp("2026-09-29T10:30:00+09:00"), metrics)
            self.assertEqual(result["minutes"], 30)
            self.assertEqual(result["stops_per_hour"]["no-exit"], 2)
            self.assertEqual(result["s3_violations_per_hour"], 2)
            self.assertEqual(result["claim_verdict_conflict"], 1)
            self.assertEqual(result["errand_deferred"], 1)
            self.assertEqual(result["typed_observation_waits"],
                             {"shop:one-shot-in-flight": 1})
            self.assertEqual([sequence for sequence, _ in result["typed_stops"]],
                             [12, 13, 14])
            self.assertIn("12: ownership:holder-silent:shop", format_report(result))


if __name__ == "__main__":
    unittest.main()
