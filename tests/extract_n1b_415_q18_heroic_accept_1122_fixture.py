"""Freeze n1-b life-415's Quest 18 acceptance boards of 2026-11-22 14:28:25
(tests/test_n1b_415_q18_heroic_accept_1122_recorded.py).

Source: the snapshot ring of incident capture 20261122-143605-loop-detected (n1-b life-415,
Magic-Eater Lv34, build bot-53f7a340e), copied read-only from the viewing server to
C:/hengband-backups/pdca/n1b-415-loop/.  The live generation (snapshots-current.jsonl.gz) is
its last 16 MiB, so it is read from the first whole gzip member on.

Kept: the board of the acceptance (turn 1,949,448 at (27,99), decision 5197
``fixedquest:request``: the status bar's ``heroism``, maximum HP 706) and the first board after
the heroism ran out (turn 1,949,474, maximum HP 696, no ``heroism``).

    python tests/extract_n1b_415_q18_heroic_accept_1122_fixture.py
"""
from __future__ import annotations

import gzip
import json
import zlib
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/n1b-415-loop/incident-captures/"
              "20261122-143605-loop-detected/snapshots/snapshots-current.jsonl.gz")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-415-q18-heroic-accept-1122.json.gz"
ACCEPT = (1949448, 27, 99)
EXPIRED_TURN = 1949474
GZIP_MAGIC = b"\x1f\x8b\x08"


def boards():
    data = SOURCE.read_bytes()
    position = data.find(GZIP_MAGIC)
    while 0 <= position < len(data):
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            text = stream.decompress(data[position:])
        except zlib.error:
            position = data.find(GZIP_MAGIC, position + 1)
            continue
        for line in text.decode("utf-8").splitlines():
            if line.strip():
                yield json.loads(line)
        if not stream.eof:
            return
        position = len(data) - len(stream.unused_data)


def main():
    accept = expired = None
    for board in boards():
        player = board.get("player", {})
        if (board.get("turn"), player.get("y"), player.get("x")) == ACCEPT:
            accept = board
        elif board.get("turn") == EXPIRED_TURN:
            expired = board
    fixture = {"source": "n1-b life-415 snapshot ring, turns 1949448 and 1949474 "
                         "(copied from the viewing server)",
               "accept": accept, "expired": expired}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, accept is not None, expired is not None, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
