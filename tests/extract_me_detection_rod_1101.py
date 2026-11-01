"""Write tests/fixtures/me-detection-rod-1101.json.gz from the n1-c capture.

Source (copied from the viewing bot's life directory, 2026-11-01):
  C:\\hengband-backups\\pdca\\captures\\viewing-incidents-20261101\\n1-c\\life-073\\
      incident-captures\\20261101-004025-stuck-prompt\\
      snapshots\\snapshots-current.jsonl.gz  boards, turns 779782-788293
                                            (a multi-member gzip tail)
      decision-tail.jsonl                    the decisions of those turns
      policy-state.json                      the absorption record (_me_staff_sequence.absorbed)

Boards: Angband 7F arrival (turn 788206, decision 15253, recorded
me-power:new-floor:detect-evil, mAp) and Angband 8F before the rest (turn
785562, decision 14980, recorded me-power:before-rest:detect-evil, mAp).

Usage (repository root): PYTHONPATH=src python tests/extract_me_detection_rod_1101.py [capture-dir]
"""
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys
import zlib

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge

CAPTURE = Path(r"C:\hengband-backups\pdca\captures\viewing-incidents-20261101\n1-c\life-073"
               r"\incident-captures\20261101-004025-stuck-prompt")
FIXTURE = Path(__file__).parent / "fixtures" / "me-detection-rod-1101.json.gz"
TURNS = {"arrival-7f": 788206, "rest-8f": 785562}
ROW_FIELDS = ("decision_sequence", "turn", "reason", "key", "position", "visible_hostiles",
              "player", "floor")
SEQUENCES = range(14975, 15260)


def _members(data: bytes):
    """Every complete gzip member from the first member header on."""
    start = data.find(b"\x1f\x8b\x08")
    out = b""
    while start != -1 and start < len(data):
        stream = zlib.decompressobj(31)
        try:
            out += stream.decompress(data[start:])
        except zlib.error:
            start = data.find(b"\x1f\x8b\x08", start + 1)
            continue
        if not stream.unused_data:
            break
        start = len(data) - len(stream.unused_data)
    return out


def _boards(root: Path) -> dict:
    wanted = set(TURNS.values())
    boards = {}
    for line in _members((root / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()).split(b"\n"):
        try:
            board = json.loads(line)
        except ValueError:
            continue
        if board.get("turn") in wanted:
            boards.setdefault(board["turn"], board)
    return boards


def _rows(root: Path) -> list:
    rows = []
    with open(root / "decision-tail.jsonl", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("decision_sequence") in SEQUENCES:
                rows.append({name: row.get(name) for name in ROW_FIELDS})
    return rows


def _absorbed(root: Path) -> dict:
    """The record keyed as me_capability.record_key (a bare sval is a staff)."""
    state = json.loads((root / "policy-state.json").read_text(encoding="utf-8"))["state"]
    return {(key if ":" in key else f"staff:{key}"): count
            for key, count in state["_me_staff_sequence"]["absorbed"].items()}


def main(root: Path) -> None:
    boards = _boards(root)
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    seen = {monster["race_id"] for board in boards.values()
            for monster in board["visible_monsters"] + board["detected_monsters"]}
    data = {
        "monraces": {str(race): asdict(races[race]) for race in sorted(seen) if race in races},
        "boards": {name: boards[turn] for name, turn in TURNS.items()},
        "rows": _rows(root),
        "absorbed": _absorbed(root),
    }
    FIXTURE.parent.mkdir(exist_ok=True)
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, default=sorted)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else CAPTURE)
