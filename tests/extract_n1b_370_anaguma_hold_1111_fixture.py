"""Freeze n1-b life-370's stop of 2026-11-11 05:42 (Orc cave 23F, build bot-0850e2334,
stall:floor-dwell:anaguma:hold).

Source: captures/20261111-054247-stall-floor-dwell-anaguma-hold copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1b-370-anaguma-hold-1111/.  Kept: the
capture's player boards (state.jsonl.gz, turns 5997122-5997227: the second pocket dug and held
against the stone trolls, race 297) and the decision rows of the same turns.  Only this tool
reads the capture; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-370-anaguma-hold-1111/"
            "20261111-054247-stall-floor-dwell-anaguma-hold")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-370-anaguma-hold-1111.json.xz"


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    boards = [row for row in lines(ROOT / "state.jsonl.gz") if row.get("type") == "player_turn"]
    turns = {board["turn"] for board in boards}
    decisions = [{field: row.get(field) for field in ("decision_sequence", "turn", "reason", "key", "position")}
                 for row in lines(ROOT / "bot-decisions.jsonl.gz")
                 if row.get("turn") in turns and "reason" in row]
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        {"source": ROOT.name + " (copied from the viewing server)", "boards": boards,
         "decisions": decisions}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
