"""Freeze the 2026-09-25 14:52 recall read/cancel ping-pong at recorded boundaries.

The capture is jsonlog/incident-20260925-1452-recall-read-cancel-pingpong.*
(copies of the live logs taken after the operator stopped the bot at 14:53)
plus the automatic capture incident-captures/20260925-145223-posting-
contract-recall-already-active.  The bot process started at 14:22; its
decision log rotated at 14:41, and the incident copy holds its decisions from
sequence 3961 (14:41:13) to the last one, 5989 ``town:recall-stockout-mining``
(14:53:52).  The state log reaches back to turn 5538425 (the dive before the
town visit); the town visit begins at the recall landing (sequence 5862).

Decisions: the decision log also holds eight rows without a
``decision_sequence``: the posting contract refused the first cancel read
of eight pairs (``posting-contract:recall-already-active``).  Decision rows
are addressed by their index among decision rows ("log index"), never by
``decision_sequence``: the landing reuses 5862 and each refused cancel shares
its sequence with the ``l\\x1b`` recovery that follows it.

Boards: each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says (the extractors' walk back from the last
row carrying the last decision's turn), except around a refused key: the
refused decision posted nothing, so the next decision decides on the same
board and its drain counts one read that produced no row.  With that rule the
walk validates (every boundary row carries the decision record's turn) for
every decision from log index 1902 (the landing's ~f probe) to the last.

What is frozen, for each of the nine recorded ``town:recall-to-alt-dungeon``
reads and the decision that follows it (the ``town:cancel-unready-recall``):
the read decision's input rows and the cancel decision's input rows; the
recorded facts of both decisions; and the landing's ~f skill list response
(the knowledge row of this town visit).  The calibration file is the one the
process wrote at 14:23:36 (observed_turn 5493010) and nothing wrote since.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "incident-20260925-1452-recall-read-cancel-pingpong"
LIVE = next(
    candidate
    for candidate in (ROOT / "jsonlog", Path("C:/hengband/bot-client/jsonlog"))
    if (candidate / f"{CAPTURE_NAME}.state.jsonl.gz").is_file()
)
STATE = LIVE / f"{CAPTURE_NAME}.state.jsonl.gz"
DECISIONS = LIVE / f"{CAPTURE_NAME}.decisions.jsonl.gz"
CALIBRATION_SOURCE = LIVE / "character-calibration.json"
AUTOMATIC = LIVE.parent / "incident-captures" / (
    "20260925-145223-posting-contract-recall-already-active"
)
TAIL_DECISIONS = AUTOMATIC / "decision-tail.jsonl"
OUTPUT = ROOT / "tests" / "fixtures" / "recall-read-cancel-pingpong-20260925.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "recall-read-cancel-pingpong-20260925.character-calibration.json"
)
READ_REASON = "town:recall-to-alt-dungeon"
RECORDED_FIELDS = [
    "log_index",
    "decision_sequence",
    "turn",
    "key",
    "reason",
    "y",
    "x",
    "inventory_used",
    "inventory_free",
    "read_key",
    "home_scan_complete",
    "identification_need",
    "home_candidate_waiting",
    "target_dungeon_id",
    "alternate_dungeon_id",
    "posting_refused",
]


def _decisions() -> tuple[list[dict], set[int]]:
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        raw = [json.loads(line) for line in stream]
    decisions: list[dict] = []
    refused: set[int] = set()
    for row in raw:
        if "decision_sequence" in row:
            decisions.append(row)
        elif row.get("contract_incident"):
            refused.add(len(decisions) - 1)
        else:
            raise RuntimeError(f"unexpected decision-log row {sorted(row)}")
    # The automatic capture's decision tail (cut at 16 MiB; its first line is
    # the remainder of a row) ends with the same rows as the copy at the
    # automatic capture's moment (14:52:26).
    tail_lines = TAIL_DECISIONS.read_text(encoding="utf-8").splitlines()[1:]
    tail = [json.loads(line) for line in tail_lines]
    if not tail or raw[: raw.index(tail[-1]) + 1][-len(tail):] != tail:
        raise RuntimeError("the automatic capture tail differs from the copy")
    return decisions, refused


def _input_ends(decisions: list[dict], rows: list[dict], refused: set[int]) -> list:
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    last = len(rows) - 1
    while rows[last].get("turn") != decisions[-1]["turn"]:
        last -= 1
    ends: list = [None] * len(decisions)
    ends[-1] = last
    for index in range(len(decisions) - 1, 0, -1):
        if index - 1 in refused:
            ends[index - 1] = ends[index]
            continue
        drain = drains[index - 1] - (1 if index - 2 in refused else 0)
        end = ends[index] - drain
        if end < 0:
            break
        ends[index - 1] = end
    return ends


def _recorded(index: int, row: dict, board: dict, refused: set[int]) -> list:
    over = row.get("over_extension") or {}
    inventory = row.get("inventory") or {}
    return [
        index,
        row["decision_sequence"],
        row["turn"],
        row["key"],
        row["reason"],
        row["position"]["y"],
        row["position"]["x"],
        inventory.get("used"),
        inventory.get("free"),
        (row.get("read") or {}).get("key"),
        (row.get("equipment_optimization") or {}).get("home_scan_complete"),
        row.get("identification_need"),
        row.get("home_candidate_waiting"),
        over.get("target_dungeon_id"),
        over.get("alternate_dungeon_id"),
        index in refused,
    ]


def main() -> None:
    decisions, refused = _decisions()
    with gzip.open(STATE, "rb") as stream:
        lines = stream.read().splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    ends = _input_ends(decisions, rows, refused)
    first = min(
        index
        for index in range(len(decisions))
        if all(
            ends[later] is not None
            and rows[ends[later]].get("turn") == decisions[later]["turn"]
            for later in range(index, len(decisions))
        )
    )
    landing = next(
        index for index in range(first, len(decisions))
        if decisions[index]["reason"] == "periodic:skill-exp-knowledge"
        and decisions[index]["floor"]["dungeon_id"] == 0
    )
    if landing != first:
        raise RuntimeError(f"the walk validates from {first}, not the landing {landing}")
    reads = [
        index for index in range(first, len(decisions))
        if decisions[index]["reason"] == READ_REASON
    ]
    for index in reads:
        if decisions[index + 1]["reason"] != "town:cancel-unready-recall":
            raise RuntimeError(f"read {index} is not followed by the cancel")
    skill = next(
        rows[position] for position in range(ends[landing] + 1, ends[landing + 1] + 1)
        if rows[position].get("type") == "knowledge"
        and (rows[position].get("knowledge") or {}).get("category") == "skill_exp"
    )
    selected: list[bytes] = []
    counts: list[int] = []
    recorded: list[list] = []
    for index in reads:
        for decision in (index, index + 1):
            segment = lines[ends[decision - 1] + 1 : ends[decision] + 1]
            if not segment:
                raise RuntimeError(f"decision {decision} reads no row")
            selected.extend(segment)
            counts.append(len(segment))
            recorded.append(
                _recorded(decision, decisions[decision], rows[ends[decision]], refused)
            )
    payload = b"".join(selected)
    source_calibration = CALIBRATION_SOURCE.read_bytes()
    calibration = source_calibration.replace(b"\r\n", b"\n")
    if json.loads(calibration) != json.loads(source_calibration):
        raise RuntimeError("line-end normalisation changed the calibration")
    CALIBRATION.write_bytes(calibration)
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    BOUNDARIES.write_text(
        json.dumps(
            {
                "reads": reads,
                "input_rows": counts,
                "attach_skill_knowledge": skill,
                "recorded_fields": RECORDED_FIELDS,
                "recorded": recorded,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    PROVENANCE.write_text(
        f"Source: jsonlog/{CAPTURE_NAME}.state.jsonl.gz and .decisions.jsonl.gz "
        "(copies of the live logs taken after the 14:53 operator stop); the "
        "automatic capture incident-captures/20260925-145223-posting-contract-"
        "recall-already-active/decision-tail.jsonl ends with the same rows.\n"
        f"state.jsonl.gz sha256 {hashlib.sha256(STATE.read_bytes()).hexdigest()}; "
        f"decisions.jsonl.gz sha256 {hashlib.sha256(DECISIONS.read_bytes()).hexdigest()}; "
        f"decision-tail.jsonl sha256 "
        f"{hashlib.sha256(TAIL_DECISIONS.read_bytes()).hexdigest()}\n"
        f"Boundary walk: validates from log index {first} (sequence "
        f"{decisions[first]['decision_sequence']}, the landing's ~f probe) to "
        f"the last decision ({len(decisions) - first} decisions); posting-"
        f"contract refusals after log indices {sorted(refused)}.\n"
        f"Frozen pairs (read log index -> cancel log index): "
        f"{[(index, index + 1) for index in reads]}; each decision's own "
        f"input rows ({len(selected)} emitter rows); decompressed sha256 "
        f"{hashlib.sha256(payload).hexdigest()}.\n"
        f"Attach skill list: the landing's skill_exp knowledge row (turn "
        f"{skill['turn']}).\n"
        "Calibration: jsonlog/character-calibration.json as the 14:22 process "
        "wrote it at 14:23:36 (observed_turn 5493010), unwritten since, sha256 "
        f"{hashlib.sha256(source_calibration).hexdigest()}; frozen with LF line "
        f"ends, sha256 {hashlib.sha256(calibration).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    print(BOUNDARIES.name, hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest())
    print(CALIBRATION.name, hashlib.sha256(calibration).hexdigest())
    print("pairs", len(reads), "rows", len(selected))


if __name__ == "__main__":
    main()
