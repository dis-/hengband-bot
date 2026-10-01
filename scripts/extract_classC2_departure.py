"""Freeze recorded Class C2 boards and the explicit departure attachment."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("C:/hengband/bot-client/incident-captures/20261001-161643-departure-unsatisfiable")
LOG = Path("C:/hengband/bot-client/jsonlog/incident-20261001-1616-departure-unsatisfiable-3")


def main():
    paths = [Path(str(LOG) + suffix) for suffix in
             (".decisions.jsonl.gz", ".state.jsonl.gz")]
    state_path = SOURCE / "policy-state.json"
    calibration_path = LOG.parent / "character-calibration.json"
    confirmed_path = LOG.parent / "confirmed-loadout.json"
    state = json.loads(state_path.read_text(encoding="utf8"))
    with gzip.open(paths[0], "rt", encoding="utf8") as stream:
        decisions = [row for line in stream if
                     (row := json.loads(line)).get("decision_sequence", 0) >= 11397]
    turns = {row["turn"] for row in decisions}
    boards = []
    knowledge = {}
    with gzip.open(paths[1], "rt", encoding="utf8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("type") == "knowledge":
                knowledge[row["knowledge"]["category"]] = row
            if row.get("turn") in turns:
                boards.append(row)
    fixture = {"source": str(LOG), "source_sha256": {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [*paths, state_path, calibration_path, confirmed_path]},
        "calibration": json.loads(calibration_path.read_text(encoding="utf8")),
        "confirmed": json.loads(confirmed_path.read_text(encoding="utf8")),
        "knowledge": knowledge,
        "boards": boards, "decisions": decisions, "state": state}
    output = ROOT / "tests/fixtures/classC2-departure-20261001.json.gz"
    data = json.dumps(fixture, ensure_ascii=False, separators=(",", ":")).encode("utf8")
    output.write_bytes(gzip.compress(data, mtime=0))
    print(output, hashlib.sha256(output.read_bytes()).hexdigest(), len(boards), len(decisions))


if __name__ == "__main__":
    main()
