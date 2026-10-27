"""Revert the three retained seams individually, then restore exact bytes."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, r"C:\hengband-backups\guard-tools")
from mutation_check import split_hunks

root = Path(__file__).resolve().parents[2]
env = dict(os.environ, PYTHONPATH="src;tests;scripts")
diff = subprocess.check_output(
    ["git", "diff", "-U3", "main", "--", "src/hengbot/*.py"],
    cwd=root, encoding="utf8")
cases = {
    "src/hengbot/cli.py": "tests.test_cli.PolicyFinalStopBannerTest",
    "src/hengbot/policy_constants.py":
        "tests.test_opening_route_pins.OpeningRoutePinsTest.test_unaffordable_route_is_an_operator_visible_final_stop",
    "src/hengbot/policy_fundraising.py":
        "tests.test_opening_route_pins.OpeningRoutePinsTest.test_restarted_income_run_returns_to_the_fixed_route",
}
seen = set()
for path, header, body in split_hunks(diff):
    if path not in cases:
        continue
    seen.add(path)
    test = cases[path]
    original = (root / path).read_bytes()
    with tempfile.TemporaryDirectory(prefix="opening-pins-") as scratch:
        patch = Path(scratch) / "revert.patch"
        patch.write_text(header + body, encoding="utf8", newline="")
        try:
            subprocess.run(["git", "apply", "-R", str(patch)], cwd=root, check=True)
            result = subprocess.run([sys.executable, "-m", "unittest", test],
                                    cwd=root, env=env, capture_output=True,
                                    text=True, encoding="utf8", errors="replace")
            print(path, body.splitlines()[0], "reverted exit", result.returncode, flush=True)
            print(result.stdout + result.stderr, flush=True)
            if result.returncode != 1 or "FAILED (" not in result.stderr:
                raise RuntimeError("pin did not fail as expected")
        finally:
            (root / path).write_bytes(original)
        subprocess.run([sys.executable, "-m", "unittest", test],
                       cwd=root, env=env, check=True)
        print("restored: PASS", path, flush=True)
assert seen == cases.keys(), seen
