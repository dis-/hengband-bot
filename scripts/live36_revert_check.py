"""Single revert of live36 runtime hunks, with unconditional restoration."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "src/hengbot" / name for name in
         ("policy_home.py", "policy_supply.py", "policy_town.py")]


def main():
    saved = {path: path.read_bytes() for path in FILES}
    env = dict(os.environ, PYTHONPATH="src;tests;scripts")
    try:
        for path in FILES:
            baseline = subprocess.check_output(
                ["git", "show", "d1bf7c28:" + path.relative_to(ROOT).as_posix()], cwd=ROOT)
            path.write_bytes(baseline)
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_live36_weight"],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf8")
        (ROOT / "reports/live36-revert.txt").write_text(
            result.stdout + result.stderr, encoding="utf8")
        print(result.stdout + result.stderr)
        if result.returncode == 0:
            raise RuntimeError("reverted runtime unexpectedly passed the pins")
    finally:
        for path, data in saved.items():
            path.write_bytes(data)
    print("Runtime restored byte-for-byte.")


if __name__ == "__main__":
    main()
