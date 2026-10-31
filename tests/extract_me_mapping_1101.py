"""Write tests/fixtures/me-mapping-1101.json.gz from the n1-c captures.

Sources (copied from the viewing bot's life directories, 2026-11-01):
  C:\\hengband-backups\\pdca\\captures\\n1c-mapping-1101\\life-073-3f\\
      board-510032.json   the board of decision 2000 (Angband 3F, turn 510032)
      decisions-3f.jsonl  decisions 1876-2000 (sequence, turn, reason, key, position)
  C:\\hengband-backups\\pdca\\captures\\n1c-mapping-1101\\life-065-1f\\
      boards-1f.json      Yeek cave 1F boards, turns 4665340-4665560
      decisions-1f.jsonl  the decisions of those turns

Usage (repository root): PYTHONPATH=src python tests/extract_me_mapping_1101.py [capture-dir]
"""
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge

CAPTURES = Path(r"C:\hengband-backups\pdca\captures\n1c-mapping-1101")
FIXTURE = Path(__file__).parent / "fixtures" / "me-mapping-1101.json.gz"
LIFE073_TURN = 510032
LIFE065_TURN = 4665371
ROW_FIELDS = ("decision_sequence", "turn", "reason", "key", "position", "visible_hostiles")


def _rows(path):
    with open(path, encoding="utf-8") as stream:
        return [dict({name: row[name] for name in ROW_FIELDS},
                     down_stairs=(row.get("map_memory") or {}).get("down_stairs"))
                for row in map(json.loads, stream)]


def main(root: Path) -> None:
    life073 = root / "life-073-3f"
    life065 = root / "life-065-1f"
    board073 = json.loads((life073 / "board-510032.json").read_text(encoding="utf-8"))["board"]
    assert board073["turn"] == LIFE073_TURN
    boards065 = json.loads((life065 / "boards-1f.json").read_text(encoding="utf-8"))
    board065 = boards065[str(LIFE065_TURN)]
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    seen = {m["race_id"] for m in board065["visible_monsters"] + board073["visible_monsters"]}
    data = {
        "monraces": {str(race): asdict(races[race]) for race in sorted(seen)},
        "life-073": {"board": board073, "rows": _rows(life073 / "decisions-3f.jsonl")},
        "life-065": {"board": board065,
                     "rows": _rows(life065 / "decisions-1f.jsonl")},
    }
    FIXTURE.parent.mkdir(exist_ok=True)
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, default=sorted)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else CAPTURES)
