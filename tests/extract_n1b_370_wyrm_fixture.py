r"""Extract the n1-b life-370 Venom Wyrm board (2026-11-11 23:30:54, turn 8344271).

Source (copied from the soak server, ~/hengbot-soak/n1-b/life-370/jsonlog/):
C:\hengband-backups\pdca\captures\n1b-370-wyrm-t1-1111\
- snapshots-20261111-233232-1ec4c4.jsonl.gz, line 5401: the board the decision read;
- decision-54432.json: the decision row (bot-decisions.jsonl.1, decision_sequence 54432).

Kept: the raw board line unchanged and the row's sequence, turn, key, reason and its
``threat_tiers`` telemetry (the reading the bot made then).
"""
import gzip
import json
import sys
from pathlib import Path

SOURCE = Path(r"C:\hengband-backups\pdca\captures\n1b-370-wyrm-t1-1111")
SNAPSHOTS = "snapshots-20261111-233232-1ec4c4.jsonl.gz"
LINE = 5401
DECISION = "decision-54432.json"


def main(target: Path) -> None:
    with gzip.open(SOURCE / SNAPSHOTS, "rt", encoding="utf-8") as stream:
        board = next(line for number, line in enumerate(stream, 1) if number == LINE)
    row = json.loads((SOURCE / DECISION).read_text(encoding="utf-8"))
    out = {
        "source": f"n1-b life-370 jsonlog/snapshots/{SNAPSHOTS} line {LINE}",
        "board": board,
        "decision": {name: row[name] for name in
                     ("decision_sequence", "turn", "key", "reason", "threat_tiers")},
    }
    target.write_bytes(gzip.compress(json.dumps(out, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
