"""Extract tests/fixtures/n1c-loot-rules-1113.jsonl.gz.

Source: n1-c (Lv36-38 zombie Magic-Eater) boards copied read-only from the viewing server
(jsonlog/snapshots, jsonlog/bot-decisions.jsonl and a town-arrival checkpoint) to
C:/hengband-backups/pdca/captures/n1c-loot-rules-1113:

* ``summoner``: life-200, Angband 49F, 2026-11-12 11:53:45-11:54:11 (turns 3141491-3144853):
  the boards from the 120th (turn 3142439) to the 214th (turn 3143260).
* ``sensed``: life-205, Angband 46F, 2026-11-12 21:35:55-21:37:27 (the second visit to 46F in
  snapshots-20261112-213639/-215236): its first 51 boards (the first sensed-T1 leave is the 49th).
* ``full-pack``: life-205, Angband 62F quest 46, 2026-11-13 01:03-01:08: the board of turn
  2239645 (23 of 23 slots).
* ``unreachable``: life-205, Angband 30F, 2026-11-12 21:10:20-21:10:31: the boards with a decision
  record from turn 1763821 to turn 1764727 (two items detected at (16,147) and (19,136) have no
  route over the known floor).
* ``skill-knowledge``: the ~f list of life-205 (dungeon 12 49F visit).
* ``me-lists``: life-205's displayed absorbed-power lists in its 2026-11-13 01:40 town-arrival
  checkpoint (policy ``_me_device_lists``).

    python tests/extract_n1c_loot_rules_1113_fixture.py
"""
import gzip
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-loot-rules-1113")
TARGET = Path(__file__).with_name("fixtures") / "n1c-loot-rules-1113.jsonl.gz"


def _boards(name):
    with gzip.open(CAPTURE / name, "rt", encoding="utf-8") as stream:
        return [board for board in map(json.loads, stream) if board.get("type") == "player_turn"]


def main() -> None:
    rows = []
    summoner = _boards("115345_1-49-0.snapshots.jsonl.gz")
    rows += [{"role": "summoner", "board": board} for board in summoner[120:215]]
    with gzip.open(CAPTURE / "n1cloot_46.jsonl.gz", "rt", encoding="utf-8") as stream:
        sensed = [row["board"] for row in map(json.loads, stream)
                  if row["seg"] == 2 and row["board"].get("type") == "player_turn"]
    rows += [{"role": "sensed", "board": board} for board in sensed[:51]]
    rows += [{"role": "full-pack", "board": board}
             for board in _boards("010313_1-62-46.snapshots.jsonl.gz") if board["turn"] == 2239645][:1]
    with gzip.open(CAPTURE / "210912_1-30-0.decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        decided = {record["turn"] for record in map(json.loads, stream)}
    rows += [{"role": "unreachable", "board": board}
             for board in _boards("210912_1-30-0.snapshots.jsonl.gz")
             if board["turn"] in decided and 1763821 <= board["turn"] <= 1764727]
    with gzip.open(CAPTURE / "221032_12-49-0.snapshots.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows.append({"role": "skill-knowledge", "board": next(
            json.loads(line) for line in stream if '"skill_exp"' in line)})
    rows.append({"role": "me-lists",
                 "lists": json.loads((CAPTURE / "me_lists_0140.json").read_text(encoding="utf-8"))})
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
