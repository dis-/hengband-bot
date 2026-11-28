"""A spare book whose inscription is a cast binding is not offered for sale, so the town does not walk
in and out of the Magic shop for it (n1-a life-545, MAINTAINABILITY.md 2-3).

Recorded (tests/extract_n1a_545_buy_deadline_1128_fixture.py, ``n1a-545-buy-deadline-1128``): the
town-arrival checkpoint of 2026-11-28 16:59:47 (Amberite Rogue, Sorcery, build b81760a38, arrival
turn 7993175), 71 rows.  The pack holds two Lv3 Sorcery books inscribed ``@mc!k`` (the cast binding
realm_spell_book keeps; one copy is retained, one is surplus) and a staff the Magic shop buys
(slot r).  Row 12 travelled to the Magic shop; on row 13, inside, the sale candidates were the book
first (``_find_book_sale``) and the staff; the batch sale composer looks at the first candidate
only and skips an item whose inscription holds an ``@`` that is not a sale tag (never overwriting
another owner's binding), so it composed nothing and left (shop:observe-and-leave /
shop:sale-inscription-unavailable-leave).  The town plan's Magic shop stop came back on every board
(25 entries), then town:blocked:stage-deadline:buy (row 70).  The same replay on 24f917dd0 (before
the 2026-11-28 *Destruction* recharge) decides the same rows: the defect is older than that change.

The fix: one answer, ``_sale_tag_bindable``, read by the sale finders (what routes the town to a
store to sell) and by the composer.  The book is no candidate; the staff is sold.

Rows 0-12 are replayed through the public ``choose_key`` posting the recorded key (they reproduce).
DECLARED CONSTRUCTED: after the row-13 inscription, the sale's reply is the row-13 page without the
staff and with the gold raised, and the outside board is row 12's at the Magic shop's entrance with
that pack.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import Position
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import STORE_MAGIC
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-buy-deadline-1128"
TRAVEL_ROW, PAGE_ROW, STOP_ROW = 12, 13, 70
LEAVE = ("\x1b", "shop:observe-and-leave")
STOP_REASON = "town:blocked:stage-deadline:buy"
MAGIC_SHOP_DOOR = Position(38, 106)
SALE_GOLD = 500


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


class BuyDeadline545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.journal = journal
        cls.decided = []
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row == TRAVEL_ROW:
                cls.outside = board
            if row == PAGE_ROW:
                cls.page, cls.checkpoint = board, checkpoint_bytes(policy)
                break
            cls.decided.append(decide(policy, board))
            post(policy, recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def recorded(self, row):
        return self.journal[row]["key"], self.journal[row]["reason"]

    def restored(self):
        return restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def book(self):
        return next(item for item in self.page.inventory if item.slot == "c")

    def test_the_replay_follows_the_record_to_the_page(self):
        self.assertEqual(self.recorded(PAGE_ROW), LEAVE)
        self.assertEqual(self.journal[STOP_ROW]["reason"], STOP_REASON)
        self.assertEqual([row for row, decided in enumerate(self.decided)
                          if decided != self.recorded(row)], [])
        self.assertEqual(self.page.store.store_type, STORE_MAGIC)

    def test_the_bound_book_is_no_sale_and_the_staff_is_sold(self):
        policy = self.restored()
        book = self.book()
        self.assertEqual((book.count, book.inscription), (2, "@mc!k"))
        self.assertGreater(policy._retention_surplus(self.page, book), 0)
        self.assertFalse(policy._sale_tag_bindable(book))
        self.assertIsNone(policy._find_book_sale(self.page))
        self.assertEqual([item.slot for item in policy._current_store_sale_candidates(self.page)],
                         ["r"])
        key, reason = decide(policy, self.page)
        self.assertEqual((key, reason), ("{r@0\r", "shop:in-store-inscribe"))

    def test_after_the_sale_the_town_goes_on_to_the_next_stop(self):
        policy = self.restored()
        key, _reason = decide(policy, self.page)
        post(policy, key)
        sold = replace(self.page, inventory=tuple(
            item for item in self.page.inventory if item.slot != "r"),
            player=replace(self.page.player, gold=self.page.player.gold + SALE_GOLD),
            turn=self.page.turn + 5)
        key, reason = decide(policy, sold)
        self.assertEqual((key, reason), ("\x1b", "shop:in-store-done"))
        post(policy, key)
        outside = replace(self.outside, inventory=sold.inventory, player=replace(
            self.outside.player, gold=sold.player.gold, position=MAGIC_SHOP_DOOR),
            turn=sold.turn + 5)
        key, reason = decide(policy, outside)
        self.assertEqual(reason, "shop:travel")
        self.assertTrue(key.startswith("\x1b`n"), key)
        self.assertNotEqual(policy._shopping_approach_store_type, STORE_MAGIC)
        self.assertFalse(reason.startswith("town:blocked"), reason)


if __name__ == "__main__":
    unittest.main()
