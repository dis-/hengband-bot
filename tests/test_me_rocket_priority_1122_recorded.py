"""A Magic-Eater buys every Wand of Rockets first, selling Home's spares for it, up to 50 absorbed.

Owner 2026-11-22 (verbatim): 「魔道具術師の場合、ロケットの魔法棒の購入優先度を最優先に。破壊の杖同様
売ってでも買う。」; how many: 「*破壊* と同じく取り込み50回まで」 (bm_destruction_fund's rocket row
of PRIORITY_WARES).

Recorded: n1-b life-413's town visit of 2026-11-21 23:06:50 (Lv31 Magic-Eater, no Rocket
absorbed; tests/fixtures/n1b-413-magic-shop-1121, shared with
test_speed_staff_first_1121_recorded).  Row 13 is the Black Market's page (52 rows, 6,625 gold,
a current Home census with spare melee weapons and body armour); live it bought ``px`` (the
Wand of Stone to Mud).  Rows before it are replayed as that test does.

DECLARED CONSTRUCTED: row 13's board with a Wand of Rockets shelved in place of the page's
サンダー・ボールの魔法棒 row (letter z: sval 29, 5 charges, 40,000 gold), with 200,000 gold (the
purchase) or the recorded 6,625 (the Home fund); the same with 50 and 51 Rockets absorbed (the
absorption record), with a Wand of Rockets already carried, and as a class other than the
Magic-Eater.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import bm_destruction_fund, item_fate, me_capability
from hengbot.model import STORE_BLACK, TVAL_WAND
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-magic-shop-1121"
PAGE_ROW = 13
PRICE = 40000
GOLD = 200000
ROCKETS = bm_destruction_fund.SV_WAND_ROCKETS
RUNG = "priority-ware:rocket"
# sv-wand-types.h SV_WAND_ELEC_BALL: the page's row replaced by the Wand of Rockets.
SV_WAND_ELEC_BALL = 21


class RocketPriorityRecordedTest(unittest.TestCase):
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

    def shelved(self, gold=GOLD, inventory=None, **player):
        """DECLARED CONSTRUCTED (module docstring): the page with a Wand of Rockets."""
        store = self.page.store
        ball = next(item for item in store.items
                    if item.tval == TVAL_WAND and item.sval == SV_WAND_ELEC_BALL)
        rocket = replace(ball, sval=ROCKETS, name="ロケットの魔法棒 (5回分)",
                         charges=5, pval=5, price=PRICE)
        items = tuple(rocket if item is ball else item for item in store.items)
        return replace(self.page, store=replace(store, items=items),
                       inventory=self.page.inventory if inventory is None else inventory,
                       player=replace(self.page.player, gold=gold, **player))

    def absorbed(self, count):
        me_capability.recorded(self.policy)[me_capability.record_key("wand", ROCKETS)] = count

    def purchase(self, board):
        """The page's purchase: the board observed by the chooser, then the shop's selector."""
        with contextlib.redirect_stdout(io.StringIO()):
            self.policy.choose_key(board)
            return self.policy._next_purchase(board)

    def rocket(self, board):
        return next(item for item in board.store.items
                    if item.tval == TVAL_WAND and item.sval == ROCKETS)

    def test_the_recorded_page(self):
        self.assertEqual(self.page.store.store_type, STORE_BLACK)
        self.assertEqual(self.recorded["key"], "px\r")
        self.assertEqual(self.page.player.gold, 6625)
        self.assertTrue(bm_destruction_fund.rocket_wanted(self.policy, self.page))

    def test_the_wand_of_rockets_is_bought_before_every_other_ware(self):
        board = self.shelved()
        ware = self.purchase(board)
        self.assertIsNotNone(ware)
        self.assertEqual((ware.letter, ware.tval, ware.sval),
                         (self.rocket(board).letter, TVAL_WAND, ROCKETS))
        self.assertEqual(self.policy._bm_destruction_shelf["ware"], "rocket")
        matches = self.policy._matching_live_purchase_rungs(board, ware)
        self.assertIn(RUNG, [match.rung_id for match in matches])

    def test_a_carried_wand_of_rockets_does_not_stop_the_next(self):
        # 「破壊の杖同様」: any number, a carried copy included.
        template = self.page.inventory[0]
        carried = replace(template, tval=TVAL_WAND, sval=ROCKETS, name="ロケットの魔法棒 (5回分)",
                          count=1, charges=5, pval=5, aware=True, known=True,
                          slot=chr(ord("a") + len(self.page.inventory)))
        board = self.shelved(inventory=(*self.page.inventory, carried))
        ware = self.purchase(board)
        self.assertIsNotNone(ware)
        self.assertEqual((ware.tval, ware.sval), (TVAL_WAND, ROCKETS))

    def test_short_gold_sells_home_spares_and_buys_nothing_else(self):
        # 「売ってでも買う」: the recorded 6,625 gold, 40,000 short of the wand and the reserve.
        board = self.shelved(gold=self.page.player.gold)
        ware = self.purchase(board)
        self.assertIsNone(ware)  # live: the Wand of Stone to Mud (x)
        self.assertEqual(self.policy._bm_destruction_shelf["ware"], "rocket")
        self.assertTrue(self.policy._bm_destruction_shelf["withheld"])
        self.assertTrue(bm_destruction_fund.staff_pending(self.policy, board))
        plan = bm_destruction_fund.plan(self.policy, board)
        self.assertTrue(plan)
        self.assertEqual({item_fate.SLOT_BY_TVAL[signature[1]] for signature in plan}
                         - bm_destruction_fund.FUND_SLOTS, set())
        self.assertFalse(self.policy._town_departure_conjuncts(
            board, commit=False)["destruction_staff_settled"])

    def test_fifty_absorbed_still_buy_first(self):
        self.absorbed(bm_destruction_fund.ME_ROCKET_COUNT_LIMIT)
        board = self.shelved()
        self.assertTrue(bm_destruction_fund.rocket_wanted(self.policy, board))
        ware = self.purchase(board)
        self.assertEqual((ware.tval, ware.sval), (TVAL_WAND, ROCKETS))

    def test_above_fifty_absorbed_the_wand_is_no_priority(self):
        self.absorbed(bm_destruction_fund.ME_ROCKET_COUNT_LIMIT + 1)
        board = self.shelved(gold=self.page.player.gold)
        self.assertFalse(bm_destruction_fund.rocket_wanted(self.policy, board))
        self.purchase(board)
        shelf = getattr(self.policy, "_bm_destruction_shelf", None)
        self.assertNotEqual((shelf or {}).get("ware"), "rocket")
        self.assertEqual(bm_destruction_fund.plan(self.policy, board), ())

    def test_only_a_magic_eater(self):
        board = self.shelved(class_id=0)
        self.assertFalse(bm_destruction_fund.rocket_wanted(self.policy, board))


if __name__ == "__main__":
    unittest.main()
