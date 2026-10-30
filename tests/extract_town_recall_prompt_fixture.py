"""Freeze the 2026-10-30 21:39 n1-a life-443 town recall stop (D26).

Source: the automatic capture incident-captures/20261030-213957-stuck-prompt
of the viewing warrior n1-a life-443 (Lv8, town, after the tavern rumors and
the character dump) and the stop capture
captures/20261030-213959-stuck-prompt-town-recall-to-yeek-cave beside it.
Decision 2660 chose ``town:recall-to-yeek-cave`` and posted ``rda``; the
executor posted r, d, then Escape at 「どのダンジョンに帰還しますか:」 and
stopped as recall-destination-unchosen (x3 -> escalate -> new character).

The snapshot ring copy is the tail of a multi-member gzip: decoding starts at
the first member header and keeps whole members only.  Frozen: the stop board
(turn 176520, the ring's last player_turn row), the recorded decision 2660
facts, and the stop screen's side-panel cells 0-13 of rows 2-3, which
choose_dungeon's prt(row, 2 + i, 14) leaves standing left of each listed
destination.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from hengbot.input_executor import _cells
from tests.extract_recall_dungeon_prompt_fixture import ring_rows


LIFE = Path("C:/hengband-backups/pdca/captures/recall-yeek-1030/n1-a/life-443")
CAPTURE = LIFE / "incident-captures" / "20261030-213957-stuck-prompt"
RING = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
TAIL = CAPTURE / "decision-tail.jsonl"
STOP = LIFE / "captures" / "20261030-213959-stuck-prompt-town-recall-to-yeek-cave" / "control-at-stop.json.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "town-recall-prompt-20261030.json.gz"
STOP_TURN = 176520


def main():
    rows = ring_rows(RING.read_bytes())
    board = next(row for row in reversed(rows) if row["type"] == "player_turn")
    assert board["turn"] == STOP_TURN, board["turn"]
    decisions = []
    for line in TAIL.read_text(encoding="utf-8").splitlines():
        try:
            decisions.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    decision = decisions[-1]
    assert (decision["turn"], decision["reason"], decision["key"]) == (
        STOP_TURN, "town:recall-to-yeek-cave", "rda")
    with gzip.open(STOP, "rt", encoding="utf-8") as stream:
        lines = json.load(stream)["screen"]["lines"]
    case = dict(
        source="incident-20261030-213957-stuck-prompt (n1-a life-443)",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (RING, TAIL, STOP)},
        board=board,
        decision={key: decision[key] for key in
                  ("decision_sequence", "turn", "reason", "key", "objective")},
        side_panel={str(row): _cells(lines[row], 0, 14) for row in (2, 3)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, board["turn"], OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
