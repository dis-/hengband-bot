"""O1: constructed class-16 boards exercise the real acceptance producer."""

import tests  # noqa: F401 -- runtime-file isolation

from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import (
    Snapshot, SV_LITE_TORCH, SV_POTION_HEALING, SV_POTION_SPEED,
    TVAL_LITE, TVAL_POTION, TVAL_SWORD,
)
from hengbot.policy import HengbotPolicy
from hengbot.quest_strategies import acceptance_hp_floor, class_throwing_items, load_quest_strategies
from policy_fixtures import item, player


class MagicEaterAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = load_quest_strategies(Path("strategy/quests"))

    def board(self, quest_id, *, class_id=16, no_healing=False):
        # DECLARED CONSTRUCTED: identical wielded results for each class,
        # isolating the acceptance floor from class/stat damage estimation.
        force = self.profiles[quest_id].required_force
        hp = acceptance_hp_floor(force["no_healing_tier"] if no_healing else force, class_id)
        character = replace(
            player(10, 10, class_id=class_id, level=5, hp=hp, max_hp=hp,
                   main_hand_blows=1, main_hand_to_h=0,
                   main_hand_to_d=9 if quest_id == 34 else 12),
            melee_skill=100, race_id=25,  # Zombie, matching the viewing character.
        )
        inventory = [item("t", TVAL_LITE, SV_LITE_TORCH,
                          count=class_throwing_items(force, class_id)["lit_torch"])]
        if not no_healing:
            inventory += [item("s", TVAL_POTION, SV_POTION_SPEED),
                          item("h", TVAL_POTION, SV_POTION_HEALING, count=2)]
        return Snapshot(
            character, {}, [], inventory=inventory,
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=1, damage_dice_sides=1)],
        )

    def readiness(self, board, quest_id):
        policy = HengbotPolicy(quest_strategies=self.profiles)
        ready = policy._approved_strategy_force_ready(board, self.profiles[quest_id])
        return ready, policy.fixed_quest_readiness_state()["strategy_force"]

    def test_magic_eater_passes_normal_floor_that_warrior_rejects(self):
        # D17/n1-c Lv7 (2026-10-30): the Q1 class-16 fallback melee floor is the kill-time 36/10=3.6.
        # D20 (2026-10-30): the Q1 warrior floor is 13.23 on the torch premise (real torch damage).
        for quest_id, floor, warrior_floor in ((34, 3.5, 8), (1, 3.6, 13.23)):
            with self.subTest(quest_id=quest_id):
                board = self.board(quest_id)
                ready, details = self.readiness(board, quest_id)
                self.assertTrue(ready, details)
                self.assertEqual(details["dps"]["required"], floor)
                self.assertGreaterEqual(details["dps"]["measured"], floor)
                # #47 (2026-10-31): Q1's class 16 is measured by its thrown
                # torches (16.76/action, QUEST_1 torch_throw_output_by_class);
                # the same melee stays below the warrior's floor.
                melee = details.get("melee_dps", details["dps"]["measured"])
                self.assertEqual(details["dps"]["measured"], 16.76 if quest_id == 1 else melee)
                self.assertLess(melee, warrior_floor)
                warrior = replace(board, player=replace(board.player, class_id=0))
                ready, unchanged = self.readiness(warrior, quest_id)
                self.assertFalse(ready)
                # Bad-luck HP floors (2026-10-30): the Q1 class-16 floor 96 is above the warrior's 88.
                self.assertEqual(unchanged["failed"], ["dps"])
                self.assertEqual(unchanged["dps"]["required"], warrior_floor)
                self.assertEqual(unchanged["dps"]["measured"], melee)

    def test_magic_eater_no_healing_tier_uses_its_class_floor(self):
        for quest_id in (34, 1):
            with self.subTest(quest_id=quest_id):
                board = self.board(quest_id, no_healing=True)
                ready, details = self.readiness(board, quest_id)
                self.assertTrue(ready, details)
                warrior = replace(board, player=replace(board.player, class_id=0))
                self.assertFalse(self.readiness(warrior, quest_id)[0])

    def test_magic_eater_still_requires_melee_damage(self):
        for quest_id in (34, 1):
            for no_healing in (False, True):
                with self.subTest(quest_id=quest_id, no_healing=no_healing):
                    board = self.board(quest_id, no_healing=no_healing)
                    board = replace(board, player=replace(board.player, main_hand_to_d=0))
                    ready, details = self.readiness(board, quest_id)
                    if quest_id == 1:
                        # #47: Q1's class 16 fights with its carried torches;
                        # weak melee (its fallback) is no gate.
                        self.assertTrue(ready, details)
                        self.assertLess(details["melee_dps"], 3.6)
                        continue
                    self.assertFalse(ready)
                    self.assertIn("dps", details["failed"])

    def test_normal_hp_floor_is_unchanged(self):
        for quest_id in (34, 1):
            with self.subTest(quest_id=quest_id):
                board = self.board(quest_id)
                board = replace(board, player=replace(board.player,
                                hp=board.player.hp - 1, max_hp=board.player.max_hp - 1))
                ready, details = self.readiness(board, quest_id)
                self.assertFalse(ready)
                self.assertEqual(details["failed"], ["hp"])
                # D17: the Q1 class-16 torch plan has one HP floor for both tiers
                # (98, then 23 with the real torch damage, now the bad-luck 96).
                self.assertEqual(details["hp"]["required"], 10 if quest_id == 34 else 96)

    def test_no_healing_hp_floor_is_unchanged(self):
        for quest_id in (34, 1):
            with self.subTest(quest_id=quest_id):
                board = self.board(quest_id, no_healing=True)
                board = replace(board, player=replace(board.player,
                                hp=board.player.hp - 1, max_hp=board.player.max_hp - 1))
                ready, details = self.readiness(board, quest_id)
                self.assertFalse(ready)
                # D17: Q1 class 16 has one HP floor for both tiers.
                self.assertEqual(details["failed"], (["speed_potions", "heal_potions"] if quest_id == 34
                                                     else ["hp", "speed_potions", "heal_potions"]))

    def test_other_classes_keep_warrior_floor(self):
        for quest_id, floor in ((34, 8), (1, 28)):
            for class_id in (-1, 1, 15, 17):
                with self.subTest(quest_id=quest_id, class_id=class_id):
                    ready, details = self.readiness(self.board(quest_id, class_id=class_id), quest_id)
                    self.assertFalse(ready)
                    self.assertEqual(details["dps"]["required"], floor)

    def test_level_one_magic_eater_enters_q34_without_potions(self):
        # Owner 2026-10-29: the verification Lv1 zombie Magic-Eater (max HP 35, melee DPS 3.96, 58 gold)
        # met neither Q34 tier and stopped in town; its class floors were lowered (HP 30, DPS 3.5).
        board = self.board(34, no_healing=True)
        board = replace(board, player=replace(board.player, level=1, hp=35, max_hp=35, main_hand_to_d=5))
        ready, details = self.readiness(board, 34)
        self.assertTrue(ready, details)
        self.assertEqual(details["failed"], [])
        self.assertLess(details["dps"]["measured"], 6)
        warrior = replace(board, player=replace(board.player, class_id=0))
        self.assertFalse(self.readiness(warrior, 34)[0])

    def test_warrior_still_passes_with_sufficient_melee_damage(self):
        for quest_id in (34, 1):
            for no_healing in (False, True):
                with self.subTest(quest_id=quest_id, no_healing=no_healing):
                    board = self.board(quest_id, class_id=0, no_healing=no_healing)
                    board = replace(board, player=replace(board.player, main_hand_to_d=100))
                    self.assertTrue(self.readiness(board, quest_id)[0])
