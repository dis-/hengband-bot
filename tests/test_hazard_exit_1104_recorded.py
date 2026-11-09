"""Leaving damaging ground first (owner 2026-11-04 「先に出る」), on n1-a life-478's boards.

Recorded: tests/extract_hazard_exit_1104_fixture.py.  The skill-exp cache is DECLARED
CONSTRUCTED from the board's level; the immunity, levitation and invulnerability controls
are DECLARED CONSTRUCTED on the recorded board, and so is the shallow board, whose deep acid
(231) is relabelled shallow acid (232) in the grid map's palette.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import damaging_ground
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "hazard-exit-1104.json.gz"
STEP_REASON = "hazard:step-off"
STEP_TO_9_165 = "1"
DEEP_ACID, SHALLOW_ACID = 231, 232  # lib/edit/TerrainDefinitions.jsonc


class HazardExit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def decide(self, raw, before=()):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.monrace))
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], None)
        for board in (*before, raw):
            key = policy.choose_key(
                policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(board), self.monrace)))
            if board is not raw and key:
                policy.confirm_key_posted(key)
        self.last_policy = policy
        return key, policy.last_reason

    def test_a_shot_and_a_quaff_become_the_step_to_the_adjacent_floor(self):
        # Recorded: ('fq*t5', 'ranged:fire-target').
        before = (self.boards["before_shot"],)  # the player came from (7,165)
        self.assertEqual(self.decide(self.boards["shot"], before), (STEP_TO_9_165, STEP_REASON))
        # Recorded later on this cell at HP 71: ('qb', 'item:strong-fight-speed').  A chooser
        # primed on one board reads Teleport there, and a read stays, so the rule is asked.
        policy = self.last_policy
        board = parse_snapshot(copy.deepcopy(self.boards["speed_low_hp"]), self.monrace)
        self.assertEqual(damaging_ground.step_off_key(policy, board, "qb"), STEP_TO_9_165)
        self.assertIsNone(damaging_ground.step_off_key(policy, board, "re"))

    def test_a_rest_walks_on_while_a_quaff_stays_without_an_adjacent_safe_cell(self):
        key, reason = self.decide(self.boards["rest_deep"])
        self.assertEqual(reason, STEP_REASON)  # Recorded: ('R&\r', 'rest').
        self.assertEqual(self.decide(self.boards["heal_deep"]), ("qe", "item:heal"))

    def test_immunity_and_invulnerability_keep_the_shot(self):
        immune = copy.deepcopy(self.boards["shot"])
        immune["player"]["immunities"]["acid"]["permanent"] = True
        self.assertTrue(self.decide(immune)[0].startswith("f"))
        invulnerable = copy.deepcopy(self.boards["shot"])
        invulnerable["player"]["status_bar"] = [{"key": "invulnerability"}]
        self.assertTrue(self.decide(invulnerable)[0].startswith("f"))

    def test_levitation_still_leaves_deep_acid(self):
        # deal_damege_by_feat (hp-mp-processor.cpp): DEEP ground deals a fifth of its
        # damage to a levitating player, so the shot is still the step off.
        floating = copy.deepcopy(self.boards["shot"])
        floating["player"]["ability_sources"]["levitation"]["temporary"] = True
        before = (self.boards["before_shot"],)
        self.assertEqual(self.decide(floating, before), (STEP_TO_9_165, STEP_REASON))

    def test_levitation_keeps_the_shot_over_shallow_acid(self):
        shallow = copy.deepcopy(self.boards["shot"])
        palette = shallow["grid_map"]["palette"]
        self.assertEqual(sum(entry[0] == DEEP_ACID for entry in palette), 1)
        for entry in palette:
            if entry[0] == DEEP_ACID:
                entry[0] = SHALLOW_ACID
        before = (self.boards["before_shot"],)
        # Standing in it hurts: the step off, as on deep acid.
        self.assertEqual(self.decide(shallow, before), (STEP_TO_9_165, STEP_REASON))
        floating = copy.deepcopy(shallow)
        floating["player"]["ability_sources"]["levitation"]["temporary"] = True
        self.assertTrue(self.decide(floating, before)[0].startswith("f"))


if __name__ == "__main__":
    unittest.main()
