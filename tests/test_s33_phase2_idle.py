"""DECLARED CONSTRUCTED B's final no-action seam.

10562/10563 retain the Home-errand/idle pairing but no board or checkpoint.
The corridor and the ladder's None sentinel are explicitly constructed.
Only _decide is substituted: choose_key's final fallback, entry admission,
declaration and shadow detector run unmodified. No readiness result is faked.
"""
import unittest
from unittest.mock import patch
import tests  # noqa: F401
from hengbot.claim_register import observe
from hengbot.policy import HengbotPolicy
from test_s33_batch_admission import corridor
from s33_phase2_fixtures import pin


class IdleFallbackTest(unittest.TestCase):
    def test_none_fallback_records_its_actual_admission(self):
        self.assertEqual(pin(10563)['row']['reason'], 'policy:none-wait')
        snapshot = corridor()
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        policy._crossarea_fundraising_enforced = True
        goal = pin(10562)['row']['claim']['goal']
        policy._claim_register.declare('home-errand',
            observe(tuple(goal['expectation']), goal['within'], source=goal['source']),
            floor=snapshot.floor_key)
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: DECLARED CONSTRUCTED missing B checkpoint; only the ladder None sentinel is supplied, with real fallback admission, claim exit and shadow validation.
        with patch.object(policy, '_decide', return_value=None):
            key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ('5', 'policy:none-wait'))
        rows = [row for row in policy._decision_errand_deferred
                if row['deferred_reason'] == 'entry:idle-fallback']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['producer_key'], key)
        self.assertFalse(rows[0]['token_would_admit'])
        self.assertIsNone(policy._s33_shadow_verdict(snapshot, key)['would_stop'])
        self.assertIsNone(policy.decision_claim['claim_verdict_conflict'])

    def test_on_does_not_emit_foreign_fallback(self):
        snapshot = corridor()
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._town_claim_bar_enforced = True
        policy._crossarea_fundraising_enforced = True
        goal = pin(10562)['row']['claim']['goal']
        policy._claim_register.declare('home-errand',
            observe(tuple(goal['expectation']), goal['within'], source=goal['source']),
            floor=snapshot.floor_key)
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: DECLARED CONSTRUCTED missing B checkpoint; only the ladder None sentinel is supplied to exercise final fallback refusal through choose_key.
        with patch.object(policy, '_decide', return_value=None):
            self.assertIsNone(policy.choose_key(snapshot))


if __name__ == '__main__':
    unittest.main()
