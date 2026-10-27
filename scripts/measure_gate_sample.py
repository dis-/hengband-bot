"""Measure full/sample=5 module pairs without the purity PASS cache."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


def measure(module, output):
    rows = []
    for mode in ("full", "5"):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(str(ROOT / part) for part in ("src", "tests", "scripts")),
                   PYTHONIOENCODING="utf-8")
        env.pop("HENGBOT_TEST_SAMPLE", None)
        if mode != "full":
            env["HENGBOT_TEST_SAMPLE"] = mode
        with tempfile.TemporaryDirectory(prefix="gate-sample-measure-") as raw:
            env["HENGBOT_HOME_HISTORY_DIR"] = str(Path(raw) / "history")
            env["HENGBOT_RUNTIME_DIR"] = str(Path(raw) / "jsonlog")
            log = output / f"{module}.{mode}.log"
            start = time.perf_counter()
            with log.open("w", encoding="utf-8") as stream:
                result = subprocess.run(
                    [sys.executable, "-m", "unittest", "-v", module], cwd=ROOT,
                    env=env, stdout=stream, stderr=subprocess.STDOUT,
                )
            row = dict(module=module, mode=mode, seconds=time.perf_counter() - start,
                       returncode=result.returncode, log=log.name)
            rows.append(row)
            print(json.dumps(row), flush=True)
            (output / f"{module}.json").write_text(
                json.dumps(rows, indent=2) + "\n", encoding="utf-8"
            )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", nargs="+")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(measure, module, args.output) for module in args.modules]
        for future in as_completed(futures):
            results.extend(future.result())
    payload = dict(head=head, workers=args.workers, python=sys.version,
                   results=sorted(results, key=lambda row: (row["module"], row["mode"])))
    (args.output / "measurements.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return int(any(row["returncode"] for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
