"""Extract stop boards from the immutable October 3 overflow captures.

Usage: python tests/extract_town_overflow_fixture.py <capture-directory>
Reads only the named captures; never consults a running bot's logs.
"""

import gzip
import hashlib
import json
from pathlib import Path
import sys


def extract(directory: Path, destination: Path) -> None:
    records = []
    for stamp in ("141604", "141633", "141702"):
        def rows(kind):
            source = next(directory.glob(f"*{stamp}*{kind}*gz"))
            with gzip.open(source, "rt", encoding="utf-8") as stream:
                return [json.loads(line) for line in stream]

        decision = [row for row in rows("decisions") if row.get("reason") ==
                    "town:blocked:overflow-no-legal-disposal"][-1]
        board = [row for row in rows("state-fixed") if row.get("turn") ==
                 decision["turn"]][-1]
        fields = (
            "decision_sequence", "turn", "reason", "key", "fundraising",
            "retention_reservations", "procurement_requirements", "position",
            "home_scan", "town_plan", "identification_need", "home_candidate_waiting",
        )
        records.append({
            "capture": stamp, "board": board,
            "decision": {key: decision[key] for key in fields},
        })
    with destination.open("wb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as stream:
            stream.write(json.dumps(records, ensure_ascii=True,
                                    separators=(",", ":")).encode())
    print(destination, hashlib.sha256(destination.read_bytes()).hexdigest())


if __name__ == "__main__":
    extract(Path(sys.argv[1]), Path(__file__).parent / "fixtures" /
            "town-overflow-20261003.json.gz")
