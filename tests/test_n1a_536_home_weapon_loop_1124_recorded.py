"""n1-a life-536: the Home weight deposit shelves the weapon the digger's hand returns to.

n1-a life-536 (Warrior Lv35, the mining fundraise "mine", シャベル and 穴掘りのドワーフのシャベル
in the hands) came back from Yeek cave 1F with 殺戮のロッホアーバー・アックス in the pack, over
the weight limit (1905 against 1750; the game's slowdown starts 350 over).  On every town visit
the Home weight deposit (``home:weight-overload-deposit``) shelved the axe, the combat-weapon
withdrawal (``_home_rearm_key``: a digger in the main hand and no weapon in the pack) took it
back, and the deposit shelved it again: nine times in the 19:15 visit, until
``town:blocked:stage-deadline:home`` (2026-11-24 19:15:31; also 17:28 and 19:02-19:14).

One verdict for the lent hands' piece (slot_lending ``retains_hands_return``): while a digger
holds a hand, the piece that hand returns to stays carried, so the weight relief sheds something
else (here 41 of the 86 鉄弾 and the 耐火の薬) and the withdrawal has nothing to take back.

Recorded: the 19:15:06 town-arrival checkpoint of n1-a life-536
(tests/fixtures/n1a-536-home-weapon-loop-1124): its first 36 rows replay as recorded, and row 36
is the arrival's Home weight deposit, recorded as 'dodb' + ESC (the axe in slot o).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load
from town_work_corpus import replay_window

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-536-home-weapon-loop-1124"
AXE = "殺戮のロッホアーバー・アックス (6d8) (+4,+3) {|毒}"
DEPOSIT_ROW = 36


class HomeWeaponLoopTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
            cls.town = replay_window("n1a-536-home-weapon-loop", cls.policy,
                                     iter(steps[:DEPOSIT_ROW]))
            cls.recorded, supply = steps[DEPOSIT_ROW]
            cls.board = supply()
            cls.key = cls.policy.choose_key(cls.board)
        cls.reason = cls.policy.last_reason

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def _axe(self):
        return next(item for item in self.board.inventory if item.name == AXE)

    def test_the_recorded_boards(self):
        self.assertIsNone(self.town.first_divergence)
        self.assertEqual(self.town.matched_rows, DEPOSIT_ROW)
        self.assertEqual((self.recorded["key"], self.recorded["reason"]),
                         ("dodb\x1b", "home:weight-overload-deposit"))
        self.assertEqual(self.policy._fundraising_mode, "mine")
        hands = {item.slot: item.is_digging_tool for item in self.board.equipment
                 if item.slot in ("main_hand", "sub_hand")}
        self.assertEqual(hands, {"main_hand": True, "sub_hand": True})
        self.assertEqual(self._axe().slot, "o")
        self.assertTrue(self.policy._inventory_overweight(self.board))

    def test_the_weight_deposit_keeps_the_returning_weapon(self):
        from hengbot import slot_lending

        policy, board, axe = self.policy, self.board, self._axe()
        self.assertTrue(slot_lending.retains_hands_return(policy, board, axe))
        self.assertEqual(policy._retention_reservation_detail(board, axe),
                         (1, slot_lending.HANDS_RETURN_BRANCH))
        self.assertEqual(policy._retention_surplus(board, axe), 0)
        relief = policy._weight_relief_selection(board, plan=False)
        self.assertNotIn(axe.slot, {item.slot for item in relief.deposits})
        # The Home still sheds the overweight, from what is not the hands' return.
        self.assertEqual(self.reason, "home:weight-overload-deposit")
        self.assertTrue(self.key.startswith("d"), repr(self.key))
        self.assertNotIn("do", self.key)

    def test_the_withdrawal_reads_the_same_verdict(self):
        """The combat-weapon withdrawal takes a weapon out only while the pack has none for the
        digger's hand; the axe the retention keeps is that weapon."""
        policy, board = self.policy, self.board
        self.assertTrue(policy._pack_has_safe_melee_weapon(board))
        from hengbot import slot_lending
        self.assertEqual(slot_lending.return_item(policy, board, "main_hand").slot,
                         self._axe().slot)

    def test_no_digger_in_hand_no_hold(self):
        from dataclasses import replace
        from hengbot import slot_lending

        policy, board = self.policy, self.board
        armed = replace(board, equipment=tuple(
            item for item in board.equipment if item.slot not in ("main_hand", "sub_hand")))
        self.assertFalse(slot_lending.retains_hands_return(policy, armed, self._axe()))


if __name__ == "__main__":
    unittest.main()
