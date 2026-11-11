"""Write tests/fixtures/deep-50f-c6-1111.json.gz from the n1-b deep-dive capture.

Source (copied read-only from hengband.net on 2026-11-11, see its SOURCE.txt):
  C:\\hengband-backups\\pdca\\captures\\deep-dive-1110\\c6-boards\\
      snapshots-20261110-210702-165f14-lines.jsonl.gz   raw boards of n1-b (Magic-Eater, Lv41)
  C:\\hengband-backups\\pdca\\captures\\deep-dive-1110\\n1b-dec.jsonl
                                                       the compact decision rows of those turns

Boards (the first board of each turn; a turn's later boards are the prompts of its command):
  lighting   Mountain 50F, turns 5332441-5332475: the arrival, and turn 5332467 where the
             recorded me-power:dark-room:lite-area (mAi) woke four of the sleepers the
             telepathy showed (REPORT 1.3, PLAN-50F 4.4).
  castle     Castle 61F, turns 5329565-5329853: the arrival detection (UCg) at (5,18), the
             recorded arrival casts after it (5329572-5329602), and the walk at (27,10) on turn
             5329849 (game distance 24) and at (28,11) on turn 5329853 (game distance 25).
  mountain   Mountain 50F, turns 5334011-5334020: the arrival detection (UCg) and the next
             board (recorded explore).

Usage (repository root): PYTHONPATH=src python tests/extract_deep_50f_c6_1111.py [capture-dir]
"""
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.monrace_knowledge import load_monrace_knowledge

CAPTURE = Path(r"C:\hengband-backups\pdca\captures\deep-dive-1110")
FIXTURE = Path(__file__).parent / "fixtures" / "deep-50f-c6-1111.json.gz"
EDIT = Path("C:/hengband/lib/edit")
CASES = {
    "lighting": (5332441, 5332446, 5332454, 5332460, 5332467, 5332475),
    "castle": (5329565, 5329572, 5329578, 5329586, 5329595, 5329602, 5329849, 5329853),
    "mountain": (5334011, 5334020),
}
ROW_FIELDS = ("s", "turn", "dg", "lv", "hp", "r", "k", "vh")


def _boards(root: Path) -> dict:
    wanted = {turn for turns in CASES.values() for turn in turns}
    boards = {}
    path = root / "c6-boards" / "snapshots-20261110-210702-165f14-lines.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            board = json.loads(line)["board"]
            if board.get("turn") in wanted:
                boards.setdefault(board["turn"], board)
    return boards


def _rows(root: Path) -> list:
    wanted = {turn for turns in CASES.values() for turn in turns}
    rows = []
    with open(root / "n1b-dec.jsonl", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") in wanted:
                rows.append({name: row.get(name) for name in ROW_FIELDS})
    return rows


def main(root: Path) -> None:
    boards = _boards(root)
    races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
    seen = {monster["race_id"] for board in boards.values()
            for monster in board["visible_monsters"] + board["detected_monsters"]}
    data = {
        "monraces": {str(race): asdict(races[race]) for race in sorted(seen) if race in races},
        "dungeons": {str(key): asdict(dungeons[key]) for key in (12, 14)},
        "cases": {name: [boards[turn] for turn in turns] for name, turns in CASES.items()},
        "rows": _rows(root),
    }
    FIXTURE.parent.mkdir(exist_ok=True)
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, default=sorted)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else CAPTURE)
