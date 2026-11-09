"""Freeze n1-c life-181's Quest 25 recall exit (2026-11-09 19:18:31) for the leave-confirm test.

Source: n1-c life-181 on hengband.net, the first of the three stuck-prompt captures
(~/hengbot-soak/n1-c/life-181/captures/20261109-191831-stuck-prompt-quest25-recall-exit),
copied read-only to C:/hengband-backups/pdca/captures/n1c-181-q25-recall-exit-1109/.  After the
Recall was read the plan walked down the west corridor to the start stair [13,1] (decisions
19990-19994, ``quest25:recall-exit-walk`` '2') and posted '<' there (decision 19995,
``quest25:recall-exit``); the game asked 「本当にこの階を去りますか？[y/n]」 and the executor stopped
on the unowned confirm (bot-stderr.log).

Kept:
 * ``boards``: the last six state rows (turns 2672208-2672235, [8,1] to [13,1]);
 * ``recorded``: the decision rows of the same turns (sequence, turn, reason, key);
 * ``stop``: the control server's screen and input context at the stop (control-at-stop.json);
 * ``stderr``: the stuck-prompt line of bot-stderr.log.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-181-q25-recall-exit-1109")
CAPTURE = ROOT / "20261109-191831-stuck-prompt-quest25-recall-exit"
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-181-q25-recall-exit-1109.json.gz"
BOARDS = 6


def _rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    boards = _rows(CAPTURE / "state.jsonl.gz")[-BOARDS:]
    turns = {board["turn"] for board in boards}
    recorded = [{"sequence": row["decision_sequence"], "turn": row["turn"],
                 "reason": row["reason"], "key": row["key"]}
                for row in _rows(CAPTURE / "bot-decisions.jsonl.gz") if row["turn"] in turns]
    assert [row["turn"] for row in recorded] == [board["turn"] for board in boards], recorded
    with gzip.open(CAPTURE / "control-at-stop.json.gz", "rt", encoding="utf-8") as stream:
        control = json.load(stream)
    stderr = [line for line in (CAPTURE / "bot-stderr.log").read_text(encoding="utf-8").splitlines()
              if line.startswith("<stuck-prompt>")]
    case = dict(source="n1c-181-q25-recall-exit-1109", boards=boards, recorded=recorded,
                stop={"screen": control["screen"], "input_kind": control["input_kind"],
                      "input_prompt": control["input_prompt"]},
                stderr=stderr)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(recorded))


if __name__ == "__main__":
    main()
