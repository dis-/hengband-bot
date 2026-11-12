"""Extract tests/fixtures/n1b-377-death-1112.pkl.xz.

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-377-death-1112/: n1-b life-377 (Magic-Eater Lv46,
Angband 80F) died 2026-11-12 13:46:53.  ``incident-captures/20261112-134653-player-death/
town-arrival`` holds the policy checkpoint of the last town arrival (decision 7763);
``full-snapshots/snapshots-current.jsonl.gz`` every response line since; ``captures/
20261112-134657-exit-no-marker/bot-decisions.jsonl.gz`` the decision rows.

The tool restores the arrival checkpoint and decides every board through the live response
path (cli ``_consume_response_sequence`` and the public ``choose_key``, each key acknowledged
as posted) up to decision 7964, the last sensed-t1:approach-destruction step before the
death's boards, and on through 7976 (every recorded key and reason must be reproduced from
the floor's arrival on, or nothing is written).  It keeps, as one xz-compressed pickle (the
checkpoints are pickles already, and one stream compresses the twelve near-identical ones):

* ``checkpoints``: per decision 7965-7976, the policy's checkpoint
  (latch_onset_capture.checkpoint_bytes) taken right after the previous key was posted:
  the state the live bot decided that board from, so a test decides each board from the
  live history (no earlier board's different answer leaks into it);
* ``segments``: per decision 7965-7976, its decision row and the response lines delivered
  since the previous decision (the previous key's completion tagged on the last board, as
  the live executor does).

Taken with bot-client bd668fd3ea (main); a later checkpoint layout may need re-extraction.

    python tests/extract_n1b_377_death_1112_fixture.py
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

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-377-death-1112")
VISIT = ROOT / "incident-captures/20261112-134653-player-death/town-arrival"
SNAPSHOTS = ROOT / "full-snapshots/snapshots-current.jsonl.gz"
DECISIONS = ROOT / "captures/20261112-134657-exit-no-marker/bot-decisions.jsonl.gz"
OUTPUT = HERE / "fixtures" / "n1b-377-death-1112.pkl.xz"
FIRST_SEQUENCE, CHECKPOINT_AFTER, LAST_SEQUENCE = 7763, 7964, 7976
# The town visit replays with differences the town journal explains (not this death's
# subject); every 80F decision from the arrival (7871, the first *Destruction*) must match.
DUNGEON_FROM = 7871
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
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    rows = [row for row in rows if FIRST_SEQUENCE <= row["decision_sequence"] <= LAST_SEQUENCE]
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
    kept, checkpoints, previous = [], {}, None
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
            if (key, policy.last_reason) != (row["key"], row["reason"]) and sequence >= DUNGEON_FROM:
                raise SystemExit(f"{sequence}: replay {key!r} {policy.last_reason}"
                                 f" != live {row['key']!r} {row['reason']}")
            policy.confirm_key_posted(key)
            previous = row
    fixture = {"source": ROOT.name, "checkpoints": checkpoints, "segments": kept}
    OUTPUT.write_bytes(lzma.compress(pickle.dumps(fixture, protocol=5),
                                     preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size, len(kept))


if __name__ == "__main__":
    main()
