"""Freeze the 2026-09-25 01:54 guardian recall ping-pong at decision boundaries.

The capture is a copy of the live logs of one bot process taken right after it
was stopped (jsonlog/incident-20260925-0201-guardian-recall-pingpong.*).  The
game was launched at 01:54 on the new exe and the bot attached at 01:54:27, so
the state log holds every emitter row the process ever read: its first row is
the first board of the whole episode.

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, and every boundary row must carry the
decision record's turn.  The state log's final row (turn 5328134) was emitted
after the bot's last decision and consumed by none, so the walk starts from
the last row carrying the last decision's turn; it then validates for every
logged decision.
The first decision after each recall landing in town reuses the sequence number
of the countdown's last wait, so decisions are addressed by their index in the
log, never by ``decision_sequence``.

Frozen window: decisions 0..LAST, the whole run up to the first decision a
restarted policy does not reproduce (263, ``town:kill-mob-approach`` recorded
against ``store:entry-await-observation`` replayed, a town fight that has
nothing to do with the recall bounce).  It holds the unsafe-recall fallback
that chose the Orc cave (8), the first three recalls to it (13, 92, 185), all
three guardian-kit-insufficient returns (37, 138, 211) and all three town
arrivals they produced (84, 177, 257).

The live process loaded jsonlog/character-calibration.json, last written
2026-09-24 05:24, i.e. before this run; its bytes are frozen beside the rows.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "incident-20260925-0201-guardian-recall-pingpong"
CAPTURE = next(
    candidate
    for candidate in (
        ROOT / "jsonlog" / CAPTURE_NAME,
        Path("C:/hengband/bot-client/jsonlog") / CAPTURE_NAME,
    )
    if candidate.with_suffix(".state.jsonl").is_file()
)
STATE = CAPTURE.with_suffix(".state.jsonl")
DECISIONS = CAPTURE.with_suffix(".decisions.jsonl")
CALIBRATION_SOURCE = CAPTURE.parent / "character-calibration.json"
OUTPUT = ROOT / "tests" / "fixtures" / "guardian-recall-pingpong-20260925.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "guardian-recall-pingpong-20260925.character-calibration.json"
)
LAST = 262  # the last decision (by log index) a restarted policy reproduces


def _decision_rows() -> list[dict]:
    rows = []
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "decision_sequence" in row:
            rows.append(row)
    return rows


def _state_lines() -> list[bytes]:
    return STATE.read_bytes().splitlines(keepends=True)


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


def main() -> None:
    decisions = _decision_rows()
    lines = _state_lines()
    rows = [json.loads(line) for line in lines]
    ends = _input_ends(decisions, rows)
    mismatched = [
        index
        for index, (decision, end) in enumerate(zip(decisions, ends))
        if rows[end].get("turn") != decision["turn"]
    ]
    if mismatched:
        raise RuntimeError(f"unexpected boundary mismatches {mismatched}")
    if ends[0] != 0:
        raise RuntimeError("the first decision does not read the first row")
    window = decisions[: LAST + 1]
    counts = [1] + [ends[i] - ends[i - 1] for i in range(1, LAST + 1)]
    selected = lines[: ends[LAST] + 1]
    payload = b"".join(selected)
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    recorded = []
    for row in window:
        over = row.get("over_extension") or {}
        recorded.append(
            [
                row["key"],
                row["reason"],
                row["floor"]["dungeon_id"],
                row["floor"]["level"],
                over.get("target_dungeon_id"),
                over.get("alternate_dungeon_id"),
                over.get("over_extended_dive_streak"),
                over.get("last_overextended_depth"),
                over.get("last_return_trigger"),
            ]
        )
    BOUNDARIES.write_text(
        json.dumps(
            {
                "decision_count": len(window),
                "input_rows": counts,
                "recorded_fields": [
                    "key",
                    "reason",
                    "dungeon_id",
                    "level",
                    "target_dungeon_id",
                    "alternate_dungeon_id",
                    "over_extended_dive_streak",
                    "last_overextended_depth",
                    "last_return_trigger",
                ],
                "recorded": recorded,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    CALIBRATION.write_bytes(
        CALIBRATION_SOURCE.read_bytes().replace(b"\r\n", b"\n")
    )
    first, last = window[0], window[-1]
    PROVENANCE.write_text(
        f"Source: jsonlog/{CAPTURE_NAME}.{{state,decisions}}.jsonl "
        "(copies of the live logs taken at the 02:01 stop).\n"
        f"state.jsonl sha256 {hashlib.sha256(STATE.read_bytes()).hexdigest()}; "
        f"decisions.jsonl sha256 "
        f"{hashlib.sha256(DECISIONS.read_bytes()).hexdigest()}\n"
        f"Selection: decisions 0..{LAST} by log index ({first['time']} - "
        f"{last['time']}, turn {first['turn']}-{last['turn']}); decision "
        f"{LAST + 1} is the first one a restarted policy does not reproduce.\n"
        "Boundary rule: walking back from the last emitter row that carries "
        "the last decision's turn (the log's final row came after the bot's "
        "last decision), each decision's input ends drain(previous decision) "
        "rows earlier and must carry the decision record's turn; the walk "
        f"validates for all {len(decisions)} logged decisions.  Decision 0 "
        "reads the state log's first row.\n"
        f"Emitter rows: {len(selected)} of {len(lines)}; decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n"
        "Calibration: jsonlog/character-calibration.json as loaded by the "
        "process (last written 2026-09-24 05:24, before the run) sha256 "
        f"{hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
