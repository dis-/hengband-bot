#!/usr/bin/env python3
"""Run the standard non-CLI unittest suite in module shards.

Reviewers and fixers should use this runner by default::

    python scripts/test_parallel_runner.py

Use ``--workers N`` to override the default (physical cores, capped at six).
``scripts/test_timing_runner.py`` remains the serial identity fallback and is
authoritative if parallel and serial results ever disagree.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from failure_headers import iter_failure_headers
from test_timing_runner import ROOT, standard_modules, timing_summary
from purity_cache import PURITY_MODULES, input_sha256, load_pass, record_pass


DEFAULT_TIMINGS = ROOT / "jsonlog" / "test-timings.json"
DEFAULT_OUTPUT = ROOT / "jsonlog" / "test-parallel-timings.json"
DEFAULT_SUMMARY = ROOT / "jsonlog" / "test-parallel-timings-summary.json"
DEFAULT_STREAMS = ROOT / "jsonlog" / "test-parallel-streams"

# HENGBOT_HOME_HISTORY_DIR now isolates every worker's durable files. Keep
# these historically risky modules in the serial tail as defense-in-depth;
# removal can follow a separately measured optimization.
SERIAL_MODULES: frozenset[str] = frozenset({
    "tests.test_absorbing_states",
    "tests.test_cli",
    "tests.test_latch_onset_capture",
    "tests.test_policy_structure",
})


def physical_cores() -> int:
    try:
        import psutil  # type: ignore[import-not-found]
        count = psutil.cpu_count(logical=False)
    except ImportError:
        count = None
    return count or os.cpu_count() or 1


def module_seconds(path: Path) -> dict[str, float] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        totals: dict[str, float] = {}
        for row in payload["tests"]:
            module = ".".join(str(row["id"]).split(".")[:2])
            totals[module] = totals.get(module, 0.0) + float(row["seconds"])
        return totals
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def partition(modules: list[str], workers: int, weights: dict[str, float] | None) -> list[list[str]]:
    shards = [[] for _ in range(workers)]
    if not weights:
        for index, module in enumerate(sorted(modules)):
            shards[index % workers].append(module)
        return shards
    default_weight = float(median(weights.values()))
    effective_weights = {module: weights.get(module, default_weight) for module in modules}
    totals = [0.0] * workers
    for module in sorted(modules, key=lambda name: (-effective_weights[name], name)):
        index = min(range(workers), key=lambda item: (totals[item], item))
        shards[index].append(module)
        totals[index] += effective_weights[module]
    return shards


def resolved(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def outcome_ids(stderr: str, kind: str) -> list[str]:
    return list(dict.fromkeys(
        header.identity
        for header in iter_failure_headers(stderr, test_names_only=False)
        if header.kind == kind
    ))


def run_shard(index: int, modules: list[str], temp_root: Path, streams: Path) -> dict[str, object]:
    name = f"worker-{index + 1}"
    timing_path = temp_root / f"{name}.json"
    summary_path = temp_root / f"{name}-summary.json"
    stdout_path, stderr_path = streams / f"{name}.stdout.log", streams / f"{name}.stderr.log"
    worker_temp = temp_root / name
    worker_temp.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT / "tests")))
    env["TEMP"] = env["TMP"] = str(worker_temp)
    history_dir = worker_temp / "home-history"
    history_dir.mkdir()
    env["HENGBOT_HOME_HISTORY_DIR"] = str(history_dir)
    command = [sys.executable, str(ROOT / "scripts" / "test_timing_runner.py"),
               "--modules", *modules, "--output", str(timing_path),
               "--summary-output", str(summary_path), "--top", "0", "--no-receipt"]
    started = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        run = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
    payload = json.loads(timing_path.read_text(encoding="utf-8"))
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    return {"name": name, "modules": modules, "returncode": run.returncode,
            "home_history_dir": str(history_dir),
            "wall_seconds": time.perf_counter() - started, "payload": payload,
            "failures": outcome_ids(stderr_text, "FAIL"),
            "errors": outcome_ids(stderr_text, "ERROR"),
            "stdout": str(stdout_path), "stderr": str(stderr_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=min(physical_cores(), 6))
    parser.add_argument("--timings", type=Path, default=DEFAULT_TIMINGS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--streams-dir", type=Path, default=DEFAULT_STREAMS)
    parser.add_argument("--modules", nargs="+", help="run only these modules")
    parser.add_argument("--purity", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--purity-cache", type=Path, default=ROOT / "jsonlog" / "purity-cache.json")
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")

    modules = standard_modules() if not args.modules else [
        name if name.startswith("tests.") else f"tests.{Path(name).stem}"
        for value in args.modules for name in value.split(",") if name
    ]
    purity_cache = resolved(args.purity_cache)
    purity_hash, purity_inputs = input_sha256(ROOT)
    cached = load_pass(purity_cache, purity_hash) if args.purity == "auto" else None
    purity_selected = [module for module in modules if module in PURITY_MODULES]
    purity_skipped = bool(purity_selected and (args.purity == "never" or cached))
    if purity_skipped:
        modules = [module for module in modules if module not in PURITY_MODULES]
        if cached:
            purity_line = (f"purity: skipped (inputs sha256={purity_hash} matched cached PASS "
                           f"from {cached.get('head_sha')} at {cached.get('time')})")
        else:
            purity_line = f"purity: skipped (--purity never; inputs sha256={purity_hash})"
    else:
        purity_line = f"purity: ran (inputs sha256={purity_hash})"
    parallel_modules = [module for module in modules if module not in SERIAL_MODULES]
    worker_count = min(args.workers, max(1, len(parallel_modules)))
    weights = module_seconds(resolved(args.timings))
    shards = partition(parallel_modules, worker_count, weights)
    serial_selected = sorted(SERIAL_MODULES.intersection(modules))
    if serial_selected:
        shards.append(serial_selected)

    streams = resolved(args.streams_dir)
    streams.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="hengbot-parallel-") as directory:
        temp_root = Path(directory)
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {pool.submit(run_shard, i, shard, temp_root, streams): i
                       for i, shard in enumerate(shards[:worker_count])}
            for future in as_completed(futures):
                results.append(future.result())
        if serial_selected:
            results.append(run_shard(len(shards) - 1, shards[-1], temp_root, streams))

    results.sort(key=lambda row: str(row["name"]))
    tests = [timing for row in results for timing in row["payload"]["tests"]]
    payload = {"generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
               "head_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "total_seconds": time.perf_counter() - started, "tests": tests,
               "failures": [test_id for row in results for test_id in row["failures"]],
               "errors": [test_id for row in results for test_id in row["errors"]],
               "shards": [{key: row[key] for key in ("name", "modules", "returncode", "wall_seconds", "home_history_dir", "failures", "errors", "stdout", "stderr")}
                          for row in results], "serial_modules": serial_selected,
               "purity": purity_line}
    output, summary_output = resolved(args.output), resolved(args.summary_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(timing_summary(payload), indent=2) + "\n", encoding="utf-8")

    for row in results:
        print(f"{row['name']}: {len(row['payload']['tests'])} tests, "
              f"{row['wall_seconds']:.3f}s, exit {row['returncode']}; "
              f"home history: {row['home_history_dir']}")
        if row["returncode"]:
            stderr = Path(str(row["stderr"])).read_text(encoding="utf-8", errors="replace")
            print(stderr.rstrip())
    print(f"Failures: {payload['failures'] or 'none'}")
    print(f"Errors: {payload['errors'] or 'none'}")
    print(purity_line)
    print(f"Total: {len(tests)} tests, {payload['total_seconds']:.3f}s; output: {output}")
    failed = any(int(row["returncode"]) != 0 for row in results)
    ran_all_purity = set(PURITY_MODULES).issubset({m for row in results for m in row["modules"]})
    if not failed and ran_all_purity:
        record_pass(purity_cache, purity_hash,
                    str(payload["head_sha"]), purity_inputs)
    return int(failed)


if __name__ == "__main__":
    import run_receipt
    raise SystemExit(run_receipt.run_native(
        "test_parallel_runner", "full", sys.argv, main,
    ))
