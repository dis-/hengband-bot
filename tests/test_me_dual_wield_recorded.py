"""#47: the Magic-Eater dual wields with a to-hit that misses (n1-c, 2026-11-01).

Owner 2026-11-01: 「あたりもしない二刀流を使っていることを改善するべき。」

Root 1 (life-077, build 577cd246b): the Q34 lantern is worn unidentified,
sensed {average} (owner 2026-10-31 「並なら付けて良い」).  The calibration
(character_sheet.derive_equipped_calibration) refused every C screen with any
unidentified worn item ("equipment-stat-modifiers-unknown"), so the optimizer
returned calibration-required for the whole life and never replaced the
Main Gauche / broken dagger dual wield (dump: to-hit -63 / -58) with the
Long Sword (2d5) (+5,+1) carried.  The recorded periodic dump of turn 440550
is replayed through the CLI's response consumer and the public chooser.

DECLARED RECONSTRUCTED: the staff sequence's power-list read of the process
(as in test_me_town_stops_recorded).
DECLARED CONSTRUCTED: the control boards with the lantern unsensed.

Fixture: tests/extract_me_dual_wield_fixture.py.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_staff_sequence
from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import CHARACTER_DUMP_MACRO, SKILL_KNOWLEDGE_MACRO
from tests import test_input_executor as harness

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
CASE = FIXTURES / "me-dual-wield-20261101.json.gz"
DUMP = FIXTURES / "me-dual-wield-20261101.bot-test2.txt.gz"
SHA256 = {
    CASE: "3ff7b55caa388f2e2ac874273888aadc7c35d804c83505eb92d1cbba2044ba91",
    DUMP: "3266396b27e990fe9417a64a95e23fe470df46c5ca4fb97d5a989f5333bc5c63",
}
HOME_KNOWLEDGE_MACRO = "~9\x1b\x1b"
LONG_SWORD, MAIN_GAUCHE, BROKEN_DAGGER = "ロング・ソード", "マン・ゴーシュ", "折れたダガー"


def hands(raw):
    return {item["slot"]: item["name"] for item in raw["equipment"]
            if item["slot"] in ("main_hand", "sub_hand")}


class MagicEaterDualWieldRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
        cls.case = json.loads(gzip.decompress(CASE.read_bytes()).decode("utf-8"))
        cls.dump = gzip.decompress(DUMP.read_bytes())
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def consume(self, policy, directory, lines):
        _decoded, snapshots = _consume_response_sequence(
            lines, policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl")
        return snapshots

    # -- root 1: the worn {average} light and the calibration ---------------

    def dumped(self, directory, edit=None):
        """The life-077 process at the recorded dump, through the dump's board."""
        life = dict(self.case["life077"])
        if edit is not None:
            for name in ("before_dump", "after_dump"):
                board = json.loads(life[name])
                edit(board)
                life[name] = json.dumps(board, ensure_ascii=False)
        policy = _policy(directory, self.monrace)
        policy._character_calibration_path.unlink()  # a fresh life: no record
        policy._character_dump_path = directory / "bot_test2.txt"
        self.consume(policy, directory, [life["town"]])
        policy.confirm_key_posted(SKILL_KNOWLEDGE_MACRO)
        self.consume(policy, directory, [life["skill"]])
        policy.confirm_key_posted(HOME_KNOWLEDGE_MACRO)
        self.consume(policy, directory, [life["home"]])
        self.consume(policy, directory, [life["before_dump"]])
        # The recorded decision 1316 posted the periodic dump on this board.
        policy._prepare_character_sheet_dump()
        policy._character_dump_path.write_bytes(self.dump)  # the game writes it
        policy.confirm_key_posted(CHARACTER_DUMP_MACRO)
        (after,) = self.consume(policy, directory, [life["character"], life["after_dump"]])
        # DECLARED RECONSTRUCTED: this process had read the staff power list.
        me_staff_sequence.state(policy).powers_read = True
        policy.choose_key(after)
        return policy, after

    def test_capture_pins_the_recorded_dual_wield(self):
        life = self.case["life077"]
        rows = {row["decision_sequence"]: row for row in life["decisions"]}
        self.assertEqual((rows[1316]["reason"], rows[1316]["key"]),
                         ("periodic:character-dump", CHARACTER_DUMP_MACRO))
        self.assertEqual(rows[1317]["calibration"]["unavailable_reason"],
                         "equipment-stat-modifiers-unknown")
        board = json.loads(life["before_dump"])
        self.assertEqual({slot: name.split(" ")[0] for slot, name in hands(board).items()},
                         {"main_hand": MAIN_GAUCHE, "sub_hand": BROKEN_DAGGER})
        light = next(item for item in board["equipment"] if item["slot"] == "light")
        self.assertEqual((light["known"], light["pseudo_feeling"], light["inscription"]),
                         (False, "average", "Q34"))
        self.assertTrue(any(item["name"].startswith(LONG_SWORD) for item in board["inventory"]))
        sheet = self.dump.decode("euc-jp")
        self.assertIn("(-63,+3)", sheet)
        self.assertIn("(-58,+1)", sheet)

    def test_worn_average_light_keeps_the_calibration_and_the_long_sword_wins(self):
        with TemporaryDirectory() as raw:
            policy, after = self.dumped(Path(raw))
            self.assertIsNotNone(policy._character_calibration,
                                 policy._calibration_unavailable_reason)
            state = policy.equipment_optimization_state(policy.with_known_skill_exp(after))
            self.assertIs(state["calibration"]["present"], True)
            self.assertNotEqual(state["result_source"], "calibration-required-return")
            best = policy._equipment_optimization_preparation.result.best.loadout
            self.assertTrue(best.item_at("main_hand").item.name.startswith(LONG_SWORD))
            self.assertIsNone(best.item_at("sub_hand"))

    def test_control_unsensed_worn_light_still_refuses_the_calibration(self):
        # DECLARED CONSTRUCTED: the dump's boards with the lantern unsensed.
        def unsensed(board):
            light = next(item for item in board["equipment"] if item["slot"] == "light")
            light.pop("pseudo_feeling")
        with TemporaryDirectory() as raw:
            policy, _after = self.dumped(Path(raw), unsensed)
            self.assertIsNone(policy._character_calibration)
            self.assertEqual(policy._calibration_unavailable_reason,
                             "equipment-stat-modifiers-unknown")


if __name__ == "__main__":
    unittest.main()
