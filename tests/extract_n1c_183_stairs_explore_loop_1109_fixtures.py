"""Extract tests/fixtures/n1c-183-stairs-explore-loop-1109/.

Sources: n1-c life-183's loop stops on Angband 49F of 2026-11-09, copied read-only from the
viewing server (~/hengbot-soak/n1-c/life-183/) to
C:/hengband-backups/pdca/captures/n1c-183-loop-1109/:

- ``stairs-2033``: incident-captures/20261109-203345-loop-detected (build b078e0b34): the
  snapshot ring snapshots-current (boards and the ~f ``knowledge`` responses from 2948290,
  before the 古代レッド・ドラゴン was shown, to the stop), its policy-state.json, and the
  decision rows of captures/20261109-203348-loop-detected.
- ``loot-2230``: n1-c life-184 captures/20261109-223004-loop-detected (build b4dec292b,
  dungeon 3 18F) state.jsonl and decisions, with the remembered terrain of its incident twin
  incident-captures/20261109-223002-loop-detected.
- ``secret-2311``: n1-c life-185 captures/20261109-231142-loop-detected (build b91cbafef,
  Yeek cave 13F) state.jsonl and decisions, with the remembered terrain of its incident twin.
- ``chest-2045``: captures/20261109-204524-loop-detected (build 2ea922e5b) state.jsonl and
  decisions, with the remembered terrain of its incident twin
  incident-captures/20261109-204520-loop-detected.

Each fixture holds its rows (boards and knowledge responses, in order), the decision rows
(turn, sequence, key, reason, position), the monster knowledge
(lib/edit/MonraceDefinitions.jsonc) of every race on the boards and the stop's remembered
terrain.

    python tests/extract_n1c_183_stairs_explore_loop_1109_fixtures.py
"""
import gzip
import json
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-183-loop-1109")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-183-stairs-explore-loop-1109"
GAME = Path("C:/hengband/lib/edit")
TERRAIN = ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t",
           "upstairs", "downstairs")
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
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def write(name: str, rows: list, decisions: list, state_dir: Path, races: dict) -> None:
    turns = {row["turn"] for row in rows if row.get("type") == "player_turn"}
    ids = {monster["race_id"] for row in rows
           for field in ("visible_monsters", "detected_monsters") for monster in row.get(field, [])}
    state = json.loads((state_dir / "policy-state.json").read_text(encoding="utf-8"))
    fixture = {
        "rows": rows,
        "decisions": [{field: row.get(field) for field in DECISION_FIELDS}
                      for row in decisions
                      if row.get("turn") in turns and row.get("reason") != "loop-detected"],
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
        "terrain": {key: state["terrain"][key] for key in TERRAIN},
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(json.dumps(fixture, ensure_ascii=False, default=sorted,
                                       separators=(",", ":")).encode("utf-8"), mtime=0)
    (OUTPUT / f"{name}.json.gz").write_bytes(payload)
    print(name, len(rows), len(fixture["decisions"]), len(payload))


def main() -> None:
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    incident = ROOT / "incident-20261109-203345"
    rows = [row for row in ring_rows(
        (incident / "snapshots" / "snapshots-current.jsonl.gz").read_bytes())
        if row.get("type") in {"player_turn", "knowledge"} and row.get("turn", 0) >= 2948290]
    write("stairs-2033", rows,
          lines(ROOT / "20261109-203348-loop-detected" / "bot-decisions.jsonl.gz"),
          ROOT / "incident-small", races)
    capture = ROOT / "20261109-204524-loop-detected"
    rows = [row for row in lines(capture / "state.jsonl.gz")
            if row.get("type") in {"player_turn", "knowledge"}]
    write("chest-2045", rows, lines(capture / "bot-decisions.jsonl.gz"),
          ROOT / "incident-small-20261109-204520", races)
    capture = ROOT / "n1c-185-20261109-231142"
    rows = [row for row in lines(capture / "state.jsonl.gz")
            if row.get("type") in {"player_turn", "knowledge"}]
    write("secret-2311", rows, lines(capture / "bot-decisions.jsonl.gz"),
          ROOT / "incident-small-185-2311", races)
    capture = ROOT / "n1c-184-20261109-223004"
    rows = [row for row in lines(capture / "state.jsonl.gz")
            if row.get("type") in {"player_turn", "knowledge"}]
    write("loot-2230", rows, lines(capture / "bot-decisions.jsonl.gz"),
          ROOT / "incident-small-184-223002", races)


if __name__ == "__main__":
    main()
