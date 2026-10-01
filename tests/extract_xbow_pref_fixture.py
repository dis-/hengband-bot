"""Freeze the live sling/Home Light Crossbow boards used by the xbow-pref pins.

Source (read-only): jsonlog/autorecover-20261002-012442-no-key-exhausted.
bot-state-fixed.jsonl.gz.  Rows are 1-based line numbers of that capture:
29/30 = Home list pages 0/52 at turn 2320564 (page 52 holds the Light
Crossbow (+4,+3)), 44 = General Store page (plain bolts), 56 = Weapon Smith
page (plain bolts), 95 = last town-surface board (Sling (+10,+10), 99 shots).
"""
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROWS = (29, 30, 44, 56, 95)


def extract(log_directory):
    stem = "autorecover-20261002-012442-no-key-exhausted"
    source_path = log_directory / f"{stem}.bot-state-fixed.jsonl.gz"
    with gzip.open(source_path, "rb") as source:
        lines = source.read().splitlines()
    payload = {
        "source": f"{stem}.bot-state-fixed.jsonl.gz",
        "rows": {str(row): json.loads(lines[row - 1]) for row in ROWS},
    }
    body = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf8")
    target = Path(__file__).parent / "fixtures/xbow-pref-live-20261002-012442.json.gz"
    target.write_bytes(gzip.compress(body, mtime=0))
    print(hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    extract(Path(sys.argv[1]))
