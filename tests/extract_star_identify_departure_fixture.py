"""Freeze the 07:16 star-identify stop from archived copies only.

No live logs, game files, or other worktrees are accessed. Rows are addressed
by their one-based physical archive line (decision 38 is line 267 because the
archive contains earlier processes too). Gzip headers use a fixed timestamp.
"""

import gzip
import hashlib
import json
from pathlib import Path


BACKUP = Path("C:/hengband-backups/state-logs/s33-phase2b-shadow-20261004")
PREFIX = "autorecover-20261005-071639-town-blocked-departure-unsatisfiable"
OUT = Path(__file__).parent / "fixtures/star-identify-departure-20261005.json.gz"


def main():
    state = BACKUP / (PREFIX + ".bot-state-fixed.jsonl.gz")
    decisions = BACKUP / (PREFIX + ".bot-decisions.jsonl.gz")
    with gzip.open(state, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    with gzip.open(decisions, "rt", encoding="utf-8") as stream:
        trace = [json.loads(line) for line in stream]
    assert len(rows) == 74 and len(trace) == 267
    assert rows[73]["turn"] == 10612593
    assert rows[70]["knowledge"]["category"] == "home"
    assert rows[62]["store"]["store_type"] == 4
    assert rows[8]["knowledge"]["category"] == "skill_exp"
    assert trace[-1]["decision_sequence"] == 38
    capture = {
        "source": {
            "state_file": state.name,
            "state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
            "decisions_file": decisions.name,
            "decisions_sha256": hashlib.sha256(decisions.read_bytes()).hexdigest(),
        },
        "board": rows[73], "character": rows[72], "skills": rows[8],
        "knowledge": rows[70], "alchemist": rows[62],
        "pins": [
            {key: row[key] for key in (
                "time", "decision_sequence", "turn", "reason", "key",
                "home_candidate_waiting", "identification_need", "procurement_requirements",
            ) if key in row}
            | {"departure_block": row.get("departure_block"),
               "shop_selector": row.get("shop_selector")}
            for row in trace[-11:]
        ],
        "deferred_home_item_signatures": trace[-1]["equipment_optimization"][
            "deferred_home_item_signatures"],
        "town_ledger": trace[-1]["departure_block"]["town_ledger"],
    }
    with OUT.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(json.dumps(capture, ensure_ascii=True,
                                        separators=(",", ":")).encode("utf-8"))
    print(OUT.name, hashlib.sha256(OUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
