"""Freeze only the live36 incident's departure seam; sources stay read-only."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("C:/hengband/bot-client/incident-captures/20261001-145837-departure-unsatisfiable")
OUTPUT = ROOT / "tests/fixtures/live36-weight.json"


def main():
    snapshot_path = SOURCE / "snapshots/snapshots-current.jsonl.gz"
    with gzip.open(snapshot_path, "rt", encoding="utf8") as stream:
        boards = list(map(json.loads, stream))
    decisions = []
    for line in (SOURCE / "decision-tail.jsonl").read_text(encoding="utf8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The tail begins mid-record.
        if 7514 <= row.get("decision_sequence", -1) <= 7520:
            decisions.append(row)
    home = next(row for row in reversed(boards)
                if (row.get("store") or {}).get("store_type") == 7)
    stop = next(row for row in reversed(boards)
                if row["turn"] == decisions[-1]["turn"] and row["type"] == "player_turn")
    state_path = SOURCE / "policy-state.json"
    state = json.loads(state_path.read_text(encoding="utf8"))
    fixture = {
        "source": str(SOURCE),
        "source_sha256": {str(path.relative_to(SOURCE)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (snapshot_path, SOURCE / "decision-tail.jsonl", state_path)},
        "stop": stop,
        "home": home,
        "shelves": state["modes_and_latches"]["_town_supplier_stock"],
        "decisions": decisions,
        "attachment": {
            "home_knowledge_current": state["state"]["_home_knowledge_current"],
            "town_store_attempted": state["modes_and_latches"]["_town_store_attempted"],
            "fundraising_mode": state["modes_and_latches"]["_fundraising_mode"],
            "purchases": state["modes_and_latches"]["_town_visit_purchases"],
            "abandoned_carry": state["modes_and_latches"]["_abandoned_quest_carry_requirements"],
            "stock_observations": state["modes_and_latches"]["_town_supplier_stock_observations"],
        },
    }
    OUTPUT.write_text(json.dumps(fixture, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf8")
    print(hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
