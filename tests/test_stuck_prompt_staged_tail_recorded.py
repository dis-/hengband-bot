"""Recorded pin: a rewritten decision does not keep the replaced key's prompt chain.

Live incident 2026-09-25 12:56 (the bot process resumed at 12:35:14 onto the
running game, the first run of the protocol-3 exe): after a dungeon 14 trip
(its last staged identify chain, sequence 7261 ``identify:pack-pressure``
'uqt', was released through both gates) the character recalled to the
Outpost.  On the landing board the skill-list probe (7286 '~f\\x1b') and
``town:recover`` (7287 'R&\\r') were posted; on the rested board (turn
5491561) decision 7288 was ``town-progress-invariant:defect:town:enchant-
launcher-tohit=>town-progress-invariant:approach`` with key '\\x1b`n%.'
(travel to the Alchemist, store 4).  The sender printed
``<identify:staged-tail-not-posted:key-replaced>``, posted nothing, and the
driver stopped about 20 s later with ``<stuck-prompt> no progress and window
recovery is disabled``.  The stop board is the state log's last row, an
ordinary ``player_turn``: the game was idle at its command prompt.

Root cause: ``_town_enchant_launcher_key`` (the recorded winning rung) staged
its prompt-gated chain for the Enchant To-Hit read 'rlc' (the row's ``read``
telemetry; gates "Read which scroll?" / "Enchant which item?"), then the town
progress invariant at the ``choose_key`` exit replaced the key with its
procurement approach.  The chain stayed staged, so
``_send_decision_key_with_prompt_chain`` found a chain that does not gate the
emitted key and returned the designed wait ``key-replaced`` without posting.
An idle game emits no further board, so the stall timer ended the run as
``stuck-prompt``.  The exe plays no part: the key never reached the transport.

Fix: the ``choose_key`` exit releases a staged chain whose command is not the
emitted key (``_release_rewritten_prompt_chain``, beside
``_release_rewritten_store_posting``), and the driver stops with the named
cause ``staged-chain-key-replaced`` if a rewrite after ``choose_key`` ever
reaches the sender with a foreign chain (tests/test_staged_prompt_chain_
rewrite.py).

Substrate (tests/extract_stuck_prompt_staged_tail_fixture.py): the recorded
facts of every decision from log index 3380 -- the first whose board the
emitter-truncated state log still holds -- to the stop, and the boards of the
closing window: the last dungeon board (7286 ``return:wait-recall``), the
landing (7286), 7287 and the stop board (7288).  The window is replayed on one
fresh policy through the public response path and the CLI's own sender.
Walls, each declared:
- attach: the policy attaches on the last dungeon board, as a resumed process
  attaches to the state log's last row, and first receives the process's
  ``~f`` skill list of 12:53 (the 7286 response in the window carries the same
  values), so the attach board is not spent on the probe;
- the calibration file is the one the process wrote at sequence 6608 and the
  window read, in a temporary directory, with the Home history/disposal files;
- the board of every decision that follows a posted key carries the live
  input executor's ``_completed_operation_sequence``/``_owner``;
- stop decision, ladder: which rung wins and which store the invariant's
  procurement progress names depend on this process's town history from
  before 12:44 (its Home catalogue, claim ledger and plan), which the capture
  no longer holds; a fresh policy ranks them differently.  The pin therefore
  takes both from the stop row: the ladder returns the recorded winning rung's
  real producer (``_town_enchant_launcher_key`` on the recorded board), and
  ``_town_procurement_progress_key`` returns the recorded key with the
  recorded progress action.  Everything after them is production code: the
  producer composes and stages the chain, the invariant wrapper decides the
  replacement and composes the reason, the exit seams run, and the sender
  posts.  The replay must reproduce the recorded key and reason of every
  window decision, the stop included.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import gzip
import hashlib
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import (
    PostingContract,
    SendResult,
    _consume_response_sequence,
    _send_decision_key_with_prompt_chain,
)
from hengbot.monrace_knowledge import load_monrace_knowledge

from test_esp_threat_rest_recorded import EDIT, _policy
from test_home_light_alternation_cli import FakeControlClient


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "stuck-prompt-staged-tail-20260925.jsonl.gz"
CALIBRATION = FIXTURES / (
    "stuck-prompt-staged-tail-20260925.character-calibration.json"
)
FIXTURE_SHA256 = "e47a45e211b2d7f5e2c98873e3a1c56789f0b597de5be80eacb9169a1f27918a"
BOUNDARIES_SHA256 = (
    "38a0346c0dc9fd9fbbf7e0f60b76f0033bc278633876b72d12ec7f9411bca04c"
)
CALIBRATION_SHA256 = (
    "44cd2ac4e61a12417967cdc1e9c24d306d09ef69a3f994e1611cf5eb54721697"
)
FIRST_LOG_INDEX = 3380
# Indices into ``recorded`` (0 = log index 3380).
LAST_IDENTIFY = 3884  # sequence 7261, identify:pack-pressure 'uqt'
WINDOW = 3909  # sequence 7286, the last dungeon board (return:wait-recall)
SKILL_PROBE = 3910  # sequence 7286 again, the landing's periodic:skill-exp-knowledge
RECOVER = 3911  # sequence 7287, town:recover
STOP = 3912  # sequence 7288, the invariant's approach
STOP_KEY = "\x1b`n%."
STOP_REASON = (
    "town-progress-invariant:defect:town:enchant-launcher-tohit"
    "=>town-progress-invariant:approach"
)
ENCHANT_READ = "rlc"
ENCHANT_GATES = (
    (1, ("どの巻物を読みますか? ", "Read which scroll? ")),
    (2, ("どのアイテムを強化しますか? ", "Enchant which item? ")),
)


class StuckPromptStagedTailRecordedTest(unittest.TestCase):
    replay = None

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == (
            CALIBRATION_SHA256
        )
        boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        assert boundaries["first_log_index"] == FIRST_LOG_INDEX
        assert boundaries["window_start"] == WINDOW
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        cls.attach_skill_knowledge = boundaries["attach_skill_knowledge"]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(boundaries["input_rows"])
        assert len(cls.recorded) == STOP + 1
        assert len(boundaries["input_rows"]) == STOP + 1 - WINDOW
        cls.starts = [0]
        for count in boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    @classmethod
    def _board_lines(cls, index):
        offset = index - WINDOW
        segment = cls.lines[cls.starts[offset] : cls.starts[offset + 1]]
        previous = cls.recorded[index - 1] if index > WINDOW else None
        if previous is not None and previous["key"]:
            # Wall (executor binding): see the module docstring.
            row = json.loads(segment[-1])
            row["_completed_operation_sequence"] = previous["decision_sequence"]
            row["_completed_operation_owner"] = previous["reason"]
            segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
        return segment

    @classmethod
    def _replay(cls):
        """Replay the closing window on one policy; drive the stop's send."""
        if cls.replay is not None:
            return cls.replay
        decisions = {}
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = _policy(directory, cls.monrace)
            policy._character_calibration_path.write_bytes(
                CALIBRATION.read_bytes()
            )
            # Wall (attach skill list): see the module docstring.
            policy.consume_skill_knowledge(cls.attach_skill_knowledge)
            for index in range(WINDOW, STOP + 1):
                _decoded, snapshots = _consume_response_sequence(
                    cls._board_lines(index), policy, lambda _key: True,
                    cls.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                snapshot = snapshots[-1]
                if index == STOP:
                    key, staged = cls._stop_decision(policy, snapshot)
                else:
                    key = policy.validate_read_key(
                        snapshot, policy.choose_key(snapshot)
                    )
                    staged = None
                chain = policy.peek_staged_prompt_chain()
                decisions[index] = {
                    "key": str(key) if key is not None else None,
                    "reason": policy.last_reason,
                    "staged": staged,
                    "chain": chain,
                    "read_key": (getattr(policy, "read_telemetry", None) or {}).get(
                        "key"
                    ),
                }
                if index == STOP:
                    stop = cls._drive_stop_send(policy, snapshot, key, directory)
                    break
                policy.confirm_key_posted(key)
        cls.replay = (decisions, stop)
        return cls.replay

    @classmethod
    def _stop_decision(cls, policy, snapshot):
        """The stop decision under the declared ladder wall."""
        recorded = cls.recorded[STOP]
        staged = []

        def recorded_winning_rung(board):
            # The recorded winning rung's real producer on the recorded board.
            key = policy._town_enchant_launcher_key(board)
            staged.append(policy.peek_staged_prompt_chain())
            return key

        with patch.object(
            policy, "_choose_key_with_latch_capture",
            side_effect=recorded_winning_rung,
        ), patch.object(
            policy, "_town_procurement_progress_key",
            return_value=(recorded["key"], recorded["invariant_progress_action"]),
        ):
            key = policy.validate_read_key(snapshot, policy.choose_key(snapshot))
        return key, staged[0] if staged else None

    @staticmethod
    def _drive_stop_send(policy, snapshot, key, directory):
        """The live sender on the stop decision (the CLI's own function)."""
        received = []

        def send(segment, *, in_store=False, decision=None):
            received.append(segment)
            return SendResult.SENT

        path = directory / "stop-input.jsonl"
        path.write_text("", encoding="utf-8")
        with path.open("r", encoding="utf-8") as stream:
            sent, _line, chain, result = _send_decision_key_with_prompt_chain(
                send, "snapshot-line", key, None, set(),
                policy=policy, shadow_client=FakeControlClient([""]),
                file=stream, deadline=time.monotonic() + 0.05,
                poll_interval=0.005, prompt_japanese=True,
                decision={
                    "sequence": policy._decision_sequence, "turn": snapshot.turn,
                    "reason": policy.last_reason, "key": key,
                    "prompt_owner_handoff": policy.prompt_owner_handoff,
                },
                snapshot=snapshot, posting_contract=PostingContract(),
                in_store=snapshot.store is not None,
            )
        return {
            "sent": sent, "chain": chain, "result": result,
            "received": received,
        }

    # ------------------------------------------------------------ recorded
    def test_recorded_replaced_enchant_chain_held_the_approach(self):
        recorded = self.recorded
        stop = recorded[STOP]
        self.assertEqual(
            (stop["decision_sequence"], stop["turn"], stop["key"], stop["reason"]),
            (7288, 5491561, STOP_KEY, STOP_REASON),
        )
        self.assertEqual((stop["dungeon_id"], stop["level"]), (0, 0))
        # The invariant replaced the enchant rung with its approach; the chain
        # the sender held was the replaced enchant read's.  (The row keeps
        # outcome/posted; stdout names the drop reason:
        # ``<identify:staged-tail-not-posted:key-replaced>``.)
        self.assertEqual(
            (stop["invariant_winning_rung"], stop["invariant_progress_action"]),
            ("town:enchant-launcher-tohit", "town-progress-invariant:approach"),
        )
        self.assertEqual(stop["read_key"], ENCHANT_READ)
        self.assertEqual(
            (stop["staged_chain_outcome"], stop["staged_chain_posted"]),
            ("not-posted", ""),
        )
        self.assertEqual(
            [(recorded[index]["decision_sequence"], recorded[index]["key"],
              recorded[index]["reason"]) for index in (WINDOW, SKILL_PROBE, RECOVER)],
            [(7286, "5", "return:wait-recall"),
             (7286, "~f\x1b", "periodic:skill-exp-knowledge"),
             (7287, "R&\r", "town:recover")],
        )
        # The earlier staged identify chain was fully released on its own
        # decision; the stop's chain is the only one ever left unposted.
        last_identify = recorded[LAST_IDENTIFY]
        self.assertEqual(
            (last_identify["decision_sequence"], last_identify["key"],
             last_identify["reason"], last_identify["staged_chain_outcome"],
             last_identify["staged_chain_posted"]),
            (7261, "uqt", "identify:pack-pressure", "released", "uqt"),
        )
        self.assertEqual(
            [index for index, row in enumerate(recorded)
             if row["staged_chain_outcome"] not in {None, "released"}],
            [STOP],
        )

    # ------------------------------------------------------------ P1
    def test_replay_reproduces_the_window_decisions(self):
        decisions, _stop = self._replay()
        self.assertEqual(
            [(decisions[index]["key"], decisions[index]["reason"])
             for index in range(WINDOW, STOP + 1)],
            [(self.recorded[index]["key"], self.recorded[index]["reason"])
             for index in range(WINDOW, STOP + 1)],
        )

    def test_p1_stop_producer_staged_the_recorded_enchant_chain(self):
        decisions, _stop = self._replay()
        staged = decisions[STOP]["staged"]
        self.assertEqual(
            (staged["owner"], staged["key"], tuple(staged["gates"])),
            ("town:enchant-launcher-tohit", ENCHANT_READ, ENCHANT_GATES),
        )
        self.assertEqual(decisions[STOP]["read_key"], self.recorded[STOP]["read_key"])

    def test_p1_stop_decision_posts_the_approach(self):
        decisions, stop = self._replay()
        # The replaced enchant read's chain does not survive the decision ...
        self.assertIsNone(decisions[STOP]["chain"])
        # ... so the sender posts the approach instead of the designed wait
        # that an idle game never ends.
        self.assertIsNone(stop["chain"])
        self.assertIsNone(stop["result"])
        self.assertIs(stop["sent"], SendResult.SENT)
        self.assertEqual(stop["received"], [STOP_KEY])


if __name__ == "__main__":
    unittest.main()
