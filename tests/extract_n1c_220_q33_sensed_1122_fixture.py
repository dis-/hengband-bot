"""Extract tests/fixtures/n1c-220-q33-sensed-1122/ (q33-sensed-1122).

Source: n1-c life-220's death of 2026-11-22 19:36:02 (Quest 33, floor (0, 45, 33), bot main
30e054b0c), copied to C:/hengband-backups/pdca/n1c-220-q33-death/:

- ``decisions.json.xz``: the decision rows from FIRST_DECISION on (10884-10959: the 23 holds on
  [1,27] that ended in the death, and the rows between them), reduced to the key, the reason, the
  turn, the position, the HP and the threat tiers' 即死 reading.
- ``boards.json.xz``: the capture's state.jsonl.gz boards (the last 62, turn 3211609 on), as the
  game wrote them.

    python tests/extract_n1c_220_q33_sensed_1122_fixture.py [CAPTURE]
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET

CAPTURE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1c-220-q33-death")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-220-q33-sensed-1122"
FIRST_DECISION = 10884  # the first hold on [1,27]


def lines(name):
    with gzip.open(CAPTURE / name, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


if __name__ == "__main__":
    reduced = [{
        "sequence": row.get("decision_sequence"), "turn": row.get("turn"), "key": row.get("key"),
        "reason": row.get("reason"), "position": row.get("position"),
        "hp": row["player"].get("hp"), "max_hp": row["player"].get("max_hp"),
        "instant_death": (row.get("threat_tiers") or {}).get("instant_death"),
        "next_action_p95": (row.get("threat_tiers") or {}).get("next_action_p95"),
    } for row in lines("bot-decisions.jsonl.gz") if (row.get("decision_sequence") or 0) >= FIRST_DECISION]
    boards = lines("state.jsonl.gz")
    FIXTURE.mkdir(parents=True, exist_ok=True)
    for name, value in (("decisions.json.xz", reduced), ("boards.json.xz", boards)):
        (FIXTURE / name).write_bytes(
            lzma.compress(json.dumps(value, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(len(reduced), len(boards), sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
