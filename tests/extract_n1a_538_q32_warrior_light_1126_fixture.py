"""Freeze n1-a life-538's Quest 32 boards for the summoner room's light and the walk to the summoner.

Source: n1-a life-538 (Zombie warrior Lv30) on hengband.net, Quest 32 floor (0,25,32), incident capture
20261126-043541-livelock-exhausted (build bot-12d92ad85), copied read-only to
C:/hengband-backups/pdca/n1a-538-q32-hold-sweep-1126 (SOURCE.txt): ``snapshots-current.jsonl.gz`` (the
floor's boards of turns 1312778-1314976) and ``decision-tail.jsonl.gz`` (the decision log's tail).

The arrival checkpoint and the stop's plan record are the n1a-538-q32-hold-sweep-1126 fixture's (the
same capture); this fixture keeps three windows of boards with their recorded decisions (sequence,
turn, reason, key):

 * ``unseen``: 1313101-1313139, the first summons by 何か (1313114, the player at [19,2] in the south
   room, recorded ``quest-strategy:melee``) and the second (1313131, ``summons:leave-teleport``);
 * ``walk``: 1314495-1314518, the 閾に棲む者 at [10,1] in view from [15,6] and shot with the plain
   arrows (``summoner:ranged-kill:named-caster``, 62 a turn);
 * ``shot``: 1313575-1313600, the six 閾に棲む者 in view from [17,2], shot (``ranged:fire-target`` /
   ``ranged:fire-offset``).
"""

from __future__ import annotations

import gzip
import json
import lzma
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1a-538-q32-hold-sweep-1126")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-538-q32-warrior-light-1126"
QUEST = 32
WINDOWS = {"unseen": (1313101, 1313139), "walk": (1314495, 1314518), "shot": (1313575, 1313600)}
PRESET = 9 | lzma.PRESET_EXTREME


def _rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    decisions = {}
    for row in _rows(ROOT / "decision-tail.jsonl.gz"):
        if "decision_sequence" in row:
            decisions.setdefault(row["turn"], []).append(row)
    windows = {name: {"boards": [], "recorded": []} for name in WINDOWS}
    for raw in _rows(ROOT / "snapshots-current.jsonl.gz"):
        if "player" not in raw:
            continue
        assert raw["floor"]["quest_id"] == QUEST
        for name, (first, last) in WINDOWS.items():
            if first <= raw["turn"] <= last:
                row, = decisions[raw["turn"]]
                windows[name]["boards"].append(raw)
                windows[name]["recorded"].append({"sequence": row["decision_sequence"], "turn": row["turn"],
                                                  "reason": row["reason"], "key": row["key"]})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"source": "n1a-538-q32-hold-sweep-1126", "windows": windows},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), preset=PRESET))
    sys.stdout.write(f"{OUTPUT} " + ", ".join(f"{name} {len(window['boards'])}" for name, window in windows.items())
                     + "\n")


if __name__ == "__main__":
    main()
