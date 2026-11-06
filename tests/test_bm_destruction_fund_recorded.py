"""The Black Market's Staff of *Destruction* (owner 2026-11-07).

「BMの買い物優先度について。*破壊*の杖の優先度を上げる。」  Asked when it buys:
「何本でも買う」.

Substrate: home-room-n1b (n1-b Lv40 2026-11-04 21:47, tests/extract_spare_gear_fixtures.py),
replayed through the public chooser.  Row 22 is that visit's own Black Market page
(it bought six Potions of Speed with 41,033 gold).

DECLARED CONSTRUCTED: no recorded Black Market page shelves the staff (the game's
fixed articles-on-sale table never lists it), so the pins put one on the recorded
page in place of the ware at letter X, at a stated price.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace

from hengbot import item_fate
from hengbot.model import SV_STAFF_DESTRUCTION, TVAL_STAFF
from tests import test_input_executor as _test_input_executor
from tests.test_spare_gear_recorded import Visit

SWEEP_SPENT_ROW = 9
BLACK_MARKET_ROW = 22
STAFF_LETTER = "X"


def with_staff(board, price):
    """The recorded page with a Staff of *Destruction* (5 charges) at letter X."""
    wares = [replace(ware, name="*破壊*の杖 (5回分)", tval=TVAL_STAFF,
                     sval=SV_STAFF_DESTRUCTION, count=1, price=price,
                     charges=5, pval=5)
             if ware.letter == STAFF_LETTER else ware
             for ware in board.store.items]
    return replace(board, store=replace(board.store, items=wares))


def carrying_staff(board):
    """DECLARED CONSTRUCTED: one Staff of *Destruction* already in the pack."""
    template = next(item for item in board.inventory if item.slot == "p")
    staff = replace(template, slot="s", name="*破壊*の杖 (5回分)",
                    sval=SV_STAFF_DESTRUCTION, charges=5, pval=5, count=1)
    return replace(board, inventory=[*board.inventory, staff])


class BlackMarketDestructionRecordedTest(_test_input_executor.ProductionHarness):
    def visit(self, rows):
        visit = Visit("home-room-n1b", True)
        self.addCleanup(visit.close)
        for index, (recorded, supply) in enumerate(visit.rows[:rows]):
            if index == SWEEP_SPENT_ROW:
                # DECLARED WALL: the rank 21+ sweep (owner 11-04) was added after
                # this recording and walks Home from row 9; spent for the stay
                # here, the recorded rows replay as they were decided.
                visit.policy._home_junk_sweep_count = (
                    visit.policy._town_visit_epoch, item_fate.SWEEP_LIMIT_PER_STAY)
            board = supply()
            key = visit.policy.choose_key(board)
            self.assertEqual((key, visit.policy.last_reason), (recorded["key"], recorded["reason"]))
            visit.post(key)
        return visit

    # -- the purchase: the top of the Black Market's optional picks ----------

    def test_the_staff_is_bought_above_the_potions_with_one_already_carried(self):
        visit = self.visit(BLACK_MARKET_ROW)
        policy = visit.policy
        recorded, supply = visit.rows[BLACK_MARKET_ROW]
        # Recorded: six Potions of Speed, the optional pick of this shelf.
        self.assertEqual((recorded["key"], recorded["reason"]), ("ps6\r\r", "shop:in-store-buy"))
        board = carrying_staff(with_staff(supply(), 15000))
        self.assertEqual(policy._total_destruction_uses(board), 5)
        self.assertEqual((policy.choose_key(board), policy.last_reason), ("pX\r", "shop:in-store-buy"))
        staff = next(ware for ware in board.store.items if ware.letter == STAFF_LETTER)
        self.assertEqual(policy._matching_live_purchase_rungs(board, staff)[0].rung_id,
                         "black-market:destruction")


if __name__ == "__main__":
    unittest.main()
