"""Extract tests/fixtures/sealed-loot-melt-1113.jsonl.gz.

Source: n1-c life-205 (Lv45 zombie Magic-Eater, Orc cave 23F) boards copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1c-loot-left-1113pm (boards-1113.jsonl.gz):

* ``board``: label ``st-1318``, the last 40 boards before the 13:18:29 return (turns up to
  4026205; jsonlog/snapshots of 2026-11-13 13:12-13:21).  On the last the live bot read Recall
  (bot-decisions, decision 4529, ``stuck:recall-escape``, key ``rk``) with three detected items
  behind a row of traps in walled rooms, (24,86), (24,90) and (25,91).
* ``wand-list``: the life's displayed absorbed wand list (岩石溶解 99/99) from its 2026-11-13 01:40
  town-arrival checkpoint, as tests/fixtures/n1c-loot-rules-1113.jsonl.gz holds it.
* ``sensed``: one telepathy-sensed hostile of the same life (label ``pf-0922``, a スケイヴン).

    python tests/extract_sealed_loot_melt_1113_fixture.py
"""
import gzip
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-loot-left-1113pm")
FIXTURES = Path(__file__).with_name("fixtures")
TARGET = FIXTURES / "sealed-loot-melt-1113.jsonl.gz"
LIVE = {"role": "live", "time": "2026-11-13T13:18:29+0900", "decision_sequence": 4529,
        "turn": 4026205, "reason": "stuck:recall-escape", "key": "rk"}


def main() -> None:
    boards, sensed = [], None
    with gzip.open(CAPTURE / "boards-1113.jsonl.gz", "rt", encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            if row["label"] == "st-1318":
                boards.append(row["board"])
            elif sensed is None and row["board"].get("detected_monsters"):
                sensed = row["board"]["detected_monsters"][0]
    with gzip.open(FIXTURES / "n1c-loot-rules-1113.jsonl.gz", "rt", encoding="utf-8") as stream:
        lists = next(row["lists"] for row in map(json.loads, stream) if row["role"] == "me-lists")
    rows = [{"role": "board", "board": board} for board in boards[-40:]]
    rows += [{"role": "wand-list", "list": lists["wand"]}, {"role": "sensed", "monster": sensed}, LIVE]
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
