"""Freeze only the three input boards at the live32 shop-leave seam."""
import gzip
import hashlib
import json
from pathlib import Path

SOURCE = Path(r"C:\hengband\bot-client\jsonlog\incident-20261001-1341-s33-on-gate-missing-town-plan")
DEST = Path(__file__).parent / "fixtures/live32-shop-leave"


def main():
    DEST.mkdir(exist_ok=True)
    rows = []
    with gzip.open(str(SOURCE) + ".decisions.jsonl.gz", "rt", encoding="utf8") as stream:
        for line_number, line in enumerate(stream, 1):
            row = json.loads(line)
            if 4215 <= row.get("decision_sequence", 0) <= 4217:
                rows.append(row)
    boards = []
    skills = None
    turns = {row["turn"] for row in rows}
    with gzip.open(str(SOURCE) + ".state.jsonl.gz", "rt", encoding="utf8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("knowledge", {}).get("skills") and row.get("turn", 0) <= max(turns):
                skills = {"knowledge": row["knowledge"], "player": row["player"]}
            if row.get("turn") in turns:
                boards.append(row)
    for name, data in (("decisions.jsonl.gz", rows), ("state.jsonl.gz", boards)):
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data).encode("utf8")
        (DEST / name).write_bytes(gzip.compress(payload, mtime=0))
    (DEST / "skills.json").write_text(json.dumps(skills, indent=2) + "\n", encoding="utf8")
    provenance = {"source": str(SOURCE), "sequences": [4215, 4216, 4217],
                  "fixture_sha256": {name: hashlib.sha256((DEST / name).read_bytes().replace(b"\r\n", b"\n")
                                                          if name.endswith(".json") else (DEST / name).read_bytes()).hexdigest()
                                     for name in ("decisions.jsonl.gz", "state.jsonl.gz", "skills.json")},
                  "source_sha256": {suffix: hashlib.sha256(Path(str(SOURCE) + "." + suffix + ".jsonl.gz").read_bytes()).hexdigest()
                                    for suffix in ("decisions", "state", "ownership-claims", "posted-characters")}}
    (DEST / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
