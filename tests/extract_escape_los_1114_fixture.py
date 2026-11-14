"""Extract tests/fixtures/escape-los-1114.jsonl.gz.

Source: n1-c life-207 (zombie Magic-Eater, ガラスの城 60F) boards copied read-only from the viewing
server (jsonlog/snapshots) to C:/hengband-backups/pdca/escape-los-1114:

* ``1654``: b1654.jsonl.gz, 2026-11-14 16:53:58-16:54:03, the boards of turns 7836301 (the
  arrival on 60F by Recall) to 7836540 (snapshots-20261114-165937-92bfcf).
* ``1629``: b1629.jsonl.gz, 2026-11-14 16:29:40-16:29:42, turns 7730790 to 7730840
  (snapshots-20261114-164408-89bb4b).

    python tests/extract_escape_los_1114_fixture.py
"""
import gzip
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/escape-los-1114")
TARGET = Path(__file__).with_name("fixtures") / "escape-los-1114.jsonl.gz"
CASES = {"1654": ("b1654.jsonl.gz", 7836301, 7836540), "1629": ("b1629.jsonl.gz", 7730790, 7730840)}


def main() -> None:
    rows = []
    for role, (name, low, high) in CASES.items():
        with gzip.open(CAPTURE / name, "rt", encoding="utf-8") as stream:
            rows += [{"role": role, "board": board} for board in map(json.loads, stream)
                     if board.get("type") == "player_turn" and low <= board["turn"] <= high]
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
