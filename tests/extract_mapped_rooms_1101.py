"""Write tests/fixtures/mapped-rooms-1101.json.gz from the n1-c capture.

Source (streamed read-only from the viewing bot's life-080, 2026-11-01):
  C:\\hengband-backups\\pdca\\captures\\n1c-mapping-1101\\life-080-4f\\
      boards-4f.json       Angband 4F boards of turns 549703, 560863 and 561131
      decisions-4f.jsonl   every decision of the 4F visit (two bot sessions)

Usage (repository root): PYTHONPATH=src python tests/extract_mapped_rooms_1101.py [capture-dir]
"""
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys

from hengbot.dungeon_knowledge import load_dungeon_knowledge

CAPTURE = Path(r"C:\hengband-backups\pdca\captures\n1c-mapping-1101\life-080-4f")
EDIT = Path(r"C:\hengband\lib\edit")
FIXTURE = Path(__file__).parent / "fixtures" / "mapped-rooms-1101.json.gz"
TURNS = (549703, 560863, 561131)
ANGBAND = 1
ROW_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")


def main(root: Path) -> None:
    boards = json.loads((root / "boards-4f.json").read_text(encoding="utf-8"))
    with open(root / "decisions-4f.jsonl", encoding="utf-8") as stream:
        rows = [{name: row[name] for name in ROW_FIELDS} for row in map(json.loads, stream)]
    # The map-area casts, and the recorded decisions from the first cast to
    # just after the last board.
    kept = [row for row in rows if row["reason"].endswith(":map-area")
            or TURNS[0] - 200 <= row["turn"] <= TURNS[-1] + 400]
    dungeon = asdict(load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")[ANGBAND])
    data = {"boards": {str(turn): boards[str(turn)] for turn in TURNS},
            "rows": kept, "dungeon": dungeon}
    FIXTURE.parent.mkdir(exist_ok=True)
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, default=sorted)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else CAPTURE)
