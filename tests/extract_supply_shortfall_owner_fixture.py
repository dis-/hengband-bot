"""Extract the October 18 supply-shortfall pins (c4-a life-012, bot d667f466).

Keeps, per capture, the raw state.jsonl lines up to the pinned decision and
the recorded decision metadata (sequence, turn, key, reason, drained record
count) the replay needs. Raw lines are stored unchanged (UTF-8 strings).
"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\hengband-backups\state-logs\c4a-loops-20261016")
CAPTURES = {
    # name: (directory, Home knowledge row, pinned decision row)
    "teleport-0316": ("20261018-031620-town-blocked-owner-retired-burst", 52, 124),
    "idstaff-0353": ("20261018-035319-town-blocked-owner-retired-burst", 18, 141),
}
SKILL = ("20261018-031620-town-blocked-owner-retired-burst", 20)


def main(target: Path) -> None:
    out = {"captures": {}}
    for name, (directory, home_row, pin) in CAPTURES.items():
        source = ROOT / directory
        with gzip.open(source / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
            lines = list(stream)
        with gzip.open(source / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        rows = [row for row in rows if "decision_sequence" in row]
        decisions = [
            {
                "row": index, "decision_sequence": row["decision_sequence"],
                "turn": row["turn"], "key": row["key"], "reason": row["reason"],
                "drained": int((row.get("timing") or {}).get("jsonl_drain_records") or 0),
            }
            for index, row in enumerate(rows) if index <= pin
        ]
        turns = [json.loads(line)["turn"] for line in lines]
        last = max(i for i, turn in enumerate(turns) if turn <= rows[pin]["turn"])
        out["captures"][name] = {
            "source": directory, "home_row": home_row, "pin": pin,
            "lines": lines[: max(last + 1, home_row + 1)],
            "decisions": decisions,
        }
    with gzip.open(ROOT / SKILL[0] / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        out["skill_line"] = list(stream)[SKILL[1]]
    target.write_bytes(gzip.compress(
        json.dumps(out, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
