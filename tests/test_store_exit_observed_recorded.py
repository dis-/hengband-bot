"""D34: an outside board ends the posted store exit (store-leave-key-suppressed).

Viewing bot n1-b life-254 (Warrior Lv23, 2026-10-30 09:17-09:19, build
62ae6c65): Home was entered and left again (``home:queue-digging-tool-withdraw``
ESC on the Home page, decision 30, posted turn 577750).  On the next, outside
board (decision 31, store None, turn 577752) the Home errand's knowledge exit
``_home_errand_knowledge_key`` read the still-LEAVING visit
(``_store_leave_inflight``) as "still in a store" and returned ESC again
(``home-errand:leave-for-knowledge:identification-catalog``).  The leave was
in flight before and after the decision, so the driver printed
``<store-leave-key:suppressed>``, posted nothing and stopped; three restarts
stopped the same way.  Cross-town travel (``town:cross-town-shopping:travel-N``
right after ``shop:in-store-done``) stopped the same way on n1-a life-428/434
and n1-b life-251/256; issue #77 was a third producer of the shape.
Leaving a store spends the player's turn (cmd-store.cpp ``do_cmd_store``), so
an outside board with a later turn is the exit's effect.

Substrate: the recorded raw state lines of the whole last bot session
(tests/extract_d34_session_fixtures.py store-exit) replayed through the public
response path on one fresh policy with the live argv flags, and the chosen
key posted through the production executor port with the driver's own
suppression rule (cli.py: leave in flight before and after the decision).

DECLARED CONSTRUCTED wall: the fresh policy has none of the live runtime
files (calibration, Home histories), so from row 14 it takes a different but
equivalent Home route (``home:leave-for-pending-withdraw`` instead of
``home:queue-digging-tool-withdraw``); row 28 (outside, turn 577737 > the
posted exit's 577726) is then the live row 31 shape.
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import time
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import STORE_HOME
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
from recorded_session_replay import replay_session
from test_esp_threat_rest_recorded import EDIT
import tests.test_input_executor as executor_harness

FIXTURE = Path(__file__).parent / "fixtures/store-exit-observed-20261030.json.gz"
SHA256 = "a48dede3911b85ac50d60073bfd4436b8ffc4657b702fc32f31fc58982dcdb42"
PIN = 28


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
                         (31, "\x1b", "home-errand:leave-for-knowledge:identification-catalog",
                          None))
        self.assertEqual(final["store_visit"]["phase"], "leaving")
        self.assertEqual(final["store_visit"]["store_type"], STORE_HOME)
        self.assertLess(final["store_visit"]["posted_turn"], final["turn"])
        self.assertEqual(self.pin["stdout_tail"], "<store-leave-key:suppressed>")

    def test_outside_board_after_the_exit_posts_its_key(self):
        decided = []
        for policy, board, recorded in self.replay():
            inflight = policy._store_leave_inflight
            key = policy.choose_key(board)
            if recorded["decision_sequence"] == PIN:
                self.assertIsNone(board.store)
                self.assertEqual(inflight[2], STORE_HOME)
                self.assertGreater(board.turn, inflight[1])
                self.assertEqual(policy.last_reason,
                                 "home-errand:leave-for-knowledge:identification-catalog")
                # 1e64843c: the leave stays in flight across the decision and
                # the driver suppresses the key (nothing posted, run stops).
                self.assertIsNone(policy._store_leave_inflight)
                game, sent = self.post(board, key, policy.last_reason, suppress=(
                    inflight is not None and policy._store_leave_inflight is not None))
                self.assertTrue(sent)
                self.assertEqual(game.accepted, [key])
            policy.confirm_key_posted(key)
            decided.append((recorded["decision_sequence"], key, policy.last_reason))
            if recorded["decision_sequence"] == PIN + 1:
                break
        # The following board resumes the errand's knowledge request.
        self.assertEqual(decided[-1][1:], (
            HOME_KNOWLEDGE_MACRO, "home-errand:request-knowledge:identification-catalog"))

    def test_control_store_board_still_waits_for_its_exit(self):
        # Control: the Home page of row 27 arms the leave; a decision on that
        # same in-store board keeps it in flight (the stale-board suppression).
        for policy, board, recorded in self.replay():
            key = policy.choose_key(board)
            policy.confirm_key_posted(key)
            if recorded["decision_sequence"] == PIN - 1:
                self.assertEqual(board.store.store_type, STORE_HOME)
                self.assertIsNotNone(policy._store_leave_inflight)
                policy.choose_key(board)
                self.assertIsNotNone(policy._store_leave_inflight)
                return
        self.fail("pinned row not reached")


if __name__ == "__main__":
    import unittest
    unittest.main()
