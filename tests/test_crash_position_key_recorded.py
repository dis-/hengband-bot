"""Crash board attachment, not a reconstruction of the lost live policy.

No checkpoint was captured. Explicit seam: select the real calibration deposit
producer and suppress the unrelated restart skill probe. The recorded final
player_turn is unchanged; all route composition and choose_key exit code runs.
No later recorded board is treated as a response to the changed decision.
"""
import tests  # noqa: F401
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint

FIXTURE = Path(__file__).parent / 'fixtures/crash-position-key-20261001.json'


def replay(restored=False):
    board = parse_snapshot(json.loads(FIXTURE.read_text(encoding='utf8')))
    policy = HengbotPolicy()
    policy.prime(board)
    policy._crossarea_fundraising_enforced = True
    policy._calibration_phase = 'deposit'
    if restored:
        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
    with patch.object(policy, '_choose_key', side_effect=policy._calibration_town_key), \
            patch.object(policy, '_skill_exp_request_key', return_value=None):
        key = policy.choose_key(board)
    return key, policy.last_reason


class CrashPositionKeyTest(unittest.TestCase):
    def test_recorded_board_returns_composed_key_after_checkpoint(self):
        self.assertEqual(hashlib.sha256(
            FIXTURE.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
            'aa91fb3596efca1d61c67d095fd61dd62c500d79157375e1b453f3ed38704ddb')
        for restored in (False, True):
            with self.subTest(restored=restored):
                self.assertEqual(replay(restored),
                                 ('\x1b`n(.', 'calibration:deposit-travel'))


if __name__ == '__main__':
    unittest.main()
