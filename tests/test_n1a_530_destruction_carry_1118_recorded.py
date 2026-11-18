"""The Home's *Destruction* staves leave with a 50F+ departure, and none leaves without them.

n1-a life-530 (Lv50 Warrior) kept 17 Staves of *Destruction* (63 charges) in the Home with a
device skill that makes them reliable (92.3%).  In town the 50F+ gate counts a Home staff
(destruction_use.holds_means, owner 2026-11-15 「装備で魔法道具使用能力を向上させて杖の成功率を
上げることで先に進むことができる」), so the Castle 51F destination opened; but the Home catalogue
shortage binder (policy_home._home_procurement_batch_member) did not take the staff, and the
"*Destruction* uses" row (current 0 / target 5) blocked no departure.  Every dive landed at 51F
without the means and read Word of Recall on the arrival board (destruction_use.
means_spent_recall_key): about 250 round trips from 10:29 to 12:50, the last one fatal.

Owner 2026-11-15 「*破壊* の杖と技能の装備は深さに関係なく持つ」 and 2026-11-18, verbatim
「破壊を持っていないのに50F以降にいるのが不具合」: the Home take withdraws the staff
(``_supplies_destruction``, as many staves as carry the uses), the departure leaf
``destruction_carried`` holds a 50F+ departure while the means is not carried, and the final
town-to-dungeon boundary (``_dungeon_entry_allowed``) refuses a 50F+ arrival without it.

Recorded: the 12:50:39 town-arrival checkpoint of that fatal departure and its first 17 journal
rows (tests/extract_n1a_530_destruction_carry_1118_fixture.py), decided through the public
choose_key; rows 0-3 replay as recorded, row 4 (the Home page) binds the staff instead of the
recorded Potion of Speed.

DECLARED CONSTRUCTED: ``carried`` -- row 4's board with one staff of the Home's first stack (5
charges) in the pack, the board the withdrawal of row 5 leads to.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_means, destruction_use
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-destruction-carry-1118"
HOME_ROW, RECALL_ROW = 4, 16


def visit(scratch: Path):
    """(policy, row 4's board, its key and reason, row 5's key and reason, rows 0-3 replayed,
    the recorded rows)."""
    policy, _journal, steps = load(FIXTURE, scratch)
    replayed = []
    for recorded, supply in steps[:HOME_ROW]:
        key = policy.choose_key(supply())
        replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
        policy.confirm_key_posted(recorded["key"])
    recorded, supply = steps[HOME_ROW]
    board = supply()
    home = (policy.choose_key(board), policy.last_reason,
            policy._home_pending_item, policy._home_pending_quantity)
    policy.confirm_key_posted(home[0])
    withdraw = (policy.choose_key(steps[HOME_ROW + 1][1]()), policy.last_reason)
    return policy, board, home, withdraw, replayed, [row for row, _supply in steps]


class N1a530DestructionCarry1118RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        (cls.policy, cls.board, cls.home, cls.withdraw, cls.replayed,
         cls.rows) = visit(Path(cls.scratch.name))

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def staves(self):
        return destruction_means.Means(self.policy, self.board).home_staves

    def carried(self):
        """DECLARED CONSTRUCTED: one staff of the Home's first stack in the pack."""
        staff = self.staves()[0]
        letters = {item.slot for item in self.board.inventory}
        slot = next(chr(code) for code in range(ord("a"), ord("z") + 1) if chr(code) not in letters)
        inventory = type(self.board.inventory)([*self.board.inventory, replace(staff, slot=slot, count=1)])
        return replace(self.board, inventory=inventory)

    def test_the_recorded_visit(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.assertEqual(self.rows[HOME_ROW]["reason"], "home:queue-catalogue-shortage")
        self.assertEqual(self.rows[HOME_ROW + 1]["reason"], "home:atomic-withdraw")
        self.assertEqual(self.rows[RECALL_ROW]["reason"], "town:recall-to-alt-dungeon")
        board, policy = self.board, self.policy
        self.assertEqual(sum(item.count for item in self.staves()), 17)
        self.assertEqual(sum(destruction_means.stack_charges(item) for item in self.staves()), 63)
        self.assertFalse(any(destruction_means.is_staff(item) for item in board.inventory))
        self.assertGreaterEqual(destruction_use.staff_success(board.player, 50), 80)
        # The town's gate counts the Home staves: the 51F destination is open.
        self.assertTrue(destruction_use.holds_means(policy, board))
        self.assertEqual(policy._intended_dive_depth(board), 51)
        self.assertEqual(policy._required_destruction_uses(board), 5)
        self.assertEqual(policy._total_destruction_uses(board), 0)

    def test_the_home_page_binds_the_staff(self):
        policy = self.policy
        key, reason, pending, quantity = self.home
        self.assertEqual((key, reason), ("\x1b", "home:queue-catalogue-shortage"))
        staff = next(item for item in self.staves() if policy._item_signature(item) == pending)
        self.assertTrue(destruction_means.is_staff(staff))
        # The shortage counts uses; one staff of five charges carries the five.
        self.assertEqual((staff.charges, quantity), (5, 1))
        # Row 5 takes one staff of that stack (the Home page's letter C) instead of the Potion of
        # Speed the live process took ('5pn1\r\x1b').
        self.assertEqual(self.withdraw, ("5 pC1\r\x1b", "home:atomic-withdraw"))

    def test_no_departure_leaves_without_the_staff(self):
        policy, board = self.policy, self.board
        self.assertFalse(destruction_means.departure_carried(policy, board, 51))
        self.assertTrue(destruction_means.departure_carried(policy, board, 49))
        self.assertFalse(policy._town_departure_conjuncts(board, commit=False)["destruction_carried"])
        self.assertFalse(policy._dungeon_entry_allowed(
            board, via_recall=True, destination_depth=51))
        self.assertEqual(policy.last_reason, "depth-gate:destination-51:destruction-not-carried")

    def test_the_carried_staff_opens_the_departure(self):
        policy, carried = self.policy, self.carried()
        self.assertTrue(destruction_means.departure_carried(policy, carried, 51))
        self.assertTrue(policy._town_departure_conjuncts(carried, commit=False)["destruction_carried"])
        self.assertEqual(policy._total_destruction_uses(carried), 5)
        self.assertEqual(destruction_means.violations(policy, carried), ())
        self.assertEqual(destruction_means.violations(policy, self.board), ())


if __name__ == "__main__":
    unittest.main()
