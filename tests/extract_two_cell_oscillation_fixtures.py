"""Freeze the three Castle 20F two-cell alternations of 2026-10-02 (read-only sources).

(a) 13:03:46-48 ``breakout:least-visited`` '2'/'8' between (30,15)/(31,15).
    No board of this window survives: the capture rings of 13:12 start at
    turn 3644500 and the live ``bot-state-fixed.jsonl`` was truncated by the
    15:0x game relaunch (first turn 3727603).  Only the decision rows remain
    (``jsonlog/bot-decisions.jsonl.1``, decisions 3463-3590); their recorded
    (sequence, turn, key, reason, position) are frozen here.
(b) 13:12:06-24 ``breeder-breakthrough:seek-frontier`` with non-breeders
    adjacent: capture ``autorecover-20261002-131232-loop-detected``.  The
    boards of decisions 5610-5647 (every drained row, the fire-target prompts
    drain three) are frozen with the last row index of each decision.
(c) 15:14-15:16 ``summoner:retreat`` '3' / ``seek-loot`` '7': capture
    ``autorecover-20261002-151537-loop-detected``.  That process attached at
    15:14:3x; its ``skill_exp`` knowledge row (state row 1) and the boards of
    its decisions 1-3 are frozen, plus the recorded rows of decisions 1-84.

Only this tool reads the captures; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path("C:/hengband/bot-client/jsonlog")
FIXTURES = ROOT / "tests" / "fixtures"
OUT = FIXTURES / "two-cell-oscillation-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "two-cell-oscillation-20261002.boundaries.json"

A_LOG = LIVE / "bot-decisions.jsonl.1"
A_FIRST, A_LAST = 3463, 3590
B_CAPTURE = "autorecover-20261002-131232-loop-detected"
B_FIRST, B_LAST = 5610, 5698
B_BOARDS_LAST = 5647
C_CAPTURE = "autorecover-20261002-151537-loop-detected"
C_ATTACH = "2026-10-02T15:14:3"  # the process that attached after 15:14:34
C_FIRST, C_LAST = 1, 84
C_BOARDS_LAST = 3


def _gz_lines(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return stream.read().splitlines(keepends=True)


def _row(decision: dict) -> list:
    return [
        decision["decision_sequence"], decision["turn"], decision["key"],
        decision["reason"],
        [decision["position"]["y"], decision["position"]["x"]],
        decision.get("visible_hostiles"),
    ]


def _a_rows() -> list[list]:
    rows = []
    with A_LOG.open("r", encoding="utf-8") as stream:
        for line in stream:
            if '"time": "2026-10-02T13:0' not in line[:40]:
                continue
            decision = json.loads(line)
            if A_FIRST <= decision["decision_sequence"] <= A_LAST:
                assert decision["floor"]["dungeon_id"] == 12
                assert decision["floor"]["level"] == 20
                rows.append(_row(decision))
    assert [row[0] for row in rows] == list(range(A_FIRST, A_LAST + 1))
    return rows


def _boards(capture: str, first: int, boards_last: int, last: int, *,
            time_floor: str = "") -> tuple[list[list], list[str], dict]:
    decisions = {
        row["decision_sequence"]: row
        for row in map(json.loads, _gz_lines(LIVE / f"{capture}.bot-decisions.jsonl.gz"))
        if row.get("decision_sequence") is not None
        and row["reason"] != "loop-detected"
        and row["time"] >= time_floor
    }
    states = _gz_lines(LIVE / f"{capture}.bot-state-fixed.jsonl.gz")
    by_turn = {}
    for index, line in enumerate(states):
        state = json.loads(line)
        if state.get("type") == "player_turn":
            by_turn[state["turn"]] = index
    recorded = [_row(decisions[sequence]) for sequence in range(first, last + 1)]
    ends = {}
    for sequence in range(first, boards_last + 1):
        decision = decisions[sequence]
        index = by_turn[decision["turn"]]
        board = json.loads(states[index])
        assert (board["player"]["y"], board["player"]["x"]) == (
            decision["position"]["y"], decision["position"]["x"]
        ), sequence
        ends[sequence] = index
    start = 0 if time_floor else ends[first] - (
        int(decisions[first]["timing"]["jsonl_drain_records"]) - 1
    )
    kept = [line.replace("\r\n", "\n") for line in states[start: ends[boards_last] + 1]]
    return recorded, kept, {str(k): v - start for k, v in ends.items()}


def main() -> None:
    a_rows = _a_rows()
    b_recorded, b_lines, b_ends = _boards(B_CAPTURE, B_FIRST, B_BOARDS_LAST, B_LAST)
    c_recorded, c_lines, c_ends = _boards(
        C_CAPTURE, C_FIRST, C_BOARDS_LAST, C_LAST, time_floor=C_ATTACH
    )
    knowledge = json.loads(c_lines[1])
    assert knowledge["type"] == "knowledge"
    assert knowledge["knowledge"]["category"] == "skill_exp"
    records = (
        [{"role": "b", "line": line} for line in b_lines]
        + [{"role": "c", "line": line} for line in c_lines]
    )
    payload = "".join(
        json.dumps(record, ensure_ascii=False) + "\n" for record in records
    )
    OUT.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    boundaries = {
        "source": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                LIVE / f"{B_CAPTURE}.bot-decisions.jsonl.gz",
                LIVE / f"{B_CAPTURE}.bot-state-fixed.jsonl.gz",
                LIVE / f"{C_CAPTURE}.bot-decisions.jsonl.gz",
                LIVE / f"{C_CAPTURE}.bot-state-fixed.jsonl.gz",
            )
        },
        "a_source": f"{A_LOG.name} decisions {A_FIRST}-{A_LAST} (no board retained)",
        "recorded_fields": [
            "decision_sequence", "turn", "key", "reason", "position",
            "visible_hostiles",
        ],
        "a_recorded": a_rows,
        "b_recorded": b_recorded,
        "b_board_end": b_ends,
        "c_recorded": c_recorded,
        "c_board_end": c_ends,
        "c_knowledge_row": 1,
    }
    BOUNDARIES.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    for path in (OUT, BOUNDARIES):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
