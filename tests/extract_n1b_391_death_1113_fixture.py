"""Extract tests/fixtures/n1b-391-death-1113.pkl.xz.

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-391-smaug-death-1113/: n1-b life-391 (Magic-Eater Lv40,
Angband 80F) died 2026-11-13 18:54:35.  ``incident-captures/20261113-185435-player-death/
town-arrival`` holds the policy checkpoint of the last town arrival (decision 6075) and
``decision-tail.jsonl`` the decision rows since; ``full-snapshots/snapshots-current.jsonl.gz``
(the live generation, copied whole: the capture's own copy is a byte tail) every response
line since.

The tool restores the arrival checkpoint and decides every board through the live response
path (cli ``_consume_response_sequence`` and the public ``choose_key``, each key acknowledged
as posted) up to decision 6409, the death's board (every recorded key and reason must be
reproduced from the floor's arrival on, or nothing is written).  It keeps, as one
xz-compressed pickle:

* ``checkpoints``: per decision 6399-6409, the policy's checkpoint
  (latch_onset_capture.checkpoint_bytes) taken right after the previous key was posted;
* ``segments``: per decision 6399-6409, its decision row and the response lines delivered
  since the previous decision (the previous key's completion tagged on the last board).

Taken with bot-client c50cd91dc4 (main); a later checkpoint layout may need re-extraction.

    python tests/extract_n1b_391_death_1113_fixture.py
"""
import gzip
import json
import lzma
import os
import pickle
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "src"), str(HERE)]

import tests  # noqa: E402,F401 -- isolate runtime files before policy imports

from hengbot.cli import _consume_response_sequence  # noqa: E402
from hengbot.latch_onset_capture import checkpoint_bytes  # noqa: E402
from hengbot.monrace_knowledge import load_monrace_knowledge  # noqa: E402
from replay_town_arrival import restore  # noqa: E402
from tests.support.recorded import EDIT  # noqa: E402

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-391-smaug-death-1113")
INCIDENT = ROOT / "incident-captures/20261113-185435-player-death"
VISIT = INCIDENT / "town-arrival"
SNAPSHOTS = ROOT / "full-snapshots/snapshots-current.jsonl.gz"
DECISIONS = INCIDENT / "decision-tail.jsonl"
OUTPUT = HERE / "fixtures" / "n1b-391-death-1113.pkl.xz"
FIRST_SEQUENCE, CHECKPOINT_AFTER, LAST_SEQUENCE = 6076, 6398, 6409
# The town visit may replay with differences the town journal explains (not this death's
# subject).  On 80F (from 6139) six boards replay differently, each the choice or retry of an
# absorbed power the live bot made from screen lines the snapshot log does not keep (the cast's
# menu pages: the town journal of the same visit holds lines this log lacks); they must be these
# six and no other, and every board of the death (6405-6409) must match.
DUNGEON_FROM = 6139
KNOWN_DIFFERENCES = {
    6207: ("9", "explore", "mAi", "me-power:dark-room:lite-area"),
    6343: ("mB01", "ranged:magic-eater-device", "mAw", "me-power:fight-unhasted:speed"),
    6358: ("4", "melee", "mAw", "me-power:fight-unhasted:speed"),
    6359: ("4", "melee", "mAw", "me-power:fight-unhasted:speed"),
    6380: ("1", "seek-loot", "mAj", "me-power:after-destruction:map-area"),
    6404: ("1", "explore", "UCg", "me-power:deep-explore-redetect:detect-all:powerful"),
}
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "rung", "position")


def tagged(segment, previous):
    """The live executor marks the last board after a posted key with its completion."""
    if previous is None or not previous["key"]:
        return segment
    segment = list(segment)
    for index in range(len(segment) - 1, -1, -1):
        row = json.loads(segment[index])
        if row.get("type") in ("player_turn", "store"):
            row["_completed_operation_sequence"] = previous["decision_sequence"]
            row["_completed_operation_owner"] = previous["reason"]
            segment[index] = json.dumps(row, ensure_ascii=False) + "\n"
            break
    return segment


def segments():
    """(decision row, response lines since the previous decision) from FIRST_SEQUENCE on."""
    lines = [line for line in gzip.open(SNAPSHOTS, "rt", encoding="utf-8") if line.strip()]
    by_sequence = {}
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a line the capture cut
        if FIRST_SEQUENCE <= row.get("decision_sequence", -1) <= LAST_SEQUENCE:
            by_sequence[row["decision_sequence"]] = row
    rows = [by_sequence[sequence] for sequence in sorted(by_sequence)]
    arrival = json.loads((VISIT / "arrival.json").read_text(encoding="utf-8"))["turn"]
    cursor = next(index for index, line in enumerate(lines)
                  if json.loads(line).get("turn", -1) >= arrival)
    for row in rows:
        segment = []
        while cursor < len(lines) and json.loads(lines[cursor]).get("turn", -1) <= row["turn"]:
            segment.append(lines[cursor])
            cursor += 1
        if any(json.loads(line).get("type") in ("player_turn", "store") for line in segment):
            yield row, segment


def main() -> None:
    monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    kept, checkpoints, previous, differed = [], {}, None, set()
    with TemporaryDirectory() as scratch:
        os.chdir(HERE.parent)
        policy = restore(VISIT, Path(scratch))
        for row, segment in segments():
            segment = tagged(segment, previous)
            sequence = row["decision_sequence"]
            if sequence > CHECKPOINT_AFTER:
                checkpoints[sequence] = checkpoint_bytes(policy)
                kept.append({"decision": {field: row.get(field) for field in DECISION_FIELDS},
                             "lines": segment})
            _, boards = _consume_response_sequence(
                segment, policy, lambda _key: True, monrace,
                knowledge_ledger_path=Path(scratch) / "k.jsonl")
            key = str(policy.choose_key(policy.with_known_skill_exp(boards[-1])))
            replayed = (key, policy.last_reason)
            if replayed != (row["key"], row["reason"]) and sequence >= DUNGEON_FROM and (
                    KNOWN_DIFFERENCES.get(sequence) != (*replayed, row["key"], row["reason"])):
                raise SystemExit(f"{sequence}: replay {key!r} {policy.last_reason}"
                                 f" != live {row['key']!r} {row['reason']}")
            if replayed != (row["key"], row["reason"]) and sequence >= DUNGEON_FROM:
                differed.add(sequence)
            policy.confirm_key_posted(key)
            previous = row
    if differed != set(KNOWN_DIFFERENCES):
        raise SystemExit(f"the known differences did not all recur: {sorted(differed)}")
    fixture = {"source": ROOT.name, "checkpoints": checkpoints, "segments": kept}
    OUTPUT.write_bytes(lzma.compress(pickle.dumps(fixture, protocol=5),
                                     preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size, len(kept))


if __name__ == "__main__":
    main()
