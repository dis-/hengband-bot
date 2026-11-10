"""Freeze the n1-c life-191 Anaguma detection stop of 2026-11-10 (tests/test_anaguma_detect_stuck_1110_recorded.py).

Source: the viewing Magic-Eater n1-c life-191, オークの洞窟23階 (floor (3, 23, 0)), stopped at
19:18:48 with ``stuck-prompt:anaguma:detect``: the pocket's hold waited its 50 game turns and
``anaguma:detect`` sent ``mCg`` (the absorbed Rod of Detection) under its bare reason while the
rod still charged from the arrival's ``UCg``; the game kept the power prompt
(「('*'で一覧, ESCで中断) どの魔力を使いますか？」) and no owner answered it.  Copied read-only
from the viewing server to C:/hengband-backups/pdca/captures/anaguma-detect-stuck-1110:

  CAPTURE/state.jsonl.gz          the last 96 rows before the stop (turns 2721538-2722672)
  CAPTURE/bot-decisions.jsonl.gz  their decision rows
  CAPTURE/control-at-stop.json.gz the game's screen at the stop (the power prompt and its list)
  INCIDENT/policy-state.json      the stop's policy summary (the absorption record)

The fixture keeps every player-turn board from the arrival's first Anaguma decision (turn
2722264) to the detection (turn 2722672): the whole plan, from the first melt to the hold.
With them: the compact decision rows, the absorption record, and the stop screen.  The same
stop repeated on life-187 (twice) and life-191 at 19:24; their captures begin after their
plans were made, so this one, whose capture holds the whole plan, is the pin.  Only this
extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/captures/anaguma-detect-stuck-1110")
CAPTURE = ROOT / "life-191_20261110-191848-stuck-prompt-anaguma-detect"
INCIDENT = ROOT / "incident-life-191_20261110-191845-stuck-prompt-state"
OUTPUT = Path(__file__).with_name("fixtures") / "anaguma-detect-stuck-20261110.json.gz"
FIRST, LAST = 2722264, 2722672


def main():
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row for row in map(json.loads, stream)
                  if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST]
    turns = {board["turn"] for board in boards}
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") in turns:
                decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"]})
    with gzip.open(CAPTURE / "control-at-stop.json.gz", "rt", encoding="utf-8") as stream:
        stop = json.load(stream)
    state = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))["state"]
    fixture = {
        "source": f"{CAPTURE.name} (copied from the viewing server)",
        "boards": boards,
        "decisions": decisions,
        "absorbed": state["_me_staff_sequence"]["absorbed"],
        "stop_plan": state["_anaguma_plan"],
        "stop_screen": stop["screen"],
        "stop_prompt": stop["input_prompt"],
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
