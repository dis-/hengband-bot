"""Freeze n1-a life-537's third Quest 33 process: the 巨大火アリ pack that hides is lured and swept for.

Source: n1-a life-537 (Zombie warrior Lv48) on hengband.net, restarted on the floor at 2026-11-25
13:15:05 (bot main 5d2d334da) after the second stop
(tests/extract_n1a_537_q33_lure_hold_1125_fixture.py) and stopped by the livelock guard at
13:18:15 (turn 4123735).  Copied to C:/hengband-backups/pdca/n1a-537-q33-shore-1125/restart-1315:
``snapshots-current.jsonl.gz`` (~/hengbot-soak/n1-a/life-537/jsonlog/snapshots) and
``q33-decisions.jsonl.gz`` (the third process's rows, decisions 0-1725).

DECLARED CONSTRUCTED (the restarts): the town-arrival policy of the first fixture decides the
first process's boards, is checkpointed and restored as a restart, decides the second process's
boards, and is restarted again the same way before the third's.  From decision ``FIRST`` it
reproduces every recorded decision of the third process.  The checkpoint before ``FIRST`` and the
boards from it to the stop are written; the committed test reads the fixture alone.  Run it with
the code of the live process (main 5d2d334da).
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
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from replay_town_arrival import adopt_calibration, restore

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1a-537-q33-shore-1125")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-537-q33-hiding-pack-1125"
QUEST = 33
FIRST = 1080   # the hold on [27,48] before the walk to the pack by the tree columns
PRESET = 9 | lzma.PRESET_EXTREME


def _rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue   # the live file's last line may be cut


def _boards(*paths):
    found = {}
    for path in paths:
        for row in _rows(path):
            if row.get("type") == "player_turn" and row["floor"].get("quest_id") == QUEST:
                found.setdefault((row["turn"], json.dumps(row["player"], sort_keys=True)), row)
    return sorted(found.values(), key=lambda row: row["turn"])


def _decisions(path: Path):
    decisions = collections.defaultdict(list)
    for row in _rows(path):
        if "decision_sequence" in row:
            decisions[row["turn"]].append(row)
    return decisions


def _decide(policy, raw):
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    policy.confirm_key_posted(policy.choose_key(snapshot))


def _restart(policy):
    return restore_checkpoint_bytes(HengbotPolicy, checkpoint_bytes(policy))


def main():
    with tempfile.TemporaryDirectory() as directory:
        extract(Path(directory))


def extract(runtime: Path):
    visit = ROOT / "town-arrival"
    policy = restore(visit, runtime)
    adopt_calibration(policy, visit / "sidecars" / "_character_calibration_path", runtime)
    for raw in _boards(ROOT / "snapshots-current.jsonl.gz")[:-1]:   # the stop's board was not decided
        _decide(policy, raw)
    policy = _restart(policy)
    second = ROOT / "restart-1232"
    start = min(_decisions(second / "q33-decisions.jsonl.gz"))
    boards = [raw for raw in _boards(second / "snapshots-20261125-123641-336285.jsonl.gz",
                                     second / "snapshots-current.jsonl.gz") if raw["turn"] >= start]
    for raw in boards[:-1]:
        _decide(policy, raw)
    policy = _restart(policy)
    third = ROOT / "restart-1315"
    decisions = _decisions(third / "q33-decisions.jsonl.gz")
    last = boards[-1]["turn"]
    used = collections.Counter()
    kept, recorded, checkpoint = [], [], None
    for raw in _boards(third / "snapshots-current.jsonl.gz"):
        if raw["turn"] <= last:
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
        _decide(policy, raw)
    assert checkpoint is not None
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "policy.pkl.xz").write_bytes(lzma.compress(checkpoint, preset=PRESET))
    (OUTPUT / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"source": "n1a-537-q33-hiding-pack-1125", "boards": kept, "recorded": recorded},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), preset=PRESET))
    sys.stdout.write(f"{OUTPUT} {len(kept)} boards\n")


if __name__ == "__main__":
    main()
