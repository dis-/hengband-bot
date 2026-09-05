#!/usr/bin/env python3
"""Run the standard non-CLI unittest suite and record per-test timings."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import unittest
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
DEFAULT_OUTPUT = ROOT / "jsonlog" / "test-timings.json"


def standard_modules() -> list[str]:
    """Return the standing full-suite identity in its established order."""
    return [
        f"tests.{path.stem}"
        for path in sorted(TESTS.glob("test_*.py"), key=lambda item: item.name)
        if path.name != "test_cli.py"
    ]


def normalize_modules(values: list[str] | None) -> list[str]:
    if not values:
        return standard_modules()
    modules: list[str] = []
    for value in values:
        for item in value.split(","):
            name = item.strip()
            if not name:
                continue
            if name.endswith(".py"):
                name = Path(name).stem
            if not name.startswith("tests."):
                name = f"tests.{name}"
            modules.append(name)
    return modules


class TimingResult(unittest.TextTestResult):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.timings: list[dict[str, object]] = []
        self._started: float | None = None

    def startTest(self, test: unittest.case.TestCase) -> None:
        super().startTest(test)
        self._started = time.perf_counter()

    def stopTest(self, test: unittest.case.TestCase) -> None:
        if self._started is not None:
            self.timings.append(
                {"id": test.id(), "seconds": time.perf_counter() - self._started}
            )
            self._started = None
        super().stopTest(test)


def aggregate(timings: list[dict[str, object]], parts: int) -> list[dict[str, object]]:
    totals: defaultdict[str, float] = defaultdict(float)
    for timing in timings:
        test_id = str(timing["id"])
        key = ".".join(test_id.split(".")[:parts])
        totals[key] += float(timing["seconds"])
    return [
        {"id": key, "seconds": seconds}
        for key, seconds in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]


def print_group(title: str, rows: list[dict[str, object]], limit: int) -> None:
    print(f"\n{title}")
    for row in rows[:limit]:
        print(f"{float(row['seconds']):10.3f}s  {row['id']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modules",
        nargs="+",
        help="module names (space- or comma-separated); default is every test_*.py except test_cli.py",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.top < 0:
        raise SystemExit("--top must be non-negative")

    # Match the standing PYTHONPATH=src;tests convention even when invoked directly.
    for path in reversed((ROOT, ROOT / "src", TESTS)):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

    modules = normalize_modules(args.modules)
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    started = time.perf_counter()
    result = unittest.TextTestRunner(resultclass=TimingResult, verbosity=1).run(suite)
    total_seconds = time.perf_counter() - started

    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "head_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "total_seconds": total_seconds,
        "tests": result.timings,
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    tests = sorted(result.timings, key=lambda row: (-float(row["seconds"]), str(row["id"])))
    print_group("Slowest tests", tests, args.top)
    print_group("Slowest classes", aggregate(result.timings, 3), args.top)
    print_group("Slowest modules", aggregate(result.timings, 2), args.top)
    print(f"\nTotal: {total_seconds:.3f}s; recorded {len(result.timings)} tests; output: {output}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
