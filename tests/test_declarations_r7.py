"""Recorded declaration gap classes, reduced to their producer handoffs."""

import unittest
import tests  # noqa: F401
from dataclasses import replace
from types import SimpleNamespace

from hengbot.claim_register import observe
from hengbot.model import (DUNGEON_ANGBAND, PLAYER_CLASS_WARRIOR, Position,
                           TVAL_DIGGING,
                           TVAL_SCROLL, TVAL_FOOD, TVAL_FLASK, TVAL_POTION,
                           SV_SCROLL_WORD_OF_RECALL, SV_FLASK_OIL)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit
from hengbot.home_errand import HomeErrandRequest
from test_policy import (Snapshot, StoreState, STORE_HOME, TVAL_LITE,
                         SV_LITE_LANTERN, grid, item, player)
from hengbot.policy_constants import CHARACTER_DUMP_MACRO, REST_MACRO
from policy_fixtures import set_completed_equipment_optimization


def bind(policy, family, key):
    claim = policy._claim_register.declare(
        family, observe(("r7-producer",), 8, "store-operation"))
    policy._record_execution_declaration(claim, key, policy.last_reason)
    return policy._claim_register.current.execution


def town_board(*, hurt=False):
    return Snapshot(
        player(10, 10, hp=200 if hurt else 255, max_hp=255,
               gold=2000, class_id=PLAYER_CLASS_WARRIOR),
        {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
        width=198, height=66, town_flag=True,
        inventory=[
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=9),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=9),
        ],
        equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN,
                        fuel=5000, is_equipment=True)],
        recall_dungeon_id=DUNGEON_ANGBAND, angband_recall_unlocked=True,
    )


class SurvivalRows(unittest.TestCase):
    def test_stuck_sequence_2_recovery_has_final_survival_offer(self):
        policy = HengbotPolicy()
        board = town_board(hurt=True)
        key = policy._town_special_key(board)
        self.assertEqual((key, policy.last_reason), (REST_MACRO, "town:recover"))
        declaration = bind(policy, "survival", key)
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "player.rest"))


class BookkeepingRows(unittest.TestCase):
    def test_tour_departure_dump_binds_bookkeeping(self):
        policy = HengbotPolicy()
        board = town_board()
        set_completed_equipment_optimization(policy)
        policy._deepest_level = 8
        policy._target_dungeon_id = DUNGEON_ANGBAND
        key = policy._town_special_key(board)
        self.assertEqual((key, policy.last_reason),
                         (CHARACTER_DUMP_MACRO, "town:character-dump"))
        declaration = bind(policy, "bookkeeping", key)
        self.assertEqual((declaration.producer, declaration.next_step),
                         ("bookkeeping", "character.dump-before-departure"))


class AtomicHomeRows(unittest.TestCase):
    def test_open_home_page_deposit_offers_composed_key(self):
        policy = HengbotPolicy()
        policy._store_visit = StoreVisit("town-errand", "deposit", STORE_HOME,
                                         opened_sequence=5)
        board = replace(town_board(), store=StoreState(STORE_HOME, []))
        deposit = board.inventory[0]
        policy._find_home_deposit = lambda _: deposit
        policy._prepare_home_visit_operation = lambda *args: True
        policy._home_deposit_batch = lambda *args: ((deposit, 1),)
        policy._home_deposit_key = lambda *args, **kwargs: "dr1\r"
        key = policy._open_home_deposit_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("dr1\r\x1b", "home:atomic-deposit"))
        self.assertEqual(policy._execution_offers_for()[-1][:2],
                         (key, "home-visit"))
        declaration = bind(policy, "home-visit", key)
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "home.operation.send"))

    def test_tour_staged_home_deposit_binds_final_key(self):
        policy = HengbotPolicy()
        visit = StoreVisit("town-errand", "deposit", STORE_HOME,
                           opened_sequence=5, posted_turn=20,
                           operation_posted=True, operation_key="db1\r\x1b",
                           operation_producer_family="home-visit")
        policy._store_visit = visit
        board = replace(town_board(), turn=20,
                        store=StoreState(STORE_HOME, []))
        key = policy._release_staged_store_operation(board)
        self.assertEqual(key, "db1\r\x1b")
        declaration = bind(policy, "home-visit", key)
        self.assertEqual((declaration.producer, declaration.next_step),
                         ("home-visit", "home.operation.send"))


class CalibrationRows(unittest.TestCase):
    def test_overweight_new_deposit_does_not_flag_completed_old_claim(self):
        policy = HengbotPolicy()
        policy._decision_sequence = 3738
        policy.last_reason = "home:atomic-deposit"
        register = policy._claim_register
        old = register.declare(
            "calibration", observe(("old-deposit",), 8, "calibration"))
        register.declare_execution(
            old.claim_id, work_id="old-deposit", producer="calibration",
            state="acting", next_step="home.operation.send")
        register.complete("old-deposit-observed")
        policy._store_visit = StoreVisit(
            "town-errand", "deposit", STORE_HOME, operation_posted=True,
            operation_released=False, posted_sequence=3738,
            operation_producer_family="calibration")
        policy._offer_execution(
            "5", producer="calibration", work_id="new-deposit",
            next_step="home.tail.send")
        self.assertEqual(policy._execution_offers_for()[-1][:2],
                         ("5", "calibration"))
        policy._record_decision_claim(town_board(), "5")
        self.assertNotEqual(policy.decision_claim["claim_id"], old.claim_id)
        self.assertEqual(policy.decision_claim["execution"]["work_id"],
                         "new-deposit")
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])

    def test_overweight_calibration_tail_keeps_calibration_owner(self):
        policy = HengbotPolicy()
        visit = StoreVisit("town-errand", "calibration", STORE_HOME,
                           opened_sequence=3737, posted_turn=20,
                           operation_posted=True, operation_key="di11\r\x1b",
                           operation_producer_family="calibration")
        policy._store_visit = visit
        board = replace(town_board(), turn=20,
                        store=StoreState(STORE_HOME, []))
        key = policy._release_staged_store_operation(board)
        declaration = bind(policy, "calibration", key)
        self.assertEqual((declaration.producer, declaration.next_step),
                         ("calibration", "home.operation.send"))


class HomeErrandRows(unittest.TestCase):
    def test_town_1941_knowledge_request_uses_errand_owner(self):
        policy = HengbotPolicy()
        board = town_board()
        request = HomeErrandRequest(("weapon", 23, 0), 1,
                                    "home-page", "combat-weapon")
        self.assertTrue(policy._file_home_errand(
            board, request, knowledge_current=False))
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("home-scan-incomplete",))
        key = policy._choose_key(board)
        self.assertEqual(policy.last_reason,
                         "home-errand:request-knowledge:combat-weapon")
        declaration = bind(policy, "home-errand", key)
        self.assertEqual(declaration.next_step, "home.knowledge.request")


class HomeScanRows(unittest.TestCase):
    def test_town_1185_page_seek_has_home_scan_offer(self):
        policy = HengbotPolicy()
        policy._no_teleport_rearm_pending = True
        board = replace(town_board(), store=StoreState(STORE_HOME, []),
                        inventory=[], equipment=[
                            item("main_hand", TVAL_DIGGING, 1,
                                 is_equipment=True)])
        key = policy._home_rearm_key(board)
        self.assertEqual((key, policy.last_reason),
                         (" ", "home:seek-combat-weapon-page"))
        declaration = bind(policy, "home-scan", key)
        self.assertEqual((declaration.producer, declaration.next_step),
                         ("home-scan", "home.page.advance"))


class EquipmentTransactionRows(unittest.TestCase):
    def test_town_1919_stale_home_action_offers_store_noop_key(self):
        policy = HengbotPolicy()
        policy.last_reason = (
            "equipment-transaction:stale-identity-invalidated:"
            "deposit:eda4854047084365")
        key = policy._equipment_home_outcome(
            "5", label="deposit-stale-worn", effect="transaction-replanned")
        self.assertEqual(key, "5")
        self.assertEqual(policy._execution_offers_for()[-1][:2],
                         ("\r", "equipment-txn"))
        declaration = bind(policy, "equipment-txn", "\r")
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "equipment.home.deposit-stale-worn"))

    def test_town_1907_posted_action_wait_is_an_acting_wait_command(self):
        policy = HengbotPolicy()
        policy._prepare_equipment_optimization = lambda _: None
        policy._equipment_transaction_session = SimpleNamespace(
            executable=True, pending_action=object(),
            posted_command_id="posted-1907", target_loadout_id="town-1907",
            unconfirmed_observations=0)
        policy._claim_register.declare(
            "equipment-txn", observe(("transaction",), 8, "transaction"))
        board = town_board()
        key = policy._equipment_transaction_town_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("5", "equipment-transaction:await-confirmation"))
        self.assertEqual(policy._execution_offers_for()[-1][:2],
                         ("5", "equipment-txn"))
        policy._record_decision_claim(board, key)
        self.assertEqual(policy.decision_claim["execution"]["state"], "acting")
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(getattr(policy, "_execution_pending_post", None))

    def test_town_1904_leave_uses_visit_owner_without_operation_family(self):
        policy = HengbotPolicy()
        policy._store_visit = StoreVisit(
            "equipment-transaction", "equipment-work", STORE_HOME)
        policy._home_entry_operation_posted = True
        board = replace(town_board(), store=StoreState(STORE_HOME, []))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "home:leave-after-one-operation"))
        self.assertEqual(policy.decision_claim["owner"], "equipment-txn")
        self.assertEqual(policy.decision_claim["execution"]["producer"],
                         "equipment-txn")
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])

    def test_town_1907_pending_action_has_owner_matched_offer(self):
        policy = HengbotPolicy()
        holder = policy._claim_register.declare(
            "equipment-txn", observe(("transaction",), 8, "transaction"))
        policy._equipment_transaction_session = SimpleNamespace(
            pending_action=object(), complete=False,
            target_loadout_id="recorded-town-1907")
        key = policy._town_holder_wait_key(holder, town_board())
        self.assertEqual((key, policy.last_reason),
                         ("5", "equipment-transaction:await-confirmation"))
        declaration = bind(policy, "equipment-txn", key)
        self.assertEqual((declaration.producer, declaration.next_step),
                         ("equipment-txn", "equipment.action.observe"))

    def test_tour_2654_home_leave_uses_operation_owner(self):
        policy = HengbotPolicy()
        board = replace(town_board(), store=StoreState(STORE_HOME, []))
        policy._store_visit = StoreVisit(
            "equipment-transaction", "equipment-work", STORE_HOME,
            operation_producer_family="equipment-txn")
        policy._home_atomic_withdraw_pending = (("weapon", 23, 0), 0, 20, 0)
        key = policy._shop(board)
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "home:leave-after-one-operation"))
        declaration = bind(policy, "equipment-txn", key)
        self.assertEqual((declaration.producer, declaration.next_step),
                         ("equipment-txn", "store.leave.send"))


if __name__ == "__main__":
    unittest.main()
