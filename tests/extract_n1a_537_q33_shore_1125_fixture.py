"""Freeze n1-a life-537's Quest 33 boards of the 船幽霊 loop and the policy that decided them.

Source: n1-a life-537 (Zombie warrior Lv48) on hengband.net, stopped by the owner's livelock guard
2026-11-25 10:11:52 (``livelock-exhausted``, floor (0, 45, 33), turn 4097513).  Copied to
C:/hengband-backups/pdca/n1a-537-q33-shore-1125: ``town-arrival/`` (the incident capture's
town-arrival checkpoint, 10:07:54, the visit before the quest), ``snapshots-current.jsonl.gz``
(~/hengbot-soak/n1-a/life-537/jsonlog/snapshots, every board of the quest floor) and
``q33-decisions.jsonl.gz`` (the rows of jsonlog/bot-decisions.jsonl{,.1} on the floor, decisions
69304-71102, one process).

The arrival policy decides every board of the floor in order through ``choose_key`` (each key
confirmed as posted), as the live process did: it reproduces 1797 of the 1799 recorded decisions
(the first board, whose row the rotation cut, and 71077, a hold counted one board apart).  Its
checkpoint before the board of decision ``FIRST`` and the boards ``FIRST``..the stop are written;
the committed test reads the fixture alone.
"""

from __future__ import annotations

import collections
import copy
import gzip
import json
import lzma
import sys
import tempfile
from pathlib import Path

import tests  # noqa: F401 -- isolate runtime files before policy imports
from hengbot.latch_onset_capture import checkpoint_bytes
from hengbot.model import parse_snapshot
from replay_town_arrival import adopt_calibration, restore

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1a-537-q33-shore-1125")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-537-q33-shore-1125"
QUEST = 33
FIRST = 71077   # the hold on [29,37] before the walk north to the 船幽霊's water
PRESET = 9 | lzma.PRESET_EXTREME


def _rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue   # the live file's last line may be cut


def main():
    boards = [row for row in _rows(ROOT / "snapshots-current.jsonl.gz")
              if row.get("type") == "player_turn" and row["floor"].get("quest_id") == QUEST]
    decisions = collections.defaultdict(list)
    for row in _rows(ROOT / "q33-decisions.jsonl.gz"):
        decisions[row["turn"]].append(row)
    with tempfile.TemporaryDirectory() as directory:
        runtime = Path(directory)
        visit = ROOT / "town-arrival"
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / "sidecars" / "_character_calibration_path", runtime)
        used = collections.Counter()
        kept, recorded, checkpoint = [], [], None
        for raw in boards:
            same = decisions.get(raw["turn"], [])
            row = same[used[raw["turn"]]] if used[raw["turn"]] < len(same) else None
            used[raw["turn"]] += 1
            sequence = None if row is None else row["decision_sequence"]
            if checkpoint is None and sequence == FIRST:
                checkpoint = checkpoint_bytes(policy)
            if checkpoint is not None:
                if row is not None:
                    assert (raw["player"]["y"], raw["player"]["x"]) == (row["position"]["y"], row["position"]["x"])
                kept.append(dict(raw, messages=raw["messages"] if row is None else row["messages"]))
                recorded.append(None if row is None else {"sequence": sequence, "turn": row["turn"],
                                                          "reason": row["reason"], "key": row["key"]})
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            policy.confirm_key_posted(policy.choose_key(snapshot))
    assert checkpoint is not None
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "policy.pkl.xz").write_bytes(lzma.compress(checkpoint, preset=PRESET))
    (OUTPUT / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"source": "n1a-537-q33-shore-1125", "boards": kept, "recorded": recorded},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), preset=PRESET))
    sys.stdout.write(f"{OUTPUT} {len(kept)} boards\n")


if __name__ == "__main__":
    main()
