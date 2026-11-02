"""Recorded Home-tail continuation after a posted Home exit."""

import base64
import gzip
import hashlib
import json
import pickle
from pathlib import Path
import unittest

import tests  # noqa: F401 -- isolate runtime files
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.policy import HengbotPolicy


class DeclarationR14Test(unittest.TestCase):
    def test_recorded_router_entry_keeps_its_declared_wait_through_detector_repair(self):
        # Short attachment from the unmodified 028434cc r14 replay. The entry
        # was selected on 3705; only confirmation and the next recorded board
        # are driven here. No later board is claimed after a changed key.
        path = Path(__file__).parent / 'fixtures/live29-router-entry.json.gz'
        packed = path.read_bytes()
        self.assertEqual(hashlib.sha256(packed).hexdigest(),
                         '54b0c6fd3148d869e66cf390a7b66cad25a5d97bfe6288a52297e5beb287d10f')
        data = json.loads(gzip.decompress(packed))
        snapshot = pickle.loads(base64.b64decode(data['snapshot']))
        for enforced in (False, True):
            for restored in (False, True):
                with self.subTest(enforced=enforced, restored=restored):
                    policy = restore_checkpoint(HengbotPolicy, data['checkpoint'])
                    policy.confirm_key_posted(data['key'])
                    if restored:
                        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
                    parent = policy._town_hold.claims.current
                    self.assertEqual(parent.owner.value, 'store-router')
                    self.assertEqual(parent.goal.source, 'store-entry')
                    declaration = parent.execution
                    self.assertEqual(declaration.producer, 'store-router')
                    self.assertEqual(declaration.state, 'awaiting')
                    self.assertEqual(declaration.operation_ref, 'decision:3705:5')
                    self.assertEqual(declaration.expected_effect, 'store-page-open')
                    self.assertEqual(declaration.continuation, 'store.entry.observe')
                    self.assertFalse(policy._store_visit.operation_posted)
                    self.assertEqual(policy.choose_key(snapshot), '2')
                    self.assertEqual(policy.last_reason,
                                     'town-progress-invariant:defect:'
                                     'store:entry-await-observation=>store:entry-await-observation')


if __name__ == "__main__":
    unittest.main()
