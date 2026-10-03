"""Freeze the 2026-10-03 07:35:33 bot process of the Identify-staff swap loop.

Source (read-only): the copy of the live logs taken at the 07:48 stop,
``C:/hengband-backups/state-logs/town-staffswap-loop-20261003-0748/``.  The
decision log holds two processes; the second (session-start 07:35:33, bot
commit 31a1d944, both enforcement switches off) began with the game relaunch,
so the state log holds every row of it.  The process is frozen from its
attach row through decision index ``LAST_INDEX`` (turn 6088392, the last row
of the town stay).

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, walking back to the row carrying the
previous decision's turn (as tests/extract_overweight_home_hold_fixture.py).

The process loaded jsonlog/character-calibration.json from disk and wrote it
again at each periodic C-sheet dump; the last write (07:47, observed turn
6086409, after the Strength restore at 6084705) is frozen as the extraction
record (tests/extraction_calibration.py).  The dump files themselves are not
in the capture, so the committed test declares a dump wall: at each posted
dump's completion it installs the frozen record whose printed stat key
matches the board -- the drained-Strength record
tests/fixtures/lethal-unseen-caster-20261003.character-calibration.json while
Strength is drained, else this 07:47 record.  jsonlog/confirmed-loadout.json
is not frozen: the walled replay reproduces the recorded decisions without
it.  Home history files are not needed either.

Only this tool reads the capture; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = Path("C:/hengband-backups/state-logs/town-staffswap-loop-20261003-0748")
DECISIONS = CAPTURE / "bot-decisions.jsonl"
STATE = CAPTURE / "bot-state-fixed.jsonl"
LIVE = Path("C:/hengband/bot-client/jsonlog")
CALIBRATION_SOURCE = LIVE / "character-calibration.json"
SOURCE_SHA256 = {
    DECISIONS: "2ab81695286c353fe15d0c8a8f24ab0e2b8b357626fb428f69d7ed2872cb49bd",
    STATE: "8ff98cab0565e81d4980cf746e8e111c7b4e61fc3d42ba0b075bfce32715a5b2",
    CALIBRATION_SOURCE: "3982b49ad2897de134790d4190ab9752eef7ac713041e7655f5a08bf1491214c",
}
STEM = "identify-staff-swap-churn-20261003"
FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT = FIXTURES / f"{STEM}.jsonl.gz"
BOUNDARIES = FIXTURES / f"{STEM}.boundaries.json"
CALIBRATION = FIXTURES / f"{STEM}.character-calibration.json"
SESSION_START = "2026-10-03T07:35:33+0900"
LAST_INDEX = 2918
STAY_FIRST = 2805  # town arrival, turn 6080192


def _lines(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as stream:
        return stream.read().splitlines(keepends=True)


def main() -> None:
    for path, digest in SOURCE_SHA256.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"{path} changed since extraction")
    raw = [json.loads(line) for line in _lines(DECISIONS)]
    start = max(i for i, row in enumerate(raw) if row.get("kind") == "session-start")
    assert raw[start]["time"] == SESSION_START
    assert raw[start]["git_commit"] == "31a1d944"
    decisions = [row for row in raw[start + 1:] if "decision_sequence" in row]
    assert len(decisions) == LAST_INDEX + 1
    lines = _lines(STATE)
    rows = [json.loads(line) for line in lines]
    drains = [int((row.get("timing") or {}).get("jsonl_drain_records") or 0)
              for row in decisions]
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
        "stay": {
            str(index): {
                "store_type": decisions[index].get("store_type"),
                "shop_selector": decisions[index].get("shop_selector"),
                "procurement_requirements": decisions[index].get(
                    "procurement_requirements"),
                "messages": decisions[index].get("messages"),
            }
            for index in range(STAY_FIRST, LAST_INDEX + 1)
        },
    }
    BOUNDARIES.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    CALIBRATION.write_bytes(
        CALIBRATION_SOURCE.read_bytes().replace(b"\r\n", b"\n"))
    for path in (OUTPUT, BOUNDARIES, CALIBRATION):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
