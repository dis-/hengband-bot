"""Freeze the Angband 24F loot-suppression window of 2026-10-02 18:27 (read-only source).

Capture ``autorecover-20261002-182813-exit-no-marker``: the process (session
35788, attached 18:12:30) that posted ``emergency:teleport`` at decision 6521
on Angband 24F, random quest 41, and never chose ``seek-loot`` again on that
floor (ownership-claims decision 6524: suspended floor-loot claim closed
``loot-suppressed:emergency-return``).  Its state ring keeps the boards from
turn 4038390 (decision 6995) to the stop at 7108; every retained row is frozen
with the last row index of each decision's board, plus the recorded
(sequence, turn, key, reason, position, visible_hostiles, visible_loot) of
6995-7108.

Only this tool reads the capture; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path("C:/hengband/bot-client/jsonlog")
FIXTURES = ROOT / "tests" / "fixtures"
OUT = FIXTURES / "loot-suppression-quest-floor-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "loot-suppression-quest-floor-20261002.boundaries.json"

CAPTURE = "autorecover-20261002-182813-exit-no-marker"
FIRST, LAST = 6995, 7108


def _gz_lines(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return stream.read().splitlines(keepends=True)


def _row(decision: dict) -> list:
    hostiles = decision.get("visible_hostiles")
    return [
        decision["decision_sequence"], decision["turn"], decision["key"],
        decision["reason"],
        [decision["position"]["y"], decision["position"]["x"]],
        len(hostiles) if isinstance(hostiles, list) else hostiles,
        [[cell["position"]["y"], cell["position"]["x"]]
         for cell in decision["loot"]["visible"]],
    ]


def main() -> None:
    decisions = {
        row["decision_sequence"]: row
        for row in map(json.loads, _gz_lines(LIVE / f"{CAPTURE}.bot-decisions.jsonl.gz"))
        if row.get("decision_sequence") is not None
    }
    states = _gz_lines(LIVE / f"{CAPTURE}.bot-state-fixed.jsonl.gz")
    by_turn = {}
    for index, line in enumerate(states):
        state = json.loads(line)
        assert state.get("type") == "player_turn"
        by_turn[state["turn"]] = index
    recorded = [_row(decisions[sequence]) for sequence in range(FIRST, LAST + 1)]
    ends = {}
    for sequence in range(FIRST, LAST + 1):
        decision = decisions[sequence]
        assert decision["floor"]["dungeon_id"] == 1, sequence
        assert decision["floor"]["level"] == 24, sequence
        assert decision["floor"]["quest_id"] == 41, sequence
        index = by_turn[decision["turn"]]
        board = json.loads(states[index])
        assert (board["player"]["y"], board["player"]["x"]) == (
            decision["position"]["y"], decision["position"]["x"]
        ), sequence
        ends[str(sequence)] = index
    assert ends[str(FIRST)] == 0
    kept = [line.replace("\r\n", "\n") for line in states[: ends[str(LAST)] + 1]]
    payload = "".join(
        json.dumps({"line": line}, ensure_ascii=False) + "\n" for line in kept
    )
    OUT.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    boundaries = {
        "source": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                LIVE / f"{CAPTURE}.bot-decisions.jsonl.gz",
                LIVE / f"{CAPTURE}.bot-state-fixed.jsonl.gz",
            )
        },
        "recorded_fields": [
            "decision_sequence", "turn", "key", "reason", "position",
            "visible_hostiles", "visible_loot",
        ],
        "recorded": recorded,
        "board_end": ends,
    }
    BOUNDARIES.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    for path in (OUT, BOUNDARIES):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
