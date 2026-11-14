"""Freeze the n1-c life-208 Quest 25 patrol stops of 2026-11-15 (tests/test_n1c_208_q25_patrol_1115_recorded.py).

Source: the viewing Magic-Eater n1-c life-208 (Lv33, build bot-5602f6e11) on Quest 25 『幽霊屋敷』
(floor (0, 48, 25)), every phase of the plan over (battle phase 11), the KILL_ALL patrol owning the
floor.  Copied read-only from the viewing server to C:/hengband-backups/pdca/n1c-208-q25-1115:

  captures/20261115-044800-stuck-prompt-quest-patrol-detect   the first stop: ``mCg`` under the
      bare reason ``quest-patrol:detect`` while the Rod of Detection charged (state rows
      4027711-4028926, their decision rows, the game's screen at the stop)
  captures/20261115-044857-loop-detected                      the restarted process: the Nexus
      quylthulg in view and walked to three times, the rounds spent, ``quest:blocked:quest-patrol-
      rounds`` repeated until the loop guard (state rows 4032518-4033446 and their decisions)
  jsonlog/q25-battle.json                                     the battle record (kills, phase)

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/n1c-208-q25-1115")
STUCK = ROOT / "captures" / "20261115-044800-stuck-prompt-quest-patrol-detect"
LOOP = ROOT / "captures" / "20261115-044857-loop-detected"
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-208-q25-patrol-1115.json.gz"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _capture(directory):
    boards = [row for row in _rows(directory / "state.jsonl.gz") if row.get("type") == "player_turn"]
    turns = {board["turn"] for board in boards}
    decisions = [{"turn": int(row["turn"]), "reason": row["reason"], "key": row["key"]}
                 for row in _rows(directory / "bot-decisions.jsonl.gz")
                 if row.get("turn") is not None and int(row["turn"]) in turns]
    return {"source": f"{directory.name} (copied from the viewing server)",
            "boards": boards, "decisions": decisions}


def main():
    stuck = _capture(STUCK)
    with gzip.open(STUCK / "control-at-stop.json.gz", "rt", encoding="utf-8") as stream:
        stop = json.load(stream)
    stuck["stop_screen"] = stop["screen"]
    fixture = {
        "stuck": stuck,
        "loop": _capture(LOOP),
        "battle_record": json.loads((ROOT / "jsonlog" / "q25-battle.json").read_text(encoding="utf-8")),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(stuck["boards"]), len(stuck["decisions"]),
          len(fixture["loop"]["boards"]), len(fixture["loop"]["decisions"]))


if __name__ == "__main__":
    main()
