"""Extract tests/fixtures/worthless-sale-20261103.json.gz.

Source: n1-c life-116, 2026-11-03 11:57 stuck-prompt:shop:one-shot-sell
(build bot-00d3a3726): the town-arrival journal's board of the one-shot
sale (row 23, the Magic shop page) and the game screen at the stop (the
sale menu the game drew).

    python tests/extract_worthless_sale_fixture.py <incident-capture-dir> <capture-dir>
"""
import gzip
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "worthless-sale-20261103.json.gz"


def main() -> None:
    incident, capture = Path(sys.argv[1]), Path(sys.argv[2])
    with gzip.open(incident / "town-arrival" / "journal.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    row = rows[23]
    with gzip.open(capture / "control-at-stop.json.gz", "rt", encoding="utf-8") as stream:
        screen = json.load(stream)["screen"]
    case = {
        "source": f"{incident.parent.parent.name}/{incident.name}",
        "decision": {"key": row["key"], "reason": row["reason"],
                     "decision_sequence": row["decision_sequence"]},
        "board": json.loads(row["line"] or row["inputs"][-1]),
        "sale_menu": screen["lines"][:10],
    }
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)


if __name__ == "__main__":
    main()
