"""Freeze the Q2 boards of n1-b life-316 (q2-live-1105).

Source: C:/hengband-backups/pdca/captures/n1b-316-q2-1105/ (q2-decisions.jsonl.gz and, inside
cap.tgz, jsonlog/snapshots/snapshots-20261105-152230-a7e465.jsonl.gz, unpacked to the directory
given as the first argument).  The rotated log holds the first process's boards twice and some
boards the bot never decided on (the second half of a targeted shot), so each decision row takes
the board of its own turn: "first" are the rows before loop-detected, "restart" the rows after
the restart's skill read.  Only this extraction tool reads the capture.
"""

from __future__ import annotations

import gzip
import json
import sys
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-316-q2-1105")
SNAPSHOTS = "jsonlog/snapshots/snapshots-20261105-152230-a7e465.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "q2-live-20261105.json.gz"
ROSTER = (86, 153, 252, 213, 270, 175, 42, 120, 918, 885, 944, 202, 1044)
RESTART_FIRST_SEQUENCE = 1


def members(data: bytes):
    """A rotated log is several gzip members."""
    while data:
        stream = zlib.decompressobj(31)
        yield stream.decompress(data)
        data = stream.unused_data


def quest_boards(unpacked: Path) -> list[dict]:
    text = b"".join(members((unpacked / SNAPSHOTS).read_bytes()))
    boards = (json.loads(line.decode("utf-8", "surrogateescape"))
              for line in text.split(b"\n") if line.strip())
    return [raw for raw in boards
            if raw.get("type") == "player_turn" and raw["floor"]["quest_id"] == 2]


def decision_rows() -> list[dict]:
    with gzip.open(CAPTURE / "q2-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    return [row for row in rows if (row.get("floor") or {}).get("quest_id") == 2]


def take(boards: list[dict], rows: list[dict]) -> list[dict]:
    by_turn: dict[int, dict] = {}
    for raw in boards:
        by_turn.setdefault(raw["turn"], raw)
    return [{"key": row["key"], "reason": row["reason"], "board": by_turn[row["turn"]]}
            for row in rows]


def main():
    boards = quest_boards(Path(sys.argv[1]))
    rows = decision_rows()
    loop = next(i for i, row in enumerate(rows) if row["reason"] == "loop-detected")
    restart = next(i for i, row in enumerate(rows)
                   if row["decision_sequence"] == RESTART_FIRST_SEQUENCE)
    second_process = boards[next(i for i, raw in enumerate(boards)
                                 if raw["turn"] == rows[restart]["turn"]):]
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ids = set(ROSTER) | {row["race_id"] for raw in boards for row in raw["visible_monsters"]}
    fixture = {
        "source": str(CAPTURE),
        "first": take(boards[:loop + 1], rows[:loop]),
        "restart": take(second_process, rows[restart:]),
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n", errors="surrogateescape") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(fixture["first"]), len(fixture["restart"]))


if __name__ == "__main__":
    main()
