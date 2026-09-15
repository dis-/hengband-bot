"""Extract the immutable board window for the 2026-09-15 Home loop."""

from __future__ import annotations

import gzip
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jsonlog" / "bot-state-fixed.jsonl"
TARGET = ROOT / "tests" / "fixtures" / "home-equip-enter-leave-loop-20260915.jsonl.gz"
FIRST_LINE = 3693
LAST_LINE = 3717


def main() -> None:
    selected = SOURCE.read_bytes().splitlines(keepends=True)[
        FIRST_LINE - 1:LAST_LINE
    ]
    if len(selected) != LAST_LINE - FIRST_LINE + 1:
        raise SystemExit("recorded window is incomplete")
    with gzip.open(TARGET, "wb") as stream:
        stream.writelines(selected)


if __name__ == "__main__":
    main()
