"""n1-c life-217 2026-11-19 17:16:29, town:blocked:stage-deadline:sell (bot main 4c9fb4bdc6).

Right after the restart the in-store seller offered the Staff of Detect Objects {@2} (an unused
device: sold) to the Magic shop with 'd2y' three times in one entry; each time the full store
answered 「すいませんが、店にはもう置く場所がありません。」 (store/sell-order.cpp store_sell:
store_check_num finds no free slot) and the tail's 'y' 「そのコマンドは店の中では使えません。」.
After a Home trip the town walked back to the same full Magic shop to sell it again, and the sell
stage's deadline stopped the visit.  The full-store mark of the cap tidy fix (home_cap.
note_store_full) was set only from the transport's report and read only by the Home relief.

Now the refusal on the store page itself marks the store full for the visit (whichever seller
asked, whatever the transport reported), and every seller honours it: no sale candidate on its
page (``_current_store_sale_candidates``: the in-store selection and the batch seller), no
sale branch of the page's shop answer, no sale stop for it in the town plan
(``SALE_NEED_CATEGORIES``), and a ware every store of its kind refused goes to the Black Market,
which buys every kind (store/service-checker.cpp switch_store_check's default).

Recorded: the stop's town-arrival checkpoint and all 23 journal rows
(tests/extract_n1c_217_store_full_all_sales_1119_fixture.py), the in-store path on as the live
bot ran (--in-store-shop-ops).  Rows 0-3 are decided through the public choose_key and compared
with the record; the replay leaves the record at row 4 (the live bot entered the Magic shop, the
replay walks first; on main 4c9fb4bdc6 alike), so rows 5-7 are the recorded store pages read as
boards: row 5 the first page, row 6 the page after the first refusal, row 7 the next.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.cli import _configure_in_store_shop_ops
from hengbot.model import STORE_BLACK, STORE_FULL_SALE_MESSAGES, STORE_MAGIC
from hengbot.policy_town import SALE_NEED_CATEGORIES
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-store-full-all-sales-1119"
OUTSIDE_ROW, PAGE_ROW, REFUSAL_ROW, NEXT_PAGE_ROW, STOP_ROW = 4, 5, 6, 7, 22


class N1c217StoreFullAllSales1119RecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        scratch = Path(self.scratch.name)
        self.policy, self.journal, steps = load(FIXTURE, scratch)
        with contextlib.redirect_stderr(io.StringIO()):
            _configure_in_store_shop_ops(self.policy, SimpleNamespace(
                in_store_shop_ops=True, decision_log=scratch / "bot-decisions.jsonl"))
        self.boards = {}
        for row, (recorded, supply) in enumerate(steps[:NEXT_PAGE_ROW + 1]):
            self.boards[row] = supply()
            if row < OUTSIDE_ROW:
                before = copy.copy(self.policy._store_visit)
                key = self.policy.choose_key(self.boards[row])
                self.assertEqual((key, self.policy.last_reason),
                                 (recorded["key"], recorded["reason"]), row)
                post(self.policy, self.boards[row], recorded["key"], before)
        page = self.boards[PAGE_ROW]
        self.staff = next(item for item in page.inventory if "@2" in item.name)

    def tearDown(self):
        self.scratch.cleanup()

    def refused(self):
        """The policy reads the page that shows the first refusal."""
        self.policy.choose_key(self.boards[REFUSAL_ROW])

    def test_the_recorded_visit(self):
        self.assertEqual(self.journal[STOP_ROW]["reason"], "town:blocked:stage-deadline:sell")
        self.assertEqual(self.boards[PAGE_ROW].store.store_type, STORE_MAGIC)
        self.assertTrue(set(self.boards[REFUSAL_ROW].messages) & STORE_FULL_SALE_MESSAGES)
        self.assertEqual([self.journal[row]["key"] for row in range(5, 9)], ["d2y"] * 4)

    def test_before_the_refusal_the_staff_is_offered(self):
        policy, page = self.policy, self.boards[PAGE_ROW]
        self.assertEqual(policy._in_store_selection(page)["would_key"], "d2y")

    def test_the_refusal_on_the_page_marks_the_store_full(self):
        self.refused()
        self.assertTrue(self.policy.store_full(STORE_MAGIC))

    def test_a_full_store_is_offered_no_sale_again(self):
        policy = self.policy
        self.refused()
        page = self.boards[NEXT_PAGE_ROW]
        self.assertEqual(policy._current_store_sale_candidates(page), [])
        selection = policy._in_store_selection(page)
        self.assertNotIn((selection or {}).get("op"), ("sell", "inscribe"))
        key = policy.choose_key(page)
        self.assertNotEqual(key, "d2y")
        self.assertFalse(policy.last_reason.startswith(("shop:in-store-sell", "shop:sell-")),
                         policy.last_reason)

    def test_the_town_plan_never_walks_to_it_to_sell(self):
        policy = self.policy
        self.refused()
        outside = self.boards[OUTSIDE_ROW]
        self.assertFalse([need for need in policy._town_need_candidates(outside)
                          if need.store_type == STORE_MAGIC
                          and need.category in SALE_NEED_CATEGORIES])

    def test_the_staff_goes_to_the_black_market(self):
        policy = self.policy
        outside = self.boards[OUTSIDE_ROW]
        self.assertEqual(policy._town_organization_sale_store(outside, self.staff), STORE_MAGIC)
        self.refused()
        self.assertEqual(policy._town_organization_sale_store(outside, self.staff), STORE_BLACK)


if __name__ == "__main__":
    unittest.main()
