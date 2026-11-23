"""A Staff of Speed bought at the Black Market and sold at the Magic shop two seconds later (n1-b life-416).

Owner rules: 2026-11-13 「魔道具術師　取り込み99回になった魔法道具はそれ以降拾わない」 (a copy adds
nothing to a power at 99, mind-magic-eater.cpp import_magic_device); 2026-11-19 「使わない魔法道具は
売る」 (item_use_route: a surplus device is sold); 2026-11-21 「スピードの杖の一本目は最優先にする」
(only the first copy, bm_destruction_fund ``first_speed_staff_wanted``: untouched here).

Recorded (tests/extract_speed_staff_buysell_1124_fixture.py, ``n1b-416-speed-staff-buysell-1124``):
the town-arrival checkpoint of 23:39:18 (turn 4313051, decision 160).  The absorbed Speed staff's
count was 99.  Row 36 (decision 197, 23:39:36) bought スピードの杖 (5回分) at the Black Market for
21,292 (``pN\\r``, ``shop:in-store-buy``): the ordinary order's device-table row
(me_device_policy ``purchase_wanted``) read ``buy_more`` 「2本目以降も買う」 alone, while every
rung of the purchase table refused the ware as surplus (purchase-source.jsonl ``rungs`` [],
``rungs_unfiltered`` ["me-device:policy"]).  Row 44 (decision 205, 23:39:38) sold it at the Magic
shop for 2,764 (``d0y``): item_use_route's ``magic-eater-absorbs`` found the power at its cap.
Rows 0-35 are decided through the public ``choose_key`` (rows 5 and 7 differ in the periodic
browse's and the store entry's timing, as the recorded stream does on any replay); each row posts
the recorded key.

DECLARED CONSTRUCTED: ``test_the_ordinary_order_refuses_a_surplus_ware`` puts back the old
``purchase_wanted`` (``buy_more`` without the cap) for row 36's decision.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import item_use_route, me_capability, me_device_policy
from hengbot.model import STORE_BLACK, SV_STAFF_SPEED, TVAL_STAFF
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-speed-staff-buysell-1124"
BUY_ROW = 36
SELL_ROW = 44


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def speed_staff(items):
    return next(item for item in items if (item.tval, item.sval) == (TVAL_STAFF, SV_STAFF_SPEED))


class SpeedStaffBuySell1124RecordedTest(unittest.TestCase):
    def replay(self, rows):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURE, Path(scratch.name))
        decided = []
        for row, (recorded, supply) in enumerate(steps[:rows]):
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(supply())
            decided.append((row, (recorded["key"], recorded["reason"]), (key, policy.last_reason)))
            post(policy, recorded["key"])
        return policy, decided, steps

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def test_the_recorded_rows_and_the_sale(self):
        _policy, _decided, steps = self.replay(0)
        self.assertEqual((steps[BUY_ROW][0]["key"], steps[BUY_ROW][0]["reason"]),
                         ("pN\r", "shop:in-store-buy"))
        self.assertEqual((steps[SELL_ROW][0]["key"], steps[SELL_ROW][0]["reason"]),
                         ("d0y", "shop:in-store-sell"))

    def test_the_black_market_does_not_buy_the_capped_speed_staff(self):
        policy, decided, steps = self.replay(BUY_ROW)
        for row, recorded, mine in decided:
            if row not in (5, 7):
                self.assertEqual(mine, recorded, row)
        board = steps[BUY_ROW][1]()
        self.assertEqual(board.store.store_type, STORE_BLACK)
        ware = speed_staff(board.store.items)
        self.assertEqual((ware.price, ware.charges), (21292, 5))
        self.assertEqual(me_capability.count(policy, board, "staff", SV_STAFF_SPEED), 99)

        key, reason = self.decide(policy, board)

        # Recorded: ('pN\r', 'shop:in-store-buy'), the staff at 21,292.
        self.assertNotEqual(key, "pN\r")
        self.assertNotEqual(reason, "shop:in-store-buy")
        self.assertEqual(board.player.gold, 122268)
        # One verdict: the ware the sale would sell is the ware the purchase refuses.
        self.assertTrue(item_use_route.surplus(policy, board, ware))
        self.assertFalse(me_device_policy.purchase_wanted(policy, board, ware))
        self.assertFalse(me_device_policy.copy_raises_power(policy, board, ware))

    def test_the_ordinary_order_refuses_a_surplus_ware(self):
        policy, _decided, steps = self.replay(BUY_ROW)
        board = steps[BUY_ROW][1]()
        ware = speed_staff(board.store.items)
        old = me_device_policy.purchase_wanted

        def buy_more_without_cap(policy_, snapshot, item):
            # DECLARED CONSTRUCTED: the device row's verdict before the fix.
            if (item.tval, item.sval) == (TVAL_STAFF, SV_STAFF_SPEED):
                return True
            return old(policy_, snapshot, item)

        with mock.patch.object(me_device_policy, "purchase_wanted", buy_more_without_cap):
            with policy._in_store_pure_scope(), contextlib.redirect_stdout(io.StringIO()):
                picked = policy._next_purchase(board)
            self.assertIsNot(picked, ware)
            key, _reason = self.decide(policy, board)
        self.assertNotEqual(key, "pN\r")


if __name__ == "__main__":
    unittest.main()
