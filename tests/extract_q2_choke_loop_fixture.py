"""Freeze the 2026-10-02 14:16:07 bot process of the 14:16:22 loop-detected stop.

Source (read-only): the auto-recovery capture
``jsonlog/autorecover-20261002-141622-loop-detected.*`` of the live checkout
(commit 275a9076, ``--enforce-crossarea-fundraising``, S3.3 switch off).  Its
decision log holds the earlier processes' tails and the whole 14:16:07
process (session-start row, then decisions 0..39 and the loop-detected row);
the state log holds every row.  The 14:16:07 process is a restart inside
quest Q2 (floor (0, 15, 2)); it is frozen from its attach row through
decision index ``LAST_INDEX``.

Boundaries as tests/extract_q2travel_progress_fixture.py.  The live
jsonlog/character-calibration.json was last written at 13:16:20, before the
process started; its LF-normalised bytes equal the already frozen
tests/fixtures/q2travel-progress-20261002.character-calibration.json
(sha256 78ba2af1...), which the test reuses.

Only this tool reads the capture; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path("C:/hengband/bot-client/jsonlog")
CAPTURE = "autorecover-20261002-141622-loop-detected"
DECISIONS = LIVE / f"{CAPTURE}.bot-decisions.jsonl.gz"
STATE = LIVE / f"{CAPTURE}.bot-state-fixed.jsonl.gz"
OUTPUT = ROOT / "tests" / "fixtures" / "q2-choke-loop-20261002.jsonl.gz"
BOUNDARIES = ROOT / "tests" / "fixtures" / "q2-choke-loop-20261002.boundaries.json"
CALIBRATION_SOURCE = LIVE / "character-calibration.json"
CALIBRATION = (ROOT / "tests" / "fixtures"
               / "q2travel-progress-20261002.character-calibration.json")
LAST_INDEX = 22


def _lines(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return stream.read().splitlines(keepends=True)


def _detail(row: dict) -> dict:
    claim = row.get("claim") or {}
    return {
        "claim": {name: claim.get(name) for name in
                  ("owner", "rung", "trigger_monsters")},
        "visible_hostiles": row.get("visible_hostiles"),
        "floor": row.get("floor"),
    }


def main() -> None:
    decisions = [json.loads(line) for line in _lines(DECISIONS)]
    start = max(i for i, row in enumerate(decisions)
                if row.get("kind") == "session-start")
    assert decisions[start]["time"] == "2026-10-02T14:16:07+0900"
    assert decisions[start]["git_commit"] == "275a9076"
    decisions = [row for row in decisions[start + 1:]
                 if row.get("reason") != "loop-detected"]
    assert [row["decision_sequence"] for row in decisions] == list(range(40))
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
        "detail": {str(index): _detail(decisions[index])
                   for index in range(LAST_INDEX + 1)},
    }
    BOUNDARIES.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    assert (CALIBRATION_SOURCE.read_bytes().replace(b"\r\n", b"\n")
            == CALIBRATION.read_bytes().replace(b"\r\n", b"\n"))
    for path in (OUTPUT, BOUNDARIES, CALIBRATION):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
