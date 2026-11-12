"""Real last boards; internal policy state below is DECLARED CONSTRUCTED.

These tails have no checkpoint. We stop at the first changed command and
never describe later captured boards as a continuation of that command.

Owner 2026-11-02 「満たせなければ採掘を1サイクル行い再度トライ。条件未達の
出発は拒否する。」: the forced visit departure leaves only when every
departure condition holds; with one unmet it starts one mining cycle
(town_end_mining).  Owner 2026-11-02 「購入に関する問題以外は採掘せずに
名前を付けて停止を採用」: only a purchase gap starts that cycle; any other
unmet condition stops.  The recorded boards fail home_catalog_ready alone, so
they stop (the one on a store entrance first steps off to read the Home
list); the departure mechanics are exercised on the same boards with Home's
catalogue complete (DECLARED CONSTRUCTED, ``catalogued``).
"""
import tests  # noqa: F401

from contextlib import contextmanager, redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import pickle
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot import cli
from hengbot.departure_readiness import ReadinessTable
from hengbot.model import QuestState
from hengbot.policy_constants import QUEST_STATUS_FINISHED
from hengbot.model import DUNGEON_YEEK_CAVE, Position, TVAL_POTION, SV_POTION_CURE_CRITICAL, TVAL_STAFF, SV_STAFF_IDENTIFY
from hengbot.policy import HengbotPolicy, REST_MACRO, TR_NO_TELE
from hengbot.policy_constants import ENTER_DUNGEON_MACRO, PACK_CAPACITY, READ_KEY, WAIT_KEY, _required_abilities_for_depth
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_town import VISIT_CLOSABLE_REASONS
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from minimum_table import board_policy, last_row
from policy_fixtures import grid, item

FIXTURES = Path(__file__).parent / "fixtures/keep-running-a0"
BOARDS = sorted(FIXTURES.glob("*.state.jsonl.gz"))


@contextmanager
def attribute_set(owner, name, value):
    """``name`` holds ``value`` for the block.  A plain set and restore: since
    988422f930 a TownVisit field is a forwarding property, which ``patch.object``
    cannot delete on the way out."""
    saved = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, saved)


def ready_board():
    return board_policy(last_row(BOARDS[0]))


def catalogued(policy):
    """DECLARED CONSTRUCTED: Home's catalogue complete (home_catalog_ready,
    the recorded boards' only unmet condition), so the departure may leave."""
    policy._equipment_catalog.home_scan_complete = True
    return policy


class MinimumTest(unittest.TestCase):
    def test_ordinary_identify_readiness_keeps_keywordless_strategy_override(self):
        policy, board, _ = ready_board()
        policy._equipment_optimization_last_depth = 1
        board = replace(board, inventory=[i for i in board.inventory
            if not (i.tval == TVAL_STAFF and i.sval == SV_STAFF_IDENTIFY)])
        for required in (True, False):
            # DECLARED CONSTRUCTED: the pre-existing quest strategy adapter.
            with self.subTest(required=required), patch.object(policy,
                    "_carry_procurement_strategy", lambda snapshot: SimpleNamespace(
                        engagement_plan={"carry_identify_staff": required})):
                self.assertEqual(policy._identify_staff_ready(board), not required)

    def test_minimum_is_pure_and_each_hard_leaf_blocks(self):
        policy, board, depth = ready_board()
        before = pickle.dumps(policy.__dict__)
        self.assertTrue(policy._departure_minimum(board, depth)["holds"])
        self.assertEqual(pickle.dumps(policy.__dict__), before)
        cases = {
            "recall_departure_ready": replace(board, inventory=[i for i in board.inventory if not i.is_recall_scroll]),
            "food_ready": replace(board, inventory=[i for i in board.inventory if not (i.is_food or i.is_wand_staff)]),
            "light_ready": replace(board, inventory=[i for i in board.inventory if not i.is_light],
                                   equipment=[i for i in board.equipment if not i.is_light]),
            "cure_critical_ready": replace(board, inventory=[i for i in board.inventory if not (i.is_potion and i.sval == SV_POTION_CURE_CRITICAL)]),
            "teleport_ready": replace(board, inventory=[i for i in board.inventory if not i.is_teleport_scroll]),
            "identify_staff_ready": replace(board, inventory=[i for i in board.inventory if not (i.tval == TVAL_STAFF and i.sval == SV_STAFF_IDENTIFY)]),
            "remove_curse_ready": replace(board, equipment=[replace(i, is_cursed=True) if i.slot == "main_hand" else i for i in board.equipment]),
            "temporary_status_clear": replace(board, player=replace(board.player, poisoned=True)),
            "hp_full": replace(board, player=replace(board.player, hp=board.player.hp - 1)),
            "mp_full": replace(board, player=replace(board.player, max_mp=board.player.mp + 1)),
            "depth_abilities": replace(board, player=replace(board.player, abilities=frozenset())),
            "equipment_observed": replace(board, equipment_observed=False),
            "teleport_items_safe": replace(board, equipment=[replace(i, known_flags=i.known_flags | {TR_NO_TELE}) if i.slot == "main_hand" else i for i in board.equipment]),
            "combat_weapon_ready": replace(board, equipment=[replace(i, tval=20) if i.slot == "main_hand" else i for i in board.equipment]),
            "inventory_weight_ready": replace(board, inventory=[replace(board.inventory[0], weight=100000)]),
            "free_pack_slots_ready": replace(board, inventory=[replace(board.inventory[0], weight=0)] * PACK_CAPACITY),
        }
        for leaf, changed in cases.items():
            with self.subTest(leaf=leaf):
                result = policy._departure_minimum(changed, 40 if leaf == "depth_abilities" else depth)
                self.assertFalse(result["holds"])
                self.assertIn(leaf, result["failed"])
        for name, value, leaf in (
            ("_home_atomic_withdraw_pending", ("posted",), "home_atomic_withdraw_clear"),
            ("_home_atomic_deposit_pending", ("posted",), "home_atomic_withdraw_clear"),
            ("_equipment_transaction_session", object(), "equipment_transfer_clear"),
            ("_equipment_transaction_owned_items", {"debt"}, "equipment_transfer_clear"),
            ("_equipment_transaction_restoring", True, "equipment_transfer_clear"),
            ("_equipment_transaction_restore_remainder", ("debt",), "equipment_transfer_clear"),
            ("_equipment_transaction_restore_terminal", True, "equipment_transfer_clear"),
            ("_equipment_transaction_posted_catalog_update", ("posted",), "equipment_transfer_clear"),
            ("_store_buy_inflight", ("posted",), "store_transfer_clear"),
            ("_batch_sell_pending", ("posted",), "store_transfer_clear"),
        ):
            with self.subTest(attribute=name), attribute_set(policy, name, value):
                result = policy._departure_minimum(board, depth)
                self.assertFalse(result["holds"])
                self.assertIn(leaf, result["failed"])

    def test_unknown_evidence_fails_closed(self):
        policy, board, depth = ready_board()
        result = policy._departure_minimum(replace(board, player=replace(board.player, stat_index=())), depth)
        self.assertFalse(result["holds"])
        self.assertIn("inventory_weight_ready", result["unknown"])
        del policy._home_atomic_withdraw_pending
        result = policy._departure_minimum(board, depth)
        self.assertIn("home_atomic_withdraw_clear", result["unknown"])
        self.assertFalse(result["holds"])

    def test_soft_work_and_one_free_slot_do_not_block(self):
        policy, board, depth = ready_board()
        policy._home_candidate_waiting = True
        policy._home_pending_item = ("unposted",)
        policy._home_pending_batch = [("unposted",)]
        policy._home_batch_review_items = [("unreviewed",)]
        policy._identification_need = "full"
        policy._equipment_catalog.home_scan_complete = False
        with patch.object(policy, "_equipment_departure_ready", side_effect=AssertionError("optimizer called")):
            while len(board.inventory) < PACK_CAPACITY - 1:
                board = replace(board, inventory=board.inventory + [replace(item("z", TVAL_POTION, 0), weight=0)])
            self.assertTrue(policy._departure_minimum(board, depth)["holds"])
            self.assertTrue(policy._dungeon_entry_allowed(board, via_recall=True,
                destination_depth=depth, minimum=True))

    def test_minimum_entry_mode_keeps_recall_depth_and_digger_invariants(self):
        policy, board, depth = ready_board()
        no_recall = replace(board, inventory=[i for i in board.inventory if not i.is_recall_scroll])
        self.assertFalse(policy._dungeon_entry_allowed(no_recall, via_recall=True,
            destination_depth=depth, minimum=True))
        self.assertFalse(policy._dungeon_entry_allowed(board, via_recall=True,
            destination_depth=81, minimum=True))
        policy._home_digger_withdraw_pending = True
        policy._visit_departure_committed = "departure-unsatisfiable"
        policy._town_blocked_reason = "repetition"
        self.assertFalse(policy._dungeon_entry_allowed(board, via_recall=False,
            destination_depth=1, minimum=True))
        self.assertEqual(policy._town_blocked_reason, "repetition")
        policy._home_digger_withdraw_pending = False
        policy._fundraising_mode = "mine"
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        self.assertTrue(policy._dungeon_entry_allowed(no_recall, via_recall=False,
            destination_depth=1, minimum=True))
        self.assertFalse(policy._dungeon_entry_allowed(no_recall, via_recall=True,
            destination_depth=1, minimum=True))


class DepartureTest(unittest.TestCase):
    def records(self, root):
        path = Path(root) / "keep-running-events.jsonl"
        return [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines()]

    def test_five_last_boards_cross_real_policy_or_driver_stop_boundary_once(self):
        for path in BOARDS:
            with self.subTest(capture=path.name), TemporaryDirectory() as root, patch.dict(
                    os.environ, HENGBOT_RUNTIME_DIR=root), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                decision = last_row(path.with_name(path.name.replace(".state.", ".decision.")))
                baseline = next(row for row in json.loads((FIXTURES / "baseline.json").read_text(encoding="utf-8"))
                                if row["capture"].split(".")[0] == path.name.split(".")[0])
                self.assertEqual(baseline["reason"], decision["reason"])
                self.assertEqual(baseline["base"], "4afde8ca")
                self.assertIn(decision["reason"], {"town:blocked:departure-unsatisfiable", "town:blocked:owner-retired-burst"})
                policy, board, depth = board_policy(last_row(path))
                self.assertTrue(policy._departure_minimum(board, depth)["holds"])
                cause = decision["reason"].removeprefix("town:blocked:")
                if cause == "owner-retired-burst":
                    # DECLARED CONSTRUCTED: terminal retirement counter/arbiter;
                    # the preserved final board is the only safety evidence.
                    policy._owner_retired_no_progress_count = 2
                    policy.last_reason = "town:blocked:owner-retired"
                    policy._owner_retired_progress = dict(visit=(board.town_id, board.floor_key),
                        routes={}, effects=set(), admitted=set(), sequence=policy._decision_sequence)
                    key = cli._handle_owner_retirement(SimpleNamespace(owner_retired_log_only=True),
                        board, WAIT_KEY, policy)
                else:
                    policy._town_blocked_reason = cause
                    key = policy._town_blocked_key(board)
                here = board.grid_at(board.player.position)
                if here is not None and here.store_number >= 0:
                    # The Home list (home_catalog_ready) is read before the
                    # departure judgement: off the store entrance first.
                    self.assertEqual(policy.last_reason, "town:entrance-step-off:town:end-step-off")
                    self.assertIn(key, "12346789")
                    self.assertFalse((Path(root) / "keep-running-events.jsonl").exists())
                    continue
                # home_catalog_ready is unmet and no purchase gap: no forced
                # departure and no mining cycle, the visit stops.
                self.assertEqual((key, policy.last_reason), (WAIT_KEY, decision["reason"]))
                self.assertTrue(cli._policy_final_stop_required(policy))
                self.assertIsNone(policy._fundraising_mode)
                rows = self.records(root)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["cause"], cause)
                self.assertEqual(rows[0]["outcome"], "hard_stop")
                self.assertEqual(rows[0]["minimum"]["failed"], [])
                self.assertEqual(rows[0]["free_pack_slots"], PACK_CAPACITY - len(board.inventory))

    def test_all_v0_hooks_and_hard_reasons_keep_their_boundary(self):
        for cause in VISIT_CLOSABLE_REASONS:
            with self.subTest(cause=cause), TemporaryDirectory() as root, patch.dict(os.environ,
                    HENGBOT_RUNTIME_DIR=root), redirect_stdout(io.StringIO()):
                policy, board, _ = ready_board()
                catalogued(policy)
                policy._town_blocked_reason = cause
                self.assertEqual(policy._town_blocked_key(board), "rha")
                self.assertEqual(len(self.records(root)), 1)
        for cause in ("overweight-home-unreachable", "overflow-no-legal-disposal", "survival-mana-no-charges"):
            with self.subTest(cause=cause), TemporaryDirectory() as root, patch.dict(os.environ, HENGBOT_RUNTIME_DIR=root):
                policy, board, _ = ready_board()
                policy._town_blocked_reason = cause
                self.assertEqual(policy._town_blocked_key(board), WAIT_KEY)
                self.assertEqual(policy.last_reason, f"town:blocked:{cause}")
                self.assertFalse((Path(root) / "keep-running-events.jsonl").exists())

    def test_burst_three_retirements_depart_or_retain_hard_stop(self):
        for safe in (True, False):
            with self.subTest(safe=safe), TemporaryDirectory() as root, patch.dict(os.environ,
                    HENGBOT_RUNTIME_DIR=root), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                policy, board, _ = ready_board()
                catalogued(policy)
                if not safe:
                    board = replace(board, player=replace(board.player, hp=1))
                args = SimpleNamespace(owner_retired_log_only=True)
                cli._handle_owner_retirement(args, board, "5", policy)  # progress baseline
                for number in range(3):
                    policy._decision_sequence += 1
                    policy.last_reason = "shop:approach"
                    policy._town_turn_arbiter.retire("store-router", ("unchanged",))
                    key = cli._handle_owner_retirement(args, board, "5", policy)
                # Unsafe (HP 1, the hp_full leaf, no purchase gap): no
                # departure and no mining cycle; the burst stops.
                self.assertEqual(key, "rha" if safe else WAIT_KEY)
                self.assertEqual(cli._policy_final_stop_required(policy), not safe)
                self.assertEqual(self.records(root)[0]["outcome"], "forced_departure" if safe else "hard_stop")
                self.assertEqual(len(self.records(root)), 1)

    def test_one_slot_record_stops_without_mining(self):
        policy, board, depth = ready_board()
        catalogued(policy)
        while len(board.inventory) < PACK_CAPACITY - 1:
            board = replace(board, inventory=board.inventory + [replace(item("z", TVAL_POTION, 0), weight=0)])
        # DECLARED CONSTRUCTED: visible active dungeon entrance under player.
        entrance = grid(board.player.position.y, board.player.position.x,
            entrance=True, downstairs=True, entrance_dungeon_id=policy._active_dungeon_target(), lit=True, in_view=True)
        board = replace(board, grids={entrance.position: entrance})
        with TemporaryDirectory() as root, patch.dict(os.environ, HENGBOT_RUNTIME_DIR=root), redirect_stdout(io.StringIO()):
            key = policy.force_visit_departure(board, "home-known-empty-withdrawal")
            # One free slot fails the ordinary five-slot reserve
            # (free_pack_slots_ready, no purchase gap): no walk-in departure
            # and no mining cycle.
            self.assertIsNone(key)
            self.assertIsNone(policy._fundraising_mode)
            row = self.records(root)[0]
            self.assertEqual(row["free_pack_slots"], 1)
            self.assertEqual(row["closed_work_under_five"], ["home-known-empty-withdrawal"])
            self.assertEqual((row["outcome"], row["entry_method"]), ("hard_stop", "none"))
            self.assertEqual(len(self.records(root)), 1)

    def test_committed_visit_preempts_release_shopping_and_refused_entrance(self):
        policy, board, _ = ready_board()
        # The committed recall is Angband's, open only after Q2 (owner 2026-11-05).
        board = replace(board, quests={
            **board.quests, 2: QuestState(2, status=QUEST_STATUS_FINISHED)})
        catalogued(policy)
        policy._observe(board)
        with TemporaryDirectory() as root, patch.dict(os.environ, HENGBOT_RUNTIME_DIR=root), redirect_stdout(io.StringIO()):
            policy.force_visit_departure(board, "departure-unsatisfiable")
            policy._town_restock_suppressed = True
            with patch.object(policy, "_departure_supplier_counterfactual", side_effect=AssertionError("release")), patch.object(
                    policy, "_shopping_approach_step", side_effect=AssertionError("required purchase")):
                self.assertEqual(policy._decide(board), "rha")
                # 98ee353d1b, owner 2026-10-31 (a condition lost after the commit is
                # satisfied again, not waited out): the commitment hands back and
                # town:recover rests; the cause stays so it is not forced twice.
                refused = replace(board, player=replace(board.player, hp=1))
                self.assertEqual(policy._decide(refused), REST_MACRO)
                self.assertEqual(policy.last_reason, "town:recover")
                self.assertIsNone(policy._visit_departure_committed)
                self.assertIn("departure-unsatisfiable", policy._visit_departure_recorded)
                self.assertIsNone(policy._town_blocked_reason)
                self.assertEqual(len(self.records(root)), 1)

    def test_committed_recall_keeps_existing_hard_hazard_cancellation(self):
        policy, board, _ = ready_board()
        catalogued(policy)
        with TemporaryDirectory() as root, patch.dict(os.environ, HENGBOT_RUNTIME_DIR=root), redirect_stdout(io.StringIO()):
            self.assertEqual(policy.force_visit_departure(board, "departure-unsatisfiable"), "rha")
            # DECLARED CONSTRUCTED: NO_TELE becomes known while recall is armed.
            armed = replace(board, player=replace(board.player, recalling=True),
                equipment=[replace(i, known_flags=i.known_flags | {TR_NO_TELE})
                           if i.slot == "main_hand" else i for i in board.equipment])
            recall = next(i for i in board.inventory if i.is_recall_scroll)
            self.assertEqual(policy._decide(armed), READ_KEY + recall.slot)
            self.assertEqual(policy.last_reason, "town:cancel-unsafe-recall")
            self.assertFalse(policy._emergency_recall_sanctioned)
            self.assertEqual(policy._visit_departure_committed, "departure-unsatisfiable")
            self.assertEqual(len(self.records(root)), 1)

    def test_existing_supply_stockout_fallback_and_exhausted_hard_stop(self):
        for exhausted in (False, True):
            with self.subTest(exhausted=exhausted), TemporaryDirectory() as root, patch.dict(os.environ,
                    HENGBOT_RUNTIME_DIR=root), redirect_stdout(io.StringIO()):
                policy, board, _ = ready_board()
                board = replace(board, inventory=[i for i in board.inventory if not i.is_recall_scroll])
                policy._supply_stockout_cycles = 3 if exhausted else 0
                policy._town_blocked_reason = "departure-unsatisfiable"
                # DECLARED CONSTRUCTED: exhausted supplier evidence (the
                # readiness table's stock-out, departure_readiness). Exercise
                # the real stockout owner's eligibility and three-run bound.
                with patch.object(policy, "_departure_block_state", return_value={"failed": ["recall_departure_ready"]}), patch.object(
                        ReadinessTable, "stocked_out",
                        lambda _table, leaf: leaf == "recall_departure_ready"):
                    key = policy._town_blocked_key(board)
                    # A stockout is no purchase gap: the town end's cycle does
                    # not start; the existing stockout run and its three-run
                    # bound remain.
                    self.assertEqual(key, WAIT_KEY)
                    self.assertEqual(policy._fundraising_mode, None if exhausted else "prepare")
                    self.assertEqual(policy._town_blocked_reason, "departure-unsatisfiable" if exhausted else None)
                row = self.records(root)[0]
                self.assertEqual(row["outcome"], "hard_stop" if exhausted else "fallback")
                self.assertIn("recall_departure_ready", row["minimum"]["failed"])
                self.assertEqual(len(self.records(root)), 1)

    def test_existing_ability_gap_fundraising_gate(self):
        policy, board, _ = ready_board()
        board = replace(board, player=replace(board.player, gold=1000),
            recall_depth=40, dungeon_recall_depths={board.recall_dungeon_id: 40})
        policy._equipment_optimization_last_depth = 40
        policy._supply_stockout_cycles = 3
        with TemporaryDirectory() as root, patch.dict(os.environ, HENGBOT_RUNTIME_DIR=root), redirect_stdout(io.StringIO()):
            self.assertEqual(policy.force_visit_departure(board, "equipment-departure-incomplete"), WAIT_KEY)
            self.assertEqual(policy._fundraising_mode, "prepare")
            # The ability gap is no purchase gap: the existing no-safe-
            # destination fundraising, not the town end's cycle.
            self.assertEqual(self.records(root)[0]["outcome"], "fallback")
            self.assertIn("depth_abilities", self.records(root)[0]["minimum"]["failed"])

    def test_transfer_debt_cannot_fall_back_to_income(self):
        policy, board, _ = ready_board()
        board = replace(board, player=replace(board.player, gold=1000),
            recall_depth=40, dungeon_recall_depths={board.recall_dungeon_id: 40})
        policy._equipment_optimization_last_depth = 40
        policy._home_atomic_deposit_pending = ("posted",)
        with TemporaryDirectory() as root, patch.dict(os.environ, HENGBOT_RUNTIME_DIR=root), redirect_stdout(io.StringIO()), patch.object(
                policy, "_supply_stockout_mining_key", side_effect=AssertionError("unsettled transfer")):
            self.assertIsNone(policy.force_visit_departure(board, "equipment-departure-incomplete"))
            self.assertIsNone(policy._fundraising_mode)
            self.assertEqual(self.records(root)[0]["outcome"], "hard_stop")
            self.assertEqual(policy._home_atomic_deposit_pending, ("posted",))

    def test_committed_descent_ignores_soft_preparation_but_keeps_hard_minimum(self):
        policy, board, _ = ready_board()
        policy._town_blocked_reason = "repetition"
        policy._visit_departure_committed = "equipment-departure-incomplete"
        policy._town_restock_suppressed = False
        policy._home_candidate_waiting = True
        with patch.object(policy, "_equipment_departure_ready", side_effect=AssertionError("optimization reopened")):
            self.assertFalse(policy._descent_is_blocked(board))
            self.assertTrue(policy._descent_is_blocked(replace(board, player=replace(board.player, hp=1))))
            self.assertEqual(policy._town_blocked_reason, "repetition")

    def test_guardian_switch_keeps_closed_soft_work_and_reads_the_one_table_stock(self):
        policy, board, _ = ready_board()
        original = policy._active_dungeon_target()
        alternate = 7
        board = replace(board, grids={}, entered_dungeon_ids=(original, alternate),
            dungeon_recall_depths={original: 19, alternate: 40},
            player=replace(board.player, abilities=board.player.abilities | _required_abilities_for_depth(40)))
        policy._town_blocked_reason = "repetition"
        policy._visit_departure_committed = "equipment-departure-incomplete"
        # DECLARED CONSTRUCTED: guardian refusal and its selected alternate.
        # The real repetition path and both actual landing minima run here.
        def destination(snapshot, *, guardian_gate=True, safety_gate=True):
            dungeon = policy._active_dungeon_target()
            return (None if guardian_gate and dungeon == original else "alt-dungeon", dungeon)

        def switch(snapshot, dungeon):
            self.assertEqual(dungeon, original)
            policy._target_dungeon_id = alternate
            return True

        with patch.object(policy, "_town_recall_destination", side_effect=destination), patch.object(
                policy, "_guardian_blocked_recall_switch", side_effect=switch), patch.object(
                policy, "_recall_town_departure_conjuncts", return_value={"equipment_departure_ready": False}):
            self.assertTrue(policy._departure_minimum(board, 19)["holds"])
            # Town rebuild stage 1 (owner 2026-11-12): the supplies are read
            # at the readiness table's one depth, the planned depth the
            # purchases follow.  The switched 40F landing no longer asks for a
            # recall stock the purchases never bought (it was WAIT here); its
            # depth gates still read the landing.
            self.assertTrue(policy._town_blocked_key(board).startswith(READ_KEY))
            self.assertEqual(policy._active_dungeon_target(), alternate)
            minimum = policy._departure_minimum(board, 40)
            self.assertTrue(minimum["values"]["recall_departure_ready"])
            self.assertTrue(minimum["values"]["depth_abilities"])
            self.assertEqual(policy._town_blocked_reason, "repetition")

    def test_restore_defaults_and_visit_transition_release_commitment(self):
        policy, board, _ = ready_board()
        del policy._visit_departure_committed
        del policy._visit_departure_recorded
        normalize_policy_state(policy)
        self.assertIsNone(policy._visit_departure_committed)
        self.assertEqual(policy._visit_departure_recorded, set())
        policy._observe(board)
        policy._visit_departure_committed = "departure-unsatisfiable"
        policy._visit_departure_recorded.add("departure-unsatisfiable")
        policy._observe(replace(board, town_id=board.town_id + 1))
        self.assertIsNone(policy._visit_departure_committed)
        self.assertEqual(policy._visit_departure_recorded, set())
        policy._visit_departure_committed = "departure-unsatisfiable"
        policy._visit_departure_recorded.add("departure-unsatisfiable")
        policy._observe(replace(board, floor_key=(1, 1, 0), town_flag=False))
        self.assertIsNone(policy._visit_departure_committed)
        self.assertEqual(policy._visit_departure_recorded, set())
