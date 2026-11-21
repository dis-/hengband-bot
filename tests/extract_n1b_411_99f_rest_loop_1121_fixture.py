"""Extract tests/fixtures/n1b-411-99f-rest-loop-1121/decisions.json.xz.

Source: n1-b life-411's stop of 2026-11-21 13:59:06 (loop-detected on Angband 99F, bot main
b9efeeca0), the incident capture n1b-411-20261121-135909-loop-detected's bot-decisions.jsonl.gz:
every decision row of the capture (the stop is the last), reduced to what the driver's cell
loop guard reads (cli._cell_loop_guard_applies, cli._is_looping): the key, the reason, the
floor, the position, the HP and MP, and the board's messages.

    python tests/extract_n1b_411_99f_melt_loop_1121_fixture.py <bot-decisions.jsonl.gz>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-99f-rest-loop-1121"


if __name__ == "__main__":
    with gzip.open(sys.argv[1], "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    reduced = [{
        "turn": row.get("turn"), "key": row.get("key"), "reason": row.get("reason"),
        "floor": row.get("floor"), "position": row.get("position"),
        "hp": row["player"].get("hp"), "mp": row["player"].get("mp"),
        "messages": row.get("messages") or [],
    } for row in rows]
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "decisions.json.xz").write_bytes(
        lzma.compress(json.dumps(reduced, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(len(reduced), sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
