"""Freeze the #47 dual-wield inputs (n1-c lives 077 and 086, 2026-11-01).

Sources (read-only gzip copies of the viewing server's
``~/hengbot-soak/n1-c/life-NNN/state.jsonl`` and ``jsonlog/bot-decisions.jsonl``,
taken 11:53 into ``<copies>/life-NNN/{state,bot-decisions}.jsonl.gz``; the
life-077 dump ``user/bot_test2.txt`` (EUC-JP), written 03:24 by the periodic
dump of turn 440550, copied from the fix-deaths-1101 capture as
``<copies>/life-077/bot_test2.txt``).

Frozen rows (zero-based ``state.jsonl`` lines, verbatim):
- ``life077``: line 3, the Home list the third process read (turn 352640;
  it made no Home operation afterwards); line 1138, the ``~f`` skill list
  (turn 437039); line 1139, the town board after it; line 1368, the board of
  the periodic dump (turn 440550); line 1369, the game's ``C`` response;
  line 1370, the board after the dump.  Decisions: the dump row and its
  successor (turn 440550).
- ``life086``: line 951, the last Home list before the swap (turn 86255);
  lines 1709-1712, the dungeon boards of the digger swap (turns
  270754-270782); line 1931, the ``~f`` skill list (turn 287399); lines
  1929, 1930 and 1932-1933, the town boards of the restore (turns
  287399-287413).  Decisions: turns 270754-270782 and 287398-287426.

Only this tool reads the copies; the committed test reads the frozen files.
Usage: python tests/extract_me_dual_wield_fixture.py <copies>
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
OUT = FIXTURES / "me-dual-wield-20261101.json.gz"
DUMP_OUT = FIXTURES / "me-dual-wield-20261101.bot-test2.txt.gz"
LIFE077 = {"home": 3, "skill": 1138, "town": 1139, "before_dump": 1368,
           "character": 1369, "after_dump": 1370}
LIFE086 = {"home": 951, "skill": 1931}
LIFE086_MINE = (1709, 1710, 1711, 1712)
LIFE086_TOWN = (1929, 1930, 1932, 1933)
DECISION_TURNS = {"life-077": ((440550, 440550),),
                  "life-086": ((270754, 270782), (287398, 287426))}


def _state_lines(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [line.rstrip("\r\n") for line in stream]


def _decision(row: dict) -> dict:
    optimization = row.get("equipment_optimization") or {}
    return {
        "decision_sequence": row["decision_sequence"], "turn": row["turn"],
        "reason": row["reason"], "key": row["key"],
        "messages": row.get("messages") or [],
        "calibration": optimization.get("calibration"),
    }


def _decisions(path: Path, ranges) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if "decision_sequence" not in row:  # a session-start row
                continue
            if any(first <= row["turn"] <= last for first, last in ranges):
                rows.append(_decision(row))
    return rows


def main(copies: Path) -> None:
    life077 = _state_lines(copies / "life-077" / "state.jsonl.gz")
    life086 = _state_lines(copies / "life-086" / "state.jsonl.gz")
    document = {
        "life077": {name: life077[index] for name, index in LIFE077.items()},
        "life086": dict({name: life086[index] for name, index in LIFE086.items()},
                        mine=[life086[index] for index in LIFE086_MINE],
                        town=[life086[index] for index in LIFE086_TOWN]),
    }
    character = json.loads(document["life077"]["character"])
    assert (character["type"], character["turn"]) == ("character", 440550)
    assert json.loads(document["life077"]["skill"])["knowledge"]["category"] == "skill_exp"
    assert json.loads(document["life077"]["home"])["knowledge"]["category"] == "home"
    assert [json.loads(line)["turn"] for line in document["life086"]["mine"]] == [
        270754, 270760, 270770, 270782]
    assert [json.loads(line)["turn"] for line in document["life086"]["town"]] == [
        287399, 287399, 287399, 287413]
    for life, ranges in DECISION_TURNS.items():
        key = life.replace("-", "")
        document[key]["decisions"] = _decisions(
            copies / life / "bot-decisions.jsonl.gz", ranges)
    OUT.write_bytes(gzip.compress(
        json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8"), mtime=0))
    DUMP_OUT.write_bytes(gzip.compress(
        (copies / "life-077" / "bot_test2.txt").read_bytes(), mtime=0))
    for path in (OUT, DUMP_OUT):
        print(path.name, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main(Path(sys.argv[1]))
