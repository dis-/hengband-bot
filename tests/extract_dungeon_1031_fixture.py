"""Freeze the 2026-10-31 dungeon death and loop boards of #47 (fix-dungeon-1031).

Sources (read-only, C:/hengband-backups/pdca/captures/latest-12h-1031):

- death-return / death-blind: n1-a life-446, incident capture
  20261031-060729-player-death (copied from the viewing server).  The ring's
  player_turn boards of turns 1712380..1712419 (the second emergency escape
  latches the town return at 1712410; the summoner avoidance then explores)
  and 1713388..1713414 (blinded at 1713414; unseen-recall walks).
- q22-sweep: n1-a life-447 captures/20261031-075341-loop-detected, state rows
  85..99 (quest-strategy:sweep-engage-mobile alternating '6'/'4').
- angband-1f: n1-c life-055 captures/20261031-081258-loop-detected (copied
  from the viewing server), state rows 0..2 (鉄獄1階, the return searches walls
  instead of reading Recall) and captures/20261031-081315-loop-detected's last
  row (standing on the 1F stair in the dark).
- wilderness: n1-c life-059 captures/20261031-090148-loop-detected, state rows
  99..103 (鉄獄2階: the walk to the up shaft at [5,62], '<', the wilderness
  arrival) and 141..143 (the refused global map after the teleport).

Each case keeps the boards and the recorded decision rows of the same turns.
The snapshot ring copy is the tail of a multi-member gzip: decoding starts at
the first member header and keeps whole members only.  Only this extraction
tool reads the captures; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/latest-12h-1031")
OUTPUT = Path(__file__).with_name("fixtures") / "dungeon-1031.json.gz"
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tail_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    return rows


def gz_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def decisions_by_turn(rows: list[dict]) -> dict[int, dict]:
    by_turn: dict[int, dict] = {}
    for row in rows:
        if "turn" in row and row.get("reason") not in (None, "loop-detected"):
            by_turn.setdefault(row["turn"],
                               {field: row.get(field) for field in DECISION_FIELDS})
    return by_turn


def ring_case(capture: Path, first: int, last: int) -> dict:
    ring = capture / "snapshots" / "snapshots-current.jsonl.gz"
    tail = capture / "decision-tail.jsonl"
    boards = sorted(
        (row for row in ring_rows(ring.read_bytes())
         if row.get("type") == "player_turn" and first <= row["turn"] <= last),
        key=lambda row: row["turn"],
    )
    decisions = decisions_by_turn(tail_rows(tail))
    return dict(
        source=str(capture.relative_to(ROOT)).replace("\\", "/"),
        sources={ring.name: sha(ring), tail.name: sha(tail)},
        boards=boards,
        decisions=[decisions.get(board["turn"]) for board in boards],
    )


def state_case(capture: Path, rows: list[int]) -> dict:
    state = capture / "state.jsonl.gz"
    decision_path = capture / "bot-decisions.jsonl.gz"
    states = [row for row in gz_rows(state) if row.get("type") == "player_turn"]
    decisions = decisions_by_turn(gz_rows(decision_path))
    boards = [states[index] for index in rows]
    return dict(
        source=str(capture.relative_to(ROOT)).replace("\\", "/"),
        sources={state.name: sha(state), decision_path.name: sha(decision_path)},
        rows=rows,
        boards=boards,
        decisions=[decisions.get(board["turn"]) for board in boards],
    )


def main():
    death = ROOT / "n1-a/life-446/incident-captures/20261031-060729-player-death"
    cases = {
        "death-return": ring_case(death, 1712380, 1712419),
        "death-blind": ring_case(death, 1713388, 1713414),
        "q22-sweep": state_case(
            ROOT / "n1-a/life-447/captures/20261031-075341-loop-detected",
            list(range(85, 100))),
        "angband-1f-lit": state_case(
            ROOT / "n1-c/life-055/captures/20261031-081258-loop-detected", [0, 1, 2]),
        "angband-1f-dark": state_case(
            ROOT / "n1-c/life-055/captures/20261031-081315-loop-detected", [114]),
        "wilderness-shaft": state_case(
            ROOT / "n1-c/life-059/captures/20261031-090148-loop-detected",
            [99, 100, 101, 102, 103]),
        "wilderness-refused": state_case(
            ROOT / "n1-c/life-059/captures/20261031-090148-loop-detected",
            [141, 142, 143]),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
