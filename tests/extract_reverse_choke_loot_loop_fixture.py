"""Freeze the 2026-10-03 11:11 reverse-choke / seek-loot alternation (Forest 32F).

Sources (read-only):

- decisions: the loop-detected capture
  ``C:/hengband-backups/state-logs/loop-reverse-choke-loot-20261003-1111/
  autorecover-20261003-111136-loop-detected.bot-decisions.jsonl.gz``
  (decisions 4552-4809 of the process, plus the loop-detected stop row).
- boards: ``C:/hengband-backups/state-logs/
  loop-reverse-choke-loot-20261003-1111-live-state-lines/
  bot-state-fixed.lines-5697-5862-6886.jsonl``.  The capture's own state
  file starts at decision 4696, after the retreat was armed, and the policy's
  floor terrain memory needs every board since the floor was entered (turn
  6182671), so these rows were copied from the live
  jsonlog/bot-state-fixed.jsonl at 11:19, before that log was rotated at
  11:27 (line endings normalized to LF; see the README beside it):
  line 1 is source line index 5697, the character's skill_exp knowledge row
  (turn 6179627, the town stay just before this floor); the rest are source
  line indices 5862-6886, every row from the arrival on Forest 32F to the
  loop stop.
- calibration: ``character-calibration.copied-1116.json`` beside them,
  jsonlog/character-calibration.json as copied at 11:16 (observed turn
  6214004, the closest observation to the incident; the file as read before
  the incident had already been overwritten).

Each decision's input is the last player_turn row carrying the decision's
turn.  Warm-up rows are the last player_turn row of every turn from the floor
arrival up to the first recorded decision (the earlier decisions of the
process were rotated out of the decision log).  Decision inputs end at
``LAST_INPUT``, the first board on which the fixed policy diverges from the
recording (R4).

Only this tool reads the sources; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = Path(
    "C:/hengband-backups/state-logs/loop-reverse-choke-loot-20261003-1111/"
    "autorecover-20261003-111136-loop-detected.bot-decisions.jsonl.gz"
)
CAPTURE_SHA256 = "87769b1269d26ab3e745992d6d218da2be559b5106b9077f5078265847856545"
LINES = Path(
    "C:/hengband-backups/state-logs/"
    "loop-reverse-choke-loot-20261003-1111-live-state-lines"
)
STATE = LINES / "bot-state-fixed.lines-5697-5862-6886.jsonl"
STATE_SHA256 = "7d1dc8b39424bcce9db986a6bc72df0ccef448bf831f6d127edd9ae6487c0acb"
CALIBRATION_SOURCE = LINES / "character-calibration.copied-1116.json"
CALIBRATION_SHA256 = "61e65792bcfbc8322382675295eb033823b30e20623d808dd87e7ced60e74594"
FIRST_DECISION = 4552
LAST_INPUT = 4775
STEM = "reverse-choke-loot-loop-20261003"
FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT = FIXTURES / f"{STEM}.jsonl.gz"
RECORDED = FIXTURES / f"{STEM}.recorded.json"
CALIBRATION = FIXTURES / f"{STEM}.character-calibration.json"


def main() -> None:
    for path, digest in (
        (CAPTURE, CAPTURE_SHA256),
        (STATE, STATE_SHA256),
        (CALIBRATION_SOURCE, CALIBRATION_SHA256),
    ):
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"{path} changed since extraction")
    with STATE.open(encoding="utf-8", newline="") as stream:
        knowledge, *floor = stream.read().splitlines(keepends=True)
    knowledge_row = json.loads(knowledge)
    assert knowledge_row["type"] == "knowledge"
    assert knowledge_row["knowledge"]["category"] == "skill_exp"

    with gzip.open(CAPTURE, "rt", encoding="utf-8") as stream:
        decisions = [json.loads(line) for line in stream]
    stop = decisions[-1]
    assert stop["reason"] == "loop-detected"
    decisions = decisions[:-1]
    assert [row["decision_sequence"] for row in decisions] == list(
        range(FIRST_DECISION, FIRST_DECISION + len(decisions)))

    rows = [(json.loads(line), line.rstrip("\r\n")) for line in floor]
    turn_rows = [(row, line) for row, line in rows if row.get("type") == "player_turn"]
    last_of_turn: dict[int, str] = {}
    for row, line in turn_rows:
        last_of_turn[row["turn"]] = line
    first_turn = decisions[0]["turn"]
    records = [{"role": "skill-knowledge", "line": knowledge.rstrip("\r\n")}]
    records += [
        {"role": "warm-up", "turn": turn, "line": last_of_turn[turn]}
        for turn in sorted(last_of_turn) if turn < first_turn
    ]
    for row in decisions:
        if row["decision_sequence"] > LAST_INPUT:
            break
        records.append({
            "role": "decision-input",
            "sequence": row["decision_sequence"],
            "line": last_of_turn[row["turn"]],
        })
    payload = "".join(
        json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    OUTPUT.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))

    recorded = {
        "source": f"{CAPTURE.name} + {STATE.name}",
        "recorded_fields": [
            "decision_sequence", "turn", "key", "reason", "position",
            "visible_hostiles", "hp", "loot_target", "claim_owner", "messages",
        ],
        "recorded": [
            [
                row["decision_sequence"], row["turn"], row["key"], row["reason"],
                [row["position"]["y"], row["position"]["x"]],
                row["visible_hostiles"], row["player"]["hp"],
                None if (row.get("loot") or {}).get("target") is None else [
                    row["loot"]["target"]["y"], row["loot"]["target"]["x"]],
                (row.get("claim") or {}).get("owner"),
                row.get("messages") or [],
            ]
            for row in decisions
        ],
        "stop": {
            "reason": stop["reason"], "turn": stop["turn"],
            "position": [stop["position"]["y"], stop["position"]["x"]],
        },
    }
    RECORDED.write_text(
        json.dumps(recorded, ensure_ascii=True, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    CALIBRATION.write_bytes(
        CALIBRATION_SOURCE.read_bytes().replace(b"\r\n", b"\n"))
    for path in (OUTPUT, RECORDED, CALIBRATION):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
