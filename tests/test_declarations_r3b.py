"""Producer offers bind only to the final key and named claim owner."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.claim_register import observe
from hengbot.model import (PLAYER_CLASS_WARRIOR, Position, QuestState,
                           Snapshot, TVAL_LITE, SV_LITE_LANTERN)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import QUEST_STATUS_REWARDED
from policy_fixtures import grid, item, player, set_completed_equipment_optimization
from policy_shop_fixture import _TownShopFixtureBase


class BookkeepingDeclarationTest(unittest.TestCase):
    def test_save_offer_binds_only_its_final_key(self):
        policy = HengbotPolicy()
        policy._periodic_save_requested = True
        board = SimpleNamespace()
        with patch.object(policy, "_periodic_filler_is_safe", return_value=True):
            key = policy._periodic_game_save_key(board, "6")
        self.assertEqual(key, "\x13")
        claim = policy._claim_register.declare(
            "bookkeeping", observe(("save",), 8, "periodic"))
        policy._record_execution_declaration(claim, "6", policy.last_reason)
        self.assertIsNone(policy._claim_register.current.execution)

        policy._periodic_save_requested = True
        with patch.object(policy, "_periodic_filler_is_safe", return_value=True):
            key = policy._periodic_game_save_key(board, "6")
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step),
                         ("bookkeeping", "acting", "game.save.send"))

    def test_skill_request_no_step_has_producer_cause(self):
        policy = HengbotPolicy()
        board = SimpleNamespace(protocol_version=2)
        self.assertIsNone(policy._skill_exp_request_key(board))
        claim = policy._claim_register.declare(
            "bookkeeping", observe(("skill-exp",), 8, "knowledge"))
        policy._record_execution_declaration(claim, None, "periodic:skill-exp")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.cause),
                         ("bookkeeping", "releasing",
                          "skill-list-protocol-unavailable"))


class TownMobDeclarationTest(unittest.TestCase):
    def test_friendly_attack_declares_exact_monster(self):
        policy = HengbotPolicy()
        target = SimpleNamespace(
            index=7, race_id=33, position=Position(1, 2), distance=1,
            friendly=True, pet=False,
        )
        board = SimpleNamespace(
            in_town=True, dungeon_level=0,
            player=SimpleNamespace(position=Position(1, 1)),
            visible_monsters=(target,),
        )
        key = policy._town_kill_mob_key(board)
        claim = policy._claim_register.declare(
            "survival", observe(("monster",), 8, "town-combat"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.state, declaration.next_step,
                          declaration.arguments),
                         ("acting", "town-monster.attack-friendly", (7, 33)))


class CurseEnchantDeclarationTest(unittest.TestCase):
    def test_remove_curse_declares_selected_item(self):
        policy = HengbotPolicy()
        cursed = SimpleNamespace(is_cursed=True)
        scroll = SimpleNamespace(is_scroll=True, aware=True, sval=1, count=1)
        board = SimpleNamespace(
            in_town=True, player=SimpleNamespace(blind=False, confused=False),
            equipment=(cursed,), inventory=(scroll,),
        )
        with (patch.object(policy, "_claim_errand_hold"),
              patch.object(policy, "_has_cursed_equipment", return_value=True),
              patch.object(policy, "_curse_unremovable", return_value=False),
              patch.object(policy, "_first_item", return_value=scroll),
              patch.object(policy, "_item_signature", return_value=("item", 7)),
              patch.object(policy, "_read_key", return_value="r-a")):
            key = policy._town_remove_curse_key(board)
        claim = policy._claim_register.declare(
            "curse-enchant", observe(("curse",), 8, "equipment"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step, declaration.arguments[0]),
                         ("curse-enchant", "acting", "curse.remove.send",
                          ("item", 7)))


class RumorDeclarationTest(_TownShopFixtureBase):
    def test_inn_batch_declares_read_count(self):
        board = Snapshot(
            player(10, 10, gold=900, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10),
             Position(10, 11): grid(10, 11, building_type=0)},
            [], inventory=self._strict_supplies(recall=3),
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN,
                            fuel=5000, is_equipment=True)],
            quests={14: QuestState(14, status=QUEST_STATUS_REWARDED)},
        )
        policy = HengbotPolicy()
        set_completed_equipment_optimization(policy)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:rumor-batch")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.next_step,
                          declaration.arguments),
                         ("rumor", "rumor.read-batch", (40,)))


class CrossTownDeclarationTest(unittest.TestCase):
    def test_shopping_funds_wait_declares_required_gold(self):
        policy = HengbotPolicy()
        policy._observed_departure_prices["food"] = (100, 1)
        board = SimpleNamespace(
            in_town=False, player=SimpleNamespace(gold=0),
        )
        with (patch.object(policy, "_cross_town_shortages",
                           return_value=(("food", 1),)),
              patch.object(policy, "_cross_town_unobtainable_categories",
                           return_value=("food",)),
              patch.object(policy, "_cross_town_candidate_order",
                           return_value=(2,)),
              patch.object(policy, "_effective_town_id", return_value=1)):
            key = policy._cross_town_shopping_key(board)
        claim = policy._claim_register.declare(
            "cross-town", observe(("funds",), 8, "shopping"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step, declaration.arguments[0]),
                         ("cross-town", "acting", "cross-town.wait-for-funds",
                          policy._cross_town_shopping_funds["required_gold"]))


class IdentificationDeclarationTest(unittest.TestCase):
    def test_device_source_request_declares_next_executor(self):
        policy = HengbotPolicy()
        target = SimpleNamespace(is_equipment=False)
        board = SimpleNamespace(in_town=True)
        with (patch.object(policy, "_claim_errand_hold"),
              patch.object(policy, "_first_item", return_value=target),
              patch.object(policy, "_find_identification_source",
                           return_value=None),
              patch.object(policy, "_item_signature", return_value=("device", 1)),
              patch.object(policy, "_request_identification")):
            self.assertIsNone(policy._town_device_processing_key(board))
        claim = policy._claim_register.declare(
            "identification", observe(("device",), 8, "knowledge"))
        policy._record_execution_declaration(claim, None, "identify:device")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step, declaration.arguments),
                         ("identification", "acting",
                          "identification.acquire-source",
                          ("normal", ("device", 1))))


if __name__ == "__main__":
    unittest.main()
