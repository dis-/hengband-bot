"""Freeze the n1-b life-411 choke holds of 2026-11-19 (tests/test_n1b_411_hold_choke_1119_recorded.py).

Source: the viewing Magic-Eater n1-b life-411 (Lv 50), Angband 95F (floor (1, 95, 0)), halted by
the server watcher ``stall:floor-dwell:seek-loot`` at 15:52:26.  Copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1b-411-hold-choke-1119:

  snapshots-current.jsonl.gz      the player-turn boards from turn 8875391 to the halt
  decisions-95f.jsonl.gz          every decision row on the floor (turn 8897330 on)

Kept: four runs of boards (each with its map) on the floor --

  arm     8902450-8902500  detected:prepare-choke from seek-loot and the hold at (20,18) it began
                           (wolves and the orc nest's members detected around it)
  expire  8902978-8902995  the same hold reaching its bound (DETECTED_THREAT_HOLD_MAX_GAME_TURNS)
  sight   8903049-8903056  a hostile in view and shot (ranged:magic-eater-device): the visible
                           channel's episode, which cleared the expired hold's latch
  rearm   8903320-8903350  the walk back near the wolves: detected:prepare-choke, then
                           summoner:hold-choke at (30,12), its second 500-game-turn wait there

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/captures/n1b-411-hold-choke-1119")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-411-hold-choke-1119.json.xz"
RUNS = {"arm": (8902450, 8902500), "expire": (8902978, 8902995), "sight": (8903049, 8903056),
        "rearm": (8903320, 8903350)}


def main():
    runs = {name: [] for name in RUNS}
    with gzip.open(ROOT / "snapshots-current.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("type") != "player_turn" or "grid_map" not in row:
                continue
            for name, (low, high) in RUNS.items():
                if low <= row["turn"] <= high:
                    runs[name].append(row)
    decisions = []
    with gzip.open(ROOT / "decisions-95f.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if any(low <= row["turn"] <= high for low, high in RUNS.values()):
                decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                                  "position": row.get("position")})
    fixture = {
        "source": "20261119-155226-stall-floor-dwell-seek-loot (copied from the viewing server)",
        "runs": runs,
        "decisions": decisions,
    }
    payload = json.dumps(fixture, ensure_ascii=False, sort_keys=True).encode("utf-8")
    OUTPUT.write_bytes(lzma.compress(payload, preset=9))
    print(OUTPUT.name, {name: len(rows) for name, rows in runs.items()}, len(decisions),
          OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
