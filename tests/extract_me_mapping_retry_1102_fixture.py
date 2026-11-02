"""Write tests/fixtures/me-mapping-retry-1102.json.gz from the n1-c capture.

Sources (copied from the viewing bot n1-c life-107, 2026-11-02):
  C:\\hengband-backups\\pdca\\captures\\mapping-retry-1102\\
      life-107-boards-942922-942984.jsonl.gz   the game's player_turn boards of
          the Angband 5F arrival (snapshots-20261102-183811-dae114, first
          record of each turn)
      life-107-decisions-5518-5530.jsonl.gz    decisions 5518-5530
          (bot-decisions.jsonl.3 at 19:30)

Usage (repository root): PYTHONPATH=src python tests/extract_me_mapping_retry_1102_fixture.py [capture-dir]
"""
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge

CAPTURES = Path(r"C:\hengband-backups\pdca\captures\mapping-retry-1102")
FIXTURE = Path(__file__).parent / "fixtures" / "me-mapping-retry-1102.json.gz"
BOARD_TURNS = (942940, 942948, 942960, 942971, 942984)
ROW_FIELDS = ("decision_sequence", "turn", "reason", "key", "position", "messages", "visible_hostiles")


def _jsonl(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main(root: Path) -> None:
    boards = {board["turn"]: board for board in _jsonl(root / "life-107-boards-942922-942984.jsonl.gz")}
    rows = [{name: row[name] for name in ROW_FIELDS}
            for row in _jsonl(root / "life-107-decisions-5518-5530.jsonl.gz")]
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    seen = {m["race_id"] for turn in BOARD_TURNS for m in boards[turn]["visible_monsters"]}
    data = {
        "monraces": {str(race): asdict(races[race]) for race in sorted(seen)},
        "boards": {str(turn): boards[turn] for turn in BOARD_TURNS},
        "rows": rows,
    }
    FIXTURE.parent.mkdir(exist_ok=True)
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, default=sorted)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else CAPTURES)
