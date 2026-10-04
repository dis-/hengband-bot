"""Constructed 20043207fb shapes on a historical protocol-3 board substrate.

No new-exe capture or live process is required. Changed fields are copied
from make_snapshot/make_character_json, not inferred from a live save.
"""
import tests  # noqa: F401
import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from hengbot.model import parse_snapshot, Snapshot, Position, TVAL_SWORD
from hengbot.policy import HengbotPolicy
from hengbot.protocol import ProtocolSchemaError
from hengbot.warrior_equipment_evaluator import melee_hit_chance, displayed_melee_hit_chance
from tests.policy_fixtures import item


def board():
    path = Path(__file__).parent / "fixtures/esp-threat-rest-20260921.protocol3.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("type") == "player_turn":
                return row
    raise AssertionError("missing historical board")


def new_board():
    row = board()
    row["player"]["melee"] = {
        "main_hand_blows": 5, "main_hand_to_d": 47, "main_hand_to_h": 123,
        "mutation_blows": 0, "sub_hand_blows": 0,
        "sub_hand_to_d": None, "sub_hand_to_h": None,
    }
    return row


class DisplayAlignmentTest(unittest.TestCase):
    def test_constructed_new_snapshot_preserves_inactive_hand(self):
        state = parse_snapshot(new_board(), {}).player
        self.assertTrue(state.melee_displayed_totals)
        self.assertEqual((state.main_hand_to_h, state.main_hand_to_d), (123, 47))
        self.assertEqual((state.sub_hand_blows, state.sub_hand_to_h, state.sub_hand_to_d), (0, None, None))
        self.assertEqual(state.mutation_blows, 0)

    def test_per_snapshot_detection_can_switch_back_to_old_exe(self):
        self.assertTrue(parse_snapshot(new_board(), {}).player.melee_displayed_totals)
        row = board()
        state = parse_snapshot(row, {}).player
        self.assertFalse(state.melee_displayed_totals)
        self.assertIsNone(state.mutation_blows)
        for key, value in row["player"]["melee"].items():
            self.assertEqual(getattr(state, key), value)

    def test_new_fields_never_silently_default(self):
        for key in new_board()["player"]["melee"]:
            with self.subTest(key=key):
                row = new_board()
                del row["player"]["melee"][key]
                with self.assertRaises(ProtocolSchemaError):
                    parse_snapshot(row, {})

    def test_inconsistent_inactive_hand_and_noninteger_bonuses_rejected(self):
        for changes in ({"sub_hand_blows": 1}, {"sub_hand_to_d": 0},
                        {"main_hand_to_h": "123"}, {"mutation_blows": -1}):
            with self.subTest(changes=changes):
                row = new_board()
                row["player"]["melee"].update(changes)
                with self.assertRaises(ProtocolSchemaError):
                    parse_snapshot(row, {})

    def test_both_hands_and_mutations_are_independently_modelled(self):
        row = new_board()
        row["player"]["melee"].update(sub_hand_blows=2, sub_hand_to_h=91,
                                         sub_hand_to_d=25, mutation_blows=5)
        state = parse_snapshot(row, {}).player
        self.assertEqual((state.sub_hand_blows, state.sub_hand_to_h, state.sub_hand_to_d, state.mutation_blows), (2, 91, 25, 5))
        row["player"]["melee"].update(main_hand_blows=0, main_hand_to_h=None, main_hand_to_d=None)
        self.assertIsNone(parse_snapshot(row, {}).player.main_hand_to_h)

    def test_displayed_hit_total_does_not_add_skill_or_weapon_twice(self):
        for skill in (0, 1, 2, 239, 240, 241, -1, -5):
            for weapon_bonus in (-7, 0, 23):
                quotient = abs(skill) // 3 * (-1 if skill < 0 else 1)
                total = 43 + weapon_bonus + quotient
                self.assertEqual(displayed_melee_hit_chance(skill, total),
                                 melee_hit_chance(skill, 43, weapon_bonus))

    def test_current_weapon_dps_uses_damage_total_once_and_no_inactive_attack(self):
        snapshot = parse_snapshot(new_board(), {})
        weapon = item("main_hand", TVAL_SWORD, 1, to_h=23, to_d=8,
                      damage_dice_num=2, damage_dice_sides=6)
        expected = 5 * (7 + 47) * displayed_melee_hit_chance(snapshot.player.melee_skill, 123)
        self.assertEqual(HengbotPolicy._main_hand_dps(snapshot, weapon), expected)
        self.assertEqual(HengbotPolicy._sub_hand_dps(snapshot, weapon), 0)
        inactive = replace(snapshot, player=replace(snapshot.player,
            main_hand_blows=0, main_hand_to_h=None, main_hand_to_d=None))
        self.assertEqual(HengbotPolicy._main_hand_dps(inactive, weapon), 0)

    def test_old_current_weapon_dps_keeps_legacy_arithmetic(self):
        snapshot = parse_snapshot(board(), {})
        weapon = item("main_hand", TVAL_SWORD, 1, to_h=23, to_d=8,
                      damage_dice_num=2, damage_dice_sides=6)
        for hand, method in (("main", HengbotPolicy._main_hand_dps), ("sub", HengbotPolicy._sub_hand_dps)):
            p = snapshot.player
            expected = getattr(p, f"{hand}_hand_blows") * max(1, 7 + getattr(p, f"{hand}_hand_to_d")) * melee_hit_chance(p.melee_skill, getattr(p, f"{hand}_hand_to_h"), 23)
            self.assertEqual(method(snapshot, weapon), expected)

    def test_new_character_fields_do_not_affect_equipped_calibration(self):
        from tests.test_character_sheet_calibration import recorded_equipped_inputs
        from hengbot.character_sheet import derive_equipped_calibration
        sheet, snapshot, character = recorded_equipped_inputs()
        before = derive_equipped_calibration(sheet, snapshot, character)
        for damage_nil, damage in ((False, [3, 0]), (True, None)):
            changed = copy.deepcopy(character)
            changed.update(melee={"blows": [3, 0, 5], "expected_damage_per_round": damage,
                                  "damage_nil": damage_nil, "bare_hand": False,
                                  "two_handed": False, "monk_stance": 0},
                           ranged={"to_h_b": 42, "shots": 1, "shot_frac": 0,
                                   "shooting_multiplier": 200, "see_infra": 0},
                           speed={"base": None, "temporary": 99, "lightspeed": True, "riding": False})
            self.assertEqual(derive_equipped_calibration(sheet, snapshot, changed), before)

    def test_readiness_fallback_uses_new_total_and_handles_null_main_hand(self):
        from tests.test_policy_quest import ApprovedQuestStrategyExecutionTest
        case = ApprovedQuestStrategyExecutionTest()
        case.setUpClass()
        policy = case._policy()
        opening = case._measured_q34_opening()
        new_player = replace(opening.player, melee_displayed_totals=True,
                             melee_skill=241, main_hand_blows=5,
                             main_hand_to_h=123, main_hand_to_d=47, mutation_blows=0)
        opening = replace(opening, player=new_player)
        with patch.object(policy, "_validated_character_calibration", return_value=None):
            policy._approved_strategy_force_ready(opening, case.profiles[34])
        weapon = opening.equipment[0]
        force = policy._strategy_force_for_snapshot(opening, case.profiles[34])
        dice = weapon.damage_dice_num * (weapon.damage_dice_sides + 1) / 2
        expected = 5 * max(0, dice + 47) * displayed_melee_hit_chance(241, 123, int(force.get("reference_ac", 100)))
        self.assertEqual(policy.fixed_quest_readiness_state()["strategy_force"]["dps"]["measured"], expected)
        opening = replace(opening, player=replace(new_player, main_hand_blows=0,
                          main_hand_to_h=None, main_hand_to_d=None))
        with patch.object(policy, "_validated_character_calibration", return_value=None):
            policy._approved_strategy_force_ready(opening, case.profiles[34])
        self.assertEqual(policy.fixed_quest_readiness_state()["strategy_force"]["dps"]["measured"], 0)

    def test_canonical_lighting_one_cannot_certify_fixed_target_death(self):
        from tests.test_policy_quest import ApprovedQuestStrategyExecutionTest
        from tests.policy_fixtures import player, grid
        case = ApprovedQuestStrategyExecutionTest()
        case.setUpClass()
        target_key = (107, 9, 11)
        for symbol in (0, 1, 2):
            policy = case._policy()
            policy._quest_strategy_visible_targets[34] = {target_key}
            policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
            snapshot = Snapshot(
                replace(player(11, 11), melee_displayed_totals=True, mutation_blows=0),
                {Position(11, 11): grid(11, 11, in_view=True),
                 Position(10, 11): grid(10, 11),
                 Position(9, 11): replace(grid(9, 11, in_view=False), map_lighting=symbol)},
                [], floor_key=(0, 5, 34), light_radius=3)
            policy._build_grid_index(snapshot)
            policy._approved_quest_strategy_key(snapshot, [], [])
            self.assertNotIn(target_key, policy._quest_strategy_cleared_targets[34])
            self.assertNotIn(34, policy._quest_strategy_pending_recovery)

    def test_new_grid_symbol_indices_do_not_recreate_visibility_bits(self):
        for symbol in (0, 1, 2):
            row = new_board()
            for entry in row["grid_map"]["palette"]:
                entry[1] = symbol
            snapshot = parse_snapshot(row, {})
            self.assertTrue(snapshot.grids)
            for cell in snapshot.grids.values():
                self.assertEqual(cell.map_lighting, symbol)
                self.assertFalse(cell.lit)
                self.assertFalse(cell.in_view)

    def test_debug_exp_never_overrides_visible_capped_skill(self):
        policy = HengbotPolicy()
        data = {"player": {"level": 30}, "knowledge": {"category": "skill_exp", "skills": [
            {"id": 1, "exp": 1000, "max": 1000, "debug_exp": 9000, "rank": 1, "at_max": True},
            {"id": 3, "exp": 2000, "max": 2000, "debug_exp": 8000, "rank": 1, "at_max": True},
        ]}}
        policy.consume_skill_knowledge(data)
        self.assertEqual(policy._skill_exp_cache[:2], (1000, 2000))
        del data["knowledge"]["skills"][0]["exp"]
        with self.assertRaises(ProtocolSchemaError):
            policy.consume_skill_knowledge(data)


if __name__ == "__main__":
    unittest.main()
