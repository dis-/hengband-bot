"""n1-b life-413: the launcher swapped to the Short Bow and back within six seconds.

Owner 2026-11-22 (verbatim): 「射撃武器の直し入った？」→「変わってないよ」→「一瞬変えた後戻してるみたい」.

What happened (2026-11-22 00:13:49-00:13:57, jsonlog/loadout-report.jsonl and bot-decisions):
the Magic-Eater bought a *Destruction* staff (5 charges).  Carried, at the worn device skill it
was a reliable staff, so the optimizer's depth-band descent (equipment_optimizer.optimize_loadout)
found a set for the 80F band; there the launcher is read for its abilities only (owner
2026-11-18, me_deep_launcher.launcher_power_unscored) and ★森の狩人ロビンフッドのショート・ボウ
(+2 DEX, resist curse) won: the equipment transaction wore it.  Four seconds later the staff
sequence (me_staff_sequence, the *Destruction* row 「持ち帰って充填してから取り込む」) absorbed the
staff into the power at 75% (below the 80% the means needs), the descent fell back to the 49F
band, where the launcher is compared by damage (owner 2026-11-21), and the ライト・クロスボウ
(x3) (+10,+10) with the 鋼鉄のクロスボウの矢 came back.

Recorded: the next visit's town-arrival checkpoint (00:17:35, turn 2079219, its first journal
row; the swap's own checkpoint had rotated out): the same power record (*破壊* 9 charges at 75%),
Home and loadout.  CONSTRUCTED on it: the staff the game sent at 00:13:50 (turn 2051429, in the
pack), put back in the pack where the game listed it.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_means, me_capability
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-launcher-flip-1122"
ROBIN = "★森の狩人ロビンフッドのショート・ボウ"
CROSSBOW = "ライト・クロスボウ"


def _staff() -> dict:
    return json.loads(lzma.decompress((FIXTURE / "staff.json.xz").read_bytes()))


def _decide(with_staff: bool):
    """(policy, board, key) of the visit's first decision, the staff in the pack or not."""
    scratch = TemporaryDirectory()
    policy, journal, steps = load(FIXTURE, Path(scratch.name))
    board = steps[0][1]()
    if with_staff:
        entry = journal[0]
        raw = json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])
        inventory = raw["inventory"]
        # The game's pack order: after the wand (g), before the bolts (h, i -> i, j).
        for item in inventory[7:]:
            item["slot"] = chr(ord(item["slot"]) + 1)
        raw["inventory"] = [*inventory[:7], {**_staff(), "slot": "h"}, *inventory[7:]]
        board = parse_snapshot(raw, policy._monrace_knowledge)
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return scratch, policy, board, key


class LauncherFlipRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {}
        for with_staff in (False, True):
            scratch, policy, board, key = _decide(with_staff)
            cls.runs[with_staff] = (policy, board, key)
            policy._home_disposal.history_path.unlink(missing_ok=True)
            cls.addClassCleanup(scratch.cleanup)

    def chosen(self, with_staff):
        policy = self.runs[with_staff][0]
        result = policy._equipment_optimization_preparation.result
        return result.chosen_decision.band, dict(result.best.loadout.slots)["bow"].item.name

    def test_the_record_and_the_staff(self):
        policy, board, key = self.runs[True]
        staff = next(item for item in board.inventory if destruction_means.is_staff(item))
        self.assertEqual((staff.slot, staff.charges), ("h", 5))
        row = me_capability.observed_row(policy, *destruction_means.POWER)
        self.assertEqual((row["current"], row["max"], row["success"]), (9, 9, 75))
        # The staff sequence takes the board for the absorption's trip, as at 00:13:50.
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant")

    def test_a_staff_the_town_absorbs_is_no_means(self):
        policy, board, _key = self.runs[True]
        means = destruction_means.Means(policy, board)
        staff = next(item for item in board.inventory if destruction_means.is_staff(item))
        self.assertTrue(means.town_absorbs(staff))
        self.assertIsNone(means.carried_charged_staff)
        self.assertFalse(means.depth_gate())
        self.assertFalse(means.supplies(staff))
        self.assertEqual(policy._optimizer_destruction_means(
            board, policy._equipment_catalog.items,
            policy._validated_character_calibration(board)), (False, None))

    def test_the_launcher_does_not_change_with_the_staff_it_absorbs(self):
        """Without the staff (the board after the absorption) the 49F band and the crossbow; with
        it the same, not the 80F band and the Short Bow worn for four seconds."""
        self.assertEqual(self.chosen(False)[0], 49)
        self.assertTrue(self.chosen(False)[1].startswith(CROSSBOW), self.chosen(False)[1])
        self.assertEqual(self.chosen(True), self.chosen(False))
        self.assertFalse(self.chosen(True)[1].startswith(ROBIN))


if __name__ == "__main__":
    unittest.main()
