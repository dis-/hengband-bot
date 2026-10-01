"""Freeze the 2026-10-02 06:14:06 bot process of the 06:16 loop-detected stop.

Source (read-only): the auto-recovery capture
``jsonlog/autorecover-20261002-061620-loop-detected.*`` of the live checkout.
Its decision log holds two whole processes (session-start rows at 06:11:24
and 06:14:06); the state log holds every row of both.  The second process is
frozen from its attach row through decision index 11 (the first
``town:blocked:no-actionable-claim-owner``).

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, and every boundary row must carry the
decision record's turn (walk back from the last row carrying the last
decision's turn, as tests/extract_overweight_home_unreachable_fixture.py).
Decision 0's input is the attach row plus its drained rows.

The process loaded jsonlog/character-calibration.json (written 05:51, before
the 06:14:06 start).  Home history files are not needed: the recorded
decisions 0..11 replay identically without them.

Only this tool reads the capture; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path("C:/hengband/bot-client/jsonlog")
CAPTURE = "autorecover-20261002-061620-loop-detected"
DECISIONS = LIVE / f"{CAPTURE}.bot-decisions.jsonl.gz"
STATE = LIVE / f"{CAPTURE}.bot-state-fixed.jsonl.gz"
CALIBRATION_SOURCE = LIVE / "character-calibration.json"
CALIBRATION_SHA256 = "e4e925925fd6faf89603a81a85d56082962c4270730390600c1b545b25abf59f"
OUTPUT = ROOT / "tests" / "fixtures" / "overweight-home-hold-20261002.jsonl.gz"
BOUNDARIES = ROOT / "tests" / "fixtures" / "overweight-home-hold-20261002.boundaries.json"
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "overweight-home-hold-20261002.character-calibration.json"
)
LAST_INDEX = 11
HOME_INDEX = 3


def _lines(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return stream.read().splitlines(keepends=True)


def main() -> None:
    decisions = [json.loads(line) for line in _lines(DECISIONS)]
    start = max(i for i, row in enumerate(decisions)
                if row.get("kind") == "session-start")
    assert decisions[start]["time"] == "2026-10-02T06:14:06+0900"
    decisions = decisions[start + 1:]
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
    first = ends[0] - drains[0]  # the attach row
    segments = [lines[first:ends[0] + 1]]
    segments += [lines[ends[i - 1] + 1:ends[i] + 1] for i in range(1, len(ends))]
    for index, segment in enumerate(segments):
        assert json.loads(segment[-1])["turn"] == decisions[index]["turn"], index
    kept = segments[:LAST_INDEX + 1]
    payload = "".join(line.replace("\r\n", "\n") for segment in kept for line in segment)
    OUTPUT.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    home = decisions[HOME_INDEX]
    stop = decisions[LAST_INDEX]
    boundaries = {
        "source": {
            str(path.name): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (DECISIONS, STATE)
        },
        "state_rows": [first, ends[LAST_INDEX]],
        "input_rows": [len(segment) for segment in kept],
        "recorded_fields": ["decision_sequence", "turn", "key", "reason", "position"],
        "recorded": [
            [row["decision_sequence"], row["turn"], row["key"], row["reason"],
             [row["position"]["y"], row["position"]["x"]]]
            for row in decisions[:LAST_INDEX + 1]
        ],
        "home_claim": {
            name: home["claim"][name]
            for name in ("claim_id", "owner", "reason", "errand_deferred")
        },
        "home_closed_claim": {
            name: home["claim"]["closed_claim"][name]
            for name in ("claim_id", "owner", "goal_kind", "closed_reason")
        },
        "stop_departure_block": {
            name: stop["departure_block"][name]
            for name in ("failed", "town_claims", "town_ledger")
        },
    }
    BOUNDARIES.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    calibration = CALIBRATION_SOURCE.read_bytes()
    assert hashlib.sha256(calibration).hexdigest() == CALIBRATION_SHA256
    CALIBRATION.write_bytes(calibration.replace(b"\r\n", b"\n"))
    for path in (OUTPUT, BOUNDARIES, CALIBRATION):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
