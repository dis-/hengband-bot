"""Recorded 2026-10-07 Home-full surplus address-miss recovery pin.

The autorecover decision capture records key ``5ph2\r\x1b`` selecting Home
catalogue index 7 (letter h), signature (tval 65, sval 6), quantity 2. The
following board reports taking three Stone-to-Mud wands (5 charges), then
"that command cannot be used in a store" twice; the requested stack has no
inventory increase. The old recovery emitted the same blocked reason on
every subsequent observation. This pin reconstructs that failed errand state
from the recorded facts and checks that relief visibly skips it and proceeds
after a fresh catalogue.
"""

from dataclasses import replace
import unittest

import tests  # noqa: F401
from hengbot.home_errand import HomeErrandRequest
from hengbot.model import STORE_HOME, parse_snapshot
from test_home_discard_incidents_recorded import catalogue, policy_at, row


RECORDED_ATTEMPT = {
    "time": "2026-10-07T03:26:19+0900",
    "key": "5ph2\r\x1b",
    "selected_tval_sval": (65, 6),
    "resolved_index": 7,
    "resolved_letter": "h",
    "quantity": 2,
}
RECORDED_FAILURE_MESSAGES = (
    "3\u672c\u306e \u5ca9\u77f3\u6eb6\u89e3\u306e\u9b54\u6cd5\u68d2 (5\u56de\u5206)(n)\u3092\u53d6\u3063\u305f\u3002",
    "\u305d\u306e\u30b3\u30de\u30f3\u30c9\u306f\u5e97\u306e\u4e2d\u3067\u306f\u4f7f\u3048\u307e\u305b\u3093\u3002",
    "\u305d\u306e\u30b3\u30de\u30f3\u30c9\u306f\u5e97\u306e\u4e2d\u3067\u306f\u4f7f\u3048\u307e\u305b\u3093\u3002 <x2>",
)


class HomeFullWithdrawFailureIncidentRecordedTest(unittest.TestCase):
    def test_failed_address_is_skipped_and_fresh_catalogue_selects_other_surplus(self):
        self.assertEqual((RECORDED_ATTEMPT["resolved_index"],
                          RECORDED_ATTEMPT["resolved_letter"],
                          RECORDED_ATTEMPT["quantity"]), (7, "h", 2))
        self.assertIn("\u0035\u56de\u5206", RECORDED_FAILURE_MESSAGES[0])
        self.assertIn("\u5e97\u306e\u4e2d\u3067\u306f\u4f7f\u3048\u307e\u305b\u3093",
                      RECORDED_FAILURE_MESSAGES[1])

        before = parse_snapshot(row("221036", 85))
        policy = policy_at(before, enforced=True)
        stock = catalogue("221036")
        policy.consume_home_knowledge(stock)
        deposit = before.inventory[0]
        policy._begin_home_full_relief(
            before, ((policy._item_signature(deposit), deposit.count, deposit.count),),
            refused=True,
        )
        candidate = next(item for item in stock
                         if policy._home_full_sale_candidate(before, item) is not None)
        signature = policy._item_signature(candidate)
        policy._home_full_relief.update(
            sale=(signature, STORE_HOME, 0), mode="sale",
            stock_count=sum(item.count for item in stock
                            if policy._item_signature(item) == signature),
        )
        self.assertTrue(policy._file_home_errand(
            before,
            HomeErrandRequest(signature, candidate.count, "home-catalog", "full-home-sale"),
            knowledge_current=True,
        ))
        policy._home_errand.post(0)
        policy._home_errand.observe_outside(0)

        key = policy._home_full_relief_key(before)
        self.assertEqual(key, "5")
        self.assertEqual(policy.last_reason, "home:full-skip:surplus-withdraw-failed")
        self.assertEqual(policy._home_full_relief["skipped"][signature],
                         "surplus-withdraw-failed")
        self.assertIsNone(policy._home_full_relief["sale"])

        policy.consume_home_knowledge(stock)
        policy._home_full_relief_key(replace(before, turn=before.turn + 1))
        self.assertIsNotNone(policy._home_full_relief["sale"])
        self.assertNotEqual(policy._home_full_relief["sale"][0], signature)


if __name__ == "__main__":
    unittest.main()
