"""Extract tests/fixtures/dungeon-stops-1103/ from the 2026-11-03 night stops.

Sources, under C:/hengband-backups/pdca/captures/stops-1103-night/ (build
91357d2d0 / e9e2c1262), only this tool reads them:

  n1-c/life-123/incident-captures/20261103-224401-loop-detected
      town-arrival: arrival checkpoint and the first 23 journal rows (the
      first adjacent board is row 21).
  n1-c/life-123/incident-captures/20261103-220751-loop-detected
      the ring's boards of decisions 14580-14590 and the stop's remembered
      terrain (the stop's descent target and path).
  n1-b/life-306/incident-captures/20261103-230451-loop-detected
      every ring board from the floor's arrival (turn 2533971) to the stop.
  n1-a/life-474/incident-captures/20261103-211313-loop-detected
      the ring's boards of decisions 12058-12115, the stop's remembered
      terrain, probed frontiers and visit counts, and the decision rows.

    PYTHONPATH="src;tests;." python tests/extract_dungeon_stops_1103_fixtures.py
"""
import gzip
import json
import lzma
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/stops-1103-night")
TOWN = ROOT / "n1-c/life-123/incident-captures/20261103-224401-loop-detected"
DOOR = ROOT / "n1-c/life-123/incident-captures/20261103-220751-loop-detected"
MAZE = ROOT / "n1-b/life-306/incident-captures/20261103-230451-loop-detected"
CAVE = ROOT / "n1-a/life-474/incident-captures/20261103-211313-loop-detected"
OUTPUT = Path(__file__).with_name("fixtures") / "dungeon-stops-1103"
TERRAIN = ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t",
           "upstairs", "downstairs")
ROW_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")
PRESET = 9 | lzma.PRESET_EXTREME


def write(name: str, data: object) -> None:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    (OUTPUT / name).write_bytes(lzma.compress(payload, preset=PRESET))


def tail_rows(capture: Path, first: int, last: int) -> list[dict]:
    rows = []
    with open(capture / "decision-tail.jsonl", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue  # the tail's first line is cut by its size cap
            if first <= row["decision_sequence"] <= last and row["reason"] != "loop-detected":
                rows.append({name: row[name] for name in ROW_FIELDS})
    return rows


def ring_boards(capture: Path, rows: list[dict]) -> list[dict]:
    """The player-turn boards of ``rows``, one per decision, in order."""
    boards = [row for row in ring_rows((capture / "snapshots/snapshots-current.jsonl.gz").read_bytes())
              if row["type"] == "player_turn"]
    by_turn = {}
    for board in boards:
        by_turn.setdefault(board["turn"], board)
    return [by_turn[row["turn"]] for row in rows]


def state(capture: Path) -> dict:
    return json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))


def town() -> None:
    visit = TOWN / "town-arrival"
    (OUTPUT / "town-melee-policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
    lines = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    (OUTPUT / "town-melee-journal.jsonl.xz").write_bytes(
        lzma.compress(b"".join(lines[:23]), preset=PRESET))


def door() -> None:
    rows = tail_rows(DOOR, 14580, 14590)
    captured = state(DOOR)
    write("descent-door.json.xz", {
        "rows": rows, "boards": ring_boards(DOOR, rows),
        "terrain": {name: captured["terrain"][name] for name in TERRAIN},
        "descent": captured["state"]["_nav_ledger"]["_descent_target"],
    })


def maze() -> None:
    boards = [row for row in ring_rows((MAZE / "snapshots/snapshots-current.jsonl.gz").read_bytes())
              if row["type"] == "player_turn" and row["turn"] >= 2533971]
    write("maze-frontier.json.xz", {
        "boards": boards,
        "rows": tail_rows(MAZE, 25218, 25421),
        "probed": state(MAZE)["state"]["_probed_frontiers"],
    })


def cave() -> None:
    rows = tail_rows(CAVE, 12058, 12115)
    captured = state(CAVE)
    write("cave-stuck.json.xz", {
        "rows": rows, "boards": ring_boards(CAVE, rows),
        "terrain": {name: captured["terrain"][name] for name in TERRAIN},
        "probed": captured["state"]["_probed_frontiers"],
        "visits": captured["state"]["_visit_counts"],
        "searches_before": [row["reason"] for row in tail_rows(CAVE, 12050, 12057)],
    })


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    town()
    door()
    maze()
    cave()
    for path in sorted(OUTPUT.iterdir()):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
