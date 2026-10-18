"""Extract the issue #76 pin (c4-a life-014, 2026-10-19 08:04 hard stop).

Capture 20261019-080433-town-blocked-departure-unsatisfiable (151 decision
rows, 103 state rows).  Keeps the raw state.jsonl lines that decision rows
144-150 drained (travel to the Armoury, the sale that lifts gold to 2,708,
the periodic save/dump and the recorded ``town:blocked:departure-
unsatisfiable`` hard stop), the recorded decision metadata of those rows, the
recorded fundraising / departure block / procurement requirements of row 148
(the only row that logs ``departure_block``), and two knowledge rows of the
same capture: the ``~f`` skill list (state row 10) and the complete Home list
(state row 79, turn 659988).  Raw lines are stored unchanged (UTF-8 strings).
"""
import gzip
import json
import sys
from pathlib import Path

CAPTURE = Path(
    r"C:\hengband-backups\state-logs\c4a-loops-20261016"
    r"\20261019-080433-town-blocked-departure-unsatisfiable"
)
FIRST, LAST, BLOCK_ROW = 144, 150, 148
SKILL_ROW, HOME_ROW, MAGIC_ROW = 10, 79, 28


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
            "drained": int((row.get("timing") or {}).get("jsonl_drain_records") or 0),
        }
        for index, row in enumerate(rows)
    ]
    spans = {index: (start, end) for index, start, end in _segments(lines, decisions)}
    start, end = spans[FIRST][0], spans[LAST][1]
    recorded = {
        key: rows[BLOCK_ROW].get(key)
        for key in ("fundraising", "town_plan", "departure_block",
                    "procurement_requirements", "player")
    }
    out = {
        "source": CAPTURE.name,
        "lines": lines[start:end],
        "decisions": decisions[FIRST:LAST + 1],
        "recorded": recorded,
        "ledger": rows[BLOCK_ROW]["departure_block"]["town_ledger"],
        "home_line": lines[HOME_ROW],
        "skill_line": lines[SKILL_ROW],
        "magic_line": lines[MAGIC_ROW],
    }
    target.write_bytes(gzip.compress(
        json.dumps(out, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
