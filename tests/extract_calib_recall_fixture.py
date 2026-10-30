"""Freeze the D38 recorded inputs (n1-b life-276, viewing server, 2026-10-31).

Sources (read-only copies from ``~/hengbot-soak/n1-b/life-276`` of the viewing
server, taken 07:33 while the life ran on build b6d47db93):
- ``state.jsonl`` (the game's output, UTF-8): zero-based lines 3600-3760 and
  5370-5395 were copied verbatim (``sed -n 3601,3761p`` / ``5371,5396p``) as
  ``state-3600-3760.jsonl`` and ``state-5370-5395.jsonl``.
- ``jsonlog/bot-decisions.jsonl``: the decision rows of turns 742272-744890
  and 757930-758122 (``decisions.jsonl``).
- ``user/bot-test.txt`` (EUC-JP, LF) and ``jsonlog/character-calibration.json``,
  both written 07:31:18 by the periodic dump of turn 758093.

Frozen rows (one JSON document):
- ``skill``: line 3639, the ``~f`` skill list read on arriving in town
  (turn 742591, level 24) by the same process.
- ``town``: lines 3721-3723, the town boards of decisions 18574
  (``town:recall-to-alt-dungeon``, turn 744608), 18575 (Word of Recall on the
  status bar, turn 744615) and 18576.
- ``dump``: lines 5390-5392, the dungeon board of decision 20170
  (``periodic:character-dump``), the game's C response and the board of
  decision 20171 (all turn 758093).
- ``record``: the calibration file that dump wrote.
- ``decisions``: the recorded decision rows 18574-18576 and 20170-20171,
  trimmed to the fields the test reads.

Only this tool reads the copies; the committed test reads the frozen files.
Usage: python tests/extract_calib_recall_fixture.py <copy directory>
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
OUT = FIXTURES / "calib-recall-20261031.json.gz"
DUMP_OUT = FIXTURES / "calib-recall-20261031.bot-test.txt.gz"
RANGES = {3600: "state-3600-3760.jsonl", 5370: "state-5370-5395.jsonl"}
SKILL_LINE = 3639
TOWN_LINES = (3721, 3722, 3723)
DUMP_LINES = (5390, 5391, 5392)
DECISIONS = (18574, 18575, 18576, 20170, 20171)


def _lines(source: Path) -> dict[int, str]:
    lines = {}
    for first, name in RANGES.items():
        with (source / name).open(encoding="utf-8") as stream:
            for offset, line in enumerate(stream):
                lines[first + offset] = line.rstrip("\r\n")
    return lines


def _decision(row: dict) -> dict:
    optimization = row.get("equipment_optimization") or {}
    return {
        "decision_sequence": row["decision_sequence"],
        "turn": row["turn"],
        "reason": row["reason"],
        "key": row["key"],
        "floor_level": (row.get("floor") or {}).get("level"),
        "result_source": optimization.get("result_source"),
        "search_telemetry_freshness": optimization.get("search_telemetry_freshness"),
        "calibration": optimization.get("calibration"),
    }


def main(source: Path) -> None:
    lines = _lines(source)
    rows = {
        "skill": lines[SKILL_LINE],
        "town": [lines[index] for index in TOWN_LINES],
        "dump": [lines[index] for index in DUMP_LINES],
    }
    skill = json.loads(rows["skill"])
    assert skill["type"] == "knowledge" and skill["turn"] == 742591
    assert skill["knowledge"]["category"] == "skill_exp"
    town = [json.loads(line) for line in rows["town"]]
    assert [board["turn"] for board in town] == [744608, 744615, 744624]
    assert [[bar["key"] for bar in board["player"]["status_bar"]] for board in town] == [
        [], ["recall"], ["recall"]]
    dump = [json.loads(line) for line in rows["dump"]]
    assert [(row["type"], row["turn"]) for row in dump] == [
        ("player_turn", 758093), ("character", 758093), ("player_turn", 758093)]
    record = json.loads((source / "character-calibration.json").read_text(encoding="utf-8"))
    assert record["observed_turn"] == 758093
    decisions = {}
    with (source / "decisions.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["decision_sequence"] in DECISIONS and row["decision_sequence"] not in decisions:
                decisions[row["decision_sequence"]] = _decision(row)
    assert sorted(decisions) == list(DECISIONS), sorted(decisions)
    document = dict(rows, record=record,
                    decisions=[decisions[sequence] for sequence in DECISIONS])
    OUT.write_bytes(gzip.compress(
        json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8"), mtime=0))
    raw = (source / "bot-test.txt").read_bytes()
    DUMP_OUT.write_bytes(gzip.compress(raw, mtime=0))
    for path in (OUT, DUMP_OUT):
        print(path.name, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main(Path(sys.argv[1]))
