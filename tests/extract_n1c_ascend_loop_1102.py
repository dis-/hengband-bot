r"""Write tests/fixtures/n1c-ascend-loop-1102.json.gz from the n1-c capture.

Source (copied read-only from the viewing bot's life-099, 2026-11-02 00:3x):
  C:\hengband-backups\pdca\captures\n1c-ascend-loop-1102\
      state-tail.jsonl.gz           the last 400 player boards
      bot-decisions-tail.jsonl.gz   the last 8000 decisions

Kept: the Angband 5F board of the recorded stuck:ascend (turn 337229, after
the arrival's detect-evil, detect-traps and map-area) and the decision rows
of the eight 3F <-> 5F cycles.

Usage (repository root): PYTHONPATH=src python tests/extract_n1c_ascend_loop_1102.py [capture-dir]
"""
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys

from hengbot.dungeon_knowledge import load_dungeon_knowledge

CAPTURE = Path(r"C:\hengband-backups\pdca\captures\n1c-ascend-loop-1102")
EDIT = Path(r"C:\hengband\lib\edit")
FIXTURE = Path(__file__).parent / "fixtures" / "n1c-ascend-loop-1102.json.gz"
STUCK_TURN = 337229
ANGBAND = 1
ROW_FIELDS = ("decision_sequence", "turn", "reason", "key", "position", "floor")
KEPT_REASONS = ("descend", "stuck:ascend", "me-power:new-floor:")


def main(root: Path) -> None:
    with gzip.open(root / "state-tail.jsonl.gz", "rt", encoding="utf-8") as stream:
        board = next(row for row in map(json.loads, stream) if row["turn"] == STUCK_TURN)
    with gzip.open(root / "bot-decisions-tail.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [{name: row[name] for name in ROW_FIELDS} for row in map(json.loads, stream)
                if row["reason"].startswith(KEPT_REASONS)]
    dungeon = asdict(load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")[ANGBAND])
    data = {"board": board, "rows": rows, "dungeon": dungeon}
    FIXTURE.parent.mkdir(exist_ok=True)
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, default=sorted)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else CAPTURE)
