#!/usr/bin/env python3
"""Verify an execution receipt against the current checkout and saved streams."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import run_receipt
import verify_scope


def verify(path: Path, root: Path = run_receipt.ROOT) -> tuple[bool, list[str], dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    head = verify_scope.git(root, "rev-parse", "HEAD").strip()
    tree = verify_scope.tree_fingerprint(root)
    if payload.get("head_sha") != head:
        problems.append(f"stale head_sha: receipt {payload.get('head_sha')} current {head}")
    if payload.get("tree_fingerprint") != tree:
        problems.append("stale tree_fingerprint")
    for name, stream in payload.get("streams", {}).items():
        stream_path = root / stream["path"]
        if not stream_path.is_file():
            problems.append(f"missing {name} stream: {stream_path}")
        elif run_receipt.sha256(stream_path) != stream.get("sha256"):
            problems.append(f"{name} stream sha256 mismatch")
    return not problems, problems, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)
    path = args.receipt if args.receipt.is_absolute() else run_receipt.ROOT / args.receipt
    ok, problems, payload = verify(path)
    print(json.dumps(payload.get("result", {}), sort_keys=True))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"VALID: {path}; receipt sha256: {run_receipt.sha256(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
