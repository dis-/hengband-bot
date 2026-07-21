import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.wait_telemetry import WaitTelemetry


class WaitTelemetryTest(unittest.TestCase):
    def test_accumulates_and_reloads_categories(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "waits.json"
            monotonic_values = iter([10.0, 10.0, 12.0, 12.0])
            ledger = WaitTelemetry(
                path,
                wall_clock=lambda: 1000.0,
                monotonic=lambda: next(monotonic_values),
                flush_interval=1.0,
            )
            ledger.record("input:generic-prompt", 0.25)
            ledger.record("input:generic-prompt", 0.5)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["total_calls"], 2)
            self.assertAlmostEqual(payload["total_seconds"], 0.75)
            self.assertEqual(payload["categories"]["input:generic-prompt"]["calls"], 2)

            reloaded = WaitTelemetry(path)
            reloaded.record("action:town:wait-recall", 1.2, force_flush=True)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["total_calls"], 3)
            self.assertAlmostEqual(payload["total_seconds"], 1.95)


if __name__ == "__main__":
    unittest.main()
