"""Recorded calibration deposit travel and its first response, 2026-10-01.

Attachment wall: no policy checkpoint exists. As in the crash-position pin,
prime a fresh policy on the last 1722292 board, attach the recorded deposit
phase, and select the real calibration producer for the first decision only.
The periodic skill probe already ran live, so suppress that restart probe.
The next board uses the ordinary production ladder and choose_key exit.

Executor wall: augment the response with the completed input operation's
sequence/owner, as the live driver does. No screen or board is manufactured.
Check the first key against live before consuming its recorded response;
stop at the second decision, where the fixed key first differs from live.
"""
import tests  # noqa: F401 -- isolate live runtime files
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).parent / "fixtures/caltravel-20261001.json.gz"


def recorded():
    with gzip.open(FIXTURE, "rb") as source:
        body = source.read().replace(b"\r\n", b"\n")
    return json.loads(body), hashlib.sha256(body).hexdigest()


def replay(on, restored):
    data, _ = recorded()
    board = parse_snapshot(data["boards"][0])
    policy = HengbotPolicy()
    policy.prime(board)
    policy._crossarea_fundraising_enforced = True
    policy._town_claim_bar_enforced = on
    policy._calibration_phase = "deposit"
    if restored:
        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
    # Attachment chooses the recorded real producer only; the second decision
    # uses the unmodified ladder.
    with patch.object(policy, "_choose_key", side_effect=policy._calibration_town_key), \
            patch.object(policy, "_skill_exp_request_key", return_value=None):
        first_key = policy.choose_key(board)
    first = (first_key, policy.last_reason)
    live = data["decisions"][0]
    if first != (live["key"], live["reason"]):
        raise AssertionError(f"diverged before recorded response: {first!r} / {live!r}")
    declaration = dict(policy.decision_claim["execution"])
    policy.confirm_key_posted(first_key)
    response = dict(data["boards"][1])
    response["_completed_operation_sequence"] = policy._decision_sequence
    response["_completed_operation_owner"] = policy.last_reason
    if restored:
        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
    with patch.object(policy, "_skill_exp_request_key", return_value=None):
        second_key = policy.choose_key(parse_snapshot(response))
    second = (second_key, policy.last_reason)
    execution = (policy.decision_claim or {}).get("execution")
    print(f"caltravel s33={on} restored={restored}: first={first!r}; "
          f"next={second!r}; live-next={data['decisions'][1]!r}")
    return first, second, declaration, execution


class CaltravelRecordedTest(unittest.TestCase):
    def test_recorded_response_continues_calibration_off_and_s33(self):
        _, digest = recorded()
        self.assertEqual(digest,
                         "270606f1b1cc4d5cfa3e5b03a0d5899433d9eb84e8ea0a9461b8903aef8404b5")
        for on in (False, True):
            for restored in (False, True):
                with self.subTest(on=on, restored=restored):
                    first, second, declaration, execution = replay(on, restored)
                    self.assertEqual(first, ("\x1b`n(.", "calibration:deposit-travel"))
                    self.assertEqual(second, ("\x1b`n(.", "calibration:deposit-travel"))
                    for offer in (declaration, execution):
                        self.assertEqual(offer["producer"], "calibration")
                        self.assertEqual(offer["work_id"], "calibration:deposit-travel")
                        self.assertEqual(offer["expected_effect"], "home-reached")
                        self.assertEqual(offer["next_step"], "calibration.deposit")
                        self.assertEqual(offer["continuation"], "calibration.deposit")


if __name__ == "__main__":
    unittest.main()
