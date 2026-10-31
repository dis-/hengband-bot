"""Freeze the 2026-10-31 12:45 n1-b life-279 death boards (D46).

Source: the automatic player-death capture cap-n1b-279-death of the viewing
warrior n1-b life-279 (Lv30 zombie warrior, Castle 22F, 555 max HP).  Its
state-tail.jsonl holds the last 1500 player_turn boards and decision-tail.jsonl
the last 703 decisions (turns 1337860-1344207; its first line starts in the
middle of a record).  Every decision there is ``melee`` against a swarm of
巨大ゴキブリ (race 1007, MULTIPLY, max blow 2) except three
``item:strong-fight-speed``; HP fell 333 -> 4 with Healing, Teleportation and
Word of Recall carried.

Frozen: the boards of the first decision (HP 333, 60%), the first decisions
under the low-HP threshold (HP < 277.5), under the heal ratio (HP < 222),
near 25% and 10%, the first strong-fight-speed board (HP 21) and the death
board (HP 4), each with its recorded decision facts.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-279-death/cap-n1b-279-death")
STATE = CAPTURE / "state-tail.jsonl"
TAIL = CAPTURE / "decision-tail.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-279-death-20261031.json.gz"
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "player",
                   "visible_hostiles", "threat_prediction")
# The recorded boards named in the module docstring, by game turn.
TURNS = (1337860, 1338894, 1339534, 1340288, 1341107, 1342360, 1344207)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tail_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    return rows


def main():
    boards = {
        row["turn"]: row
        for row in (json.loads(line) for line in
                    STATE.read_text(encoding="utf-8").splitlines())
        if row.get("type") == "player_turn" and row["turn"] in TURNS
    }
    decisions = {row["turn"]: row for row in tail_rows(TAIL) if row["turn"] in TURNS}
    assert sorted(boards) == sorted(decisions) == list(TURNS), (sorted(boards), sorted(decisions))
    case = dict(
        source="cap-n1b-279-death (n1-b life-279, player-death 2026-10-31 12:45)",
        sources={STATE.name: sha(STATE), TAIL.name: sha(TAIL)},
        boards=[boards[turn] for turn in TURNS],
        decisions=[
            {field: decisions[turn].get(field) for field in DECISION_FIELDS}
            for turn in TURNS
        ],
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
