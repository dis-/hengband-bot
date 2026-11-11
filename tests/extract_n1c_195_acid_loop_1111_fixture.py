"""Freeze n1-c life-195's loop stop of 2026-11-11 19:10 (Orc cave 23F, build bot-2d3ec8136).

Source: the automatic incident capture 20261111-191031-loop-detected copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1c-195-acid-1111/incident-20261111-191031/
(the stop's captures/20261111-191033-loop-detected next to it for the decision log).

Kept: the ring boards from the last dry cell of the walk in (turn 4667997, the dirt (50,177))
through the first round of the loop on the shallow acid puddle (turn 4668087), the recorded
decision rows of those turns, and of the stop's policy-state the remembered terrain, the visit
counts and the exploration's goal.  Only this tool reads the capture; the committed test reads
the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-195-acid-1111")
INCIDENT = ROOT / "incident-20261111-191031"
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-195-acid-loop-1111.json.xz"
TURNS = (4667997, 4668006, 4668018, 4668029, 4668039, 4668048, 4668059, 4668068, 4668075,
         4668087)
TERRAIN = ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t")


def main():
    boards = {}
    for row in ring_rows(INCIDENT / "snapshots" / "snapshots-current.jsonl.gz"):
        if row["type"] == "player_turn" and row["turn"] in TURNS:
            boards[row["turn"]] = row  # the last board of the turn
    decisions = []
    with gzip.open(ROOT / "20261111-191033-loop-detected" / "bot-decisions.jsonl.gz", "rt",
                   encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("turn") in TURNS and row.get("reason") not in (None, "loop-detected"):
                decisions.append({field: row.get(field)
                                  for field in ("decision_sequence", "turn", "reason", "key", "position")})
    captured = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))
    fixture = {
        "source": "20261111-191031-loop-detected (copied from the viewing server)",
        "boards": [boards[turn] for turn in TURNS],
        "decisions": decisions,
        "terrain": {key: captured["terrain"][key] for key in TERRAIN},
        "visits": captured["state"]["_visit_counts"],
        "explore_goal": captured["state"]["_explore_goal_identity"],
    }
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        fixture, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
