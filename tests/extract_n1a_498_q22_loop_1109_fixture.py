"""Build tests/fixtures/n1a-498-q22-loop-1109.json.gz from n1-a life-498's captures.

Source (read-only copies of the server captures):
C:/hengband-backups/pdca/captures/n1a-498-q22-loop-1109/
  captures/20261109-1224{38,55}-, 20261109-122512-loop-detected/bot-decisions.jsonl.gz
  incident-captures/20261109-122507-loop-detected/snapshots/snapshots-current.jsonl.gz
The last snapshot ring covers turns 713315..726761, i.e. all three runs.

Selection: per run, every recorded decision of that bot process (run 1 from the
first row of its capture's decision tail, runs 2 and 3 from the restarted
process's first decision) up to the loop-detected stop, each with the first
player_turn board of its turn.  Grid maps are stored once and referenced.
The character calibration is the town-arrival sidecar of the first incident capture.
"""
import gzip
import hashlib
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/captures/n1a-498-q22-loop-1109")
CAPTURES = ("20261109-122438", "20261109-122455", "20261109-122512")
RING = (SOURCE / "incident-captures/20261109-122507-loop-detected/snapshots"
        / "snapshots-current.jsonl.gz")
CALIBRATION = (SOURCE / "incident-captures/20261109-122437-loop-detected/town-arrival"
               / "sidecars/_character_calibration_path")
OUT = Path(__file__).with_name("fixtures") / "n1a-498-q22-loop-1109.json.gz"


def decisions(capture):
    path = SOURCE / "captures" / f"{capture}-loop-detected" / "bot-decisions.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    # Restarted processes: the rows after the last process-start marker.
    starts = [index for index, row in enumerate(rows) if "position" not in row]
    if starts:
        rows = rows[starts[-1] + 1:]
    return [
        {key: row[key] for key in ("decision_sequence", "turn", "key", "reason")}
        | {"position": [row["position"]["y"], row["position"]["x"]]}
        for row in rows if row.get("reason") != "loop-detected"
    ]


def main():
    boards = {}
    with gzip.open(RING, "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            board = json.loads(line)
            if board.get("type") == "player_turn":
                boards.setdefault(board["turn"], board)
    grid_maps = {}
    runs = []
    for capture in CAPTURES:
        rows = decisions(capture)
        run_boards = []
        for row in rows:
            board = json.loads(json.dumps(boards[row["turn"]]))
            text = json.dumps(board["grid_map"], sort_keys=True)
            digest = hashlib.sha256(text.encode()).hexdigest()[:16]
            grid_maps.setdefault(digest, board["grid_map"])
            board["grid_map"] = digest
            run_boards.append(board)
        runs.append({"capture": capture, "decisions": rows, "boards": run_boards})
    payload = {
        "runs": runs,
        "grid_maps": grid_maps,
        "calibration": json.loads(CALIBRATION.read_text(encoding="utf-8")),
    }
    with gzip.open(OUT, "wt", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUT, OUT.stat().st_size, [len(run["boards"]) for run in runs], len(grid_maps))


if __name__ == "__main__":
    main()
