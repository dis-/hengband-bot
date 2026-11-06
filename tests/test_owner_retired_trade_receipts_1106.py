"""Productive Home round trips are not "no progress" (owner 2026-11-06).

Owner 2026-11-06: 「自宅との往復で鑑定や売却が進んでいるのに「進んでいない」と判定して止まる誤りも直す。」

Recorded: n1-a life-487, town:blocked:owner-retired-burst at 2026-11-06 00:09:37 (capture
20261106-000937-town-blocked-owner-retired-burst, carried into life-489's incident-captures),
decision rows 2586-2662.  Four owners retired in the visit (home-scan at 2613 and 2630,
store-router at 2648, home-visit at 2662) while each cycle traded: withdraw for identification ->
*Identify* -> deposit -> withdraw for full-home-sale -> sell, and buy -> deposit.  The pack was
the same after each cycle, so the vectors repeated; the store visit's effect flag stayed false
for every one-shot operation (rows 2586-2662), so no receipt reached the driver's counter and the
third counted retirement stopped the visit.  The receipt messages below are those rows' own.

DECLARED CONSTRUCTED: the driver double (tests/test_owner_retirement_slice1.Policy) and the boards
carrying only the recorded messages; the arbiter retirements are posted directly, as in
test_owner_retirement_slice1.BurstTest.
"""
import tests  # noqa: F401 -- runtime isolation
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot import cli
from tests.test_owner_retirement_slice1 import Policy, args, retire

SOLD_GLAIVE = "(トランプ)ギザルム (2d5) (+9,+7) (+1探索) {+探r因沌;麻, @1}を $8133で売却しました。"
SOLD_BAR = "(吸血)鉄棒 (2d7) (+3,+5) {経|吸, @1}を $8391で売却しました。"
BOUGHT_SPEED = "3服の スピードの薬を $1305で購入しました。"
BOUGHT_CLW = "体力回復の薬を $5252で購入しました。"
BOUGHT_RESIST = "耐性の薬を $4375で購入しました。"
STASHED = "体力回復の薬 {25%引き}を置いた。(c)"


def board(*messages, store_type=None):
    return SimpleNamespace(town_id=1, floor_key=(0, 0, 0), in_town=True, turn=100,
                           store=None if store_type is None else SimpleNamespace(store_type=store_type),
                           messages=tuple(messages))


class TradeReceiptTest(unittest.TestCase):
    def handle(self, policy, snapshot=None, key='5'):
        with patch('sys.stderr', io.StringIO()):
            result = cli._handle_owner_retirement(args(), snapshot or board(), key, policy)
        policy._decision_sequence += 1
        return result

    def test_life_487_cycles_that_sell_and_stash_do_not_burst(self):
        policy = Policy()
        self.handle(policy)  # the visit's baseline
        for receipt, owner in ((SOLD_GLAIVE, 'home-scan'), (SOLD_BAR, 'home-scan'),
                               (BOUGHT_CLW, 'store-router'), (BOUGHT_RESIST, 'home-visit')):
            self.handle(policy, board(receipt, store_type=2))
            retire(policy, owner)
            self.assertEqual(self.handle(policy), '5')
            self.assertNotEqual(policy.last_reason, 'town:blocked:owner-retired-burst')
            self.assertEqual(policy._owner_retired_no_progress_count, 1)

    def test_english_receipts_count_too(self):
        policy = Policy()
        self.handle(policy)
        retire(policy); self.handle(policy)
        retire(policy); self.handle(policy)
        self.handle(policy, board("You sold a Glaive (2d5) (+9,+7) for 8133 gold.", store_type=2))
        self.assertEqual(policy._owner_retired_no_progress_count, 0)

    def test_a_repeated_trade_or_a_home_move_is_no_progress(self):
        # A buy/sell or withdraw/deposit ping-pong repeats the same receipt, or none.
        policy = Policy()
        self.handle(policy)
        self.handle(policy, board(BOUGHT_SPEED, store_type=6))
        retire(policy); self.handle(policy)
        retire(policy); self.handle(policy, board(BOUGHT_SPEED, store_type=6))
        self.assertEqual(policy._owner_retired_no_progress_count, 2)
        self.handle(policy, board(STASHED, store_type=7))
        retire(policy); self.handle(policy)
        self.assertEqual(policy.last_reason, 'town:blocked:owner-retired-burst')


if __name__ == "__main__":
    unittest.main()
