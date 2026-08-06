"""Run the opt-in, long absorbing-state catalogue with diagnostic reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from absorbing_state_catalog import SEEDED_STATES  # noqa: E402
from absorbing_state_harness import drive  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("states", nargs="*", help="catalogue names (default: all six)")
    args = parser.parse_args()
    selected = [s for s in SEEDED_STATES if not args.states or s.name in args.states]
    unknown = set(args.states) - {s.name for s in selected}
    if unknown:
        parser.error(f"unknown states: {', '.join(sorted(unknown))}")
    failed = False
    for state in selected:
        result = drive(state)
        print(result.report(), flush=True)
        failed |= not result.passed
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
