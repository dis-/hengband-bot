"""Extract the D34 recorded-session pins (viewing bots, 2026-10-30).

Each capture holds two bot sessions; the last one (a restart after the same
stop) is kept whole: its raw state.jsonl lines (from its first board), the
metadata of its decision rows, the recorded final row and the last stdout and
stderr lines.  Raw lines are stored unchanged (UTF-8 strings).

  store-exit  n1-b life-254 20261030-091901-store-leave-key-suppressed
              (decision rows 0-31, state rows from 58)
  bounty      n1-a life-420 20261030-034617-stuck-prompt-bounty-cashout
              (decision rows 0-4, state rows from 45)
  library     n1-a life-433 20261030-144719-stuck-prompt-town-morivant-full-identify-library
              (one session tail, decision rows 7568-7692, state rows 0-71: row 72
              is already the board after the final step onto the Library)

usage: extract_d34_session_fixtures.py <case> <target .json.gz>
"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\hengband-backups\pdca\captures\unfixed-24h-1031")
CASES = {
    "store-exit": ("n1-b/life-254/captures/20261030-091901-store-leave-key-suppressed", 58, None),
    "bounty": ("n1-a/life-420/captures/20261030-034617-stuck-prompt-bounty-cashout", 45, None),
    "library": ("n1-a/life-433/captures/"
                "20261030-144719-stuck-prompt-town-morivant-full-identify-library", 0, 72),
}


def _lines(capture: Path, name: str) -> list[str]:
    with gzip.open(capture / name, "rt", encoding="utf-8") as stream:
        return list(stream)


def main(case: str, target: Path) -> None:
    relative, first_state_row, end_state_row = CASES[case]
    capture = ROOT / relative
    rows = []
    for line in _lines(capture, "bot-decisions.jsonl.gz"):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append(None)  # the previous session's torn tail
    start = max((index for index, row in enumerate(rows)
                 if row is not None and row.get("decision_sequence") == 0), default=0)
    rows = [row for row in rows[start:] if row is not None and "decision_sequence" in row]
    decisions = [
        {
            "decision_sequence": row["decision_sequence"], "turn": row["turn"],
            "key": row["key"], "reason": row["reason"], "store_type": row["store_type"],
            "position": row["position"],
            "drained": int((row.get("timing") or {}).get("jsonl_drain_records") or 0),
        }
        for row in rows
    ]
    final = rows[-1]
    out = {
        "source": relative,
        "lines": _lines(capture, "state.jsonl.gz")[first_state_row:end_state_row],
        "decisions": decisions,
        "final": {
            "decision_sequence": final["decision_sequence"], "turn": final["turn"],
            "key": final["key"], "reason": final["reason"],
            "store_type": final["store_type"], "store_visit": final["store_visit"],
        },
        "stdout_tail": (capture / "bot-stdout.log").read_text(encoding="utf-8").splitlines()[-1],
        "stderr_tail": (capture / "bot-stderr.log").read_text(encoding="utf-8").splitlines()[-1],
    }
    target.write_bytes(gzip.compress(
        json.dumps(out, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
