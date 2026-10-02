"""Copy independent incident seams; never write to recorder-owned jsonlog."""
import gzip
import hashlib
import json
from pathlib import Path

SOURCE = Path(r"C:\hengband\bot-client\jsonlog")
DEST = Path(__file__).parent / "fixtures/tpstockout-20261002.json.gz"


def main():
    sources = {}
    boards = []
    decisions = []
    for stamp in ("023427", "023556"):
        for kind in ("state-fixed", "decisions"):
            name = f"autorecover-20261002-{stamp}-loop-detected.bot-{kind}.jsonl.gz"
            data = (SOURCE / name).read_bytes()
            sources[name] = hashlib.sha256(data).hexdigest()
            rows = [json.loads(line) for line in gzip.decompress(data).decode("utf8").splitlines()]
            if kind == "state-fixed":
                boards.extend(rows)
            elif stamp == "023556":
                decisions.extend(rows)
    stop = next(row for row in reversed(decisions)
                if row.get("reason") == "town:blocked:no-actionable-claim-owner")
    board = next(row for row in reversed(boards)
                 if row.get("type") == "player_turn" and row["turn"] == stop["turn"])
    shelves = {}
    knowledge = {}
    for row in boards:
        if row.get("turn", 0) > stop["turn"]:
            continue
        if row.get("store"):
            shelves[str(row["store"]["store_type"])] = row
        if row.get("knowledge"):
            knowledge[row["knowledge"]["category"]] = row["knowledge"]
    calibration_data = (SOURCE / "character-calibration.json").read_bytes()
    sources["character-calibration.json (mtime 2026-10-02 01:25:22)"] = hashlib.sha256(calibration_data.replace(b"\r\n", b"\n")).hexdigest()
    capture = dict(sources=sources, calibration=json.loads(calibration_data), board=board, decision=stop,
                   shelves=shelves, knowledge=knowledge)
    data = json.dumps(capture, ensure_ascii=False, sort_keys=True).encode("utf8")
    DEST.write_bytes(gzip.compress(data, mtime=0))
    print(DEST.name, hashlib.sha256(DEST.read_bytes()).hexdigest())
    print("knowledge", list(knowledge), "shelves", list(shelves))


if __name__ == "__main__":
    main()
