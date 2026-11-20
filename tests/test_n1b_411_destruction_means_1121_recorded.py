"""The absorbed *Destruction* in the loadouts the optimizer weighs, a worn NO_MAGIC aside.

n1-b life-411 (Magic-Eater, *Destruction* absorbed 99, displayed 96%) came back from its mining
set at 2026-11-21 04:55:38 wearing a body armour with NO_MAGIC (反魔法).  A worn NO_MAGIC refuses
every absorbed power (me_power_success.REFUSED_FAILURE), so on that board the 50F+ means is not
held (destruction_use.holds_means: true).  But the optimizer read the board's answer as the
answer for every loadout (``has_destruction``): with the armour worn no loadout had the means,
and with it off every loadout had it, the NO_MAGIC one included.

Recorded: that arrival's checkpoint and its first board (tests/
extract_n1b_411_destruction_means_1121_fixture.py).

DECLARED CONSTRUCTED: the worn loadout without the NO_MAGIC piece (its slot left empty).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_means, destruction_use, me_power_success
from hengbot.equipment_optimizer import current_loadout, destruction_means as loadout_means
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-destruction-means-1121"


class N1b411DestructionMeansRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, steps = load(FIXTURE, Path(self.scratch.name))
        recorded, supply = steps[0]
        self.board = supply()
        with contextlib.redirect_stdout(io.StringIO()):
            self.policy.choose_key(self.board)

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def test_the_worn_anti_magic_refuses_this_board_only(self):
        policy, board = self.policy, self.board
        self.assertTrue(me_power_success.worn_anti_magic(board))
        means = destruction_means.Means(policy, board)
        self.assertEqual(means.absorbed_charges, 0)
        self.assertFalse(destruction_use.holds_means(policy, board))
        # The loadouts the search weighs: the power itself is reliable without the armour.
        self.assertEqual(means.unrefused_absorbed_charges, 99)
        self.assertTrue(means.optimizer_without_gear())

    def test_a_no_magic_loadout_has_no_absorbed_means(self):
        worn = current_loadout(self.policy._equipment_catalog.items)
        self.assertIn(me_power_success.TR_NO_MAGIC, worn.flags)
        self.assertFalse(loadout_means(worn, True, None))
        without = replace(worn, slots=tuple((slot, item) for slot, item in worn.slots
                                            if me_power_success.TR_NO_MAGIC not in item.flags))
        self.assertTrue(loadout_means(without, True, None))


if __name__ == "__main__":
    unittest.main()
