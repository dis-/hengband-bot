#!/usr/bin/env python3
"""Run the authoritative serial non-CLI suite and record reproducible timings."""

from __future__ import annotations

import argparse
import json
import os
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
DEFAULT_SUMMARY_OUTPUT = ROOT / "jsonlog" / "test-timings-summary.json"


def standard_modules() -> list[str]:
    """Return the standing full-suite identity in its established order."""
    return [
        f"tests.{path.stem}"
        for path in sorted(TESTS.glob("test*.py"), key=lambda item: item.name)
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
        self._recorded: set[str] = set()

    def startTest(self, test: unittest.case.TestCase) -> None:
        super().startTest(test)
        self._started = time.perf_counter()

    def stopTest(self, test: unittest.case.TestCase) -> None:
        if self._started is not None:
            self._record(test, time.perf_counter() - self._started)
            self._started = None
        super().stopTest(test)

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # setUpClass/import failures arrive as _ErrorHolder objects without a
        # startTest/stopTest pair. Keep their identities in timing artifacts.
        if test.id() not in self._recorded:
            self._record(test, 0.0)
        super().addError(test, err)

    def _record(self, test: unittest.case.TestCase, seconds: float) -> None:
        test_id = test.id()
        if test_id not in self._recorded:
            self.timings.append({"id": test_id, "seconds": seconds})
            self._recorded.add(test_id)


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


def timing_summary(payload: dict[str, object], limit: int = 15) -> dict[str, object]:
    """Return the reproducible T3 test/class/module aggregates."""
    timings = list(payload["tests"])
    top_tests = sorted(timings, key=lambda row: (-float(row["seconds"]), str(row["id"])))
    classes = aggregate(timings, 3)
    modules = aggregate(timings, 2)
    total = float(payload["total_seconds"])
    return {
        "generated_at": payload["generated_at"],
        "head_sha": payload["head_sha"],
        "total_seconds": total,
        "test_count": len(timings),
        "top_tests": top_tests[:limit],
        "top_classes": classes[:10],
        "top_modules": modules[:10],
        "top_10_classes_share_percent": (
            100.0 * sum(float(row["seconds"]) for row in classes[:10]) / total
            if total else 0.0
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modules",
        nargs="+",
        help="module names (space- or comma-separated); default is every test_*.py except test_cli.py",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
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
    os.environ["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(TESTS)))

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
    summary_output = (
        args.summary_output if args.summary_output.is_absolute() else ROOT / args.summary_output
    )
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(timing_summary(payload), indent=2) + "\n", encoding="utf-8"
    )

    tests = sorted(result.timings, key=lambda row: (-float(row["seconds"]), str(row["id"])))
    print_group("Slowest tests", tests, args.top)
    print_group("Slowest classes", aggregate(result.timings, 3), args.top)
    print_group("Slowest modules", aggregate(result.timings, 2), args.top)
    print(
        f"\nTotal: {total_seconds:.3f}s; recorded {len(result.timings)} tests; "
        f"output: {output}; summary: {summary_output}"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
