"""The expeditions carry twice the computed Restore Mana (owner 2026-11-21).

Owner (verbatim, LOCKED): 「100Fに持っていく魔力復活の薬の量を想定の倍にして」 and 「99Fも想定の倍で」.
The computed target (restore_mana_target.plan's ``target``) stays "the plan" of the recall rule
「魔力復活の薬を予定の倍以上使ったとき」 (angband_finale restore_mana_overspent); what the preparation
owns, the readiness requires and the carry keeps is twice it (``carry``).

Recorded: n1-c life-217's town visit of 2026-11-21 05:55:10 (tests/fixtures/n1c-finale-prep-1121),
its first board.  DECLARED CONSTRUCTED: the expedition's Restore Mana used (for the recall rule).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, restore_mana_target
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-finale-prep-1121"


class FinaleRestoreManaDoubleRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        _recorded, supply = steps[0]
        self.board = supply()
        with contextlib.redirect_stdout(io.StringIO()):
            self.policy.choose_key(self.board)

    def tearDown(self):
        self.scratch.cleanup()

    def test_twice_the_plan_is_owned_required_and_carried(self):
        goal = angband_finale.restore_mana_goal(self.policy, self.board)
        self.assertIsNotNone(goal)
        rows = angband_finale.readiness(self.policy, self.board)
        self.assertEqual(rows["owned"]["restore_mana"]["required"], 2 * goal)
        self.assertEqual(rows["carried"]["restore_mana"]["required"], 2 * goal)
        self.assertEqual(angband_finale.restore_mana_carry(self.policy, self.board), 2 * goal)
        figures = restore_mana_target.plan(self.policy, self.board)
        self.assertEqual((figures["target"], figures["carry"]), (goal, 2 * goal))

    def test_the_recall_rule_keeps_the_plan(self):
        goal = angband_finale.restore_mana_goal(self.policy, self.board)
        memory = angband_finale.memory(self.policy)
        memory.restore_mana_used = 2 * goal - 1  # DECLARED
        self.assertFalse(angband_finale.restore_mana_overspent(self.policy, self.board))
        memory.restore_mana_used = 2 * goal  # DECLARED: the doubled carry used up
        self.assertTrue(angband_finale.restore_mana_overspent(self.policy, self.board))


if __name__ == "__main__":
    unittest.main()
