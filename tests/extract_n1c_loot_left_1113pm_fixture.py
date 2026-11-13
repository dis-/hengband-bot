"""Extract tests/fixtures/n1c-loot-left-1113pm.jsonl.gz.

Source: n1-c life-205 (Lv45 zombie Magic-Eater, Orc cave 23F) boards copied read-only from the
viewing server (jsonlog/snapshots/snapshots-20261113-092455-b627b9.jsonl.gz and
jsonlog/bot-decisions.jsonl.7) to C:/hengband-backups/pdca/captures/n1c-loot-left-1113pm
(boards-1113.jsonl.gz, label ``pf-0922``):

* ``full-pack``: the last three boards before the 09:22:12 return (turns 3629396-3629410): the
  walk to a pile, its pickup (22 -> 23 of 23 slots) and the board the pack filled, on which the
  live bot read Recall (decision 1979, ``return:recall``, trigger ``pack-full``, key ``ri``).

    python tests/extract_n1c_loot_left_1113pm_fixture.py
"""
import gzip
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-loot-left-1113pm")
TARGET = Path(__file__).with_name("fixtures") / "n1c-loot-left-1113pm.jsonl.gz"
LIVE = {"role": "live-return", "time": "2026-11-13T09:22:12+0900", "decision_sequence": 1979,
        "turn": 3629410, "reason": "return:recall", "trigger": "pack-full", "key": "ri"}


def main() -> None:
    with gzip.open(CAPTURE / "boards-1113.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row["board"] for row in map(json.loads, stream) if row["label"] == "pf-0922"]
    rows = [{"role": "full-pack", "board": board} for board in boards[-3:]]
    rows.append(LIVE)
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
