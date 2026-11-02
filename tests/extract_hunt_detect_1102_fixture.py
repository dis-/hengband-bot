"""Write tests/fixtures/hunt-detect-1102.json.gz from two n1-c random-quest floors.

Sources (copied read-only from the viewing bot, 2026-11-02):
  C:\\hengband-backups\\pdca\\captures\\viewing-incidents-20261102\\n1-c\\
    life-103\\incident-captures\\20261102-090917-livelock-exhausted\\
        Angband 24F, RANDOM quest 41, target 『金のスニッチ』 race 1329 (not EVIL);
        board turn 2408201 (decision 12584, recorded ``explore``), Lv30 HP 430/430.
    life-098\\incident-captures\\20261101-200240-livelock-exhausted\\
        Angband 12F, RANDOM quest 43, target 鬼殺隊の『先輩』 race 1164 (EVIL);
        board turn 1171515 (the ring's first board; the decision tail starts at
        turn 1176550), Lv21 HP 223/223.
  Each: snapshots/snapshots-current.jsonl.gz (a multi-member gzip tail), the
  decision rows of the board's turns (decision-tail.jsonl), and from
  policy-state.json the absorption record and the floor's me_powers uses made
  before the board's turn (``_me_power_floor``).

Usage (repository root): PYTHONPATH=src python tests/extract_hunt_detect_1102_fixture.py
"""
from dataclasses import asdict
import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_detection_rod_1101 import _members

ROOT = Path(r"C:\hengband-backups\pdca\captures\viewing-incidents-20261102\n1-c")
FIXTURE = Path(__file__).parent / "fixtures" / "hunt-detect-1102.json.gz"
CASES = {
    "snitch-24f": (ROOT / "life-103/incident-captures/20261102-090917-livelock-exhausted",
                   2408201, range(12580, 12590), 1329),
    "senior-12f": (ROOT / "life-098/incident-captures/20261101-200240-livelock-exhausted",
                   1171515, range(0), 1164),
    # hunt-redetect-1102: the stuck:wander boards near the before-rest Detect
    # Evil at (16,17), turn 1173086: 993 and 1008 game turns later, and turn
    # 1176550 (decision 8091, recorded ``search``).
    "senior-12f-993": (ROOT / "life-098/incident-captures/20261101-200240-livelock-exhausted",
                       1174079, range(0), 1164),
    "senior-12f-1008": (ROOT / "life-098/incident-captures/20261101-200240-livelock-exhausted",
                        1174094, range(0), 1164),
    "senior-12f-search": (ROOT / "life-098/incident-captures/20261101-200240-livelock-exhausted",
                          1176550, range(8091, 8092), 1164),
}
ROW_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")


def _board(root: Path, turn: int) -> dict:
    data = _members((root / "snapshots" / "snapshots-current.jsonl.gz").read_bytes())
    for line in data.split(b"\n"):
        try:
            board = json.loads(line)
        except ValueError:
            continue
        if board.get("type") == "player_turn" and board.get("turn") == turn:
            return board
    raise LookupError(turn)


def _rows(root: Path, sequences) -> list:
    rows = []
    with open(root / "decision-tail.jsonl", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("decision_sequence") in sequences:
                rows.append({name: row.get(name) for name in ROW_FIELDS})
    return rows


def _state(root: Path, turn: int) -> dict:
    state = json.loads((root / "policy-state.json").read_text(encoding="utf-8"))["state"]
    absorbed = {(key if ":" in key else f"staff:{key}"): count
                for key, count in state["_me_staff_sequence"]["absorbed"].items()}
    floor = state["_me_power_floor"]
    return {"absorbed": absorbed, "floor": floor["floor"],
            "uses": [use for use in floor["uses"] if use["turn"] < turn]}


def main() -> None:
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    cases, seen = {}, set()
    for name, (root, turn, sequences, target) in CASES.items():
        board = _board(root, turn)
        seen |= {target} | {monster["race_id"] for monster in
                            board["visible_monsters"] + board["detected_monsters"]}
        cases[name] = {"source": str(root), "board": board, "rows": _rows(root, sequences),
                       "target": target, **_state(root, turn)}
    data = {"cases": cases,
            "monraces": {str(race): asdict(races[race]) for race in sorted(seen) if race in races}}
    FIXTURE.parent.mkdir(exist_ok=True)
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, default=sorted)
    print(FIXTURE, FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
