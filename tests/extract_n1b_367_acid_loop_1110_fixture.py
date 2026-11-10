"""Freeze n1-b life-367's loop stop of 2026-11-10 20:11 (Orc cave 23F, build bot-c6308419e).

Source: the automatic incident capture 20261110-201148-loop-detected copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1b-367-acid-loop-1110/inc/ (the stop's
captures/20261110-201151-loop-detected next to it for the decision log).

Kept: the ring boards of one round of the loop (turns 5143175-5143191: the player on (45,61),
the shallow acid puddle (46,60), (45,59), (45,60), and (45,61) again), the recorded decision rows
of those turns, and of the stop's policy-state the remembered terrain and the visit counts.
Only this tool reads the capture; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1b-367-acid-loop-1110")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-367-acid-loop-1110.json.xz"
TURNS = (5143175, 5143180, 5143183, 5143187, 5143191)
TERRAIN = ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t")


def main():
    boards = {}
    for row in ring_rows(ROOT / "inc" / "snapshots" / "snapshots-current.jsonl.gz"):
        if row["type"] == "player_turn" and row["turn"] in TURNS:
            boards[row["turn"]] = row  # the last board of the turn
    decisions = []
    with gzip.open(ROOT / "20261110-201151-loop-detected" / "bot-decisions.jsonl.gz", "rt",
                   encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("turn") in TURNS and row.get("reason") not in (None, "loop-detected"):
                decisions.append({field: row.get(field)
                                  for field in ("decision_sequence", "turn", "reason", "key", "position")})
    captured = json.loads((ROOT / "inc" / "policy-state.json").read_text(encoding="utf-8"))
    fixture = {
        "source": "20261110-201148-loop-detected (copied from the viewing server)",
        "boards": [boards[turn] for turn in TURNS],
        "decisions": decisions,
        "terrain": {key: captured["terrain"][key] for key in TERRAIN},
        "visits": captured["state"]["_visit_counts"],
    }
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        fixture, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
