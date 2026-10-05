"""Freeze the 17:21/17:22 owner stops from the named backup only."""
import gzip
import hashlib
import json
from pathlib import Path


BACKUP = Path(r"C:\hengband-backups\state-logs\owner-retired-20261005-1721")
OUTPUT = Path(__file__).parent / "fixtures/owner-retired-class2-20261005.json.gz"


def extract():
    pins = {}
    for stamp in ("172143", "172225"):
        pin = {"sources": {}}
        for kind in ("decisions", "state-fixed"):
            path = next(BACKUP.glob(f"*{stamp}*.bot-{kind}.jsonl.gz"))
            pin["sources"][kind] = {
                "name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            with gzip.open(path, "rt", encoding="utf-8-sig") as stream:
                rows = [{"line": line, "row": json.loads(text)}
                        for line, text in enumerate(stream, 1)]
            pin[kind] = rows[-18:] if kind == "decisions" else rows
        pins[stamp] = pin
    OUTPUT.write_bytes(gzip.compress(json.dumps(
        {"backup": str(BACKUP), "pins": pins}, ensure_ascii=False,
    ).encode("utf-8"), mtime=0))
    print(hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    extract()
