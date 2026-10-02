"""Freeze the 2026-10-02 17:01:12 bot process of the 17:01:48 owner-retired stop.

Source (read-only): the auto-recovery capture
``jsonlog/autorecover-20261002-170148-town-blocked-owner-retired.*`` of the
live checkout (commit 35a18252, ``--enforce-crossarea-fundraising``, S3.3
switch off).  Its decision log holds the two previous processes' tails and the
whole 17:01:12 process (session-start row, then decisions 0..7); the state
log holds every row.  The process is frozen from its attach row through
decision index 7 (``town:blocked:owner-retired``).

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, and every boundary row must carry the
decision record's turn (as tests/extract_oneshot_preempt_fixture.py).
Decision 0's input is the attach row plus its drained rows.

The calibration file is the live jsonlog/character-calibration.json (13:16,
unchanged until after the stop), committed as
tests/fixtures/town-blackmarket-stall-20261002.character-calibration.json.
The live process held its own session's equipped C-sheet calibration
(``equipped-c-screen``, schema 2); the committed test replays without
installing the schema-1 file record and reproduces the recorded decisions.

Only this tool reads the capture; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path("C:/hengband/bot-client/jsonlog")
CAPTURE = "autorecover-20261002-170148-town-blocked-owner-retired"
DECISIONS = LIVE / f"{CAPTURE}.bot-decisions.jsonl.gz"
STATE = LIVE / f"{CAPTURE}.bot-state-fixed.jsonl.gz"
OUTPUT = ROOT / "tests" / "fixtures" / "town-blackmarket-stall-20261002.jsonl.gz"
BOUNDARIES = ROOT / "tests" / "fixtures" / "town-blackmarket-stall-20261002.boundaries.json"
LAST_INDEX = 7
DETAIL_INDEXES = (0, 1, 2, 3, 4, 5, 6, 7)


def _lines(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return stream.read().splitlines(keepends=True)


def _detail(row: dict) -> dict:
    claim = row.get("claim") or {}
    selector = row.get("shop_selector") or {}
    visit = row.get("store_visit") or {}
    return {
        "store_type": row.get("store_type"),
        "arbiter": row.get("arbiter"),
        "claim": {name: claim.get(name) for name in
                  ("claim_id", "owner", "state", "budget", "rung")},
        "execution": {name: (claim.get("execution") or {}).get(name) for name in
                      ("producer", "work_id", "next_step", "arguments",
                       "expected_effect", "continuation")},
        "store_visit": {name: visit.get(name) for name in
                        ("owner", "purpose", "store_type", "visit_origin", "phase")},
        "shop_selector": {name: selector.get(name) for name in
                          ("winning_rung", "wanted_purchase", "rejection_reason",
                           "town_progress_invariant")},
        "procurement_requirements": row.get("procurement_requirements"),
        "gold": (row.get("player") or {}).get("gold"),
    }


def main() -> None:
    decisions = [json.loads(line) for line in _lines(DECISIONS)]
    start = max(i for i, row in enumerate(decisions)
                if row.get("kind") == "session-start")
    assert decisions[start]["time"] == "2026-10-02T17:01:12+0900"
    assert decisions[start]["git_commit"] == "35a18252"
    decisions = decisions[start + 1:]
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
        "detail": {str(index): _detail(decisions[index]) for index in DETAIL_INDEXES},
    }
    BOUNDARIES.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    for path in (OUTPUT, BOUNDARIES):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
