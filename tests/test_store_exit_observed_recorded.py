"""D34: an outside board ends the posted store exit (store-leave-key-suppressed).

Viewing bot n1-b life-256 (2026-10-30 12:25): in Telmora the bot left the
Alchemist (decision 3623, ``town-progress-invariant:continue-observed-shop``
ESC, posted turn 1234423).  On the next, outside board (decision 3624, store
None, turn 1234433) cross-town shopping returned its travel step ``9``
(``town:cross-town-shopping:travel-2``) before the inflight-leave branch of
``_choose_key`` could release the still-LEAVING visit.  The leave was in
flight before and after the decision, so the driver printed
``<store-leave-key:suppressed>``, posted nothing and stopped.  n1-a life-428
and 434 and n1-b life-251 stopped the same way; the Home errand's knowledge
exit (``home-errand:leave-for-knowledge:*``, n1-a 420/430/433, n1-b 254 x3)
and issue #77 were other producers of the shape.  Leaving a store spends
the player's turn (cmd-store.cpp ``do_cmd_store``), so an outside board with
a later turn is the exit's effect.

Substrate: the recorded raw state lines of the session tail
(tests/extract_d34_session_fixtures.py store-exit) replayed through the public
response path on one fresh policy with the live argv flags; the replay
reproduces the recorded key and reason of decisions 3621-3624.  The chosen
key is posted through the production executor port with the driver's own
suppression rule (cli.py: leave in flight before and after the decision).
DECLARED CONSTRUCTED: the command loop's reply to the posted key.
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import time
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.monrace_knowledge import load_monrace_knowledge
from recorded_session_replay import replay_session
from test_esp_threat_rest_recorded import EDIT
import tests.test_input_executor as executor_harness

FIXTURE = Path(__file__).parent / "fixtures/store-exit-observed-20261030.json.gz"
SHA256 = "c9637127a7098f24cbf217e78c19be72c372a47641341ebc1f0eceb696865f0d"
PIN = 3624
STORE_ALCHEMIST = 5


class StoreExitObservedRecordedTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self):
        return replay_session(self, self.pin, self.monrace)

    def post(self, board, key, reason, *, suppress):
        raw = json.loads(self.pin["lines"][-1])
        game = executor_harness.FaithfulHookGame()
        game.state = raw
        game.screen = executor_harness.command_screen(board.turn)
        # DECLARED CONSTRUCTED: the command loop's reply to the posted key.
        game.screens = [executor_harness.command_screen(board.turn)]
        game.states = [dict(raw, turn=board.turn)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome,
                         "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False, suppress=suppress,
            decision={"sequence": PIN, "reason": reason}, snapshot=board,
            posting_contract=PostingContract())
        return game, sent

    def test_recorded_stop(self):
        final = self.pin["final"]
        self.assertEqual((final["decision_sequence"], final["key"], final["reason"],
                          final["store_type"]),
                         (PIN, "9", "town:cross-town-shopping:travel-2", None))
        self.assertEqual(final["store_visit"]["phase"], "leaving")
        self.assertEqual(final["store_visit"]["store_type"], STORE_ALCHEMIST)
        self.assertLess(final["store_visit"]["posted_turn"], final["turn"])
        self.assertEqual(self.pin["stdout_tail"], "<store-leave-key:suppressed>")

    def test_outside_board_after_the_exit_posts_its_key(self):
        for policy, board, recorded in self.replay():
            inflight = policy._store_leave_inflight
            key = policy.choose_key(board)
            if recorded["decision_sequence"] == PIN:
                break
            policy.confirm_key_posted(key)
        else:
            self.fail("pinned row not reached")
        self.assertIsNone(board.store)
        self.assertEqual(inflight[2], STORE_ALCHEMIST)
        self.assertGreater(board.turn, inflight[1])
        self.assertEqual((key, policy.last_reason), ("9", "town:cross-town-shopping:travel-2"))
        # Before the fix the leave stays in flight across the decision and
        # the driver suppresses the key (nothing posted, run stops).
        self.assertIsNone(policy._store_leave_inflight)
        game, sent = self.post(board, key, policy.last_reason, suppress=(
            inflight is not None and policy._store_leave_inflight is not None))
        self.assertTrue(sent)
        self.assertEqual(game.accepted, [key])

    def test_control_store_board_keeps_its_exit_in_flight(self):
        # Control: the Alchemist page of decision 3623 arms the leave; that
        # in-store board is not the exit's effect, so the release keeps it.
        for policy, board, recorded in self.replay():
            key = policy.choose_key(board)
            policy.confirm_key_posted(key)
            if recorded["decision_sequence"] == PIN - 1:
                self.assertEqual(board.store.store_type, STORE_ALCHEMIST)
                self.assertEqual((key, policy.last_reason),
                                 ("", "town-progress-invariant:continue-observed-shop"))
                self.assertIsNotNone(policy._store_leave_inflight)
                policy._release_observed_store_exit(board)
                self.assertIsNotNone(policy._store_leave_inflight)
                return
        self.fail("pinned row not reached")


if __name__ == "__main__":
    import unittest
    unittest.main()
