"""Freeze the two calibration travel incident boards without altering screens."""
import gzip
import hashlib
import json
from pathlib import Path
import sys


def extract(log_directory):
    stem = "incident-20261001-2157-holder-silent-calibration-deposit-travel"
    with gzip.open(log_directory / f"{stem}.state.jsonl.gz", "rt", encoding="utf8") as source:
        rows = list(map(json.loads, source))
    with gzip.open(log_directory / f"{stem}.decisions.jsonl.gz", "rt", encoding="utf8") as source:
        decisions = [row for row in map(json.loads, source)
                     if row.get("decision_sequence") in (4676, 4677)]
    boards = [row for row in rows if row.get("type") == "player_turn"
              and row.get("turn") in (1722292, 1722384)]
    payload = {
        "boards": boards[-2:],
        "decisions": [{name: row[name] for name in
                       ("decision_sequence", "turn", "key", "reason")}
                      for row in decisions],
    }
    body = (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf8")
    target = Path(__file__).parent / "fixtures/caltravel-20261001.json.gz"
    target.write_bytes(gzip.compress(body, mtime=0))
    print(hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    extract(Path(sys.argv[1]))
