"""Hard-timeout pin for the October 4 post-purchase Home batch hang.

The policy is reconstructed by replay, not a live process checkpoint. The
board is captured row 82, following the two faithfully reproduced purchases.
"""
import tests  # isolate runtime writes, including in subprocesses
import base64
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import subprocess
import sys
import time
import unittest

from extraction_calibration import restore_recorded_checkpoint
from hengbot.policy import HengbotPolicy
from hengbot.model import SV_SCROLL_STAR_REMOVE_CURSE, TVAL_SCROLL
from hengbot.policy_constants import SELL_KEY
from dataclasses import replace

FIXTURE = Path(__file__).parent / 'fixtures/home-deposit-hang-20261004.json.gz'
FIXTURE_SHA256 = '3ff41369456241666dfe1ab9a858f64a5b1c9f997755001e95c8d6b2437b3024'


def restore(*, observe=False):
    payload = gzip.decompress(FIXTURE.read_bytes())
    assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
    row = json.loads(payload)
    policy = restore_recorded_checkpoint(HengbotPolicy, row['policy'])
    snapshot = pickle.loads(base64.b64decode(row['snapshot']))
    if observe:
        # Reconstruct only the recorded watch's confirmed purchase transition
        # for the quantity unit pins. The subprocess pin exercises this
        # transition through public choose_key with a hard timeout.
        _, signature, before_count, before_gold, _, _ = policy._store_buy_inflight
        after_count = policy._inventory_signature_count(snapshot, signature)
        assert after_count > before_count or snapshot.player.gold < before_gold
        policy._town_visit_purchases.add(signature)
        policy._town_visit_purchase_quantities[signature] = (
            policy._town_visit_purchase_quantities.get(signature, 0)
            + max(0, after_count - before_count))
    return policy, snapshot


def worker():
    policy, snapshot = restore()
    started = time.perf_counter()
    key = policy.choose_key(snapshot)
    print(json.dumps({'key': key, 'reason': policy.last_reason,
        'elapsed': time.perf_counter() - started,
        'refusal': policy._shop_selector_diagnostics.get('home_deposit_batch_refusal')}))


class HomeDepositHangRecordedTest(unittest.TestCase):
    def test_post_purchase_decision_returns_under_hard_timeout(self):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'],
            capture_output=True, text=True, timeout=8, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads(result.stdout)
        self.assertLess(row['elapsed'], 3)
        self.assertIsNone(row['refusal'])
        self.assertTrue(row['reason'].startswith('home:full-'), row)

    def test_recorded_reserve_is_protected_in_pack_but_transferred_to_home(self):
        policy, snapshot = restore(observe=True)
        item = next(i for i in snapshot.inventory
                    if i.tval == TVAL_SCROLL and i.sval == SV_SCROLL_STAR_REMOVE_CURSE)
        self.assertTrue(policy._star_remove_curse_reserve_deposit_pending)
        self.assertEqual(policy._retention_surplus(snapshot, item), 0)
        self.assertTrue(policy._home_deposit_candidate(item, snapshot))
        self.assertEqual(policy._home_deposit_quantity(snapshot, item), 1)
        self.assertEqual(policy._home_deposit_key(snapshot, item), SELL_KEY + item.slot)
        self.assertEqual(policy._star_remove_curse_reserve_deposit_inflight[1], 1)

    def test_reserve_transfer_moves_only_one_scroll_from_a_stack(self):
        # DECLARED CONSTRUCTED: same recorded reserve, three stacked scrolls.
        policy, snapshot = restore(observe=True)
        item = next(i for i in snapshot.inventory
                    if i.tval == TVAL_SCROLL and i.sval == SV_SCROLL_STAR_REMOVE_CURSE)
        stacked = replace(item, count=3)
        board = replace(snapshot, inventory=tuple(stacked if i.slot == item.slot else i
                                                for i in snapshot.inventory))
        self.assertEqual(policy._home_deposit_quantity(board, stacked), 1)
        self.assertEqual(policy._home_deposit_key(board, stacked), SELL_KEY + item.slot + '1\r')

    def test_pending_withdrawal_keeps_ordinary_retention(self):
        policy, snapshot = restore(observe=True)
        item = next(i for i in snapshot.inventory
                    if i.tval == TVAL_SCROLL and i.sval == SV_SCROLL_STAR_REMOVE_CURSE)
        policy._star_remove_curse_reserve_withdraw_pending = True
        self.assertEqual(policy._home_deposit_quantity(snapshot, item), 0)

    def test_zero_quantity_stops_with_diagnostic(self):
        policy, snapshot = restore(observe=True)
        item = next(i for i in snapshot.inventory
                    if i.tval == TVAL_SCROLL and i.sval == SV_SCROLL_STAR_REMOVE_CURSE)
        policy._star_remove_curse_reserve_deposit_pending = False
        # Deliberately pass a stale candidate to the composer; the selector
        # would no longer choose it under ordinary visit-purchase retention.
        self.assertEqual(policy._home_deposit_batch(snapshot, item), ())
        # Public choose's final diagnostic pass must preserve the marker for
        # cli._write_decision's shop_selector JSONL field, for this decision.
        policy._record_shop_selector_diagnostics(snapshot, '')
        self.assertEqual(policy._shop_selector_diagnostics['home_deposit_batch_refusal'],
                         {'slot': item.slot, 'reason': 'no-simulated-surplus'})
        policy._decision_sequence += 1
        policy._record_shop_selector_diagnostics(snapshot, '')
        self.assertNotIn('home_deposit_batch_refusal', policy._shop_selector_diagnostics)


if __name__ == '__main__':
    if '--worker' in sys.argv:
        worker()
    else:
        unittest.main()
