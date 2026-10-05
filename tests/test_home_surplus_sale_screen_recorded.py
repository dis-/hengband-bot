"""2026-10-05 sale failures: immutable decisions and B's actual store board.

No checkpoint or post-sale screen was supplied. Relief/visit state is rebuilt
from the withdrawal/route decisions; protocol 2 bypasses the missing attach
skill cache, with the last recorded map carried forward. A has decisions only:
its policy replay explicitly reconstructs the named boots from B's board and
uses A's recorded slot/visit. It is not an exact A snapshot replay.
"""
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest
import tests  # noqa: F401 -- isolate runtime files

from hengbot.model import parse_snapshot, STORE_ARMOURY, STORE_BLACK, STORE_HOME
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


FIXTURE = Path(__file__).parent / 'fixtures/home-surplus-sale-screen-20261005.json.gz'
SHA256 = 'e4c80991c8e2a6008d6558cbcac9e19ef08652ff97702381b3acb3b4844182f2'


class HomeSurplusSaleScreenRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(payload))

    def board(self):
        row = dict(self.data['B_states'][-1]['row'], grid_map=self.data['B_grid_map'])
        return replace(parse_snapshot(row), protocol_version=2)

    def policy_at(self, board, *, enabled, enforced=False, opened=6335):
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = enforced
        policy._in_store_ops_enabled = enabled
        policy.observe_store_screen(True)
        target = next(i for i in board.inventory if i.inscription == '@0')
        policy._home_full_relief = {
            'town': policy._effective_town_id(board),
            'sale': (policy._item_signature(target), STORE_ARMOURY, 0),
            'withdrawn': True, 'remaining': 1, 'deposits': (),
        }
        policy._store_visit = StoreVisit('town-errand', 'shopping', STORE_ARMOURY,
            StoreVisitPhase.OPERATING, opened_sequence=opened)
        return policy, target

    def assert_owned_leave(self, policy, board):
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ('\x1b', 'shop:unsellable-home-full-surplus-sale-refused'))
        self.assertIsNone(policy._batch_sell_pending)
        self.assertEqual(policy.decision_claim['owner'], 'shop-sell')
        self.assertEqual(policy._claim_register.current.execution.producer, 'shop-sell')
        for name in ('declaration_mismatch', 'claim_verdict_conflict', 'violation'):
            self.assertIsNone(policy.decision_claim[name])
        self.assertIsNone(policy._s33_shadow_verdict(board, key)['would_stop'])
        self.assertNotIn(STORE_ARMOURY, policy._store_sale_refused)

    def test_A_recorded_failure_and_reconstructed_owned_refusal(self):
        rows = [e['row'] for e in self.data['A_decisions']]
        self.assertEqual([r['decision_sequence'] for r in rows], list(range(1128, 1133)))
        self.assertEqual([r['key'] for r in rows],
                         ['5  pb\x1b', '\x1b`n".', '{o@0\r', 'd0y', '\x1b'])
        self.assertEqual(rows[3]['reason'], 'shop:in-store-sell')
        self.assertEqual(self.data['A_breaker']['cause'], 'unowned-screen')
        self.assertEqual(self.data['A_breaker']['decision_sequence'], 1131)
        # A's message identifies the same boots [2,-2], without B's sale tag.
        board = self.board()
        target = next(i for i in board.inventory if i.inscription == '@0')
        self.assertEqual(target.name.split(']')[0], rows[3]['messages'][0].split(']')[0])
        # DECLARED CONSTRUCTED: A's inventory/skill checkpoint is absent.
        board = replace(board, turn=rows[3]['turn'], inventory=tuple(
            replace(i, slot='o') if i == target else
            replace(i, slot='q') if i.slot == 'o' else i
            for i in board.inventory))
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, _ = self.policy_at(board, enabled=True, enforced=enforced, opened=1129)
                self.assert_owned_leave(policy, board)

    def test_B_recorded_singleton_and_posted_tail_now_leave(self):
        board = self.board()
        target = next(i for i in board.inventory if i.inscription == '@0')
        self.assertEqual((target.slot, target.count, target.tval, target.sval, target.to_a),
                         ('q', 1, 30, 2, -2))
        self.assertTrue(target.known and target.fully_known and target.is_ego)
        self.assertFalse(target.is_cursed or target.is_broken or target.is_artifact)
        self.assertEqual(self.data['B_states'][-1]['line'], 74)
        self.assertEqual(board.turn, 11524631)
        decision = self.data['B_decisions'][-1]['row']
        self.assertEqual((decision['reason'], decision['key']),
                         ('shop:one-shot-sale-compose', 'd0y'))
        self.assertEqual(''.join(e['row']['character'] for e in self.data['B_posted']), 'd0y')
        self.assertIn('in_store_breaker=unowned-screen', self.data['B_stderr'])
        self.assertIn('reason=unowned unknown: unrecognized-store-input', self.data['B_stderr'])
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, _ = self.policy_at(board, enabled=False, enforced=enforced)
                self.assert_owned_leave(policy, board)

    def test_shared_acceptance_excludes_negative_armour_even_in_black_market(self):
        board = self.board()
        policy, target = self.policy_at(board, enabled=True)
        for tval in range(30, 39):
            with self.subTest(tval=tval):
                armour = replace(target, tval=tval)
                self.assertFalse(policy._store_accepts_sale(STORE_ARMOURY, armour))
                self.assertFalse(policy._store_accepts_sale(STORE_BLACK, armour))
                self.assertTrue(policy._store_accepts_sale(STORE_HOME, armour))
        self.assertTrue(policy._store_accepts_sale(STORE_ARMOURY, replace(target, to_a=0)))
        self.assertTrue(policy._store_accepts_sale(STORE_ARMOURY, replace(target, known=False)))
        self.assertTrue(policy._store_accepts_sale(STORE_ARMOURY, replace(target, is_artifact=True)))

    def test_batch_selection_uses_the_same_acceptance_gate(self):
        board = self.board()
        policy, target = self.policy_at(board, enabled=False)
        self.assertEqual(policy._current_store_sale_candidates(board), [])
        self.assertIsNone(policy._batch_sell_key(board, [target]))
        self.assertIsNone(policy._batch_sell_pending)

    def test_pending_inscription_rechecks_acceptance_on_observed_board(self):
        board = self.board()
        policy, target = self.policy_at(board, enabled=True)
        # DECLARED CONSTRUCTED: an older accepted plan survived to this board.
        policy._batch_sell_pending = {
            'store_type': STORE_ARMOURY, 'phase': 'await-inscription',
            'entries': [{'signature': policy._sale_item_identity(target), 'tag': '0'}],
            'before_gold': board.player.gold,
        }
        self.assertEqual(policy._batch_sell_key(board), '\x1b')
        self.assertEqual(policy.last_reason, 'shop:sale-unaccepted-leave')
        self.assertIsNone(policy._batch_sell_pending)

    def test_accepted_sale_still_uses_observed_stack_quantity_and_item_verdict(self):
        board = self.board()
        original = next(i for i in board.inventory if i.inscription == '@0')
        for count, expected in ((1, 'd0y'), (3, 'd03\ry')):
            with self.subTest(count=count):
                # DECLARED CONSTRUCTED: accepted armour and quantity boundary.
                target = replace(original, to_a=0, count=count)
                current = replace(board, inventory=tuple(
                    target if i == original else i for i in board.inventory))
                policy, _ = self.policy_at(current, enabled=True, enforced=True)
                key = policy.choose_key(current)
                self.assertEqual((key, policy.last_reason), (expected, 'shop:in-store-sell'))
                self.assertEqual(policy._in_store_entry_ledger['pending']['kind'], 'sell')
                self.assertEqual(policy._store_visit.operation_key, key)
                self.assertIsNone(policy._s33_shadow_verdict(current, key)['would_stop'])

    def test_inscription_merge_recomposes_quantity_from_the_observed_stack(self):
        board = self.board()
        original = next(i for i in board.inventory if i.inscription == '@0')
        # DECLARED CONSTRUCTED: a singleton plan, then an observed stack of 3.
        target = replace(original, to_a=0, count=3)
        after = replace(board, inventory=tuple(
            target if i == original else i for i in board.inventory))
        untagged = replace(target, count=1, inscription='',
                           name=target.name.replace(', @0', ''))
        before = replace(board, inventory=tuple(
            untagged if i == original else i for i in board.inventory))
        policy = HengbotPolicy()
        policy.prime(before)
        policy._town_claim_bar_enforced = True
        policy._in_store_ops_enabled = True
        policy.observe_store_screen(True)
        policy._home_full_relief = {
            'town': policy._effective_town_id(before),
            'sale': (policy._item_signature(untagged), STORE_ARMOURY, 0),
            'withdrawn': True, 'remaining': 1, 'deposits': (),
        }
        policy._store_visit = StoreVisit('town-errand', 'shopping', STORE_ARMOURY,
            StoreVisitPhase.OPERATING, opened_sequence=6335)
        inscription = policy.choose_key(before)
        self.assertEqual((inscription, policy.last_reason), ('{q@0\r', 'shop:in-store-inscribe'))
        self.assertEqual(policy._batch_sell_pending['entries'][0]['count'], 1)
        policy.confirm_key_posted(inscription)
        key = policy.choose_key(after)
        self.assertEqual((key, policy.last_reason), ('d03\ry', 'shop:in-store-sell'))
        entry = policy._batch_sell_pending['entries'][0]
        self.assertEqual((entry['count'], entry['quantity']), (3, 3))
        self.assertIsNone(policy._s33_shadow_verdict(after, key)['would_stop'])


if __name__ == '__main__':
    unittest.main()
