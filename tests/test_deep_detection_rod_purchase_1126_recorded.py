"""A 50F+ character buys a shelved Rod of Detection first, from the gold it can spare.

Owner 2026-11-26 (verbatim): 「50F以降は全感知のロッドを持つ」 (bm_destruction_fund's detection-rod
row of PRIORITY_WARES, deep_detection_rod).  The owner did not say 「売ってでも」: no Home spare is
sold for it.

Recorded: n1-b life-413's town visit of 2026-11-21 23:06:50 (tests/fixtures/n1b-413-magic-shop-1121,
shared with test_me_rocket_priority_1122_recorded).  Row 13 is the Black Market's page (52 rows,
6,625 gold, a current Home census with spare melee weapons and body armour); live it bought ``px``
(the Wand of Stone to Mud).  Rows before it are replayed as that test does.

DECLARED CONSTRUCTED: row 13's board with a Rod of Detection shelved in place of the page's
サンダー・ボールの魔法棒 row (tval 66, sval 6, 30,000 gold), the deepest recall depth 50 (the
recorded one is shallower), with 200,000 gold (the purchase) or the recorded 6,625 (no fund); the
same with a recall depth of 49, with a Rod of Detection carried, at Home, or absorbed (the
absorption record), and a Home Rod of Detection with none carried (the Home withdrawal); the
retention read as a warrior (class 0) as well.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import bm_destruction_fund, deep_detection_rod, me_capability
from hengbot.model import STORE_BLACK, SV_ROD_DETECTION, TVAL_ROD, TVAL_WAND
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-magic-shop-1121"
PAGE_ROW = 13
PRICE = 30000
GOLD = 200000
RUNG = "priority-ware:detection-rod"
# sv-wand-types.h SV_WAND_ELEC_BALL: the page's row replaced by the Rod of Detection.
SV_WAND_ELEC_BALL = 21


class DetectionRodPurchaseRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        policy, _journal, steps = load(FIXTURE, Path(self.scratch.name))
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        for recorded, supply in steps[:PAGE_ROW]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(board)
            if recorded["key"]:
                policy.confirm_key_posted(recorded["key"])
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, recorded["key"]):
                    policy.commit_staged_prompt_chain(
                        {"outcome": "released", "posted": recorded["key"]})
        self.recorded, supply = steps[PAGE_ROW]
        self.page = supply()
        self.policy = policy

    def rod_item(self, template, **fields):
        return replace(template, tval=TVAL_ROD, sval=SV_ROD_DETECTION, name="全感知のロッド",
                       charges=0, pval=99, aware=True, known=True, **fields)

    def shelved(self, gold=GOLD, depth=50, inventory=None):
        """DECLARED CONSTRUCTED (module docstring): the page with a Rod of Detection."""
        store = self.page.store
        ball = next(item for item in store.items
                    if item.tval == TVAL_WAND and item.sval == SV_WAND_ELEC_BALL)
        rod = self.rod_item(ball, price=PRICE)
        items = tuple(rod if item is ball else item for item in store.items)
        return replace(self.page, store=replace(store, items=items),
                       dungeon_recall_depths={1: depth}, recall_depth=depth,
                       inventory=self.page.inventory if inventory is None else inventory,
                       player=replace(self.page.player, gold=gold))

    def carried_rod(self):
        template = self.page.inventory[0]
        return self.rod_item(template, count=1, charging=False, charging_count=0,
                             slot=chr(ord("a") + len(self.page.inventory)))

    def purchase(self, board):
        with contextlib.redirect_stdout(io.StringIO()):
            self.policy.choose_key(board)
            return self.policy._next_purchase(board)

    def test_the_recorded_page(self):
        self.assertEqual(self.page.store.store_type, STORE_BLACK)
        self.assertEqual(self.recorded["key"], "px\r")
        self.assertEqual(self.page.player.gold, 6625)

    def test_the_rod_is_bought_before_every_other_ware(self):
        board = self.shelved()
        self.assertTrue(deep_detection_rod.purchase_wanted(self.policy, board))
        ware = self.purchase(board)
        self.assertIsNotNone(ware)
        self.assertEqual((ware.tval, ware.sval), (TVAL_ROD, SV_ROD_DETECTION))
        self.assertEqual(self.policy._bm_destruction_shelf["ware"], "detection-rod")
        matches = self.policy._matching_live_purchase_rungs(board, ware)
        self.assertIn(RUNG, [match.rung_id for match in matches])

    def test_short_gold_sells_nothing_for_it(self):
        # Not 「売ってでも」: the recorded 6,625 gold leaves the page's own order.
        board = self.shelved(gold=self.page.player.gold)
        ware = self.purchase(board)
        self.assertFalse(ware is not None and (ware.tval, ware.sval) == (TVAL_ROD, SV_ROD_DETECTION))
        shelf = getattr(self.policy, "_bm_destruction_shelf", None)
        self.assertNotEqual((shelf or {}).get("ware"), "detection-rod")
        self.assertEqual(bm_destruction_fund.plan(self.policy, board), ())
        self.assertFalse(bm_destruction_fund.staff_pending(self.policy, board))

    def test_above_50f_the_rod_is_no_priority(self):
        board = self.shelved(depth=49)
        self.assertFalse(deep_detection_rod.purchase_wanted(self.policy, board))
        ware = self.purchase(board)
        self.assertFalse(ware is not None and (ware.tval, ware.sval) == (TVAL_ROD, SV_ROD_DETECTION))

    def test_an_owned_rod_is_not_bought_again(self):
        carried = self.shelved(inventory=(*self.page.inventory, self.carried_rod()))
        self.assertFalse(deep_detection_rod.purchase_wanted(self.policy, carried))
        self.policy._home_knowledge_items = (*self.policy._home_knowledge_items, self.carried_rod())
        self.assertFalse(deep_detection_rod.purchase_wanted(self.policy, self.shelved()))

    def test_an_absorbed_rod_is_owned(self):
        me_capability.recorded(self.policy)[me_capability.record_key("rod", SV_ROD_DETECTION)] = 1
        self.assertFalse(deep_detection_rod.purchase_wanted(self.policy, self.shelved()))

    def test_a_home_rod_is_taken_out_and_a_carried_one_kept(self):
        board = self.shelved()
        home_rod = self.carried_rod()
        self.policy._home_knowledge_items = (*self.policy._home_knowledge_items, home_rod)
        self.assertEqual(self.policy._procurement_missing_amount(board, home_rod), 1)
        self.assertTrue(self.policy._home_procurement_batch_member(board, home_rod))
        carried = self.shelved(inventory=(*self.page.inventory, self.carried_rod()))
        self.assertEqual(self.policy._procurement_missing_amount(carried, home_rod), 0)
        kept = deep_detection_rod.carried(carried)
        # The Magic-Eater absorbs it in town (me-device:absorb-in-town keeps it meanwhile);
        # another class keeps it under the rod's own branch.
        self.assertEqual(self.policy._retention_reservation_detail(carried, kept)[0], 1)
        warrior = replace(carried, player=replace(carried.player, class_id=0))
        self.assertEqual(self.policy._retention_reservation_detail(warrior, kept),
                         (1, deep_detection_rod.RETENTION_BRANCH))

    def test_without_the_row_the_page_buys_something_else(self):
        # Revert proof: the table without its detection-rod row.
        rows = tuple(entry for entry in bm_destruction_fund.PRIORITY_WARES
                     if entry.label != "detection-rod")
        with mock.patch.object(bm_destruction_fund, "PRIORITY_WARES", rows):
            ware = self.purchase(self.shelved())
        self.assertFalse(ware is not None and (ware.tval, ware.sval) == (TVAL_ROD, SV_ROD_DETECTION))


if __name__ == "__main__":
    unittest.main()
