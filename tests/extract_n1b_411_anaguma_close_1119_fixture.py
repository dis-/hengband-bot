"""Extract the fixture of the n1-b life-411 stop of 2026-11-19 (anaguma:close-step into a vein).

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-411-anaguma-close-1119:

 - ``411/`` -- life-411 captures/20261119-051535-loop-detected (state.jsonl.gz,
   bot-decisions.jsonl.gz);
 - ``inc411/`` -- incident-captures/20261119-051534-loop-detected (policy-state.json: the
   absorption record and the Anaguma plan held at the stop).

The player-turn boards from turn 8162386 on (the close-in's haste on the pocket, the step out,
the *Destruction* and the refused steps), their decision rows, the absorption record and the
plan go to tests/fixtures/n1b-411-anaguma-close-1119.json.xz.

    python tests/extract_n1b_411_anaguma_close_1119_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-411-anaguma-close-1119")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-anaguma-close-1119.json.xz"
FIRST_TURN = 8162386
PRESET = 9 | lzma.PRESET_EXTREME


def main() -> None:
    with gzip.open(ROOT / "411" / "state.jsonl.gz", "rt", encoding="utf-8",
                   errors="surrogateescape") as stream:
        boards = [row for row in map(json.loads, stream)
                  if row.get("type") == "player_turn" and row["turn"] >= FIRST_TURN]
    decisions = []
    with gzip.open(ROOT / "411" / "bot-decisions.jsonl.gz", "rt", encoding="utf-8",
                   errors="surrogateescape") as stream:
        for row in map(json.loads, stream):
            if row.get("turn", 0) >= FIRST_TURN and "reason" in row:
                decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                                  "position": row.get("position"), "messages": row.get("messages")})
    state = json.loads((ROOT / "inc411" / "policy-state.json").read_text(encoding="utf-8"))["state"]
    fixture = {"boards": boards, "decisions": decisions,
               "absorbed": state["_me_staff_sequence"]["absorbed"],
               "stop_plan": state["_anaguma_plan"]}
    FIXTURE.write_bytes(lzma.compress(
        json.dumps(fixture, ensure_ascii=False).encode("utf-8", "surrogateescape"), preset=PRESET))
    print("anaguma-close-411", len(boards), len(decisions))


if __name__ == "__main__":
    main()
