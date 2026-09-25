"""Freeze the 2026-09-25 12:56 stuck-prompt stop at recorded decision boundaries.

The capture is jsonlog/incident-20260925-1256-stuck-prompt.* (copies of the
live logs taken right after the stop) plus the automatic capture
incident-captures/20260925-125619-stuck-prompt.  The bot process was started
at 12:35:14 onto the running game.

Decisions: the incident's decisions.jsonl.gz holds only the last 3,457
decisions of the process (sequence 3834..7288).  The whole process is the live
generation jsonlog/bot-decisions.jsonl from its 12:35:14 sequence-0 row (the
generation opened at 10:19:52 and was not rotated again); this tool checks
that its tail equals the incident copy and the automatic capture's
decision-tail.jsonl row for row.

Boards: the state log does not reach back to the process start.  The emitter
truncated it during the process (at its size limit); its first row (turn
5461120, 12:44) is the board of log index 3380 (sequence 3378).  Each
decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, and every boundary row must carry the
decision record's turn; the walk from the last row validates for every
decision from log index 3380 to the stop.  Decisions are addressed by their
index in the log, never by ``decision_sequence``: the landing reuses 7286.

What is frozen:
- ``recorded``: the listed facts of every decision from log index 3380 to the
  stop (the boundaries file);
- the boards of the closing window only -- the last dungeon board (sequence
  7286 ``return:wait-recall``, read alone, as a resumed process attaches to
  the state log's last row), the landing (7286 skill-list probe), the
  ``town:recover`` board (7287) and the stop board (7288, the state log's
  last row);
- ``attach_skill_knowledge``: the process's ``~f`` skill list response of
  12:53 (turn 5483557), so an attaching policy does not spend the dungeon
  board on the probe (the 7286 response in the window carries the same
  values).

Calibration: the process rewrote jsonlog/character-calibration.json at
sequence 6608 (12:53, the naked-character calibration) and nothing wrote it
afterwards (mtime 12:53), so the file on disk is the one the window's
decisions read; it is frozen as
tests/fixtures/stuck-prompt-staged-tail-20260925.character-calibration.json.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "incident-20260925-1256-stuck-prompt"
LIVE = next(
    candidate
    for candidate in (ROOT / "jsonlog", Path("C:/hengband/bot-client/jsonlog"))
    if (candidate / f"{CAPTURE_NAME}.state.jsonl.gz").is_file()
)
STATE = LIVE / f"{CAPTURE_NAME}.state.jsonl.gz"
INCIDENT_DECISIONS = LIVE / f"{CAPTURE_NAME}.decisions.jsonl.gz"
LIVE_DECISIONS = LIVE / "bot-decisions.jsonl"
CALIBRATION_SOURCE = LIVE / "character-calibration.json"
AUTOMATIC = LIVE.parent / "incident-captures" / "20260925-125619-stuck-prompt"
TAIL_DECISIONS = AUTOMATIC / "decision-tail.jsonl"
OUTPUT = ROOT / "tests" / "fixtures" / "stuck-prompt-staged-tail-20260925.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "stuck-prompt-staged-tail-20260925.character-calibration.json"
)
PROCESS_START = "2026-09-25T12:35:14+0900"
WINDOW = 4  # the last dungeon board, the landing, town:recover, the stop
RECORDED_FIELDS = [
    "decision_sequence",
    "turn",
    "key",
    "reason",
    "y",
    "x",
    "dungeon_id",
    "level",
    "store_type",
    "staged_chain_outcome",
    "staged_chain_posted",
    "read_key",
    "invariant_winning_rung",
    "invariant_progress_action",
]


def _decision_rows() -> list[dict]:
    rows = []
    started = False
    with LIVE_DECISIONS.open("rb") as stream:
        for line in stream:
            row = json.loads(line)
            if "decision_sequence" not in row:
                continue
            if row["decision_sequence"] == 0 and row["time"] == PROCESS_START:
                started = True
            if started:
                rows.append(row)
    if not rows:
        raise RuntimeError("the 12:35 process start is not in the live log")
    with gzip.open(INCIDENT_DECISIONS, "rt", encoding="utf-8") as stream:
        incident = [json.loads(line) for line in stream]
    if rows[-len(incident):] != incident:
        raise RuntimeError("the live log tail differs from the incident copy")
    # The capture keeps the last 16 MiB of the log: its first line is the cut
    # remainder of a row and is not compared.
    tail_lines = TAIL_DECISIONS.read_text(encoding="utf-8").splitlines()[1:]
    tail = [json.loads(line) for line in tail_lines]
    tail = [row for row in tail if "decision_sequence" in row]
    if rows[-len(tail):] != tail:
        raise RuntimeError("the live log tail differs from the capture tail")
    return rows


def _input_ends(decisions: list[dict], rows: list[dict]) -> list[int]:
    """Walk back from the last row carrying the last decision's turn."""
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    last = len(rows) - 1
    while rows[last].get("turn") != decisions[-1]["turn"]:
        last -= 1
    ends = [last]
    for index in range(len(decisions) - 1, 0, -1):
        end = max(0, ends[-1] - drains[index - 1])
        while end > 0 and rows[end].get("turn") != decisions[index - 1]["turn"]:
            end -= 1
        ends.append(end)
    ends.reverse()
    return ends


def _recorded(row: dict) -> list:
    chain = row.get("staged_prompt_chain") or {}
    invariant = (row.get("shop_selector") or {}).get("town_progress_invariant") or {}
    return [
        row["decision_sequence"],
        row["turn"],
        row["key"],
        row["reason"],
        row["position"]["y"],
        row["position"]["x"],
        row["floor"]["dungeon_id"],
        row["floor"]["level"],
        row.get("store_type"),
        chain.get("outcome"),
        chain.get("posted"),
        (row.get("read") or {}).get("key"),
        invariant.get("winning_rung"),
        invariant.get("progress_action"),
    ]


def main() -> None:
    decisions = _decision_rows()
    with gzip.open(STATE, "rb") as stream:
        lines = stream.read().splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    ends = _input_ends(decisions, rows)
    # The log begins at the board of decision ``first``: that board is row 0
    # and every earlier decision's board is gone.
    first = next(index for index, end in enumerate(ends) if end > 0) - 1
    if ends[first] != 0 or rows[0].get("turn") != decisions[first]["turn"]:
        raise RuntimeError("the state log does not begin at a decision board")
    decisions = decisions[first:]
    ends = ends[first:]
    mismatched = [
        index
        for index, (decision, end) in enumerate(zip(decisions, ends))
        if rows[end].get("turn") != decision["turn"]
    ]
    if mismatched:
        raise RuntimeError(f"unexpected boundary mismatches {mismatched[:20]}")
    if ends[-1] != len(rows) - 1:
        raise RuntimeError("the stop board is not the last state row")
    window = len(decisions) - WINDOW
    attach = ends[window]
    counts = [1] + [ends[i] - ends[i - 1] for i in range(window + 1, len(decisions))]
    if min(counts) < 1:
        raise RuntimeError("a decision reads no row")
    selected = [lines[attach]] + lines[attach + 1 : ends[-1] + 1]
    payload = b"".join(selected)
    skill_rows = [
        row for row in rows
        if row.get("type") == "knowledge"
        and (row.get("knowledge") or {}).get("category") == "skill_exp"
    ]
    attach_skill = skill_rows[0]
    if attach_skill["turn"] >= decisions[window]["turn"]:
        raise RuntimeError("the skill list is not older than the attach board")
    source_calibration = CALIBRATION_SOURCE.read_bytes()
    # Frozen with LF line ends (the repository's text normalisation); the
    # JSON content is the live file's.
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
                "first_log_index": first,
                "window_start": window,
                "input_rows": counts,
                "attach_skill_knowledge": attach_skill,
                "recorded_fields": RECORDED_FIELDS,
                "recorded": [_recorded(row) for row in decisions],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    start, last = decisions[0], decisions[-1]
    PROVENANCE.write_text(
        f"Source: jsonlog/{CAPTURE_NAME}.state.jsonl.gz (copy of the live "
        "state log taken at the 12:56 stop); decisions: jsonlog/bot-decisions."
        "jsonl (live generation) from the 12:35:14 sequence-0 row, its tail "
        f"equal row for row to jsonlog/{CAPTURE_NAME}.decisions.jsonl.gz and "
        "to incident-captures/20260925-125619-stuck-prompt/decision-tail.jsonl.\n"
        f"state.jsonl.gz sha256 {hashlib.sha256(STATE.read_bytes()).hexdigest()}; "
        f"decisions.jsonl.gz sha256 "
        f"{hashlib.sha256(INCIDENT_DECISIONS.read_bytes()).hexdigest()}; "
        f"decision-tail.jsonl sha256 "
        f"{hashlib.sha256(TAIL_DECISIONS.read_bytes()).hexdigest()}\n"
        f"Recorded facts: log index {first} (sequence "
        f"{start['decision_sequence']}, the first decision whose board the "
        "truncated state log still holds) to the stop, "
        f"{len(decisions)} decisions ({start['time']} - {last['time']}, turn "
        f"{start['turn']}-{last['turn']}); the boundary walk validates for all "
        "of them.\n"
        f"Frozen boards: the last {WINDOW} decisions (window index {window}, "
        f"sequence {decisions[window]['decision_sequence']}..."
        f"{last['decision_sequence']}); the first reads its board row "
        f"{attach} alone, the stop board is the state log's last row.  "
        f"Emitter rows: {len(selected)}; decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n"
        f"Attach skill list: the state log's first skill_exp knowledge row "
        f"(turn {attach_skill['turn']}).\n"
        "Calibration: jsonlog/character-calibration.json as the process's "
        "sequence-6608 calibration wrote it (mtime 12:53, unwritten since), "
        f"sha256 {hashlib.sha256(source_calibration).hexdigest()}; frozen "
        "with LF line ends, sha256 "
        f"{hashlib.sha256(calibration).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    print(BOUNDARIES.name, hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest())
    print(CALIBRATION.name, hashlib.sha256(calibration).hexdigest())
    print("decisions", len(decisions), "window", window, "rows", len(selected))


if __name__ == "__main__":
    main()
