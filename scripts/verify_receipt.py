#!/usr/bin/env python3
"""Verify an unsigned receipt against current source and saved streams.

Receipts defend against drift and carelessness, not deliberate forgery.  The
source fingerprint excludes ``jsonlog/`` so appending the event which references
a receipt does not invalidate it; suspicious evidence should still be spot-run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import run_receipt
import verify_scope


def verify(path: Path, root: Path | None = None) -> tuple[bool, list[str], dict[str, object]]:
    root = root or run_receipt.ROOT
    payload = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    head = verify_scope.git(root, "rev-parse", "HEAD").strip()
    tree = run_receipt.source_fingerprint(root)
    if payload.get("head_sha") != head:
        problems.append(f"stale head_sha: receipt {payload.get('head_sha')} current {head}")
    if payload.get("source_fingerprint") != tree:
        problems.append("stale source_fingerprint")
    stream_text: dict[str, str] = {}
    for name, stream in payload.get("streams", {}).items():
        stream_path = root / stream["path"]
        if not stream_path.is_file():
            problems.append(f"missing {name} stream: {stream_path}")
        elif run_receipt.sha256(stream_path) != stream.get("sha256"):
            problems.append(f"{name} stream sha256 mismatch")
        else:
            stream_text[name] = stream_path.read_text(encoding="utf-8", errors="replace")
    derived: dict[str, object] = {}
    if {"stdout", "stderr"} <= stream_text.keys():
        derived = run_receipt.summarize(stream_text["stdout"], stream_text["stderr"])
        recorded = payload.get("result")
        if not isinstance(recorded, dict):
            problems.append("result mismatch: receipt result is not an object")
        else:
            for field, value in derived.items():
                if recorded.get(field) != value:
                    problems.append(f"result.{field} mismatch: receipt {recorded.get(field)!r} derived {value!r}")
            for field in recorded.keys() - derived.keys():
                problems.append(f"result.{field} mismatch: field is not derived from streams")
        inferred = run_receipt.inferred_exit_code(stream_text["stdout"], stream_text["stderr"])
        if inferred is not None and payload.get("exit_code") != inferred:
            problems.append(f"exit_code mismatch: receipt {payload.get('exit_code')!r} derived {inferred}")
    payload["derived_result"] = derived
    return not problems, problems, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)
    path = args.receipt if args.receipt.is_absolute() else run_receipt.ROOT / args.receipt
    ok, problems, payload = verify(path)
    print(f"tool: {payload.get('tool')}")
    print(f"target: {payload.get('target')}")
    print(f"argv: {json.dumps(payload.get('argv'))}")
    print(f"exit_code: {payload.get('exit_code')}")
    print(f"derived_result: {json.dumps(payload.get('derived_result', {}), sort_keys=True)}")
    print('note: failures: [] means no FAIL header scraped; exit_code is the primary signal')
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"VALID: {path}; receipt sha256: {run_receipt.sha256(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
