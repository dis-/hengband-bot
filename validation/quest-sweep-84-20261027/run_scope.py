"""Run every derived module, with file-based discovery and visible logs."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def main():
    scope = json.loads((OUT / "scope-derived.json").read_text(encoding="utf-8"))
    modules = scope["modules"]
    priority = ("tests.test_policy_quest", "tests.test_policy_structure", "tests.test_absorbing_states")
    ordered = [module for module in priority if module in modules]
    ordered.extend(module for module in modules if module not in ordered)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        str(ROOT / part) for part in ("", "src", "tests", "scripts")
    ))

    def run(module):
        started = time.monotonic()
        path = OUT / (module + ".log")
        with path.open("w", encoding="utf-8") as stream:
            try:
                process = subprocess.run(
                    [sys.executable, str(OUT / "run_module.py"), module],
                    cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                    timeout=900,
                )
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        log = path.read_text(encoding="utf-8", errors="replace")
        count = re.search(r"Ran (\d+) tests?", log)
        skipped = re.search(r"skipped=(\d+)", log)
        result = {
            "returncode": code, "seconds": round(time.monotonic() - started, 2),
            "tests": int(count.group(1)) if count else None,
            "skipped": int(skipped.group(1)) if skipped else 0,
        }
        print(module, result, flush=True)
        return module, result

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(pool.map(run, ordered))
    summary = {
        "head": head, "base": "4db110bd5", "derived": scope,
        "excluded": ["tests.test_cli.DecisionTimingTest"], "modules": results,
    }
    (OUT / "scope-results.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return int(any(result["returncode"] != 0 for result in results.values()))


if __name__ == "__main__":
    sys.exit(main())
