"""Recorded pin (issue #77): an outside board releases the posted Home exit.

Live soak 2026-10-19 08:13 (c4-a life-014, Level 22, main 35b1cf2d, capture
20261019-081331-store-leave-key-suppressed, gold 9,982, pack 23/23): after
the Light scrolls were bought the bot travelled Home, left the open page
(row 3680 ``home:scan-incomplete-open-page``), and on the next, outside
board (row 3681, store None, turn 766016 > posted turn 766012) posted ESC
again as ``home:scan-leave-store``.  ``_home_full_knowledge_key`` read the
still-LEAVING visit (``_store_leave_inflight``) as "still in a store", so
the leave stayed in flight across the decision and the driver printed
``<store-leave-key:suppressed>`` (cli.py: in flight before and after the
decision); no key was sent and the run stopped.

Substrate: the recorded raw state rows of decision rows 3666-3675
(tests/extract_home_leave_suppressed_fixture.py) replayed through the public
response path (``_consume_response_sequence``, ``choose_key``,
``confirm_key_posted``) on one fresh policy, with the live argv flags
(cross-area fundraising, in-store shop operations).

DECLARED CONSTRUCTED walls: the ``~f`` skill list of the same capture (state
row 67) on every board, and the fixture's segmentation (``_segments``), which
gives row 3674 the Home page after the composed withdrawal (state row 104)
instead of the outside board the live driver decided on (state row 101).
Under these walls the fresh policy leaves that Home page on 3674 and row
3675 (state row 105, outside, turn 765348 > 765340) is the same shape as
the live row 3681: 35b1cf2d posts ``("\\x1b", "home:scan-leave-store")``
with the leave still in flight.
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import STORE_HOME
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO, LEAVE_STORE_KEY
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / "fixtures/home-leave-suppressed-20261019.json.gz"
SHA256 = "2e5d7cbe1ad1917e68e3b8920e46f3ada4587cd30821e8d410c03108bfd11302"
PIN = 3675


class HomeLeaveSuppressedRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.skill = json.loads(cls.pin["skill_line"])
        assert cls.skill["knowledge"]["category"] == "skill_exp"
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, stop):
        """Replay to decision ``stop``; return (policy, board, inflight)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        policy = _policy(root, self.monrace)
        policy._crossarea_fundraising_enforced = True  # live argv
        policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
        previous = None
        for segment in self.pin["segments"]:
            recorded = segment["decision"]
            lines = segment["lines"]
            if previous is not None and previous["key"]:
                row = json.loads(lines[-1])
                row["_completed_operation_sequence"] = previous["decision_sequence"]
                row["_completed_operation_owner"] = previous["reason"]
                lines = lines[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
            _, boards = _consume_response_sequence(
                lines, policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=root / "knowledge.jsonl")
            board = boards[-1]
            if previous is None:
                policy.prime(board)
            policy.consume_skill_knowledge(
                {**self.skill, "player": {"level": board.player.level}})
            board = policy.with_known_skill_exp(board)
            if recorded["decision_sequence"] == stop:
                return policy, board, policy._store_leave_inflight
            key = policy.choose_key(board)
            policy.confirm_key_posted(key)
            previous = recorded
        raise AssertionError("pinned row not reached")

    def test_captured_rows(self):
        self.assertEqual(
            [(s["decision"]["decision_sequence"], s["decision"]["reason"])
             for s in self.pin["segments"]][-3:],
            [(3673, "home:leave-for-pending-withdraw"),
             (3674, "home:atomic-withdraw"),
             (3675, "town:entrance-step-off:shop:observed-operation-uncomposable")],
        )
        final = self.pin["final"]
        self.assertEqual((final["key"], final["reason"], final["store_type"]),
                         ("\x1b", "home:scan-leave-store", None))
        self.assertEqual(final["store_visit"]["phase"], "leaving")
        self.assertEqual(final["store_visit"]["store_type"], STORE_HOME)
        self.assertLess(final["store_visit"]["posted_turn"], final["turn"])
        self.assertEqual(final["inventory"], {"used": 23, "free": 0})
        self.assertEqual(final["gold"], 9982)

    def test_outside_board_releases_the_posted_home_exit(self):
        policy, board, inflight = self.replay(PIN)
        self.assertIsNone(board.store)
        self.assertIsNotNone(inflight)
        self.assertEqual(inflight[2], STORE_HOME)
        self.assertGreater(board.turn, inflight[1])
        key = policy.choose_key(board)
        # 35b1cf2d: ("\x1b", "home:scan-leave-store") with the leave still in
        # flight, which the driver suppresses.
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        self.assertIsNone(policy._store_leave_inflight)

    def test_control_open_home_page_still_leaves(self):
        # Control: on the recorded Home page of row 3674 (state row 104) an
        # unconfirmed leave still posts the exit, unchanged.
        policy, board, _inflight = self.replay(3674)
        self.assertEqual(board.store.store_type, STORE_HOME)
        policy._store_leave_inflight = (
            policy._decision_sequence, board.turn, STORE_HOME)
        key = policy._home_full_knowledge_key(board)
        self.assertEqual((key, policy.last_reason),
                         (LEAVE_STORE_KEY, "home:scan-leave-store"))
        self.assertIsNotNone(policy._store_leave_inflight)


if __name__ == "__main__":
    unittest.main()
