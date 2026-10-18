"""Extract the issue #66 recurrence pin (c4-a, 2026-10-19 00:50 manual capture).

Capture 20261019-0050-manual-town-wander (last 3000 decision rows and the
last 387 state rows before the pause).  Keeps the raw state.jsonl lines that
decision rows 2547-2548 drained (the first two ``stuck:wander`` rows after the
Temple visit, gold 1,587), the recorded decision metadata of those rows and
of the recorded town plan / fundraising / departure block, the recorded town
ledger of decision row 2544 (the last row before 2547 that logs it), and two
knowledge rows of the same capture: the ``~f`` skill list (state row 1) and
the complete Home list (state row 112, turn 2945295).  Raw lines are stored
unchanged (UTF-8 strings).
"""
import gzip
import json
import sys
from pathlib import Path

CAPTURE = Path(
    r"C:\hengband-backups\state-logs\c4a-loops-20261016"
    r"\20261019-0050-manual-town-wander"
)
FIRST, LAST, LEDGER_ROW = 2547, 2548, 2544
SKILL_ROW, HOME_ROW = 1, 112


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
        key: rows[FIRST][key]
        for key in ("fundraising", "town_plan", "departure_block",
                    "procurement_requirements", "player")
    }
    out = {
        "source": CAPTURE.name,
        "lines": lines[start:end],
        "decisions": decisions[FIRST:LAST + 1],
        "recorded": recorded,
        "ledger": rows[LEDGER_ROW]["departure_block"]["town_ledger"],
        "home_line": lines[HOME_ROW],
        "skill_line": lines[SKILL_ROW],
    }
    target.write_bytes(gzip.compress(
        json.dumps(out, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
