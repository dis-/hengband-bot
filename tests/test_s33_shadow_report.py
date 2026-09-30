"""Small synthetic window pins every shadow aggregation and first occurrence."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import tests  # noqa: F401
from s33_shadow_report import render, summarize, timestamp


class ShadowReportTest(unittest.TestCase):
    def test_window_counts_grouping_first_rows_and_partial_tail(self):
        def row(seq, minute, producer, stop, *, gap=False, mismatch=None):
            return {"time": f"2026-10-01T00:{minute:02d}:00Z",
                    "decision_sequence": seq, "reason": producer,
                    "s33_shadow": {"would_stop": stop,
                        "holder_family": "home-visit", "holder_claim_id": 12,
                        "declaration_state": None if gap else "acting",
                        "declaration_gap": gap, "mismatch": mismatch,
                        "would_skip_families": ["rumor", "shop-buy"]}}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            path.write_text("\n".join(map(json.dumps, [
                row(0, 0, "outside", None),
                row(1, 1, "town:rumor-batch", "ownership:gate-missing:rumor", gap=True),
                row(2, 2, "town:rumor-batch", "ownership:gate-missing:rumor"),
                row(3, 3, "town:rumor-single", "ownership:gate-missing:rumor",
                    mismatch={"inferred": "acting", "declared": None}),
                row(4, 4, "shop:travel", None),
                {"time": "2026-10-01T00:04:30Z", "decision_sequence": 5},
                row(6, 5, "outside", "ownership:gate-missing:rumor"),
            ])) + '\n{"partial":', encoding="utf8")
            report = summarize(path, timestamp("2026-10-01T00:01:00Z"),
                               timestamp("2026-10-01T00:05:00Z"))
        self.assertEqual((report["minutes"], report["decisions"],
                          report["shadow_decisions"]), (4, 5, 4))
        self.assertEqual(report["would_stop"], [{"reason": "ownership:gate-missing:rumor",
            "family": "home-visit", "count": 3}])
        self.assertEqual([(r["producer_reason"], r["decision_sequence"], r["time"])
                          for r in report["first_stops"]], [
            ("town:rumor-batch", 1, "2026-10-01T00:01:00Z"),
            ("town:rumor-single", 3, "2026-10-01T00:03:00Z")])
        self.assertEqual(report["declaration_gaps"], {"home-visit": 1})
        self.assertEqual(report["mismatches"], {"home-visit": 1})
        self.assertEqual(report["gate_leaks"], {"rumor": 3})
        self.assertEqual(report["would_skip"], {"rumor": 4, "shop-buy": 4})
        self.assertIn("minutes=4 decisions=5 shadow_decisions=4", render(report))

    def test_invalid_window_is_rejected(self):
        when = timestamp("2026-10-01T00:00:00Z")
        with self.assertRaises(ValueError):
            summarize(Path("unused"), when, when)


if __name__ == "__main__":
    unittest.main()
