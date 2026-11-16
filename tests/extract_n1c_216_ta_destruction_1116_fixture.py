"""Extract tests/fixtures/n1c-216-ta-destruction-1116.pkl.xz.

Source: n1-c life-216 (Magic-Eater, 64F, 2026-11-16), copied read-only from the viewing server's
``~/hengbot-soak/n1-c/life-216/jsonlog`` by the TA-order investigation into a capture directory:

* ``policy.pkl``: the policy checkpoint (latch_onset_capture.checkpoint_bytes) the investigation
  restored for the 64F boards; restored with the board below and decided through the public
  ``choose_key``, main reproduces the live decision (``mCn3``,
  ``me-power:unbeatable-in-range:teleport-away``);
* ``tail_ta.jsonl.gz``: the response line of game turn 3030658 (19:44:11, decision 15311):
  アイアン・リッチ (a summoner, T3, left as a T1 is: ``leave_due`` True) beside the player, the
  absorbed *Destruction* at 97%;
* ``ta_full.jsonl``: the investigation's extract of the live decision rows; the row of that turn.

Kept as one xz-compressed pickle: ``checkpoint`` (bytes), ``board`` (the response line, a dict)
and ``decision`` (the live row).

    python tests/extract_n1c_216_ta_destruction_1116_fixture.py <capture directory>
"""
import gzip
import json
import lzma
import pickle
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-ta-destruction-1116.pkl.xz"
TURN = 3030658


if __name__ == "__main__":
    capture = Path(sys.argv[1])
    board = next(row for row in map(json.loads, gzip.open(capture / "tail_ta.jsonl.gz", "rt", encoding="utf-8"))
                 if row.get("type") == "player_turn" and row["turn"] == TURN)
    decision = next(row for row in map(json.loads, open(capture / "ta_full.jsonl", encoding="utf-8"))
                    if row["turn"] == TURN)
    case = {"checkpoint": (capture / "policy.pkl").read_bytes(), "board": board, "decision": decision}
    FIXTURE.write_bytes(lzma.compress(pickle.dumps(case), preset=9 | lzma.PRESET_EXTREME))
    print(FIXTURE.stat().st_size)
