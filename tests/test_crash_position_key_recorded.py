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

FIXTURE = Path(__file__).parent / 'fixtures/crash-position-key-20261001.json'


def replay():
    board = parse_snapshot(json.loads(FIXTURE.read_text(encoding='utf8')))
    policy = HengbotPolicy()
    policy.prime(board)
    policy._crossarea_fundraising_enforced = True
    policy._calibration_phase = 'deposit'
    with patch.object(policy, '_choose_key', side_effect=policy._calibration_town_key), \
            patch.object(policy, '_skill_exp_request_key', return_value=None):
        key = policy.choose_key(board)
    return key, policy.last_reason


if __name__ == '__main__':
    print(replay())
