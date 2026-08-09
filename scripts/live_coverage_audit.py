#!/usr/bin/env python3
"""Report live decision reasons and composed keys absent from the test tree."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import glob
import json
from pathlib import Path
import sys
from typing import Iterable


DEFAULT_LOG = "jsonlog/bot-decisions.jsonl"
DEFAULT_EVIDENCE_GLOB = "jsonlog/evidence-*.jsonl"


def default_log_paths() -> list[Path]:
    paths = [Path(DEFAULT_LOG)]
    paths.extend(Path(name) for name in sorted(glob.glob(DEFAULT_EVIDENCE_GLOB)))
    return [path for path in paths if path.is_file()]


def read_live_values(paths: Iterable[Path]) -> tuple[Counter[str], Counter[str]]:
    reasons: Counter[str] = Counter()
    keys: Counter[str] = Counter()
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
                reason = record.get("reason")
                key = record.get("key")
                if isinstance(reason, str):
                    reasons[reason] += 1
                if isinstance(key, str) and len(key) > 1:
                    keys[key] += 1
    return reasons, keys


def read_test_references(paths: Iterable[Path]) -> tuple[str, set[str]]:
    source_parts: list[str] = []
    literals: set[str] = set()
    for path in paths:
        source = path.read_text(encoding="utf-8")
        source_parts.append(source)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            raise ValueError(f"{path}:{exc.lineno}: cannot parse test file: {exc.msg}") from exc
        literals.update(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    return "\n".join(source_parts), literals


def find_orphans(
    reasons: Counter[str], keys: Counter[str], test_source: str, test_literals: set[str]
) -> list[tuple[str, str, int]]:
    orphaned: list[tuple[str, str, int]] = []
    for reason, count in reasons.items():
        if reason not in test_source and reason not in test_literals:
            orphaned.append(("reason", reason, count))
    for key, count in keys.items():
        if key not in test_literals:
            orphaned.append(("key-shape", repr(key), count))
    return sorted(orphaned, key=lambda item: (item[0], item[1]))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="*", type=Path, help="decision-log JSONL paths")
    parser.add_argument(
        "--tests",
        nargs="+",
        type=Path,
        default=None,
        help="test Python files (default: tests/*.py)",
    )
    parser.add_argument(
        "--max-orphans",
        type=int,
        default=0,
        help="maximum permitted number of distinct orphan entries (default: 0)",
    )
    args = parser.parse_args(argv)
    if args.max_orphans < 0:
        parser.error("--max-orphans must be non-negative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logs = args.logs or default_log_paths()
    tests = args.tests or sorted(Path("tests").glob("*.py"))
    if not logs:
        print("error: no decision logs found", file=sys.stderr)
        return 2
    if not tests:
        print("error: no test files found", file=sys.stderr)
        return 2
    try:
        reasons, keys = read_live_values(logs)
        test_source, test_literals = read_test_references(tests)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    orphaned = find_orphans(reasons, keys, test_source, test_literals)
    for kind, value, count in orphaned:
        print(f"ORPHANED {kind} {value} count={count}")
    print(
        f"audited reasons={len(reasons)} composed-key-shapes={len(keys)} "
        f"orphaned={len(orphaned)} max={args.max_orphans}"
    )
    return 1 if len(orphaned) > args.max_orphans else 0


if __name__ == "__main__":
    raise SystemExit(main())
