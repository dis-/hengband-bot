"""Producer offers bind only to the final key and named claim owner."""

import unittest
import tests  # noqa: F401
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.claim_register import observe
from hengbot.model import (PLAYER_CLASS_WARRIOR, Position, QuestState,
                           Snapshot, TVAL_LITE, SV_LITE_LANTERN,
                           TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE,
                           TVAL_ROD)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import QUEST_STATUS_REWARDED
from policy_fixtures import grid, item, player, set_completed_equipment_optimization
import policy_shop_fixture


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
        cursed = item("a", 23, 0, is_equipment=True, is_cursed=True)
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        board = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            equipment=[cursed], inventory=[scroll],
        )
        key = policy._town_remove_curse_key(board)
        claim = policy._claim_register.declare(
            "curse-enchant", observe(("curse",), 8, "equipment"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step, declaration.arguments[0]),
                         ("curse-enchant", "acting", "curse.remove.send",
                          policy._item_signature(cursed)))


class RumorDeclarationTest(policy_shop_fixture._TownShopFixtureBase):
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
    def test_no_shortage_declares_no_step(self):
        policy = HengbotPolicy()
        board = SimpleNamespace(in_town=False)
        with (patch.object(policy, "_cross_town_shortages",
                           return_value=()),
              patch.object(policy, "_cross_town_unobtainable_categories",
                           return_value=())):
            key = policy._cross_town_shopping_key(board)
        claim = policy._claim_register.declare(
            "cross-town", observe(("shopping",), 8, "shopping"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.cause),
                         ("cross-town", "releasing",
                          "no-unobtainable-shortage"))


class IdentificationDeclarationTest(unittest.TestCase):
    def test_device_source_request_declares_next_executor(self):
        policy = HengbotPolicy()
        target = item("a", TVAL_ROD, -1, aware=False, known=False)
        board = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True, inventory=[target],
        )
        self.assertIsNone(policy._town_device_processing_key(board))
        claim = policy._claim_register.declare(
            "identification", observe(("device",), 8, "knowledge"))
        policy._record_execution_declaration(claim, None, "identify:device")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step, declaration.arguments),
                         ("identification", "acting",
                          "identification.acquire-source",
                          ("normal", policy._item_signature(target))))


class CalibrationDeclarationTest(unittest.TestCase):
    def test_deferred_calibration_declares_no_step(self):
        policy = HengbotPolicy()
        board = SimpleNamespace()
        with patch.object(policy, "_defer_town_errand", return_value=True):
            key = policy._calibration_town_key(board)
        self.assertIsNone(key)
        claim = policy._claim_register.declare(
            "calibration", observe(("character",), 8, "calibration"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.cause),
                         ("calibration", "releasing",
                          "deferred-by-town-holder"))


class DepartureDeclarationTest(unittest.TestCase):
    def test_recall_confirmation_without_watch_declares_no_step(self):
        policy = HengbotPolicy()
        board = SimpleNamespace(player=SimpleNamespace(recalling=False))
        key = policy._dungeon_recall_confirmation_key(board)
        claim = policy._claim_register.declare(
            "departure", observe(("floor",), 8, "return"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.cause),
                         ("departure", "releasing",
                          "recall-confirmation-not-pending"))


class FundraisingDeclarationTest(unittest.TestCase):
    def test_shallow_ascent_declares_town_arrival(self):
        position = Position(6, 39)
        board = Snapshot(
            player(position.y, position.x, food=12000),
            {position: grid(position.y, position.x, upstairs=True)},
            [], floor_key=(2, 1, 0), width=80, height=20, turn=100,
        )
        policy = HengbotPolicy()
        key = policy._leave_fundraising_floor(board, allow_recall=False)
        claim = policy._claim_register.declare(
            "fundraising", observe(("floor",), 8, "fundraising"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step, declaration.continuation),
                         ("fundraising", "acting", "fundraising.ascend.send",
                          "fundraising.observe-town-arrival"))


class EquipmentTxnDeclarationTest(unittest.TestCase):
    def test_restore_terminal_declares_owed_stop(self):
        policy = HengbotPolicy()
        policy._equipment_transaction_owned_items = [("armour-a", "body")]
        policy._equipment_transaction_restore_terminal = (
            "equipment-transaction:restore-blocked-terminal"
        )
        board = SimpleNamespace(store=None)
        with (patch.object(policy, "_defer_town_errand", return_value=False),
              patch.object(policy, "_abandon_blocked_equipment_transaction")):
            key = policy._equipment_transaction_town_owner_key(board)
        claim = policy._claim_register.declare(
            "equipment-txn", observe(("transaction",), 8, "equipment"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step),
                         ("equipment-txn", "acting",
                          "equipment.restore-blocked-stop"))

    def test_posted_action_wait_keeps_operation_identity(self):
        policy = HengbotPolicy()
        claim = policy._claim_register.declare(
            "equipment-txn", observe(("transaction",), 8, "equipment"))
        policy._offer_execution_awaiting(
            "5", producer="equipment-txn", work_id="equipment:town:pending:a",
            operation_ref="command:42", expected_effect="equipment-action-confirmed",
            continuation="equipment.next-action",
        )
        policy._record_execution_declaration(
            claim, "5", "equipment-transaction:await-confirmation")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.state, declaration.operation_ref,
                          declaration.expected_effect),
                         ("awaiting", "command:42",
                          "equipment-action-confirmed"))
        self.assertIsNone(getattr(policy, "_execution_pending_post", None))


class EquipmentOptDeclarationTest(unittest.TestCase):
    def test_optimizer_outside_town_declares_no_step(self):
        policy = HengbotPolicy()
        board = SimpleNamespace(
            in_town=False, player=SimpleNamespace(class_id=PLAYER_CLASS_WARRIOR),
        )
        self.assertIsNone(policy._prepare_equipment_optimization(board))
        claim = policy._claim_register.declare(
            "equipment-opt", observe(("loadout",), 8, "optimizer"))
        policy._record_execution_declaration(claim, None, "equipment:optimizer")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.cause),
                         ("equipment-opt", "releasing",
                          "optimizer-context-unavailable"))


if __name__ == "__main__":
    unittest.main()
