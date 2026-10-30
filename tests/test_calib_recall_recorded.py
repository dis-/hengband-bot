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

Cause 2 (the "dump that does not rebuild").  Outside town the optimizer
returns early and republishes its last town ``result_source``
(``search_telemetry_freshness`` ``stale-republished``), and the calibration
telemetry printed ``unavailable_reason`` None both when the calibration was
present and when it was missing.  Recorded: the periodic dump of decision
20170 (turn 758093) rebuilt the calibration (it wrote the frozen record),
while decision 20171 still read ``calibration-required-return`` with
reason None.  The telemetry now says whether the calibration is present and
names the state of a missing one.

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
from hengbot.policy_constants import CHARACTER_DUMP_MACRO, SKILL_KNOWLEDGE_MACRO
from hengbot.warrior_optimization import load_character_calibration

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

    def test_dungeon_dump_rebuilds_and_the_telemetry_says_so(self):
        recorded = self.decisions
        self.assertEqual((recorded[20170]["reason"], recorded[20170]["key"]),
                         ("periodic:character-dump", CHARACTER_DUMP_MACRO))
        # Recorded after the dump: the stale town result and no reason.
        self.assertEqual((recorded[20171]["result_source"],
                          recorded[20171]["search_telemetry_freshness"],
                          recorded[20171]["calibration"]["unavailable_reason"]),
                         ("calibration-required-return", "stale-republished", None))
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            # A fresh process: the calibration file holds another session's record.
            policy = _policy(directory, self.monrace)
            policy._character_dump_path = directory / "bot-test.txt"
            self.read_skill_list(policy, directory)
            (board,) = self.boards(policy, directory, self.case["dump"][:1])
            missing = policy.equipment_optimization_state(board)["calibration"]
            self.assertIs(missing.get("present"), False)
            self.assertIsNotNone(missing["unavailable_reason"])
            # Decision 20170 posted the recorded dump macro on this board (a
            # fresh policy lacks the live floor memory that made it a filler).
            policy._prepare_character_sheet_dump()
            # The game writes the dump while the posted macro runs.
            policy._character_dump_path.write_bytes(self.dump)
            policy.confirm_key_posted(CHARACTER_DUMP_MACRO)
            pending = policy.equipment_optimization_state(board)["calibration"]
            self.assertEqual((pending.get("present"), pending["pending"],
                              pending["unavailable_reason"]),
                             (False, True, "dump-pending"))
            (after,) = self.boards(policy, directory, self.case["dump"][1:])
            policy.choose_key(after)
            state = policy.equipment_optimization_state(after)
            calibration = policy._character_calibration
            self.assertIsNotNone(calibration, policy._calibration_unavailable_reason)
            self.assertIs(state["calibration"].get("present"), True)
            self.assertIsNone(state["calibration"]["unavailable_reason"])
            frozen = load_character_calibration(policy._character_calibration_path)
            record = self.case["record"]
            self.assertEqual(frozen.observed_turn, record["observed_turn"])
            for name in ("natural_stats", "intrinsic_adjustments", "visible_stat_key"):
                self.assertEqual(list(getattr(calibration, name)), record[name], name)
            self.assertEqual((calibration.base_hp, calibration.base_ac_bonus, calibration.level),
                             (record["base_hp"], record["base_ac_bonus"], record["level"]))


if __name__ == "__main__":
    unittest.main()
