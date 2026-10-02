"""Freeze the Angband 24F quest-leave stop of 2026-10-02 18:29:04 (read-only source).

Capture ``autorecover-20261002-182904-exit-no-marker``: the process that
attached at 18:28:18 (fresh policy, decisions 0-329) on Angband 24F, random
quest 41, armed the breeder latch itself at decision 299, walked
``breeder-breakthrough:seek-upstairs`` 299-328 and posted
``breeder-breakthrough:ascend`` '<' at 329; the game asked
「本当にこの階を去りますか？[y/n]」 and the executor stopped (stderr
``<stuck-prompt> ... reason=unowned confirm``).  The state ring keeps the
boards from turn 4041440 (decision 217) to the stop; every retained row is
frozen with the last row index of each decision's board, plus the recorded
(sequence, turn, key, reason, position, visible_hostiles) of 217-329.

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
OUT = FIXTURES / "quest-leave-confirm-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "quest-leave-confirm-20261002.boundaries.json"

CAPTURE = "autorecover-20261002-182904-exit-no-marker"
ATTACH = "2026-10-02T18:28:18"
FIRST, LAST = 217, 329


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


def main() -> None:
    decisions = {
        row["decision_sequence"]: row
        for row in map(json.loads, _gz_lines(LIVE / f"{CAPTURE}.bot-decisions.jsonl.gz"))
        if row.get("decision_sequence") is not None and row["time"] >= ATTACH
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
        assert decision["floor"] == {
            "dungeon_id": 1, "level": 24, "quest_id": 41, "feeling": 5,
        }, sequence
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
                LIVE / f"{CAPTURE}.bot-stderr.log",
            )
        },
        "stderr_stop": (LIVE / f"{CAPTURE}.bot-stderr.log").read_text(
            encoding="utf-8").splitlines()[-1],
        "recorded_fields": [
            "decision_sequence", "turn", "key", "reason", "position",
            "visible_hostiles",
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
