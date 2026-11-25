"""No guardian or strong unique is sought out while the finale is prepared (owner 2026-11-26).

Owner 2026-11-26 (verbatim), the answer to 「決戦の準備中（体力回復と*体力回復*を集めている間）の
n1-c の戦い方をどう変えますか？」: 「守護者は追わないが、薬は今まで通り使う」
(finale_prep ``forbids_hunting``).

Recorded: n1-c life-222 (Zombie Magic-Eater Lv49, Angband recall depth 99 after Oberon), back from
the 99F expedition with its 30 Potions of Healing in the pack: on the town board of 2026-11-26
01:13:26 the conquest target (policy_quest ``_conquest_target``) took the Castle over Angband; the
character recalled to the Castle 65F again and again, chased 『カロン』 and 皇帝『レイザーク』
(race 882, the Castle's guardian) under ``hunt:detected-target`` and, at 01:27:45, swept the
kill's floor under ``conquest:*`` -- owned Healing 33 -> 17.  The board kept is the 65F one of
01:27:32 (decision 27419, ``hunt:detected-target``, the Vorpal Blade wielded, Reizark detected;
tests/fixtures/n1c-222-finale-prep-no-guardian-1126.json.gz,
tests/extract_n1c_222_finale_prep_no_guardian_1126_fixture.py) with the same life's absorbed power
lists of 2026-11-25 (tests/fixtures/n1c-222-me-lists-1125.json).

DECLARED CONSTRUCTED: the gate turned off (``forbids_hunting`` patched to False) shows the board
picks the Castle's conquest as the live run did; ``_target_dungeon_id`` set to the Castle stands
for a target another owner (the finale funds' dive, finale_bm_tour ``DIVE_REASON``) chose; the
Angband recall depth lowered to 94 is a character not preparing the finale.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_finale, finale_prep, hunt_target
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1c-222-finale-prep-no-guardian-1126.json.gz", "rt",
               encoding="utf-8") as _stream:
    BOARDS = json.load(_stream)
LISTS = json.loads((FIXTURES / "n1c-222-me-lists-1125.json").read_text(encoding="utf-8"))["lists"]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
CASTLE = 12
REIZARK = 882
GUARDIAN_FLOOR = 65


class FinalePrepNoGuardian1126RecordedTest(unittest.TestCase):
    def castle(self, *, angband_depth=None):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        raw = copy.deepcopy(BOARDS["castle"])
        if angband_depth is not None:
            raw["progress"]["dungeon_recall_depths"]["1"] = angband_depth  # DECLARED CONSTRUCTED
        policy = _policy(Path(scratch.name), MONRACE)
        board = parse_snapshot(copy.deepcopy(raw), MONRACE)
        policy.prime(board)
        for kind in ("staff", "wand", "rod"):
            listed = dict(copy.deepcopy(raw), turn=raw["turn"] - 1,
                          _magic_eater_power_list={"kind": kind, "rows": LISTS[kind]})
            observe_lists(policy, parse_snapshot(listed, MONRACE))
        return policy, board

    def test_the_recorded_board(self):
        policy, board = self.castle()
        self.assertEqual(board.floor_key[:2], (CASTLE, GUARDIAN_FLOOR))
        self.assertNotIn(CASTLE, board.conquered_dungeon_ids)
        self.assertIn(REIZARK, {monster.race_id for monster in board.detected_monsters})
        self.assertTrue(angband_finale.preparing(board))
        self.assertTrue(finale_prep.forbids_hunting(policy, board))

    def test_the_live_conquest_without_the_gate(self):
        policy, board = self.castle()
        with mock.patch.object(finale_prep, "forbids_hunting", lambda *_args: False):
            self.assertEqual(policy._conquest_target(board), CASTLE)
            policy._target_dungeon_id = CASTLE
            self.assertEqual(policy._target_guardian_floor_id(board), REIZARK)
            self.assertEqual(hunt_target.target_race(policy, board), REIZARK)
            self.assertFalse(policy._guardian_floor_blocked(board, CASTLE, GUARDIAN_FLOOR))

    def test_no_conquest_while_the_finale_is_prepared(self):
        policy, board = self.castle()
        policy._conquest_committed = CASTLE  # the live latch of 01:13:26

        # Before: the Castle (the conquest that took it over Angband).
        self.assertIsNone(policy._conquest_target(board))
        self.assertIsNone(policy._conquest_committed)

    def test_no_guardian_hunt_on_a_target_s_guardian_floor(self):
        policy, board = self.castle()
        policy._target_dungeon_id = CASTLE  # DECLARED CONSTRUCTED: the funds dive's target

        # Before: Reizark, hunted under hunt:detected-target and fought by the guardian rung.
        self.assertIsNone(policy._target_guardian_floor_id(board))
        self.assertIsNone(hunt_target.target_race(policy, board))
        self.assertFalse(policy._viable_target_guardian_visible(board, board.detected_monsters))
        # Before: open (the kit beats Reizark), so the descent went down onto it.
        self.assertTrue(policy._guardian_floor_blocked(board, CASTLE, GUARDIAN_FLOOR))
        self.assertFalse(policy._guardian_floor_blocked(board, CASTLE, GUARDIAN_FLOOR - 1))

    def test_a_character_not_preparing_the_finale_still_conquers(self):
        policy, board = self.castle(angband_depth=94)
        self.assertFalse(angband_finale.preparing(board))
        self.assertFalse(finale_prep.forbids_hunting(policy, board))

        self.assertEqual(policy._conquest_target(board), CASTLE)
        policy._target_dungeon_id = CASTLE
        self.assertEqual(policy._target_guardian_floor_id(board), REIZARK)

    def test_the_expedition_is_not_held(self):
        policy, board = self.castle()
        finale_prep.phase(policy).lifted = True  # the cap lifted: the 99F/100F battle's own

        self.assertFalse(finale_prep.forbids_hunting(policy, board))

    def sensed_hunt(self, policy, board, *, with_unique=True):
        """The rest's answer to the sensed group with the estimate read winnable.  DECLARED
        CONSTRUCTED: the recorded board reads it infeasible, and its group (the awake sensed
        non-summoners: the hounds of Tindalos, race 739, and race 938) holds no unique, Reizark a
        summoner the tiers leave out; ``with_unique`` stands Reizark in the group without his
        summons (a strong unique that does not summon)."""
        assess = policy._esp_threat_assess

        def winnable(snapshot):
            assessment, tiered = assess(snapshot)
            assessment["feasibility"]["feasible"] = True
            if with_unique:
                reizark = next(monster for monster in snapshot.detected_monsters
                               if monster.race_id == REIZARK)
                tiered = [*tiered, replace(reizark, can_summon=False)]
            return assessment, tiered
        with mock.patch.object(policy, "_esp_threat_assess", winnable):
            policy._esp_threat_rest_key(board, policy._strategic_hostiles(board))
        return policy._esp_threat_assessment

    def test_the_live_sensed_hunt_without_the_gate(self):
        policy, board = self.castle()
        with mock.patch.object(finale_prep, "forbids_hunting", lambda *_args: False):
            assessment = self.sensed_hunt(policy, board)
        self.assertEqual((assessment["tier"], assessment["action"]), ("strong", "hunt"))

    def test_no_sensed_strong_unique_is_hunted(self):
        policy, board = self.castle()
        assessment = self.sensed_hunt(policy, board)

        # Before: "hunt" (the committed walk to Reizark's group).
        self.assertEqual((assessment["tier"], assessment["action"]), ("strong", "leave"))
        self.assertEqual(assessment["finale_prep"], "no-unique-hunt")
        self.assertIsNone(policy._esp_threat_hunt)

    def test_a_sensed_strong_group_without_a_unique_is_still_hunted(self):
        policy, board = self.castle()
        assessment = self.sensed_hunt(policy, board, with_unique=False)

        self.assertEqual((assessment["tier"], assessment["action"]), ("strong", "hunt"))
        self.assertNotIn("finale_prep", assessment)

    def test_a_strong_unique_is_named(self):
        policy, board = self.castle()
        named = finale_prep.uniques(policy, board.detected_monsters)

        self.assertIn(REIZARK, {monster.race_id for monster in named})
        self.assertNotIn(739, {monster.race_id for monster in named})  # not UNIQUE


if __name__ == "__main__":
    unittest.main()
