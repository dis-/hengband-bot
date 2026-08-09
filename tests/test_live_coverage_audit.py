import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


AUDITOR = Path(__file__).resolve().parents[1] / "scripts" / "live_coverage_audit.py"


class LiveCoverageAuditTest(unittest.TestCase):
    def test_synthetic_log_reports_only_unreferenced_live_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "decisions.jsonl"
            test_file = root / "test_synthetic.py"
            records = [
                {"reason": "covered:reason", "key": "ab\r"},
                {"reason": "orphan:reason", "key": "xy\x1b"},
                {"reason": "orphan:reason", "key": "z"},
            ]
            log.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            test_file.write_text(
                "COVERED_REASON = 'covered:reason'\nCOVERED_KEY = 'ab\\r'\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(AUDITOR), str(log), "--tests", str(test_file)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1, result)
            self.assertIn("ORPHANED reason orphan:reason count=2", result.stdout)
            self.assertIn("ORPHANED key-shape 'xy\\x1b' count=1", result.stdout)
            self.assertNotIn("covered:reason", result.stdout)
            self.assertNotIn("ab\\r", result.stdout)
            self.assertIn("orphaned=2 max=0", result.stdout)

            allowed = subprocess.run(
                [
                    sys.executable,
                    str(AUDITOR),
                    str(log),
                    "--tests",
                    str(test_file),
                    "--max-orphans",
                    "2",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(allowed.returncode, 0, allowed)


if __name__ == "__main__":
    unittest.main()
