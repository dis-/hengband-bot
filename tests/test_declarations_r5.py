"""Pins for final-owner declarations at town producer return sites."""

import tests  # noqa: F401
import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.claim_register import observe
from hengbot.model import (Position, Snapshot, StoreState, STORE_HOME,
                           STORE_GENERAL, TVAL_POTION, TVAL_WAND,
                           SV_POTION_RESTORE_CON)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import FOOD_TYPE_MANA
from policy_fixtures import grid, item, player


def bind(policy, family, key):
    claim = policy._claim_register.declare(
        family, observe(("r5",), 8, "town"))
    policy._record_execution_declaration(claim, key, policy.last_reason)
    return policy._claim_register.current.execution


def town_board(*, store=None, entrance=False):
    here = Position(10, 10)
    cells = {here: replace(grid(10, 10),
                           store_number=STORE_HOME if entrance else -1),
             Position(10, 11): grid(10, 11)}
    return Snapshot(player(10, 10), cells, [], floor_key=(0, 0, 0),
                    town_flag=True, store=store)


class DeclarationReturnTest(unittest.TestCase):
    def test_home_step_off_offer_uses_final_home_owner(self):
        policy = HengbotPolicy()
        key = policy._town_entrance_step_off_key(
            town_board(entrance=True), "home:process-next-batch-item")
        declaration = bind(policy, "home-visit", key)
        self.assertIsNotNone(key)
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step),
                         ("home-visit", "acting", "departure.step-off-entrance"))

    def test_equipment_wait_step_off_rebinds_final_equipment_key(self):
        policy = HengbotPolicy()
        key = policy._town_entrance_step_off_key(
            town_board(entrance=True),
            "equipment-transaction:await-confirmation")
        declaration = bind(policy, "equipment-txn", key)
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "departure.step-off-entrance"))

    def test_shop_observation_leave_has_shop_buy_offer(self):
        policy = HengbotPolicy()
        board = town_board(store=StoreState(STORE_GENERAL, []))
        key = policy._choose_key(board)
        self.assertEqual(policy.last_reason, "shop:observe-and-leave")
        declaration = bind(policy, "shop-buy", key)
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "store.leave.send"))

    def test_home_shortage_leave_has_home_offer(self):
        policy = HengbotPolicy()
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        board = town_board(store=StoreState(STORE_HOME, []))
        with (patch.object(policy, "_town_space_deposit_actionable",
                           return_value=False),
              patch.object(policy, "_queue_home_catalogue_shortages",
                           return_value=True)):
            key = policy._choose_key(board)
        self.assertEqual(policy.last_reason, "home:queue-catalogue-shortage")
        declaration = bind(policy, "home-visit", key)
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "store.leave.send"))

    def test_one_operation_home_leave_has_home_offer(self):
        policy = HengbotPolicy()
        policy._home_entry_operation_posted = True
        board = town_board(store=StoreState(STORE_HOME, []))
        key = policy._choose_key(board)
        self.assertEqual(policy.last_reason, "home:leave-after-one-operation")
        declaration = bind(policy, "home-visit", key)
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "store.leave.send"))

    def test_recall_stockout_handoff_declares_leave(self):
        policy = HengbotPolicy()
        board = town_board(store=StoreState(STORE_GENERAL, []))
        with patch.object(policy, "_start_unobtainable_recall_stockout_mining",
                          return_value=True):
            key = policy._choose_key(board)
        self.assertEqual(policy.last_reason, "town:recall-stockout-mining")
        declaration = bind(policy, "fundraising", key)
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "store.leave.send"))

    def test_stat_restore_quaff_declares_survival(self):
        policy = HengbotPolicy()
        potion = item("a", TVAL_POTION, SV_POTION_RESTORE_CON)
        board = replace(town_board(), player=player(10, 10,
                                                   drained_stats=("con",)),
                        inventory=[potion])
        key = policy._stat_restore_quaff_key(board, [])
        declaration = bind(policy, "survival", key)
        self.assertEqual((key, declaration.next_step),
                         ("qa", "survival.quaff-stat-restore"))

    def test_mana_food_absorb_declares_survival(self):
        policy = HengbotPolicy()
        wand = item("d", TVAL_WAND, 1, charges=15)
        board = replace(town_board(), player=player(
            10, 10, food=100, food_type=FOOD_TYPE_MANA), inventory=[wand])
        key = policy._mana_food_survival_override_key(board)
        declaration = bind(policy, "survival", key)
        self.assertEqual((key, declaration.next_step),
                         ("Ed", "survival.absorb-mana-food"))

    def test_skill_request_offer_binds_on_first_decision(self):
        policy = HengbotPolicy()
        initial = town_board()
        board = replace(initial, protocol_version=3,
                        player=replace(initial.player, two_weapon_skill=None,
                                       shield_skill=None))
        self.assertEqual(policy.choose_key(board), "~f\x1b")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.next_step),
                         ("bookkeeping", "knowledge.skill-exp.request"))


if __name__ == "__main__":
    unittest.main()
