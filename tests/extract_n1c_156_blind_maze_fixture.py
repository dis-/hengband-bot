"""Freeze the n1-c life-156 death boards of 2026-11-07 23:08 (迷宮10階).

Source: copies of the automatic player-death capture of the viewing Magic-Eater
n1-c (incident capture 20261106-230800-player-death):

  state-tail.txt
      the last player boards of the life, turns 1044263-1044440: blind on the
      down staircase the Labyrinth's up-shaft from 12F landed it on, every cell
      of the board but one forgotten (player-move.cpp ``wiz_dark`` in a FORGET
      dungeon), punched, kicked and clubbed by unseen attackers while it
      waited (``return:wait`` / ``emergency:wait``) from HP 171 to death;
  dec-tail.jsonl
      the recorded decision rows (12F and 10F, decisions 2374-2772).

Usage: python tests/extract_n1c_156_blind_maze_fixture.py <state-tail.txt> <dec-tail.jsonl>
Only this extraction tool reads the copies; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "death-n1c-156-1107.json.gz"
FIRST_DECISION = 2686  # the last sighted board before the ヴラスタ's first bite


def main(state_tail: str, decision_tail: str) -> None:
    boards = [json.loads(line) for line in Path(state_tail).read_text(encoding="utf-8").splitlines()
              if line.startswith('{"clock"')]
    decisions = []
    for line in Path(decision_tail).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["decision_sequence"] >= FIRST_DECISION:
            decisions.append({
                "sequence": row["decision_sequence"], "turn": row["turn"], "key": row["key"],
                "reason": row["reason"], "rung": row["rung"], "hp": row["player"]["hp"],
                "status": row["player"]["status"], "position": row["position"],
                "level": row["floor"]["level"], "messages": row["messages"],
                "down_stairs": row["map_memory"].get("down_stairs"),
            })
    case = {"boards": boards, "decisions": decisions}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main(*sys.argv[1:3])
