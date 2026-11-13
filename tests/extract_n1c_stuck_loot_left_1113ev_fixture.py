"""Extract tests/fixtures/n1c-stuck-loot-left-1113ev.jsonl.gz.

Source: n1-c life-205 (Lv46 zombie Magic-Eater, Orc cave 23F) boards copied read-only from the
viewing server (jsonlog/snapshots/snapshots-20261113-153728-8fe0cf.jsonl.gz and
snapshots-20261113-192038-298e18.jsonl.gz, matched to bot-decisions.jsonl.7 / .2 by turn and
player cell) to C:/hengband-backups/pdca/captures/n1c-stuck-loot-left-1113ev (boards-live.jsonl.gz):

* ``pack-full`` (label ``ret-1544``): the five boards of 15:44:19-15:44:20 (turns
  4269104-4269118): the pickup that filled the pack (23 of 23), the exchange's walk onto a
  metal scale mail pile (base 1100) and the board on the pile, where the live bot read Recall
  (decision 4148, ``return:recall``, key ``rj``).
* ``hold`` (label ``ana-1917``): the 44 boards of 19:17:00-19:17:23 (turns 4607100-4607260): the
  loot walk committed to a polearm at (55,60), then the anaguma pocket dug at (53,63)/(52,62)
  and held there; live (bot-decisions.jsonl.2, decision 10505) the polearm was deferred for the
  floor on the 32nd board of the hold.  Each board carries the live decision's reason and key.

    python tests/extract_n1c_stuck_loot_left_1113ev_fixture.py
"""
import gzip
import json
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-stuck-loot-left-1113ev")
TARGET = Path(__file__).with_name("fixtures") / "n1c-stuck-loot-left-1113ev.jsonl.gz"
LIVE_RETURN = {"role": "live-return", "time": "2026-11-13T15:44:20+0900",
               "decision_sequence": 4148, "turn": 4269118, "reason": "return:recall",
               "trigger": "pack-full", "key": "rj"}
LIVE_DEFERRAL = {"role": "live-deferral", "time": "2026-11-13T19:17:22+0900",
                 "decision_sequence": 10505, "turn": 4607253, "reason": "anaguma:hold",
                 "deferred": [55, 60]}


def main() -> None:
    live = {}
    with gzip.open(CAPTURE / "dec.jsonl.gz", "rt", encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            if row["tu"] is not None and row["pos"]:
                live[(row["tu"], row["pos"]["y"], row["pos"]["x"])] = row
    boards = {"ret-1544": [], "ana-1917": []}
    with gzip.open(CAPTURE / "boards-live.jsonl.gz", "rt", encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            if row["label"] in boards and row["board"].get("type") in ("player_turn", "knowledge"):
                boards[row["label"]].append(row["board"])
    rows = []
    for board in sorted(boards["ret-1544"], key=lambda board: board["turn"]):
        rows.append({"role": "pack-full", "board": board})
    rows.append(LIVE_RETURN)
    for board in sorted(boards["ana-1917"], key=lambda board: board["turn"]):
        decision = live[(board["turn"], board["player"]["y"], board["player"]["x"])]
        rows.append({"role": "hold", "board": board,
                     "live": {"reason": decision["r"], "key": decision["k"]}})
    rows.append(LIVE_DEFERRAL)
    TARGET.parent.mkdir(exist_ok=True)
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
