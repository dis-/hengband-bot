"""A pack below the four-free-slot floor with nothing legal to dispose of goes on with the visit
instead of stopping (n1-a life-545, MAINTAINABILITY.md 2).

Recorded (tests/extract_n1a_545_overflow_no_disposal_1128_fixture.py,
``n1a-545-overflow-no-disposal-1128``): the town-arrival checkpoint of 2026-11-28 03:00:59
(Amberite Rogue CL39, Sorcery, gold 24237, arrival turn 6761472) after a dive that returned for a
full pack.  Row 2 deposited the worn-out suit of armour at Home, row 10 bought recall scrolls at
the Alchemist, and row 12 stopped as town:blocked:overflow-no-legal-disposal with 21 of the 23
pack slots used (2 free, the floor MIN_TERMINAL_FREE_PACK_SLOTS is 4).  Home held 138 of 240.

Twenty of the 21 stacks are the retention reservations' whole stack (the three Sorcery books,
four foods, six potions, Teleportation and Word of Recall, three rods, Stone to Mud, two kinds of
shot); the 21st, a Mushroom of Restoring, is reserved by nothing but no Home deposit, sale or
destruction rule takes it.  So no legal disposal could reach the floor: the overflow owner's
answer was the stop.  The fix gives way: nothing is returned, the visit goes on to its town end,
which waives the OPTIONAL free-slot leaf.

Every row before the stop is replayed through the public ``choose_key`` and compared with the
record (full state: the town-arrival checkpoint, its journal and sidecars).

DECLARED CONSTRUCTED: the last test steps the row-12 board one square off the Alchemist's door
(the key the fixed row-12 decision sends) to read the next decision.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import dataclasses
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import Position
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import MIN_TERMINAL_FREE_PACK_SLOTS, PACK_CAPACITY
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-overflow-no-disposal-1128"
STOP_ROW = 12
STOP = ("7", "town:blocked:overflow-no-legal-disposal")
UNRESERVED = "d"  # 全復活のキノコ (TVAL_FOOD, SV_FOOD_RESTORING 19)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class OverflowNoDisposal545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.stop = (journal[STOP_ROW]["key"], journal[STOP_ROW]["reason"])
        cls.replayed = []
        for recorded, supply in steps[:STOP_ROW]:
            cls.replayed.append((decide(policy, supply()), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])
        cls.board = steps[STOP_ROW][1]()
        cls.checkpoint = checkpoint_bytes(policy)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        self.assertEqual(self.stop, STOP)
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def test_no_carried_stack_is_a_legal_disposal(self):
        policy, board = self.policy, self.board
        self.assertEqual(PACK_CAPACITY - len(board.inventory), 2)
        self.assertLess(PACK_CAPACITY - len(board.inventory), MIN_TERMINAL_FREE_PACK_SLOTS)
        self.assertTrue(policy._home_available(board))
        self.assertFalse(policy._home_is_full(board))
        # A stack is destroyed or deposited whole to free its slot; 18 stacks are wholly reserved
        # and two hold one past their reservation (エルフの行糧 4 of 3, 致命傷の治癒の薬 11 of 10).
        reserved = [item.slot for item in board.inventory
                    if not policy._entire_stack_is_surplus(board, item)]
        self.assertEqual(len(reserved), 20)
        self.assertTrue(all(policy._retention_reservation(board, item) > 0
                            for item in board.inventory if item.slot in reserved))
        self.assertNotIn(UNRESERVED, reserved)
        mushroom = next(item for item in board.inventory if item.slot == UNRESERVED)
        self.assertEqual((mushroom.tval, mushroom.sval), (80, 19))
        self.assertIsNone(policy._overflow_disposal_item(board))
        self.assertIsNone(policy._find_home_deposit(board))
        self.assertIsNone(policy._find_town_organization_surplus(board))
        self.assertIsNone(policy._find_worthless_junk(board))
        # Even the one unreserved stack gone, the pack stays below the floor.
        self.assertLess(PACK_CAPACITY - (len(board.inventory) - 1), MIN_TERMINAL_FREE_PACK_SLOTS)

    def test_the_overflow_owner_gives_way(self):
        policy, board = self.policy, self.board
        self.assertIsNone(policy._town_overflow_destroy_key(board, try_relief=True))
        self.assertIsNone(policy._town_blocked_reason)

    def test_the_stop_board_goes_on_to_the_town_end(self):
        policy, board = self.policy, self.board
        key, reason = decide(policy, board)
        self.assertNotEqual((key, reason), STOP)
        self.assertNotIn("blocked", reason)
        self.assertEqual(reason, "town:entrance-step-off:town:end-step-off")
        self.assertIsNone(policy._town_blocked_reason)

    def test_off_the_door_the_visit_departs_with_the_pack_as_it_is(self):
        # DECLARED CONSTRUCTED: the row-12 board one square up-left (the step-off key '7').
        policy, board = self.policy, self.board
        key, _reason = decide(policy, board)
        self.assertEqual(key, "7")
        post(policy, key)
        here = board.player.position
        off = dataclasses.replace(board, turn=board.turn + 10, player=dataclasses.replace(
            board.player, position=Position(y=here.y - 1, x=here.x - 1)))
        self.assertEqual(off.grid_at(off.player.position).store_number, -1)
        key, reason = decide(policy, off)
        self.assertEqual(reason, "town:repetition-depart:recall")
        self.assertTrue(key.startswith("r"), key)


if __name__ == "__main__":
    unittest.main()
