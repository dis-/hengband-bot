"""Freeze the n1-b life-399 Quest 25 loops of 2026-11-15 16:46-16:47 (tests/test_n1b_399_q25_loops_1115_recorded.py).

Source: the viewing Magic-Eater n1-b life-399 (Lv35-36, build bot-e305dfdea) on Quest 25 『幽霊屋敷』.
Copied read-only from the viewing server to C:/hengband-backups/pdca/q25-n1b399-loop-1115:

  captures/20261115-164640-loop-detected   the ambush on [13,1]: the presence check's walk to [12,2]
      and back every 50 quiet actions (state rows 1902005-1902989, decisions)
  captures/20261115-164747-loop-detected   the corpse masses' phase on [1,7]: arrows at [2,20]
      (state rows 1918666-1919043, decisions)
  captures/20261115-164754-loop-detected   the same, the escalation
  q25-battle.json                          the battle record left (turn 1919350, phase 6)

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/q25-n1b399-loop-1115")
AMBUSH = ROOT / "captures" / "20261115-164640-loop-detected"
MASSES = ROOT / "captures" / "20261115-164747-loop-detected"
LAST = ROOT / "captures" / "20261115-164754-loop-detected"
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-399-q25-loops-1115.json.gz"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _part(directory, first, last):
    boards = [row for row in _rows(directory / "state.jsonl.gz")
              if row.get("type") == "player_turn" and first <= row["turn"] <= last]
    decisions = [[int(row["turn"]), row["reason"], row["key"], [row["position"]["y"], row["position"]["x"]]]
                 for row in _rows(directory / "bot-decisions.jsonl.gz") if "reason" in row]
    return {"boards": boards, "decisions": decisions}


def main():
    fixture = {
        "ambush": _part(AMBUSH, 1902224, 1902989),
        "masses": _part(MASSES, 1918900, 1919043),
        "last": {"decisions": _part(LAST, 0, 0)["decisions"]},
        "battle_record": json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(fixture["ambush"]["boards"]), len(fixture["masses"]["boards"]))


if __name__ == "__main__":
    main()
