"""Extract the fixture of n1-b life-348's quest-search lap on Angband 62F (RANDOM quest 46, 2026-11-08).

Input: the capture directory C:\\hengband-backups\\pdca\\captures\\n1b-348-62f-loop-1108 with
state-tail.jsonl.gz (the last boards, 16:18), policy-state.json (the live checkpoint of 16:18),
decisions-tail.jsonl.gz (16:09:33-16:18:28) and exploration-ledger-1630.json (the floor's
ledger, copied at 16:30).  Output: the last board, the checkpoint's remembered terrain, the
ledger's mapped areas, and every decision row reduced to the replayed fields.
"""
import gzip
import json
import lzma
from pathlib import Path
import sys

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-62f-quest-cover-1108.json.xz"
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position", "messages")
TERRAIN = ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t", "upstairs")


def _rows(path: Path) -> list:
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def extract(capture: Path) -> dict:
    checkpoint = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))
    ledger = json.loads((capture / "exploration-ledger-1630.json").read_text(encoding="utf-8"))
    return {
        "board": _rows(capture / "state-tail.jsonl.gz")[-1],
        "terrain": {name: checkpoint["terrain"][name] for name in TERRAIN},
        "mapped_areas": ledger["mapped_areas"],
        "decisions": [{name: row[name] for name in DECISION_FIELDS}
                      for row in _rows(capture / "decisions-tail.jsonl.gz")],
    }


if __name__ == "__main__":
    pin = extract(Path(sys.argv[1]))
    payload = json.dumps(pin, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(payload.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, len(pin["decisions"]))
