"""Freeze the 2026-10-03 11:59:45 bot process of the 12:04:21 owner-retired stop.

Source (read-only): the copy of the live logs taken after the stop,
``C:/hengband-backups/state-logs/town-owner-retired-20261003-1159/``
(``bot-decisions.live-1205.jsonl`` / ``bot-state-fixed.live-1205.jsonl``).
The decision log holds the tail of the 11:59:35 process, the whole 11:59:45
process (session-start row, then decisions 0..1390, bot commit 155e2829,
``--enforce-crossarea-fundraising``) and the head of the 12:04:38 process.
The state log begins at turn 6437914 (11:56:38), so it holds every row of
the 11:59:45 process; the process is frozen from its attach row through
decision index ``LAST_INDEX`` (``town:blocked:owner-retired``, turn 6484634).
The 11:59:35 stop's process began before the state log, so it cannot be
frozen from its attach row.

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, walking back to the row carrying the
previous decision's turn (as tests/extract_town_blackmarket_stall_fixture.py);
decision 0's input is the attach row plus its drained rows.

No calibration or C-sheet dump file is frozen: the dump files are not in the
capture, so the committed test replays without a dump path (the posted C
macros complete nothing and the calibration stays unavailable, the state the
live process reported at the stop: ``unavailable_reason`` visible-stat-key).

Only this tool reads the capture; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = Path(
    "C:/hengband-backups/state-logs/town-owner-retired-20261003-1159"
)
DECISIONS = CAPTURE / "bot-decisions.live-1205.jsonl"
STATE = CAPTURE / "bot-state-fixed.live-1205.jsonl"
SOURCE_SHA256 = {
    DECISIONS: "54218258f5afaf1c847e8897b3e1068a76fb4c87ce0edf321edce30b635637d8",
    STATE: "3869d11a1d73109038c7c7fe70f70b8b7258b5f052778783b64661119f482880",
}
STEM = "town-cure-supplier-20261003"
FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT = FIXTURES / f"{STEM}.jsonl.gz"
BOUNDARIES = FIXTURES / f"{STEM}.boundaries.json"
SESSION_START = "2026-10-03T11:59:45+0900"
LAST_INDEX = 1390
DETAIL_INDEXES = tuple(range(1381, LAST_INDEX + 1))


def _lines(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as stream:
        return stream.read().splitlines(keepends=True)


def _detail(row: dict) -> dict:
    claim = row.get("claim") or {}
    selector = row.get("shop_selector") or {}
    return {
        "store_type": row.get("store_type"),
        "arbiter": row.get("arbiter"),
        "claim": {name: claim.get(name) for name in
                  ("claim_id", "owner", "state", "rung")},
        "town_plan": row.get("town_plan"),
        "shop_selector": {name: selector.get(name) for name in
                          ("winning_rung", "wanted_purchase", "rejection_reason")},
        "procurement_requirements": row.get("procurement_requirements"),
        "fundraising": row.get("fundraising"),
        "gold": (row.get("player") or {}).get("gold"),
    }


def main() -> None:
    for path, digest in SOURCE_SHA256.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
    rows_all = [json.loads(line) for line in _lines(DECISIONS)]
    start = next(i for i, row in enumerate(rows_all)
                 if row.get("kind") == "session-start"
                 and row.get("time") == SESSION_START)
    assert rows_all[start]["git_commit"] == "155e2829"
    decisions = rows_all[start + 1:start + 2 + LAST_INDEX]
    # Decision indices, not decision_sequence: five floor-change decisions
    # repeat the previous sequence number (1391 rows, sequences 0..1385).
    assert len(decisions) == LAST_INDEX + 1
    assert all("kind" not in row for row in decisions)
    assert decisions[-1]["decision_sequence"] == 1385
    assert decisions[-1]["reason"] == "town:blocked:owner-retired"
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
        assert segment, index
        assert json.loads(segment[-1])["turn"] == decisions[index]["turn"], index
    payload = "".join(
        line.replace("\r\n", "\n") for segment in segments for line in segment
    )
    OUTPUT.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    boundaries = {
        "source": {
            path.name: digest for path, digest in SOURCE_SHA256.items()
        },
        "session_start": SESSION_START,
        "state_rows": [first, ends[-1]],
        "input_rows": [len(segment) for segment in segments],
        "recorded_fields": [
            "decision_sequence", "turn", "key", "reason", "position", "floor",
        ],
        "recorded": [
            [row["decision_sequence"], row["turn"], row["key"], row["reason"],
             [row["position"]["y"], row["position"]["x"]],
             [row["floor"]["dungeon_id"], row["floor"]["level"]]]
            for row in decisions
        ],
        "detail": {str(index): _detail(decisions[index])
                   for index in DETAIL_INDEXES},
    }
    BOUNDARIES.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    for path in (OUTPUT, BOUNDARIES):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
