"""Revert just the movement matcher, run the live31 pins, restore bytes."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "src/hengbot/policy_home.py"
original = path.read_bytes()
base = subprocess.check_output(["git", "show", "dcb3fed7:src/hengbot/policy_home.py"], cwd=ROOT)
start = b"    def _calibration_restore_item_matches("
end = b"    @staticmethod"
assert original.count(start) == base.count(start) == 1
old_method = base[base.index(start):base.index(end, base.index(start))]
try:
    reverted = original[:original.index(start)] + old_method + original[original.index(end, original.index(start)):]
    path.write_bytes(reverted)
    result = subprocess.run([sys.executable, "-m", "unittest", "tests.test_calibration_live31"],
        cwd=ROOT, env=dict(os.environ, PYTHONUTF8="1", PYTHONPATH="src;tests;scripts"),
        capture_output=True, text=True, encoding="utf8")
    output = result.stdout + result.stderr
    (ROOT / "reports/live31-revert.txt").write_text(output, encoding="utf8")
    print(output)
    assert result.returncode == 1
    assert "FAILED (failures=3)" in output
    assert "'5' != '5po3\\r\\x1b'" in output
finally:
    path.write_bytes(original)
assert path.read_bytes() == original
print("Single matcher revert rejected; source restored byte-for-byte.")
