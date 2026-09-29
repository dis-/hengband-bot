"""Record-only execution declarations survive checkpoints and claim transitions."""

import pickle
import unittest
from pathlib import Path
from types import SimpleNamespace
import gzip
import json
from unittest.mock import patch
from dataclasses import replace

from hengbot.claim_register import (
    ClaimRegister, declaration_mismatch, observe, reach,
)
from hengbot.home_errand import HomeErrandRequest
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ENTRANCE_TRAVEL_MACRO, HengbotPolicy
from hengbot.policy_types import StoreVisit
from test_policy import (
    Snapshot, StoreState, STORE_ALCHEMIST, SV_SCROLL_REMOVE_CURSE,
    STORE_HOME, TVAL_CHAOS_BOOK, TVAL_SCROLL, grid, item, player, store_item,
)


SHORT_ROUTE = Path(__file__).parent / "fixtures/s33-live-short-entrance-224.json.gz"


def short_route_board():
    with gzip.open(SHORT_ROUTE, "rt", encoding="utf-8") as stream:
        recorded = json.load(stream)
    return parse_snapshot(recorded["snapshot"], load_monrace_knowledge(
        Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc")))


class ExecutionDeclarationTest(unittest.TestCase):
    def test_town_page_declarations_do_not_change_keys_with_s33_switch(self):
        outcomes = []
        for enforced in (False, True):
            policy = HengbotPolicy()
            policy._town_claim_bar_enforced = enforced
            policy._decision_sequence = 47
            key = policy._shop(SimpleNamespace(store=None))
            outcomes.append((key, policy.last_reason))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_home_scan_holder_wait_declares_named_observation(self):
        policy = HengbotPolicy()
        board = short_route_board()
        policy.prime(board)
        policy._decision_sequence = 41
        policy._home_knowledge_scan_requested = True
        policy._home_knowledge_scan_epoch = 7
        claim = policy._claim_register.declare(
            "home-scan", observe(("home-knowledge-current",), 8, "knowledge"))
        key = policy._town_holder_wait_key(claim, board)
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual(key, "5")
        self.assertEqual((declaration.producer, declaration.next_step,
                          declaration.work_id),
                         ("home-scan", "home.knowledge.observe",
                         "home-knowledge:7"))

    def test_open_home_scan_completion_declares_page_exit(self):
        board = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=[], store=StoreState(STORE_HOME, []),
        )
        policy = HengbotPolicy()
        key = policy.choose_key(board)
        declaration = policy.decision_claim["execution"]
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "home:scan-complete-from-open-page"))
        self.assertEqual((declaration["producer"], declaration["next_step"],
                          declaration["expected_effect"]),
                         ("home-scan", "store.leave.send", "outside-store"))

    def test_direct_home_page_deposit_declares_exact_item_and_count(self):
        policy = HengbotPolicy()
        policy._decision_sequence = 31
        policy._item_signature = lambda item: ("torch", 39, 0)
        policy._retention_surplus = lambda board, item: 3
        item = SimpleNamespace(slot="h", count=5, charges=0, tval=39, sval=0)
        board = SimpleNamespace(inventory=(item,), player=SimpleNamespace(gold=42))
        key = policy._home_deposit_key(board, item)
        claim = policy._claim_register.declare(
            "home-visit", observe(("inventory",), 8, "store-operation"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual(key, "dh3\r")
        self.assertEqual((declaration.state, declaration.next_step,
                          declaration.arguments),
                         ("acting", "home.deposit.send",
                         ("h", 3, ("torch", 39, 0))))

    def test_rejected_home_page_deposit_declares_leave(self):
        policy = HengbotPolicy()
        policy._decision_sequence = 32
        policy._item_signature = lambda item: ("torch", 39, 0)
        item = SimpleNamespace(slot="h", count=5, charges=0)
        board = SimpleNamespace(inventory=(item,), player=SimpleNamespace(gold=42))
        policy._last_sell_sig = ("h", ("torch", 39, 0), 5, 0, 1, 42)
        policy._store_sell_stuck_count = 999
        key = policy._home_deposit_key(board, item)
        claim = policy._claim_register.declare(
            "home-visit", observe(("store",), 8, "store-operation"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((key, declaration.producer, declaration.next_step),
                         ("\x1b", "home-visit", "store.leave.send"))

    def test_shop_invalid_page_declares_leave_under_shop_seller(self):
        policy = HengbotPolicy()
        policy._decision_sequence = 44
        key = policy._shop(SimpleNamespace(store=None))
        claim = policy._claim_register.declare(
            "shop-sell", observe(("store",), 8, "store-operation"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((key, declaration.producer, declaration.next_step,
                          declaration.expected_effect),
                         ("\x1b", "shop-sell", "store.leave.send",
                          "outside-store"))

    def test_shop_buy_declares_exact_page_command(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, price=100)
        board = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=[], store=StoreState(STORE_ALCHEMIST, [ware]),
        )
        policy = HengbotPolicy()
        policy._decision_sequence = 45
        with (patch.object(policy, "_next_purchase", return_value=ware),
              patch.object(policy, "_purchase_quantity", return_value=1)):
            key = policy._shop(board)
        claim = policy._claim_register.declare(
            "shop-buy", observe(("inventory",), 8, "store-operation"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((key, declaration.producer, declaration.next_step),
                         ("pa\r", "shop-buy", "shop.purchase.send"))

    def test_shop_one_shot_composition_wait_is_not_a_posted_purchase(self):
        ware = store_item("a", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, price=100)
        observed = StoreState(STORE_ALCHEMIST, [ware], page_top=0)
        outside = Snapshot(
            player(10, 10),
            {Position(10, 10): replace(
                grid(10, 10), store_number=STORE_ALCHEMIST)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[], store=None,
        )
        policy = HengbotPolicy()
        policy._decision_sequence = 45
        policy._shop_observation = (observed, 45)
        policy._store_visit = StoreVisit(
            "town-errand", "shopping", STORE_ALCHEMIST)
        with (patch.object(policy, "_next_purchase", return_value=ware),
              patch.object(policy, "_purchase_quantity", return_value=1)):
            wait_key = policy._atomic_shop_transaction_key(outside)
        claim = policy._claim_register.declare(
            "shop-buy", observe(("inventory",), 8, "store-operation"))
        policy._record_execution_declaration(claim, wait_key, policy.last_reason)
        self.assertEqual(policy._claim_register.current.execution.next_step,
                         "shop.one-shot.dispatch")
        policy.confirm_key_posted(wait_key)
        self.assertEqual(policy._claim_register.current.execution.state,
                         "acting")
        self.assertIsNone(policy._claim_register.current.execution.operation_ref)
        operation_key = policy._release_staged_store_operation(
            replace(outside, store=observed))
        self.assertEqual(operation_key, "pa\r\x1b")
        policy._record_execution_declaration(
            policy._claim_register.current, operation_key, policy.last_reason)
        self.assertEqual(policy._claim_register.current.execution.next_step,
                         "shop.one-shot.send")

    def test_home_errand_filing_leave_names_its_request(self):
        board = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=[], store=StoreState(STORE_HOME, []),
        )
        policy = HengbotPolicy()
        policy._decision_sequence = 46
        policy._home_errand.file(
            HomeErrandRequest(("weapon", 1, 2), 1, "home-page", "combat-weapon"),
            knowledge_current=True,
        )
        key = policy._shop(board)
        claim = policy._claim_register.declare(
            "home-errand", observe(("inventory",), 8, "store-operation"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((key, declaration.producer, declaration.next_step),
                         ("\x1b", "home-errand", "store.leave.send"))

    def test_refused_transport_remains_named_acting_work(self):
        policy = HengbotPolicy()
        policy._decision_sequence = 32
        claim = policy._claim_register.declare(
            "home-visit", observe(("inventory",), 8, "store-operation"))
        policy._offer_execution(
            "dh3\r", producer="home-visit", work_id="deposit:torch",
            next_step="home.deposit.send", expected_effect="inventory-decreased",
        )
        policy._record_execution_declaration(claim, "dh3\r", "home:deposit")
        policy.refuse_key_posting("home:deposit", "dh3\r")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.state, declaration.next_step,
                          declaration.operation_ref, declaration.evidence),
                         ("acting", "transport.resolve-refusal", None,
                          "posting-refused"))
        self.assertIsNone(policy._execution_pending_post)
        policy.confirm_key_posted("dh3\r")
        self.assertEqual(policy._claim_register.current.execution.state,
                         "acting")

    def test_session_installation_offers_first_action_before_send(self):
        policy = HengbotPolicy()
        policy._decision_sequence = 33
        action = SimpleNamespace(kind="takeoff", item_identity="armour-a")
        session = SimpleNamespace(current_action=action, executable=True,
                                  required_context="legacy")
        policy._set_equipment_transaction_session(session)
        claim = policy._claim_register.declare(
            "equipment-txn", observe(("transaction",), 8, "equipment"))
        policy._record_execution_declaration(claim, "", "equipment:session-installed")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.state, declaration.next_step,
                          declaration.arguments, declaration.operation_ref),
                         ("acting", "equipment.next-action",
                          ("takeoff", "armour-a"), None))

    def test_revision_and_checkpoint_round_trip(self):
        register = ClaimRegister()
        claim = register.declare("store-router", reach((31, 150)))
        first = register.declare_execution(
            claim.claim_id, work_id="route:entrance:31,150",
            producer="store-router", state="acting", next_step="route.resume",
            arguments=("entrance", (31, 150)), budget_ref="town-travel",
        )
        self.assertEqual(first.revision, 1)
        restored = pickle.loads(pickle.dumps(register))
        self.assertEqual(restored.current.execution, first)
        restored.await_observation()
        self.assertEqual(restored.current.execution, first)
        second = restored.declare_execution(
            claim.claim_id, work_id=first.work_id, producer="store-router",
            state="awaiting", operation_ref="decision:223:travel",
            expected_effect="arrive:31,150", continuation="route.resume",
        )
        self.assertEqual(second.revision, 2)
        self.assertEqual(restored.current.as_dict()["execution"]["state"],
                         "awaiting")
        self.assertIsNone(restored.declare_execution(
            claim.claim_id + 1, work_id="wrong", producer="store-router",
            state="acting", next_step="route.resume"))

    def test_predeclaration_checkpoint_reads_class_default(self):
        register = ClaimRegister()
        claim = register.declare("store-router", reach((31, 150)))
        del claim.__dict__["execution"]
        restored = pickle.loads(pickle.dumps(register))
        self.assertIsNone(restored.current.execution)
        self.assertIsNone(restored.current.as_dict()["execution"])

    def test_1154_short_entrance_route_has_resume_step(self):
        # Recorded 223/224: #140 Reach(31,150), stopped five cells short.
        board = short_route_board()
        policy = HengbotPolicy()
        policy.prime(board)
        policy._decision_sequence = 223
        policy._claim_register._next_id = 140
        key = policy._town_travel_key(
            board, Position(31, 150), ENTRANCE_TRAVEL_MACRO,
            "town:travel-entrance",
        )
        self.assertEqual(key, ENTRANCE_TRAVEL_MACRO)
        claim = policy._claim_register.declare(
            "store-router", reach((31, 150)), floor=board.floor_key,
        )
        policy._record_execution_declaration(claim, key, "town:travel-entrance")
        declaration = policy._claim_register.current.execution
        self.assertEqual((claim.claim_id, declaration.state,
                          declaration.next_step, declaration.arguments),
                         (140, "acting", "route.resume",
                          ("entrance", (31, 150))))
        policy.confirm_key_posted(key)
        self.assertEqual(policy._claim_register.current.execution.state,
                         "awaiting")
        policy._town_holder_wait_key(policy._claim_register.current, board)
        self.assertEqual(policy._claim_register.current.execution.state,
                         "acting")
        self.assertEqual(policy._claim_register.current.execution.next_step,
                         "route.resume")
        mismatch = declaration_mismatch(
            policy._claim_register.current, "silent",
            "ownership:holder-silent:store-router")
        self.assertEqual((mismatch["inferred"], mismatch["declared"]["state"],
                          mismatch["declared"]["next_step"]),
                         ("silent", "acting", "route.resume"))

    def test_store_router_short_entrance_walk_declares_final_direction(self):
        board = short_route_board()
        policy = HengbotPolicy()
        policy.prime(board)
        policy._decision_sequence = 224
        policy._town_travel_key = lambda *args: None
        policy._town_map_goal_step = lambda *args: Position(32, 145)
        claim = policy._claim_register.declare(
            "store-router", reach((31, 150)), floor=board.floor_key)
        key = policy._town_holder_wait_key(claim, board)
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.next_step,
                          declaration.arguments),
                         ("store-router", "route.resume",
                          ("entrance", (31, 150))))

    def test_1904_home_withdraw_effect_closes_named_operation(self):
        # The recorded Home transfer was observed before visit state retired.
        policy = HengbotPolicy()
        policy._decision_sequence = 26
        visit = SimpleNamespace(opened_sequence=25)
        policy._home_operation_visit = lambda producer: visit
        board = SimpleNamespace(turn=140385)
        key = "CRa\x1b"
        self.assertTrue(policy._compose_home_operation(
            board, key, "Ra", producer_family="home-visit"))
        claim = policy._claim_register.declare(
            "home-visit", observe(("inventory",), 8, "store-operation"))
        policy._record_execution_declaration(claim, key, "home:atomic-withdraw")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.state, declaration.next_step,
                          declaration.work_id),
                         ("acting", "home.operation.send", "home-operation:25:Ra"))
        policy.confirm_key_posted(key)
        self.assertEqual(policy._claim_register.current.execution.operation_ref,
                         f"decision:26:{key}")
        closed = policy._claim_register.complete("home-withdraw-observed")
        self.assertEqual((closed.execution.state, closed.execution.evidence),
                         ("done", "home-withdraw-observed"))
        mismatch = declaration_mismatch(
            closed, "awaiting", "equipment-transaction:atomic-deposit")
        self.assertEqual((mismatch["inferred"], mismatch["declared"]["state"],
                          mismatch["declared"]["evidence"]),
                         ("awaiting", "done", "home-withdraw-observed"))

    def test_2322_calibration_takeoff_retains_posted_action(self):
        # Recorded 42/43: 'ta' under calibration #30, then holder-silent.
        policy = HengbotPolicy()
        policy._decision_sequence = 42
        policy._calibration_session_owned = lambda: True
        session = SimpleNamespace(
            target_loadout_id="recorded-strip", index=0,
            prepare=lambda *args: True,
        )
        action = SimpleNamespace(kind="takeoff", target_slot="main_hand",
                                 item_identity="9c2eb7e52ebfe13f")
        self.assertTrue(policy._prepare_equipment_transaction_command(
            session, action, None, "ta", ("town", 0)))
        policy._claim_register._next_id = 30
        claim = policy._claim_register.declare(
            "calibration", observe(("transaction",), 8, "calibration"))
        policy._record_execution_declaration(
            claim, "ta", "equipment-transaction:takeoff")
        self.assertEqual(policy._claim_register.current.execution.next_step,
                         "equipment.next-action")
        policy.confirm_key_posted("ta")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.state, declaration.operation_ref,
                          declaration.expected_effect),
                         ("awaiting", "decision:42:ta",
                          "equipment-effect:takeoff:main_hand"))
        policy._record_execution_declaration(
            policy._claim_register.current, None,
            "ownership:holder-silent:calibration")
        mismatch = policy._decision_declaration_mismatch
        self.assertEqual((mismatch["inferred"], mismatch["declared"]["state"]),
                         ("silent", "awaiting"))

    def test_2134_rejected_stair_has_no_fabricated_post(self):
        # Recorded 1712: empty stair wait after a rejected descent candidate.
        board = short_route_board()
        policy = HengbotPolicy()
        policy.prime(board)
        policy._decision_sequence = 1712
        policy._pending_stair_command = (
            ">", board.floor_key, board.player.position, board.turn, board)
        policy._owner_may_select = lambda *args: False
        key = policy._suppress_pending_stair_command(board, ">")
        self.assertEqual(key, "")
        claim = policy._claim_register.declare(
            "departure", observe(("floor",), 350, "floor-change"))
        policy._claim_register.await_observation()
        policy._record_execution_declaration(
            policy._claim_register.current, key, "stair:await-observation")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.state, declaration.next_step,
                          declaration.operation_ref),
                         ("acting", "stair.post", None))
        self.assertEqual(policy._decision_declaration_mismatch["inferred"],
                         "unposted-await")
        self.assertIsNone(getattr(policy, "_execution_pending_post", None))
        mismatch = declaration_mismatch(
            policy._claim_register.current, "unposted-await",
            "stair:await-observation")
        self.assertEqual((mismatch["inferred"], mismatch["declared"]["state"],
                          mismatch["declared"]["operation_ref"]),
                         ("unposted-await", "acting", None))


if __name__ == "__main__":
    unittest.main()
