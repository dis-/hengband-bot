"""Extract the issue #77 pin (c4-a life-014, 2026-10-19 08:13 capture).

Capture 20261019-081331-store-leave-key-suppressed (219 decision rows, 116
state rows).  Keeps, for decision rows 3666-3675, the raw state.jsonl lines
that ``_segments`` assigns to each row (the segmentation of
test_supply_shortfall_owner_recorded), the recorded decision metadata of
those rows and of the final row 3681, and the ``~f`` skill list (state row
67).  Raw lines are stored unchanged (UTF-8 strings).
"""
import gzip
import json
import sys
from pathlib import Path

CAPTURE = Path(
    r"C:\hengband-backups\state-logs\c4a-loops-20261016"
    r"\20261019-081331-store-leave-key-suppressed"
)
FIRST, LAST, FINAL = 3666, 3675, 3681
SKILL_ROW = 67


def _lines(name: str) -> list[str]:
    with gzip.open(CAPTURE / name, "rt", encoding="utf-8") as stream:
        return list(stream)


def main(target: Path) -> None:
    sys.path[:0] = [str(Path(__file__).parent)]
    from test_supply_shortfall_owner_recorded import _segments

    lines = _lines("state.jsonl.gz")
    rows = [json.loads(line) for line in _lines("bot-decisions.jsonl.gz")]
    rows = [row for row in rows if "decision_sequence" in row]
    decisions = [
        {
            "row": index, "decision_sequence": row["decision_sequence"],
            "turn": row["turn"], "key": row["key"], "reason": row["reason"],
            "store_type": row["store_type"],
            "drained": int((row.get("timing") or {}).get("jsonl_drain_records") or 0),
        }
        for index, row in enumerate(rows)
    ]
    segments = [
        {"decision": decisions[index], "state_rows": [start, end],
         "lines": lines[start:end]}
        for index, start, end in _segments(lines, decisions)
        if FIRST <= decisions[index]["decision_sequence"] <= LAST
    ]
    final = next(row for row in rows if row["decision_sequence"] == FINAL)
    out = {
        "source": CAPTURE.name,
        "segments": segments,
        "final": {
            "decision_sequence": FINAL, "turn": final["turn"],
            "key": final["key"], "reason": final["reason"],
            "store_type": final["store_type"],
            "store_visit": final["store_visit"],
            "inventory": final["inventory"],
            "gold": final["player"]["gold"],
        },
        "skill_line": lines[SKILL_ROW],
    }
    target.write_bytes(gzip.compress(
        json.dumps(out, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
