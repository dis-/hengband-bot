"""DECLARED CONSTRUCTED pins for L5:3484 and A2028:279.

Those tails lack a restorable checkpoint and the complete relevant Home pages.
These pins exercise the observed-location alternatives, not a fabricated
continuous replay of their historical missing-item diagnosis.
"""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import tests  # noqa: F401
from hengbot.claim_register import observe, ClaimOwner
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import (
    EquipmentTransaction, EquipmentTransactionPlan, PHASE_HOME_PREPARE, PHASE_EQUIP,
    PHASE_HOME_FINALIZE)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import STORE_HOME, StoreState
from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.monrace_knowledge import MonraceKnowledge
from policy_fixtures import item, store_item, seed_character_calibration
from test_s33_batch_admission import corridor


def target():
    return item("a", 38, 1, name="Leather Scale Mail [11,+0]", known=True,
                fully_known=True, is_equipment=True, ac=11)


def session_for(gear, *, copies=1):
    identity, move = equipment_identity(gear), equipment_move_identity(gear)
    actions = (EquipmentTransaction(PHASE_HOME_PREPARE, "withdraw", "home:missing:0",
                item_identity=identity, move_identity=move),)
    actions += tuple(EquipmentTransaction(PHASE_EQUIP, "equip", "home:missing:0",
                    slot, identity, move) for slot in ("body", "outer")[:copies])
    return EquipmentTransactionSession(EquipmentTransactionPlan(actions, (), copies))


def attached(board, session):
    policy = HengbotPolicy()
    policy.prime(board)
    policy._town_claim_bar_enforced = True
    policy._equipment_transaction_session = session
    session.opened_sequence = 1
    # Use the production session goal: its opening sequence/action plan is
    # the identity the real completion path closes after observed work.
    goal = policy._claim_operation_goal(board, ClaimOwner.EQUIPMENT_TXN,
                                        "equipment-transaction:constructed", "transaction")
    claim = policy._claim_register.declare("equipment-txn", goal, floor=board.floor_key)
    policy._claim_register.declare_execution(claim.claim_id, producer="equipment-txn",
        work_id="equipment:constructed", state="acting", next_step="equipment.next-action",
        expected_effect="equipment-action-confirmed", continuation="equipment.next-action")
    return policy


class ReconciliationTest(unittest.TestCase):
    def test_already_carried_withdrawal_runs_outside_equip(self):
        gear = target()
        board = replace(corridor(), inventory=(gear,))
        session = session_for(gear)
        policy = attached(board, session)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        claim = policy._claim_register.current
        action = session.current_action
        policy._claim_register.declare_execution(claim.claim_id, producer="equipment-txn",
            work_id=f"equipment:{session.target_loadout_id}:0", state="acting",
            next_step="equipment.next-action",
            arguments=(action.kind, action.target_slot, action.item_identity),
            expected_effect="equipment-action-confirmed", continuation="equipment.next-action")
        key = policy.choose_key(board)
        self.assertEqual(session.index, 1)
        self.assertTrue(key.startswith("w"), repr(key))
        self.assertEqual(policy.last_reason, "equipment-transaction:equip")
        self.assertFalse(session.blockers)
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
        self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])

    def test_one_copy_cannot_complete_two_targets(self):
        gear = target()
        session = session_for(gear, copies=2)
        board = replace(corridor(), inventory=(gear,))
        self.assertFalse(session.reconcile_carried(board))
        self.assertEqual(session.index, 0)

    def test_unrelated_planned_equip_keeps_its_post_observation_protocol(self):
        gear = target()
        action = EquipmentTransaction(PHASE_EQUIP, "equip", "pack:target:0",
            "body", equipment_identity(gear), equipment_move_identity(gear))
        session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 1))
        board = replace(corridor(), equipment=(replace(gear, slot="body"),))
        self.assertFalse(session.reconcile_carried(board))
        self.assertEqual(session.index, 0)

    def test_already_worn_target_completes_without_home(self):
        gear = target()
        board = replace(corridor(), equipment=(replace(gear, slot="body"),))
        session = session_for(gear)
        policy = attached(board, session)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        key = policy.choose_key(board)
        self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertTrue(session.complete)
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertFalse(policy._equipment_transaction_owned_items)
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])

    def test_partial_home_page_cannot_prove_missing(self):
        gear = target()
        board = replace(corridor(), store=StoreState(STORE_HOME, [],
                        stock_num=60, page_top=0, page_size=52))
        session = session_for(gear)
        policy = attached(board, session)
        key = policy.choose_key(board)
        self.assertEqual(key, " ")
        self.assertEqual(policy.last_reason, "equipment-transaction:seek-home-page")
        self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
        self.assertFalse(session.blockers)
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])

    def test_complete_empty_home_proves_missing(self):
        gear = target()
        board = replace(corridor(), store=StoreState(STORE_HOME, [],
                        stock_num=0, page_top=0, page_size=52))
        session = session_for(gear)
        policy = attached(board, session)
        key = policy.choose_key(board)
        self.assertTrue(any(b.startswith("withdraw-item-missing:") for b in session.blockers))
        self.assertEqual(key, "\x1b")
        self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])

    def test_old_checkpoint_normalizes_new_observation_state(self):
        policy = HengbotPolicy()
        del policy._equipment_transaction_posted_catalog_update
        del policy._equipment_optional_failure_departure
        del policy._equipment_transaction_home_pages
        policy._policy_state_version = 3
        normalize_policy_state(policy)
        self.assertIsNone(policy._equipment_transaction_posted_catalog_update)
        self.assertIsNone(policy._equipment_optional_failure_departure)
        self.assertIsNone(policy._equipment_transaction_home_pages)

    def test_all_observed_home_pages_prove_absence(self):
        wares = [store_item("a", 80, 35, name=f"Food {index}") for index in range(3)]
        board = replace(corridor(), store=StoreState(STORE_HOME, [wares[0]],
                        stock_num=3, page_top=0, page_size=1))
        session = session_for(target())
        policy = attached(board, session)
        for index in range(3):
            current = replace(board, turn=100 + index, store=StoreState(
                STORE_HOME, [wares[index]], stock_num=3, page_top=index, page_size=1))
            key = policy.choose_key(current)
            if index < 2:
                self.assertEqual(key, " ")
                self.assertFalse(session.blockers)
            else:
                self.assertTrue(any(b.startswith("withdraw-item-missing:") for b in session.blockers))
                self.assertEqual(key, "\x1b")
                self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertTrue(policy._equipment_catalog.home_scan_complete)

    def test_equipping_a_split_stack_confirms_by_physical_identity(self):
        gear = target()
        original = replace(gear, count=2)
        session = session_for(original)
        board = replace(corridor(), inventory=(gear,))
        policy = attached(board, session)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "equipment-transaction:equip")
        self.assertTrue(policy.confirm_key_posted(key))
        after = replace(board, turn=101, inventory=(), equipment=(replace(gear, slot="body"),))
        policy.choose_key(after)
        self.assertTrue(session.complete)

    def test_posted_deposit_updates_catalog_only_after_observed_effect(self):
        gear = target()
        board = replace(corridor(), inventory=(gear,), store=StoreState(
            STORE_HOME, [], stock_num=0, page_top=0, page_size=52))
        action = EquipmentTransaction(PHASE_HOME_FINALIZE, "deposit", "pack:target:0",
            item_identity=equipment_identity(gear), move_identity=equipment_move_identity(gear))
        session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 1))
        policy = attached(board, session)
        key = policy.choose_key(board)
        self.assertEqual(key, "da")
        self.assertTrue(policy.confirm_key_posted(key))
        self.assertFalse(any(owned.origin == "home" for owned in policy._equipment_catalog.items))
        self.assertIsNotNone(policy._equipment_transaction_posted_catalog_update)
        ware = store_item("a", gear.tval, gear.sval, name=gear.name, known=True,
                          fully_known=True, is_equipment=True, ac=gear.ac)
        # DECLARED CONSTRUCTED effect board for exactly the key above.
        after = replace(board, turn=101, inventory=(), store=StoreState(
            STORE_HOME, [ware], stock_num=1, page_top=0, page_size=52))
        policy.choose_key(after)
        self.assertTrue(session.complete)
        self.assertIsNone(policy._equipment_transaction_posted_catalog_update)
        self.assertEqual(sum(owned.origin == "home" for owned in policy._equipment_catalog.items), 1)

    def optional_policy(self, directory, *, inventory=()):
        gear = replace(target(), slot="body")
        board = replace(corridor(), equipment=(gear,), inventory=inventory,
                        player=replace(corridor().player, class_id=0,
                                       stat_cur=(18, 10, 10, 18), stat_use=(18, 10, 10, 18)))
        policy = HengbotPolicy(monrace_knowledge={1: MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=0, rarity=1)})
        policy.prime(board)
        policy._confirmed_loadout_path = Path(directory) / "confirmed.json"
        seed_character_calibration(policy, board)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        policy._town_store_attempted[STORE_HOME] = board.turn
        policy._refresh_carried_equipment_catalog(board)
        # DECLARED CONSTRUCTED failed physical target: the worn item remains
        # selected by the real optimizer; there is no restoration operation.
        policy._equipment_transaction_failed_items.add("identity:" + equipment_identity(gear))
        preparation = policy._prepare_equipment_optimization(board)
        self.assertEqual(preparation.blockers, ("equipment-transaction-failed",))
        self.assertIsNone(policy._equipment_transaction_session)
        policy._record_confirmed_loadout(board)
        return policy, board, preparation

    def test_optional_failure_records_real_current_loadout_and_reason(self):
        with TemporaryDirectory() as directory:
            policy, board, preparation = self.optional_policy(directory)
            self.assertTrue(policy._equipment_departure_ready(board))
            self.assertTrue(policy._confirmed_loadout_path.is_file())
            policy._decision_input_snapshot = board
            policy.last_reason = "descend"
            policy.confirm_key_posted(">")
            self.assertEqual(policy.equipment_optimization_state()["optional_failure_departure"]["reason"],
                             "optional-optimization-failure-confirmed-loadout")
            self.assertTrue(policy._current_worn_loadout_confirmed(board, preparation))
            policy._town_claim_bar_enforced = True
            policy._char_dump_done_this_visit = True
            key = policy.choose_key(board)
            self.assertIsNone(policy.decision_claim["declaration_mismatch"])
            self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
            self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])

    def test_optional_failure_cannot_depart_with_debt_or_missing_depth_ability(self):
        with TemporaryDirectory() as directory:
            policy, board, preparation = self.optional_policy(directory)
            policy._equipment_transaction_owned_items.append((equipment_move_identity(target()), "body"))
            self.assertFalse(policy._safe_optional_equipment_failure_departure(board, preparation))
            policy._equipment_transaction_owned_items.clear()
            policy._target_dungeon_id = 1
            board = replace(board, dungeon_recall_depths={1: 31}, angband_recall_unlocked=True)
            self.assertFalse(policy._equipment_departure_ready(board))
            self.assertIsNone(policy._equipment_optional_failure_departure)

    def test_optional_failure_uses_shallow_walk_in_and_records_only_posted_departure(self):
        with TemporaryDirectory() as directory:
            policy, board, preparation = self.optional_policy(directory)
            policy._target_dungeon_id = 1
            board = replace(board, dungeon_recall_depths={1: 31})
            self.assertIn("resist_chaos", policy._missing_required_abilities(board, 31))
            before = policy._confirmed_loadout_path.stat().st_mtime_ns
            self.assertTrue(policy._equipment_departure_ready(board))
            self.assertTrue(policy._retire_actionless_equipment_failure(board))
            self.assertIsNone(policy._equipment_optional_failure_departure)
            self.assertEqual(policy._confirmed_loadout_path.stat().st_mtime_ns, before)
            failed_ids = policy._equipment_optional_failure_pending["failed_item_ids"]
            self.assertTrue(failed_ids)
            policy._decision_input_snapshot = board
            policy.last_reason = "descend"
            policy.confirm_key_posted("5")
            self.assertIsNone(policy._equipment_optional_failure_departure)
            policy.confirm_key_posted(">")
            record = policy._equipment_optional_failure_departure
            self.assertEqual(record["reason"], "optional-optimization-failure-confirmed-loadout")
            self.assertEqual(record["depth"], 1)
            self.assertEqual(record["item_ids"], sorted(policy._validated_confirmed_loadout().item_ids))
            self.assertEqual(record["failed_item_ids"], failed_ids)

    def test_optional_failure_pure_check_never_creates_confirmation(self):
        with TemporaryDirectory() as directory:
            policy, board, preparation = self.optional_policy(directory)
            policy._confirmed_loadout_path.unlink()
            policy._confirmed_loadout = None
            policy._confirmed_loadout_loaded = False
            self.assertTrue(policy._safe_optional_equipment_failure_departure(board, preparation))
            self.assertFalse(policy._confirmed_loadout_path.exists())
            self.assertIsNone(policy._equipment_optional_failure_departure)
            self.assertTrue(policy._equipment_departure_ready(board))
            self.assertFalse(policy._confirmed_loadout_path.exists())
            policy._decision_input_snapshot = board
            policy.last_reason = "descend"
            policy.confirm_key_posted(">")
            self.assertTrue(policy._confirmed_loadout_path.is_file())
            self.assertTrue(policy._current_worn_loadout_confirmed(board, preparation))

    def test_optional_failure_uses_recall_snapshot_and_walk_in_min_depth(self):
        from hengbot.dungeon_knowledge import DungeonInfo
        with TemporaryDirectory() as directory:
            policy, board, preparation = self.optional_policy(directory)
            policy._target_dungeon_id = 1
            board = replace(board, angband_recall_unlocked=True,
                            recall_dungeon_id=1, recall_depth=31, dungeon_recall_depths={})
            self.assertFalse(policy._equipment_departure_ready(board))
            self.assertFalse(policy._retire_actionless_equipment_failure(board))
            policy._dungeon_knowledge[1] = DungeonInfo(1, "Constructed", 31, 100, 1)
            board = replace(board, angband_recall_unlocked=False, recall_depth=0)
            self.assertFalse(policy._equipment_departure_ready(board))

    def test_optional_failure_fixed_quest_entry_ignores_unrelated_deep_recall(self):
        from hengbot.quest_knowledge import QuestInfo
        from policy_fixtures import grid
        with TemporaryDirectory() as directory:
            policy, board, preparation = self.optional_policy(directory)
            policy._target_dungeon_id = 1
            policy._quest_knowledge[99] = QuestInfo(99, "Constructed", 0, 5, 0)
            here = board.player.position
            board = replace(board, angband_recall_unlocked=True, dungeon_recall_depths={1: 31},
                            grids={**board.grids, here: grid(here.y, here.x,
                                   has_quest_enter=True, quest_id=99)})
            self.assertFalse(policy._equipment_departure_ready(board))
            key = policy._fixed_quest_enter_key(board, 99)
            self.assertEqual(key, ">")
            self.assertIsNone(policy._equipment_optional_failure_departure)
            # An unrelated shallow gate probe cannot change the posted quest's
            # diagnostic depth; posting reads the actual entrance again.
            self.assertTrue(policy._equipment_departure_ready(board, destination_depth=1))
            policy._decision_input_snapshot = board
            policy.confirm_key_posted(key)
            self.assertEqual(policy._equipment_optional_failure_departure["depth"], 5)

    def test_optional_failure_final_walk_in_gate_uses_its_own_depth(self):
        from hengbot.model import TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL
        recall = item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10, known=True)
        with TemporaryDirectory() as directory:
            policy, board, preparation = self.optional_policy(directory, inventory=(recall,))
            policy._target_dungeon_id = 1
            board = replace(board, angband_recall_unlocked=True, dungeon_recall_depths={1: 31})
            policy._map_predicate_snapshot = board
            self.assertFalse(policy._equipment_departure_ready(board))
            self.assertTrue(policy._dungeon_entry_allowed(board, via_recall=False, destination_depth=1))
            self.assertFalse(policy._dungeon_entry_allowed(board, via_recall=True, destination_depth=31))

    def test_optional_failure_posted_recall_records_selected_landing(self):
        from hengbot.model import TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL
        recall = item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10, known=True)
        with TemporaryDirectory() as directory:
            policy, board, preparation = self.optional_policy(directory, inventory=(recall,))
            policy._target_dungeon_id = 1
            board = replace(board, angband_recall_unlocked=True,
                            recall_dungeon_id=1, recall_depth=10)
            self.assertTrue(policy._dungeon_entry_allowed(
                board, via_recall=True, destination_depth=10))
            policy._decision_input_snapshot = board
            policy.last_reason = "town:repetition-depart:recall"
            self.assertIsNone(policy._pending_recall_dungeon_id)
            key = policy._read_key(board, recall)
            policy.confirm_key_posted(key)
            record = policy._equipment_optional_failure_departure
            self.assertEqual(record["depth"], 10)
            self.assertTrue(record["posted"])
            self.assertTrue(record["failed_item_ids"])
            landing = replace(board, town_flag=False,
                              floor_key=(1, 10, 0), turn=board.turn + 1)
            policy._observe(landing)
            self.assertEqual(policy.equipment_optimization_state()["optional_failure_departure"], record)
            policy._observe(replace(board, turn=board.turn + 2))
            self.assertIsNone(policy._equipment_optional_failure_departure)


if __name__ == "__main__":
    unittest.main()
