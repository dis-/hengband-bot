"""Freeze the 2026-11-02 16:18 n1-c life-106 Yeek cave 1F loop (hourly-1600-1102).

Sources, copied under C:/hengband-backups/pdca/captures/hourly-1600-1102/:

  incident-life-106-20261102-161856-loop-detected/
      snapshots/snapshots-current.jsonl.gz  the ring of the looping session
          (bot-9afd9203e); rows 2106-2109 (turns 1007948-1007972).
      policy-state.json  the remembered terrain of the floor (``terrain``),
          the breakthrough latch and the fundraising mode at the stop.
  n1-c-life-106-20261102-161858-loop-detected/bot-decisions.jsonl.gz
      decisions 14061-14064 (the same turns).

Only this extraction tool reads the captures; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-1600-1102")
INCIDENT = ROOT / "incident-life-106-20261102-161856-loop-detected"
CAPTURE = ROOT / "n1-c-life-106-20261102-161858-loop-detected"
OUTPUT = Path(__file__).with_name("fixtures") / "breeder-reachable-upstairs-1102.json.gz"
ROWS = range(2106, 2110)
TERRAIN = ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t",
           "upstairs", "downstairs")


def _decisions(turns: set[int]) -> list[dict]:
    rows = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["turn"] in turns and row["reason"] != "loop-detected":
                rows.append({key: row[key] for key in
                             ("decision_sequence", "turn", "reason", "key", "position")})
    return rows


def main() -> None:
    ring_path = INCIDENT / "snapshots" / "snapshots-current.jsonl.gz"
    ring = ring_rows(ring_path.read_bytes())
    state_path = INCIDENT / "policy-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    boards = [ring[index] for index in ROWS]
    data = {
        "sources": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (ring_path, state_path)},
        "boards": boards,
        "terrain": {name: state["terrain"][name] for name in TERRAIN},
        "floor": state["floor"],
        "modes": {
            "_breeder_breakthrough_floor": state["state"]["_breeder_breakthrough_floor"],
            "_fundraising_mode": state["modes_and_latches"]["_fundraising_mode"],
            "_crossarea_fundraising_enforced":
                state["modes_and_latches"]["_crossarea_fundraising_enforced"],
        },
        "decisions": _decisions({board["turn"] for board in boards}),
    }
    payload = gzip.compress(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"), mtime=0)
    OUTPUT.write_bytes(payload)
    print(OUTPUT, len(payload), hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    main()
