"""The Home's cap of 200 stacks and its tidy, Home root fix stage 2 (owner 2026-11-19
「自宅の満杯問題で問題を起こしすぎなので根本解決すること」, PROPOSAL
C:\\hengband-backups\\pdca\\home-full-root-1119 3-2 and 3-6).

The owner's answers: 「200件（空き40）」 (the Home keeps at most 200 stacks, 40 free for
deposits), 「安い順に売ってよい」 (past the sellable stock, ranks 11-20 cheapest first; the top
ten stay), 「一気に片づける」 (down to the cap in one visit), 「上限を置かない」 (supplies' spares
are not sold for the cap).

n1-a life-531 came home on 2026-11-19 02:21:47 with 239 stacks at Home and 12 in the pack.  The
recorded visit never touched the shelf (row 3 deposited into the 239 Home).  Now the cap tidy
begins on the first board it may (row 2): 39 stacks over the cap, taken in batches while the
pack keeps its reserve, the last on the shelf first so no census is needed between takes, the
batch then sold one ware after another, and the tidy ends at the cap.

Recorded: n1-a life-531's town-arrival checkpoint and its first journal rows
(tests/extract_n1a_531_home_cap_1119_fixture.py).  Rows 0-1 are decided through the public
choose_key and compared with the record.

DECLARED CONSTRUCTED: the boards after row 2 -- the player at the Home entrance (row 3's cell),
each taken ware added to the pack (the game's take), each sold ware removed (the store's sale).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from unittest.mock import patch
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import home_cap, home_ledger, item_fate, town_pack_budget
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-home-cap-1119"
CAP_ROW = 2
ENTRANCE_ROW = 3
TVAL_POTION, TVAL_SCROLL = 75, 70

# Recorded under the 11-19 top-ten keep (item_fate.KEPT_RANKS 10).  The owner's 2026-11-21 top
# five (「部位ごとに残す数を5位までに減らす」) changes which wares go, not the mechanics pinned here;
# tests/test_n1b_411_home_keep_top5_1121_recorded.py pins the top five.
_TOP_TEN = patch.object(item_fate, "KEPT_RANKS", 10)


def setUpModule():
    _TOP_TEN.start()


def tearDownModule():
    _TOP_TEN.stop()



class HomeCapTidyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        boards = []
        for row, (recorded, supply) in enumerate(steps[:ENTRANCE_ROW + 1]):
            boards.append(supply())
            if row < CAP_ROW:
                before = copy.copy(policy._store_visit)
                key = policy.choose_key(boards[-1])
                cls.replayed.append(((key, policy.last_reason),
                                     (recorded["key"], recorded["reason"])))
                post(policy, boards[-1], recorded["key"], before)
        cls.arrival = boards[CAP_ROW]
        cls.outside = replace(boards[CAP_ROW], player=replace(
            boards[CAP_ROW].player, position=boards[ENTRANCE_ROW].player.position))
        cls.checkpoint = checkpoint_bytes(policy)
        # The Home's transaction history file the restored policy appends to.
        cls.history = policy._home_disposal.history_path
        cls.history_bytes = cls.history.read_bytes() if cls.history.exists() else None

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        if self.history_bytes is not None:
            self.history.write_bytes(self.history_bytes)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def decide(self, board):
        before = copy.copy(self.policy._store_visit)
        key = self.policy.choose_key(board)
        reason = self.policy.last_reason
        post(self.policy, board, key, before)
        return key, reason

    def shelf(self, signature):
        return next(item for item in self.policy._home_knowledge_items
                    if self.policy._item_signature(item) == signature)

    @staticmethod
    def taken(board, item):
        """The game's take: the stack joins the pack at the next letter."""
        letter = chr(ord("a") + len(board.inventory))
        return replace(board, inventory=(*board.inventory, replace(item, slot=letter)))

    def take_batch(self):
        """Arrive, walk to the entrance, take wares until the batch is sold; the boards."""
        policy = self.policy
        self.decide(self.arrival)
        board = self.outside
        self.decide(board)                       # store:entry-await-observation
        takes = []
        self.fates = []
        for _ in range(20):
            relief = policy._home_full_relief
            if relief is None or relief.draining:
                break
            if policy._home_atomic_withdraw_pending is None:
                self.decide(board)
                continue
            ware = self.shelf(relief.sale[0])
            self.fates.append(item_fate.fate(policy, board, ware, item_fate.SHELF))
            takes.append(ware)
            board = self.taken(board, ware)
            self.decide(board)
        return board, takes

    def test_the_arrival_home_stands_over_the_cap(self):
        policy, board = self.policy, self.arrival
        self.assertEqual(home_cap.stock_count(policy, board), 239)
        self.assertTrue(home_cap.at_cap(policy, board))
        self.assertEqual(self.journal[ENTRANCE_ROW]["reason"], "home:atomic-deposit")

    def test_the_tidy_begins_and_takes_a_ware_the_fate_sells(self):
        policy = self.policy
        key, _ = self.decide(self.arrival)
        relief = policy._home_full_relief
        self.assertTrue(relief.cap)
        self.assertEqual(relief.remaining, 239 - home_ledger.HOME_KEEP_CAP)
        self.assertEqual(relief.deposits, ())
        self.assertEqual(relief.mode, "sale")
        ware = self.shelf(relief.sale[0])
        self.assertEqual(item_fate.fate(policy, self.arrival, ware, item_fate.SHELF),
                         item_fate.SELL)
        self.assertEqual(key, self.journal[CAP_ROW]["key"])   # to the Home, as recorded
        # At the entrance the take is composed outside (entry, take, exit).
        self.decide(self.outside)
        key, reason = self.decide(self.outside)
        self.assertEqual(reason, "home-errand:atomic-withdraw:full-home-sale")
        self.assertTrue(key.startswith("5") and key.endswith("\x1b"))

    def test_the_supplies_spares_are_not_sold_for_the_cap(self):
        policy, board = self.policy, self.arrival
        spares = [item for item in policy._home_knowledge_items
                  if item.tval in (TVAL_POTION, TVAL_SCROLL)
                  and policy._home_full_sale_candidate(board, item) is not None]
        # Today's full-Home relief would sell them; the cap's fate keeps them.
        self.assertTrue(spares)
        self.assertFalse(any(home_cap.sheds(policy, board, item) for item in spares))

    def test_the_wares_are_taken_in_one_batch_without_a_census(self):
        policy = self.policy
        board, takes = self.take_batch()
        relief = policy._home_full_relief
        self.assertTrue(relief.draining)
        # Taken while another ware fit: the batch stopped at the weight limit (194.9 of
        # 195.0 lb), no ware the cap sheds can be carried more.
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1949, 1950))
        self.assertFalse(any(policy._can_add_item_without_overweight(board, item)
                             for item in policy._home_knowledge_items
                             if home_cap.sheds(policy, board, item)))
        self.assertEqual(len(takes), len(board.inventory) - len(self.arrival.inventory))
        self.assertGreater(len(takes), 1)
        self.assertEqual(relief.remaining, 239 - home_ledger.HOME_KEEP_CAP - len(takes))
        # The census of the arrival served every take: none was asked between them.
        self.assertTrue(policy._home_knowledge_current)
        # Every ware, when it was chosen, was one the fate moves.
        self.assertEqual(set(self.fates) - set(home_cap.SHED_FATES), set())

    def test_the_batch_is_sold_one_ware_after_another(self):
        policy = self.policy
        board, takes = self.take_batch()
        relief = policy._home_full_relief
        remaining = relief.remaining
        sold = []
        for _ in range(len(takes)):
            relief = policy._home_full_relief
            if relief is None or relief.sale is None:
                break
            self.assertTrue(relief.pack_only and relief.withdrawn and relief.mode == "sale")
            ware = relief.sale[0]
            sold.append(ware)
            board = replace(board, inventory=tuple(
                item for item in board.inventory if policy._item_signature(item) != ware))
            for _ in range(3):
                # The sale is settled on a board outside its store.
                self.decide(board)
                relief = policy._home_full_relief
                if relief is None or relief.sale is None or relief.sale[0] != ware:
                    break
        self.assertEqual(sold, [policy._item_signature(ware) for ware in takes])
        relief = policy._home_full_relief
        # The slots were counted at the takes: the sales count none again.
        self.assertEqual(relief.remaining, remaining)
        self.assertEqual((relief.carried, relief.draining), ((), False))
        # The next batch starts from a census of the shelf.
        self.assertFalse(policy._home_knowledge_current)

    def test_the_tidy_ends_at_the_cap(self):
        policy = self.policy
        self.decide(self.arrival)
        relief = policy._home_full_relief
        relief.remaining = 0
        relief.reset("sale", "mode")
        policy._home_errand.finish()
        policy._home_pending_item = None
        self.assertIsNone(policy._home_full_relief_key(self.arrival))
        self.assertIsNone(policy._home_full_relief)
        self.assertEqual(policy.last_reason, "home:cap-tidy-done")
        # Not again this visit.
        self.assertFalse(policy._begin_home_cap_tidy(self.arrival))

    def test_a_room_piece_brought_home_is_sold_not_shelved_at_the_cap(self):
        policy, board = self.policy, self.arrival
        room = [item for item in policy._home_knowledge_items
                if item_fate.fate(policy, board, item, item_fate.SHELF) == item_fate.ROOM_SALE]
        self.assertTrue(room)
        piece = replace(room[0], slot=chr(ord("a") + len(board.inventory)))
        carried = replace(board, inventory=(*board.inventory, piece))
        self.assertEqual(item_fate.gear_tier(policy, carried, piece), item_fate.ROOM)
        # At the cap the 11-20 piece needs room like a full Home's: it goes to its buyer
        # and is never shelved ...
        self.assertTrue(item_fate.ranked_gear_saleable(policy, carried, piece))
        self.assertTrue(item_fate.sold_not_shelved(policy, carried, piece))
        self.assertFalse(policy._home_deposit_candidate(piece, carried))
        # ... and a Home of 199 stacks takes it.
        policy._home_knowledge_items = policy._home_knowledge_items[:199]
        self.assertFalse(home_cap.at_cap(policy, carried))
        self.assertFalse(item_fate.home_at_cap(policy, carried))

    def test_only_kept_stock_left_ends_the_tidy_over_the_cap(self):
        policy, board = self.policy, self.arrival
        self.decide(board)
        relief = policy._home_full_relief
        policy._home_errand.finish()
        policy._home_pending_item = None
        relief.reset("sale", "mode")
        # Every stack the fate moves has gone (skipped as if sold): the supplies' spares and
        # the kept gear are all that is left, still over the cap.
        for item in policy._home_knowledge_items:
            if home_cap.sheds(policy, board, item):
                signature = policy._item_signature(item)
                relief.skipped[signature] = "test-sold"
                relief.skipped_home_counts[signature] = 0
        self.assertIsNone(policy._home_full_relief_key(board))
        self.assertIsNone(policy._home_full_relief)
        self.assertEqual(policy.last_reason, "home:cap-tidy-nothing-to-shed")

    def test_past_twelve_unidentified_stacks_identification_comes_first(self):
        policy, board = self.policy, self.arrival
        items = list(policy._home_knowledge_items)
        kept = [index for index, item in enumerate(items)
                if item.is_equipment and not item.is_artifact and item.known
                and item_fate.fate(policy, board, item, item_fate.SHELF) == item_fate.HOME]
        unknown = sum(1 for item in items if not item.known)
        # The carried Identify staves identify a shelf stack now.
        self.assertIsNotNone(policy._carried_identification_source(board, full=False))
        for index in kept[:home_cap.IDENTIFY_FIRST + 1 - unknown]:
            items[index] = replace(items[index], known=False)
        policy._home_knowledge_items = tuple(items)
        self.decide(board)
        relief = policy._home_full_relief
        self.assertTrue(relief.cap)
        self.assertEqual(relief.mode, "identify")
        self.assertFalse(self.shelf(relief.sale[0]).known)

    def test_twelve_unidentified_stacks_wait_for_the_sales(self):
        policy, board = self.policy, self.arrival
        items = list(policy._home_knowledge_items)
        kept = [index for index, item in enumerate(items)
                if item.is_equipment and not item.is_artifact and item.known
                and item_fate.fate(policy, board, item, item_fate.SHELF) == item_fate.HOME]
        unknown = sum(1 for item in items if not item.known)
        for index in kept[:home_cap.IDENTIFY_FIRST - unknown]:
            items[index] = replace(items[index], known=False)
        policy._home_knowledge_items = tuple(items)
        self.decide(board)
        self.assertEqual(policy._home_full_relief.mode, "sale")

    def test_a_home_seen_over_the_cap_asks_one_census(self):
        policy, board = self.policy, self.arrival
        # A census of an earlier visit, no longer current (no Home change asks for a scan).
        policy._invalidate_home_observation()
        policy._home_knowledge_invalidated = False
        self.assertIsNone(home_cap.stock_count(policy, board))
        # A deposit waiting for the Home goes first (the recorded row 3 shelves it) ...
        deposit = policy._find_home_deposit(board)
        self.assertIsNotNone(deposit)
        self.assertFalse(home_cap.census_wanted(policy, board))
        # ... without it the cap asks the census itself.
        while (deposit := policy._find_home_deposit(board)) is not None:
            board = replace(board, inventory=tuple(
                item for item in board.inventory if item.slot != deposit.slot))
        self.assertTrue(home_cap.census_wanted(policy, board))
        key, reason = self.decide(board)
        self.assertTrue(key.startswith("~9"), (key, reason))
        self.assertIsNone(policy._home_full_relief)
        # The census the cap asked for (home_cap.census_requested).
        self.assertEqual(policy._home_cap_tidy["census"], policy._town_visit_epoch, reason)
        # One census per visit.
        self.assertFalse(home_cap.census_wanted(policy, board))

    def test_no_tidy_while_the_pack_keeps_its_reserve(self):
        policy, board = self.policy, self.arrival
        filler = board.inventory[0]
        full = replace(board, inventory=(*board.inventory, *(
            replace(filler, slot=chr(ord("a") + index))
            for index in range(len(board.inventory), 23 - 4))))
        self.assertFalse(town_pack_budget.permits(full, 1))
        self.assertFalse(policy._begin_home_cap_tidy(full))
        self.assertTrue(policy._begin_home_cap_tidy(board))


if __name__ == "__main__":
    unittest.main()
