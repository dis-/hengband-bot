"""O4: constructed visible zombie Magic-Eater sheet and real loadout producers."""
import tests  # noqa: F401
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.character_sheet import derive_equipped_calibration, parse_character_sheet
from hengbot.equipment_optimizer import OwnedEquipmentCatalog, current_loadout
from hengbot.model import Snapshot, SV_LITE_FEANOR
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.warrior_equipment_evaluator import WarriorCombatInputs, evaluate_warrior_melee
from hengbot.warrior_loadout_evaluator import warrior_ranged_offense_dps
from hengbot.warrior_optimization import PLAYER_ABILITY_FLAGS, weapon_expected_dps
from tests.policy_fixtures import item, player


def magic_eater_inputs():
    sheet = parse_character_sheet(
        (Path(__file__).parent / "fixtures/magic-eater-o4-sheet.txt").read_bytes())
    equipment = (
        replace(item("main_hand", 23, 17, name="Long Sword (2d5) (+0,+0)",
                     damage_dice_num=2, damage_dice_sides=5), weight=130, weapon_proficiency=4000),
        item("light", 39, SV_LITE_FEANOR, name="Feanorian Lamp"),
        item("body", 36, 2, name="Robe [2,+0]", ac=2),
    )
    equipment = tuple(replace(gear, known=True, fully_known=True, is_equipment=True)
                      for gear in equipment)
    actor = replace(player(10, 10, hp=200, max_hp=200, class_id=16, level=27),
                    race_id=25, personality_id=1, ac=15,
                    stat_cur=(70, 12, 17, 18, 17, 15),
                    stat_max=(70, 12, 17, 18, 17, 15),
                    stat_use=(100, 6, 11, 48, 38, 13),
                    melee_skill=85, shooting_skill=65, saving_skill=50)
    board = Snapshot(player=actor, grids={}, visible_monsters=(), equipment=equipment,
                     inventory=(), town_flag=True, floor_key=(0, 0, 0))
    character = dict(race_title="Zombie", class_title="Magic-Eater", personality_title="Mighty",
                     mutations=[], characteristics=[dict(flag_id=flag, player=flag in {47, 51, 52, 60, 78})
                                                   for flag in set(PLAYER_ABILITY_FLAGS.values()) | {78}],
                     base_ac=2, ac_bonus=13,
                     stat_modifiers=[dict(stat_id=i, player=dict(symbol=".")) for i in range(6)],
                     curse_marks=[dict(slot=gear.slot, mark=".") for gear in equipment])
    return sheet, board, character


def monster_knowledge():
    return {1: MonraceKnowledge(max_hp=20, average_hp=20, speed=110, can_summon=False,
                               friendly=False, level=1, armor_class=0, rarity=1,
                               blows=(MonsterBlow("HIT", "HURT", 1, 4),))}


class MagicEaterCalibrationTest(unittest.TestCase):
    def calibrated(self):
        sheet, board, character = magic_eater_inputs()
        calibration = derive_equipped_calibration(sheet, board, character)
        return board, calibration

    def test_constructed_class16_sheet_calibrates(self):
        board, calibration = self.calibrated()
        self.assertEqual(calibration.class_id, 16)
        self.assertEqual(calibration.schema_version, 2)
        self.assertEqual(calibration.base_stats, (100, 6, 11, 48, 38, 13))
        self.assertEqual(calibration.intrinsic_adjustments, (3, -6, -6, 3, 3, -2))
        self.assertIsNone(calibration.stale_reason(board.player, ()))

    def policy_and_board(self):
        board, calibration = self.calibrated()
        upgrade = replace(board.equipment[2], slot="a", name="Robe [2,+20]", to_a=20)
        board = replace(board, inventory=(upgrade,))
        policy = HengbotPolicy(monrace_knowledge=monster_knowledge())
        policy._character_calibration = calibration
        policy._character_calibration_loaded = True
        policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
        policy._equipment_catalog.home_scan_complete = True
        return policy, board

    def test_class16_policy_optimizer_selects_armour_upgrade(self):
        policy, board = self.policy_and_board()
        prepared = policy._prepare_equipment_optimization(board, depth_override=1)
        self.assertIsNotNone(prepared)
        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(prepared.result.best.loadout.item_at("body").item.to_a, 20)
        self.assertAlmostEqual(prepared.result.best.metrics.expected_dps, 16.52176467692308)
        self.assertTrue(prepared.transaction.actions)

    def test_class16_departure_checks_pending_equipment(self):
        policy, board = self.policy_and_board()
        self.assertFalse(policy._equipment_departure_ready(board, destination_depth=1))

    def test_class16_bodyless_character_requests_shared_rearm(self):
        policy, board = self.policy_and_board()
        board = replace(board, equipment=board.equipment[:2], player=replace(board.player, ac=13))
        policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
        policy._home_knowledge_current = True
        policy._request_priority_body_rearm(board)
        prepared = policy._equipment_optimization_preparation
        self.assertIsNotNone(prepared)
        self.assertTrue(prepared.ready, prepared.blockers)
        self.assertEqual(prepared.result.best.loadout.item_at("body").item.to_a, 20)

    def test_class16_acceptance_dps_uses_its_blow_table(self):
        board, calibration = self.calibrated()
        dps = weapon_expected_dps(board, board.equipment[0], 100, calibration)
        self.assertIsNotNone(dps)
        # calc_num_blow: STR index 23, DEX index 18, weight 130, mul 3,
        # two-hand index +1 gives 3 blows. The AC100 score includes criticals.
        self.assertAlmostEqual(dps, 16.52176467692308)

    def test_class16_blow_limits_weight_and_two_hand_level_bonus(self):
        board, calibration = self.calibrated()
        catalog = OwnedEquipmentCatalog()
        catalog.refresh_carried((), board.equipment)
        current = current_loadout(catalog.items)
        inputs = WarriorCombatInputs(level=board.player.level,
                                     natural_str=calibration.natural_stats[0],
                                     natural_dex=calibration.natural_stats[3],
                                     intrinsic_str=calibration.intrinsic_adjustments[0],
                                     intrinsic_dex=calibration.intrinsic_adjustments[3],
                                     melee_skill=board.player.melee_skill, class_id=16)
        # Game calc_num_blow/BLOWS_TABLE: the light weapon still uses wgt=100;
        # two hands add only one STR index, even at level 46; no level/40 blow.
        cases = ((70, 18, 30, "one_handed", 27, 3),
                 (70, 18, 130, "one_handed", 27, 2),
                 (70, 18, 130, "two_handed", 46, 3),
                 (238, 238, 30, "one_handed", 50, 5))
        for strength, dexterity, weight, mode, level, expected in cases:
            with self.subTest(case=(strength, dexterity, weight, mode, level)):
                slots = tuple((slot, replace(owned, item=replace(owned.item, weight=weight))
                               if slot == "main_hand" else owned)
                              for slot, owned in current.slots)
                loadout = replace(current, slots=slots, hand_mode=mode)
                result = evaluate_warrior_melee(
                    loadout, replace(inputs, natural_str=strength, natural_dex=dexterity, level=level))
                self.assertEqual(result.hands[0].blows, expected)

    def test_class16_launcher_has_no_warrior_level_shots(self):
        board, _ = self.calibrated()
        bow = replace(item("bow", 19, 12, name="Short Bow", known=True,
                           fully_known=True, is_equipment=True), weight=30, weapon_proficiency=4000)
        catalog = OwnedEquipmentCatalog()
        catalog.refresh_carried((), board.equipment + (bow,))
        loadout = current_loadout(catalog.items)
        inputs = WarriorCombatInputs(level=27, natural_str=100, natural_dex=48,
                                     melee_skill=85, shooting_skill=65, class_id=16)
        damage = warrior_ranged_offense_dps(loadout, inputs)
        self.assertGreater(damage, 0)
        self.assertEqual(damage, warrior_ranged_offense_dps(loadout, replace(inputs, level=50)))
        self.assertAlmostEqual(warrior_ranged_offense_dps(loadout, replace(inputs, class_id=0)),
                               damage * 1.54)


if __name__ == "__main__":
    unittest.main()
