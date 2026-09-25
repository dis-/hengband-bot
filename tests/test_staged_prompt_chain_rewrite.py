"""P2 (class): a staged prompt chain belongs to the key it staged.

Live incident 2026-09-25 12:56 (tests/test_stuck_prompt_staged_tail_
recorded.py): the launcher-enchant producer staged its chain for 'rlc', the
town progress invariant replaced the emitted key at the ``choose_key`` exit,
the stale chain made the sender refuse the replacement as ``key-replaced``
and the idle game never produced another board, so the run ended as a
misattributed ``stuck-prompt``.

- The policy exit keeps a staged chain only for the key it gates (the real
  ``identify:dungeon-equipment`` producer, rewritten by the exit's own
  ``_forbid_wait_while_damaged`` seam), and the sender then posts the
  replacement.
- A rewrite after ``choose_key`` (the CLI's ``validate_read_key`` call) that
  still reaches the sender with a foreign chain stops the run under its own
  name instead of waiting for a board an idle game never emits.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hengbot.cli import (
    PostingContract,
    SendResult,
    _send_decision_key_with_prompt_chain,
)
from hengbot.policy_constants import WAIT_KEY
from tests.run_follow_hygiene import run_follow as _run_follow
from tests.test_home_light_alternation import _fresh_policy
from tests import test_home_light_alternation_cli as d6_pins
from tests.test_home_light_alternation_cli import FakeControlClient


class _Sandbox(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory(prefix="hengbot-chain-rewrite-")
        self.sandbox = Path(self.scratch.name)
        self.previous_cwd = Path.cwd()
        os.chdir(self.sandbox)
        self.previous_history = os.environ.get("HENGBOT_HOME_HISTORY_DIR")
        os.environ["HENGBOT_HOME_HISTORY_DIR"] = str(self.sandbox)

    def tearDown(self) -> None:
        os.chdir(self.previous_cwd)
        if self.previous_history is None:
            os.environ.pop("HENGBOT_HOME_HISTORY_DIR", None)
        else:
            os.environ["HENGBOT_HOME_HISTORY_DIR"] = self.previous_history
        self.scratch.cleanup()


class PolicyExitReleasesReplacedChainTest(_Sandbox):
    def _decide(self, rewrite=None):
        policy = _fresh_policy(self.sandbox)
        snapshot = d6_pins.PromptGatedIdentificationPins._snapshot()
        if rewrite is None:
            key = policy.choose_key(snapshot)
        else:
            with patch.object(
                policy, "_forbid_wait_while_damaged",
                side_effect=lambda _snapshot, _key: rewrite,
            ):
                key = policy.choose_key(snapshot)
        return policy, snapshot, key

    def _send(self, policy, snapshot, key):
        received = []

        def send(segment, *, in_store=False, decision=None):
            received.append(segment)
            return SendResult.SENT

        path = self.sandbox / f"input-{time.monotonic_ns()}.jsonl"
        path.write_text("", encoding="utf-8")
        with path.open("r", encoding="utf-8") as stream:
            sent, _line, chain, result = _send_decision_key_with_prompt_chain(
                send, "snapshot-line", key, None, set(),
                policy=policy, shadow_client=FakeControlClient([""]),
                file=stream, deadline=time.monotonic() + 0.05,
                poll_interval=0.005, prompt_japanese=False,
                decision={"key": key, "reason": policy.last_reason},
                snapshot=snapshot, posting_contract=PostingContract(),
                in_store=False,
            )
        return sent, chain, result, received

    def test_unrewritten_decision_keeps_its_chain(self):
        policy, _snapshot, key = self._decide()
        self.assertEqual(key, "uis")
        self.assertEqual(policy.last_reason, "identify:dungeon-equipment")
        chain = policy.peek_staged_prompt_chain()
        self.assertEqual(
            (chain["owner"], chain["key"]), ("identify:dungeon-equipment", "uis")
        )

    def test_exit_rewrite_releases_the_replaced_chain(self):
        policy, snapshot, key = self._decide(rewrite=WAIT_KEY)
        self.assertEqual(key, WAIT_KEY)
        self.assertIsNone(policy.peek_staged_prompt_chain())
        sent, chain, result, received = self._send(policy, snapshot, key)
        self.assertIs(sent, SendResult.SENT)
        self.assertIsNone(chain)
        self.assertIsNone(result)
        self.assertEqual(received, [WAIT_KEY])

    def test_exit_rewrite_to_a_foreign_command_of_equal_length_releases(self):
        # Same length, another command byte: not the staged command.
        policy, _snapshot, key = self._decide(rewrite="\x1b`n")
        self.assertEqual(key, "\x1b`n")
        self.assertIsNone(policy.peek_staged_prompt_chain())

    def test_letter_rebind_keeps_the_chain_for_the_gated_sender(self):
        # A rebind of the selected letters keeps the staged command; the
        # sender gates the emitted letters (validate_read_key's contract).
        policy, _snapshot, key = self._decide(rewrite="uit")
        self.assertEqual(key, "uit")
        chain = policy.peek_staged_prompt_chain()
        self.assertEqual(chain["key"], "uis")


class SenderStopsOnForeignChainTest(_Sandbox):
    def _drive(self):
        from hengbot import cli

        state = self.sandbox / "state.jsonl"
        decisions = self.sandbox / "decisions.jsonl"
        pins = d6_pins.PromptGatedIdentificationPins()
        pins.sandbox = self.sandbox
        state.write_text(pins._snapshot_json(1, identify=True), encoding="utf-8")
        args = cli._build_argument_parser().parse_args([
            "--state-file", str(state), "--decision-log", str(decisions),
            "--poll-interval", "0.001", "--stall-timeout", "0.2",
        ])
        args.wait_telemetry = Mock()
        args.prompt_japanese = False
        fake = FakeControlClient(["(i, ESC) Use which staff? ".ljust(80)])
        args.shadow_client = fake
        policy = _fresh_policy(self.sandbox)
        choose_key = policy.choose_key

        decided = threading.Event()

        def choose(snapshot):
            if snapshot.turn >= 3:
                policy._decision_sequence += 1
                policy.last_reason = "equipment-transaction:restore-blocked-terminal"
                return ""
            try:
                return choose_key(snapshot)
            finally:
                decided.set()

        policy.choose_key = Mock(side_effect=choose)
        validate_read_key = policy.validate_read_key

        def rewrite_after_decision(snapshot, key):
            # A rewrite between choose_key and the sender (the CLI's
            # validate_read_key call site) leaves the decision's chain staged.
            if key == "uis":
                return WAIT_KEY
            return validate_read_key(snapshot, key)

        policy.validate_read_key = Mock(side_effect=rewrite_after_decision)
        received = []
        following = threading.Event()

        def append_snapshots():
            # The follow loop decides on appended boards: turn 2 is the
            # chain decision; turn 3 (a terminal filler) only exists after
            # it, so a driver that keeps waiting reaches it.
            following.wait()
            with state.open("a", encoding="utf-8") as stream:
                stream.write(pins._snapshot_json(2, identify=True))
                stream.flush()
                decided.wait(5)
                time.sleep(0.05)
                stream.write(pins._snapshot_json(3, identify=True))
                stream.flush()

        writer = threading.Thread(target=append_snapshots)
        writer.start()
        freeze = Mock()
        try:
            with patch(
                "hengbot.cli._arm_decision_watchdog", side_effect=following.set
            ), patch("hengbot.cli._freeze_incident_safely", freeze):
                result = _run_follow(
                    args, policy,
                    lambda key, **_kwargs: received.append(key) or True, {},
                )
        finally:
            following.set()
            decided.set()
            writer.join()
        rows = [
            json.loads(line)
            for line in decisions.read_text(encoding="utf-8").splitlines()
        ]
        return result, received, rows, policy, freeze

    def test_foreign_chain_stops_with_its_own_cause(self):
        result, received, rows, policy, freeze = self._drive()
        self.assertEqual(result, 0)
        # Nothing reached the game: neither the chain nor the replacement.
        self.assertEqual(received, [])
        self.assertEqual(rows[0]["key"], WAIT_KEY)
        self.assertEqual(
            {name: rows[0]["staged_prompt_chain"][name]
             for name in ("outcome", "posted")},
            {"outcome": "not-posted", "posted": ""},
        )
        self.assertEqual(
            [call.args[1] for call in freeze.call_args_list],
            ["staged-chain-key-replaced"],
        )
        # The run stopped on that decision; it did not wait for another board.
        self.assertEqual(policy.choose_key.call_count, 1)
        self.assertIsNone(policy.peek_staged_prompt_chain())


if __name__ == "__main__":
    unittest.main()
