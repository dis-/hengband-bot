"""Freeze n1-b life-418's Quest 33 boards before its named stop, and the policy that decided them.

Source: n1-b life-418 (Magic-Eater Lv44) on hengband.net, stopped 2026-11-25 13:32:21 by the
plan's own stop ``quest:blocked:sweep-nothing-comes`` on the floor (0, 45, 33) after 126 holds on
[20,42] (bot main 5d2d334da).  Copied to C:/hengband-backups/pdca/n1b-418-q33-blocked-1125:
``town-arrival/`` (the incident capture's town-arrival checkpoint, 13:18:39, the visit before the
quest), ``snapshots-current.jsonl.gz`` (~/hengbot-soak/n1-b/life-418/jsonlog/snapshots, every board
of the quest floor) and ``q33-decisions.jsonl.gz`` (the rows on the floor, decisions 2969-6595, one
process).

The arrival policy decides every board of the floor in order through ``choose_key`` (each key
confirmed as posted; the one skill-list answer on the floor is consumed as the live reader does).
Its checkpoint before decision ``FIRST`` and the boards from it to the stop are written; the
committed test reads the fixture alone.  Run it with the code of the live process.
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

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1b-418-q33-blocked-1125")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-418-q33-blocked-1125"
QUEST = 33
FIRST = 6300
PRESET = 9 | lzma.PRESET_EXTREME


def _rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue   # the live file's last line may be cut


def _stream(path: Path):
    """The quest floor's boards and the knowledge answers between them, in order."""
    on = False
    for row in _rows(path):
        if row.get("type") == "player_turn":
            on = row["floor"].get("quest_id") == QUEST
            if on:
                yield row
        elif on and row.get("type") == "knowledge":
            yield row


def main():
    with tempfile.TemporaryDirectory() as directory:
        extract(Path(directory))


def extract(runtime: Path):
    visit = ROOT / "town-arrival"
    policy = restore(visit, runtime)
    calibration = visit / "sidecars" / "_character_calibration_path"
    if calibration.is_file():
        adopt_calibration(policy, calibration, runtime)
    decisions = collections.defaultdict(list)
    for row in _rows(ROOT / "q33-decisions.jsonl.gz"):
        if "decision_sequence" in row:
            decisions[row["turn"]].append(row)
    used = collections.Counter()
    kept, recorded, checkpoint = [], [], None
    for raw in _stream(ROOT / "snapshots-current.jsonl.gz"):
        if raw.get("type") == "knowledge":
            if ((raw.get("knowledge") or {}).get("category") == "skill_exp"
                    and getattr(policy, "_skill_exp_request_inflight", False)):
                policy.consume_skill_knowledge(raw)
                if checkpoint is not None:
                    kept.append(raw)
                    recorded.append(None)
            continue
        same = decisions.get(raw["turn"], [])
        row = same[used[raw["turn"]]] if used[raw["turn"]] < len(same) else None
        used[raw["turn"]] += 1
        sequence = None if row is None else row["decision_sequence"]
        if checkpoint is None and sequence == FIRST:
            checkpoint = checkpoint_bytes(policy)
        if checkpoint is not None:
            kept.append(dict(raw, messages=raw["messages"] if row is None else row["messages"]))
            recorded.append(None if row is None else {"sequence": sequence, "turn": row["turn"],
                                                      "reason": row["reason"], "key": row["key"]})
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.confirm_key_posted(policy.choose_key(snapshot))
    assert checkpoint is not None
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "policy.pkl.xz").write_bytes(lzma.compress(checkpoint, preset=PRESET))
    (OUTPUT / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"source": "n1b-418-q33-blocked-1125", "boards": kept, "recorded": recorded},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), preset=PRESET))
    sys.stdout.write(f"{OUTPUT} {len(kept)} boards\n")


if __name__ == "__main__":
    main()
