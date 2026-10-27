"""Run unchanged guard scripts on an isolated Linux checkout of the same git objects.

The caller supplies game-data and PYTHONPATH compatibility symlinks, the
Windows timing snapshot, and an independent memory-limited validation slot.
No product or test source is rewritten for Linux.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path.cwd()
OUT = ROOT / "validation/quest-sweep-84-20261027"
BASE = "4db110bd5"


def main():
    results = {}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        str(ROOT / part) for part in ("", "src", "tests", "scripts")
    ))
    commands = {
        "mutation-linux": [sys.executable, ".guard-tools/mutation_check.py", ".", BASE,
                           "--tests", "tests.test_quest_sweep_hold_recorded", "--record", "--full"],
        "fast-tier-linux": [sys.executable, ".guard-tools/fast_tier.py", ".", BASE,
                            "--shards", "4", "--timings", str(ROOT / ".validation-timings")],
        "scope-linux": [sys.executable, str(OUT / "run_scope.py")],
    }
    for name, command in commands.items():
        print("starting", name, flush=True)
        started = time.monotonic()
        with (OUT / (name + ".log")).open("w", encoding="utf-8") as stream:
            try:
                process = subprocess.run(command, env=env, stdout=stream,
                                         stderr=subprocess.STDOUT, timeout=1200)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        results[name] = {"returncode": code, "seconds": round(time.monotonic() - started, 2)}
        (OUT / "linux-stages.json").write_text(json.dumps({
            "head": head, "base": BASE, "python": sys.version, "results": results,
        }, indent=2) + "\n", encoding="utf-8")
        print(name, results[name], flush=True)
        if subprocess.check_output(["git", "status", "--porcelain", "--", "src", "tests"]).strip():
            raise SystemExit("validation changed product or test sources")
    return int(any(value["returncode"] != 0 for value in results.values()))


if __name__ == "__main__":
    sys.exit(main())
