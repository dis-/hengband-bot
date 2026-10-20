"""Extract the identify-staff stockout kit pin (c4-a life-014, 2026-10-20 14:00).

Capture 20261020-140000-town-blocked-departure-unsatisfiable (99 decision
rows, 77 state rows).  Keeps the raw state.jsonl lines that decision row 98
(decision_sequence 115, the recorded ``town:blocked:departure-unsatisfiable``)
drained, the recorded decision metadata of rows 96-98, the recorded
fundraising / departure block / procurement requirements / in-store telemetry
of row 98, the confirmed sale messages of row 35 (decision_sequence 52: six
Treasure Detection scrolls sold to the Alchemist), and the complete Home list
of state row 71 (turn 3089994).

Three rows come from other captures of the same life (the 14:00 capture holds
neither shop page nor a skill list): the Alchemist page of capture
20261020-135723 state row 89 (turn 3086706, 90 Treasure Detection scrolls),
the Magic Shop page of the same capture state row 95 (turn 3086865), and the
``~f`` skill list of capture 20261020-103021 state row 7.  Raw lines are stored
unchanged (UTF-8 strings).
"""
import gzip
import json
import sys
from pathlib import Path

CAPTURES = Path(r"C:\hengband-backups\state-logs\c4a-loops-20261016")
CAPTURE = CAPTURES / "20261020-140000-town-blocked-departure-unsatisfiable"
SHOP_CAPTURE = CAPTURES / "20261020-135723-town-blocked-departure-unsatisfiable"
SKILL_CAPTURE = CAPTURES / "20261020-103021-town-blocked-departure-unsatisfiable"
FIRST, PIN, SALE_ROW = 96, 98, 35
HOME_ROW, ALCHEMIST_ROW, MAGIC_ROW, SKILL_ROW = 71, 89, 95, 7


def _lines(capture: Path, name: str) -> list[str]:
    with gzip.open(capture / name, "rt", encoding="utf-8") as stream:
        return list(stream)


def main(target: Path) -> None:
    sys.path[:0] = [str(Path(__file__).parent)]
    from test_supply_shortfall_owner_recorded import _segments

    lines = _lines(CAPTURE, "state.jsonl.gz")
    rows = [json.loads(line) for line in _lines(CAPTURE, "bot-decisions.jsonl.gz")]
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
    start, end = spans[PIN]
    recorded = {
        key: rows[PIN].get(key)
        for key in ("fundraising", "departure_block", "procurement_requirements",
                    "player", "in_store")
    }
    shop_lines = _lines(SHOP_CAPTURE, "state.jsonl.gz")
    out = {
        "source": CAPTURE.name,
        "lines": lines[start:end],
        "decisions": decisions[FIRST:PIN + 1],
        "recorded": recorded,
        "sale_messages": rows[SALE_ROW]["messages"],
        "sale_sequence": rows[SALE_ROW]["decision_sequence"],
        "home_line": lines[HOME_ROW],
        "alchemist_line": shop_lines[ALCHEMIST_ROW],
        "magic_line": shop_lines[MAGIC_ROW],
        "skill_line": _lines(SKILL_CAPTURE, "state.jsonl.gz")[SKILL_ROW],
    }
    target.write_bytes(gzip.compress(
        json.dumps(out, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
