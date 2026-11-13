"""Extract the fixtures of the n1-b life-393 / life-394 stops of 2026-11-14.

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-393-anaguma-walk-1114:

 - ``393/`` -- life-393 captures/20261114-014004-loop-detected (state.jsonl.gz,
   bot-decisions.jsonl.gz) and ``inc393/`` -- incident-captures/20261114-014002-loop-detected
   (policy-state.json: the absorption record and the Anaguma plan held at the stop).  The
   player-turn boards from turn 3224944 on (the last board before the floor's plan), their
   decision rows, the absorption record and the plan go to
   tests/fixtures/n1b-393-394-1114/anaguma-walk-393.json.xz.
 - ``inc394/town-arrival`` -- life-394 incident-captures/20261114-015105-quest-blocked-me-staff:
   the town-arrival checkpoint (policy.pkl, journal.jsonl.gz, the calibration sidecar),
   recompressed with xz into tests/fixtures/n1b-393-394-1114/me-staff-394/ (the
   extract_viewing_stops_1113_fixtures layout).

    python tests/extract_n1b_393_394_1114_fixtures.py
"""
import gzip
import json
import lzma
from pathlib import Path

import extract_viewing_stops_1113_fixtures as layout

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-393-anaguma-walk-1114")
FIXTURES = Path(__file__).with_name("fixtures") / "n1b-393-394-1114"
FIRST_TURN = 3224944


def anaguma_walk() -> None:
    with gzip.open(ROOT / "393" / "state.jsonl.gz", "rt", encoding="utf-8",
                   errors="surrogateescape") as stream:
        boards = [row for row in map(json.loads, stream)
                  if row.get("type") == "player_turn" and row["turn"] >= FIRST_TURN]
    decisions = []
    with gzip.open(ROOT / "393" / "bot-decisions.jsonl.gz", "rt", encoding="utf-8",
                   errors="surrogateescape") as stream:
        for row in map(json.loads, stream):
            if row.get("turn", 0) >= FIRST_TURN and "reason" in row:
                decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                                  "position": row.get("position"), "messages": row.get("messages")})
    state = json.loads((ROOT / "inc393" / "policy-state.json").read_text(encoding="utf-8"))["state"]
    fixture = {"boards": boards, "decisions": decisions,
               "absorbed": state["_me_staff_sequence"]["absorbed"],
               "stop_plan": state["_anaguma_plan"]}
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "anaguma-walk-393.json.xz").write_bytes(lzma.compress(
        json.dumps(fixture, ensure_ascii=False).encode("utf-8", "surrogateescape"),
        preset=layout.PRESET))
    print("anaguma-walk-393", len(boards), len(decisions))


def main() -> None:
    anaguma_walk()
    layout.FIXTURES = FIXTURES
    layout.arrival(ROOT / "inc394" / "town-arrival", "me-staff-394")
    print("me-staff-394")


if __name__ == "__main__":
    main()
