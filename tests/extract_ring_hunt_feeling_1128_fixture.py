"""Extract tests/fixtures/ring-hunt-feeling-1128.jsonl.xz (tests/test_ring_hunt_feeling_1128_recorded.py).

Source: n1-b life-419 (Magic-Eater CL50, HP 1128, permanent speed +17; build of 2026-11-28) on
hengband.net, the viewing server's snapshot log
``jsonlog/snapshots/snapshots-20261128-041517-69ccdc.jsonl.gz`` copied read-only to
C:/hengband-backups/pdca/captures/ring-hunt-feeling-1128/ and cut there to the Angband 80F floor
entered by Word of Recall at turn 14150431 (``n1b-419-80F-14150431.jsonl``, its 782 player-turn
boards).  The feeling became known (10) at 14151315; the decision log recorded ``('3',
'explore')`` there and ``explore`` on every board after it until 14153080.

Kept: the player-turn boards from 14151150 (a ``seek-loot`` board, feeling 0) to 14151330,
xz-compressed.

    python tests/extract_ring_hunt_feeling_1128_fixture.py
"""
import json
import lzma
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/captures/ring-hunt-feeling-1128/n1b-419-80F-14150431.jsonl")
FIXTURE = Path(__file__).with_name("fixtures") / "ring-hunt-feeling-1128.jsonl.xz"
FIRST, LAST = 14151150, 14151330


def main():
    rows = []
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST:
            rows.append(json.dumps(row, ensure_ascii=False))
    FIXTURE.write_bytes(lzma.compress(("\n".join(rows) + "\n").encode("utf-8"), preset=9))
    print(FIXTURE.name, len(rows), FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
