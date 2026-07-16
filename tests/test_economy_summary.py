import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.economy_summary import summarize


def _entry(stamp: float, kind: str, amount: int, cause: str) -> str:
    return json.dumps(
        {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S+0900", time.localtime(stamp)),
            "kind": kind,
            "amount": amount,
            "cause_reason": cause,
        }
    )


class EconomySummaryTest(unittest.TestCase):
    def test_aggregates_window_and_attributes_mining(self):
        now = time.mktime(time.strptime("2026-07-16T13:00:00", "%Y-%m-%dT%H:%M:%S"))
        lines = [
            _entry(now - 30 * 60, "income", 100, "fundraise:seek-loot"),
            _entry(now - 20 * 60, "income", 50, "shop:sell-device"),
            _entry(now - 10 * 60, "expense", 40, "shop:buy-food"),
            # outside the window: ignored
            _entry(now - 120 * 60, "income", 999, "fundraise:seek-loot"),
        ]
        with TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            ledger.write_text("\n".join(lines), encoding="utf-8")
            line = summarize(ledger, 60, now=now)
        self.assertIn("income 150g", line)
        self.assertIn("mining 100g/1 picks", line)
        self.assertIn("expense 40g", line)
        self.assertIn("net +110g", line)
        self.assertIn("3 events", line)

    def test_tolerates_blank_and_malformed_lines(self):
        now = time.mktime(time.strptime("2026-07-16T13:00:00", "%Y-%m-%dT%H:%M:%S"))
        lines = ["", "not-json", _entry(now - 60, "income", 10, "fundraise:seek-loot")]
        with TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            ledger.write_text("\n".join(lines), encoding="utf-8")
            line = summarize(ledger, 60, now=now)
        self.assertIn("income 10g", line)
        self.assertIn("1 events", line)


if __name__ == "__main__":
    unittest.main()
