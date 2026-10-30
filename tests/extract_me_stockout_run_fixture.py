"""Freeze the 2026-10-31 n1-c life-045 staff-stockout mining run (D35).

Source: the viewing zombie Magic-Eater n1-c life-045 (Lv8, Outpost, build
475bc157b): its snapshot ring jsonlog/snapshots/snapshots-current.jsonl.gz
(copied to C:/hengband-backups/pdca/captures/me-stockout-1031/) and its
decision log beside it.  At turn 209432 the staff sequence chose
``me-staff:fundraise:staff-stockout:1648`` with 1647 gold (the Magic shop
page at 209421 sold the Identify staff, not Treasure Location); the run
detected 146 veins on Yeek cave 1F, dug one, picked up 37 gold (1660) and the
next decision (212034) was fundraise:seek-upstairs with 145 veins known.

Frozen: the Magic shop page (209421), the town board (209432), the dungeon
board right after the nugget (212034), the last skill-proficiency and Home
knowledge rows before each, and the recorded decision rows of those turns.
Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import zlib
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/me-stockout-1031")
RING = CAPTURE / "life-045-snapshots-current.jsonl.gz"
DECISIONS = CAPTURE / "life-045-bot-decisions.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "me-stockout-run-20261031.json.gz"
STORE_TURN, TOWN_TURN, DUNGEON_TURN = 209421, 209432, 212034
DECISION_FIELDS = ("turn", "reason", "key", "player", "floor", "position", "mining", "fundraising")


def ring_rows(data: bytes) -> list[dict]:
    rows, buf = [], data[data.index(b"\x1f\x8b\x08"):]
    while buf:
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = stream.decompress(buf)
        rows.extend(json.loads(line) for line in out.decode("utf-8").splitlines()
                    if line.strip())
        if not stream.eof:
            break  # the ring was copied while its last member was written
        buf = stream.unused_data
    return rows


def main():
    rows = ring_rows(RING.read_bytes())

    def board(kind, turn):
        index = next(i for i, row in enumerate(rows) if row["type"] == kind and row["turn"] == turn)
        return index, rows[index]

    def knowledge(category, before):
        return next(row for row in reversed(rows[:before]) if row["type"] == "knowledge"
                    and row["knowledge"]["category"] == category)

    store_index, store = board("store", STORE_TURN)
    town_index, town = board("player_turn", TOWN_TURN)
    dungeon_index, dungeon = board("player_turn", DUNGEON_TURN)
    assert store["store"]["store_type"] == 5 and town_index == store_index + 1
    assert (town["player"]["gold"], dungeon["player"]["gold"]) == (1647, 1660)
    decisions = {}
    with DECISIONS.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") in (STORE_TURN, TOWN_TURN, DUNGEON_TURN):
                decisions.setdefault(str(row["turn"]), {k: row.get(k) for k in DECISION_FIELDS})
    case = dict(
        source="n1-c life-045 (build 475bc157b) snapshot ring and decision log",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (RING, DECISIONS)},
        store=store,
        town=town,
        dungeon=dungeon,
        town_knowledge=[knowledge("skill_exp", store_index), knowledge("home", store_index)],
        dungeon_knowledge=[knowledge("skill_exp", dungeon_index), knowledge("home", dungeon_index)],
        decisions=decisions,
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
