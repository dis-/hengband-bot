"""Extract tests/fixtures/n1c-222-esp-fringe-1126/ (n1c-222-esp-fringe-1126).

Source: n1-c life-222's stop of 2026-11-26 10:16:39 (loop-detected on Angband 93F, floor (1, 93, 0),
bot main 9b7f2c3b4, "confined to [(13, 24), (13, 25), (14, 26), (15, 27), (15, 28), (16, 29)] over 40
decisions"), copied read-only to C:/hengband-backups/pdca/n1c-222-esp-fringe-1126/:

  boards.jsonl    the rows of life-222's jsonlog/snapshots/snapshots-current.jsonl.gz from turn
                  12405777 to the stop (the player_turn boards are kept)
  dec.jsonl       the rows of life-222's jsonlog/bot-decisions.jsonl from turn 12405777 to the stop
  map-memory.pkl  life-222's jsonlog/map-memory.pkl at the stop (map_memory_record: the 93F map the
                  process remembered, written at turn 12405881 or just before)

- ``boards.json.xz``: the player_turn boards;
- ``decisions.json.xz``: the decision rows reduced to the turn, the position, the key and the reason;
- ``map-memory.pkl.xz``: the map memory record as it was written.

    python tests/extract_n1c_222_esp_fringe_1126_fixture.py [SOURCE_DIRECTORY]
"""
import json
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET

SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1c-222-esp-fringe-1126")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-esp-fringe-1126"


def _rows(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
            if line.strip()]


if __name__ == "__main__":
    boards = [row for row in _rows(SOURCE / "boards.jsonl") if row.get("type") == "player_turn"]
    decisions = [{"turn": row["turn"], "position": [row["position"]["y"], row["position"]["x"]],
                  "key": row.get("key"), "reason": row.get("reason")}
                 for row in _rows(SOURCE / "dec.jsonl") if row.get("turn")]
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "boards.json.xz").write_bytes(lzma.compress(
        json.dumps(boards, ensure_ascii=False).encode("utf-8", "surrogateescape"), preset=PRESET))
    (FIXTURE / "decisions.json.xz").write_bytes(lzma.compress(
        json.dumps(decisions, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    (FIXTURE / "map-memory.pkl.xz").write_bytes(lzma.compress((SOURCE / "map-memory.pkl").read_bytes(), preset=PRESET))
    print(len(boards), len(decisions), sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
