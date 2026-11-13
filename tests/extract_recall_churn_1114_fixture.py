"""Extract tests/fixtures/recall-churn-1114.pkl.xz.

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-207-recall-churn-1114/: n1-c life-207 (Magic-Eater Lv46,
max HP 603, build bot-7c614b268) recalled into ガラスの城 (Glass castle, dungeon 20) 60F and back
about once a minute on 2026-11-14 (the owner's 「帰還の条件がおかしい気がする」).
``ta2/town-arrival/20261114-042638.294254307-turn5212597`` is the policy checkpoint of the town
arrival of 04:26:38 (before decision 4090), ``dec-tail4.jsonl.gz`` the decision rows since and
``snap-current.jsonl.gz`` (the live snapshot generation ``snapshots-current.jsonl.gz`` of 04:31)
every response line since.

The tool restores the arrival checkpoint, replays the town visit from its journal (decisions
4091-4131, replay_town_arrival: the journal keeps the CLI timer latches the snapshot log does
not), then decides every board of the floor through the live response path (cli
``_consume_response_sequence`` and the public ``choose_key``, each key acknowledged as posted)
up to decision 4135; every recorded key and reason must be reproduced (or nothing is written).  It keeps, as one xz-compressed pickle:

* ``checkpoints``: per decision of ``KEPT``, the policy's checkpoint
  (latch_onset_capture.checkpoint_bytes) taken right after the previous key was posted;
* ``segments``: per decision of ``KEPT``, its decision row and the response lines delivered
  since the previous decision (the previous key's completion tagged on the last board).

Taken with bot-client 7c614b2680 (main); a later checkpoint layout may need re-extraction.

    python tests/extract_recall_churn_1114_fixture.py
"""
import gzip
import json
import lzma
import os
import pickle
import sys
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "src"), str(HERE)]

import tests  # noqa: E402,F401 -- isolate runtime files before policy imports

from hengbot.cli import _consume_response_sequence  # noqa: E402
from hengbot.latch_onset_capture import checkpoint_bytes  # noqa: E402
from hengbot.monrace_knowledge import load_monrace_knowledge  # noqa: E402
from replay_town_arrival import decisions, restore  # noqa: E402
from tests.support.recorded import EDIT  # noqa: E402

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-207-recall-churn-1114")
VISIT = ROOT / "ta2/town-arrival/20261114-042638.294254307-turn5212597"
SNAPSHOTS = ROOT / "snap-current.jsonl.gz"
DECISIONS = ROOT / "dec-tail4.jsonl.gz"
OUTPUT = HERE / "fixtures" / "recall-churn-1114.pkl.xz"
SINCE = "2026-11-14T04:26:38"  # the decision sequence restarts with the bot process
FIRST_SEQUENCE, LAST_SEQUENCE = 4132, 4135  # the floor after the journalled town visit
KEPT = (4132, 4133, 4134, 4135)  # the 60F arrival board to the first board after the Recall read
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


def _lines(path):
    """The generation's lines; the live generation may end in a member still being written."""
    lines = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    lines.append(line)
    except (EOFError, zlib.error):
        pass
    return lines


def _rows():
    rows = {}
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue  # a line the copy cut
            if (row.get("time", "") >= SINCE
                    and FIRST_SEQUENCE <= row.get("decision_sequence", -1) <= LAST_SEQUENCE):
                rows.setdefault(row["decision_sequence"], row)
    return [rows[sequence] for sequence in sorted(rows)]


def segments(after_turn):
    """(decision row, response lines since the previous decision) from FIRST_SEQUENCE on: the
    lines after the journal's last board (game turn ``after_turn``)."""
    lines = _lines(SNAPSHOTS)
    cursor = next(index for index, line in enumerate(lines)
                  if json.loads(line).get("turn", -1) > after_turn)
    for row in _rows():
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
        last_turn = None
        for recorded, supply in decisions(policy, VISIT, Path(scratch)):
            board = supply()
            key = policy.choose_key(board)
            if (key, policy.last_reason) != (recorded["key"], recorded["reason"]):
                raise SystemExit(f"journal row {recorded['row']}: replay {key!r} {policy.last_reason}"
                                 f" != live {recorded['key']!r} {recorded['reason']}")
            policy.confirm_key_posted(key)
            last_turn = board.turn
        for row, segment in segments(last_turn):
            segment = tagged(segment, previous)
            sequence = row["decision_sequence"]
            if sequence in KEPT:
                checkpoints[sequence] = checkpoint_bytes(policy)
                kept.append({"decision": {field: row.get(field) for field in DECISION_FIELDS},
                             "lines": segment})
            _, boards = _consume_response_sequence(
                segment, policy, lambda _key: True, monrace,
                knowledge_ledger_path=Path(scratch) / "k.jsonl")
            key = str(policy.choose_key(policy.with_known_skill_exp(boards[-1])))
            if (key, policy.last_reason) != (row["key"], row["reason"]):
                raise SystemExit(f"{sequence}: replay {key!r} {policy.last_reason}"
                                 f" != live {row['key']!r} {row['reason']}")
            policy.confirm_key_posted(key)
            previous = row
            if sequence >= LAST_SEQUENCE:
                break
    if sorted(checkpoints) != sorted(KEPT):
        raise SystemExit(f"kept {sorted(checkpoints)}, wanted {KEPT}")
    fixture = {"source": ROOT.name, "checkpoints": checkpoints, "segments": kept}
    OUTPUT.write_bytes(lzma.compress(pickle.dumps(fixture, protocol=5),
                                     preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size, len(kept))


if __name__ == "__main__":
    main()
