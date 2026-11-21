"""Extract tests/fixtures/n1b-413-ring-flipflop-1122/recorded.pkl.xz.

n1-b life-413 (Magic-Eater Lv37) stopped 2026-11-22 02:24:17 in town with
``town:blocked:equipment-slot-flipflop:main_ring`` after Quest 25.  Source: the visit's
town-arrival checkpoint and the life's ``character-calibration.json`` (written by the
02:24:15 dump, decision 372), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-413-ring-flipflop-1122/ with the tail of the life's
loadout-report.jsonl and equipment-visit.jsonl.

Written out (pickled, xz): the journal boards of row 161 (decision 363, STR drained 84 -> 74,
殺戮の指輪 worn, 腕力の指輪 at Home) and row 171 (decision 373, STR restored by
腕力復活の薬), each with the policy's cached ~f skill exp; 腕力の指輪 (+5) {+腕} as row 0's
board wore it; the arrival policy's monster knowledge; the restored calibration.

DECLARED CONSTRUCTED: the drained calibration.  The checkpoint's calibration sidecar is an
older session's (STR undrained, WIS drained) and the visit's own dumps have no dump file in
the capture; the calibration the visit derived after its WIS restore (decision 330) differs
from the restored one only in STR, natural 74 (loadout-report ``combat_inputs.natural_str``
of 02:23:45-02:24:11), so it is the restored one with STR natural 74 (base 104 = the board's
``use``) and row 161's printed stat key.  With it the optimizer reproduces the live melee of
both searches exactly (257.516 drained, 261.507 restored).

    python tests/extract_n1b_413_ring_flipflop_fixture.py
    (PYTHONPATH: src, tests and the root)
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import json
import lzma
import pickle
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from hengbot.warrior_optimization import load_character_calibration
from replay_town_arrival import journal, restore

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-413-ring-flipflop-1122")
VISIT = CAPTURE / "town-arrival" / "20261122-022329.374259196-turn2591166"
TARGET = Path(__file__).with_name("fixtures") / "n1b-413-ring-flipflop-1122" / "recorded.pkl.xz"
DRAINED_ROW, RESTORED_ROW, ARRIVAL_ROW = 161, 171, 0
DRAINED_STR = 74


def main() -> None:
    rows = journal(VISIT)
    with TemporaryDirectory() as raw:
        policy = restore(VISIT, Path(raw))

        def board(index):
            entry = rows[index]
            line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
            return policy._with_cached_skill_exp(
                parse_snapshot(json.loads(line), policy._monrace_knowledge))

        drained_board, restored_board = board(DRAINED_ROW), board(RESTORED_ROW)
        restored = load_character_calibration(CAPTURE / "character-calibration.json")
        drained = replace(
            restored,
            natural_stats=(DRAINED_STR, *restored.natural_stats[1:]),
            stat_cur=(DRAINED_STR, *restored.stat_cur[1:]),
            base_stats=(drained_board.player.stat_use[0], *restored.base_stats[1:]),
            visible_stat_key=drained_board.player.printed_stat_cur_key,
        )
        recorded = {
            "drained_board": drained_board,
            "restored_board": restored_board,
            "strength_ring": next(item for item in board(ARRIVAL_ROW).equipment
                                  if item.slot == "main_ring"),
            "knowledge": policy._monrace_knowledge,
            "drained_calibration": drained,
            "restored_calibration": restored,
            "decisions": (rows[DRAINED_ROW]["decision_sequence"],
                          rows[RESTORED_ROW]["decision_sequence"]),
        }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(lzma.compress(pickle.dumps(recorded), preset=9 | lzma.PRESET_EXTREME))
    print(TARGET, TARGET.stat().st_size)


if __name__ == "__main__":
    main()
