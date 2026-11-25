"""Freeze n1-a life-538's Quest 32 stop: retake-hold and sweep-engage-mobile alternated to the livelock stop.

Source: n1-a life-538 (Zombie warrior Lv30) on hengband.net, stopped 2026-11-26 04:35:41 on the Quest 32
floor (0,25,32) by ``livelock:exhausted`` (turn 1314976, build bot-12d92ad85; incident capture
20261126-043541-livelock-exhausted).  Copied read-only to C:/hengband-backups/pdca/n1a-538-q32-hold-sweep-1126
(SOURCE.txt):

 * ``arrival-policy.pkl``: the capture's town-arrival checkpoint (turn 1264421, the visit that took the quest);
 * ``quest-plan.pkl``: the plan record (quest_plan_record) the process left at the stop;
 * ``snapshots-current.jsonl.gz``: the floor's boards of turns 1312778-1314976;
 * ``decision-tail.jsonl.gz``: the decision log's tail (its first line cut).

The fixture keeps the arrival checkpoint, the plan record, the boards of the last window (turn
1314585, the player on the hold [19,4], to the stop) with their recorded decisions (sequence, turn,
reason, key; the stop's board, which has no decision row, as ``livelock:exhausted``), and two
single boards: 1314506 (閾に棲む者 in view from [15,6]) and 1313331 (a スタンウォール in view from
[13,5], an earlier sweep/retake alternation of the same floor).
"""

from __future__ import annotations

import gzip
import json
import lzma
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1a-538-q32-hold-sweep-1126")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-538-q32-hold-sweep-1126"
QUEST = 32
WINDOW_START = 1314585
SUMMONER_BOARD = 1314506
STUN_WALL_BOARD = 1313331
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
    boards, recorded, singles = [], [], {}
    for raw in _rows(ROOT / "snapshots-current.jsonl.gz"):
        if "player" not in raw:
            continue
        assert raw["floor"]["quest_id"] == QUEST
        if raw["turn"] in (SUMMONER_BOARD, STUN_WALL_BOARD):
            singles[str(raw["turn"])] = raw
        if raw["turn"] < WINDOW_START:
            continue
        boards.append(raw)
        if raw["turn"] not in decisions:
            # The stop's board: the livelock leave answered it (meta.json's last reason), no decision row.
            recorded.append({"sequence": None, "turn": raw["turn"], "reason": "livelock:exhausted", "key": None})
            continue
        row, = decisions[raw["turn"]]
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"]})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "policy.pkl.xz").write_bytes(lzma.compress((ROOT / "arrival-policy.pkl").read_bytes(), preset=PRESET))
    (OUTPUT / "quest-plan.pkl.xz").write_bytes(lzma.compress((ROOT / "quest-plan.pkl").read_bytes(), preset=PRESET))
    (OUTPUT / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"source": "n1a-538-q32-hold-sweep-1126", "boards": boards, "recorded": recorded,
         "singles": singles},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), preset=PRESET))
    sys.stdout.write(f"{OUTPUT} {len(boards)} boards, singles {sorted(singles)}\n")


if __name__ == "__main__":
    main()
