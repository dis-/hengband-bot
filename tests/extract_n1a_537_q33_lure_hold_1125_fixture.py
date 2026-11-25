"""Freeze n1-a life-537's second Quest 33 process: the lure's wait at the 巨大火アリ's pocket.

Source: n1-a life-537 (Zombie warrior Lv48) on hengband.net.  After the first stop on the floor
(tests/extract_n1a_537_q33_shore_1125_fixture.py, 10:11:52) the bot was restarted on the floor at
2026-11-25 12:32:51 (bot main 12c52ae3b) and stopped again by the livelock guard at 12:37:33
(turn 4112895).  Copied to C:/hengband-backups/pdca/n1a-537-q33-shore-1125/restart-1232:
``snapshots-current.jsonl.gz`` and ``snapshots-20261125-123641-336285.jsonl.gz``
(~/hengbot-soak/n1-a/life-537/jsonlog/snapshots) and ``q33-decisions.jsonl.gz`` (the second
process's rows of jsonlog/bot-decisions.jsonl, decisions 0-2446).

DECLARED CONSTRUCTED (the restart): the town-arrival policy of the first fixture decides the first
process's 1800 boards, is checkpointed and restored (latch_onset_capture.restore_checkpoint_bytes
normalizes it as a restart does), then decides the second process's boards.  It reproduces 2443 of
its 2447 recorded decisions (the first board's skill read, and 1517-1526, where the replay's own
livelock guard fires); the decisions 2400-2446 are all reproduced.  The checkpoint before decision
``FIRST`` and the boards from it to the stop are written; the committed test reads the fixture alone.
Run it with the code of the live process (main 12c52ae3b).
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
SECOND = ROOT / "restart-1232"
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-537-q33-lure-hold-1125"
QUEST = 33
FIRST = 2400   # the walk to [28,52] before the wait at the 巨大火アリ's pocket
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


def _decide(policy, raw):
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    policy.confirm_key_posted(policy.choose_key(snapshot))


def main():
    with tempfile.TemporaryDirectory() as directory:
        extract(Path(directory))


def extract(runtime: Path):
    visit = ROOT / "town-arrival"
    policy = restore(visit, runtime)
    adopt_calibration(policy, visit / "sidecars" / "_character_calibration_path", runtime)
    first = _boards(ROOT / "snapshots-current.jsonl.gz")
    for raw in first[:-1]:   # the stop's board was not decided
        _decide(policy, raw)
    policy = restore_checkpoint_bytes(HengbotPolicy, checkpoint_bytes(policy))
    decisions = collections.defaultdict(list)
    for row in _rows(SECOND / "q33-decisions.jsonl.gz"):
        if "decision_sequence" in row:
            decisions[row["turn"]].append(row)
    start = min(decisions)
    second = [raw for raw in _boards(SECOND / "snapshots-20261125-123641-336285.jsonl.gz",
                                     SECOND / "snapshots-current.jsonl.gz") if raw["turn"] >= start]
    used = collections.Counter()
    kept, recorded, checkpoint = [], [], None
    for raw in second:
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
        {"source": "n1a-537-q33-lure-hold-1125", "boards": kept, "recorded": recorded},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), preset=PRESET))
    sys.stdout.write(f"{OUTPUT} {len(kept)} boards\n")


if __name__ == "__main__":
    main()
