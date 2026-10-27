"""Compare observed derived failures against main and the incoming branch."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
scratch = Path(tempfile.mkdtemp(prefix="opening-structure-baseline-"))
subprocess.run(["git", "worktree", "add", "--detach", str(scratch), "main"], cwd=ROOT, check=True)
shutil.copytree(Path(r"C:\hengband\lib\edit"), scratch / "lib" / "edit")
(OUT / "baseline-worktree.txt").write_text(str(scratch) + "\n", encoding="utf-8")
env = dict(os.environ, PYTHONPATH="src;tests;scripts", PYTHONIOENCODING="utf-8")
results = {}
cases = {
    "stockout": "tests.test_keep_running_a0.DepartureTest.test_existing_supply_stockout_fallback_and_exhausted_hard_stop",
    "cli-follow": "tests.test_cli.CliTest.test_run_follow_records_none_key_and_waits_for_next_snapshot",
}
for label, ref in (("main", "main"), ("incoming", "22b2b2806")):
    subprocess.run(["git", "switch", "--detach", ref], cwd=scratch, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=scratch, text=True).strip()
    for case, test in cases.items():
        started = time.monotonic()
        with (OUT / (label + "-" + case + ".log")).open("w", encoding="utf-8") as log:
            try:
                proc = subprocess.run([sys.executable, "-m", "unittest", test], cwd=scratch, env=env,
                                      stdout=log, stderr=subprocess.STDOUT, timeout=120)
                result = {"head": head, "exit_code": proc.returncode, "test": test}
            except subprocess.TimeoutExpired:
                result = {"head": head, "exit_code": None, "timeout": 120, "test": test}
        result["seconds"] = round(time.monotonic() - started, 3)
        results[label + "-" + case] = result
        (OUT / "baseline-results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(label, case, result, flush=True)
