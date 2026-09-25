"""Freeze the 2026-09-26 01:57 pile-pickup stuck-prompt stop.

Sources (read-only):
- jsonlog/incident-20260926-0157-pickup-prompt-unrecognized.state.jsonl.gz,
  .decisions.jsonl.gz and .stderr.log (copies of the live logs taken at the
  stop);
- incident-captures/20260926-015751-stuck-prompt/decision-tail.jsonl (the
  automatic capture).

The stop decision is decision_sequence 281 (``conquest:pickup`` 'gaa', turn
5782217) and it is the last row of both decision sources; the tool checks the
two rows are equal, and equal to the previous decision (280, the step onto
the pile) as well.  The state log's last three rows are the boards of 280
(turn 5782212), of 281 (turn 5782217, the compose board) and the command
boundary the game reached after the pickup (turn 5782222): a ``player_turn``
row is written at the next command read, before the trailing key of the
posted macro was consumed.  Each board must carry its decision's recorded
turn and position; the tool fails otherwise.

Frozen records (one JSON object per line, gzip, mtime 0):
  role "board": ``previous`` (decision 280's board), ``compose`` (decision
      281's board) and ``after`` (the command boundary after 'ga');
  role "decision": the recorded facts of decisions 280 and 281;
  role "stop": the stderr line the driver printed;
  role "skill-knowledge": the state log's latest ``~f`` skill list (turn
      5780207), so a replayed policy does not spend the compose board on the
      periodic probe.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "incident-20260926-0157-pickup-prompt-unrecognized"
LIVE = next(
    candidate
    for candidate in (ROOT / "jsonlog", Path("C:/hengband/bot-client/jsonlog"))
    if (candidate / f"{CAPTURE_NAME}.state.jsonl.gz").is_file()
)
STATE = LIVE / f"{CAPTURE_NAME}.state.jsonl.gz"
DECISIONS = LIVE / f"{CAPTURE_NAME}.decisions.jsonl.gz"
STDERR = LIVE / f"{CAPTURE_NAME}.stderr.log"
AUTOMATIC = LIVE.parent / "incident-captures" / "20260926-015751-stuck-prompt"
TAIL = AUTOMATIC / "decision-tail.jsonl"
OUTPUT = ROOT / "tests" / "fixtures" / "pickup-pile-prompt-20260926.jsonl.gz"
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
STOP_SEQUENCE = 281
DECISION_FIELDS = (
    "time", "decision_sequence", "turn", "key", "reason", "position",
    "messages", "inventory", "floor", "claim",
)


def main() -> None:
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        decisions = [json.loads(line) for line in stream]
    # The capture keeps the last bytes of the log: its first line may be the
    # cut remainder of a row and is not compared.
    tail_lines = TAIL.read_text(encoding="utf-8").splitlines()[1:]
    tail = [json.loads(line) for line in tail_lines]
    tail = [row for row in tail if "decision_sequence" in row]
    if decisions[-2:] != tail[-2:]:
        raise RuntimeError("the incident decisions differ from the capture tail")
    previous, stop = decisions[-2:]
    if (stop["decision_sequence"], stop["key"], stop["reason"]) != (
        STOP_SEQUENCE, "gaa", "conquest:pickup"
    ):
        raise RuntimeError("the last decision is not the recorded pickup")
    with gzip.open(STATE, "rb") as stream:
        lines = stream.read().splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    boards = {"previous": rows[-3], "compose": rows[-2], "after": rows[-1]}
    for name, decision in (("previous", previous), ("compose", stop)):
        board = boards[name]
        if board.get("turn") != decision["turn"] or (
            board["player"]["y"], board["player"]["x"]
        ) != (decision["position"]["y"], decision["position"]["x"]):
            raise RuntimeError(f"the {name} board is not its decision's board")
    after = boards["after"]
    if after["turn"] <= stop["turn"] or (
        after["player"]["y"], after["player"]["x"]
    ) != (stop["position"]["y"], stop["position"]["x"]):
        raise RuntimeError("the after board is not the post-pickup boundary")
    stderr = STDERR.read_text(encoding="utf-8").strip()
    if not stderr.startswith("<stuck-prompt> owner=conquest:pickup"):
        raise RuntimeError("stderr is not the recorded stop")
    records = [
        {"role": "board", "name": name, "board": board}
        for name, board in boards.items()
    ]
    records += [
        {
            "role": "decision",
            "decision": {field: row.get(field) for field in DECISION_FIELDS},
        }
        for row in (previous, stop)
    ]
    records.append({"role": "stop", "stderr": stderr})
    skill = [
        row for row in rows
        if row.get("type") == "knowledge"
        and (row.get("knowledge") or {}).get("category") == "skill_exp"
    ][-1]
    if skill["turn"] >= previous["turn"]:
        raise RuntimeError("the skill list is not older than the boards")
    records.append({"role": "skill-knowledge", "board": skill})
    payload = "".join(
        json.dumps(record, ensure_ascii=False) + "\n" for record in records
    ).encode("utf-8")
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    PROVENANCE.write_text(
        f"Source: jsonlog/{CAPTURE_NAME}.state.jsonl.gz (last three rows, "
        f"turns {rows[-3]['turn']}, {rows[-2]['turn']}, {rows[-1]['turn']}), "
        f"jsonlog/{CAPTURE_NAME}.decisions.jsonl.gz (last two rows, sequences "
        f"{previous['decision_sequence']} and {stop['decision_sequence']}, "
        "equal to the last two rows of incident-captures/"
        "20260926-015751-stuck-prompt/decision-tail.jsonl), "
        f"jsonlog/{CAPTURE_NAME}.stderr.log.\n"
        f"state.jsonl.gz sha256 {hashlib.sha256(STATE.read_bytes()).hexdigest()}; "
        f"decisions.jsonl.gz sha256 "
        f"{hashlib.sha256(DECISIONS.read_bytes()).hexdigest()}; "
        f"decision-tail.jsonl sha256 "
        f"{hashlib.sha256(TAIL.read_bytes()).hexdigest()}; "
        f"stderr.log sha256 {hashlib.sha256(STDERR.read_bytes()).hexdigest()}\n"
        f"Skill list: the state log's last skill_exp knowledge row (turn "
        f"{skill['turn']}).\n"
        f"Frozen records: {len(records)}; decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
