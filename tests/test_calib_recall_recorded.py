"""D38: the recorded n1-b life-276 calibration drops (viewing server, 2026-10-31).

Live (build b6d47db93): the equipment optimizer reported
``calibration-required-return`` on most decisions of n1-b and n1-a.

Cause 1.  Word of Recall puts ``recall`` (BAR_RECALL) on the status bar;
character_sheet.temporary_bonuses refused it as an unknown timed effect, so
_validated_character_calibration dropped the calibration on every recall
read.  Recorded: decision 18574 (town, turn 744608,
``town:recall-to-alt-dungeon``) still had it (``signature-cache-hit``);
decision 18575 (turn 744615, ``recall`` on the bar) reported
``unknown-timed-effect:recall``.  The game draws BAR_RECALL from
``player_ptr->word_recall`` only (main-window-stat-poster.cpp) and no stat,
AC or HP computation reads it.

Fixture: tests/extract_calib_recall_fixture.py.
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
from hengbot.policy_constants import SKILL_KNOWLEDGE_MACRO

from extraction_calibration import install_extraction_calibration
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
CASE = FIXTURES / "calib-recall-20261031.json.gz"
DUMP = FIXTURES / "calib-recall-20261031.bot-test.txt.gz"
SHA256 = {
    CASE: "91d731b540eeb54889a84afec8c3d254dfd6de108c0ccc2c5773d329ccd41df3",
    DUMP: "3ffb4df05ca0ca741563de8f66df3b56811bfacd862373e7be3611dbb713f83e",
}


class CalibRecallRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
        cls.case = json.loads(gzip.decompress(CASE.read_bytes()).decode("utf-8"))
        cls.dump = gzip.decompress(DUMP.read_bytes())
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.decisions = {row["decision_sequence"]: row for row in cls.case["decisions"]}

    def boards(self, policy, directory, lines):
        _decoded, snapshots = _consume_response_sequence(
            lines, policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl")
        return snapshots

    def read_skill_list(self, policy, directory):
        # The ~f list the same process read on arriving in town (turn 742591).
        policy.confirm_key_posted(SKILL_KNOWLEDGE_MACRO)
        self.boards(policy, directory, [self.case["skill"]])

    def test_recall_on_the_status_bar_keeps_the_calibration(self):
        recorded = self.decisions
        self.assertEqual((recorded[18574]["reason"], recorded[18574]["result_source"]),
                         ("town:recall-to-alt-dungeon", "signature-cache-hit"))
        self.assertEqual((recorded[18575]["result_source"],
                          recorded[18575]["calibration"]["unavailable_reason"]),
                         ("calibration-required-return", "unknown-timed-effect:recall"))
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, self.monrace)
            # The record the process held (same level, max HP, stats and
            # worn set as these boards; stale_reason below checks it).
            policy._character_calibration_path.write_text(
                json.dumps(self.case["record"]), encoding="utf-8")
            calibration = install_extraction_calibration(policy)
            policy._calibration_session_id = calibration.session_id
            self.read_skill_list(policy, directory)
            before, recall, after = self.boards(policy, directory, self.case["town"])
            self.assertIsNone(calibration.stale_reason(
                before.player, policy._current_pinned_identities(before),
                mutation_signature=policy._mutation_signature))
            self.assertEqual(tuple(recall.player.status_bar), ("recall",))
            for board in (before, recall, after):
                policy.choose_key(board)
                state = policy.equipment_optimization_state(board)
                self.assertIs(policy._character_calibration, calibration, board.turn)
                self.assertIsNone(state["calibration"]["unavailable_reason"], board.turn)
                self.assertNotEqual(state["result_source"], "calibration-required-return",
                                    board.turn)


if __name__ == "__main__":
    unittest.main()
