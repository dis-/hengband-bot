"""Freeze n1-b life-418's second Quest 33 process: the lure's walk turning at each board.

Source: n1-b life-418 (Magic-Eater Lv44) on hengband.net, restarted on the floor at 2026-11-25
15:07:38 (bot main c56d737dd, game upstream 8c09a69b3) after the named stop of 13:32
(tests/extract_n1b_418_q33_blocked_1125_fixture.py) and stopped by the livelock guard at 15:08:59
(turn 5272035).  Copied to C:/hengband-backups/pdca/n1b-418-q33-blocked-1125/restart-1507:
``snapshots-20261125-150752-060b21.jsonl.gz`` and ``snapshots-current.jsonl.gz``
(~/hengbot-soak/n1-b/life-418/jsonlog/snapshots) and ``q33-decisions.jsonl.gz`` (the second
process's rows, decisions 0-662).

DECLARED CONSTRUCTED (the restart): the first fixture's policy decides its boards to the stop, is
checkpointed and restored as a restart does, then decides the second process's boards (the
skill-list answers among them consumed as the live reader does).  From decision ``FIRST`` it
reproduces the recorded decisions.  The checkpoint before ``FIRST`` and the boards from it to the
stop are written; the committed test reads the fixture alone.  Run it with the code of the live
process (main c56d737dd).
"""

from __future__ import annotations

import collections
import copy
import gzip
import json
import lzma
import sys
from pathlib import Path

import tests  # noqa: F401 -- isolate runtime files before policy imports
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/n1b-418-q33-blocked-1125")
FIRST_FIXTURE = Path(__file__).with_name("fixtures") / "n1b-418-q33-blocked-1125"
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-418-q33-lure-target-1125"
QUEST = 33
FIRST = 600   # the walk from [28,25] to the 'c' room before the turning walk
PRESET = 9 | lzma.PRESET_EXTREME


def _rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue   # the live file's last line may be cut


def _decide(policy, raw):
    if raw.get("type") == "knowledge":
        if getattr(policy, "_skill_exp_request_inflight", False):
            policy.consume_skill_knowledge(raw)
        return
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    policy.confirm_key_posted(policy.choose_key(snapshot))


def main():
    first = json.loads(lzma.decompress((FIRST_FIXTURE / "boards.json.xz").read_bytes()))
    policy = restore_checkpoint_bytes(HengbotPolicy, lzma.decompress((FIRST_FIXTURE / "policy.pkl.xz").read_bytes()))
    for raw in first["boards"][:-1]:   # the stop's board was not decided
        _decide(policy, raw)
    stop = first["boards"][-1]["turn"]
    policy = restore_checkpoint_bytes(HengbotPolicy, checkpoint_bytes(policy))
    second = ROOT / "restart-1507"
    decisions = collections.defaultdict(list)
    for row in _rows(second / "q33-decisions.jsonl.gz"):
        if "decision_sequence" in row:
            decisions[row["turn"]].append(row)
    used = collections.Counter()
    kept, recorded, checkpoint, on = [], [], None, False
    for path in ("snapshots-20261125-150752-060b21.jsonl.gz", "snapshots-current.jsonl.gz"):
        for raw in _rows(second / path):
            if raw.get("type") == "player_turn":
                on = raw["floor"].get("quest_id") == QUEST and raw["turn"] > stop
                if not on:
                    continue
                same = decisions.get(raw["turn"], [])
                row = same[used[raw["turn"]]] if used[raw["turn"]] < len(same) else None
                used[raw["turn"]] += 1
                if checkpoint is None and row is not None and row["decision_sequence"] == FIRST:
                    checkpoint = checkpoint_bytes(policy)
                if checkpoint is not None:
                    kept.append(dict(raw, messages=raw["messages"] if row is None else row["messages"]))
                    recorded.append(None if row is None else {
                        "sequence": row["decision_sequence"], "turn": row["turn"],
                        "reason": row["reason"], "key": row["key"]})
            elif not (on and raw.get("type") == "knowledge"):
                continue
            elif checkpoint is not None:
                kept.append(raw)
                recorded.append(None)
            _decide(policy, raw)
    assert checkpoint is not None
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "policy.pkl.xz").write_bytes(lzma.compress(checkpoint, preset=PRESET))
    (OUTPUT / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"source": "n1b-418-q33-lure-target-1125", "boards": kept, "recorded": recorded},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), preset=PRESET))
    sys.stdout.write(f"{OUTPUT} {len(kept)} boards\n")


if __name__ == "__main__":
    main()
