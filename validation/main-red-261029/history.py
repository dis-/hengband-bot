"""Reproduce the incident tests on every first-parent snapshot, read-only."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
HISTORY = ROOT.parent / "main-red-history-261029"
NAMES = json.loads((OUT / "incident-tests.json").read_text(encoding="utf-8"))
RUNNER = '''import json, os, sys, time, unittest
sys.path.insert(0, os.getcwd())
names = json.loads(sys.argv[1])
result = {}
for name in names:
    start = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromName(name)
    outcome = unittest.TestResult()
    suite.run(outcome)
    result[name] = dict(ran=outcome.testsRun, seconds=round(time.monotonic()-start, 2),
                        failures=[s for _,s in outcome.failures], errors=[s for _,s in outcome.errors])
    print(name + ': ' + ('PASS' if outcome.wasSuccessful() else 'FAIL'), flush=True)
open(sys.argv[2], 'w', encoding='utf-8').write(json.dumps(result, ensure_ascii=False, indent=2))
'''


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    commits = [git("rev-parse", "78deea2ac")]
    commits += git("rev-list", "--first-parent", "--reverse", "78deea2ac..eebc99f0e").splitlines()
    if not HISTORY.exists():
        subprocess.run(["git", "worktree", "add", "--detach", str(HISTORY), commits[0]], cwd=ROOT, check=True)
    env = dict(os.environ, PYTHONPATH="src;tests;scripts", PYTHONIOENCODING="utf-8")
    runner = OUT / "history_runner.py"
    runner.write_text(RUNNER, encoding="utf-8")
    for commit in commits:
        output = OUT / (commit[:9] + ".json")
        if output.exists() and '--force' not in sys.argv:
            continue
        subprocess.run(["git", "checkout", "--detach", commit], cwd=HISTORY, check=True, capture_output=True)
        print(commit[:9], flush=True)
        with (OUT / (commit[:9] + ".log")).open("w", encoding="utf-8") as log:
            proc = subprocess.run([sys.executable, str(runner), json.dumps(NAMES), str(output)],
                                  cwd=HISTORY, env=env, stdout=log, stderr=subprocess.STDOUT)
        if proc.returncode:
            raise SystemExit(proc.returncode)
        rows = json.loads(output.read_text(encoding="utf-8"))
        print('  ' + ', '.join(name.rsplit('.', 1)[-1] for name, row in rows.items()
                              if row['failures'] or row['errors']), flush=True)


if __name__ == "__main__":
    main()
