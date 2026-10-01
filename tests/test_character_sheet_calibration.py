"""Real CP932 L28 dump versus its saved strip record; arithmetic cases labeled."""
import tests  # noqa: F401
from dataclasses import replace
import json
from pathlib import Path
import re
import unittest

from hengbot.character_sheet import (CharacterSheetUnavailable, StatRow,
                                    parse_character_sheet, derive_equipped_calibration,
                                    invert_current, printed_stat, temporary_bonuses)
from hengbot.model import Snapshot
from hengbot.warrior_optimization import load_character_calibration, character_intrinsic_flags
from tests.policy_fixtures import player, item

FIXTURES = Path(__file__).parent / "fixtures/calib-equivalence"


def recorded_equipped_inputs():
    raw = (FIXTURES / "bot-test-234935.txt").read_bytes()
    sheet = parse_character_sheet(raw)
    slots = ("main_hand", "sub_hand", "bow", "main_ring", "sub_ring", "neck",
             "light", "body", "outer", "head", "arms", "feet")
    tvals = (22, 34, 19, 45, 45, 40, 39, 36, 35, 34, 31, 30)
    equipment = []
    block = sheet.text.split("[キャラクタの装備]", 1)[1].split("[キャラクタの持ち物]", 1)[0]
    for letter, name in re.findall(r"^([a-l])\) (.+)$", block, re.M):
        index = ord(letter) - ord("a")
        if name.startswith("("):
            continue
        armor = re.search(r"\[(?:(\d+),)?([+-]\d+)\]", name)
        ac, to_a = (int(armor[1] or 0), int(armor[2])) if armor else (0, 0)
        # Visible stat grid: the weapon's '3' in DEX and CHR, all others dots.
        pval, flags = (3, frozenset({3, 5})) if letter == "a" else (0, frozenset())
        equipment.append(item(slots[index], tvals[index], 0, name=name, known=True,
                              fully_known=True, is_equipment=True, ac=ac, to_a=to_a,
                              pval=pval, known_flags=flags))
    flag_labels = {10: "赤外線視力", 47: "経験値保持", 48: "耐酸", 49: "耐電撃",
                   50: "耐火炎", 51: "耐冷気", 52: "耐毒", 60: "耐地獄",
                   78: "透明体視認", 79: "テレパシー", 80: "遅消化"}
    characteristics = []
    for flag, label in flag_labels.items():
        match = re.search(re.escape(label) + r"\s*:\s*([.+*v]+)", sheet.text)
        if match is None:
            raise AssertionError(f"missing recorded flag row {label}")
        characteristics.append({"flag_id": flag, "player": match[1][-1] == "+"})
    character = {"race_title": "ゾンビ", "class_title": "戦士",
                 "personality_title": "ちからじまん", "mutations": [],
                 "characteristics": characteristics, "base_ac": 19, "ac_bonus": 56}
    snapshot = Snapshot(turn=1921699, player=replace(player(1, 1), class_id=0, race_id=25,
                        personality_id=1, level=sheet.level, hp=sheet.max_hp,
                        max_hp=sheet.max_hp, ac=sheet.armor_class,
                        stat_cur=tuple(row.base for row in sheet.rows),
                        stat_max=tuple(row.base for row in sheet.rows),
                        stat_use=tuple(row.actual for row in sheet.rows)),
                        grids={}, visible_monsters=(), inventory=(), equipment=tuple(equipment))
    return sheet, snapshot, character


class CharacterSheetCalibrationTest(unittest.TestCase):
    def test_real_l28_equivalence_all_semantic_fields(self):
        sheet, snapshot, character = recorded_equipped_inputs()
        actual = derive_equipped_calibration(sheet, snapshot, character)
        expected = load_character_calibration(FIXTURES / "character-calibration.json")
        for field in ("race_id", "class_id", "personality_id", "level", "stat_cur",
                      "base_stats", "base_hp", "base_ac_bonus", "intrinsic_abilities",
                      "pinned_identities", "mutation_signature", "intrinsic_tr_flags"):
            with self.subTest(field=field):
                self.assertEqual(getattr(actual, field), getattr(expected, field))
        self.assertEqual(actual.base_stats, (164, 5, 9, 91, 115, 6))
        self.assertEqual(actual.base_hp, 403)
        self.assertEqual(actual.base_ac_bonus, 0)
        self.assertEqual(actual.hp_floor, 29)

    def test_arithmetic_floor_minimal_candidate_and_unique_positive_inverse(self):
        for current, adjustment, expected in ((3, -10, 3), (18, -1, 19), (121, 6, 61)):
            row = StatRow(100, 0, 0, 0, 0, current, current)
            self.assertEqual(invert_current(row, adjustment), expected)
        self.assertEqual(printed_stat("18/***"), (238, True))
        self.assertEqual(printed_stat("18/219"), (237, False))

    def test_saturation_does_not_reject_and_irrelevant_floor_does_not_reject(self):
        sheet, snapshot, character = recorded_equipped_inputs()
        weapon = replace(snapshot.equipment[0], pval=10,
                         known_flags=frozenset({0, 3, 5}))
        rows = list(sheet.rows)
        rows[0] = replace(rows[0], actual=238, saturated=True)
        rows[3] = replace(rows[3], actual=191)
        snapshot = replace(snapshot, equipment=(weapon,) + snapshot.equipment[1:],
                           player=replace(snapshot.player, stat_use=(238, 5, 9, 191, 115, 68), ac=82))
        sheet = replace(sheet, rows=tuple(rows), armor_class=82)
        self.assertEqual(derive_equipped_calibration(sheet, snapshot, character).base_stats[0], 164)

    def test_temporary_effects_use_maximum_ac_group_and_post_floor_hp(self):
        self.assertEqual(temporary_bonuses(frozenset({"ultimate_resistance", "shield", "blessed", "berserk", "heroism"})), (40, 95))
        sheet, snapshot, character = recorded_equipped_inputs()
        snapshot = replace(snapshot, player=replace(snapshot.player, max_hp=541, ac=170))
        sheet = replace(sheet, max_hp=541, armor_class=170)
        value = derive_equipped_calibration(sheet, snapshot, character,
                effects=frozenset({"ultimate_resistance", "shield", "blessed", "berserk", "heroism"}))
        self.assertEqual((value.base_hp, value.base_ac_bonus), (403, 0))
        with self.assertRaisesRegex(CharacterSheetUnavailable, "unknown-timed-effect"):
            temporary_bonuses(frozenset({"unimplemented-effect"}))

    def test_immunity_and_vulnerability_are_source_separated(self):
        self.assertEqual(character_intrinsic_flags([
            {"flag_id": 50, "player": False, "immunity": True},
            {"flag_id": 51, "player": False, "vulnerability": True},
            {"flag_id": 52, "temporary": True}]), frozenset({42, 153}))

    def test_missing_table_and_mixed_epoch_are_rejected(self):
        with self.assertRaisesRegex(CharacterSheetUnavailable, "visible-base-missing"):
            parse_character_sheet(b"missing")
        sheet, snapshot, character = recorded_equipped_inputs()
        with self.assertRaisesRegex(CharacterSheetUnavailable, "snapshot-mismatch"):
            derive_equipped_calibration(sheet, replace(snapshot, player=replace(snapshot.player, level=29)), character)
