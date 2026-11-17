"""n1-a life-530 2026-11-17 18:24:29 stuck-prompt:home:atomic-withdraw.

The Home held fifteen stacks of the same クロスボウの矢 (signature equal):
fourteen of 99 and one of 1.  The catalogue selected the last stack (a single
arrow, so no quantity answer) while the letter observed on page 4 named the
first 99-arrow stack; the game then asked いくつですか (1-99) and the key
``5   pY\\x1b`` left the prompt unanswered.  The take must bind to the stack
the letter addresses (store/purchase-order.cpp asks the quantity only when
``item_store.number > 1``).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy import HengbotPolicy, STORE_HOME

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "incident-20261117-182429-n1a-530-home-duplicate-stack-withdraw.jsonl.gz"
)


class HomeDuplicateStackWithdrawRecordedPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = [json.loads(line) for line in stream if line.strip()]

    def _policy(self):
        page4, knowledge, entrance = self.rows
        policy = HengbotPolicy()
        policy.consume_home_knowledge(tuple(_parse_items(
            knowledge["knowledge"]["items"]
        )))
        policy._record_observed_home_addresses(parse_snapshot(page4))
        bolts = next(
            item for item in policy._home_knowledge_items
            if item.name == "クロスボウの矢 (1d5) (+0,+0) (61/shot 84/turn)"
        )
        policy._home_pending_item = policy._item_signature(bolts)
        policy._home_pending_quantity = 1
        policy._shopping_approach_store_type = STORE_HOME
        return policy, parse_snapshot(entrance)

    def test_d1_recorded_home_has_same_signature_stacks_of_99_and_1(self):
        policy, _entrance = self._policy()
        signature = policy._home_pending_item
        counts = [
            item.count for item in policy._home_knowledge_items
            if policy._item_signature(item) == signature
        ]
        self.assertEqual(counts, [99] * 14 + [1])

    def test_d2_take_answers_the_quantity_of_the_addressed_99_stack(self):
        policy, entrance = self._policy()

        key = policy._atomic_home_withdraw_key(
            entrance, entrance.player.position
        )

        self.assertIsNotNone(key)
        self.assertTrue(key.endswith("   pY1\r\x1b"), repr(key))
        telemetry = policy._home_atomic_withdraw_telemetry
        self.assertEqual(
            (telemetry["resolved_index"], telemetry["resolved_letter"],
             telemetry["quantity"]),
            (206, "Y", 1),
        )
        # The confirmed take shortens the catalogue at the addressed stack.
        self.assertEqual(policy._home_atomic_withdraw_index, 206)


if __name__ == "__main__":
    unittest.main()
