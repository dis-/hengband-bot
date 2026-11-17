"""Five Stone to Mud wands for every class but the Magic-Eater (owner 2026-11-17).

Owner, verbatim: 「戦士は岩石溶解を5本だけ持てばいい。」  n1-a life-530 (zombie warrior Lv43)
came home 2026-11-17 23:28 at 194.0/180.0 lb with 18 Stone to Mud wands (215 charges, 18 lb) in
slot k, kept whole as the zombie's MANA food reserve device (``mana-device``) and by the 10-20
keep-all (``utility:stone-to-mud``).  The first weight-overload deposit (row 2) shed the two
axes and a *Destruction* scroll only (``dndmdg``).

Now the carry keeps five wands (stone_to_mud_carry) whatever branch holds the stack, and row 2
also shelves the other 13 (``dk13``).

Recorded: n1-a life-530's town-arrival checkpoint (tests/fixtures/n1a-530-home-full-reject-1117,
rows 0-1 decided through the public choose_key and compared with the record).  The control is
n1-c life-205 (Magic-Eater), whose 8 drained wands stay whole (tests/fixtures/
n1c-205-food-devices-1113).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import stone_to_mud_carry
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
N1A = FIXTURES / "n1a-530-home-full-reject-1117"
N1C = FIXTURES / "n1c-205-food-devices-1113"
DEPOSIT_ROW = 2


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def wands(board):
    return [item for item in board.inventory if stone_to_mud_carry.is_stone_to_mud_wand(item)]


class WarriorStoneToMudCarryRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(N1A, Path(cls.scratch.name))
        cls.replayed = []
        for recorded, supply in steps[:DEPOSIT_ROW]:
            key = policy.choose_key(supply())
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])
        cls.policy, cls.board = policy, steps[DEPOSIT_ROW][1]()

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_warrior_keeps_five_of_its_eighteen_wands(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        board = self.board
        self.assertEqual(board.player.class_id, 0)
        [wand] = wands(board)
        self.assertEqual((wand.slot, wand.count, wand.charges), ("k", 18, 215))
        # Before: (18, "mana-device") -- the whole stack.
        self.assertEqual(self.policy._retention_reservation_detail(board, wand), (5, "mana-device"))
        self.assertEqual(self.policy._retention_surplus(board, wand), 13)
        self.assertTrue(self.policy._home_deposit_candidate(wand, board))

    def test_the_weight_deposit_shelves_the_thirteen_others(self):
        self.assertEqual(self.journal[DEPOSIT_ROW]["key"], "dndmdg\x1b")
        key = self.policy.choose_key(self.board)
        self.assertEqual((key, self.policy.last_reason),
                         ("dndmdk13\rdg\x1b", "home:weight-overload-deposit"))

    def test_five_wands_are_shared_best_stack_first(self):
        # DECLARED CONSTRUCTED: the recorded stack split into a drained stack of 4 before a
        # charged stack of 3 (the game keeps them apart only while their charges differ).
        [wand] = wands(self.board)
        drained = replace(wand, slot="k", count=4, charges=0)
        charged = replace(wand, slot="l", count=3, charges=36)
        board = replace(self.board, inventory=(
            *(item for item in self.board.inventory if item is not wand), drained, charged))
        self.assertEqual(stone_to_mud_carry.kept_wand_share(board, charged), 3)
        self.assertEqual(stone_to_mud_carry.kept_wand_share(board, drained), 2)


class MagicEaterStoneToMudControlRecordedTest(unittest.TestCase):
    def test_the_magic_eater_keeps_every_wand(self):
        with TemporaryDirectory() as scratch:
            policy, _journal, steps = load(N1C, Path(scratch))
            board = steps[0][1]()
            self.assertEqual(board.player.class_id, 16)
            [wand] = wands(board)
            self.assertEqual(wand.count, 8)
            self.assertFalse(stone_to_mud_carry.stone_to_mud_cap_applies(board))
            self.assertEqual(stone_to_mud_carry.stone_to_mud_kept(board, wand, wand.count), 8)
            self.assertEqual(policy._retention_reservation_detail(board, wand),
                             (8, "me-staff:absorb"))
            self.assertFalse(policy._home_deposit_candidate(wand, board))


if __name__ == "__main__":
    unittest.main()
