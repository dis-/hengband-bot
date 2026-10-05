"""Recorded October 5 relief effects with DECLARED RECONSTRUCTED owner state.

No policy checkpoint exists in these backups. Reconstruct a seven-slot relief
and its posted/observed sale from the captured inventory delta. Exercise the
real relief producer, progress vector, and arbiter, not a historical replay
after changed commands. The no-space-effect control is constructed.
"""
import gzip
import hashlib
import json
from pathlib import Path
import unittest

import tests  # noqa: F401 -- isolate runtime writes
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / 'fixtures/home-relief-progress-20261005.json.gz'


def captured_board(row):
    # Constructed static lore only; the recorded perceptions remain intact.
    lore = {monster['race_id']: MonraceKnowledge(10, 110, False, False)
            for monster in row.get('visible_monsters', []) + row.get('detected_monsters', [])}
    return parse_snapshot(row, lore)


class RecordedHomeReliefProgressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
            '401859e31d77e2c28957ef18cf91b09e26b0211a2a72a23c5cda2023d06548d1')
        cls.pin = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        cls.states = {entry['line']: entry['row'] for entry in cls.pin['state-fixed']}
        cls.decisions = {entry['line']: entry['row'] for entry in cls.pin['decisions']}

    def policy(self):
        p = HengbotPolicy()
        p.prime(captured_board(self.states[32]))
        p.consume_skill_knowledge(self.states[7])
        p._home_full_relief = {
            'town': p._effective_town_id(captured_board(self.states[32])),
            'remaining': 7, 'deposits': (), 'sale': None, 'withdrawn': False,
        }
        return p

    def observed_sale(self, p, withdrawn_line, sold_line):
        before = captured_board(self.states[32])
        taken = captured_board(self.states[withdrawn_line])
        sold = captured_board(self.states[sold_line])
        previous = {p._sale_item_identity(item) for item in before.inventory}
        surplus = [item for item in taken.inventory
                   if p._sale_item_identity(item) not in previous]
        self.assertEqual(len(surplus), 1)
        signature = p._item_signature(surplus[0])
        self.assertFalse(any(p._sale_item_identity(item) ==
                             p._sale_item_identity(surplus[0]) for item in sold.inventory))
        p._home_full_relief['sale'] = (signature, sold.store.store_type, 0)
        p._home_full_relief['withdrawn'] = False
        old_remaining = p._home_full_relief['remaining']
        p._home_full_relief_key(taken)
        self.assertTrue(p._home_full_relief['withdrawn'])
        self.assertEqual(p._home_full_relief['remaining'], old_remaining)
        key = p._home_full_relief_key(sold)
        self.assertEqual(p._home_full_relief['remaining'], old_remaining - 1)
        self.assertEqual(key, '\x1b')
        self.assertEqual(p.last_reason, 'home:scan-leave-store')
        # CONSTRUCTED outside response to the changed exit. A census cannot
        # be posted on the captured in-store sale-effect screen.
        from dataclasses import replace
        sold = replace(sold, store=None, turn=sold.turn + 1)
        key = p._home_full_relief_key(sold)
        self.assertEqual(p.last_reason, 'home:request-knowledge-scan')
        self.assertTrue(key.startswith('~9'))
        # Posting is outside this focused producer/arbitration pin. Clear the
        # reconstructed scan flight before the next captured sale observation.
        p.settle_home_knowledge_request()
        return sold, key

    def run_pin(self, *, erase_effect=False):
        p = self.policy()
        arbiter = p._town_turn_arbiter
        results = []
        for taken, sold in ((38, 56), (66, 72), (82, 88)):
            board, key = self.observed_sale(p, taken, sold)
            vector = p._town_arbiter_progress_vector(board, p.last_reason)
            if erase_effect:
                # Exact old vector shape, before the relief fact was added.
                vector = vector[:-1]
            allowed = arbiter.may_select(p.last_reason, vector)
            results.append((allowed, arbiter.observe(
                in_town=True, reason=p.last_reason, progress_vector=vector)))
            # A different producer between scans records the actual round-trip
            # recurrence; no clock or gold change is used as progress.
            arbiter.observe(in_town=True, reason='home:full-queue-surplus-withdraw',
                            progress_vector=vector)
        return p, results

    def test_recorded_home_relief_remaining_prevents_owner_retirement(self):
        self.assertEqual([len(self.states[n]['knowledge']['items'])
                          for n in (31, 57, 73)], [240, 239, 238])
        self.assertEqual([self.states[n]['store']['stock_num']
                          for n in (38, 66, 82)], [239, 238, 237])
        self.assertEqual(self.decisions[236]['reason'], 'town:blocked:owner-retired')
        _, before = self.run_pin(erase_effect=True)
        self.assertFalse(before[-1][0], before)
        p, after = self.run_pin()
        self.assertEqual(p._home_full_relief['remaining'], 4)
        self.assertTrue(all(allowed and row['progress'] and not row['would_retire']
                            for allowed, row in after), after)

    def test_home_relief_no_observed_space_effect_still_retires(self):
        p = self.policy()
        board = captured_board(self.states[56])
        arbiter = p._town_turn_arbiter
        reason = 'home:request-knowledge-scan'
        vector = p._town_arbiter_progress_vector(board, reason)
        for _ in range(arbiter.registry['detectors'].budget):
            row = arbiter.observe(in_town=True, reason=reason, progress_vector=vector)
            arbiter.observe(in_town=True, reason='home:full-queue-surplus-withdraw',
                            progress_vector=vector)
        self.assertFalse(row['progress'])
        self.assertTrue(row['would_retire'])
        self.assertFalse(arbiter.may_select(reason, vector))
        self.assertEqual(p._home_full_relief['remaining'], 7)

    def test_home_relief_gold_alone_does_not_change_progress_vector(self):
        p = self.policy()
        vectors = [p._town_arbiter_progress_vector(captured_board(self.states[n]),
                                                  'home:request-knowledge-scan')
                   for n in (56, 72, 88)]
        self.assertEqual(vectors[0], vectors[1])
        self.assertEqual(vectors[1], vectors[2])

    def test_home_relief_requested_withdrawal_without_effect_does_not_reduce_remaining(self):
        p = self.policy()
        taken = captured_board(self.states[38])
        empty = captured_board(self.states[56])
        previous = {p._sale_item_identity(item) for item in empty.inventory}
        target = next(item for item in taken.inventory
                      if p._sale_item_identity(item) not in previous)
        p._home_full_relief['sale'] = (p._item_signature(target), empty.store.store_type, 0)
        p._home_full_relief_key(empty)
        self.assertFalse(p._home_full_relief['withdrawn'])
        self.assertEqual(p._home_full_relief['remaining'], 7)
