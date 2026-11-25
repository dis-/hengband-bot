"""Freeze n1-a life-537's last Quest 33 round: the sweep walked past two cave spiders 100 times.

Source: n1-a life-537 (Zombie warrior Lv48) on hengband.net, the process started at 2026-11-25 19:51
(bot main 082d25624) on the Quest 33 floor and stopped by name at 20:21:45 (turn 4326278,
``quest:blocked:sweep-nothing-left``; incident capture 20261125-202145-quest-blocked-sweep-nothing-left).
Copied to C:/hengband-backups/pdca/n1a-537-q33-nothing-left-1125 (SOURCE.txt):

 * ``boards.jsonl.gz``: the floor's player_turn boards of the last round of the stops, from the
   board on the last stop's stand [25,73] that began it (turn 4325393) to the stop's board on the
   same stand (turn 4326278);
 * ``decision-tail.jsonl.gz``: the decisions of 20:20:06-20:21:45 (every one of these boards);
 * ``quest-plan.pkl`` and ``sweep-kills.json``: the plan state and the tracked races' kills the
   process left at the stop (quest_plan_record, quest_sweep_record).

The fixture keeps the boards with their recorded decision (sequence, turn, reason, key), the
navigator of the plan record and the kills.  The test restores them on the policy of
tests/fixtures/n1a-537-q33-shore-1125 (the same life on the same floor, 10:10).
"""

from __future__ import annotations

import collections
import gzip
import json
import lzma
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1a-537-q33-nothing-left-1125")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-537-q33-nothing-left-1125"
QUEST = 33
PRESET = 9 | lzma.PRESET_EXTREME


def _rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    decisions = collections.defaultdict(list)
    for row in _rows(ROOT / "decision-tail.jsonl.gz"):
        if "decision_sequence" in row:
            decisions[row["turn"]].append(row)
    used = collections.Counter()
    boards, recorded = [], []
    for raw in _rows(ROOT / "boards.jsonl.gz"):
        assert raw["floor"]["quest_id"] == QUEST
        same = decisions[raw["turn"]]
        row = same[used[raw["turn"]]]
        used[raw["turn"]] += 1
        boards.append(raw)
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"]})
    kills = json.loads((ROOT / "sweep-kills.json").read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "quest-plan.pkl.xz").write_bytes(lzma.compress((ROOT / "quest-plan.pkl").read_bytes(), preset=PRESET))
    (OUTPUT / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"source": "n1a-537-q33-nothing-left-1125", "boards": boards, "recorded": recorded,
         "kills": kills["kills"]},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), preset=PRESET))
    sys.stdout.write(f"{OUTPUT} {len(boards)} boards\n")


if __name__ == "__main__":
    main()
