"""While Recall counts down, an unseen hit of a third of the maximum HP: *Destruction*, else Teleportation.

Owner 2026-11-21 (verbatim, LOCKED) 「破壊が使えるなら破壊を優先。なければテレポート。」, the answer to
acting during the Recall's countdown when one unseen attacker's observed hit takes a third of the
maximum HP or more, instant death or not (recall_wait_teleport ``big_hit_key``).  Recorded (capture
n1c-218-20261121-death-48f, tests/fixtures/n1c-218-recall-wait-teleport-1121): on the Castle's 48F
with its Recall counting down, n1-c (max HP 674) took an unseen mana breath of 266 at turn 3164597
(HP 542 -> 276; 『ストリガルドワー』 in view) and drank a Potion of Healing (item:heal); it held no
*Destruction* means, so the answer is the Teleportation scroll.

DECLARED CONSTRUCTED: the CLI's resume reads on, as in the live process; for the *Destruction*
case, destruction_use's key answering a use (the means held).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import destruction_use, recall_wait_teleport
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-218-recall-wait-teleport-1121"
BIG_HIT_TURN = 3164597


class RecallWaitUnseenBigHitRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    @staticmethod
    def deliver(policy, key):
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def until_big_hit(self):
        """The policy just before the decision on turn BIG_HIT_TURN, and that board."""
        policy, _journal, steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        policy._me_power_resume_reads = True  # the live CLI's
        for recorded, supply in steps:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(board)
            self.deliver(policy, recorded["key"])
        rows = json.loads(lzma.decompress((FIXTURE / "dungeon.json.xz").read_bytes()))
        for row in rows:
            board = parse_snapshot(row["board"], policy._monrace_knowledge)
            if board.turn == BIG_HIT_TURN:
                self.assertEqual(row["reason"], "item:heal")  # recorded
                return policy, board
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(board)
            self.deliver(policy, row["key"])
        self.fail("no big-hit board")

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def test_without_destruction_the_teleport(self):
        policy, board = self.until_big_hit()
        self.assertTrue(board.player.recalling)
        key, reason = self.decide(policy, board)
        self.assertEqual(reason, "emergency:teleport")  # recall_wait_teleport.BIG_HIT_TELEPORT_REASON
        self.assertTrue(key.startswith("r"), key)
        self.assertTrue(recall_wait_teleport.big_unseen_hit(policy, board))  # 266 * 3 >= 674

    def test_destruction_first_when_held(self):
        policy, board = self.until_big_hit()

        def use(policy_, snapshot, **kwargs):  # DECLARED: the means held
            policy_.last_reason = destruction_use.REASON + kwargs.get("suffix", "")
            return "UA3"
        with mock.patch.object(destruction_use, "key", side_effect=use):
            key, reason = self.decide(policy, board)
        self.assertEqual(key, "UA3")
        self.assertTrue(reason.endswith(recall_wait_teleport.BIG_HIT_SUFFIX), reason)


if __name__ == "__main__":
    unittest.main()
