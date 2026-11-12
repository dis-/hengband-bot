"""Freeze n1-c life-201's Quest 31 emergency stair (2026-11-12 13:21:39) for the leave-confirm test.

Source: n1-c life-201 on hengband.net, the stuck-prompt capture
(~/hengbot-soak/n1-c/life-201/captures/20261112-132139-stuck-prompt-emergency-stairs-quest-fail),
copied read-only to C:/hengband-backups/pdca/captures/n1c-201-stairs-quest-fail-1112/.  On the
Quest 31 floor (『柳じじい』, fixed ONCE kill-all, dungeon 0 level 22) the bot read its last Teleport
scroll (decision 7596, ``emergency:teleport`` 're'), landed on the up stair [18,1] and posted '<'
(decision 7597, ``emergency:stairs-quest-fail``); the game asked 「本当にこの階を去りますか？[y/n]」
and the executor stopped on the unowned confirm (bot-stderr.log).

Kept:
 * ``boards``: the last two state rows (turns 867742 and 867751);
 * ``recorded``: the decision rows of the same turns (sequence, turn, reason, key);
 * ``stop``: the control server's screen and input context at the stop (control-at-stop.json);
 * ``stderr``: the stuck-prompt line of bot-stderr.log.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-201-stairs-quest-fail-1112")
CAPTURE = ROOT / "20261112-132139-stuck-prompt-emergency-stairs-quest-fail"
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-201-stairs-quest-fail-1112.json.gz"
BOARDS = 2


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
    case = dict(source="n1c-201-stairs-quest-fail-1112", boards=boards, recorded=recorded,
                stop={"screen": control["screen"], "input_kind": control["input_kind"],
                      "input_prompt": control["input_prompt"]},
                stderr=stderr)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(recorded))


if __name__ == "__main__":
    main()
