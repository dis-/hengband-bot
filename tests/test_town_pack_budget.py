"""#47 / #119 third recurrence: immutable boards and a shared slot budget.

ATTACH WALL: no Python checkpoint was captured. Each stop board attaches a
fresh policy, the preceding recorded Home knowledge answer and the recorded
fundraising facts. The established recorded-policy helper supplies static
game definitions; its older calibration is not claimed to be this character's
calibration. The skill census cache is constructed to isolate town work.
Stop at the first divergent key. Executor responses below are explicitly
constructed command boundaries, not live responses to the new action.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime writes
import ast
import copy
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from hengbot.cli import _consume_response_sequence, _ExecutorInputPort, _send_new_decision_key
from hengbot.item_reservation import reserved_item_command, store_item_key
from hengbot.model import STORE_HOME, TVAL_SCROLL, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY
from hengbot.town_pack_budget import incoming_slots, permits, pressure_deposit
from hengbot.town_terminal import TerminalRef, terminal_admission
from tests import test_input_executor as executor_harness
from tests.test_esp_threat_rest_recorded import _policy


FIXTURE = Path(__file__).parent / "fixtures/overflow-root-20261028.json.gz"
SHA256 = "794486145fba9316f799e3ec33b331b07e4e479b9dfedcf3470cacdb769cdbdf"


class TownPackBudgetTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        cls.records = json.loads(gzip.decompress(FIXTURE.read_bytes()))

    def attached(self, index):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        record = self.records[index]
        policy = _policy(directory, {})
        home = next(row for row in reversed(record["states"])
                    if row.get("knowledge", {}).get("category") == "home")
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        _consume_response_sequence(
            [json.dumps(home)], policy, lambda key: True, {},
            knowledge_ledger_path=directory / "knowledge.jsonl")
        raw = record["states"][-1]
        board = parse_snapshot(raw)
        policy.prime(board)
        facts = record["decisions"][-1]
        policy._fundraising_mode = facts["fundraising"]["mode"]
        policy._planned_mining_runs = facts["fundraising"]["planned_runs"]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return policy, board, raw

    def test_three_captured_stops_choose_a_preserving_next_step_and_follow_posts_it(self):
        for index, enforced in ((i, flag) for i in range(3) for flag in (False, True)):
            with self.subTest(capture=index, enforced=enforced):
                policy, board, raw = self.attached(index)
                policy._town_claim_bar_enforced = enforced
                self.assertEqual(self.records[index]["decisions"][-1]["reason"],
                                 "town:blocked:overflow-no-legal-disposal")
                self.assertEqual(len(board.inventory), 20)
                candidate = policy._find_home_deposit(board)
                self.assertIsNotNone(candidate)
                self.assertEqual(policy._retention_reservation(board, candidate), 0)
                key = policy.choose_key(board)
                self.assertIn(policy.last_reason, {"shop:travel", "home:atomic-deposit"})
                self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
                game = executor_harness.FaithfulHookGame()
                game.state = copy.deepcopy(raw)
                game.screen = executor_harness.command_screen(board.turn)
                after = copy.deepcopy(raw)
                after["turn"] += 1
                game.states = [after]
                game.screens = [executor_harness.command_screen(after["turn"])]
                _, _, executor = self.make(game)
                self.assertEqual(executor.observe_boundary(
                    deadline=time.monotonic() + 2).outcome, "ready")
                port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                          request_budget=2, policy=policy)
                _send_new_decision_key(
                    port, json.dumps(raw), key, None, set(), in_store=False,
                    snapshot=board, decision={"sequence": policy._decision_sequence,
                                             "reason": policy.last_reason, "key": key})
                self.assertEqual(port.last_result.outcome, "completed")
                self.assertTrue(game.accepted)
                self.assertNotIn("p", game.accepted)

    def test_budget_allows_only_observed_room_or_zero_slot_operations(self):
        board = parse_snapshot(self.records[1]["states"][-1])
        four = replace(board, inventory=board.inventory[:19])
        five = replace(board, inventory=board.inventory[:18])
        self.assertFalse(permits(four, 1))
        self.assertTrue(permits(four, 0))
        self.assertTrue(permits(five, 1))
        self.assertFalse(permits(five, 2))
        self.assertTrue(permits(board, 0))

    def test_every_production_overflow_call_enables_legal_relief(self):
        # The low-level destroy primitive remains compatible with existing
        # callers, but no production path may use it as a terminal stop
        # without trying the preserving remedies. Guard against new bypasses.
        calls = []
        source = Path(__file__).resolve().parents[1] / "src" / "hengbot"
        for path in source.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "_town_overflow_destroy_key"):
                    calls.append((path.name, node.lineno))
                    enabled = next((kw.value for kw in node.keywords if kw.arg == "try_relief"), None)
                    self.assertIsInstance(enabled, ast.Constant, calls[-1])
                    self.assertIs(enabled.value, True, calls[-1])
        self.assertTrue(calls)

    def test_terminal_overflow_retries_a_legal_home_route_before_blocking(self):
        policy, board, _ = self.attached(2)
        key = policy._town_overflow_destroy_key(board, try_relief=True)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)

    def test_terminal_overflow_observes_unknown_home_stock_before_giving_up(self):
        policy, board, _ = self.attached(2)
        policy._invalidate_home_observation()
        key = policy._town_overflow_destroy_key(board, try_relief=True)
        self.assertEqual((key, policy.last_reason), ("~9\x1b", "home:request-knowledge-scan"))

    def test_full_home_fallback_reaches_the_real_store_sale_selector(self):
        policy, board, _ = self.attached(2)
        candidate = policy._find_home_deposit(board)
        # Constructed: Home has refused this visit. Keep all other signatures
        # reserved so that the existing normal sale finders cannot take them.
        policy._home_deposit_abandoned = True
        for item in board.inventory:
            if item.slot != candidate.slot:
                signature = policy._item_signature(item)
                policy._town_visit_purchases.add(signature)
                policy._town_visit_purchase_quantities[signature] = item.count
        raw_home = next(row for row in reversed(self.records[2]["states"])
                        if row.get("store", {}).get("store_type") == STORE_HOME)
        outlet = policy._town_organization_sale_store(board, candidate)
        self.assertIsNotNone(outlet)
        store = replace(parse_snapshot(raw_home).store, store_type=outlet, items=[])
        sale_board = replace(board, store=store)
        self.assertIn(candidate, policy._current_store_sale_candidates(sale_board))

    def test_home_take_and_purchase_cannot_spend_the_fourth_slot(self):
        policy, board, _ = self.attached(1)
        four = replace(board, inventory=board.inventory[:19])
        # Constructed known new kind, with a valid shelf address and price.
        shelf_board = next(parse_snapshot(row) for row in self.records[1]["states"]
                           if row.get("type") == "store" and row["store"]["store_type"] != STORE_HOME)
        item = replace(shelf_board.store.items[0], tval=TVAL_SCROLL, sval=99,
                       known=True, aware=True, count=1, price=1)
        self.assertEqual(incoming_slots(four, item, 1), 1)
        self.assertFalse(policy._store_purchase_fits_pack(four, item))
        for kind in ("buy", "withdraw"):
            with self.subTest(kind=kind):
                self.assertIsNone(store_item_key(policy, four, kind, item,
                                                 "shop-buy" if kind == "buy" else "home-errand",
                                                 quantity=1))
        # A completed prior deposit is credited only on its new observation.
        five = replace(four, inventory=four.inventory[:-1])
        self.assertTrue(policy._store_purchase_fits_pack(five, item))
        self.assertIsNotNone(store_item_key(policy, five, "withdraw", item,
                                            "home-errand", quantity=1))

    def test_recorded_atomic_withdrawal_keeps_four_slots_until_a_deposit_lands(self):
        facts = next(d for d in reversed(self.records[1]["decisions"])
                     if d["reason"] == "home:atomic-withdraw")
        raw = next(row for row in reversed(self.records[1]["states"])
                   if row["turn"] == facts["turn"] and row["type"] == "player_turn")
        captured = parse_snapshot(raw)
        self.assertEqual(len(captured.inventory), 19)
        for freed_first in (False, True):
            with self.subTest(freed_first=freed_first):
                policy, _, _ = self.attached(1)
                take = facts["home_atomic_withdraw"]
                signature = tuple(take["selected_signature"])
                policy._shopping_approach_store_type = STORE_HOME
                policy._home_pending_item = signature
                policy._home_pending_quantity = take["quantity"]
                policy._home_pending_quantities[signature] = take["quantity"]
                policy._home_page_size = 52  # recorded Home page_size
                # Constructed control: only the already observed one-slot
                # deposit effect differs; no promise of a later sale is credit.
                board = (replace(captured, inventory=captured.inventory[:-1])
                         if freed_first else captured)
                key = policy._atomic_home_withdraw_dispatch_key(board, board.player.position)
                if freed_first:
                    self.assertEqual(key, "5pj5\r\x1b")
                    self.assertIsNotNone(policy._home_atomic_withdraw_pending)
                else:
                    self.assertIsNone(key)
                    self.assertIsNone(policy._home_atomic_withdraw_pending)

    def test_stack_merge_costs_no_slot_but_a_different_inscription_does(self):
        board = parse_snapshot(self.records[0]["states"][-1])
        item = board.inventory[0]
        self.assertEqual(incoming_slots(board, item, 1), 0)
        self.assertEqual(incoming_slots(board, replace(item, inscription="other"), 1), 1)
        self.assertEqual(incoming_slots(board, replace(item, known=False), 1), 1)

    def test_staff_use_cannot_unstack_into_the_reserve(self):
        policy, board, _ = self.attached(0)
        staff = next(item for item in board.inventory if item.tval == 55 and item.count > 1)
        self.assertIsNone(reserved_item_command(policy, board, "staff", staff))
        roomy = replace(board, inventory=board.inventory[:10])
        self.assertIsNotNone(reserved_item_command(policy, roomy, "staff", staff))

    def test_reward_admission_reserves_the_whole_visible_pile(self):
        board = parse_snapshot(self.records[0]["states"][-1])
        policy = HengbotPolicy()
        self.assertFalse(terminal_admission(
            policy, board, TerminalRef("quest-reward", (22,))).admitted)

    def test_equipment_takeoff_and_stack_wield_consult_the_same_budget(self):
        policy, board, _ = self.attached(0)
        worn = next(item for item in board.equipment if item.slot in EQUIPMENT_SLOT_KEY)
        four = replace(board, inventory=board.inventory[:19])
        result = policy._equipment_mutation.request_takeoff(
            four, "test", EQUIPMENT_SLOT_KEY[worn.slot], policy=policy)
        self.assertIsNone(result.key)
        self.assertEqual(result.report, "town-pack-budget")
        # Constructed: wield one item from a two-item pack stack, so the old
        # occupant needs an additional slot rather than replacing a pack slot.
        stack = replace(worn, slot="a", count=2, to_h=worn.to_h + 1)
        four = replace(four, inventory=[stack, *four.inventory[1:]])
        result = policy._equipment_mutation.request_wield(
            four, "test", stack, worn.slot, EQUIPMENT_SLOT_KEY, policy=policy)
        self.assertIsNone(result.key)
        self.assertEqual(result.report, "town-pack-budget")

    def test_town_floor_pickup_cannot_consume_reserved_slots(self):
        policy, board, _ = self.attached(0)
        here = board.grid_at(board.player.position)
        grids = dict(board.grids)
        grids[here.position] = replace(here, object_count=2)
        four = replace(board, inventory=board.inventory[:19], grids=grids)
        self.assertIsNone(policy._current_floor_item_key(
            four, pickup_reason="pickup", trigger_reason="pickup"))
        five = replace(four, inventory=four.inventory[:-1])
        policy._position_changed = True
        self.assertIsNone(policy._current_floor_item_key(
            five, pickup_reason="pickup", trigger_reason="pickup"))
        self.assertIsNone(policy._pending_loot_pickup)

    def test_open_chest_collection_yields_to_pack_relief_in_town(self):
        policy, board, _ = self.attached(0)
        here = board.grid_at(board.player.position)
        grids = dict(board.grids)
        grids[here.position] = replace(here, object_count=2, object_tvals=(TVAL_SCROLL,))
        board = replace(board, inventory=board.inventory[:19], grids=grids)
        # Constructed opened-chest state on the captured town tile.
        policy._chest_position = here.position
        policy._chest_phase_counts = {"open": 1}
        self.assertIsNone(policy._chest_processing_key(board, []))

    def test_automatic_pickup_tiles_are_budgeted_by_routes_and_the_walk_executor(self):
        policy, board, _ = self.attached(2)
        neighbor = policy._walkable_neighbors(board, board.player.position)[0]
        grids = dict(board.grids)
        grids[neighbor] = replace(grids[neighbor], object_count=1, object_tvals=(10,))
        four = replace(board, inventory=board.inventory[:19], grids=grids)
        self.assertNotIn(neighbor, policy._walkable_neighbors(four, four.player.position))
        self.assertEqual(policy._step_toward(four, neighbor), "5")
        self.assertEqual(policy.last_reason, "warning:blocked-step")
        five = replace(four, inventory=four.inventory[:-1])
        self.assertIn(neighbor, policy._walkable_neighbors(five, five.player.position))

    def test_native_travel_cannot_hide_automatic_pickups_between_boards(self):
        for freed_first in (False, True):
            with self.subTest(freed_first=freed_first):
                policy, board, _ = self.attached(2)
                neighbor = policy._walkable_neighbors(board, board.player.position)[0]
                grids = dict(board.grids)
                grids[neighbor] = replace(grids[neighbor], object_count=1, object_tvals=(10,))
                board = replace(board, inventory=board.inventory[:18 if freed_first else 19], grids=grids)
                goal = policy._town_map.store_position(STORE_HOME)
                macro = "\x1b`n(."
                key = policy._town_travel_key(board, goal, macro, "shop:travel")
                self.assertEqual(key, macro if freed_first else None)

    def test_pressure_deposits_preserve_reservations_and_purpose_purchases(self):
        policy, board, _ = self.attached(2)
        candidate = policy._find_home_deposit(board)
        self.assertTrue(pressure_deposit(policy, board, candidate))
        policy._town_visit_purchases.add(policy._item_signature(candidate))
        self.assertFalse(pressure_deposit(policy, board, candidate))
        for item in board.inventory:
            if policy._retention_reservation(board, item):
                self.assertFalse(pressure_deposit(policy, board, item))
