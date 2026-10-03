"""Freeze the 2026-10-03 10:49:42 bot process of the store re-entry stays.

Source (read-only): the copy of the live logs taken at the 10:56 stop,
``C:/hengband-backups/state-logs/town-store-reentry-20261003-1056/``
(SOL-DESIGN-store-reentry-20261003 section 1).  The decision log holds four
processes; the third (session-start 10:49:42, bot commit c0cb88f6, both
enforcement switches off) is the one the design measured.  The state log
starts at that process's first row (turn 6088552), so every input row of it
is in the capture.  The process is frozen from its attach row through its
last decision (index ``LAST_INDEX``, turn 6106318, the 10:56:47 Black-market
release ``ph5\\r\\r\\x1b``).  Decision indices equal ``decision_sequence``
except after the two observation-only skill probes (sequence 167 and 761 are
each written twice), so the test addresses rows by index.

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, walking back to the row carrying the
previous decision's turn (as tests/extract_identify_staff_swap_churn_fixture.py).

No calibration record is frozen here: the process's periodic dumps read the
C-sheet file, which is not in the capture; the committed test installs the
07:47 record of tests/fixtures/identify-staff-swap-churn-20261003.
character-calibration.json (DUMP WALL, matched by printed stats).

Only this tool reads the capture; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = Path("C:/hengband-backups/state-logs/town-store-reentry-20261003-1056")
DECISIONS = CAPTURE / "bot-decisions.jsonl"
STATE = CAPTURE / "bot-state-fixed.jsonl"
SOURCE_SHA256 = {
    DECISIONS: "11f18d6e92a5fae15a24ffe207c77a96e0624cb3fe5faf0d5c8a411af77cfc04",
    STATE: "e7e4cd91ccbdd7a41effe1d8864415fe73f224fc046ef14c6e5b29bcecf0af65",
}
STEM = "store-reentry-20261003"
FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT = FIXTURES / f"{STEM}.jsonl.gz"
BOUNDARIES = FIXTURES / f"{STEM}.boundaries.json"
SESSION_START = "2026-10-03T10:49:42+0900"
LAST_INDEX = 846
# Per-decision fields kept for the pins (shop selector, plan evidence).
KEPT = ("store_type", "shop_selector", "plan_change_evidence", "town_plan",
        "identification_need", "messages", "store_visit")


def _lines(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as stream:
        return stream.read().splitlines(keepends=True)


def main() -> None:
    for path, digest in SOURCE_SHA256.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"{path} changed since extraction")
    raw = [json.loads(line) for line in _lines(DECISIONS)]
    starts = [i for i, row in enumerate(raw) if row.get("kind") == "session-start"]
    start = next(i for i in starts if raw[i]["time"] == SESSION_START)
    end = next((i for i in starts if i > start), len(raw))
    assert raw[start]["git_commit"] == "c0cb88f6"
    decisions = [row for row in raw[start + 1:end] if "decision_sequence" in row]
    assert len(decisions) == LAST_INDEX + 1, len(decisions)
    lines = _lines(STATE)
    rows = [json.loads(line) for line in lines]
    drains = [int((row.get("timing") or {}).get("jsonl_drain_records") or 0)
              for row in decisions]
    last = len(rows) - 1
    while rows[last].get("turn") != decisions[-1]["turn"]:
        last -= 1
    ends = [last]
    for index in range(len(decisions) - 1, 0, -1):
        stop = max(0, ends[-1] - drains[index - 1])
        while stop > 0 and rows[stop].get("turn") != decisions[index - 1]["turn"]:
            stop -= 1
        ends.append(stop)
    ends.reverse()
    first = max(0, ends[0] - drains[0])  # the attach row
    segments = [lines[first:ends[0] + 1]]
    segments += [lines[ends[i - 1] + 1:ends[i] + 1] for i in range(1, len(ends))]
    for index, segment in enumerate(segments):
        assert segment, index
        assert json.loads(segment[-1])["turn"] == decisions[index]["turn"], index
    payload = "".join(
        line.replace("\r\n", "\n") for segment in segments for line in segment
    )
    OUTPUT.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    boundaries = {
        "source": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SOURCE_SHA256
        },
        "session_start": SESSION_START,
        "state_rows": [first, ends[-1]],
        "input_rows": [len(segment) for segment in segments],
        "recorded_fields": ["decision_sequence", "turn", "key", "reason"],
        "recorded": [
            [row["decision_sequence"], row["turn"], row["key"], row["reason"]]
            for row in decisions
        ],
        "facts": {
            str(index): {name: decisions[index].get(name) for name in KEPT}
            for index, row in enumerate(decisions)
            if row.get("store_type") is not None
            or row.get("plan_change_evidence") is not None
        },
    }
    BOUNDARIES.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    for path in (OUTPUT, BOUNDARIES):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
