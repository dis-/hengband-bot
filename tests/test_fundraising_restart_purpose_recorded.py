"""Recorded pin: a bot restart mid mining run leaves the floor, not stops.

Live 2026-10-03 (capture ``autorecover-20261003-045218-ownership-contract-
conflict-fundraising-missing-purpose``; rows copied to
``fixtures/fundraising-restart-missing-purpose-20261003.*``):
- 03:47:04 / 03:48:29 the previous process descended from town to Yeek Cave
  1F (``descend``, mode ``mine``); that is where it created the run purpose
  (``_fundraising_run_purpose``, process memory only).
- 03:49:25 (turn 5957310) its last decision, ``fundraise:seek-loot``; the
  operator killed the process there, the game kept running.
- 04:52:04 the supervisor started a new process (``session-start``,
  ``--enforce-crossarea-fundraising``).  ``prime`` re-adopted mode ``mine``
  from the board, but no purpose or record exists in a fresh policy (incident
  ``policy-state.json``: ``_fundraising_run_purpose`` / ``_purpose_record``
  null).  After the periodic ``~f`` its first fundraising decision was the
  ``missing-purpose`` stop (decision 247), and every resume repeated it.

Substrate: the state lines the new process read (index 112 is the board at
startup, 113-117 the replies to ``~f``).  R4: the replay is compared with the
recorded decisions and ends at the first divergence, the decision fixed here.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "fundraising-restart-missing-purpose-20261003.jsonl.gz"
DECISIONS = FIXTURES / "fundraising-restart-missing-purpose-20261003.decisions.json"
SHA256 = {
    FIXTURE: "740dd0075d4f8a16a2ac9de6fae21861eb2276b340f461bbcf0bc63ed97b263c",
    DECISIONS: "d3e3cc2649901db07b09364484fc3ca4f371b09b5bb0da19911e033c7c72d4d5",
}
STOP = "ownership:contract-conflict:fundraising:missing-purpose"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class FundraisingRestartPurposeRecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = [json.loads(line) for line in stream]
        cls.decisions = {
            row["index"]: row
            for row in json.loads(DECISIONS.read_text(encoding="utf-8"))["rows"]
        }
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._crossarea_fundraising_enforced = True  # live argv

    def test_recorded_rows_are_the_incident(self):
        self.assertEqual(self.decisions[244]["reason"], "fundraise:seek-loot")
        self.assertEqual(self.decisions[245]["kind"], "session-start")
        self.assertTrue(self.decisions[245]["enforce_crossarea_fundraising"])
        self.assertEqual(self.decisions[247]["reason"], STOP)
        self.assertEqual(self.decisions[247]["floor"], [2, 1])
        self.assertEqual(self.decisions[247]["fundraising"]["mode"], "mine")
        self.assertEqual([row["index"] for row in self.rows],
                         [112, 113, 114, 115, 116, 117])

    def test_restarted_mining_run_leaves_the_floor(self):
        policy = self.policy
        startup = parse_snapshot(json.loads(self.rows[0]["line"]), self.monrace)
        policy.prime(startup)
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertIsNone(policy._fundraising_run_purpose)
        self.assertIsNone(policy._fundraising_purpose_record)

        key = policy.choose_key(startup)
        self.assertEqual(
            (key, policy.last_reason),
            (self.decisions[246]["key"], self.decisions[246]["reason"]),
        )
        policy.confirm_key_posted(key)

        _decoded, snapshots = _consume_response_sequence(
            [row["line"] for row in self.rows[1:]],
            policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        board = snapshots[-1]
        self.assertEqual(board.turn, self.decisions[247]["turn"])
        # First divergence from the recorded decision (live: "5", the stop).
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, STOP)
        self.assertNotEqual(key, self.decisions[247]["key"])
        # The fundraising floor exit (1F: walk to the up staircase).
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs-explore")


if __name__ == "__main__":
    unittest.main()
