"""Issue #88: calibration accepts the sheet-neutral (class A) mutations.

Inputs are labeled: RECORDED = the 07-25 auto-dump (its only mutation is
BR_FIRE 1) and the existing L28 / 0917 calibration fixtures; DECLARED = a
mutation list or max HP written into those recorded inputs by the test.
"""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

from dataclasses import replace
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

import hengbot.character_sheet as character_sheet
from hengbot.character_sheet import (CharacterSheetUnavailable, derive_equipped_calibration,
                                    parse_character_sheet)
from hengbot.model import Snapshot, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import CHARACTER_DUMP_MACRO
from tests.policy_fixtures import item, player
from tests.test_character_sheet_calibration import recorded_equipped_inputs

FIXTURES = Path(__file__).parent / "fixtures"
JULY_DUMP = FIXTURES / "mutation-calibration/bot-test_Autodump_2026-07-25_054022.txt"
CALIB = FIXTURES / "calib-equivalence"

# Design DESIGN-mutation-calibration-1019.md section 4 (the partition of 0..95).
DESIGN_CLASS_A = frozenset(range(0, 64)) | frozenset(
    {75, 76, 77, 78, 79, 80, 81, 82, 86, 87, 88, 89, 92, 94, 95})
DESIGN_CLASS_B = frozenset(range(64, 75)) | frozenset({83, 84, 85, 90, 91})
DESIGN_CLASS_C = frozenset({93})

SLOTS = ("main_hand", "sub_hand", "bow", "main_ring", "sub_ring", "neck",
         "light", "body", "outer", "head", "arms", "feet")
TVALS = (22, 34, 19, 45, 45, 40, 39, 37, 35, 32, 31, 30)
FLAG_LABELS = {10: "赤外線視力", 46: "耐麻痺", 47: "経験値保持", 48: "耐酸", 49: "耐電撃",
               50: "耐火炎", 51: "耐冷気", 52: "耐毒", 53: "耐恐怖", 54: "耐閃光",
               55: "耐暗黒", 56: "耐盲目", 57: "耐混乱", 58: "耐轟音", 59: "耐破片",
               60: "耐地獄", 61: "耐因混", 62: "耐カオ", 63: "耐劣化", 76: "浮遊",
               78: "透明体視認", 79: "テレパシー", 80: "遅消化"}


def july_inputs(mutations):
    """RECORDED 07-25 dump; the snapshot projects only its visible numbers."""
    sheet = parse_character_sheet(JULY_DUMP.read_bytes())
    text = sheet.text.replace("\r\n", "\n")
    header = re.search(r"(?m)^.*能力\s+基本.*\n", text)
    stat_lines = text[header.end():].split("\n")[:6]
    symbols = [line.rstrip()[-13:] for line in stat_lines]
    block = text.split("[キャラクタの装備]", 1)[1].split("[キャラクタの持ち物]", 1)[0]
    equipment = []
    for letter, name in re.findall(r"(?m)^([a-l])\) (.+)$", block):
        index = ord(letter) - ord("a")
        if name.startswith("("):
            continue
        armor = re.search(r"\[(?:(\d+),)?([+-]\d+)\]", name)
        ac, to_a = (int(armor[1] or 0), int(armor[2])) if armor else (0, 0)
        digits = {stat: int(row[index]) for stat, row in enumerate(symbols) if row[index].isdigit()}
        pval = max(digits.values(), default=0)
        equipment.append(item(SLOTS[index], TVALS[index], 0, name=name, known=True,
                              fully_known=True, is_equipment=True, ac=ac, to_a=to_a,
                              pval=pval, known_flags=frozenset(digits)))
    characteristics = []
    for flag, label in FLAG_LABELS.items():
        match = re.search(re.escape(label) + r"\s*:\s*([.+*v]+)", text)
        characteristics.append({"flag_id": flag, "player": match[1][-1] == "+"})
    armor = re.search(r"ＡＣ\s+\[(\d+),([+-]\d+)\]", text)
    character = {"race_title": "ゾンビ", "class_title": "戦士",
                 "personality_title": "ちからじまん", "mutations": list(mutations),
                 "characteristics": characteristics,
                 "base_ac": int(armor[1]), "ac_bonus": int(armor[2]),
                 "stat_modifiers": [{"stat_id": i, "player": {"symbol": symbols[i][-1]}}
                                    for i in range(6)],
                 "curse_marks": [{"slot": gear.slot, "mark": "."} for gear in equipment]}
    snapshot = Snapshot(turn=1, player=replace(
        player(1, 1), class_id=0, race_id=25, personality_id=1, level=sheet.level,
        hp=sheet.max_hp, max_hp=sheet.max_hp, ac=sheet.armor_class,
        stat_cur=tuple(row.base for row in sheet.rows),
        stat_max=tuple(row.base for row in sheet.rows),
        stat_use=tuple(row.actual if row.current is None else row.current for row in sheet.rows)),
        grids={}, visible_monsters=(), inventory=(), equipment=tuple(equipment))
    return sheet, snapshot, character


class SheetNeutralMutationTest(unittest.TestCase):
    def test_recorded_july_dump_with_br_fire_equals_its_no_mutation_calibration(self):
        sheet, snapshot, character = july_inputs([1])
        mutated = derive_equipped_calibration(sheet, snapshot, character)
        sheet, snapshot, character = july_inputs([])
        plain = derive_equipped_calibration(sheet, snapshot, character)
        self.assertEqual(mutated.mutation_signature, (1,))
        self.assertEqual(plain.mutation_signature, ())
        self.assertEqual(replace(mutated, mutation_signature=()), plain)
        self.assertEqual(plain.level, 25)

    def test_swap_pos_equals_no_mutation_except_signature_and_still_invalidates(self):
        sheet, snapshot, character = recorded_equipped_inputs()
        plain = derive_equipped_calibration(sheet, snapshot, character)
        mutated = derive_equipped_calibration(sheet, snapshot, dict(character, mutations=[12]))
        self.assertEqual(mutated.mutation_signature, (12,))
        self.assertEqual(replace(mutated, mutation_signature=()), plain)
        self.assertIsNone(mutated.stale_reason(snapshot.player, (), mutation_signature=(12,)))
        self.assertEqual(mutated.stale_reason(snapshot.player, (), mutation_signature=()),
                         "mutations")

    def test_every_class_a_mutation_is_accepted_without_changing_the_calibration(self):
        sheet, snapshot, character = recorded_equipped_inputs()
        plain = derive_equipped_calibration(sheet, snapshot, character)
        for mutation in sorted(DESIGN_CLASS_A):
            with self.subTest(mutation=mutation):
                value = derive_equipped_calibration(
                    sheet, snapshot, dict(character, mutations=[mutation]))
                self.assertEqual(replace(value, mutation_signature=()), plain)

    def test_reason_lists_only_the_ids_outside_the_allowlist(self):
        sheet, snapshot, character = recorded_equipped_inputs()
        # Owner decision 2026-10-23 (#88 stage 2, all of class B): class B is no longer refused.
        for mutations, reason in (([12, 69], "mutation-symbol-mismatch"),
                                  ([93], "unsupported-mutation:93"),
                                  ([96], "unsupported-mutation:96"),
                                  ([93, 12, 74, 1], "unsupported-mutation:93")):
            with self.subTest(mutations=mutations):
                with self.assertRaises(CharacterSheetUnavailable) as raised:
                    derive_equipped_calibration(sheet, snapshot,
                                                dict(character, mutations=mutations))
                self.assertEqual(str(raised.exception), reason)

    def test_allowlist_is_the_design_partition(self):
        # The design's class B already holds ILL_NORM 74 (64..74 are eleven
        # ids), so the partition is A | B | {93}.
        self.assertIn(74, DESIGN_CLASS_B)
        self.assertEqual(character_sheet.SHEET_NEUTRAL_MUTATIONS, DESIGN_CLASS_A)
        self.assertEqual(len(character_sheet.SHEET_NEUTRAL_MUTATIONS), 79)
        self.assertEqual(character_sheet.SHEET_NEUTRAL_MUTATIONS & DESIGN_CLASS_B, frozenset())
        self.assertEqual(character_sheet.SHEET_NEUTRAL_MUTATIONS | DESIGN_CLASS_B | {74} | DESIGN_CLASS_C,
                         frozenset(range(96)))
        self.assertEqual(len(DESIGN_CLASS_B), 16)


def _game_source_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "src/mutation/mutation-flag-types.h").is_file():
            return parent / "src"
    return None


class GameSourceCrossCheckTest(unittest.TestCase):
    def test_no_allowlisted_mutation_reaches_stats_ac_or_the_stat_table(self):
        root = _game_source_root()
        if root is None:
            self.skipTest("game source absent")
        header = (root / "mutation/mutation-flag-types.h").read_text(encoding="utf-8")
        names = {int(value): name for name, value in
                 re.findall(r"(?m)^\s*([A-Z_]+)\s*=\s*(\d+),", header)}
        self.assertEqual(set(names), set(range(96)))
        status = (root / "player/player-status.cpp").read_text(encoding="utf-8")
        body = re.search(r"(?ms)^static ARMOUR_CLASS calc_to_ac\(PlayerType \*player_ptr, "
                         r"bool is_real_value\)\n\{\n(.*?)^\}\n", status)
        texts = [path.read_text(encoding="utf-8")
                 for path in sorted((root / "player-ability").glob("*.cpp"))]
        texts += [body[1], (root / "view/display-player-stat-info.cpp").read_text(encoding="utf-8")]
        referenced = {mutation for mutation, name in names.items()
                      if any(f"PlayerMutationType::{name}" in text for text in texts)}
        self.assertEqual(referenced & character_sheet.SHEET_NEUTRAL_MUTATIONS, set())
        # Control: the same scan does find the class B rules.
        self.assertEqual(referenced, set(DESIGN_CLASS_B))


class PolicyIntegrationTest(unittest.TestCase):
    """RECORDED 0917 response and dump through the posted-dump lifecycle."""

    KNOWLEDGE = {35: MonraceKnowledge(30, 110, False, False, level=1, rarity=1,
                                      average_hp=30, armor_class=10,
                                      blows=(MonsterBlow("HIT", "HURT", 1, 8),))}

    def envelope(self, mutations):
        data = json.loads((CALIB / "0917-equipped.json").read_text(encoding="utf-8"))
        data["player"]["status_bar"] = []
        data["character"].update(race_title="Zombie", class_title="Warrior",
                                  personality_title="Mighty", mutations=list(mutations))
        return data

    def calibrated(self, directory, mutations):
        policy = HengbotPolicy(monrace_knowledge=self.KNOWLEDGE)
        policy._character_dump_path = Path(directory) / "equipped.txt"
        policy._character_calibration_path = Path(directory) / "constants.json"
        policy._prepare_character_sheet_dump()
        self.assertTrue(policy.confirm_key_posted(CHARACTER_DUMP_MACRO))
        policy._character_dump_path.write_bytes((CALIB / "0917-synthesized.txt").read_bytes())
        data = self.envelope(mutations)
        board = parse_snapshot(data, {})
        policy.observe_character_snapshot(data["character"], envelope=data)
        policy._complete_character_dump(board)
        return policy, data, board

    def test_swap_pos_character_reaches_the_optimizer(self):
        with TemporaryDirectory() as directory:
            policy, _data, board = self.calibrated(directory, [12])
            self.assertIsNone(policy._calibration_unavailable_reason)
            self.assertEqual(policy._character_calibration.mutation_signature, (12,))
            policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
            policy._equipment_catalog.observe_home_page([])
            preparation = policy._prepare_equipment_optimization(board)
            self.assertEqual(preparation.blockers, ())
            self.assertIsNotNone(preparation.result.best.loadout)

    def test_max_hp_reroll_makes_the_calibration_stale(self):
        with TemporaryDirectory() as directory:
            policy, data, board = self.calibrated(directory, [])
            self.assertIsNotNone(policy._validated_character_calibration(board))
            # DECLARED: a heroism bonus raises max HP by exactly its visible 10.
            heroic = parse_snapshot(dict(data, player=dict(
                data["player"], max_hp=data["player"]["max_hp"] + 10,
                status_bar=[{"key": "hero"}])), {})
            self.assertIsNotNone(policy._validated_character_calibration(heroic))
            # DECLARED: the same character after a hit-dice reroll.
            rerolled = parse_snapshot(dict(data, player=dict(
                data["player"], max_hp=data["player"]["max_hp"] + 1)), {})
            self.assertIsNone(policy._validated_character_calibration(rerolled))
            self.assertEqual(policy._calibration_unavailable_reason, "visible-max-hp-changed")
            self.assertIsNone(policy._character_calibration)


if __name__ == "__main__":
    unittest.main()
