"""Offline sequential module validation; never launch the game or full suite."""
import json
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "validation" / "suitefix2"
MODULES = ["test_ownership_s2b1_ladder", "test_town_approach_retired_recorded",
           "test_town_cure_supplier_recorded"]

revision = sys.argv[1]
root = ROOT if revision == "final" else OUT / revision
modules = sys.argv[2:] or MODULES
results_path = OUT / f"{revision}-results.json"
results = json.loads(results_path.read_text(encoding="utf8")) if results_path.exists() else []
for module in modules:
    if module == "test_policy_town":
        now = datetime.now(timezone(timedelta(hours=9)))
        if now.date().isoformat() == "2026-10-04" and (now.hour, now.minute) < (16, 40):
            raise SystemExit("test_policy_town is prohibited before 16:40 JST")
    print(f"START {revision} {module}", flush=True)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": os.pathsep.join(
        map(str, (root / "src", root, root / "tests", root / "scripts")))}
    start = time.monotonic()
    started_at = datetime.now(timezone(timedelta(hours=9))).isoformat()
    log = OUT / f"{revision}-{module}.log"
    with log.open("w", encoding="utf8") as stream:
        run = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest", "-v", module],
                             cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT)
    output = log.read_text(encoding="utf8")
    count = re.search(r"Ran (\d+) tests?", output)
    result = dict(revision=revision, module=module, exit_code=run.returncode,
                  tests=int(count[1]) if count else None,
                  started_at=started_at,
                  seconds=round(time.monotonic() - start, 2))
    for field in ("failures", "errors", "skipped"):
        found = re.search(rf"\b{field}=(\d+)", output)
        result[field] = int(found[1]) if found else 0
    results = [entry for entry in results if entry["module"] != module] + [result]
    results_path.write_text(json.dumps(results, indent=2), encoding="utf8")
    print(json.dumps(result), flush=True)
    if run.returncode:
        print(output[-4500:], flush=True)

if revision == "final" and any(entry["exit_code"] for entry in results):
    raise SystemExit(1)
