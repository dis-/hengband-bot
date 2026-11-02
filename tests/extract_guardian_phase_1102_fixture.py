"""Freeze the n1-b life-249 Boldor reposition board of 2026-10-30 (guardian-phase-1102).

Source: the viewing Warrior n1-b life-249 (Lv19), イークの洞穴 13F (dungeon 2,
guardian 237 イークの大王『ボルドール』), copied read-only to
C:/hengband-backups/pdca/captures/unfixed-24h-1031/n1-b/life-249/:

  board     ring row of turn 463280 in
            incident-captures/20261030-002000-loop-detected/snapshots/
            snapshots-current.jsonl.gz, the board of decision 15005
            ('rh', guardian:teleport-to-cover: the 14 テレポートの巻物 in h;
            the pack also holds 1 ショート・テレポートの巻物 in g).
  skill     the last skill_exp knowledge row of the ring before it.
  decisions decisions 15003-15006 of the 00:20:01 capture's
            bot-decisions.jsonl.gz (key and reason only).

Only this extraction tool reads the captures; the committed test reads the
fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/unfixed-24h-1031/n1-b/life-249")
RING = (ROOT / "incident-captures/20261030-002000-loop-detected/snapshots"
        / "snapshots-current.jsonl.gz")
DECISIONS = ROOT / "captures/20261030-002001-loop-detected/bot-decisions.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "guardian-phase-20261030.json.gz"
TURN = 463280
SEQUENCES = range(15003, 15007)


def main():
    rows = ring_rows(RING)
    index = max(i for i, row in enumerate(rows)
                if row.get("type") == "player_turn" and row["turn"] == TURN)
    skill = next(row for row in reversed(rows[:index])
                 if row.get("type") == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp")
    decisions = []
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("decision_sequence") in SEQUENCES:
                decisions.append({key: row[key] for key in (
                    "decision_sequence", "turn", "key", "reason")})
    fixture = {"source": str(ROOT), "board": rows[index], "skill": skill,
               "decisions": decisions}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
