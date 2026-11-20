"""Extract the fixture of the n1-b life-411 stop of 2026-11-21 03:21 (a reserved heal, no key).

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-411-20261121-032127-no-key-exhausted:

 - ``captures/20261121-032127-no-key-exhausted/`` -- state.jsonl.gz (the 29 player-turn boards
   of the ring, the Recall read and its wait up to the stop) and bot-decisions.jsonl.gz (their
   decision rows);
 - ``incident-captures/20261121-032124-no-key-exhausted/town-arrival/`` -- the town-arrival
   checkpoint of 03:19:04 (policy.pkl), read for the full-Home retry ledger
   (``_home_full_retry_deposits``) the policy carried out of that town visit and held at the stop.

Writes tests/fixtures/n1b-411-heal-reserved-1121.json.xz.

    python tests/extract_n1b_411_heal_reserved_1121_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-411-20261121-032127-no-key-exhausted")
CAPTURE = ROOT / "captures" / "20261121-032127-no-key-exhausted"
ARRIVAL = ROOT / "incident-captures" / "20261121-032124-no-key-exhausted" / "town-arrival"
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-heal-reserved-1121.json.xz"
PRESET = 9 | lzma.PRESET_EXTREME


def main() -> None:
    from replay_town_arrival import restore

    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8",
                   errors="surrogateescape") as stream:
        boards = [row for row in map(json.loads, stream) if row.get("type") == "player_turn"]
    first = boards[0]["turn"]
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8",
                   errors="surrogateescape") as stream:
        for row in map(json.loads, stream):
            if row.get("turn", 0) >= first and "reason" in row:
                decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                                  "player": row.get("player"), "messages": row.get("messages")})
    arrival = restore(ARRIVAL)
    fixture = {"boards": boards, "decisions": decisions,
               "arrival_turn": arrival._town_visit_epoch,
               "retry_deposits": [[list(entry[0]), *entry[1:]]
                                  for entry in arrival._home_full_retry_deposits]}
    FIXTURE.write_bytes(lzma.compress(
        json.dumps(fixture, ensure_ascii=False).encode("utf-8", "surrogateescape"), preset=PRESET))
    print("heal-reserved-411", len(boards), len(decisions), fixture["retry_deposits"])


if __name__ == "__main__":
    main()
