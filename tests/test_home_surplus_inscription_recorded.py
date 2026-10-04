"""21:07 recorded Home-surplus inscription; reconstructed visit/relief only.

No full checkpoint exists. Prime attaches to the two exact recorded STORE
boards (with the last emitted grid_map carried forward). Relief and the visit
are reconstructed from the recorded withdrawal/route and previous purchase.
The missing attach skill cache is bypassed with protocol 2, as in shadow3
pins; item/store data are untouched. No selector is mocked.
"""
from dataclasses import replace
import tests
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase

FIXTURE = Path(__file__).parent / 'fixtures/home-surplus-inscription-20261004.json.gz'
SHA256 = 'fc2f8c7954f25938fccced18cdca18e7c2f6c068ef17ea95111acd6b5ff726c7'

class HomeSurplusInscriptionRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(payload))

    def test_recorded_inscription_was_posted_without_a_sale(self):
        data = self.data
        self.assertEqual(data['decisions']['238']['key'], '{c@2\r')
        self.assertEqual((data['decisions']['239']['key'], data['decisions']['239']['reason']),
                         ('', 'shop:one-shot-in-flight'))
        self.assertEqual(''.join(row['character'] for row in data['posted'].values()), '{c@2\r')
        before, after = (parse_snapshot(data['boards'][str(n)]) for n in (77, 78))
        self.assertEqual(before.player.gold, after.player.gold)
        self.assertEqual([(i.slot, i.count) for i in before.inventory],
                         [(i.slot, i.count) for i in after.inventory])
        self.assertEqual(next(i for i in after.inventory if i.slot == 'c').inscription, '@2')

    def test_observed_inscription_advances_to_owned_sale(self):
        before, after = (replace(parse_snapshot(self.data['boards'][str(n)]), protocol_version=2) for n in (77, 78))
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = HengbotPolicy()
                policy.prime(before)
                policy._town_claim_bar_enforced = enforced
                policy._in_store_ops_enabled = True
                policy.observe_store_screen(True)
                target = next(i for i in before.inventory if i.slot == 'c')
                policy._home_full_relief = {'town': policy._effective_town_id(before),
                    'sale': (policy._item_signature(target), 4, 0), 'withdrawn': True,
                    'remaining': 1, 'deposits': ()}
                policy._store_visit = StoreVisit('town-errand', 'shopping', 4,
                    StoreVisitPhase.OPERATING, opened_sequence=20)
                # Row 232 bought on the previous entry. Row 233 confirms it
                # then exits via Home relief, leaving that entry ledger behind.
                previous = self.data['decisions']['232']['store_visit']
                policy._in_store_entry_ledger = {
                    'store': previous['store_type'],
                    'opened_sequence': previous['opened_sequence'],
                    'ops': 1, 'pending': None, 'ended': False}
                key = policy.choose_key(before)
                self.assertEqual((key, policy.last_reason), ('{c@2\r', 'shop:in-store-inscribe'))
                self.assertEqual(policy._batch_sell_pending['phase'], 'await-inscription')
                policy.confirm_key_posted(key)
                key = policy.choose_key(after)
                self.assertEqual((key, policy.last_reason), ('d214\ry', 'shop:in-store-sell'))
                self.assertEqual(policy._batch_sell_pending['phase'], 'await-sale')
                self.assertEqual(policy._in_store_entry_ledger['pending']['kind'], 'sell')
                self.assertEqual(policy._store_visit.operation_key, key)
                self.assertEqual(policy._claim_register.current.execution.producer, 'shop-sell')
                self.assertIsNone(policy._s33_shadow_verdict(after, key)['would_stop'])

if __name__ == '__main__':
    unittest.main()
