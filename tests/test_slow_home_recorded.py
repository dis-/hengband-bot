"""Full Home performance and key/reason equality on the October 5 recording.

The checkpoint is reconstructed from the recorded suffix, not a live capture.
The independent suffix pin consumes all responses and chooses only boards on
which the recorded driver chose. Neither pin freezes equipment decisions.
"""
import tests  # runtime isolation, inherited by the child processes
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import time
import unittest

from extraction_calibration import restore_recorded_checkpoint
from hengbot.policy import HengbotPolicy
from replay_slow_home import replay

FIXTURES = Path(__file__).parent / 'fixtures'
CHECKPOINT = FIXTURES / 'slow-home-faithful-20261005.json.gz'
RESPONSES = FIXTURES / 'slow-home-20261005.responses.jsonl.gz'
CHECKPOINT_SHA256 = 'be2f4282eaf69ad219ea8daf52833525a803cfd08e390cd39a5542e83d9323b5'


def fixture():
    payload = CHECKPOINT.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == CHECKPOINT_SHA256
    return json.loads(gzip.decompress(payload))


def worker(mode):
    expected = fixture()
    if mode == '--replay':
        actual = replay(RESPONSES, profile_final=False)
        assert [(r['key'], r['reason']) for r in actual] == [
            (r['key'], r['reason']) for r in expected['decisions']]
        print(json.dumps({'equal_decisions': len(actual), 'elapsed': actual[-1]['elapsed']}))
        return
    policy = restore_recorded_checkpoint(HengbotPolicy, expected['policy'])
    snapshot = pickle.loads(base64.b64decode(expected['snapshot']))
    assert len(policy._home_knowledge_items) == 240
    started = time.thread_time()
    key = policy.choose_key(snapshot)
    elapsed = time.thread_time() - started
    assert (key, policy.last_reason) == (
        expected['decisions'][-1]['key'], expected['decisions'][-1]['reason'])
    print(json.dumps({'key': key, 'reason': policy.last_reason, 'elapsed': elapsed}))


class SlowHomeRecordedTest(unittest.TestCase):
    def child(self, mode, timeout):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(
            str(root / part) for part in ('', 'src', 'tests', 'scripts')))
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), mode],
                                capture_output=True, text=True, timeout=timeout,
                                cwd=root, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.splitlines()[-1])

    def test_recorded_board_decides_under_five_seconds_with_hard_timeout(self):
        row = self.child('--worker', 12)
        self.assertLess(row['elapsed'], 5, row)
        self.assertEqual((row['key'], row['reason']), ('1', 'home:request-knowledge-scan'))

    def test_recorded_suffix_keys_and_reasons_are_identical(self):
        self.assertEqual(hashlib.sha256(RESPONSES.read_bytes()).hexdigest(),
                         fixture()['source_sha256'])
        row = self.child('--replay', 30)
        self.assertEqual(row['equal_decisions'], 12)
        self.assertLess(row['elapsed'], 5, row)


if __name__ == '__main__':
    if '--worker' in sys.argv or '--replay' in sys.argv:
        worker(sys.argv[1])
    else:
        unittest.main()
