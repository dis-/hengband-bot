"""Extract tests/fixtures/n1c-216-hunt-veto-loop-1117.jsonl.gz.

Source: n1-c life-216 (Lv47 Magic-Eater), Angband 50F, RANDOM quest 40, 2026-11-17, the
automatic loop-detected capture 20261117-024050 and the incident capture 20261117-024047,
copied read-only from the viewing server to C:/hengband-backups/pdca/n1c-216-angband-loop-1117.
Kept: the two boards of the alternation's first round, (33,54) at turn 3873594 and (33,55) at
3873599, their recorded decisions, the retreat vetoes the stop's policy summary held
(``_engagement_avoid_cells``; all of them the engagement claim's own), and the floor memory and
hunt visit of ROOT/replayed-memory-3873591.json: the incident's town-arrival checkpoint replayed
through the captured boards to the turn before the first kept board (its ``source``).

    python tests/extract_n1c_216_hunt_veto_loop_1117_fixture.py
"""
import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/n1c-216-angband-loop-1117")
CAPTURE = ROOT / "20261117-024050-loop-detected"
INCIDENT = ROOT / "incident-20261117-024047-loop-detected"
TARGET = Path(__file__).with_name("fixtures") / "n1c-216-hunt-veto-loop-1117.jsonl.gz"
TURNS = (3873594, 3873599)


def _lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    rows = []
    state = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))["state"]
    rows.append({"role": "vetoes", "cells": state["_engagement_avoid_cells"]})
    memory = json.loads((ROOT / "replayed-memory-3873591.json").read_text(encoding="utf-8"))
    rows.append({"role": "memory", **memory})
    seen = set()
    for board in _lines(CAPTURE / "state.jsonl.gz"):
        if board.get("type") == "player_turn" and board["turn"] in TURNS and board["turn"] not in seen:
            seen.add(board["turn"])
            rows.append({"role": "board", "board": board})
    for record in _lines(CAPTURE / "bot-decisions.jsonl.gz"):
        if record.get("turn") in TURNS:
            rows.append({"role": "decision", "decision": {
                key: record[key] for key in ("turn", "decision_sequence", "reason", "key", "position")}})
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
