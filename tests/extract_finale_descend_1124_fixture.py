"""Extract tests/fixtures/finale-descend-n1c-221-1124.jsonl.gz (tests/test_finale_descend_1124_recorded.py).

Source: n1-c life-221 (Magic-Eater Lv50, Oberon killed, the Serpent of Chaos's 100F the target),
2026-11-24, a read-only copy in C:/hengband-backups/pdca/captures/finale-descend-1124/:

  n1c221-95f.jsonl   the viewing server's snapshot logs
                     ``jsonlog/snapshots/snapshots-20261124-163814-c248f3.jsonl.gz``,
                     ``snapshots-20261124-165414-942731.jsonl.gz`` and ``snapshots-current.jsonl.gz``,
                     the turns around four decisions of the 95F visit after the finale's
                     preparation lifted the cap (16:51:52):
                     6450711-6450729  the arrival (live seq10960 me-power detect-all, 10964 explore)
                     6451301-6451319  live seq11191 detected:prepare-choke, 11192 detected:hold-choke
                     6451936-6452003  live seq11434 explore, 11454 seek-loot
                     6454130-6454149  live seq12232 loot:identify-floor-item, 12276 return:recall
                                      (trigger pack-full, 23 of 23 slots used)

Kept: the dungeon player_turn boards (95F), the first of each turn, gzip.

    python tests/extract_finale_descend_1124_fixture.py
"""
import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/finale-descend-1124")
FIXTURE = Path(__file__).with_name("fixtures") / "finale-descend-n1c-221-1124.jsonl.gz"


def main():
    kept, seen = [], set()
    for line in (ROOT / "n1c221-95f.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("type") != "player_turn" or row["turn"] in seen:
            continue
        if (row.get("floor") or {}).get("level") != 95:
            continue
        seen.add(row["turn"])
        kept.append(line)
    FIXTURE.write_bytes(gzip.compress(("\n".join(kept) + "\n").encode("utf-8"), 9))
    print(len(kept), FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
