"""Extract the issue #64 pin (c4-a, 2026-10-18 09:15:16 owner-retired burst).

Keeps the raw state.jsonl lines of the capture up to the board after the
pinned Home page, the recorded decision metadata (sequence, turn, key,
reason, drained record count) up to that board, and two knowledge rows of the
same character from earlier captures: the complete Home list (083222 state
row 46) and the ``~f`` skill list (074006 state row 7).  Raw lines are stored
unchanged (UTF-8 strings).
"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\hengband-backups\state-logs\c4a-loops-20261016")
CAPTURE = "20261018-091516-town-blocked-owner-retired-burst"
HOME = ("20261018-083222-town-blocked-owner-retired-burst", 46)
SKILL = ("20261018-074006-loop-detected", 7)
LAST_DECISION = 93


def _lines(directory: str, name: str = "state.jsonl.gz") -> list[str]:
    with gzip.open(ROOT / directory / name, "rt", encoding="utf-8") as stream:
        return list(stream)


def main(target: Path) -> None:
    lines = _lines(CAPTURE)
    rows = [json.loads(line) for line in _lines(CAPTURE, "bot-decisions.jsonl.gz")]
    rows = [row for row in rows if "decision_sequence" in row]
    decisions = [
        {
            "row": index, "decision_sequence": row["decision_sequence"],
            "turn": row["turn"], "key": row["key"], "reason": row["reason"],
            "drained": int((row.get("timing") or {}).get("jsonl_drain_records") or 0),
        }
        for index, row in enumerate(rows) if index <= LAST_DECISION
    ]
    turns = [json.loads(line)["turn"] for line in lines]
    last = max(i for i, turn in enumerate(turns)
               if turn <= rows[LAST_DECISION]["turn"])
    out = {
        "source": CAPTURE,
        "lines": lines[: last + 1],
        "decisions": decisions,
        "home_line": _lines(HOME[0])[HOME[1]],
        "skill_line": _lines(SKILL[0])[SKILL[1]],
    }
    target.write_bytes(gzip.compress(
        json.dumps(out, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
