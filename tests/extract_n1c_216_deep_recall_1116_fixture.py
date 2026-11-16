"""Extract tests/fixtures/n1c-216-deep-recall-1116.pkl.xz.

Source: n1-c life-216 (Magic-Eater Lv41, Castle 64F, 2026-11-16), copied read-only from the
viewing server's ``~/hengbot-soak/n1-c/life-216``:

* ``town-arrival/20261116-203526.366174117-turn3160191``: the town visit before the dive, replayed
  through tests/replay_town_arrival.py (67 of 67 rows matched, the last ``town:wait-recall``);
* ``state.jsonl`` lines 3982-3983: the first 64F board (game turn 3162281, 20:35:43, decision 3710);
  line 3982 was delivered to the replayed policy, whose checkpoint
  (latch_onset_capture.checkpoint_bytes) was then taken;
* the decision log's row of that board: ``re`` ``deep-teleport:recall``.

Kept as one xz-compressed pickle: ``checkpoint`` (bytes), ``board`` (state line 3983, a dict)
and ``decision`` (the live row's key and reason).

    python tests/extract_n1c_216_deep_recall_1116_fixture.py <checkpoint.pkl> <state line 3983 file>
"""
import json
import lzma
import pickle
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-deep-recall-1116.pkl.xz"
DECISION = {"turn": 3162281, "decision_sequence": 3710, "key": "re", "reason": "deep-teleport:recall"}


if __name__ == "__main__":
    checkpoint = Path(sys.argv[1]).read_bytes()
    board = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    assert board["turn"] == DECISION["turn"]
    case = {"checkpoint": checkpoint, "board": board, "decision": DECISION}
    FIXTURE.write_bytes(lzma.compress(pickle.dumps(case), preset=9 | lzma.PRESET_EXTREME))
    print(FIXTURE.stat().st_size)
