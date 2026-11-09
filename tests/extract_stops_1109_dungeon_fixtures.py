"""Extract tests/fixtures/stops-1109-dungeon/.

Sources: the viewing bots' dungeon loop stops of 2026-11-08/09, copied read-only from the
viewing server (~/hengbot-soak/<inst>/life-NNN/) to
C:/hengband-backups/pdca/captures/stops-1109/dungeon/<inst>_life-NNN_<kind>_<stamp>/:

- ``l1-346``: n1-b life-346 incident-captures/20261108-105147-loop-detected (Angband 18F):
  the snapshot ring snapshots-current, decision-tail.jsonl and policy-state.json.
- ``l1-356``: n1-b life-356 captures/20261109-044429-loop-detected (Yeek cave 5F).
- ``l3-355``: n1-b life-355 captures/20261109-040109-loop-detected (Angband 71F).
- ``l5-173``: n1-c life-173 captures/20261108-211203-loop-detected (dungeon 4, 15F).

Each fixture holds the boards of its turns, their decision rows (turn, sequence, key,
reason, position), the monster knowledge (lib/edit/MonraceDefinitions.jsonc) of every race on
them and the remembered terrain and modes of the stop's policy-state (an incident capture's
own, or for a capture its incident twin's, STATES).

    python tests/extract_stops_1109_dungeon_fixtures.py
"""
import gzip
import json
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge

ROOT = Path("C:/hengband-backups/pdca/captures/stops-1109/dungeon")
OUTPUT = Path(__file__).with_name("fixtures") / "stops-1109-dungeon"
GAME = Path("C:/hengband/lib/edit")
TERRAIN = ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t",
           "upstairs", "downstairs")
# The captures' incident twin, whose policy-state holds the floor's remembered terrain.
STATES = {
    "l1-356": "n1-b_life-356_incident-captures_20261109-044427-loop-detected",
    "l3-355": "n1-b_life-355_incident-captures_20261109-040108-loop-detected",
    "l5-173": "n1-c_life-173_incident-captures_20261108-211201-loop-detected",
}
CASES = {
    # name: (directory, first turn, last turn)
    "l1-346": ("n1-b_life-346_incident-captures_20261108-105147-loop-detected", 1301035, 1301200),
    "l1-356": ("n1-b_life-356_captures_20261109-044429-loop-detected", 0, 1 << 62),
    "l3-355": ("n1-b_life-355_captures_20261109-040109-loop-detected", 0, 1 << 62),
    "l5-173": ("n1-c_life-173_captures_20261108-211203-loop-detected", 0, 1 << 62),
}
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position")


def ring_rows(data: bytes) -> list:
    rows, buf = [], data[data.index(b"\x1f\x8b\x08"):]
    while buf:
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = stream.decompress(buf)
        if not stream.eof:
            break  # the ring was copied while its last member was written
        rows.extend(json.loads(line) for line in out.decode("utf-8").splitlines() if line.strip())
        buf = stream.unused_data
    return rows


def lines(path: Path) -> list:
    opener = gzip.open if path.suffix == ".gz" else open
    rows = []
    with opener(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass  # the tail's first line is cut
    return rows


def extract(name: str, directory: str, first: int, last: int, races: dict) -> None:
    source = ROOT / directory
    incident = (source / "policy-state.json").is_file()
    if incident:
        boards = ring_rows((source / "snapshots" / "snapshots-current.jsonl.gz").read_bytes())
        decisions = lines(source / "decision-tail.jsonl")
    else:
        boards = lines(source / "state.jsonl.gz")
        decisions = lines(source / "bot-decisions.jsonl.gz")
    boards = [board for board in boards
              if board.get("type") == "player_turn" and first <= board["turn"] <= last]
    turns = {board["turn"] for board in boards}
    fixture = {
        "boards": boards,
        "decisions": [{field: row.get(field) for field in DECISION_FIELDS}
                      for row in decisions
                      if row.get("turn") in turns and row.get("reason") != "loop-detected"],
    }
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for row in board.get(field, [])}
    fixture["monraces"] = {key: asdict(races[key]) for key in sorted(ids)}
    state_path = (ROOT / STATES[name] if name in STATES else source) / "policy-state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        fixture["terrain"] = {key: state["terrain"][key] for key in TERRAIN}
        fixture["state"] = {key: state["state"].get(key) for key in ("_breeder_breakthrough_floor",)}
        fixture["modes"] = {key: state["modes_and_latches"].get(key) for key in (
            "_fundraising_mode", "_crossarea_fundraising_enforced", "_status_threat_latch")}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(json.dumps(fixture, ensure_ascii=False, default=sorted,
                                       separators=(",", ":")).encode("utf-8"), mtime=0)
    (OUTPUT / f"{name}.json.gz").write_bytes(payload)
    print(name, len(boards), len(fixture["decisions"]), len(payload))


def main() -> None:
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    for name, (directory, first, last) in CASES.items():
        extract(name, directory, first, last, races)


if __name__ == "__main__":
    main()
