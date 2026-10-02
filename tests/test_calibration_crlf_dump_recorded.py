"""Recorded pin: the live equipped C-sheet dump yields a calibration.

Live 2026-10-02 (commit 35a18252 lineage): every periodic dump since the
equipped C-sheet calibration landed was refused (decision rows'
``equipment_optimization.calibration.unavailable_reason`` =
``dump-equipment-mismatch`` from 15:12 to the 17:00 stop), so the equipment
optimizer never ran (``result_source`` ``calibration-required-return``) and
the Home 耐混乱の指輪 (tval 45, sval 43, known flag 57) was never worn.  The
21F recall landing then failed its depth gate (missing resist_conf) and the
bot stopped in town.

Two defects, both on this recorded input
(tests/extract_calibration_crlf_dump_fixture.py):
1. character_sheet.py: the game writes the dump with CRLF; the slot-name
   regex kept the ``\\r`` so no worn name matched -> dump-equipment-mismatch.
2. policy_calibration.py: choose_key completes the dump on its raw board,
   before it fills the protocol-3 ~f skill_exp -> skill-exp-unknown.

The second test replays the 17:01 town board (town-blackmarket-stall fixture)
on the policy that acquired this calibration: the optimizer plans to wear
耐混乱の指輪 (and keeps the gate's other leaves), and board 2 becomes the Home
equipment trip instead of the live Black Market approach.  That key differs
from live, so the pin stops there (R4).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import CHARACTER_DUMP_MACRO, SKILL_KNOWLEDGE_MACRO
from hengbot.policy_constants import required_depth_gates

from test_esp_threat_rest_recorded import _policy
import test_town_blackmarket_stall_recorded as stall_pin

FIXTURES = Path(__file__).parent / "fixtures"
ROWS = FIXTURES / "calibration-crlf-dump-20261002.jsonl.gz"
DUMP = FIXTURES / "calibration-crlf-dump-20261002.bot-test.txt.gz"
SHA256 = {
    ROWS: "6a700fc4c6458a5659602d5ee789d45daac3c3530a215c8cd5823ebc3c938daf",
    DUMP: "7210322a1434099cf54499125af7392883b3cc5494e0a2110dd1a2f4b0fb4be3",
}
RESIST_CONF_FLAG = 57
FIRST_CHANGED = 2


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _acquire_calibration(policy, directory: Path, monrace):
    """Drive the live dump path: ~f, C macro posted, file written, C reply, board."""
    with gzip.open(ROWS, "rt", encoding="utf-8") as stream:
        skill, character, board = stream.read().splitlines(keepends=True)
    dump = gzip.decompress(DUMP.read_bytes())
    assert b"\r\n" in dump  # the game's own line ends
    policy._character_dump_path = directory / "bot-test.txt"
    policy.confirm_key_posted(SKILL_KNOWLEDGE_MACRO)
    _consume_response_sequence([skill], policy, lambda _key: True, monrace,
                               knowledge_ledger_path=directory / "knowledge.jsonl")
    policy._prepare_character_sheet_dump()
    policy._character_dump_path.write_bytes(dump)
    policy.confirm_key_posted(CHARACTER_DUMP_MACRO)
    _decoded, snapshots = _consume_response_sequence(
        [character, board], policy, lambda _key: True, monrace,
        knowledge_ledger_path=directory / "knowledge.jsonl")
    policy.choose_key(snapshots[-1])


class CalibrationCrlfDumpRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        Stall = stall_pin.TownBlackMarketStallRecordedTest
        Stall.setUpClass()
        cls.stall = Stall()
        cls.monrace = Stall.monrace

    def test_live_dump_yields_the_equipped_calibration(self):
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, self.monrace)
            _acquire_calibration(policy, directory, self.monrace)
            self.assertIsNone(policy._calibration_unavailable_reason)
            calibration = policy._character_calibration
            self.assertIsNotNone(calibration)
            self.assertEqual(calibration.source, "equipped-c-screen")
            self.assertEqual(calibration.stat_cur, (84, 15, 18, 61, 62, 12))
            self.assertEqual(calibration.base_hp, 429)
            self.assertEqual(calibration.base_ac_bonus, 0)

    def test_town_optimizer_plans_the_home_resist_confusion_ring(self):
        seen = {}
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, self.monrace)
            policy._character_calibration_path.write_bytes(
                (FIXTURES / "town-blackmarket-stall-20261002.character-calibration.json")
                .read_bytes())
            policy._crossarea_fundraising_enforced = True  # live argv
            _acquire_calibration(policy, directory, self.monrace)
            rows = []
            for index in range(FIRST_CHANGED + 1):
                _decoded, snapshots = _consume_response_sequence(
                    self.stall.segments[index], policy, lambda _key: True,
                    self.monrace, knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                board = snapshots[-1]
                key = policy.choose_key(board)
                rows.append((str(key), policy.last_reason))
                if index == FIRST_CHANGED:
                    seen["board"] = board
                    seen["preparation"] = policy._equipment_optimization_preparation
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain(
                        {"outcome": "released", "posted": str(key)})
        for index in range(FIRST_CHANGED):
            self.assertEqual(rows[index], self.stall._live(index), index)
        preparation = seen["preparation"]
        self.assertEqual(preparation.blockers, ())
        target = preparation.result.best.loadout
        rings = {slot: owned.item.name for slot, owned in target.slots
                 if slot in {"main_ring", "sub_ring"}}
        self.assertIn("耐混乱の指輪", rings.values())
        self.assertIn(RESIST_CONF_FLAG, target.flags)
        # The worn board misses exactly resist_conf for the 21F landing.
        board = seen["board"]
        self.assertIn("resist_conf", required_depth_gates(21))
        self.assertNotIn("resist_conf", board.player.abilities)
        self.assertEqual(self.stall._live(FIRST_CHANGED), ("9", "shop:approach"))
        self.assertEqual(rows[FIRST_CHANGED],
                         ("\x1b`n(.", "equipment-transaction:travel-home"))


if __name__ == "__main__":
    unittest.main()
