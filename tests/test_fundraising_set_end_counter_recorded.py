"""Recorded pins: a set ended at the gold target does not carry its run count.

Live 2026-10-02 (one bot process, started 22:09:40; decision rows copied to
``fixtures/fundraising-set-end-counter-20261002.decisions.json``):
- 22:18:37-22:23:36 a mining set ran 5 Yeek Cave 1F trips (decisions 2031,
  2191, 2453, 2837, 2903) and came back at 20,122 gold; the gold-target set end
  cleared the mode, but ``_mining_runs_completed`` stayed 5;
- 22:24:11 (3649) the normal-dive Home visit deposited the treasure detection
  scrolls (``di5``), as decided 2026-09-18 for mining gear off duty;
- 22:34:38 (5072) gold 2,208 started the next set: ``prepare`` with
  ``kit_secured`` false.  The detection target was 5 - 5 = 0, so Home
  withdrew only a digger (5075 ``pC``), left with
  ``home:route-claim-unfulfilled`` (5079), and the exhausted plan turned
  ``prepare`` into ``scavenge`` (5080): Yeek 1F walked without mining.

Substrate: recorded boards of the same character (capture
``autorecover-20261002-061401-loop-detected``, lines 63-67, a town return at
17,342 gold with its ``~f`` and ``~9`` replies; capture
``autorecover-20261002-060052-exit-no-marker``, line 76, the town at 1,264
gold).  DECLARED WALL: before the first board the policy carries the live
state of 22:23:36 -- mode ``mine`` with 5 completed runs.  The set end is
reached through ``choose_key`` (the town decision calls it on every board).
The next set is started with ``_start_fundraising`` on the poor board, and the
requirement is read through ``_procurement_missing_amount``, the gate
``_queue_home_catalogue_shortages`` applies to each Home item.
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
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import MINING_RUNS_PER_SET

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "fundraising-set-end-counter-20261002.jsonl.gz"
DECISIONS = FIXTURES / "fundraising-set-end-counter-20261002.decisions.json"
SHA256 = {
    FIXTURE: "963f514748167ca92ccf309083da46f17150734e065ab4806cb2998b0c1e4a4a",
    DECISIONS: "e9a522d73093698f9dce7b220c4ad7f0a34fc6298f71a576b33738cd52125c1f",
}
LIVE_YEEK_ENTRIES = (2031, 2191, 2453, 2837, 2903)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class FundraisingSetEndCounterRecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = [json.loads(line) for line in stream]
        cls.decisions = {
            row["decision_sequence"]: row
            for row in json.loads(DECISIONS.read_text(encoding="utf-8"))["rows"]
        }
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._crossarea_fundraising_enforced = True  # live argv

    def _feed(self, *indices):
        _decoded, snapshots = _consume_response_sequence(
            [self.rows[index]["line"] for index in indices],
            self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        return snapshots[-1]

    def _decide(self, *indices):
        board = self._feed(*indices)
        key = self.policy.choose_key(board)
        self.policy.confirm_key_posted(key)
        return board

    def _return_at_gold_target_then_poor_town(self):
        # DECLARED WALL: the live process state at 22:23:36 (decision 3622).
        self.policy._fundraising_mode = "mine"
        self.policy._mining_runs_completed = len(LIVE_YEEK_ENTRIES)
        rich = self._decide(0)
        self._decide(1, 2)
        self._decide(3, 4)
        self.assertGreaterEqual(rich.player.gold, 15000)
        self.assertIsNone(self.policy._fundraising_mode)
        poor = self._feed(5)
        self.assertEqual(poor.player.gold, 1264)
        self.assertTrue(self.policy._start_fundraising(poor))
        self.assertEqual(self.policy._fundraising_mode, "prepare")
        return poor

    def test_recorded_rows_are_the_incident(self):
        for sequence in LIVE_YEEK_ENTRIES:
            self.assertEqual(self.decisions[sequence]["floor"], [2, 1])
            self.assertEqual(
                self.decisions[sequence]["fundraising"]["mode"], "mine"
            )
        self.assertEqual(self.decisions[3622]["gold"], 20122)
        self.assertEqual(self.decisions[3649]["key"], "di5\r\x1b")
        start = self.decisions[5072]["fundraising"]
        self.assertEqual((start["mode"], start["kit_secured"]), ("prepare", False))
        self.assertNotIn(
            "Treasure Detection scrolls",
            {row["item"] for row in self.decisions[5072]["procurement_requirements"]},
        )
        self.assertEqual(self.decisions[5079]["reason"], "home:route-claim-unfulfilled")
        self.assertEqual(self.decisions[5080]["fundraising"]["mode"], "scavenge")
        self.assertEqual(self.decisions[5082]["reason"], "fundraise:scavenge")

    def test_gold_target_set_end_restarts_the_run_count(self):
        self._return_at_gold_target_then_poor_town()
        self.assertEqual(self.policy._mining_runs_completed, 0)

    def test_next_set_asks_home_for_the_stored_detection_scrolls(self):
        poor = self._return_at_gold_target_then_poor_town()
        self.assertEqual(
            self.policy._mining_detection_scroll_target(poor), MINING_RUNS_PER_SET
        )
        stored = [
            item for item in self.policy._home_knowledge_items
            if item.is_treasure_detection_scroll
        ]
        self.assertTrue(stored)
        self.assertEqual(
            self.policy._procurement_missing_amount(poor, stored[0]),
            MINING_RUNS_PER_SET,
        )


if __name__ == "__main__":
    unittest.main()
