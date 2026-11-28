"""The rogue recharges its Staves of *Destruction* at Morivant's Tower and takes no empty staff for a
use (owner 2026-11-28 「盗賊が破壊の杖をチャージして使い回せるようにして」, n1-a life-545).

Two recorded town arrivals of n1-a life-545 (Amberite Rogue CL40, Sorcery; the staff at 95% with
the worn device skill):

``n1a-545-destruction-recharge-1128`` (tests/extract_n1a_545_destruction_recharge_1128_fixture.py):
the Outpost arrival of 2026-11-28 15:12:56 (turn 7780622, gold 40344, no staff carried; the Home
holds 25 empty staves), 103 rows.  Row 31 left the Black Market to sell the Home's spares for its
4-charge staff (bm_destruction_fund, bought on row 59 for 77196 gold); row 84 took 11 EMPTY staves
out of the Home for the 11-use shortage of Angband 70F (``_home_procurement_units``: the empty
staff counted as a means, one use a staff); row 101 read the recall with 1 x 4 and 11 x 0 carried.

``n1a-545-recall-contradiction-1128`` (the fixture of test_n1a_545_recall_contradiction_1128):
the Morivant arrival of 2026-11-28 09:34 (gold 113641, 1 x 3 and 17 x 0 carried), whose row 17
zapped the Rod of Recall for Angband 65F (10 uses wanted, 3 owned).

The fix (destruction_means): an empty staff is no means and no stock (``supplies``); while a
recharge adds a wanted use and the Tower's trip is spare (wand_tower_recharge), the Home's empty
staves are taken for it, the carried ones are kept for it, the recall read goes to the Tower first,
and no staff is bought for the shortage (``recharge_covers``).

Every row is decided through the public ``choose_key`` posting the recorded key, up to the first row
the fix decides otherwise (rows before it reproduce; row 47 of the Outpost arrival does not on main
either: the Home census posted before the checkpoint is awaited past STORE_STUCK_LIMIT, listed).
DECLARED CONSTRUCTED (the Morivant trip): the player is put beside the Tower of Sorcery (the walk of
single steps from row 17 is ~60 boards), and the recharge's reply is the row-17 pack with the staves
filled to 5 (building-recharger.cpp building_recharge_all: 18 staves stack at one pval) and the gold
less morivant_tower.recharge_cost.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import bm_destruction_fund, destruction_means, morivant_tower, wand_tower_recharge
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import Position
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
OUTPOST = FIXTURES / "n1a-545-destruction-recharge-1128"
MORIVANT = FIXTURES / "n1a-545-recall-contradiction-1128"
FUND_ROW, TAKE_ROW, TAKE_DECIDE_ROW = 31, 84, 83
UNREPRODUCED = (47,)
FUND = ("~9\x1b", "home:request-knowledge-scan")
TAKE = ("5 py11\r\x1b", "home:atomic-withdraw")
READ_ROW = 17
READ = ("zna", "town:recall-to-angband")
TOWER = Position(20, 55)  # 03_Morivant.jsonc building 8 (Tower of Sorcery) on the recorded map
STEP = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
        "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        key = policy.choose_key(board)
    return key, policy.last_reason


def no_recharge():
    """Revert: no trip is planned (the rest of the fix stays)."""
    return mock.patch.object(destruction_means.Means, "recharge_planned",
                             property(lambda self: False))


def old_supplies():
    """Revert: the empty staff counts as a means again (the definition before the fix)."""
    return mock.patch.object(
        destruction_means.Means, "supplies",
        lambda self, item: (destruction_means.is_staff(item) and self.staff_reliable
                            and not self.town_absorbs(item)))


def old_retention():
    """Revert: every carried *Destruction* item is kept while the departure wants uses."""
    return mock.patch.object(destruction_means.Means, "retains",
                             lambda self, item, gate_open: gate_open)


def main_behaviour():
    """The whole fix reverted: no trip, the empty staff a means, the old retention."""
    stack = contextlib.ExitStack()
    for patch in (no_recharge(), old_supplies(), old_retention()):
        stack.enter_context(patch)
    return stack


def replay(fixture, scratch, stop, *patches):
    """(decided rows before ``stop``, the recorded rows, the ``stop`` board, its checkpoint, the
    next recorded board)."""
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        policy, journal, steps = load(fixture, scratch)
        decided = []
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row == stop:
                checkpoint = checkpoint_bytes(policy)
                return decided, journal, board, checkpoint, steps[row + 1][1]()
            decided.append(decide(policy, board))
            post(policy, recorded["key"])
    raise AssertionError(stop)


def staves(board):
    return [(item.count, item.charges) for item in board.inventory if destruction_means.is_staff(item)]


class OutpostArrival545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        root = Path(cls.scratch.name)
        (root / "fund").mkdir()
        (root / "take").mkdir()
        cls.fund_decided, cls.journal, cls.fund_board, cls.fund_checkpoint, _ = replay(
            OUTPOST, root / "fund", FUND_ROW)
        # The supplies fix alone (no trip: the recorded gold after the staff's purchase cannot
        # pay one) up to the recorded take of the empty staves.
        cls.take_decided, _, cls.take_board, cls.take_checkpoint, cls.take_next = replay(
            OUTPOST, root / "take", TAKE_DECIDE_ROW, no_recharge())

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def recorded(self, row):
        return self.journal[row]["key"], self.journal[row]["reason"]

    def test_the_replay_follows_the_record(self):
        self.assertEqual(self.recorded(FUND_ROW), FUND)
        self.assertEqual(self.recorded(TAKE_ROW), TAKE)
        self.assertEqual([row for row, decided in enumerate(self.fund_decided)
                          if decided != self.recorded(row)], [])
        self.assertEqual([row for row, decided in enumerate(self.take_decided)
                          if decided != self.recorded(row)], list(UNREPRODUCED))

    def test_the_black_market_staff_is_not_funded_while_the_recharge_covers(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.fund_checkpoint)
        board = self.fund_board
        means = destruction_means.Means(policy, board)
        # Mountain 46F (short of 50F): the staff carried whatever the depth, 5 uses; none owned.
        self.assertEqual((means.wanted_uses, means.owned_staff_charges, means.recharge_short),
                         (5, 0, 5))
        stack = means.home_recharge_stack
        self.assertEqual((stack.count, stack.charges), (25, 0))
        self.assertEqual(means.home_recharge_take(stack), 1)
        self.assertTrue(means.recharge_planned)
        self.assertTrue(means.recharge_covers())
        self.assertFalse(bm_destruction_fund.staff_wanted(policy, board))
        key, reason = decide(policy, board)
        self.assertTrue(key, reason)
        self.assertNotEqual((key, reason), FUND)
        self.assertIsNone(bm_destruction_fund._shelf(policy, board))
        self.assertFalse(reason.startswith("town:blocked"), reason)

    def test_revert_the_recharge_funds_the_staff_as_recorded(self):
        # The replay with no trip planned (setUpClass) decided the recorded fund on the same row.
        self.assertEqual(self.take_decided[FUND_ROW], FUND)

    def test_no_empty_staff_is_taken_without_the_trip(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.take_checkpoint)
        board = self.take_board
        self.assertEqual(staves(board), [(1, 4)])
        stack = next(item for item in policy._home_knowledge_items
                     if destruction_means.is_staff(item) and item.charges == 0)
        self.assertEqual(stack.count, 25)
        with no_recharge():
            self.assertFalse(policy._supplies_destruction(board, stack))
            self.assertEqual(policy._procurement_missing_amount(board, stack), 0)
            key, reason = decide(policy, board)
        self.assertNotEqual((key, reason), self.recorded(TAKE_DECIDE_ROW))
        self.assertFalse(reason.startswith("town:blocked"), reason)

    def test_revert_the_empty_staff_means_takes_eleven(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.take_checkpoint)
        with no_recharge(), old_supplies():
            self.assertEqual(decide(policy, self.take_board), self.recorded(TAKE_DECIDE_ROW))
            post(policy, self.recorded(TAKE_DECIDE_ROW)[0])
            self.assertEqual(decide(policy, self.take_next), TAKE)


class MorivantArrival545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        root = Path(cls.scratch.name)
        (root / "fix").mkdir()
        (root / "revert").mkdir()
        cls.decided, cls.journal, cls.read_board, cls.read_checkpoint, _ = replay(
            MORIVANT, root / "fix", READ_ROW)
        cls.revert_decided, _, revert_board, revert_checkpoint, _ = replay(
            MORIVANT, root / "revert", READ_ROW, main_behaviour())
        with main_behaviour():
            cls.revert_read = decide(restore_checkpoint_bytes(HengbotPolicy, revert_checkpoint),
                                     revert_board)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def restored(self):
        return restore_checkpoint_bytes(HengbotPolicy, self.read_checkpoint)

    def test_the_read_goes_to_the_tower(self):
        self.assertEqual((self.journal[READ_ROW]["key"], self.journal[READ_ROW]["reason"]), READ)
        policy, board = self.restored(), self.read_board
        self.assertEqual(policy._effective_town_id(board), wand_tower_recharge.MORIVANT_TOWN_ID)
        self.assertEqual(staves(board), [(1, 3), (17, 0)])
        means = destruction_means.Means(policy, board)
        # Angband 65F: 10 uses (required_destruction_uses), 3 owned; the carried staves add 87.
        self.assertEqual((means.wanted_uses, means.owned_staff_charges, means.recharge_short,
                          means.carried_refill), (10, 3, 7, 87))
        self.assertTrue(means.recharge_planned)
        key, reason = decide(policy, board)
        self.assertTrue(key)
        self.assertEqual(reason, wand_tower_recharge.APPROACH_REASON)

    def test_the_replay_follows_the_record_to_the_read(self):
        recorded = [(row["key"], row["reason"]) for row in self.journal[:READ_ROW]]
        # Row 5: the periodic character dump (test_n1a_545_recall_contradiction_1128 UNREPRODUCED).
        self.assertEqual([row for row, decided in enumerate(self.decided)
                          if decided != recorded[row]], [5])
        self.assertEqual([row for row, decided in enumerate(self.revert_decided)
                          if decided != recorded[row]], [5])

    def test_revert_the_fix_reads_the_recall_as_recorded(self):
        self.assertEqual(self.revert_read, READ)

    def test_the_tower_recharges_the_staves_and_the_visit_goes_on(self):
        policy, board = self.restored(), self.read_board
        key, reason = decide(policy, board)
        self.assertEqual(reason, wand_tower_recharge.APPROACH_REASON)
        post(policy, key)
        beside = policy._walkable_neighbors(board, TOWER)[0]
        board = replace(board, player=replace(board.player, position=beside), turn=board.turn + 10)
        key, reason = decide(policy, board)
        self.assertEqual(reason, wand_tower_recharge.RECHARGE_REASON)
        self.assertTrue(key.endswith(morivant_tower.RECHARGE_ALL_TAIL), key)
        self.assertEqual(policy._step_toward(board, TOWER), key[0])
        post(policy, key)
        # The recharge's reply (module docstring): 18 staves of 5, the gold less the price.
        cost = morivant_tower.recharge_cost(board)
        self.assertEqual(cost, 17 * 5 * 750 + 2 * 750)
        held = [item for item in board.inventory if destruction_means.is_staff(item)]
        filled = replace(held[-1], count=18, charges=5, pval=5)
        board = replace(board, inventory=tuple(
            [item for item in board.inventory if not destruction_means.is_staff(item)] + [filled]),
            player=replace(board.player, gold=board.player.gold - cost, position=TOWER),
            turn=board.turn + 20)
        means = destruction_means.Means(policy, board)
        self.assertEqual((means.owned_staff_charges, means.recharge_short), (90, 0))
        self.assertFalse(means.recharge_planned)
        reasons = []
        for _ in range(4):
            key, reason = decide(policy, board)
            reasons.append(reason)
            self.assertFalse(reason.startswith("town:blocked"), reasons)
            self.assertFalse(reason.startswith(wand_tower_recharge.REASON), reasons)
            if not key:
                break
            post(policy, key)
            if key[0] in STEP:
                dy, dx = STEP[key[0]]
                here = board.player.position
                board = replace(board, player=replace(
                    board.player, position=Position(here.y + dy, here.x + dx)),
                    turn=board.turn + 10)
        self.assertTrue(reasons[0], reasons)
        # The recall read's errand finds nothing left to fill and gives the read back.
        self.assertIsNone(wand_tower_recharge.town_key(policy, board))
        self.assertTrue(wand_tower_recharge.state(policy).recharged)


if __name__ == "__main__":
    unittest.main()
