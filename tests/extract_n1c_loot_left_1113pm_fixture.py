"""Extract tests/fixtures/n1c-loot-left-1113pm.jsonl.gz.

Source: n1-c life-205 (Lv45 zombie Magic-Eater, Orc cave 23F) boards copied read-only from the
viewing server (jsonlog/snapshots/snapshots-20261113-092455-b627b9.jsonl.gz and
jsonlog/bot-decisions.jsonl.7) to C:/hengband-backups/pdca/captures/n1c-loot-left-1113pm
(boards-1113.jsonl.gz, label ``pf-0922``):

* ``full-pack``: the last three boards before the 09:22:12 return (turns 3629396-3629410): the
  walk to a pile, its pickup (22 -> 23 of 23 slots) and the board the pack filled, on which the
  live bot read Recall (decision 1979, ``return:recall``, trigger ``pack-full``, key ``ri``).
* ``choke-hold``: snapshots-20261113-132925-54476e.jsonl.gz (boards-hc-1326.jsonl.gz, label
  ``hc-1326``), the 260th to the 274th board of 13:26:20-13:26:49 (turns 4044384-4044417): a
  loot walk committed to (57,164), then a ``detected:hold-choke`` at (55,163).  Live
  (bot-decisions.jsonl.1, decisions 7870-7904): the walk to the heavy chain mail at (55,163)
  was deferred on the 25th board of a choke hold at (57,164) (13:26:32, decision 7904).

    python tests/extract_n1c_loot_left_1113pm_fixture.py
"""
import gzip
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-loot-left-1113pm")
TARGET = Path(__file__).with_name("fixtures") / "n1c-loot-left-1113pm.jsonl.gz"
LIVE = {"role": "live-return", "time": "2026-11-13T09:22:12+0900", "decision_sequence": 1979,
        "turn": 3629410, "reason": "return:recall", "trigger": "pack-full", "key": "ri"}
LIVE_DEFERRAL = {"role": "live-deferral", "time": "2026-11-13T13:26:32+0900",
                 "decision_sequence": 7904, "turn": 4044234, "reason": "detected:hold-choke",
                 "deferred": [55, 163]}


def main() -> None:
    with gzip.open(CAPTURE / "boards-1113.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row["board"] for row in map(json.loads, stream) if row["label"] == "pf-0922"]
    rows = [{"role": "full-pack", "board": board} for board in boards[-3:]]
    rows.append(LIVE)
    with gzip.open(CAPTURE / "boards-hc-1326.jsonl.gz", "rt", encoding="utf-8") as stream:
        held = [row["board"] for row in map(json.loads, stream) if row["label"] == "hc-1326"]
    rows += [{"role": "choke-hold", "board": board} for board in held[260:275]]
    rows.append(LIVE_DEFERRAL)
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
