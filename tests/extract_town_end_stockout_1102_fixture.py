"""Freeze the town-end-stockout-1102 boards (2026-11-02 21:11 and 21:14).

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/hourly-2200-1102/:

  n1-c-life-109-20261102-211116-town-blocked-survival-cure-critical-ready/state.jsonl.gz
      n1-c (Magic-Eater Lv16) climbing out of its Yeek Cave 1F mining run:
      the last 1F board (turn 1027553), the first town board (1027554) and
      the stop board (1027575, town:blocked:survival:cure_critical_ready).
  n1-a-life-464-20261102-211429-town-blocked-survival-identify-staff-ready/state.jsonl.gz
      n1-a (Warrior Lv42) after its Identify-staff stockout run: the stop
      board (5553829, town:blocked:survival:identify_staff_ready), the
      Magic shop page it saw (5553353), the Alchemist page (5553815) and the
      last Home list it read.

Kept: those boards, each capture's skill row, n1-a's last Home row.  Only
this extraction tool reads the captures; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_n1c_loops_0336_1102_fixtures import write


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-2200-1102")
N1C = ROOT / "n1-c-life-109-20261102-211116-town-blocked-survival-cure-critical-ready"
N1A = ROOT / "n1-a-life-464-20261102-211429-town-blocked-survival-identify-staff-ready"
OUTPUT = Path(__file__).with_name("fixtures") / "town-end-stockout-1102.json.gz"


def rows_of(capture: Path) -> list[dict]:
    with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def first(rows, kind, turn):
    return next(row for row in rows if row["type"] == kind and row["turn"] == turn)


def knowledge(rows, category, *, last=False):
    found = [row for row in rows if row["type"] == "knowledge"
             and row["knowledge"]["category"] == category]
    return found[-1] if last else found[0]


def main():
    n1c, n1a = rows_of(N1C), rows_of(N1A)
    write(OUTPUT, dict(
        source="state.jsonl.gz of the two hourly-2200-1102 captures (copied from the viewing server)",
        n1c=dict(dungeon=first(n1c, "player_turn", 1027553),
                 arrival=first(n1c, "player_turn", 1027554),
                 stop=first(n1c, "player_turn", 1027575),
                 skill=knowledge(n1c, "skill_exp")),
        n1a=dict(stop=[row for row in n1a if row["type"] == "player_turn"
                       and row["turn"] == 5553829][-1],
                 magic=first(n1a, "store", 5553353),
                 alchemist=first(n1a, "store", 5553815),
                 home=knowledge(n1a, "home", last=True),
                 skill=knowledge(n1a, "skill_exp"))))


if __name__ == "__main__":
    main()
