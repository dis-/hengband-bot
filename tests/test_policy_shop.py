import ast

import gzip

import inspect

import json

import os

import subprocess

import sys

import textwrap

import unittest

from collections import Counter, deque

from dataclasses import replace

from pathlib import Path

from tempfile import TemporaryDirectory

from types import SimpleNamespace

from unittest.mock import Mock, patch

import policy_shop_fixture as shop_fixture

from policy_fixtures import (
    store_item,
    grid,
    _public_shop_inner,
    player,
    item,
    set_known_target,
    set_completed_equipment_optimization,
    seed_confirmed_loadout,
    seed_character_calibration,
    hostile,
)

try:
    from trajectory_harness import drive_trajectory
except ModuleNotFoundError:
    from tests.trajectory_harness import drive_trajectory

import hengbot.policy as policy_module

import hengbot.equipment_mutation as equipment_mutation_module

from hengbot.home_errand import HomeErrandRequest

from hengbot.home_visit import HomeVisitKind, HomeVisitRequest

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint

from hengbot.cli import (
    POLICY_FINAL_STOP_REASONS,
    _dispatch_response_lines,
    _send_new_decision_key,
    _send_stall_recovery_nudge,
    _decision_record,
)

from hengbot.town_maps import TownMap, parse_town_map

from hengbot.wilderness_map import WildernessMap

from hengbot.model import (
    AbilitySources,
    DUNGEON_ANGBAND,
    DUNGEON_CHAMELEON_CAVE,
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    STORE_ALCHEMIST,
    STORE_ARMOURY,
    STORE_BLACK,
    STORE_GENERAL,
    STORE_HOME,
    STORE_MAGIC,
    STORE_TEMPLE,
    STORE_WEAPON,
    SV_DIGGING_PICK,
    SV_DIGGING_SHOVEL,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_LITE_FEANOR,
    SV_LITE_TORCH,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_SPEED,
    SV_POTION_HEALING,
    SV_POTION_RESIST_COLD,
    SV_POTION_RESTORE_STR,
    SV_POTION_RESTORE_CON,
    SV_POTION_INC_STR,
    SV_POTION_AUGMENTATION,
    SV_POTION_SLEEP,
    SV_ROD_IDENTIFY,
    SV_ROD_LITE,
    SV_SCROLL_WORD_OF_RECALL,
    SV_SCROLL_REMOVE_CURSE,
    SV_SCROLL_STAR_REMOVE_CURSE,
    SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
    SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
    SV_SCROLL_DETECT_TREASURE,
    SV_SCROLL_HOLY_CHANT,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_LIGHT,
    SV_SCROLL_PHASE_DOOR,
    SV_SCROLL_STAR_IDENTIFY,
    SV_SCROLL_TELEPORT,
    SV_SCROLL_STAR_DESTRUCTION,
    SV_STAFF_DESTRUCTION,
    SV_STAFF_IDENTIFY,
    SV_WAND_STONE_TO_MUD,
    TVAL_BOTTLE,
    TVAL_ARROW,
    TVAL_BOLT,
    TVAL_CHEST,
    TVAL_SHOT,
    TVAL_BOW,
    SV_BOW_SLING,
    SV_BOW_SHORT,
    SV_BOW_LIGHT_XBOW,
    TVAL_DIGGING,
    TVAL_FLASK,
    TVAL_AMULET,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_CHAOS_BOOK,
    TVAL_LIFE_BOOK,
    TVAL_HISSATSU_BOOK,
    TVAL_POTION,
    TVAL_RING,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_SOFT_ARMOR,
    TVAL_STAFF,
    TVAL_SWORD,
    TVAL_WAND,
    GridState,
    InventoryItem,
    MonsterState,
    PlayerState,
    Position,
    QuestState,
    Snapshot,
    StoreItem,
    StoreState,
    _parse_store,
    parse_snapshot,
)

from hengbot.dungeon_knowledge import DungeonInfo

from hengbot.equipment_optimizer import (
    EvaluatedLoadout, Loadout, LoadoutMetrics, OptimizationResult,
    OwnedEquipment, OwnedEquipmentCatalog, TR_TELEPORT, current_loadout,
)

from hengbot.monrace_knowledge import (
    MonraceKnowledge, MonsterBlow, load_monrace_knowledge,
)

from hengbot.quest_knowledge import (
    QUEST_FLAG_ONCE, QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER,
    QUEST_TYPE_RANDOM,
    QuestBattlefield, QuestInfo,
    find_quest_definitions,
    load_quest_knowledge,
)

from hengbot.quest_strategies import StrategyProfile, load_quest_strategies

from hengbot.quest_navigator import QuestFloorNavigator

from hengbot.projection_path import projection_path

from hengbot.equipment_mutation import progress_core

from hengbot.policy import (
    HengbotPolicy,
    EscapeState,
    BUY_KEY,
    CHARACTER_DUMP_MACRO,
    DESTROY_FAIL_LIMIT,
    DIGGER_WIELD_LIMIT,
    MINING_THREAT_FREE_LIMIT,
    EMPTY_DIVE_LIMIT,
    NO_DEPTH_PROGRESS_DIVE_LIMIT,
    OVEREXTEND_LOOT_MAX,
    RANGED_MAX_DISTANCE,
    UNUSED_DIVE_LIMIT,
    SELL_KEY,
    SELL_CONFIRM_SUFFIX,
    READ_KEY,
    UP_STAIRS_KEY,
    WAIT_KEY,
    STUCK_ESCAPE_LIMIT,
    TOWN_WANDER_LIMIT,
    STORE_RETRY_TURNS,
    STAFF_IDENTIFY_MIN_DEPTH,
    STAFF_IDENTIFY_MIN_CHARGES,
    TELEPORT_RETURN_THRESHOLD,
    TELEPORT_SCROLL_DEEP_TARGET,
    STAFF_IDENTIFY_MAX_COUNT,
    IDENTIFY_PRESSURE_FREE_SLOTS,
    IDENTIFY_FAIL_LIMIT,
    IDENTIFY_CHARGE_FLOOR,
    IDENTIFY_PURCHASE_MAX,
    INSCRIBE_KEY,
    RECALL_ISSUE_CONFIRM_TURNS,
    RECALL_MIN_DEPTH,
    SUPPLY_THRESHOLDS,
    RESUME_DESCENT_BLOCK_DECISIONS,
    FUNDRAISING_GOLD_TARGET,
    FUNDRAISING_KIT_RESERVE,
    FUNDRAISING_START_GOLD,
    FIXED_QUEST_CURE_CRITICAL_HP,
    QUEST_STATUS_COMPLETED,
    QUEST_STATUS_FINISHED,
    QUEST_STATUS_REWARDED,
    QUEST_STATUS_TAKEN,
    QUEST_STATUS_UNTAKEN,
    FOOD_MIN_SVAL,
    OIL_TARGET,
    AMMO_CARRY_TARGET,
    TORCH_THROW_TARGET,
    CHEST_SEARCH_BUDGET,
    CHEST_DISARM_BUDGET,
    CHEST_OPEN_BUDGET,
    LIVELOCK_LIMIT,
    HOME_PAGE_SINGLE_PAGE_MESSAGES,
    LEAVE_STORE_KEY,
    MINING_RUNS_PER_SET,
    DETECTION_SCROLL_BUFFER,
    BARREN_FLOOR_SKIP_THRESHOLD,
    BREEDER_CONTAINMENT_WINDOW,
    MINING_ROUTE_REVISIT_LIMIT,
    MINING_NAVIGATION_REVISIT_LIMIT,
    MINING_STALL_LIMIT,
    MINING_SWEEP_HARD_LIMIT,
    MINING_SWEEP_NO_PROGRESS_LIMIT,
    MIN_FREE_PACK_SLOTS,
    NEIGHBOR_OFFSETS,
    HOME_BATCH_RESERVED_SLOTS,
    PACK_CAPACITY,
    PICKUP_KEY,
    REST_MACRO,
    RESTOCK_WAIT_MACRO,
    STORE_RESTOCK_WAIT_TURNS,
    STUCK_WINDOW,
    DOOR_OPEN_LIMIT,
    RUBBLE_DIG_LIMIT,
    SEARCH_LIMIT,
    STORE_STUCK_LIMIT,
    StoreVisit,
    StoreVisitPhase,
    SHOP_APPROACH_STUCK_LIMIT,
    TUNNEL_KEY,
    TR_NO_TELE,
    TOWN_CYCLE_WINDOW,
    TOWN_CYCLE_BREAK_LIMIT,
    TOWN_CYCLE_IGNORED_REASONS,
    TOWN_TRAVEL_STALL_LIMIT,
    TOWN_TRAVEL_TURN_STALL_LIMIT,
    TOWN_TELEPORT_COST,
    TOWN_STOP_PASS_LIMIT,
    CALIBRATION_HOME_VISIT_LIMIT,
    TownErrandPlan,
    TownTravelProgress,
    TownNeed,
    TOWN_NO_PROGRESS_LIMIT,
    WAIT_KEY,
)

def setUpModule():
    global _knowledge_tmp, _knowledge_patch
    _knowledge_tmp = TemporaryDirectory()
    _knowledge_patch = patch(
        "hengbot.cli.KNOWLEDGE_RESPONSE_LEDGER_PATH",
        Path(_knowledge_tmp.name) / "knowledge-responses.jsonl",
    )
    _knowledge_patch.start()

def tearDownModule():
    _knowledge_patch.stop()
    _knowledge_tmp.cleanup()

def _supply_test_case(name):
    import test_policy_supply
    return getattr(test_policy_supply, name)()

FOOD_TYPE_MANA = 4

class ShopPurchaseSellPolicyTest(shop_fixture._TownShopFixtureBase):
    def _consume_failed_digger_procurement_withdrawal(
        self, policy, outside, stored, offered
    ):
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: the real Home entry and atomic operation run while unrelated town decision collaborators are isolated
        policy._floor_key = outside.floor_key
        policy._fundraising_mode = "prepare"
        policy._equipment_catalog._home = {}
        signature = policy._item_signature(stored)
        item_class = policy._procurement_class(offered)
        position = outside.player.position
        home_entrance = replace(
            outside,
            grids={
                position: replace(
                    grid(position.y, position.x), store_number=STORE_HOME
                ),
                Position(position.y, position.x - 1): grid(
                    position.y, position.x - 1
                ),
            },
        )
        policy._home_procurement_probe = item_class
        policy._home_pending_item = signature
        policy._home_page_size = 12
        policy._digger_home_withdraw_failures = 1
        policy._shop_observation = None
        policy._store_visit = None
        policy._town_errand_plan = None
        policy._shopping_approach_store_type = STORE_HOME
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: the public withdrawal observer is the subject; only unrelated downstream policy selection is replaced
        with patch.object(
            policy,
            "_decide",
            side_effect=lambda snapshot: policy._shopping_approach_key(
                snapshot, snapshot.player.position, "shop:travel"
            ),
        ):
            entry_key = policy.choose_key(home_entrance)
        self.assertEqual(entry_key, WAIT_KEY)
        policy.confirm_key_posted(entry_key)
        operation_key = policy.choose_key(replace(
            home_entrance,
            store=StoreState(
                STORE_HOME, [stored], stock_num=1, page_top=0, page_size=12,
            ),
        ))
        self.assertEqual(operation_key, "pa\x1b")
        policy.confirm_key_posted(operation_key)
        failed_outside = replace(home_entrance, turn=home_entrance.turn + 1)
        policy.choose_key(failed_outside)
        return failed_outside

    def _digger_purchase_gate_fixture(self, *, home_present=True, terminal=False):
        offered = store_item(
            "a", TVAL_DIGGING, 1, name="new shovel", price=50,
            is_equipment=True,
        )
        stored = store_item(
            "h", TVAL_DIGGING, 4, name="stored pick", is_equipment=True,
        )
        position = Position(10, 10)
        outside = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {position: replace(grid(10, 10), store_number=STORE_GENERAL)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=self._strict_supplies(detection=5),
        )
        policy = HengbotPolicy()
        policy._floor_key = outside.floor_key
        policy._fundraising_mode = "prepare"
        policy.consume_home_knowledge(
            (stored,) if home_present or terminal else ()
        )
        # Procurement's live Home gate consumes the complete ~9 catalogue;
        # the separate equipment catalog is deliberately empty here because
        # this pin models a consumer-equivalent tool, not an optimizer-owned
        # loadout candidate.
        policy._equipment_catalog._home = {}
        if terminal:
            self._consume_failed_digger_procurement_withdrawal(
                policy, outside, stored, offered
            )
            self.assertIsNotNone(policy._home_procurement_withdraw_failure)
            policy.consume_home_knowledge((stored,) if home_present else ())
            policy._equipment_catalog._home = {}
        observed = StoreState(STORE_GENERAL, [offered], page_top=0)
        policy._shop_observation = (observed, policy._decision_sequence)
        policy._shopping_approach_store_type = STORE_GENERAL
        policy._shopping_approach_goal = position
        policy._store_visit = StoreVisit("town-errand", "shopping", STORE_GENERAL)
        return policy, outside, observed

    def test_pin_vacuity_digger_fallback_cannot_bypass_known_home_stock(self):
        policy, outside, observed = self._digger_purchase_gate_fixture()

        policy.choose_key(replace(outside, store=observed))
        key = policy.choose_key(replace(outside, turn=outside.turn + 1))

        self.assertIn(key, set("12346789") | {WAIT_KEY})
        self.assertFalse(key.startswith(BUY_KEY))
        self.assertEqual(policy._home_gate_telemetry["result"], "home-first")
        self.assertEqual(
            policy._home_gate_telemetry["branch"], "wrapper-candidate-home-first"
        )

    def test_pin_vacuity_digger_terminal_failure_present_retries_home_once(self):
        policy, outside, observed = self._digger_purchase_gate_fixture(
            terminal=True
        )
        self.assertGreaterEqual(policy._decision_sequence, 3)
        self.assertTrue(policy._deferred_home_items)

        policy.choose_key(replace(outside, store=observed))
        key = policy.choose_key(replace(outside, turn=outside.turn + 1))

        signature = policy._item_signature(policy._home_knowledge_items[0])
        self.assertNotEqual(key, WAIT_KEY, policy.last_reason)
        self.assertEqual(
            policy._home_gate_telemetry["branch"],
            "wrapper-candidate-home-first",
        )
        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertIn(signature, policy._retried_deferred_home_items)
        self.assertIsNone(policy._home_procurement_withdraw_failure)

    def test_pin_vacuity_digger_terminal_failure_absent_allows_buy(self):
        policy, outside, observed = self._digger_purchase_gate_fixture(
            home_present=False, terminal=True
        )

        gate = policy._purchase_has_fresh_home_absence(
            replace(outside, store=observed), observed.items[0]
        )
        buy_key = policy._shop(replace(outside, store=observed))

        self.assertIs(gate, policy_module.ProcurementHomeGate.ALLOW_PURCHASE)
        self.assertEqual(
            policy._home_gate_telemetry["branch"],
            "wrapper-fresh-catalogue-absence",
        )
        self.assertTrue(buy_key.startswith(BUY_KEY), buy_key)

    def test_cure_shortage_falls_back_to_alchemist_after_temple(self):
        snap = Snapshot(
            player(10, 10, gold=8000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(
                recall=5, teleport=15, critical=0
            ),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 4
        policy._town_store_attempted[STORE_TEMPLE] = snap.turn

        self.assertFalse(policy._cure_critical_ready(snap))
        self.assertEqual(
            policy._next_required_store_type(snap), STORE_ALCHEMIST
        )

    def test_fundraising_checks_home_for_digger_before_general_store(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(detection=5),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"

        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)
        pol._town_store_attempted[STORE_HOME] = 0
        self.assertEqual(pol._next_required_store_type(snap), STORE_GENERAL)
        pol._town_store_attempted[STORE_GENERAL] = 0
        self.assertIsNone(pol._next_required_store_type(snap))
        self.assertEqual(pol._fundraising_mode, "scavenge")

    def test_recovered_home_entry_arms_standing_digger_withdrawal_after_restart(self):
        digger = store_item(
            "F", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="captured shovel", is_equipment=True,
        )
        inside = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_HOME
                )
            },
            [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=self._strict_supplies(detection=5),
            store=StoreState(STORE_HOME, [digger], page_size=52),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        policy._equipment_catalog.observe_home_page([digger])
        policy._shopping_approach_store_type = STORE_HOME
        policy._shopping_approach_goal = inside.player.position
        resumed = restore_checkpoint(HengbotPolicy, checkpoint(policy))

        self.assertEqual(resumed.choose_key(inside), LEAVE_STORE_KEY)
        self.assertEqual(
            resumed.last_reason, "home:queue-digging-tool-withdraw"
        )
        self.assertEqual(resumed._home_pending_item, resumed._item_signature(digger))

        outside = replace(inside, store=None, turn=inside.turn + 1)
        self.assertEqual(resumed.choose_key(outside), "5")

    def test_pending_observed_home_withdrawal_bounces_without_stop_pass(self):
        oil = store_item("a", 77, 0, name="Flask of oil")
        inside = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=self._strict_supplies(detection=5),
            store=StoreState(
                STORE_HOME, [oil], stock_num=1, page_top=0, page_size=52,
            ),
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((oil,))
        policy._home_pending_item = policy._item_signature(oil)
        policy._shopping_approach_store_type = STORE_HOME

        self.assertEqual(policy.choose_key(inside), LEAVE_STORE_KEY)
        self.assertEqual(
            policy.last_reason, "home:leave-for-pending-withdraw"
        )
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)

    def test_pending_unobserved_home_withdrawal_does_not_false_bounce(self):
        held = store_item("a", 77, 0, name="Flask of oil")
        missing = store_item("b", 70, 26, name="Missing scroll")
        inside = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=self._strict_supplies(detection=5),
            store=StoreState(
                STORE_HOME, [held], stock_num=1, page_top=0, page_size=52,
            ),
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((held,))
        policy._home_pending_item = policy._item_signature(missing)
        policy._shopping_approach_store_type = STORE_HOME

        self.assertEqual(policy.choose_key(inside), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:route-claim-unfulfilled")
        self.assertEqual(policy._town_store_attempted[STORE_HOME], inside.turn)

    def test_stored_digger_is_not_treated_as_carried_fundraising_kit(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(detection=5),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._equipment_catalog.observe_home_page(
            [
                store_item(
                    "a", TVAL_DIGGING, 4,
                    name="stored pick", is_equipment=True,
                )
            ]
        )

        self.assertTrue(policy._has_withdrawable_digging_tool(snap))
        self.assertFalse(policy._fundraising_kit_secured(snap))
        self.assertEqual(policy._fundraising_kit_reserve(snap), 0)
        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)

    def test_shallow_mana_fundraising_departs_when_device_food_is_unaffordable(self):
        snap = Snapshot(
            player(
                38,
                106,
                hp=217,
                max_hp=217,
                food=5000,
                food_type=FOOD_TYPE_MANA,
                gold=337,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(38, 106): grid(38, 106)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[item("e", TVAL_WAND, 15, charges=3)],
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    is_equipment=True,
                    fuel=5000,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        policy._town_store_attempted[STORE_MAGIC] = snap.turn

        self.assertFalse(policy._food_ready(snap))
        self.assertTrue(policy._fundraising_food_ready(snap))
        self.assertTrue(policy._fundraising_departure_ready(snap))
        self.assertNotEqual(policy._next_required_store_type(snap), STORE_MAGIC)
        self.assertIsNone(policy._town_blocked_reason)

    def test_fundraising_checks_home_before_buying_treasure_detection(self):
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(detection=0),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)

    def test_deep_recall_cannot_depart_below_requirement_after_stores_fail(self):
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(recall=5, detection=0),
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=13,
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        policy = HengbotPolicy()
        policy._deepest_level = 13
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._home_candidate_waiting = False
        policy._food_ready = lambda _snapshot: True
        policy._light_ready = lambda _snapshot: True
        policy._teleport_ready = lambda _snapshot: True
        policy._cure_critical_ready = lambda _snapshot: True
        policy._identify_staff_ready = lambda _snapshot: True
        policy._town_store_attempted.update(
            {STORE_TEMPLE: 0, STORE_ALCHEMIST: 0, STORE_BLACK: 0}
        )

        self.assertFalse(policy._recall_ready(snap))
        self.assertFalse(policy._recall_departure_ready(snap))
        policy._next_required_store_type(snap)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_unobtainable_recall_below_requirement_blocks_departure(self):
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(recall=4, detection=0),
            equipment=[self._lantern()],
            recall_depth=13,
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        policy = HengbotPolicy()
        policy._deepest_level = 13
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._town_store_attempted.update({STORE_TEMPLE: 0, STORE_ALCHEMIST: 0})

        status = policy._supply_ledger(snap, policy._planned_depth())["recall"]
        self.assertLess(status.count, status.required_departure)
        self.assertFalse(status.obtainable)
        self.assertFalse(policy._recall_departure_ready(snap))
        policy._next_required_store_type(snap)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_fundraising_withdraws_stored_detection_before_digger(self):
        inventory = self._strict_supplies(detection=0)
        store = StoreState(
            STORE_HOME,
            [
                store_item(
                    "a",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=25,
                ),
                store_item("b", TVAL_DIGGING, 1, name="shovel", is_equipment=True),
            ],
        )
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=store,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        scroll, digger = store.items
        policy.consume_home_knowledge(tuple(store.items))
        policy._home_page_size = 52
        policy._shopping_approach_store_type = STORE_HOME
        policy._home_pending_item = policy._item_signature(scroll)
        policy._home_pending_quantity = min(
            policy._mining_detection_scroll_target(snap)
            + DETECTION_SCROLL_BUFFER,
            scroll.count,
        )
        outside = replace(
            snap,
            store=None,
            grids={Position(10, 10): replace(grid(10, 10), store_number=STORE_HOME)},
        )
        key = policy._atomic_home_withdraw_key(outside, outside.player.position)
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy._home_atomic_withdraw_pending[2].name, scroll.name)
        self.assertNotEqual(
            policy._home_atomic_withdraw_pending[2].name, digger.name
        )

    def test_fundraising_withdraws_detection_buffer_from_home(self):
        target = 4
        stored_count = target + DETECTION_SCROLL_BUFFER
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(detection=0),
            store=StoreState(
                STORE_HOME,
                [
                    store_item(
                        "a",
                        TVAL_SCROLL,
                        SV_SCROLL_DETECT_TREASURE,
                        count=stored_count,
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._planned_mining_runs = target

        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:queue-treasure-detection-withdraw")
        self.assertEqual(policy._home_pending_quantity, stored_count)

    def test_fundraising_withdraws_second_digger_from_home(self):
        held_digger = item("p", TVAL_DIGGING, 1, name="held shovel")
        stored_digger = store_item(
            "b", TVAL_DIGGING, 4, name="stored pick", is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(detection=5),
                held_digger,
            ],
            store=StoreState(STORE_HOME, [stored_digger]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:queue-digging-tool-withdraw")

        with_second = replace(
            snap,
            inventory=[
                *snap.inventory,
                item("q", TVAL_DIGGING, 4, name="stored pick"),
            ],
            store=StoreState(STORE_HOME, [], stock_num=0, page_top=0, page_size=52),
        )
        self.assertEqual(policy._shop(with_second), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:leave-with-digging-tool")
        self.assertEqual(policy._digging_tool_count(with_second), 2)

    def test_home_stock_blocks_digger_buy_even_after_home_was_attempted(self):
        """Fact 4: the old buy gate counted pack+equipment but omitted Home."""
        held = item("p", TVAL_DIGGING, 1, name="held shovel")
        stored = store_item(
            "b", TVAL_DIGGING, 4, name="stored pick", is_equipment=True
        )
        general_digger = store_item(
            "a", TVAL_DIGGING, 1, name="new shovel", price=50,
            is_equipment=True,
        )
        general = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*self._strict_supplies(detection=5), held],
            store=StoreState(STORE_GENERAL, [general_digger]),
        )

        for attempted in (False, True):
            policy = HengbotPolicy()
            policy._fundraising_mode = "prepare"
            policy.consume_home_knowledge((stored,))
            if attempted:
                policy._town_store_attempted[STORE_HOME] = general.turn
            self.assertEqual(policy._withdrawable_digging_tool_count(general), 2)
            self.assertIsNone(policy._next_purchase_unreserved(general))

            restarted = HengbotPolicy()
            restarted._fundraising_mode = "prepare"
            restarted.consume_home_knowledge((stored,))
            if attempted:
                restarted._town_store_attempted[STORE_HOME] = general.turn
            self.assertIsNone(restarted._next_purchase_unreserved(general))

    def test_two_visible_withdraw_failures_do_not_override_total_stock_target(self):
        held = item("p", TVAL_DIGGING, 1, name="held shovel")
        stored = store_item(
            "b", TVAL_DIGGING, 4, name="stored pick", is_equipment=True
        )
        offered = store_item("a", TVAL_DIGGING, 1, name="new shovel", price=50)
        general = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*self._strict_supplies(detection=5), held],
            store=StoreState(STORE_GENERAL, [offered]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy.consume_home_knowledge((stored,))

        policy._digger_home_withdraw_failures = 1
        self.assertIsNone(policy._next_purchase_unreserved(general))
        policy._digger_home_withdraw_failures = 2
        self.assertFalse(
            policy._digger_buy_fallback_available(general),
            "one carried plus one withdrawable Home digger reaches the target",
        )
        policy._fundraising_mode = "scavenge"
        self.assertNotIn(
            TownNeed(STORE_GENERAL, "fundraising-digger", "normal"),
            policy._enumerate_town_needs(replace(general, store=None)),
        )
        policy._record_shop_selector_diagnostics(general, LEAVE_STORE_KEY)
        self.assertFalse(policy._digger_buy_fallback_available(general))
        self.assertEqual(policy._shop(general), LEAVE_STORE_KEY)
        self.assertFalse(policy._digger_fallback_bought_this_visit)
        self.assertIsNone(policy._next_purchase_unreserved(general))

        ordinary = HengbotPolicy()
        ordinary._fundraising_mode = "prepare"
        self.assertTrue(ordinary._shop(general).startswith(BUY_KEY))
        self.assertEqual(ordinary.last_reason, "shop:buy-digging-tool")

    def test_confirmed_digger_sale_arms_sell_rebuy_churn_defect(self):
        """The captured 02:49 sale arms the later 02:51 rebuy stop."""
        sold = replace(
            item("a", TVAL_DIGGING, 1, name="sold shovel", pval=0),
            inscription="@0",
        )
        better = [
            item("b", TVAL_DIGGING, 4, name="kept pick", pval=1),
            item("c", TVAL_DIGGING, 7, name="kept mattock", pval=2),
        ]
        sale = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[sold, *better],
            store=StoreState(STORE_GENERAL, []),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._batch_sell_key(sale, [sold]), "d0y")
        confirmed = replace(
            sale,
            player=replace(sale.player, gold=74),
            inventory=better,
        )
        self.assertEqual(policy._batch_sell_key(confirmed), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:one-shot-sale-observed")
        self.assertIn(
            (TVAL_DIGGING, sold.sval), policy._town_visit_sale_signatures
        )

        offered = store_item(
            "a", TVAL_DIGGING, 1, name="new shovel", price=50,
            is_equipment=True,
        )
        rebuy = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*self._strict_supplies(detection=5), better[0]],
            store=StoreState(STORE_GENERAL, [offered]),
        )
        policy._fundraising_mode = "prepare"
        self.assertEqual(policy._shop(rebuy), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:sell-rebuy-churn-defect")
        self.assertEqual(
            policy.town_visit_report,
            f"town-visit:sell-rebuy-churn:{TVAL_DIGGING}:{sold.sval}",
        )

    def test_confirmed_sale_allows_a_different_sval_with_the_same_tval(self):
        policy = HengbotPolicy()
        policy._town_visit_sale_signatures.add((TVAL_SCROLL, 9))
        policy._identification_need = "normal"
        policy._equipment_catalog.observe_home_page([])
        policy._home_knowledge_current = True
        policy._home_scan_item_count = 0
        target = item(
            "a", TVAL_RING, -1, name="unknown ring", known=False,
            aware=False, is_equipment=True,
        )
        identify = store_item(
            "f", TVAL_SCROLL, SV_SCROLL_IDENTIFY,
            name="Scroll of Identify", price=81
        )
        shop = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[target],
            store=StoreState(STORE_ALCHEMIST, [identify]),
        )
        key = _public_shop_inner(self, policy, shop)

        self.assertIn(BUY_KEY, key, policy._shop_selector_diagnostics)
        self.assertNotEqual(policy.last_reason, "shop:sell-rebuy-churn-defect")

    def test_gate1_digger_rebuy_window_stops_after_first_fallback_purchase(self):
        """Gate 1: replay the 02:51:21/02:51:36 stock transition.

        The 02:51:08 Home scan contained one shovel.  Failed withdrawal
        bookkeeping must not authorize even the first replacement purchase
        while that consumer-equivalent Home stock remains current.
        """
        stored = store_item(
            "b", TVAL_DIGGING, 1, name="Home shovel", is_equipment=True
        )
        offered = store_item(
            "m", TVAL_DIGGING, 4, name="general-store pick", price=148,
            is_equipment=True,
        )
        before = Snapshot(
            player(10, 10, gold=2022, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(detection=10),
            store=StoreState(STORE_GENERAL, [offered]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy.consume_home_knowledge((stored,))
        policy._digger_home_withdraw_failures = 2

        self.assertEqual(policy._withdrawable_digging_tool_count(before), 1)
        self.assertTrue(policy._digger_buy_fallback_available(before))
        self.assertEqual(policy._shop(before), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:home-first-before-purchase")
        self.assertIsNone(policy._store_buy_inflight)

        carried = item("k", TVAL_DIGGING, 4, name="general-store pick")
        after = replace(
            before,
            player=replace(before.player, gold=1874),
            inventory=[*before.inventory, carried],
        )
        policy._digger_fallback_bought_this_visit = False  # strongest reset case

        self.assertEqual(policy._withdrawable_digging_tool_count(after), 2)
        self.assertFalse(policy._digger_buy_fallback_available(after))
        self.assertIsNone(policy._next_purchase_unreserved(after))
        self.assertNotIn(
            TownNeed(STORE_GENERAL, "fundraising-digger", "normal"),
            policy._enumerate_town_needs(replace(after, store=None)),
        )

    def test_failed_digger_withdraw_retries_only_after_fresh_home_observation(self):
        digger = store_item(
            "H", TVAL_DIGGING, SV_DIGGING_PICK,
            name="stored pick", is_equipment=True,
        )
        outside = Snapshot(
            player(45, 123, gold=1030, class_id=PLAYER_CLASS_WARRIOR),
            {Position(45, 123): replace(
                grid(45, 123), store_number=STORE_HOME
            )}, [],
            floor_key=(0, 0, 0), town_flag=True, turn=2127406,
            inventory=self._strict_supplies(detection=5),
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(digger)
        policy.consume_home_knowledge((digger,))
        policy._home_pending_item = signature
        policy._home_digger_withdraw_pending = True
        policy._home_atomic_withdraw_pending = (signature, 0, digger, 1)
        policy._home_atomic_withdraw_posted_turn = 2127396
        policy._floor_key = outside.floor_key

        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: isolate the observation transition from unrelated town routing
        policy._decide = Mock(return_value=WAIT_KEY)
        policy.choose_key(outside)

        self.assertEqual(policy._home_pending_item, signature)
        self.assertTrue(policy._home_digger_withdraw_pending)
        self.assertFalse(policy._home_knowledge_current)
        self.assertTrue(policy._home_knowledge_invalidated)
        self.assertEqual(policy._digger_home_withdraw_failures, 1)
        self.assertNotEqual(
            policy.last_reason, "shop:observed-operation-uncomposable"
        )

        policy.consume_home_knowledge(tuple(
            store_item(
                chr(ord("a") + index) if index < 26 else chr(ord("A") + index - 26),
                TVAL_FOOD,
                index,
                name=f"filler-{index}",
            )
            for index in range(33)
        ) + (digger,))
        policy._home_page_size = 52
        policy._shopping_approach_store_type = STORE_HOME

        retry = policy._atomic_home_withdraw_key(
            outside, outside.player.position
        )

        self.assertEqual(retry, WAIT_KEY)
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")

    def test_failed_digger_fresh_retry_is_restart_immune(self):
        digger = store_item(
            "H", TVAL_DIGGING, SV_DIGGING_PICK,
            name="stored pick", is_equipment=True,
        )
        outside = Snapshot(
            player(45, 123, gold=1030, class_id=PLAYER_CLASS_WARRIOR),
            {Position(45, 123): replace(
                grid(45, 123), store_number=STORE_HOME
            )}, [],
            floor_key=(0, 0, 0), town_flag=True, turn=2127406,
            inventory=self._strict_supplies(detection=5),
        )
        delivered = []
        for _ in range(2):
            policy = HengbotPolicy()
            signature = policy._item_signature(digger)
            policy.consume_home_knowledge((digger,))
            policy._home_pending_item = signature
            policy._home_digger_withdraw_pending = True
            policy._home_atomic_withdraw_pending = (signature, 0, digger, 1)
            policy._home_atomic_withdraw_posted_turn = 2127396
            policy._floor_key = outside.floor_key
            # TEST_FAKERY_LINT_ALLOW: public-path-replaced: isolate the observation transition from unrelated town routing
            policy._decide = Mock(return_value=WAIT_KEY)
            policy.choose_key(outside)
            policy.consume_home_knowledge(tuple(
                store_item(
                    chr(ord("a") + index) if index < 26 else chr(ord("A") + index - 26),
                    TVAL_FOOD,
                    index,
                    name=f"filler-{index}",
                )
                for index in range(33)
            ) + (digger,))
            policy._home_page_size = 52
            policy._shopping_approach_store_type = STORE_HOME
            delivered.append(policy._atomic_home_withdraw_key(
                outside, outside.player.position
            ))

        self.assertEqual(delivered, [WAIT_KEY, WAIT_KEY])

    def test_restart_without_home_scan_uses_carried_digger_count(self):
        offered = store_item("a", TVAL_DIGGING, 1, name="new shovel", price=50)
        held = item("p", TVAL_DIGGING, 1, name="held shovel")
        general = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*self._strict_supplies(detection=5), held, replace(held, slot="q")],
            store=StoreState(STORE_GENERAL, [offered]),
        )
        restarted = HengbotPolicy()
        restarted._fundraising_mode = "prepare"
        self.assertIsNone(restarted._next_purchase_unreserved(general))
        short_restarted = HengbotPolicy()
        short_restarted._fundraising_mode = "prepare"
        self.assertIsNotNone(short_restarted._next_purchase_unreserved(
            replace(general, inventory=[*self._strict_supplies(detection=5), held])
        ))

    def test_fundraising_empty_torch_waits_for_general_store_restock(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=1967,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10, entrance=True)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=100,
            inventory=[
                *self._strict_supplies(recall=0, detection=5),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_TORCH,
                    fuel=0,
                    is_equipment=True,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertFalse(policy._fundraising_departure_ready(snap))
        self.assertEqual(policy._next_required_store_type(snap), STORE_GENERAL)

        policy._town_store_attempted[STORE_GENERAL] = 0
        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertEqual(policy._town_special_key(snap), RESTOCK_WAIT_MACRO)
        self.assertTrue(policy.last_reason.startswith("town:wait-restock:"))

    def test_restocked_mining_kit_is_affordable_and_promotes_before_wait(self):
        base = Snapshot(
            player(10, 10, gold=478, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=100,
            inventory=self._strict_supplies(detection=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._town_store_attempted[STORE_GENERAL] = base.turn

        self.assertIsNone(
            policy._retry_after_store_restock(base, (STORE_GENERAL,))
        )
        expiry = replace(base, turn=policy._town_restock_wait_until)
        self.assertEqual(
            policy._retry_after_store_restock(expiry, (STORE_GENERAL,)),
            STORE_GENERAL,
        )

        digger = store_item(
            "d", TVAL_DIGGING, SV_DIGGING_SHOVEL, price=100
        )
        general = replace(
            expiry,
            store=StoreState(STORE_GENERAL, [digger]),
            town_flag=False,
        )
        self.assertEqual(policy._next_purchase(general), digger)

        detection = store_item(
            "t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, price=20
        )
        alchemist = replace(
            expiry,
            inventory=[
                *base.inventory,
                item("z", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            store=StoreState(STORE_ALCHEMIST, [detection]),
            town_flag=False,
        )
        self.assertEqual(policy._next_purchase(alchemist), detection)

        ready = replace(
            expiry,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
        )
        policy._town_restock_wait_until = ready.turn + STORE_RESTOCK_WAIT_TURNS
        policy._town_restock_waiting_for = (STORE_ALCHEMIST,)
        policy._town_restock_suppressed = True
        with patch.object(
            policy, "_fundraising_departure_ready", return_value=False
        ):
            policy._town_special_key(ready)

        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertFalse(policy.last_reason.startswith("town:wait-restock:"))

    def test_fundraising_routes_one_flask_oil_shortage_to_general_store(self):
        snap = Snapshot(
            player(10, 10, gold=3374, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=OIL_TARGET - 1, fuel=500),
                item("d", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=3),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = 3

        self.assertEqual(policy._next_required_store_type(snap), STORE_GENERAL)

    def test_identification_need_preserves_the_oil_supply_claim(self):
        snap = Snapshot(
            player(10, 10, gold=3374, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_GENERAL
                )
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=OIL_TARGET - 1),
            ],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._identification_need = "normal"

        claims = policy._enumerate_live_store_claims(snap)

        self.assertIn(TownNeed(STORE_GENERAL, "oil", "normal"), claims)

        key = policy.choose_key(snap)

        self.assertEqual(key, "5")
        self.assertEqual(policy.last_reason, "shop:travel:await-entry")
        self.assertEqual(policy._shopping_approach_store_type, STORE_GENERAL)

    def test_august_22_unentered_general_oil_claim_routes_to_supplier(self):
        """Replay incident rows 356-400 from the retained turn-712398 board."""
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "incident-town-oil-stall-turn-712398.jsonl.gz"
        )
        raw = None
        with gzip.open(fixture, "rt", encoding="utf-8-sig") as rows:
            for line in rows:
                candidate = json.loads(line)
                if candidate.get("turn") == 712398:
                    raw = candidate
                    break
        self.assertIsNotNone(raw)
        snap = parse_snapshot(raw, {})
        policy = HengbotPolicy()
        policy._deepest_level = 1
        set_completed_equipment_optimization(policy)
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._town_store_attempted = {
            STORE_MAGIC: snap.turn,
            STORE_TEMPLE: snap.turn,
            STORE_ALCHEMIST: snap.turn,
        }
        policy._town_errand_plan = TownErrandPlan(
            [STORE_GENERAL, STORE_BLACK]
        )
        policy._town_cycle_pending = False
        policy._town_blocked_reason = "no-actionable-claim-owner"
        policy._town_visit_ledger.passes_since_progress = 19

        claims = policy._enumerate_live_store_claims(snap)
        key = policy.choose_key(snap)

        self.assertIn(TownNeed(STORE_GENERAL, "oil", "normal"), claims)
        self.assertNotIn(STORE_GENERAL, policy._town_store_attempted)
        self.assertEqual(policy._shopping_approach_store_type, STORE_GENERAL)
        self.assertIn(
            "oil", policy._town_errand_plan.need_categories[STORE_GENERAL]
        )
        self.assertTrue(key)
        self.assertIn(policy.last_reason, {"shop:approach", "shop:travel"})

    def test_fundraising_withdraws_two_of_three_home_diggers_before_leaving(self):
        inventory = self._strict_supplies(detection=5)
        first_store = StoreState(
            STORE_HOME,
            [
                store_item("a", TVAL_DIGGING, 1, name="shovel", is_equipment=True),
                store_item("b", TVAL_DIGGING, 4, name="pick", is_equipment=True),
                store_item("c", TVAL_DIGGING, 5, name="mattock", is_equipment=True),
            ],
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=first_store,
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"

        self.assertEqual(pol._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home:queue-digging-tool-withdraw")

        with_mattock = replace(
            snap,
            inventory=[*inventory, item("z", TVAL_DIGGING, 5, name="mattock")],
            store=StoreState(STORE_HOME, first_store.items[:2]),
        )
        self.assertEqual(pol._shop(with_mattock), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home:leave-with-item")

        with_two = replace(
            with_mattock,
            inventory=[
                *with_mattock.inventory,
                item("y", TVAL_DIGGING, 4, name="pick"),
            ],
            store=StoreState(STORE_HOME, first_store.items[:1]),
        )
        self.assertEqual(pol._shop(with_two), "\x1b")
        self.assertEqual(pol.last_reason, "home:leave-with-digging-tool")
        self.assertEqual(pol._digging_tool_count(with_two), 2)

    def test_fundraising_with_one_home_digger_withdraws_once_then_leaves(self):
        inventory = self._strict_supplies(detection=5)
        digger = store_item(
            "a", TVAL_DIGGING, 1, name="shovel", is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=StoreState(STORE_HOME, [digger]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        with_digger = replace(
            snap,
            inventory=[
                *inventory,
                item("z", TVAL_DIGGING, 1, name="shovel"),
            ],
            store=StoreState(STORE_HOME, []),
        )
        self.assertEqual(policy._shop(with_digger), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:leave-with-digging-tool")

    def test_second_digger_queue_survives_surface_item_processing_until_post(self):
        inventory = [
            *self._strict_supplies(detection=5),
            item("z", TVAL_DIGGING, 1, name="carried shovel"),
        ]
        home_diggers = [
            store_item("a", TVAL_DIGGING, 1, name="home shovel", is_equipment=True),
            store_item("b", TVAL_DIGGING, 4, name="home pick", is_equipment=True),
        ]
        inside = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True, inventory=inventory,
            store=StoreState(STORE_HOME, home_diggers),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertEqual(policy._shop(inside), LEAVE_STORE_KEY)
        queued = policy._home_pending_item
        outside = replace(inside, store=None)
        self.assertIsNone(policy._town_item_processing_key(outside))
        self.assertEqual(policy._home_pending_item, queued)
        self.assertTrue(policy._home_withdrawal_queued)
        self.assertNotIn(queued, policy._deferred_home_items)

        policy.consume_home_knowledge(home_diggers)
        policy._home_page_size = 52
        policy._shopping_approach_store_type = STORE_HOME
        entrance = replace(
            outside,
            grids={Position(10, 10): replace(
                grid(10, 10), store_number=STORE_HOME
            )},
        )
        withdrawal = policy._atomic_home_withdraw_key(
            entrance, entrance.player.position
        )
        self.assertEqual(withdrawal, WAIT_KEY)
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")

        gained_pick = item(
            "k", TVAL_DIGGING, 4, name="home pick"
        )
        gained = replace(
            entrance,
            inventory=[*self._strict_supplies(detection=5), gained_pick],
            equipment=[replace(
                inventory[-1], slot="main_hand", is_equipment=True
            )],
            turn=entrance.turn + 1,
        )
        policy._store_visit = None
        policy.choose_key(gained)
        self.assertEqual(policy._digging_tool_count(gained), 2)
        self.assertFalse(policy._home_digger_withdraw_pending)
        self.assertIsNone(policy._home_atomic_withdraw_pending)

        dual_wield_tail = policy._wield_digging_tool_key(
            gained, "fundraise:wield-digging-tool"
        )
        self.assertEqual(dual_wield_tail, "wky")

    def test_scavenge_plan_routes_unaddressed_home_digger_latch_and_clears_queue(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True, inventory=[],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        policy._town_errand_plan = TownErrandPlan([STORE_ALCHEMIST, STORE_GENERAL])
        policy._home_pending_item = None
        policy._home_digger_withdraw_pending = True
        policy._home_withdrawal_queued = True

        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertFalse(policy._home_withdrawal_queued)

    def test_fundraising_leave_with_mining_supplies_latches_home(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_HOME
                ),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=123,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, 4, name="pick"),
            ],
            store=StoreState(STORE_HOME, []),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_ALCHEMIST, STORE_HOME]
        )

        self.assertEqual(pol._shop(snap), "\x1b")
        self.assertEqual(pol.last_reason, "home:leave-with-mining-supplies")
        self.assertEqual(pol._town_store_attempted[STORE_HOME], 123)
        self.assertEqual(pol._town_errand_plan.index, 1)

        outside = replace(snap, store=None)
        self.assertNotEqual(pol._next_required_store_type(outside), STORE_HOME)
        self.assertNotEqual(pol._shopping_approach_step(outside), Position(10, 11))

    def test_idle_consumable_disposal_does_not_trigger_shadow_drift(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=123,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, 4, name="pick"),
            ],
            store=StoreState(STORE_HOME, []),
        )
        outside = replace(snap, store=None)
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._home_disposal_pass = True
        pol._home_disposal_pending = (("missing", TVAL_FOOD, 1), "destroy")

        # An idle disposal scan no longer owns a Home approach; it remains
        # available when executable Home work has already opened the store.
        self.assertNotEqual(pol._next_required_store_type(outside), STORE_HOME)
        pol._shop(snap)
        pol._next_required_store_type(outside)

        self.assertEqual(pol._town_visit_ledger.drift_warnings, [])

    def test_idle_consumable_disposal_completion_releases_mining_fast_exit(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=123,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, 4, name="pick"),
            ],
            store=StoreState(STORE_HOME, []),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._home_disposal_pass = True

        self.assertEqual(pol._shop(snap), " ")
        self.assertEqual(pol._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home-disposal:scan-complete")
        self.assertFalse(pol._home_disposal_pass)

        self.assertEqual(pol._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home:leave-with-mining-supplies")

    def test_completed_single_home_plan_does_not_rearm_same_owner(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_HOME
                ),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=123,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, 4, name="pick"),
            ],
            store=StoreState(STORE_HOME, []),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._town_errand_plan = TownErrandPlan(
            [STORE_HOME],
            need_categories={STORE_HOME: ("completed-home-owner",)},
        )
        pol._town_need_candidates = lambda _snapshot: [
            TownNeed(STORE_HOME, "idle-consumable-scan", "home-first")
        ]

        self.assertEqual(pol._shop(snap), "\x1b")
        self.assertEqual(pol._town_errand_plan.index, 1)

        outside = replace(snap, store=None)
        self.assertEqual(pol._next_required_store_type(outside), STORE_HOME)
        self.assertEqual(pol._town_errand_plan.index, 0)

    def test_mining_home_completion_does_not_consume_post_alchemist_home_phase(self):
        """The first Home stop must advance before its attempted latch is set."""
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=123,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, 4, name="pick"),
            ],
            store=StoreState(STORE_HOME, []),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_ALCHEMIST, STORE_HOME]
        )

        self.assertEqual(pol._shop(snap), "\x1b")
        self.assertEqual(pol._town_errand_plan.index, 1)
        self.assertEqual(pol._town_errand_plan.completed_this_visit, [STORE_HOME])

        active = [
            TownNeed(STORE_ALCHEMIST, "identification-source", "before-withdrawal"),
            TownNeed(STORE_HOME, "identification-withdrawal", "post-alchemist-home"),
        ]
        pol._town_need_candidates = lambda snapshot: list(active)
        pol._town_terminal_transitions = lambda snapshot: None
        outside = replace(snap, store=None)

        self.assertEqual(pol._next_required_store_type(outside), STORE_ALCHEMIST)
        self.assertEqual(pol._town_errand_plan.index, 0)

    def test_fundraising_does_not_revisit_home_for_unrelated_deposit(self):
        spare = item(
            "z",
            TVAL_RING,
            1,
            name="spare ring",
            known=True,
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_HOME
                ),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(detection=5),
                item("y", TVAL_DIGGING, 4, name="pick"),
                item(
                    "u", TVAL_LITE, SV_LITE_TORCH,
                    count=TORCH_THROW_TARGET, fuel=2500,
                ),
                spare,
            ],
            equipment=[self._lantern()],
        )
        pol = HengbotPolicy()
        set_known_target(pol)
        pol._fundraising_mode = "mine"

        self.assertIsNotNone(pol._find_home_deposit(snap))
        self.assertEqual(pol._next_required_store_type(snap), STORE_GENERAL)

    def test_fundraising_searches_all_home_pages_for_digger(self):
        inventory = self._strict_supplies(detection=5)
        first_page = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=StoreState(
                STORE_HOME,
                [store_item("a", TVAL_RING, 1, name="ring", is_equipment=True)],
            ),
        )
        second_page = Snapshot(
            first_page.player,
            first_page.grids,
            [],
            floor_key=first_page.floor_key,
            town_flag=True,
            inventory=inventory,
            store=StoreState(
                STORE_HOME,
                [store_item("b", TVAL_DIGGING, 4, name="pick", is_equipment=True)],
            ),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"

        self.assertEqual(pol._shop(first_page), " ")
        self.assertEqual(pol.last_reason, "home:seek-digging-tool-page")
        self.assertEqual(pol._shop(second_page), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home:queue-digging-tool-withdraw")

    def test_fundraising_promotion_preserves_just_visited_store_latch(self):
        snap = Snapshot(
            player(10, 10, gold=268, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        policy._town_errand_plan = policy_module.TownErrandPlan(
            [STORE_ALCHEMIST]
        )

        policy._town_special_key(snap)

        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertIn(STORE_ALCHEMIST, policy._town_store_attempted)
        self.assertNotEqual(
            policy._next_required_store_type(snap), STORE_ALCHEMIST
        )

    def test_fundraising_buys_treasure_detection_before_identify(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._identification_need = "normal"
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): GridState(
                    position=Position(10, 11),
                    known=True,
                    passable=True,
                    wall=False,
                    has_monster=False,
                    has_down_stairs=False,
                    has_up_stairs=False,
                    unsafe=False,
                    store_number=STORE_HOME,
                ),
            },
            [],
            inventory=[item("f", TVAL_FOOD, 35, count=5)],
            store=StoreState(
                STORE_ALCHEMIST,
                [
                    store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=20),
                    store_item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, price=10),
                ],
            ),
        )
        purchase = pol._next_purchase(snap)
        self.assertIsNotNone(purchase)
        self.assertTrue(purchase.is_treasure_detection_scroll)

    def test_fundraising_buys_detection_scroll_buffer(self):
        target = 4
        detection = store_item(
            "t",
            TVAL_SCROLL,
            SV_SCROLL_DETECT_TREASURE,
            price=10,
            count=50,
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(detection=target),
            store=StoreState(STORE_ALCHEMIST, [detection]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._planned_mining_runs = target

        self.assertEqual(
            policy._shop(snap),
            f"pt{DETECTION_SCROLL_BUFFER}\r\r",
        )
        self.assertEqual(policy.last_reason, "shop:buy-treasure-detection")

    def test_detection_buffer_is_not_a_departure_requirement(self):
        target = 4
        snap = Snapshot(
            player(10, 10, gold=0, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(detection=target),
                item("z", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            equipment=[self._lantern()],
            store=StoreState(STORE_ALCHEMIST, []),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._planned_mining_runs = target

        self.assertTrue(policy._fundraising_supplies_ready(snap))
        self.assertNotEqual(
            policy._next_required_store_type(snap), STORE_ALCHEMIST
        )
        self.assertIsNone(policy._town_special_key(snap))
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertIsNone(policy._town_restock_wait_until)

    def test_fundraising_routes_minimum_kit_before_dive_supplies(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        snap = Snapshot(
            player(10, 10, gold=FUNDRAISING_KIT_RESERVE, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[item("f", TVAL_FOOD, 35, count=9)],
        )

        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)
        pol._town_store_attempted[STORE_HOME] = 0
        self.assertEqual(pol._next_required_store_type(snap), STORE_GENERAL)
        pol._town_store_attempted[STORE_GENERAL] = 0
        self.assertEqual(pol._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_tight_gold_skips_dive_supply_that_breaks_fundraising_reserve(self):
        pol = HengbotPolicy()
        pol._deepest_level = 10
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_KIT_RESERVE + 50,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
                item("f", TVAL_FOOD, 35, count=9),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            ],
            equipment=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
            store=StoreState(
                STORE_ALCHEMIST,
                [store_item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, price=60)],
            ),
        )

        self.assertIsNone(pol._next_purchase(snap))
        self.assertGreaterEqual(snap.player.gold, FUNDRAISING_KIT_RESERVE)

    def test_owned_fundraising_kit_leaves_purchase_order_unchanged(self):
        pol = HengbotPolicy()
        pol._deepest_level = 10
        teleport = store_item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, price=100)
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
                item("x", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
                item("f", TVAL_FOOD, 35, count=9),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            ],
            equipment=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
            store=StoreState(STORE_ALCHEMIST, [teleport]),
        )

        self.assertEqual(pol._next_purchase(snap), teleport)

    def test_reserve_never_blocks_fundraising_kit_purchase(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        digger = store_item(
            "d", TVAL_DIGGING, SV_DIGGING_SHOVEL, price=FUNDRAISING_KIT_RESERVE
        )
        snap = Snapshot(
            player(10, 10, gold=FUNDRAISING_KIT_RESERVE, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            store=StoreState(STORE_GENERAL, [digger]),
        )

        self.assertEqual(pol._next_purchase(snap), digger)

    def test_fundraising_buys_optional_second_digger_with_one_at_home(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        home_digger = store_item(
            "h", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        pol._equipment_catalog.observe_home_page([home_digger])
        shop_digger = store_item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL, price=100)
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(detection=5),
            equipment=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
            store=StoreState(STORE_GENERAL, [shop_digger]),
        )

        self.assertEqual(pol._next_purchase(snap), shop_digger)

    def test_identify_errand_still_buys_departure_teleport_scrolls(self):
        # An identify errand must not short-circuit _next_purchase: while at the
        # Alchemist (which also sells teleport scrolls) the bot has to keep
        # stocking departure supplies. Otherwise the store is marked 'attempted'
        # after the identify visit and the bot, still short a teleport scroll,
        # can never become departure-ready and wanders the town instead.
        pol = HengbotPolicy()
        pol._identification_need = "normal"  # errand active
        pol._deepest_level = 10  # planned depth deep enough to require teleports
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, count=5),  # identify source in hand
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
                item("f", TVAL_FOOD, 35, count=9),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            ],
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)],
            store=StoreState(
                STORE_ALCHEMIST,
                [
                    store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=20),
                    store_item("t", TVAL_SCROLL, 9, price=100),  # teleport scroll
                ],
            ),
        )
        purchase = pol._next_purchase(snap)
        self.assertIsNotNone(purchase)
        self.assertTrue(purchase.is_teleport_scroll)

    def test_fundraising_seeks_digging_tool_before_identification_store(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._identification_need = "normal"
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): GridState(
                    position=Position(10, 11),
                    known=True,
                    passable=True,
                    wall=False,
                    has_monster=False,
                    has_down_stairs=False,
                    has_up_stairs=False,
                    unsafe=False,
                    store_number=STORE_HOME,
                ),
            },
            [],
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item(
                    "t",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=MINING_RUNS_PER_SET,
                ),
            ],
        )
        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)
        pol._town_store_attempted[STORE_HOME] = 0
        self.assertEqual(pol._next_required_store_type(snap), STORE_GENERAL)

    def test_full_weapon_smith_is_latched_after_repeated_rejection(self):
        # A full store accepts the weapon type yet rejects the sale (no room).
        # After the stuck detector proves the rejection, the store must be latched
        # as sale-refused so the withdraw/route logic stops feeding it more.
        pol = HengbotPolicy()
        spare = item("k", 23, 1, name="a Dagger", is_equipment=True, known=True)
        stock = store_item("a", 23, 2, name="a Long Sword", price=50)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[spare],
            store=StoreState(store_type=STORE_WEAPON, items=[stock]),
        )
        # Identical-snapshot calls simulate the store rejecting the sale
        # (pack/gold/turn never change). The first emits the sell; the second,
        # seeing the unchanged board, must LEAVE (Escape) rather than re-emit a
        # multi-key sell whose trailing keys would desync into the store command
        # loop after the "no room" message — and latch the store as full.
        first = pol._store_sell_key(
            snap, spare, "shop:sell-inferior-weapon",
            rejected_reason="shop:unsellable-weapon-leave",
        )
        second = pol._store_sell_key(
            snap, spare, "shop:sell-inferior-weapon",
            rejected_reason="shop:unsellable-weapon-leave",
        )
        self.assertNotEqual(first, LEAVE_STORE_KEY)
        self.assertEqual(second, LEAVE_STORE_KEY)
        self.assertIn(STORE_WEAPON, pol._store_sale_refused)

    def test_cross_turn_sell_rejection_is_latched_on_third_attempt(self):
        pol = HengbotPolicy()
        pile = item("j", TVAL_WAND, 1, name="wands", count=3, charges=9)

        def snapshot(turn, carried=pile):
            return Snapshot(
                player(10, 10),
                {Position(10, 10): grid(10, 10)},
                [],
                turn=turn,
                floor_key=(0, 0, 0),
                inventory=[carried],
                store=StoreState(store_type=STORE_MAGIC, items=[]),
            )

        self.assertEqual(pol._store_sell_key(snapshot(1), pile, "shop:sell-device"), "{j@0\r")
        self.assertEqual(pol._store_sell_key(snapshot(2), pile, "shop:sell-device"), LEAVE_STORE_KEY)
        self.assertEqual(
            pol._store_sell_key(
                snapshot(3), pile, "shop:sell-device",
                rejected_reason="shop:unsellable-device-leave",
            ),
            LEAVE_STORE_KEY,
        )
        self.assertEqual(pol.last_reason, "shop:unsellable-device-leave")
        self.assertIn(pol._item_signature(pile), pol._unsellable_items)
        self.assertIn(STORE_MAGIC, pol._store_sale_refused)

    def test_cross_turn_sell_attempts_reset_after_count_decreases(self):
        pol = HengbotPolicy()
        pile = item("j", TVAL_WAND, 1, name="wands", count=3, charges=9)
        reduced = replace(pile, count=2, charges=6)

        def snapshot(turn, carried):
            return Snapshot(
                player(10, 10),
                {Position(10, 10): grid(10, 10)},
                [],
                turn=turn,
                floor_key=(0, 0, 0),
                inventory=[carried],
                store=StoreState(store_type=STORE_MAGIC, items=[]),
            )

        self.assertNotEqual(
            pol._store_sell_key(snapshot(1, pile), pile, "shop:sell-device"),
            LEAVE_STORE_KEY,
        )
        self.assertEqual(
            pol._store_sell_key(snapshot(2, pile), pile, "shop:sell-device"),
            LEAVE_STORE_KEY,
        )
        self.assertEqual(
            pol._store_sell_key(snapshot(3, reduced), reduced, "shop:sell-device"),
            LEAVE_STORE_KEY,
        )
        self.assertEqual(
            pol._store_sell_key(snapshot(4, reduced), reduced, "shop:sell-device"),
            LEAVE_STORE_KEY,
        )
        self.assertEqual(
            pol._store_sell_key(snapshot(5, reduced), reduced, "shop:sell-device"),
            LEAVE_STORE_KEY,
        )

    def test_no_spare_withdrawal_while_weapon_smith_is_full(self):
        # Once the smith is full this visit, pulling more spares from Home only
        # churns futile trips to a store with no room — do not withdraw.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._store_sale_refused.add(STORE_WEAPON)
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        spare = store_item(
            "a", 23, 1, name="a Dagger", is_equipment=True, aware=True, known=True,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[ego],
            store=StoreState(store_type=STORE_HOME, items=[spare]),
        )

        pol.choose_key(snap)

        self.assertNotEqual(pol.last_reason, "home:withdraw-inferior-weapon")

    def test_full_smith_lets_inferior_spares_shelve_back(self):
        # Leftover spares stuck in the pack when the smith fills must become
        # depositable, or a pack of unsellable weapons stalls town departure.
        pol = HengbotPolicy()
        set_known_target(pol)
        pol._store_sale_refused.add(STORE_WEAPON)
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        spare = item(
            "b", 23, 1, name="a Dagger", is_equipment=True, known=True,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[spare],
            equipment=[ego],
        )

        self.assertEqual(pol._find_home_deposit(snap), spare)

    def test_low_gold_itself_starts_fundraising_with_home_first(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_gold_at_start_threshold_does_not_start_fundraising(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        policy._next_required_store_type(snap)

        self.assertIsNone(policy._fundraising_mode)

    def test_restock_suppression_blocks_low_gold_trigger(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._town_restock_suppressed = True

        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertIsNone(policy._fundraising_mode)

    def test_cycle_break_preserves_shallow_recall_purchase_errand(self):
        snap = Snapshot(
            player(10, 10, gold=3616, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._last_return_trigger = "recall-low"

        policy._break_town_cycle(snap)

        self.assertFalse(policy._town_restock_suppressed)
        self.assertEqual(policy._next_required_store_type(snap), STORE_TEMPLE)
        self.assertNotIn(STORE_TEMPLE, policy._town_store_attempted)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_town_requires_fifth_recall_after_shops_are_exhausted(self):
        snap = Snapshot(
            player(10, 10, gold=8599, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=100,
            inventory=self._strict_supplies(recall=3, teleport=4, critical=4),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 4
        policy.prime(snap)

        self.assertEqual(policy._next_required_store_type(snap), STORE_TEMPLE)
        recall_requirement = next(
            requirement
            for requirement in policy.procurement_requirements(snap)
            if requirement["item"] == "Word of Recall scrolls"
        )
        self.assertEqual(recall_requirement["current"], 3)
        self.assertEqual(recall_requirement["target"], 6)

        policy._town_store_attempted.update(
            {STORE_TEMPLE: 0, STORE_ALCHEMIST: 0, STORE_BLACK: 0}
        )
        self.assertFalse(policy._recall_departure_ready(snap))

    def test_expired_recall_restock_wait_routes_to_released_store_publicly(self):
        from hengbot.town_maps import find_outpost_map

        path = find_outpost_map(Path(__file__).resolve().parent.parent)
        if path is None:
            self.skipTest("Outpost map not found")
        town_map = parse_town_map(path)
        alchemist = town_map.store_position(STORE_ALCHEMIST)
        start = Position(alchemist.y + 1, alchemist.x)
        snap = Snapshot(
            player(
                start.y, start.x, gold=8000, class_id=PLAYER_CLASS_WARRIOR,
                abilities=frozenset(
                    {"resist_pois", "resist_cold", "resist_elec", "resist_acid"}
                ),
            ),
            {start: grid(start.y, start.x)},
            [], turn=100, inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()], recall_dungeon_id=14, recall_depth=29,
            entered_dungeon_ids=(1, 14), width=town_map.width,
            height=town_map.height,
        )
        policy = HengbotPolicy(town_map=town_map)
        policy._observe(snap)
        policy._deepest_level = 31
        policy._target_dungeon_id = 14
        policy._char_dump_done_this_visit = True
        # This visit exhausted every current errand. Restock releases only the
        # two recall suppliers, so the real router must choose between them.
        policy._town_store_attempted.update({store_type: 0 for store_type in range(8)})
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: public restock-release routing uses the real map/router while isolating unrelated readiness collaborators
        policy._food_ready = lambda _snapshot: True
        policy._light_ready = lambda _snapshot: True
        policy._teleport_ready = lambda _snapshot: True
        policy._cure_critical_ready = lambda _snapshot: True
        policy._identify_staff_ready = lambda _snapshot: True
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._equipment_departure_ready = lambda _snapshot: True
        policy._find_home_deposit = lambda _snapshot: None

        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)
        expiry = replace(
            snap, turn=policy._town_restock_wait_until,
        )
        released = policy._retry_after_store_restock(
            expiry, (STORE_TEMPLE, STORE_ALCHEMIST)
        )
        self.assertEqual(released, STORE_TEMPLE)
        self.assertEqual(
            policy._released_restock_store_key(
                expiry, (STORE_TEMPLE, STORE_ALCHEMIST)
            ),
            "8",
        )
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertEqual(policy._shopping_approach_store_type, STORE_ALCHEMIST)
        self.assertIsNone(policy._town_restock_wait_until)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_failed_alchemist_approach_allows_teleport_short_departure(self):
        snap = Snapshot(
            player(10, 10, gold=8000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=200,
            inventory=self._strict_supplies(recall=7, teleport=0, critical=3),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy.prime(snap)
        policy._deepest_level = 11
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        policy._shopping_stuck = True

        self.assertIsNone(policy._shopping_approach_step(snap))
        self.assertFalse(policy._shopping_stuck)
        self.assertIn(STORE_ALCHEMIST, policy._town_store_attempted)
        self.assertNotEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)

    def test_defers_star_identify_candidate_and_releases_home_latch(self):
        target = item(
            "a",
            23,
            1,
            name="ego sword",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=300,
            inventory=[*self._strict_supplies(recall=7), target],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy.prime(snap)
        signature = policy._item_signature(target)
        policy._home_pending_item = signature
        policy._identification_candidate = signature
        policy._identification_need = "full"
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        self.assertIsNone(policy._town_item_processing_key(snap))
        self.assertNotEqual(policy.last_reason, "home:need-identify")
        self.assertIsNone(policy._identification_need)
        self.assertIsNone(policy._home_pending_item)
        self.assertIsNone(policy._home_pending_slot)
        self.assertFalse(policy._home_candidate_waiting)
        self.assertIn(signature, policy._deferred_home_items)
        self.assertNotEqual(
            policy._next_required_store_type(snap), STORE_ALCHEMIST
        )
        self.assertIsNone(policy._town_restock_wait_until)

        home = replace(
            snap,
            store=StoreState(store_type=STORE_HOME, items=[]),
        )
        policy.choose_key(home)
        self.assertNotEqual(policy.last_reason, "home:leave-with-item")

    def test_unobserved_identify_candidate_does_not_claim_home_route(self):
        target = item(
            "a",
            23,
            1,
            name="ego sword",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, gold=3000, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11, unsafe=False), store_number=STORE_HOME
                ),
            },
            [],
            turn=300,
            inventory=[*self._strict_supplies(recall=7), star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy.prime(snap)
        policy._home_knowledge_scan_requested = True
        policy._identification_candidate = policy._item_signature(target)
        policy._identification_need = "full"
        policy._home_candidate_waiting = True
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        self.assertNotEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertNotEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)
        self.assertNotEqual(policy.last_reason, "shop:approach")

    def test_full_identify_errand_precedes_unrelated_home_deposit(self):
        target = item(
            "a",
            23,
            1,
            name="ego sword",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        spare = item(
            "b", 36, 1, name="spare armour", known=True, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): GridState(
                    position=Position(10, 11),
                    known=True,
                    passable=True,
                    wall=False,
                    has_monster=False,
                    has_down_stairs=False,
                    has_up_stairs=False,
                    unsafe=False,
                    store_number=STORE_HOME,
                ),
            },
            [],
            inventory=[
                target,
                spare,
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=OIL_TARGET),
            ],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        set_known_target(policy)
        policy._home_pending_item = policy._item_signature(target)
        policy._identification_candidate = policy._item_signature(target)
        policy._identification_need = "full"

        self.assertEqual(policy._find_home_deposit(snap), spare)
        self.assertEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_shallow_mining_uses_three_carried_scrolls_as_partial_campaign(self):
        snap = self._shallow_partial_mining_snapshot(3)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy._next_required_store_type(snap), STORE_GENERAL)
        policy._town_store_attempted[STORE_GENERAL] = 0
        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertEqual(policy._planned_mining_runs, 3)
        self.assertEqual(policy._mining_detection_scroll_target(snap), 3)
        self.assertTrue(policy._fundraising_supplies_ready(snap))

    def test_shallow_mining_uses_one_carried_scroll_as_partial_campaign(self):
        snap = self._shallow_partial_mining_snapshot(1)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy._next_required_store_type(snap), STORE_GENERAL)
        policy._town_store_attempted[STORE_GENERAL] = 0
        self.assertIsNone(policy._next_required_store_type(snap))
        self.assertEqual(policy._planned_mining_runs, 1)
        self.assertEqual(policy._mining_detection_scroll_target(snap), 1)

    def test_shallow_mining_with_zero_scrolls_still_shops(self):
        snap = self._shallow_partial_mining_snapshot(0)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertIsNone(policy._planned_mining_runs)

    def test_detection_stockout_with_sufficient_gold_switches_to_normal_exploration(self):
        snap = Snapshot(
            player(
                10, 10, level=7, gold=FUNDRAISING_START_GOLD + 7000,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(
                    recall=5, detection=0, teleport=5, critical=5,
                ),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            ],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._town_store_attempted[STORE_HOME] = 0
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        policy._next_required_store_type(snap)

        self.assertIsNone(policy._fundraising_mode)
        self.assertFalse(
            policy._ledger_departure_shortages(
                policy._supply_ledger(snap, policy._planned_depth())
            )
        )

    def test_detection_stockout_rearms_normal_supply_stores_before_departure(self):
        snap = Snapshot(
            player(
                10, 10, level=7, gold=FUNDRAISING_START_GOLD + 7000,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(
                    recall=0, detection=0, teleport=5, critical=5,
                ),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            ],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._town_store_attempted[STORE_HOME] = 0
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        self.assertIn(
            policy._next_required_store_type(snap),
            {STORE_GENERAL, STORE_MAGIC, STORE_TEMPLE, STORE_ALCHEMIST},
        )
        self.assertIsNone(policy._fundraising_mode)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_known_distant_store_uses_native_travel_without_bfs_memory(self):
        home = Position(45, 123)
        snap = Snapshot(
            player(36, 90, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(36, 90): grid(36, 90),
                home: replace(grid(home.y, home.x), store_number=STORE_HOME),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda snapshot: STORE_HOME
        policy._build_grid_index(snap)

        step = policy._shopping_approach_step(snap)
        self.assertEqual(step, home)
        self.assertEqual(
            policy._shopping_approach_key(snap, step, "shop:travel"),
            "\x1b`n(.",
        )

    def test_store_entry_snapshot_waits_instead_of_stepping_back_off(self):
        entrance = Position(10, 10)
        snap = Snapshot(
            player(entrance.y, entrance.x, class_id=PLAYER_CLASS_WARRIOR),
            {
                entrance: replace(
                    grid(entrance.y, entrance.x), store_number=STORE_HOME
                ),
                # Retained Home-cycle shape: the only eligible step-off is
                # east, so the historical projection names the exact key '6'.
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda snapshot: STORE_HOME
        policy._build_grid_index(snap)

        step = policy._shopping_approach_step(snap)

        self.assertEqual(step, entrance)
        self.assertEqual(
            policy._shopping_approach_key(snap, step, "shop:travel"), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "shop:travel:await-entry")

        # Public emission must preserve the entry command.  Replacing this WAIT
        # with a direction lets that direction land in the store dispatcher.
        policy = HengbotPolicy()
        seed_character_calibration(policy, snap)
        policy._home_knowledge_scan_requested = True
        self.assertEqual(policy.choose_key(snap), WAIT_KEY)
        self.assertEqual(policy.last_reason, "shop:travel:await-entry")

        retry_step = policy._shopping_approach_step(snap)
        self.assertEqual(retry_step, Position(10, 11))

    def test_store_exit_snapshot_still_steps_off_for_reentry(self):
        entrance = Position(10, 10)
        snap = Snapshot(
            player(entrance.y, entrance.x, class_id=PLAYER_CLASS_WARRIOR),
            {
                entrance: replace(
                    grid(entrance.y, entrance.x), store_number=STORE_HOME
                ),
                Position(9, 11): grid(9, 11),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda snapshot: STORE_HOME
        policy._last_snapshot_was_store = True
        policy._build_grid_index(snap)

        self.assertEqual(policy._shopping_approach_step(snap), Position(9, 11))

    def test_unconfirmed_alchemist_purchase_flicker_does_not_reenter(self):
        entrance = Position(37, 91)
        snap = Snapshot(
            player(entrance.y, entrance.x, class_id=PLAYER_CLASS_WARRIOR),
            {
                entrance: replace(
                    grid(entrance.y, entrance.x), store_number=STORE_ALCHEMIST
                ),
                Position(36, 90): grid(36, 90),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda snapshot: STORE_ALCHEMIST
        policy._last_snapshot_was_store = True
        policy._town_visit_ledger.pending_store_transaction = (
            STORE_ALCHEMIST,
            1,
        )
        policy._build_grid_index(snap)

        step = policy._shopping_approach_step(snap)

        self.assertEqual(step, entrance)
        self.assertEqual(
            policy._shopping_approach_key(snap, step, "shop:travel"), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "shop:travel:await-entry")

    def test_bounded_store_transaction_retry_still_reenters_for_real_work(self):
        entrance = Position(37, 91)
        retry = Position(36, 90)
        snap = Snapshot(
            player(entrance.y, entrance.x, class_id=PLAYER_CLASS_WARRIOR),
            {
                entrance: replace(
                    grid(entrance.y, entrance.x), store_number=STORE_ALCHEMIST
                ),
                retry: grid(retry.y, retry.x),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda snapshot: STORE_ALCHEMIST
        policy._last_snapshot_was_store = True
        policy._town_visit_ledger.pending_store_transaction = (
            STORE_ALCHEMIST,
            1,
        )
        policy._town_visit_ledger.pending_store_context_waits = STORE_STUCK_LIMIT
        policy._build_grid_index(snap)

        self.assertEqual(policy._shopping_approach_step(snap), retry)

    def test_home_rearm_skips_no_teleport_weapon_and_withdraws_safe_one(self):
        blocked = item(
            "main_hand",
            23,
            1,
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        home = StoreState(
            STORE_HOME,
            [
                store_item(
                    "a", 23, 1, is_artifact=True, known_flags=frozenset({TR_NO_TELE})
                ),
                store_item("b", 23, 2, name="safe scimitar"),
            ],
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): self._home_tile(10, 10)},
            [],
            equipment=[blocked, self._lantern()],
            store=home,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home-errand:filed:combat-weapon")

    def test_routes_to_home_to_re_arm_even_when_home_is_not_visible(self):
        # Pickaxe wielded, no weapon in the pack: route to the Home to withdraw the real
        # weapon before diving — even with NO Home tile in view (an unlit Home is absent
        # from the grids). _shopping_approach_step walks there via the static town map;
        # gating this on a visible Home left the character wandering the town unable to
        # re-arm (the stuck:wander the user hit).
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},  # no Home tile visible
            [],
            inventory=list(self._strict_supplies(recall=1, detection=4)),
            equipment=[tool, self._lantern()],
        )
        pol = HengbotPolicy()
        self.assertFalse(pol._home_available(snap))  # Home not in view
        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)

    def test_routes_home_when_pack_weapons_are_unknown_or_cursed(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="shovel", is_equipment=True,
        )
        unknown = item(
            "u", 21, 5, name="unknown mace", is_equipment=True, known=False,
        )
        cursed = item(
            "c", 23, 1, name="cursed sword", is_equipment=True,
            known=True, is_cursed=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[unknown, cursed, *self._strict_supplies(recall=1, detection=4)],
            equipment=[tool, self._lantern()],
        )

        self.assertEqual(HengbotPolicy()._next_required_store_type(snap), STORE_HOME)

    def test_invalidated_home_catalog_routes_back_for_rescan(self):
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)

        self.assertFalse(policy._equipment_catalog.home_scan_complete)
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)
        policy._shopping_stuck = True
        policy._shopping_approach_step(town)
        self.assertFalse(policy._shopping_stuck)

    def test_unavailable_identify_rearms_blocked_home_for_catalog_scan(self):
        """A deferred candidate must hand Home from identify to scan ownership."""
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=12224),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
        incomplete = store_item(
            "a", 22, 20, name="unidentified mace", known=False,
            fully_known=False, is_equipment=True,
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(incomplete)
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._identification_need = "normal"
        policy._identification_candidate = signature
        policy._home_candidate_waiting = True
        policy._town_store_attempted.update(
            {STORE_HOME: town.turn, STORE_ALCHEMIST: town.turn}
        )
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_ALCHEMIST],
            index=2,
            blocked_this_visit=[STORE_HOME, STORE_ALCHEMIST],
        )

        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)
        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertEqual(policy._identification_need, "normal")
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertNotIn(
            STORE_HOME, policy._town_errand_plan.blocked_this_visit
        )

    def test_complete_home_scan_routes_back_to_incomplete_item_page(self):
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
        incomplete_ego = store_item(
            "a", 31, 1, name="partly known ego gloves", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        policy = HengbotPolicy()
        seed_character_calibration(policy, town)
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete_ego])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete_ego])

        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)

    def test_complete_home_scan_does_not_route_to_deferred_incomplete_item(self):
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
        incomplete = store_item(
            "a", 23, 4, name="unidentified dagger", known=False,
            fully_known=False, is_equipment=True,
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._deferred_home_items.add(policy._item_signature(incomplete))
        policy._home_candidate_waiting = False

        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertFalse(policy._has_actionable_incomplete_home_item(town))
        self.assertNotEqual(policy._next_required_store_type(town), STORE_HOME)

    def test_home_normal_identify_defers_after_empty_alchemist_visit(self):
        town = self._ready_home_town(gold=FUNDRAISING_START_GOLD)
        candidate = store_item(
            "a", 23, 4, name="unidentified dagger", known=False,
            fully_known=False, pseudo_feeling="good", is_equipment=True,
        )
        home = replace(
            town,
            store=StoreState(store_type=STORE_HOME, items=[candidate]),
            town_flag=False,
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(candidate)
        policy._town_store_attempted[STORE_ALCHEMIST] = town.turn

        self.assertIsNone(policy._find_home_candidate(home))
        self.assertIn(signature, policy._deferred_home_items)

        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([candidate])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([candidate])
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertFalse(policy._has_actionable_incomplete_home_item(town))
        preparation = policy._prepare_equipment_optimization(town)
        self.assertIsNotNone(preparation)
        self.assertNotIn("home-scan-incomplete", preparation.blockers)
        self.assertNotEqual(policy._next_required_store_type(town), STORE_HOME)

        routing_policy = HengbotPolicy()
        routing_policy._equipment_catalog.refresh_carried(
            town.inventory, town.equipment
        )
        routing_policy._equipment_catalog.observe_home_page([candidate])
        routing_policy._town_store_attempted[STORE_ALCHEMIST] = town.turn
        self.assertFalse(
            routing_policy._has_actionable_incomplete_home_item(town)
        )
        self.assertIn(signature, routing_policy._deferred_home_items)

    def test_unbuyable_full_identify_home_item_persists_across_town_reentry(self):
        town = self._ready_home_town(gold=FUNDRAISING_START_GOLD)
        candidate = store_item(
            "a", 23, 4, name="partly known ego blade", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        home = replace(
            town,
            store=StoreState(
                store_type=STORE_HOME, items=[candidate], stock_num=1,
                page_top=0, page_size=52,
            ),
            town_flag=False,
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(candidate)

        self.assertEqual(policy._shop(home), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:need-full-identify")
        self.assertIn(signature, policy._unbuyable_full_identify_sigs)

        # A changed floor key exercises the fresh-town reset that clears the
        # visit-scoped deferral set. The permanent no-source fact must survive.
        policy._deferred_home_items.add(signature)
        policy._floor_key = (DUNGEON_YEEK_CAVE, 1, 0)
        policy._observe(town)
        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertIn(signature, policy._unbuyable_full_identify_sigs)
        self.assertIsNone(policy._find_home_candidate(home))

    def test_persistent_full_identify_skip_rearms_when_source_appears(self):
        candidate = store_item(
            "a", 23, 4, name="partly known ego blade", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        source = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY,
            name="scroll of star identify", known=True, aware=True,
        )
        town = replace(
            self._ready_home_town(gold=FUNDRAISING_START_GOLD),
            inventory=[*self._strict_supplies(recall=1), source],
        )
        home = replace(
            town,
            store=StoreState(store_type=STORE_HOME, items=[candidate]),
            town_flag=False,
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(candidate)
        policy._unbuyable_full_identify_sigs.add(signature)
        policy._deferred_home_items.add(signature)

        self.assertEqual(policy._find_home_candidate(home), candidate)
        self.assertEqual(policy._shop(home), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:queue-batch-withdraw")

    def test_processed_incomplete_home_item_is_not_actionable(self):
        # An incomplete Home item routes back to the Home only until a processing
        # pass burns it into _processed_home_items. After that _find_home_candidate
        # skips it, so _has_actionable_incomplete_home_item must agree — otherwise
        # home:processing-complete is reported while routing still insists on the
        # Home, looping the visit (or masking the real departure block).
        town = self._ready_home_town(gold=FUNDRAISING_START_GOLD)
        incomplete = store_item(
            "a", 31, 1, name="partly known ego gloves", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        policy = HengbotPolicy()
        # Isolate the actionable-incomplete routing from the separate
        # _home_candidate_waiting route (mirrors the deferred-item test above).
        policy._home_candidate_waiting = False
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete])

        self.assertTrue(policy._has_actionable_incomplete_home_item(town))
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)

        policy._processed_home_items.add(policy._item_signature(incomplete))
        self.assertFalse(policy._has_actionable_incomplete_home_item(town))
        self.assertNotEqual(policy._next_required_store_type(town), STORE_HOME)

    def test_unrepairable_incomplete_catalog_is_terminal_blocker(self):
        town = self._ready_home_town(gold=FUNDRAISING_GOLD_TARGET)
        policy = HengbotPolicy()
        policy._prepare_equipment_optimization = lambda snapshot: SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
        )
        policy._next_required_store_type = lambda snapshot: None

        self.assertEqual(
            policy._terminal_equipment_blocker(town),
            "equipment-incomplete-catalog",
        )

    def test_home_star_identify_source_breaks_incomplete_catalog_deadlock(self):
        """02:13 naked-strip shape reaches the stored source via choose_key."""
        unknown = item(
            "u", TVAL_SWORD, 1, name="unknown sword", known=False,
            fully_known=False, pseudo_feeling="good", is_equipment=True,
        )
        staffs = [
            item(
                slot, TVAL_STAFF, SV_STAFF_IDENTIFY,
                name="Staff of Identify", known=True, aware=True, charges=charges,
            )
            for slot, charges in (("s", 11), ("t", 8))
        ]
        ordinary = item(
            "v", TVAL_SCROLL, SV_SCROLL_IDENTIFY,
            name="Scroll of Identify", known=True, aware=True,
        )
        stored_ego = store_item(
            "a", TVAL_RING, 1, name="stored ego ring", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        stored_source = store_item(
            "b", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY,
            name="Scroll of *Identify*", known=True, aware=True, count=3,
        )
        outside = replace(
            self._ready_home_town(),
            inventory=[*self._ready_home_town().inventory, unknown, *staffs, ordinary],
            equipment=[],
        )
        policy = HengbotPolicy()
        policy._deepest_level = STAFF_IDENTIFY_MIN_DEPTH
        policy._floor_key = outside.floor_key
        policy.consume_home_knowledge((stored_ego, stored_source))
        policy._home_page_size = 12

        first_key = policy.choose_key(outside)
        self.assertEqual(first_key, "rvu")
        self.assertEqual(policy.last_reason, "identify:normal")
        self.assertEqual(policy._total_identify_staff_charges(outside), 19)
        self.assertEqual(
            next(
                requirement for requirement in policy.procurement_requirements(outside)
                if requirement["item"] == "Identify staff charges"
            ),
            {"item": "Identify staff charges", "current": 19, "target": 20, "missing": 1},
        )

        identified = replace(unknown, known=True, fully_known=True)
        outside = replace(
            outside,
            inventory=[*self._ready_home_town().inventory, identified, *staffs, ordinary],
            turn=outside.turn + 1,
        )
        signature = policy._item_signature(stored_ego)
        policy._identification_need = "full"
        policy._identification_candidate = signature
        policy._home_candidate_waiting = True
        policy._town_store_attempted[STORE_ALCHEMIST] = outside.turn
        self.assertTrue(policy._identification_need_unsatisfiable(outside))
        approach_key = policy.choose_key(outside)
        self.assertTrue(approach_key)
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertEqual(
            policy._home_errand.request.signature,
            policy._item_signature(stored_source),
        )
        entrance = replace(
            outside,
            player=replace(outside.player, position=Position(10, 11)),
            turn=outside.turn + 1,
        )
        withdrawal_key = policy.choose_key(entrance)
        self.assertEqual(withdrawal_key, WAIT_KEY, policy.last_reason)
        self.assertEqual(policy._store_visit.operation_key, "pb1\r\x1b")
        self.assertEqual(
            policy.last_reason, "home-errand:atomic-withdraw:identification"
        )
        carried_source = item(
            "w", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY,
            name=stored_source.name, known=True, aware=True,
        )
        withdrawn = replace(
            entrance,
            inventory=[*entrance.inventory, carried_source],
            turn=entrance.turn + 1,
        )
        policy._store_visit = None
        target_withdrawal = policy.choose_key(withdrawn)
        self.assertEqual(policy._home_errand.request.signature, signature)
        self.assertIsNotNone(policy._find_identification_source(withdrawn, full=True))
        self.assertFalse(policy._home_candidate_waiting)
        self.assertEqual(target_withdrawal, WAIT_KEY)
        self.assertEqual(
            policy.last_reason,
            "home-errand:atomic-withdraw:identification-catalog",
        )

    def test_unknown_jewelry_with_only_staff_routes_to_buy_identify_scroll(self):
        ring = item(
            "a",
            TVAL_RING,
            -1,
            name="unknown ring",
            aware=False,
            known=False,
            is_equipment=True,
        )
        staff = item(
            "u", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=2, name="staff"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                ring,
                staff,
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=OIL_TARGET),
            ],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertIsNone(policy._town_item_processing_key(snap))
        self.assertEqual(policy._identification_need, "normal")
        self.assertEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_carried_identify_target_is_deferred_after_scroll_stock_failure(self):
        # Regression for the second 2026-07-23 loop: a low-skill warrior tried
        # the same Staff of Identify command 30 times, then repeatedly entered
        # and left an Alchemist that had no Identify scroll.  Once that store is
        # genuinely exhausted, defer the carried target for this town visit.
        ring = item(
            "a",
            TVAL_RING,
            -1,
            name="unknown ring",
            aware=False,
            known=False,
            is_equipment=True,
        )
        staff = item(
            "u", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20, name="staff"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[ring, staff],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._observe(snap)

        policy._refresh_carried_equipment_catalog(snap)
        self.assertIsNone(policy._town_item_processing_key(snap))
        policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(
            store_type=STORE_ALCHEMIST, items=[]
        )
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
            policy._effective_town_id(snap), snap.turn
        )
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        self.assertNotEqual(
            policy._next_required_store_type(snap), STORE_ALCHEMIST
        )
        signature = policy._item_signature(ring)
        rearmed = []
        original_rearm = policy._rearm_town_store_for_new_work
        with patch.object(
            policy,
            "_rearm_town_store_for_new_work",
            side_effect=lambda store: (rearmed.append(store), original_rearm(store))[1],
        ):
            for _ in range(12):
                policy._observe(snap)
                policy._town_terminal_transitions(snap)
                self.assertIsNone(policy._town_item_processing_key(snap))

        self.assertIn(signature, policy._town_unidentifiable_carried_sigs)
        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertEqual(rearmed.count(STORE_ALCHEMIST), 0)
        self.assertIsNone(policy._identification_need)
        self.assertTrue(
            policy._town_departure_conjuncts(snap)["identification_need_clear"]
        )

        arrival = replace(snap, floor_key=(1, 1, 1), town_flag=False)
        policy._observe(arrival)
        policy._observe(snap)
        self.assertNotIn(signature, policy._town_unidentifiable_carried_sigs)
        self.assertIsNone(policy._town_item_processing_key(snap))
        self.assertEqual(policy._identification_candidate, signature)
        self.assertEqual(policy._identification_need, "normal")

    def test_affordable_identify_stock_rearms_owner_then_purchase_resolves(self):
        ring = item(
            "a", TVAL_RING, -1, name="unknown ring", aware=False,
            known=False, is_equipment=True,
        )
        scroll = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_IDENTIFY,
            name="Scroll of Identify", price=81, count=4,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=100),
            {Position(10, 10): grid(10, 10)}, [], inventory=[ring],
            equipment=[self._lantern()], town_flag=True, town_id=1, turn=40,
        )
        policy = HengbotPolicy()
        policy._refresh_carried_equipment_catalog(snap)
        self.assertIsNone(policy._town_item_processing_key(snap))
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(
            store_type=STORE_ALCHEMIST, items=[scroll]
        )
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (1, 40)

        policy._town_terminal_transitions(snap)
        self.assertEqual(policy._identification_need, "normal")
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)
        inside = replace(
            snap, store=policy._town_supplier_stock[STORE_ALCHEMIST], turn=41
        )
        self.assertEqual(policy._next_purchase_unreserved(inside), scroll)

    def test_defers_unknown_device_when_identification_is_unavailable(self):
        wand = item("a", TVAL_WAND, -1, aware=False, known=False, name="unknown wand")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[wand],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(
            store_type=STORE_ALCHEMIST, items=[]
        )
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
            policy._effective_town_id(snap), snap.turn
        )

        policy.choose_key(snap)
        self.assertIn(policy._item_signature(wand), policy._deferred_device_items)
        self.assertNotEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_batch_sale_entry_re_resolves_item_at_composition_boundary(self):
        stale = replace(
            item("j", TVAL_WAND, 1, count=2, name="wand"), inscription="@0"
        )
        current = replace(stale, count=1)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[current],
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()

        entry = policy._batch_sale_entry(snap, stale, "0")

        self.assertEqual(entry["count"], 1)
        self.assertEqual(entry["sell"], "d0y")

    def test_batch_sale_missing_or_foreign_inscription_is_visible_refusal(self):
        stale = replace(
            item("j", TVAL_WAND, 1, name="wand"), inscription="@0"
        )
        collision = replace(stale, slot="k", inscription="@1")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[collision],
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertIsNone(policy._batch_sale_entry(snap, stale, "0"))
        self.assertEqual(
            policy.last_reason, "shop:batch-sale-signature-unobserved"
        )

    def test_live_shaped_recall_purchase_completes_with_gold_and_pack_delta(self):
        snap = Snapshot(
            player(10, 10, gold=7589, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): replace(grid(10, 10), store_number=STORE_TEMPLE)}, [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_TEMPLE, items=[
                store_item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20)
            ]),
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), LEAVE_STORE_KEY)
        surface = replace(snap, store=None, turn=snap.turn + 1)
        entry = policy.choose_key(surface)
        self.assertEqual(entry, "5")
        operation = policy.choose_key(replace(snap, turn=surface.turn + 1))
        key = entry + operation
        posted = []
        sent, _ = _send_new_decision_key(
            lambda value, **_kwargs: posted.extend(value) or True,
            "door-composed-temple-store", key, None, set(), in_store=False,
            decision={"reason": policy.last_reason, "key": key},
        )
        self.assertTrue(sent)
        self.assertEqual(key, "5pa\r\x1b")
        self.assertEqual("".join(posted), key)
        state = "surface"
        for character in posted:
            if state == "surface" and character == "5":
                state = "store"
            elif state == "store" and character == "p":
                state = "buy-selection"
            elif state == "buy-selection" and character == "a":
                state = "quantity"
            elif state == "quantity" and character == "\r":
                state = "store"
            elif state == "store" and character == LEAVE_STORE_KEY:
                state = "surface"
            else:
                self.fail((state, character))
        purchased = item(
            "z", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            name="Scroll of Word of Recall",
        )
        applied = replace(
            snap,
            player=replace(snap.player, gold=7569),
            inventory=[*snap.inventory, purchased],
            store=None,
            turn=snap.turn + 1,
        )
        policy.choose_key(applied)
        self.assertEqual(state, "surface")
        self.assertEqual(snap.player.gold - applied.player.gold, 20)
        self.assertEqual(len(applied.inventory) - len(snap.inventory), 1)
        self.assertIsNone(policy._store_buy_inflight)

    def test_pile_sale_quantity_is_capped_by_retention_surplus(self):
        pile = item("j", TVAL_FOOD, FOOD_MIN_SVAL, count=3, name="rations")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[pile],
            store=StoreState(store_type=STORE_GENERAL, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()

        with patch.object(policy, "_retention_reservation", return_value=1):
            self.assertEqual(
                policy._store_sell_key(snap, pile, "shop:sell-food"),
                "{j@0\r",
            )

    def test_batch_sale_entry_owns_absent_signature_refusal(self):
        """S6 deletes the unreachable caller branch and pins the real refusal."""
        missing = replace(
            item("x", TVAL_WAND, 1, name="missing"), inscription="@0"
        )
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[], town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertIsNone(policy._batch_sale_entry(snapshot, missing, "0"))
        self.assertEqual(policy.last_reason, "shop:batch-sale-signature-unobserved")

    def test_batch_sale_inscribes_then_sells_by_stable_tags(self):
        candidates = [
            item("x", TVAL_WAND, 1, count=1, name="one"),
            item("y", TVAL_WAND, 2, count=4, name="four"),
            item("z", TVAL_WAND, 3, count=2, name="two"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=candidates,
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(policy, "_current_store_sale_candidates", return_value=candidates), patch.object(
            policy, "_retention_surplus", side_effect=lambda snapshot, target: target.count
        ):
            self.assertEqual(policy._batch_sell_key(snap), "{x@0\r")
            observed = replace(
                snap,
                inventory=[
                    replace(candidates[0], inscription="@0")
                ],
            )
            self.assertEqual(policy._batch_sell_key(observed), "d0y")

    def test_batch_sale_reuses_an_existing_exact_tag(self):
        candidates = [
            replace(item("x", TVAL_WAND, 1, name="one"), inscription="{@0}"),
            item("y", TVAL_WAND, 2, name="two"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=candidates,
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(policy, "_current_store_sale_candidates", return_value=candidates), patch.object(
            policy, "_retention_surplus", return_value=1
        ):
            self.assertEqual(policy._batch_sell_key(snap), "d0y")

    def test_collision_evidence_reinscribes_intended_item_before_sale(self):
        evidence = json.loads(
            Path("tests/fixtures/sale_inscription_collision_20260810.json")
            .read_text(encoding="utf-8")
        )
        potion = replace(
            item("b", TVAL_POTION, 1, count=2, name="Resist Heat potion"),
            inscription="@0",
        )
        staff = replace(
            item("m", TVAL_STAFF, 1, count=1, name="Light staff"),
            inscription="@0",
        )
        snap = Snapshot(
            player(10, 10, gold=evidence["gold"], class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[potion, staff],
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(
            policy, "_current_store_sale_candidates", return_value=[staff]
        ), patch.object(policy, "_retention_surplus", return_value=1):
            first = policy._batch_sell_key(snap)
            self.assertEqual(first, "{m@1\r")
            self.assertNotEqual(first, evidence["posted_key"])
            observed = replace(
                snap, inventory=[potion, replace(staff, inscription="@1")]
            )
            self.assertEqual(policy._batch_sell_key(observed), "d1y")
            self.assertNotIn("d0", first + "d1y")

    def test_unique_preinscribed_sale_still_composes_directly(self):
        sale = replace(item("m", TVAL_STAFF, 1, name="staff"), inscription="@7")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[sale],
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(policy, "_retention_surplus", return_value=1):
            self.assertEqual(policy._batch_sell_key(snap, [sale]), "d7y")

    def test_sale_refuses_when_no_unique_numeric_tag_is_available(self):
        blockers = [
            replace(item(chr(ord("a") + digit), TVAL_STAFF, digit + 1),
                    inscription=f"@{digit}")
            for digit in range(10)
        ]
        intended = replace(
            item("m", TVAL_STAFF, 20, name="intended"), inscription="@0"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            inventory=[*blockers, intended],
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._batch_sell_key(snap, [intended]), LEAVE_STORE_KEY)
        self.assertEqual(
            policy.last_reason, "shop:sale-inscription-ambiguous-leave"
        )

    def test_batch_straggler_advances_attempt_and_does_not_rebatch(self):
        candidates = [
            item("x", TVAL_WAND, 1, name="one", count=2),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=candidates,
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(policy, "_current_store_sale_candidates", return_value=candidates), patch.object(
            policy, "_retention_surplus", return_value=1
        ):
            self.assertEqual(policy._batch_sell_key(snap), "{x@0\r")
            observed = replace(
                snap,
                inventory=[
                    replace(candidates[0], inscription="@0"),
                ],
            )
            self.assertEqual(policy._batch_sell_key(observed), "d01\ry")
            remaining = replace(
                snap, inventory=[replace(candidates[0], inscription="@0")]
            )
            self.assertEqual(policy._batch_sell_key(remaining), LEAVE_STORE_KEY)
            self.assertEqual(policy.last_reason, "shop:one-shot-sale-observed")
            self.assertEqual(
                policy._store_sell_attempt,
                (policy._item_signature(candidates[0]), 2, 1),
            )

    def test_sale_does_not_run_when_inscription_cannot_be_bound(self):
        blocked = replace(
            item("j", TVAL_WAND, 1, name="wand"), inscription="@q1"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[blocked],
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:sale-inscription-unavailable-leave")

    def test_nonpositive_surplus_sells_the_whole_offered_pile(self):
        pile = item("j", TVAL_WAND, 1, count=3, name="pile")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[pile],
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
        )
        policy = HengbotPolicy()
        with patch.object(policy, "_retention_surplus", return_value=0):
            self.assertEqual(policy._store_sell_key(snap, pile, "shop:sell"), "{j@0\r")

    def test_mana_race_counts_charges_across_stacked_identify_staves(self):
        devices = [
            item("k", TVAL_WAND, 6, charges=5, name="stone to mud"),
            item("l", TVAL_STAFF, SV_STAFF_IDENTIFY, count=3, charges=7,
                 name="identify stack"),
            item("m", TVAL_STAFF, SV_STAFF_IDENTIFY, count=2, charges=6,
                 name="identify stack"),
            item("n", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=3,
                 name="identify staff"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR,
                   food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=devices,
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._deepest_level = 25

        self.assertEqual(policy._total_identify_staff_charges(snap), 36)
        self.assertEqual(policy._count_mana_food_uses(snap), 36)
        self.assertEqual(policy._find_surplus_identify_staff(snap).slot, "n")
        self.assertEqual(policy._find_device_sale(snap).slot, "n")
        self.assertNotIn(
            "Identify staff charges",
            {entry["item"] for entry in policy.procurement_requirements(snap)},
        )

        ware = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY,
            price=162, pval=3, count=11,
        )
        stocked_shop = replace(
            snap, store=StoreState(store_type=STORE_MAGIC, items=[ware])
        )
        self.assertIsNone(policy._next_purchase_unreserved(stocked_shop))

    def test_mana_reserve_counts_withdrawable_home_device_charges(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR,
                   food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            town_flag=True,
        )
        home_wand = item(
            "a", TVAL_WAND, 6, count=2, charges=9,
            known=True, name="Home food wand",
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((home_wand,))

        self.assertEqual(policy._count_mana_food_uses(snap), 18)
        self.assertEqual(policy._count_mana_food_devices(snap), 2)
        self.assertTrue(policy._food_ready(snap))

        ware = store_item("e", TVAL_WAND, 7, price=1083, charges=31)
        stocked = replace(
            snap, store=StoreState(store_type=STORE_MAGIC, items=[ware])
        )
        self.assertIsNone(policy._next_purchase_unreserved(stocked))

    def test_known_cursed_ego_is_selected_for_sale(self):
        target = item(
            "a", 23, 1, name="cursed ego sword", known=True,
            fully_known=False, is_equipment=True, is_ego=True, is_cursed=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target],
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._find_low_level_sale(snap), target)

    def test_equipped_unidentified_weapon_without_source_routes_to_buy_identify(self):
        # The incident state: a worn, unidentified weapon and no identify
        # source in the pack. The decision must not fall through to town
        # wander -- it registers the need (mirroring the known=True/full-ID
        # path) so the existing buy-identify errand routes to the Alchemist.
        weapon = item(
            "main_hand",
            23,
            1,
            name="unidentified sword",
            known=False,
            pseudo_feeling="good",
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=OIL_TARGET)
            ],
            equipment=[weapon, self._lantern()],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertIsNone(policy._town_equipped_identification_key(snap))
        self.assertEqual(policy._identification_need, "normal")
        self.assertEqual(
            policy._identification_candidate, policy._item_signature(weapon)
        )
        self.assertEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_unbuyable_full_identify_is_deferred_after_alchemist_attempt(self):
        lantern = item(
            "light",
            39,
            1,
            name="ego lantern",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        home_weapon = store_item(
            "a",
            23,
            4,
            name="unidentified dagger",
            known=False,
            fully_known=False,
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=12570),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[lantern],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried(
            snap.inventory, snap.equipment
        )
        policy._equipment_catalog.observe_home_page([home_weapon])
        policy._home_candidate_waiting = True
        policy._identification_need = "normal"
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn

        self.assertIsNone(policy._town_equipped_identification_key(snap))

        signature = policy._item_signature(lantern)
        self.assertIn(signature, policy._deferred_home_items)
        self.assertEqual(policy._identification_need, "normal")
        self.assertIsNone(policy._identification_candidate)
        self.assertIsNone(policy._town_equipped_identification_key(snap))
        self.assertNotEqual(
            policy._next_required_store_type(snap), STORE_ALCHEMIST
        )

        self.assertFalse(policy._identification_need_unsatisfiable(snap))

        policy._identification_need = "full"
        self.assertTrue(policy._identification_need_unsatisfiable(snap))

        normal_unavailable = HengbotPolicy()
        normal_unavailable._identification_need = "normal"
        normal_unavailable._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        self.assertTrue(
            normal_unavailable._identification_need_unsatisfiable(snap)
        )

    def test_equipped_identify_does_not_append_target_after_fallible_staff_use(self):
        # Regression for the 2026-07-23 magic-shop loop.  When a Staff of
        # Identify failed to activate, the appended `/g` equipment selector was
        # interpreted on the town map and re-entered the shop underfoot.  The
        # bot then alternated identify:normal-equipped with shop:leave forever.
        light = item(
            "light",
            39,
            1,
            name="unidentified lantern",
            known=False,
            is_equipment=True,
        )
        staff = item(
            "f",
            TVAL_STAFF,
            SV_STAFF_IDENTIFY,
            name="identify staff",
            known=True,
            aware=True,
            charges=20,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                staff,
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=OIL_TARGET),
            ],
            equipment=[light],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertIsNone(policy._town_equipped_identification_key(snap))
        self.assertEqual(policy._identification_need, "normal")
        self.assertTrue(policy._identification_requires_reliable_source(snap))
        self.assertEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)

    def test_carried_ego_weapon_without_source_routes_to_buy_star_identify(self):
        lance = item(
            "l",
            22,
            20,
            name="extra attacks lance",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                lance,
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=OIL_TARGET),
            ],
            equipment=[self._lantern()],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertIsNone(policy._town_item_processing_key(snap))
        self.assertEqual(policy._identification_need, "full")
        self.assertEqual(
            policy._identification_candidate, policy._item_signature(lance)
        )
        self.assertEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)

class TownErrandPlanTest(unittest.TestCase):
    def test_calibration_home_budget_admits_measured_full_calibration(self):
        measured_full_calibration_visits = 98
        self.assertEqual(CALIBRATION_HOME_VISIT_LIMIT, 300)
        self.assertGreaterEqual(
            CALIBRATION_HOME_VISIT_LIMIT,
            measured_full_calibration_visits,
        )

    def _snapshot(self, *, turn=100, width=20, height=20):
        return Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            width=width,
            height=height,
            turn=turn,
        )

    def _policy(self, needs, town_map=None):
        policy = HengbotPolicy(town_map=town_map)
        policy._town_need_candidates = lambda snapshot: list(needs)
        policy._town_terminal_transitions = lambda snapshot: None
        return policy

    def _deferred_identify_staff_incident(self, *, deferred=True):
        carried = item(
            "d", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=7,
            name="Staff of Identify",
        )
        home_staff = item(
            "h", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=5,
            name="Staff of Identify",
        )
        stock = store_item(
            "a", TVAL_STAFF, SV_STAFF_IDENTIFY, price=888, charges=20,
            count=3, name="Staff of Identify",
        )
        position = Position(10, 10)
        snapshot = Snapshot(
            player(10, 10, gold=9869, class_id=PLAYER_CLASS_WARRIOR),
            {position: replace(grid(10, 10), store_number=STORE_MAGIC)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[carried],
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._deepest_level = STAFF_IDENTIFY_MIN_DEPTH
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [home_staff]
        if deferred:
            policy._defer_home_item(
                policy._item_signature(home_staff), "fixture-deferred-home-staff"
            )
        policy._shop_observation = (StoreState(STORE_MAGIC, [stock], page_top=0), 2042)
        return policy, snapshot, home_staff

    def _consume_failed_procurement_withdrawal(
        self, policy, outside, home_item, item_class
    ):
        policy._deepest_level = STAFF_IDENTIFY_MIN_DEPTH
        policy.consume_home_knowledge((home_item,))
        signature = policy._item_signature(home_item)
        offered = store_item(
            "a", home_item.tval, home_item.sval, name=home_item.name,
            count=home_item.count, charges=home_item.charges,
            is_equipment=home_item.is_equipment,
        )
        self.assertIs(
            policy._purchase_has_fresh_home_absence(outside, offered),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )
        home_position = outside.player.position
        home_entrance = replace(
            outside,
            inventory=[],
            grids={
                home_position: replace(
                    grid(home_position.y, home_position.x), store_number=STORE_HOME
                ),
                Position(home_position.y, home_position.x - 1): grid(
                    home_position.y, home_position.x - 1
                ),
            },
        )
        policy._home_page_size = 12
        policy._shop_observation = None
        policy._store_visit = None
        policy._town_errand_plan = None
        policy._shopping_approach_store_type = STORE_HOME
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: the public withdrawal observer is the subject; only unrelated downstream policy selection is replaced
        with patch.object(
            policy,
            "_decide",
            side_effect=lambda snapshot: policy._shopping_approach_key(
                snapshot, snapshot.player.position, "shop:travel"
            ),
        ):
            entry_key = policy.choose_key(home_entrance)
        self.assertEqual(entry_key, WAIT_KEY)
        self.assertIsNotNone(
            policy._store_visit.operation_key,
            (policy.last_reason, policy._store_visit, policy._home_pending_item),
        )
        policy.confirm_key_posted(entry_key)
        page_item = store_item(
            "a", home_item.tval, home_item.sval, name=home_item.name,
            count=home_item.count, charges=home_item.charges,
            is_equipment=home_item.is_equipment,
        )
        operation_key = policy.choose_key(
            replace(
                home_entrance,
                store=StoreState(
                    STORE_HOME, [page_item], stock_num=1,
                    page_top=0, page_size=12,
                ),
            )
        )
        requested = policy._home_atomic_withdraw_pending[3]
        expected_operation = (
            f"pa{requested}\r\x1b" if page_item.count > 1 else "pa\x1b"
        )
        self.assertEqual(
            operation_key, expected_operation,
            (policy.last_reason, policy._store_visit, policy._home_pending_item),
        )
        policy.confirm_key_posted(operation_key)
        policy.choose_key(replace(home_entrance, turn=home_entrance.turn + 1))
        return policy, replace(outside, turn=home_entrance.turn + 2)

    def test_deferred_home_staff_retries_before_incident_magic_buy(self):
        policy, entrance, home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        observed = policy._shop_observation
        policy, entrance = self._consume_failed_procurement_withdrawal(
            policy, entrance, home_staff, policy._procurement_class(home_staff)
        )
        policy.consume_home_knowledge((home_staff,))
        policy._shop_observation = (observed[0], policy._decision_sequence)

        key = policy._atomic_shop_transaction_key(entrance)

        signature = policy._item_signature(home_staff)
        self.assertIsNone(key)
        self.assertEqual(
            policy._home_gate_telemetry["branch"],
            "wrapper-candidate-home-first",
        )
        self.assertEqual(
            policy._town_visit_ledger.pending_store_transaction[0], STORE_HOME
        )
        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertIn(signature, policy._retried_deferred_home_items)

    def test_pin_vacuity_incident_latch_rearms_routable_home_first(self):
        policy, entrance, _home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        entrance = replace(
            entrance,
            grids={
                **entrance.grids,
                Position(10, 13): replace(
                    grid(10, 13), store_number=STORE_HOME
                ),
            },
        )
        policy._set_town_store_attempted(STORE_HOME, entrance.turn, "test-home-stop")

        key = policy.choose_key(entrance)

        self.assertEqual(key, WAIT_KEY)
        self.assertFalse(key.startswith(BUY_KEY))
        self.assertIsNone(policy._town_visit_ledger.pending_store_transaction)
        gate = policy._home_gate_telemetry
        self.assertEqual(gate["result"], "home-first")
        self.assertEqual(gate["branch"], "wrapper-candidate-home-first")
        self.assertTrue(gate["inputs"]["attempted"])
        self.assertEqual(gate["home_latch"]["active"]["site"], "test-home-stop")
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

        route_key = policy.choose_key(replace(entrance, turn=entrance.turn + 1))
        if policy._shopping_approach_store_type is None:
            route_key = policy.choose_key(replace(entrance, turn=entrance.turn + 2))
        self.assertNotEqual(route_key, WAIT_KEY)
        self.assertEqual(
            policy._home_pending_item, policy._item_signature(_home_staff)
        )
        self.assertNotIn(
            policy._item_signature(_home_staff), policy._deferred_home_items
        )

    def test_home_gate_candidate_without_latch_records_home_first(self):
        policy, entrance, _home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )

        key = policy.choose_key(entrance)
        self.assertFalse(key.startswith(BUY_KEY))

        gate = policy._home_gate_telemetry
        self.assertEqual(gate["result"], "home-first")
        self.assertEqual(gate["branch"], "wrapper-candidate-home-first")
        self.assertFalse(gate["inputs"]["attempted"])

    def test_pre_telemetry_checkpoint_shop_gate_records_compatible_values(self):
        policy, entrance, _home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        for name in (
            "_home_latch_active",
            "_home_latch_history",
            "_home_gate_telemetry",
            "_equipment_fresh_search_target_ids",
        ):
            delattr(policy, name)
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))

        shop_snapshot = replace(entrance, store=restored._shop_observation[0])
        key = restored._shop(shop_snapshot)

        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(
            restored._home_gate_telemetry["branch"],
            "wrapper-candidate-home-first",
        )
        self.assertFalse(restored._home_gate_telemetry["inputs"]["attempted"])
        self.assertIsNone(restored._home_gate_telemetry["home_latch"]["active"])

    def test_home_attempt_setdefault_keeps_original_time_and_provenance(self):
        policy, entrance, _home_staff = self._deferred_identify_staff_incident()
        policy._set_town_store_attempted(STORE_HOME, 41, "first-site")

        policy._set_town_store_attempted(
            STORE_HOME, 99, "later-site", if_absent=True
        )

        self.assertEqual(policy._town_store_attempted[STORE_HOME], 41)
        self.assertEqual(policy._home_latch_active, {"turn": 41, "site": "first-site"})
        self.assertEqual(
            policy._home_latch_history, [{"turn": 41, "site": "first-site"}]
        )

    def test_cycle_break_home_setdefault_records_its_site(self):
        policy, entrance, _home_staff = self._deferred_identify_staff_incident()
        policy._last_return_trigger = None
        policy._departure_blocking_town_needs = lambda _snapshot: []

        policy._break_town_cycle(entrance)

        self.assertEqual(policy._town_store_attempted[STORE_HOME], entrance.turn)
        self.assertEqual(
            policy._home_latch_active,
            {
                "turn": entrance.turn,
                "site": "repetition-preserve-exhausted-store",
            },
        )

    def test_home_gate_decision_record_keeps_consumed_wrapper_evaluation(self):
        policy, incident, _home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        parsed = parse_snapshot(
            {
                "turn": incident.turn,
                "player": {"y": 10, "x": 10, "hp": 10, "max_hp": 10},
                "floor": {"dungeon_id": 0, "level": 0, "in_town": True},
            },
            {},
        )
        entrance = replace(
            parsed,
            player=incident.player,
            grids=incident.grids,
            floor_key=incident.floor_key,
            inventory=incident.inventory,
            town_flag=True,
        )

        key = policy.choose_key(entrance)
        policy._wanted_purchase_is_home_first_refused(entrance, STORE_MAGIC)
        gate = policy._home_gate_telemetry
        record = _decision_record(
            entrance, key, policy.last_reason, home_gate=gate
        )

        self.assertEqual(record["home_gate"]["result"], "home-first")
        self.assertEqual(
            record["home_gate"]["branch"], "wrapper-candidate-home-first"
        )
        self.assertFalse(record["home_gate"]["inputs"]["attempted"])
        self.assertIsNone(record["home_gate"]["home_latch"]["active"])

    def test_home_latch_active_tracks_attempted_predicate_both_directions(self):
        policy, entrance, _home_staff = self._deferred_identify_staff_incident()
        policy._set_town_store_attempted(STORE_HOME, entrance.turn, "pin-latched")
        policy._home_knowledge_items = []
        policy._purchase_has_fresh_home_absence(
            entrance, policy._shop_observation[0].items[0]
        )
        self.assertTrue(policy._home_gate_telemetry["inputs"]["attempted"])
        self.assertEqual(
            policy._home_gate_telemetry["home_latch"]["active"]["site"],
            "pin-latched",
        )

        policy._town_store_attempted.clear()
        policy._purchase_has_fresh_home_absence(
            entrance, policy._shop_observation[0].items[0]
        )
        self.assertFalse(policy._home_gate_telemetry["inputs"]["attempted"])
        self.assertIsNone(policy._home_gate_telemetry["home_latch"]["active"])

    def test_home_gate_fresh_absence_records_class_census(self):
        policy, entrance, _home_staff = self._deferred_identify_staff_incident()
        policy._home_knowledge_items = []

        key = policy.choose_key(entrance)

        self.assertEqual(key, WAIT_KEY)
        gate = policy._home_gate_telemetry
        self.assertEqual(gate["branch"], "wrapper-fresh-catalogue-absence")
        self.assertEqual(gate["wrapper_fallthrough"], "fresh-catalogue-absence")
        self.assertEqual(gate["candidate_absence_census"]["class_matches"], 0)

    def test_terminal_failure_ignores_exhausted_torch_and_retries_fueled_torch(self):
        policy = HengbotPolicy()
        entrance = self._snapshot()
        offered = store_item(
            "a", TVAL_LITE, SV_LITE_TORCH, price=3, name="Torch"
        )
        item_class = policy._procurement_class(offered)
        fueled = item(
            "h", TVAL_LITE, SV_LITE_TORCH, count=1, fuel=5000,
            name="Torch",
        )
        policy, entrance = self._consume_failed_procurement_withdrawal(
            policy, entrance, fueled, item_class
        )
        exhausted = replace(fueled, fuel=0)
        policy.consume_home_knowledge((exhausted,))

        gate = policy._purchase_has_fresh_home_absence(entrance, offered)

        self.assertIs(gate, policy_module.ProcurementHomeGate.ALLOW_PURCHASE)
        self.assertEqual(
            policy._home_gate_telemetry["branch"],
            "wrapper-fresh-catalogue-absence",
        )
        self.assertEqual(
            policy._home_gate_telemetry["candidate_absence_census"]["torch_no_fuel"],
            1,
        )

        policy.consume_home_knowledge((fueled,))

        gate = policy._purchase_has_fresh_home_absence(entrance, offered)

        signature = policy._item_signature(fueled)
        self.assertIs(gate, policy_module.ProcurementHomeGate.HOME_FIRST)
        self.assertEqual(
            policy._home_gate_telemetry["branch"],
            "wrapper-candidate-home-first",
        )
        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertIn(signature, policy._retried_deferred_home_items)

    def test_pin_vacuity_terminal_withdraw_failure_present_retries_home_once(self):
        policy, entrance, home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        item_class = policy._procurement_class(home_staff)
        policy, entrance = self._consume_failed_procurement_withdrawal(
            policy, entrance, home_staff, item_class
        )
        policy.consume_home_knowledge((home_staff,))
        policy._equipment_catalog._home = {}
        policy._floor_key = entrance.floor_key
        policy._calibration_phase = None
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: the purchase gate is isolated from unrelated automatic character calibration
        policy._character_calibration_key = Mock(return_value=None)
        policy._shop_observation = (
            StoreState(
                STORE_MAGIC,
                [store_item(
                    "a", TVAL_STAFF, SV_STAFF_IDENTIFY, price=888,
                    charges=20, count=3, name="Staff of Identify",
                )],
                page_top=0,
            ),
            policy._decision_sequence,
        )
        policy._shopping_approach_store_type = STORE_MAGIC
        policy._shopping_approach_goal = entrance.player.position
        policy._store_visit = StoreVisit("town-errand", "shopping", STORE_MAGIC)
        key = policy.choose_key(entrance)

        signature = policy._item_signature(home_staff)
        self.assertFalse(key.startswith(BUY_KEY), key)
        self.assertIsNone(policy._store_buy_inflight)
        gate = policy._home_gate_telemetry
        self.assertEqual(gate["result"], "home-first")
        self.assertEqual(gate["branch"], "wrapper-candidate-home-first")
        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertIn(signature, policy._retried_deferred_home_items)
        self.assertIsNone(gate["withdraw_failure"])

    def test_procurement_claim_is_not_deferred_before_atomic_withdraw_posts(self):
        policy, entrance, home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        offered = policy._shop_observation[0].items[0]

        gate = policy._purchase_has_fresh_home_absence(entrance, offered)
        processing_key = policy._town_item_processing_key(entrance)

        self.assertIs(gate, policy_module.ProcurementHomeGate.HOME_FIRST)
        self.assertIsNone(processing_key)
        self.assertTrue(policy._home_withdrawal_queued)
        self.assertEqual(
            policy._home_pending_item, policy._item_signature(home_staff)
        )
        self.assertNotIn(
            policy._item_signature(home_staff), policy._deferred_home_items
        )

    def test_procurement_oil_withdraw_uses_missing_amount_capped_by_stock(self):
        for stock, expected in ((8, 5), (3, 3)):
            with self.subTest(stock=stock):
                policy = HengbotPolicy()
                policy._deepest_level = 1
                oil = store_item(
                    "a", TVAL_FLASK, SV_FLASK_OIL, count=stock, name="Flask of oil"
                )
                outside = replace(
                    self._snapshot(),
                    inventory=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=7500)],
                    grids={
                        Position(10, 10): replace(
                            grid(10, 10), store_number=STORE_HOME
                        )
                    },
                )
                policy.consume_home_knowledge((oil,))
                signature = policy._item_signature(oil)
                self.assertIs(
                    policy._purchase_has_fresh_home_absence(outside, oil),
                    policy_module.ProcurementHomeGate.HOME_FIRST,
                )
                policy._home_page_size = 12
                policy._store_visit = StoreVisit(
                    "home-visit", "procurement-withdrawal", STORE_HOME
                )

                self.assertEqual(
                    policy._atomic_home_withdraw_key(
                        outside, outside.player.position
                    ),
                    WAIT_KEY,
                )
                self.assertEqual(
                    policy._store_visit.operation_key, f"pa{expected}\r\x1b"
                )

    def test_batch_queue_does_not_overwrite_gate_quantity_before_composition(self):
        policy = HengbotPolicy()
        policy._deepest_level = 1
        oil = store_item("a", TVAL_FLASK, SV_FLASK_OIL, count=5, name="Oil")
        one_missing = replace(
            self._snapshot(),
            inventory=[
                item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=7500),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=4, name="Oil"),
            ],
            grids={Position(10, 10): replace(grid(10, 10), store_number=STORE_HOME)},
        )
        policy.consume_home_knowledge((oil,))
        self.assertIs(
            policy._purchase_has_fresh_home_absence(one_missing, oil),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )
        signature = policy._item_signature(oil)
        self.assertEqual(policy._home_pending_quantities[signature], 1)
        five_missing = replace(one_missing, inventory=one_missing.inventory[:1])
        policy._queue_home_procurement_batch(five_missing, oil)
        policy._home_page_size = 12
        policy._store_visit = StoreVisit("home-visit", "procurement-withdrawal", STORE_HOME)

        self.assertEqual(
            policy._atomic_home_withdraw_key(five_missing, five_missing.player.position),
            WAIT_KEY,
        )
        self.assertEqual(policy._store_visit.operation_key, "pa1\r\x1b")

    def test_atomic_composer_floors_legacy_zero_quantity_to_one(self):
        policy = HengbotPolicy()
        policy._deepest_level = 1
        oil = store_item("a", TVAL_FLASK, SV_FLASK_OIL, count=5, name="Oil")
        snapshot = replace(
            self._snapshot(),
            inventory=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=7500)],
            grids={Position(10, 10): replace(grid(10, 10), store_number=STORE_HOME)},
        )
        policy.consume_home_knowledge((oil,))
        self.assertIs(
            policy._purchase_has_fresh_home_absence(snapshot, oil),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )
        # Narrow compatibility seam: live producers reject zero, but restored
        # checkpoints from the prior schema may still contain it.
        policy._home_pending_quantities[policy._item_signature(oil)] = 0
        policy._home_page_size = 12
        policy._store_visit = StoreVisit("home-visit", "procurement-withdrawal", STORE_HOME)
        self.assertEqual(
            policy._atomic_home_withdraw_key(snapshot, snapshot.player.position),
            WAIT_KEY,
        )
        self.assertEqual(policy._store_visit.operation_key, "pa1\r\x1b")

    def test_oil_gate_queue_blocks_claim_processing_until_withdraw_posts(self):
        policy = HengbotPolicy()
        policy._deepest_level = 1
        oil = store_item("a", TVAL_FLASK, SV_FLASK_OIL, count=5, name="Oil")
        snapshot = replace(
            self._snapshot(),
            inventory=[
                item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=7500),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=1, name="Oil"),
            ],
        )
        policy.consume_home_knowledge((oil,))
        self.assertIs(
            policy._purchase_has_fresh_home_absence(snapshot, oil),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )
        pending = policy._home_pending_item

        self.assertIsNone(policy._town_item_processing_key(snapshot))
        self.assertTrue(policy._home_withdrawal_queued)
        self.assertEqual(policy._home_pending_item, pending)

    def test_procurement_batch_state_resets_on_real_town_exit_and_fresh_visit(self):
        for target in (
            replace(self._snapshot(), floor_key=(1, 1, 0), town_flag=False),
            replace(self._snapshot(), floor_key=(0, 0, 0), town_flag=True),
        ):
            with self.subTest(in_town=target.in_town):
                policy = HengbotPolicy()
                policy._floor_key = (2, 2, 0)
                policy._home_pending_quantities[("Oil", TVAL_FLASK, SV_FLASK_OIL)] = 5
                policy._home_procurement_batch_active = True
                # TEST_FAKERY_LINT_ALLOW: public-path-replaced: observe reset is the subject; unrelated decision selection is isolated
                with patch.object(policy, "_decide", return_value=None):
                    policy.choose_key(target)
                self.assertEqual(policy._home_pending_quantities, {})
                self.assertFalse(policy._home_procurement_batch_active)

    def test_oil_with_permanent_light_is_not_routed_or_queued_through_home(self):
        policy = HengbotPolicy()
        oil = store_item("a", TVAL_FLASK, SV_FLASK_OIL, count=8, name="Oil")
        outside = replace(
            self._snapshot(),
            inventory=[
                item("l", TVAL_LITE, SV_LITE_FEANOR, name="Phial", known=True)
            ],
        )
        policy.consume_home_knowledge((oil,))

        gate = policy._purchase_has_fresh_home_absence(outside, oil)

        self.assertIs(gate, policy_module.ProcurementHomeGate.ALLOW_PURCHASE)
        self.assertEqual(policy._home_gate_telemetry["branch"], "wrapper-no-procurement-need")
        self.assertEqual(
            policy._home_gate_telemetry["wrapper_fallthrough"],
            "no-procurement-need",
        )
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual(policy._home_pending_batch, [])
        self.assertFalse(policy._home_procurement_batch_active)
        self.assertNotEqual(policy._next_required_store_type(outside), STORE_HOME)

    def test_detection_and_digger_routing_follows_fundraising_requirement_mode(self):
        wares = (
            store_item("a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=9),
            store_item("b", TVAL_DIGGING, SV_DIGGING_SHOVEL, count=5),
        )
        for mode, expected in ((None, False), ("descend", False), ("mine", True), ("prepare", True)):
            with self.subTest(mode=mode):
                policy = HengbotPolicy()
                policy._fundraising_mode = mode
                entrance = self._snapshot()
                policy.consume_home_knowledge(wares)
                for ware in wares:
                    missing = policy._procurement_missing_amount(entrance, ware)
                    self.assertEqual(missing > 1, expected)
                    gate = policy._purchase_has_fresh_home_absence(entrance, ware)
                    self.assertIs(
                        gate,
                        policy_module.ProcurementHomeGate.HOME_FIRST
                        if expected else policy_module.ProcurementHomeGate.ALLOW_PURCHASE,
                    )

    def test_procurement_batch_keeps_home_between_two_real_withdrawal_operations(self):
        policy = HengbotPolicy()
        policy._deepest_level = policy_module.TELEPORT_REQUIRED_DEPTH
        snapshot = replace(
            self._snapshot(),
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=7500)],
            grids={
                Position(10, 10): replace(grid(10, 10), store_number=STORE_HOME)
            },
        )
        self.assertTrue(snapshot.in_town)
        policy._floor_key = snapshot.floor_key
        oil = store_item("a", TVAL_FLASK, SV_FLASK_OIL, count=5, name="Oil")
        teleport = store_item(
            "b", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15, name="Teleport"
        )
        policy.consume_home_knowledge((oil, teleport))
        self.assertIs(
            policy._purchase_has_fresh_home_absence(snapshot, oil),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )
        self.assertIn(policy._item_signature(teleport), policy._home_pending_batch)
        policy._home_page_size = 12
        policy._shopping_approach_store_type = STORE_HOME
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: the real Home entry owner is driven while unrelated downstream selection is isolated
        with patch.object(
            policy,
            "_decide",
            side_effect=lambda current: policy._shopping_approach_key(
                current, current.player.position, "shop:travel"
            ),
        ):
            first = policy.choose_key(snapshot)
        self.assertEqual(first, WAIT_KEY)
        policy.confirm_key_posted(first)
        first_operation = policy.choose_key(
            replace(
                snapshot,
                store=StoreState(
                    STORE_HOME, [oil, teleport], stock_num=2,
                    page_top=0, page_size=12,
                ),
            )
        )
        self.assertEqual(first_operation, "pa5\r\x1b")
        policy.confirm_key_posted(first_operation)
        gained = replace(
            snapshot,
            turn=snapshot.turn + 1,
            inventory=[*snapshot.inventory, item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, name="Oil")],
        )
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: public observation and item processing are under test; later unrelated policy selection is isolated
        with patch.object(policy, "_decide", side_effect=policy._town_item_processing_key):
            policy.choose_key(gained)

        # After the real producer and first withdrawal observation, remove the
        # completed approach shell so only batch retention owns store selection.
        policy._shopping_approach_store_type = None
        policy._shopping_approach_goal = None
        policy._store_visit = None
        policy._town_errand_plan = TownErrandPlan([STORE_MAGIC])
        policy.consume_home_knowledge(())
        self.assertTrue(policy._home_procurement_batch_active)
        self.assertTrue(policy._home_pending_batch)
        owner = policy._next_required_store_type(gained)
        self.assertEqual(owner, STORE_HOME)
        self.assertEqual(policy._home_pending_batch, [policy._item_signature(teleport)])
        policy.consume_home_knowledge((teleport,))
        policy._store_visit = StoreVisit("home-visit-2", "procurement-withdrawal", STORE_HOME)
        second = policy._atomic_home_withdraw_key(gained, gained.player.position)
        self.assertEqual(second, WAIT_KEY)
        self.assertRegex(policy._store_visit.operation_key, r"^pa[1-9][0-9]*\r\x1b$")

    def test_procurement_quantity_uses_supply_ledger_depth_and_mana_food_rules(self):
        teleport_policy = HengbotPolicy()
        teleport_policy._deepest_level = 20
        shallow = replace(self._snapshot(), floor_key=(0, 1, 0))
        teleport = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=20, name="Teleport"
        )
        self.assertEqual(
            teleport_policy._procurement_missing_amount(shallow, teleport), 15
        )

        mana_policy = HengbotPolicy()
        mana_snapshot = replace(
            self._snapshot(), player=player(10, 10, food_type=FOOD_TYPE_MANA)
        )
        mana_device = replace(
            store_item("a", TVAL_STAFF, 99, count=2, name="Mana food device"),
            pval=20,
        )
        self.assertEqual(
            mana_policy._procurement_missing_amount(mana_snapshot, mana_device), 15
        )

    def test_depth_21_ccw_home_stock_refuses_alchemist_purchase_end_to_end(self):
        policy = HengbotPolicy()
        policy._deepest_level = 21
        ccw = store_item(
            "a", TVAL_POTION, SV_POTION_CURE_CRITICAL,
            count=20, price=100, name="Cure Critical Wounds",
        )
        snapshot = replace(
            self._snapshot(),
            inventory=[item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=1)],
            store=StoreState(STORE_ALCHEMIST, [ccw], page_top=0),
        )
        policy.consume_home_knowledge((replace(ccw, letter="h"),))

        key = policy._shop(snapshot)

        self.assertFalse(key.startswith(BUY_KEY), key)
        self.assertEqual(policy.last_reason, "shop:home-first-before-purchase")
        self.assertEqual(policy._home_gate_telemetry["result"], "home-first")

    def test_zero_need_deferred_oil_bypasses_both_home_gates_truthfully(self):
        policy = HengbotPolicy()
        policy._deepest_level = 1
        oil = item("h", TVAL_FLASK, SV_FLASK_OIL, count=8, name="Oil")
        lantern_snapshot = replace(
            self._snapshot(),
            inventory=[item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=7500)],
        )
        policy, outside = self._consume_failed_procurement_withdrawal(
            policy, lantern_snapshot, oil, policy._procurement_class(oil)
        )
        policy.consume_home_knowledge((oil,))
        permanent = replace(
            outside,
            inventory=[item("l", TVAL_LITE, SV_LITE_FEANOR, known=True)],
        )
        offered = store_item("a", TVAL_FLASK, SV_FLASK_OIL, count=8, name="Oil")

        wrapper = policy._purchase_has_fresh_home_absence(permanent, offered)
        wrapper_telemetry = dict(policy._home_gate_telemetry)
        evaluate = policy._evaluate_purchase_home_gate(permanent, offered)

        self.assertIs(wrapper, policy_module.ProcurementHomeGate.ALLOW_PURCHASE)
        self.assertIs(evaluate, policy_module.ProcurementHomeGate.ALLOW_PURCHASE)
        self.assertEqual(wrapper_telemetry["branch"], "wrapper-no-procurement-need")
        self.assertEqual(
            wrapper_telemetry["wrapper_fallthrough"], "no-procurement-need"
        )

    def test_detection_and_digger_quantities_are_composed_from_real_gate(self):
        for ware, expected in (
            (
                store_item(
                    "a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
                    count=9, name="Detect Treasure",
                ),
                5,
            ),
            (store_item("a", TVAL_DIGGING, SV_DIGGING_SHOVEL, count=5, name="Shovel"), 2),
        ):
            with self.subTest(ware=ware.name):
                policy = HengbotPolicy()
                policy._fundraising_mode = "prepare"
                snapshot = replace(
                    self._snapshot(),
                    grids={
                        Position(10, 10): replace(
                            grid(10, 10), store_number=STORE_HOME
                        )
                    },
                )
                policy.consume_home_knowledge((ware,))
                self.assertIs(
                    policy._purchase_has_fresh_home_absence(snapshot, ware),
                    policy_module.ProcurementHomeGate.HOME_FIRST,
                )
                policy._home_page_size = 12
                policy._store_visit = StoreVisit(
                    "home-visit", "procurement-withdrawal", STORE_HOME
                )
                self.assertEqual(
                    policy._atomic_home_withdraw_key(
                        snapshot, snapshot.player.position
                    ),
                    WAIT_KEY,
                )
                self.assertEqual(
                    policy._store_visit.operation_key, f"pa{expected}\r\x1b"
                )

    def test_procurement_batch_active_clears_when_batch_drains(self):
        policy = HengbotPolicy()
        policy._home_procurement_batch_active = True

        policy._activate_home_batch_item()

        self.assertFalse(policy._home_procurement_batch_active)

    def test_pin_vacuity_observed_terminal_withdraw_failure_records_procurement(self):
        policy, entrance, home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        signature = policy._item_signature(home_staff)
        item_class = policy._procurement_class(home_staff)
        policy, _ = self._consume_failed_procurement_withdrawal(
            policy, entrance, home_staff, item_class
        )

        failure = policy._home_procurement_withdraw_failure
        self.assertIsNotNone(failure)
        self.assertEqual(failure["identity"], signature)
        self.assertEqual(failure["item_class"], "device:is-wand-staff")
        self.assertEqual(failure["reason"], "home:atomic-withdraw-failed")
        self.assertEqual(failure["attempts"], 1)
        self.assertFalse(policy._home_knowledge_current)
        self.assertTrue(policy._home_knowledge_invalidated)

    def test_terminal_failure_viable_deferred_stock_is_refused_by_evaluate_consumer(self):
        policy, entrance, home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        item_class = policy._procurement_class(home_staff)
        policy, entrance = self._consume_failed_procurement_withdrawal(
            policy, entrance, home_staff, item_class
        )
        policy.consume_home_knowledge((home_staff,))
        policy._shop_observation = (
            StoreState(
                STORE_MAGIC,
                [store_item(
                    "a", TVAL_STAFF, SV_STAFF_IDENTIFY, price=888,
                    charges=20, count=3, name="Staff of Identify",
                )],
                page_top=0,
            ),
            policy._decision_sequence,
        )

        refused = policy._wanted_purchase_is_home_first_refused(
            entrance, STORE_MAGIC
        )

        self.assertTrue(refused)
        self.assertEqual(
            policy._home_gate_telemetry["branch"],
            "evaluate-withdraw-failed-stock-present",
        )

    def test_all_viable_deferred_without_failure_is_refused_by_evaluate_consumer(self):
        policy = HengbotPolicy()
        home_digger = store_item(
            "a", TVAL_DIGGING, SV_DIGGING_SHOVEL, count=2, name="Shovel"
        )
        outside = replace(
            self._snapshot(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_HOME
                )
            },
        )
        policy._fundraising_mode = "prepare"
        policy.consume_home_knowledge((home_digger,))
        self.assertIs(
            policy._purchase_has_fresh_home_absence(outside, home_digger),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )
        policy._home_page_size = 12
        policy._store_visit = StoreVisit(
            "home-visit", "procurement-withdrawal", STORE_HOME
        )
        self.assertEqual(
            policy._atomic_home_withdraw_key(outside, outside.player.position),
            WAIT_KEY,
        )
        policy.confirm_key_posted(policy._store_visit.operation_key)
        self.assertIsNone(policy._town_item_processing_key(outside))
        self.assertIsNone(policy._home_procurement_withdraw_failure)
        self.assertEqual(
            policy._deferred_home_item_sites[policy._item_signature(home_digger)],
            "town-item-processing-missing-pending",
        )
        offered = store_item(
            "a", TVAL_DIGGING, SV_DIGGING_SHOVEL, price=20, name="Shovel"
        )
        policy._shop_observation = (
            StoreState(STORE_GENERAL, [offered], page_top=0),
            policy._decision_sequence,
        )

        refused = policy._wanted_purchase_is_home_first_refused(
            outside, STORE_GENERAL
        )

        self.assertTrue(refused)

    def test_successful_same_class_withdrawal_clears_procurement_failure(self):
        policy, entrance, home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        item_class = policy._procurement_class(home_staff)
        policy, entrance = self._consume_failed_procurement_withdrawal(
            policy, entrance, home_staff, item_class
        )
        signature = policy._item_signature(home_staff)
        policy._home_atomic_withdraw_pending = (signature, 0, home_staff, 1)
        policy._home_atomic_withdraw_posted_turn = entrance.turn - 1
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: the withdrawal success observer is the subject; downstream town selection is not asserted
        policy._decide = Mock(return_value=WAIT_KEY)

        policy.choose_key(replace(entrance, inventory=[home_staff]))

        self.assertIsNone(policy._home_procurement_withdraw_failure)
        other_staff = item(
            "w", TVAL_WAND, 99, charges=1, name="other Home wand"
        )
        policy.consume_home_knowledge((home_staff, other_staff))
        offered = store_item(
            "a", TVAL_STAFF, SV_STAFF_IDENTIFY, price=888,
            charges=20, count=3, name="Staff of Identify",
        )
        self.assertIs(
            policy._evaluate_purchase_home_gate(entrance, offered),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )
        self.assertNotEqual(
            policy._home_gate_telemetry["branch"],
            "evaluate-withdraw-failed-stock-present",
        )

    def test_equipment_withdraw_failure_does_not_claim_procurement_probe(self):
        target = item(
            "h", TVAL_RING, 99, name="Home target", known=True,
            fully_known=True, is_equipment=True,
        )
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "withdraw",
            "home-target",
            item_identity=policy_module.equipment_identity(target),
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((target,))
        policy._home_page_size = 12
        policy._shopping_approach_store_type = STORE_HOME
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 0)
            )
        )
        policy._home_procurement_probe = policy._procurement_class(target)
        position = Position(10, 10)
        entrance = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {position: replace(grid(10, 10), store_number=STORE_HOME)},
            [], turn=100, floor_key=(0, 0, 0), town_flag=True,
        )
        self.assertEqual(
            policy._atomic_home_withdraw_key(entrance, position), WAIT_KEY
        )
        self.assertIsNone(policy._home_atomic_withdraw_procurement_class)
        policy._home_procurement_probe = policy._procurement_class(target)
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: calls are wrapped to prove the equipment-owned operation does not invoke procurement-only collaborators
        policy._home_atomic_withdraw_posted_turn = entrance.turn
        policy._store_visit = None
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: the equipment-withdraw failure observer is the subject; downstream town selection is not asserted
        policy._decide = Mock(return_value=WAIT_KEY)

        with (
            patch.object(
                policy, "_invalidate_home_observation",
                wraps=policy._invalidate_home_observation,
            ) as invalidate,
            patch.object(
                policy, "_rearm_town_store_for_new_work",
                wraps=policy._rearm_town_store_for_new_work,
            ) as rearm,
        ):
            policy.choose_key(replace(entrance, turn=entrance.turn + 1))

        self.assertIsNone(policy._home_procurement_withdraw_failure)
        invalidate.assert_not_called()
        rearm.assert_not_called()

    def test_pin_vacuity_terminal_withdraw_failure_absent_allows_buy(self):
        policy, entrance, home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        item_class = policy._procurement_class(home_staff)
        policy, entrance = self._consume_failed_procurement_withdrawal(
            policy, entrance, home_staff, item_class
        )
        policy.consume_home_knowledge(())
        policy._shopping_approach_store_type = STORE_MAGIC
        policy._shopping_approach_goal = entrance.player.position
        policy._store_visit = StoreVisit("town-errand", "shopping", STORE_MAGIC)
        observed_store = StoreState(
            STORE_MAGIC,
            [store_item(
                "a", TVAL_STAFF, SV_STAFF_IDENTIFY, price=888,
                charges=20, count=3, name="Staff of Identify",
            )],
            page_top=0,
        )
        policy._shop_observation = (observed_store, policy._decision_sequence)
        gate = policy._purchase_has_fresh_home_absence(
            replace(entrance, store=observed_store), observed_store.items[0]
        )
        buy_key = policy._shop(replace(entrance, store=observed_store))

        self.assertIs(gate, policy_module.ProcurementHomeGate.ALLOW_PURCHASE)
        self.assertEqual(
            policy._home_gate_telemetry["branch"],
            "wrapper-fresh-catalogue-absence",
        )
        self.assertTrue(buy_key.startswith(BUY_KEY), buy_key)

    def test_retrievable_home_staff_still_preempts_incident_magic_buy(self):
        policy, entrance, home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )

        self.assertIsNone(policy._atomic_shop_transaction_key(entrance))
        self.assertEqual(
            policy._shop_selector_diagnostics["composition_refusal"],
            "shop:home-first-before-purchase",
        )
        self.assertEqual(policy._home_pending_item, policy._item_signature(home_staff))

    def test_other_retrievable_home_device_still_preempts_deferred_staff(self):
        policy, entrance, _home_staff = self._deferred_identify_staff_incident()
        other = item(
            "w", TVAL_WAND, 99, charges=1, name="another Home wand"
        )
        policy._home_knowledge_items.append(other)

        self.assertIsNone(policy._atomic_shop_transaction_key(entrance))
        self.assertEqual(
            policy._shop_selector_diagnostics["composition_refusal"],
            "shop:home-first-before-purchase",
        )

    def test_incident_magic_entrance_cycle_retries_home_before_composed_buy(self):
        policy, entrance, home_staff = self._deferred_identify_staff_incident()
        observed_store = policy._shop_observation[0]
        policy._store_visit = StoreVisit("town-errand", "shopping", STORE_MAGIC)

        class MagicEntranceWorld:
            def __init__(self):
                self.inside = False
                self.applied = 0
                self.gold = entrance.player.gold
                self.inventory = list(entrance.inventory)
                self.stock = list(observed_store.items)

            def deliver_events(self, _policy):
                pass

            def snapshot(self, decision):
                return replace(
                    entrance,
                    turn=entrance.turn + decision,
                    player=replace(entrance.player, gold=self.gold),
                    inventory=list(self.inventory),
                    store=(
                        StoreState(STORE_MAGIC, list(self.stock), page_top=0)
                        if self.inside else None
                    ),
                )

            def apply(self, key):
                self.applied += 1
                if key == WAIT_KEY:
                    self.inside = True
                elif self.inside and key.startswith(BUY_KEY + "a"):
                    bought = self.stock.pop(0)
                    self.gold -= bought.price
                    self.inventory.append(item(
                        "z", bought.tval, bought.sval, count=bought.count,
                        charges=bought.charges, name=bought.name,
                    ))
                    self.inside = False

            def progress_fingerprint(self):
                return self.inside, self.gold, len(self.inventory), len(self.stock)

        world = MagicEntranceWorld()
        result = drive_trajectory(
            policy,
            world,
            decisions=3,
            owner_bound=3,
            pair_bound=3,
            milestones=(
                (
                    "entered-without-buy",
                    1,
                    lambda _policy, current, _reason, key: (
                        current.inside and key == WAIT_KEY
                    ),
                ),
                (
                    "second-decision-still-no-buy",
                    2,
                    lambda _policy, current, _reason, key: (
                        current.applied >= 2 and not key.startswith(BUY_KEY)
                    ),
                ),
            ),
        )
        key = result.transcript[-1][1]
        self.assertFalse(any(k.startswith(BUY_KEY) for _reason, k in result.transcript))
        self.assertEqual(
            policy._home_gate_telemetry["branch"],
            "wrapper-candidate-home-first",
        )
        self.assertIn(
            policy._item_signature(home_staff),
            policy._retried_deferred_home_items,
        )
        self.assertEqual(world.gold, entrance.player.gold)
        self.assertEqual(len(world.inventory), len(entrance.inventory))

    def _identification_claim_incident(self, *, shape):
        policy = HengbotPolicy()
        policy._home_candidate_waiting = True
        policy._identification_candidate = None
        policy._identification_need = "basic"
        if shape != "unscanned":
            policy._equipment_catalog.home_scan_complete = True
            policy._home_knowledge_current = True
            policy._home_knowledge_valid_before = 12
        if shape == "bindable":
            target = item(
                "h", 23, 25, name="incomplete Home equipment", known=False,
                fully_known=False, is_equipment=True,
            )
            owned = OwnedEquipment("home-target", target, "home")
            policy._equipment_catalog._home = {owned.id: owned}
            policy._home_knowledge_items = [target]
        elif shape == "incident":
            deferred_staff = item(
                "h", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=5,
                name="Staff of Identify",
            )
            policy._home_knowledge_items = [deferred_staff]
            policy._deferred_home_items.add(
                policy._item_signature(deferred_staff)
            )
        elif shape == "all-deferred":
            target = item(
                "h", 23, 25, name="deferred incomplete Home equipment",
                known=False, fully_known=False, is_equipment=True,
            )
            owned = OwnedEquipment("deferred-home-target", target, "home")
            policy._equipment_catalog._home = {owned.id: owned}
            policy._home_knowledge_items = [target]
            policy._deferred_home_items.add(policy._item_signature(target))
        snapshot = replace(
            self._snapshot(),
            town_flag=True,
            town_id=0,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_HOME
                ),
            },
            inventory=[item(
                "i", TVAL_SCROLL, policy_module.SV_SCROLL_IDENTIFY,
                name="Identify", known=True, aware=True,
            )],
        )
        return policy, snapshot

    def test_deferred_only_identification_claim_self_retires(self):
        policy, snapshot = self._identification_claim_incident(shape="incident")

        categories = {
            need.category for need in policy._town_need_candidates(snapshot)
        }

        self.assertNotIn("identification-withdrawal", categories)
        self.assertNotEqual(policy._next_required_store_type(snapshot), STORE_HOME)

    def test_bindable_identification_claim_revives(self):
        policy, snapshot = self._identification_claim_incident(shape="bindable")

        categories = {need.category for need in policy._town_need_candidates(snapshot)}

        self.assertIn("identification-withdrawal", categories)

    def test_all_deferred_identification_claim_self_retires(self):
        policy, snapshot = self._identification_claim_incident(
            shape="all-deferred"
        )

        categories = {need.category for need in policy._town_need_candidates(snapshot)}

        self.assertNotIn("identification-withdrawal", categories)
        self.assertNotEqual(policy._next_required_store_type(snapshot), STORE_HOME)

    def test_unscanned_empty_identification_catalog_keeps_claim(self):
        policy, snapshot = self._identification_claim_incident(shape="unscanned")

        categories = {need.category for need in policy._town_need_candidates(snapshot)}

        self.assertIn("identification-withdrawal", categories)

    def test_shop_refusal_diagnostics_distinguish_page_states(self):
        policy, entrance, _home_staff = self._deferred_identify_staff_incident(
            deferred=False
        )
        observed_store = policy._shop_observation[0]
        policy._star_remove_curse_shelf_seen = False
        record = policy._record_shop_selector_diagnostics

        def mutating_diagnostic(snapshot, key):
            record(snapshot, key)
            policy._star_remove_curse_shelf_seen = True

        with patch.object(
            policy,
            "_record_shop_selector_diagnostics",
            side_effect=mutating_diagnostic,
        ):
            self.assertIsNone(policy._atomic_shop_transaction_key(entrance))
        self.assertFalse(policy._star_remove_curse_shelf_seen)
        self.assertEqual(
            policy._shop_selector_diagnostics["composition_refusal"],
            "shop:home-first-before-purchase",
        )

        policy._record_shop_selector_diagnostics(entrance, WAIT_KEY)
        self.assertEqual(
            policy._shop_selector_diagnostics["rejection_reason"],
            "no-store-page-observed",
        )
        empty_page = replace(entrance, store=StoreState(STORE_MAGIC, []))
        policy._record_shop_selector_diagnostics(empty_page, WAIT_KEY)
        self.assertEqual(
            policy._shop_selector_diagnostics["rejection_reason"],
            "observed-page-nothing-wanted",
        )
        self.assertEqual(
            policy._shop_selector_diagnostics["composition_refusal"],
            "shop:home-first-before-purchase",
        )

    def test_visit_ledger_survives_plan_rebuild(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        self.assertIsNotNone(policy._next_required_store_type(snapshot))

        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False
        )
        before = (
            dict(policy._town_visit_ledger.store_visits),
            dict(policy._town_visit_ledger.need_attempts),
        )
        policy._town_errand_plan = None
        policy._next_required_store_type(snapshot)

        self.assertEqual(
            (
                dict(policy._town_visit_ledger.store_visits),
                dict(policy._town_visit_ledger.need_attempts),
            ),
            before,
        )
        self.assertEqual(policy._town_errand_plan.current_stop_passes, 0)

    def test_catalogued_identification_withdrawal_is_composed_before_home_entry(self):
        policy = HengbotPolicy()
        target = item(
            "a", 23, 25, name="unidentified home blade", known=False,
            fully_known=False, is_equipment=True,
        )
        source = item(
            "b", TVAL_SCROLL, policy_module.SV_SCROLL_IDENTIFY,
            name="Identify", known=True, aware=True,
        )
        entrance = replace(
            self._snapshot(),
            inventory=[source],
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_HOME
                )
            },
        )
        owned = OwnedEquipment("home-target", target, "home")
        policy._equipment_catalog._home = {owned.id: owned}
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_items = (target,)
        policy._home_knowledge_valid_before = 1
        policy._home_knowledge_current = True
        policy._home_page_size = 12
        policy._home_candidate_waiting = True
        policy._shopping_approach_store_type = STORE_HOME
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME],
            need_categories={STORE_HOME: ("identification-withdrawal",)},
        )

        key = policy._shopping_approach_key(
            entrance, entrance.player.position, "shop:travel"
        )

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason,
            "home-errand:atomic-withdraw:identification-catalog",
        )
        self.assertIn(BUY_KEY, policy._store_visit.operation_key)
        self.assertFalse(policy._home_candidate_waiting)
        self.assertIsNotNone(policy._home_atomic_withdraw_pending)

    def test_uncomposable_home_stop_advances_without_entry(self):
        policy = HengbotPolicy()
        target = item(
            "a", 23, 25, name="unidentified home blade", known=False,
            fully_known=False, is_equipment=True,
        )
        entrance = replace(
            self._snapshot(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_HOME
                ),
                Position(10, 11): grid(10, 11),
            },
        )
        owned = OwnedEquipment("home-target", target, "home")
        policy._equipment_catalog._home = {owned.id: owned}
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_items = (target,)
        policy._home_knowledge_valid_before = 1
        policy._home_knowledge_current = True
        policy._home_candidate_waiting = True
        policy._shopping_approach_store_type = STORE_HOME
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_ALCHEMIST],
            need_categories={STORE_HOME: ("identification-withdrawal",)},
        )

        posted = policy._shopping_approach_key(
            entrance, entrance.player.position, "shop:travel"
        )

        self.assertEqual(posted, WAIT_KEY)
        self.assertEqual(policy._town_errand_plan.index, 1)
        self.assertNotEqual(policy._store_entry_wait_owner, STORE_HOME)
        policy._shopping_approach_store_type = STORE_ALCHEMIST
        following = [
            policy._shopping_approach_key(
                entrance, Position(10, 11), "shop:travel"
            )
            for _ in range(2)
        ]
        self.assertNotIn(WAIT_KEY, following)
        self.assertNotEqual(policy._store_entry_wait_owner, STORE_HOME)

    def test_observed_uncomposable_nonhome_stop_advances_without_entry(self):
        policy = HengbotPolicy()
        entrance = replace(
            self._snapshot(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_GENERAL
                )
            },
        )
        policy._shopping_approach_store_type = STORE_GENERAL
        policy._shop_observation = (
            StoreState(store_type=STORE_GENERAL, items=[], page_top=0), 1
        )
        policy._town_errand_plan = TownErrandPlan(
            [STORE_GENERAL, STORE_ALCHEMIST],
            need_categories={STORE_GENERAL: ("food",)},
        )
        policy._shop = lambda snapshot: LEAVE_STORE_KEY

        key = policy._shopping_approach_key(
            entrance, entrance.player.position, "shop:travel"
        )

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy._town_errand_plan.index, 1)
        self.assertIn(STORE_GENERAL, policy._town_errand_plan.blocked_this_visit)
        self.assertNotIn("`", key)
        self.assertIsNone(policy._shop_observation)

    def test_observed_nothing_wanted_advances_actual_plan_stop_despite_stale_approach(self):
        policy = HengbotPolicy()
        entrance = replace(
            self._snapshot(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_WEAPON
                )
            },
        )
        policy._shopping_approach_store_type = STORE_ALCHEMIST
        policy._shop_observation = (
            StoreState(store_type=STORE_WEAPON, items=[], page_top=0), 1
        )
        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON, STORE_BLACK, STORE_GENERAL],
            need_categories={STORE_WEAPON: ("quest-ranged-kit",)},
        )
        policy._shop = lambda snapshot: LEAVE_STORE_KEY

        self.assertEqual(policy._atomic_shop_transaction_key(entrance), WAIT_KEY)
        self.assertEqual(policy._town_errand_plan.index, 1)
        self.assertIn(STORE_WEAPON, policy._town_errand_plan.blocked_this_visit)
        self.assertIsNone(policy._shop_observation)

    def test_all_nothing_wanted_plan_stops_end_without_rebuild(self):
        policy = HengbotPolicy()
        entrance = replace(
            self._snapshot(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_WEAPON
                )
            },
        )
        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON],
            need_categories={STORE_WEAPON: ("quest-ranged-kit",)},
        )
        policy._shopping_approach_store_type = STORE_ALCHEMIST
        policy._shop_observation = (
            StoreState(store_type=STORE_WEAPON, items=[], page_top=0), 1
        )
        policy._shop = lambda snapshot: LEAVE_STORE_KEY

        self.assertEqual(policy._atomic_shop_transaction_key(entrance), WAIT_KEY)
        exhausted = policy._town_errand_plan
        self.assertEqual(exhausted.index, len(exhausted.stops))
        self.assertIn(STORE_WEAPON, exhausted.blocked_this_visit)
        policy._town_need_candidates = lambda snapshot: [
            TownNeed(STORE_WEAPON, "quest-ranged-kit", "ordinary")
        ]

        self.assertIsNone(policy._next_required_store_type(entrance))
        self.assertIsNone(policy._town_errand_plan)

    def test_uncomposable_shop_observation_cannot_compose_after_pack_change(self):
        policy = HengbotPolicy()
        entrance = replace(
            self._snapshot(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_GENERAL
                )
            },
        )
        policy._shopping_approach_store_type = STORE_GENERAL
        policy._shop_observation = (
            StoreState(store_type=STORE_GENERAL, items=[], page_top=0), 1
        )
        policy._shop = lambda snapshot: LEAVE_STORE_KEY

        self.assertIsNone(policy._atomic_shop_transaction_key(entrance))
        self.assertIsNone(policy._shop_observation)

        policy._shop = lambda snapshot: BUY_KEY + "a"
        richer = replace(entrance, player=replace(entrance.player, gold=9999))
        self.assertIsNone(policy._atomic_shop_transaction_key(richer))


    def test_visit_ledger_resets_only_on_town_entry(self):
        policy = self._policy([])
        town = replace(self._snapshot(), town_flag=True)
        dungeon = replace(town, town_flag=False, floor_key=(1, 1, 0))
        policy._observe(town)
        policy._town_visit_ledger.store_visits[STORE_HOME] = 2
        policy._town_errand_plan = TownErrandPlan([STORE_HOME])
        policy._town_errand_plan = None
        policy._observe(town)
        self.assertEqual(policy._town_visit_ledger.store_visits[STORE_HOME], 2)

        policy._observe(dungeon)
        self.assertEqual(policy._town_visit_ledger.store_visits[STORE_HOME], 2)
        policy._observe(town)
        self.assertEqual(dict(policy._town_visit_ledger.store_visits), {})

    def test_shadow_drift_warning_is_once_and_requires_reemission(self):
        needs = [TownNeed(STORE_HOME, "idle-consumable-scan", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        policy._town_visit_ledger.satisfied_needs.add(
            (STORE_HOME, "idle-consumable-scan")
        )

        policy._next_required_store_type(snapshot)
        policy._next_required_store_type(snapshot)
        self.assertEqual(
            policy._town_visit_ledger.drift_warnings,
            ["drift:home:idle-consumable-scan"],
        )

        cleared = self._policy(
            [TownNeed(STORE_HOME, "idle-consumable-scan", "home-first")]
        )
        self.assertEqual(cleared._next_required_store_type(snapshot), STORE_HOME)
        cleared._town_visit_ledger.satisfied_needs.add(
            (STORE_HOME, "idle-consumable-scan")
        )
        cleared._town_need_candidates = lambda candidate: []
        cleared._next_required_store_type(snapshot)
        self.assertEqual(cleared._town_visit_ledger.drift_warnings, [])

    def test_departure_telemetry_contains_visit_ledger(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_errand_plan = TownErrandPlan([STORE_HOME])
        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False
        )

        block = policy._departure_block_state(
            snapshot
        )

        self.assertEqual(
            block["town_ledger"],
            {
                "store_visits": {STORE_HOME: 1},
                "need_attempts": {"equipment-catalog": 1},
                "approach_fails": {},
                "unsatisfied_passes": {STORE_HOME: 1},
                "blocked_stores": [],
                "passes_since_progress": 0,
                "drift_warnings": [],
            },
        )

    def test_departure_ready_opportunistic_need_has_no_claim(self):
        needs = [TownNeed(STORE_HOME, "idle-consumable-scan", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_departure_ready = lambda candidate: True

        self.assertFalse(policy._town_claims_active(snapshot))
        self.assertEqual(policy._town_claim_categories, [])
        policy._shopping_approach_step = Mock(
            side_effect=AssertionError("opportunistic errand owned departure turn")
        )
        policy._town_special_key = Mock(return_value="DEPART")

        self.assertEqual(policy._decide(snapshot), "DEPART")
        policy._town_special_key.assert_called()

    def test_claim_terminal_bookkeeping_never_runs_in_dungeon(self):
        policy = self._policy([])
        dungeon = replace(
            self._snapshot(),
            town_flag=False,
            floor_key=(1, 1, 1),
        )
        policy._town_terminal_transitions = Mock(
            side_effect=AssertionError("town transition ran in dungeon")
        )

        policy._decide(dungeon)
        policy._town_terminal_transitions.assert_not_called()

    def test_departure_blocking_supply_need_keeps_claim(self):
        needs = [TownNeed(STORE_GENERAL, "food", "normal")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_departure_ready = lambda candidate: False

        self.assertTrue(policy._town_claims_active(snapshot))
        self.assertEqual(policy._town_claim_categories, ["food"])
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)

    def test_nonhome_count_block_does_not_kill_departure_blocking_claim(self):
        needs = [TownNeed(STORE_GENERAL, "light", "normal")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_visit_ledger.blocked_stores.add(STORE_GENERAL)
        policy._shopping_approach_step = Mock(
            side_effect=AssertionError("blocked claim reached errand router")
        )
        policy._town_special_key = Mock(return_value="DEPART")

        self.assertTrue(policy._town_claims_active(snapshot))
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)

    def test_nonhome_need_count_does_not_kill_departure_blocking_claim(self):
        needs = [TownNeed(STORE_MAGIC, "identify-staff", "normal")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_visit_ledger.need_attempts["identify-staff"] = (
            TOWN_STOP_PASS_LIMIT
        )
        policy._shopping_approach_step = Mock(
            side_effect=AssertionError("exhausted claim reached errand router")
        )
        policy._town_special_key = Mock(return_value="DEPART")

        self.assertTrue(policy._town_claims_active(snapshot))
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_MAGIC)

    def test_nonhome_approach_count_does_not_kill_departure_blocking_claim(self):
        needs = [TownNeed(STORE_TEMPLE, "recall", "normal")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_visit_ledger.approach_fails[STORE_TEMPLE] = (
            TOWN_STOP_PASS_LIMIT
        )
        policy._shopping_approach_step = Mock(
            side_effect=AssertionError("unreachable claim reached errand router")
        )
        policy._town_special_key = Mock(return_value="DEPART")

        self.assertTrue(policy._town_claims_active(snapshot))
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_TEMPLE)

    def test_claimless_town_turn_runs_terminal_bookkeeping(self):
        policy = self._policy([])
        snapshot = replace(
            self._snapshot(),
            player=replace(
                self._snapshot().player,
                gold=FUNDRAISING_GOLD_TARGET,
            ),
        )
        policy._town_terminal_transitions = (
            HengbotPolicy._town_terminal_transitions.__get__(policy)
        )
        policy._fundraising_mode = "prepare"
        policy._planned_mining_runs = 2
        policy._town_special_key = Mock(return_value="DEPART")

        self.assertEqual(policy._decide(snapshot), "DEPART")
        self.assertIsNone(policy._fundraising_mode)
        self.assertIsNone(policy._planned_mining_runs)

    def test_opportunistic_need_claims_only_while_departure_is_blocked(self):
        needs = [TownNeed(STORE_WEAPON, "disposal", "normal")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_departure_ready = lambda candidate: False

        self.assertTrue(policy._town_claims_active(snapshot))
        self.assertEqual(policy._town_claim_categories, ["disposal"])
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_WEAPON)

    def test_town_claim_telemetry_lists_claims_and_empty_default(self):
        needs = [
            TownNeed(STORE_GENERAL, "food", "normal"),
            TownNeed(STORE_BLACK, "black-market", "normal"),
        ]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_departure_ready = lambda candidate: True

        self.assertTrue(policy._town_claims_active(snapshot))
        block = policy._departure_block_state(
            snapshot
        )
        self.assertEqual(block["town_claims"], ["food"])

        policy._town_need_candidates = lambda candidate: [
            TownNeed(STORE_BLACK, "black-market", "normal")
        ]
        self.assertFalse(policy._town_claims_active(snapshot))
        block = policy._departure_block_state(
            snapshot
        )
        self.assertEqual(block["town_claims"], [])

    def test_multi_errand_circuit_is_home_first_and_nearest_neighbor(self):
        stores = {
            STORE_HOME: Position(10, 9),
            STORE_GENERAL: Position(10, 5),
            STORE_ALCHEMIST: Position(10, 12),
            STORE_TEMPLE: Position(10, 16),
            STORE_BLACK: Position(15, 16),
        }
        town_map = TownMap("Outpost", 20, 20, frozenset(), stores)
        needs = [
            TownNeed(STORE_HOME, "deposit", "home-first"),
            TownNeed(STORE_ALCHEMIST, "teleport", "normal"),
            TownNeed(STORE_TEMPLE, "cure-critical", "normal"),
            TownNeed(STORE_GENERAL, "oil", "normal"),
            TownNeed(STORE_BLACK, "black-market", "normal"),
        ]
        policy = self._policy(needs, town_map)
        snapshot = self._snapshot()

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertEqual(
            policy._town_errand_plan.stops,
            [STORE_HOME, STORE_ALCHEMIST, STORE_TEMPLE, STORE_GENERAL, STORE_BLACK],
        )
        self.assertEqual(len(policy._town_errand_plan.stops), len(set(policy._town_errand_plan.stops)))

    def test_optional_black_market_is_after_mandatory_supply_stops(self):
        stores = {
            STORE_HOME: Position(10, 9),
            STORE_GENERAL: Position(10, 5),
            STORE_ALCHEMIST: Position(10, 12),
            STORE_BLACK: Position(10, 10),
        }
        town_map = TownMap("Outpost", 20, 20, frozenset(), stores)
        needs = [
            TownNeed(STORE_HOME, "fundraising-kit", "home-first"),
            TownNeed(STORE_GENERAL, "fundraising-digger", "normal"),
            TownNeed(STORE_ALCHEMIST, "mining-detection", "normal"),
            TownNeed(STORE_BLACK, "black-market", "normal"),
        ]
        policy = self._policy(needs, town_map)

        policy._next_required_store_type(self._snapshot())

        self.assertEqual(
            policy._town_errand_plan.stops,
            [STORE_HOME, STORE_ALCHEMIST, STORE_GENERAL, STORE_BLACK],
        )

    def test_identification_source_precedes_single_withdrawal_home(self):
        needs = [
            TownNeed(STORE_ALCHEMIST, "identification-source", "before-withdrawal"),
            TownNeed(STORE_HOME, "identification-withdrawal", "post-alchemist-home"),
        ]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_ALCHEMIST)
        self.assertEqual(policy._town_errand_plan.stops, [STORE_ALCHEMIST, STORE_HOME])
        self.assertLessEqual(policy._town_errand_plan.stops.count(STORE_HOME), 2)

    def test_latched_stop_skips_and_expired_latch_can_replan(self):
        needs = [TownNeed(STORE_ALCHEMIST, "teleport", "normal")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_store_attempted[STORE_ALCHEMIST] = snapshot.turn
        self.assertEqual(
            policy._next_required_store_type(snapshot), STORE_ALCHEMIST
        )
        policy._town_store_attempted.pop(STORE_ALCHEMIST, None)
        self.assertEqual(policy._next_required_store_type(replace(snapshot, turn=200)), STORE_ALCHEMIST)

    def test_latched_home_rearms_once_for_invalidated_catalog_scan(self):
        # Live 2026-07-23 sequence: a Home deposit invalidated the page scan,
        # unavailable full identification exhausted the Home stop, and deferring
        # that item still left Home latched.  The mandatory rescan was skipped and
        # town fell through to stuck:wander with departure permanently blocked.
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._equipment_catalog.home_scan_complete = False
        policy._town_store_attempted[STORE_HOME] = snapshot.turn

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_HOME],
            ("equipment-catalog",),
        )

        # A failed rescan remains bounded by the normal visit latch instead of
        # opening a new Home carousel.
        policy._town_store_attempted[STORE_HOME] = snapshot.turn
        self.assertIsNone(policy._next_required_store_type(snapshot))
        self.assertEqual(policy._town_errand_plan.skipped_latched, [])

    def test_departure_ready_keeps_persistent_home_need_latched(self):
        needs = [TownNeed(STORE_HOME, "idle-consumable-scan", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._home_disposal_pass = True
        policy._town_store_attempted[STORE_HOME] = snapshot.turn
        policy._town_departure_ready = lambda candidate: True

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

    def test_departure_block_preserves_persistent_home_rearm(self):
        needs = [TownNeed(STORE_HOME, "idle-consumable-scan", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._home_disposal_pass = True
        policy._town_store_attempted[STORE_HOME] = snapshot.turn
        policy._town_departure_ready = lambda candidate: False

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_HOME],
            ("idle-consumable-scan",),
        )

    def test_departure_ready_does_not_skip_first_home_visit(self):
        needs = [TownNeed(STORE_HOME, "idle-consumable-scan", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._home_disposal_pass = True
        policy._town_departure_ready = lambda candidate: True

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

    def test_departure_ready_preserves_post_alchemist_home_rearm(self):
        needs = [
            TownNeed(
                STORE_HOME,
                "identification-withdrawal",
                "post-alchemist-home",
            )
        ]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_store_attempted[STORE_HOME] = snapshot.turn
        policy._town_departure_ready = lambda candidate: True

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

    def test_departure_ready_does_not_rebuild_exhausted_plan_for_home(self):
        needs = [TownNeed(STORE_HOME, "deposit", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME],
            index=1,
            completed_this_visit=[STORE_HOME],
        )
        policy._town_store_attempted[STORE_HOME] = snapshot.turn
        policy._town_departure_ready = lambda candidate: True

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._town_errand_plan.stops, [STORE_HOME])

    def test_latched_home_rearms_for_new_deposit_after_earlier_home_pass(self):
        needs = [TownNeed(STORE_HOME, "deposit", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_store_attempted[STORE_HOME] = snapshot.turn

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_HOME],
            ("deposit",),
        )

        policy._town_store_attempted[STORE_HOME] = snapshot.turn
        self.assertIsNone(policy._next_required_store_type(snapshot))

    def test_new_home_deposit_rebuilds_plan_after_later_shop_finishes(self):
        # Live 2026-07-24 sequence: Home completed, Black Market then bought a
        # surplus speed potion, and the resulting deposit could not supersede
        # the exhausted plan's completed/attempted Home latch.
        active = [TownNeed(STORE_HOME, "deposit", "home-first")]
        policy = self._policy(active)
        snapshot = self._snapshot()

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        active[:] = []
        policy._report_town_stop_pass(snapshot, STORE_HOME, goal_satisfied=True)
        active[:] = [TownNeed(STORE_BLACK, "black-market", "normal")]
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_BLACK)
        active[:] = []
        policy._report_town_stop_pass(snapshot, STORE_BLACK, goal_satisfied=True)
        policy._town_store_attempted[STORE_HOME] = snapshot.turn

        active[:] = [TownNeed(STORE_HOME, "deposit", "home-first")]
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._town_errand_plan.stops, [STORE_HOME])

    def test_new_home_work_does_not_rearm_a_blocked_home(self):
        active = [TownNeed(STORE_HOME, "deposit", "home-first")]
        policy = self._policy(active)
        snapshot = self._snapshot()
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME],
            index=1,
            blocked_this_visit=[STORE_HOME],
        )
        policy._town_store_attempted[STORE_HOME] = snapshot.turn

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

    def test_mid_visit_need_is_inserted_after_current_stop(self):
        active = [TownNeed(STORE_GENERAL, "oil", "normal")]
        policy = self._policy(active)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        active.append(TownNeed(STORE_ALCHEMIST, "teleport", "normal"))
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertEqual(policy._town_errand_plan.stops, [STORE_GENERAL, STORE_ALCHEMIST])
        self.assertEqual(policy._town_errand_plan.inserted_this_visit, [])

    def test_new_supply_needs_rebuild_an_exhausted_identification_plan(self):
        active = [
            TownNeed(
                STORE_ALCHEMIST,
                "identification-source",
                "before-withdrawal",
            )
        ]
        policy = self._policy(active)
        snapshot = self._snapshot()
        self.assertEqual(
            policy._next_required_store_type(snapshot), STORE_ALCHEMIST
        )
        active[:] = []
        policy._report_town_stop_pass(
            snapshot, STORE_ALCHEMIST, goal_satisfied=True
        )

        active[:] = [
            TownNeed(STORE_GENERAL, "oil", "normal"),
            TownNeed(STORE_MAGIC, "identify-staff", "normal"),
        ]

        self.assertIn(
            policy._next_required_store_type(snapshot),
            {STORE_GENERAL, STORE_MAGIC},
        )
        self.assertEqual(
            set(policy._town_errand_plan.stops),
            {STORE_GENERAL, STORE_MAGIC},
        )

    def test_full_identification_purchase_rearms_post_alchemist_home(self):
        # Live 2026-07-23 sequence: Home was completed while discovering a
        # partly-known item, Alchemist then supplied *Identify*, but the shared
        # completed/attempted Home latch discarded the required withdrawal pass
        # and town fell through to stuck:wander.
        active = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(active)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        active[:] = []
        policy._report_town_stop_pass(snapshot, STORE_HOME, goal_satisfied=True)
        policy._town_store_attempted[STORE_HOME] = snapshot.turn

        active[:] = [
            TownNeed(
                STORE_ALCHEMIST,
                "identification-source",
                "before-withdrawal",
            )
        ]
        self.assertEqual(
            policy._next_required_store_type(snapshot), STORE_ALCHEMIST
        )
        active[:] = []
        policy._report_town_stop_pass(
            snapshot, STORE_ALCHEMIST, goal_satisfied=True
        )
        policy._town_store_attempted[STORE_ALCHEMIST] = snapshot.turn

        active[:] = [
            TownNeed(
                STORE_HOME,
                "identification-withdrawal",
                "post-alchemist-home",
            )
        ]
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._town_errand_plan.stops, [STORE_HOME])

    def test_upfront_second_home_stop_ignores_only_first_home_latch(self):
        active = [
            TownNeed(STORE_HOME, "equipment-catalog", "home-first"),
            TownNeed(
                STORE_ALCHEMIST,
                "identification-source",
                "before-withdrawal",
            ),
            TownNeed(
                STORE_HOME,
                "identification-withdrawal",
                "post-alchemist-home",
            ),
        ]
        policy = self._policy(active)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        policy._town_errand_plan.need_categories[STORE_HOME] = (
            "equipment-catalog",
        )
        active.pop(0)
        policy._report_town_stop_pass(snapshot, STORE_HOME, goal_satisfied=True)
        policy._town_store_attempted[STORE_HOME] = snapshot.turn

        self.assertEqual(
            policy._next_required_store_type(snapshot), STORE_ALCHEMIST
        )
        active.pop(0)
        policy._report_town_stop_pass(
            snapshot, STORE_ALCHEMIST, goal_satisfied=True
        )
        policy._town_store_attempted[STORE_ALCHEMIST] = snapshot.turn

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

    def test_mid_visit_mandatory_need_is_inserted_before_optional_stop(self):
        active = [
            TownNeed(STORE_GENERAL, "oil", "normal"),
            TownNeed(STORE_BLACK, "black-market", "normal"),
        ]
        policy = self._policy(active)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)

        active.append(TownNeed(STORE_ALCHEMIST, "teleport", "normal"))
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertEqual(
            policy._town_errand_plan.stops,
            [STORE_GENERAL, STORE_ALCHEMIST, STORE_BLACK],
        )

    def test_mid_visit_replan_drops_a_stop_whose_need_disappeared(self):
        active = [
            TownNeed(STORE_GENERAL, "oil", "normal"),
            TownNeed(STORE_BLACK, "black-market", "normal"),
        ]
        policy = self._policy(active)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)

        active.remove(TownNeed(STORE_BLACK, "black-market", "normal"))
        active.append(TownNeed(STORE_ALCHEMIST, "teleport", "normal"))

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertEqual(
            policy._town_errand_plan.stops,
            [STORE_GENERAL, STORE_ALCHEMIST],
        )

    def test_enumeration_is_pure_and_terminal_ready_builds_no_plan(self):
        policy = HengbotPolicy()
        snapshot = self._snapshot()
        watched = (
            policy._fundraising_mode,
            policy._planned_mining_runs,
            dict(policy._town_store_attempted),
            policy._town_blocked_reason,
            policy._town_restock_wait_until,
        )
        first = policy._enumerate_town_needs(snapshot)
        second = policy._enumerate_town_needs(snapshot)
        self.assertEqual(first, second)
        self.assertEqual(
            watched,
            (
                policy._fundraising_mode,
                policy._planned_mining_runs,
                dict(policy._town_store_attempted),
                policy._town_blocked_reason,
                policy._town_restock_wait_until,
            ),
        )
        empty = self._policy([])
        self.assertIsNone(empty._next_required_store_type(snapshot))
        self.assertIsNone(empty._town_errand_plan)

    def test_cycle_break_and_restock_suppression_clear_plan(self):
        policy = self._policy([TownNeed(STORE_GENERAL, "oil", "normal")])
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        policy._break_town_cycle(snapshot)
        self.assertIsNone(policy._town_errand_plan)
        self.assertIsNone(policy._next_required_store_type(snapshot))

    def test_completed_stop_is_not_reacquired_from_live_needs(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME],
            index=1,
            completed_this_visit=[STORE_HOME],
        )

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertEqual(policy._town_errand_plan.stops, [STORE_HOME])

    def test_unsatisfied_stop_blocks_after_three_completed_passes(self):
        needs = [
            TownNeed(STORE_HOME, "safe-weapon", "home-first"),
            TownNeed(STORE_GENERAL, "food", "normal"),
        ]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

        for _ in range(TOWN_STOP_PASS_LIMIT):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)

    def test_calibration_prerequisite_home_scan_uses_calibration_visit_bound(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("home-scan-incomplete",), result=None,
        )
        self.assertIsNone(policy._calibration_phase)
        self.assertFalse(policy._equipment_catalog.home_scan_complete)
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

        for entry in range(CALIBRATION_HOME_VISIT_LIMIT - 1):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False,
                operation_completed=True,
            )
            self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
            self.assertEqual(
                policy._town_visit_ledger.unsatisfied_passes[STORE_HOME],
                entry + 1,
            )

        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False,
            operation_completed=False,
        )
        self.assertIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME],
            CALIBRATION_HOME_VISIT_LIMIT,
        )

    def test_turn_2952001_mixed_home_work_uses_pipeline_ceiling(self):
        """Embed the mixed Home owner from the third onset capture."""
        needs = [
            TownNeed(STORE_HOME, "equipment-catalog", "home-first"),
            TownNeed(
                STORE_HOME,
                "identification-withdrawal",
                "surplus-identify-staff",
            ),
        ]
        policy = self._policy(needs)
        snapshot = self._snapshot(turn=2952001)
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("home-scan-incomplete",), result=None,
        )

        for _ in range(TOWN_STOP_PASS_LIMIT):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False,
                operation_completed=True,
            )

        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(
            policy._town_store_visit_limit(STORE_HOME),
            CALIBRATION_HOME_VISIT_LIMIT,
        )

    def test_any_optimizer_blocker_is_outstanding_equipment_work(self):
        policy = self._policy(
            [TownNeed(STORE_HOME, "safe-weapon", "home-first")]
        )
        policy._equipment_catalog.home_scan_complete = True
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("no-valid-loadout",), result=None,
        )

        self.assertEqual(
            policy._town_store_visit_limit(STORE_HOME),
            CALIBRATION_HOME_VISIT_LIMIT,
        )

    def test_home_outside_calibration_pipeline_keeps_three_visit_bound(self):
        """Historical name retained; equipment blockers now define the scope."""
        self.test_any_optimizer_blocker_is_outstanding_equipment_work()

    def test_successful_optimizer_session_keeps_home_allowance(self):
        policy = self._policy(
            [TownNeed(STORE_HOME, "safe-weapon", "home-first")]
        )
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=object(),
        )
        policy._equipment_transaction_session = SimpleNamespace(complete=False)

        self.assertTrue(policy._outstanding_equipment_work())
        self.assertEqual(
            policy._town_store_visit_limit(STORE_HOME),
            CALIBRATION_HOME_VISIT_LIMIT,
        )
        with self.assertRaisesRegex(ValueError, "no visit-count limit"):
            policy._town_store_visit_limit(STORE_ALCHEMIST)

    def test_home_identity_queue_is_outstanding_equipment_work(self):
        policy = self._policy([])
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=None,
        )
        policy._home_pending_batch = [("queued armour", 30, 1)]

        self.assertTrue(policy._outstanding_equipment_work())
        self.assertEqual(
            policy._town_store_visit_limit(STORE_HOME),
            CALIBRATION_HOME_VISIT_LIMIT,
        )

    def test_prerequisite_scan_visits_continue_into_calibration_budget(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("home-scan-incomplete",), result=None,
        )
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        for _ in range(3):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False,
                operation_completed=True,
            )

        policy._calibration_phase = "deposit"
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",), result=None,
        )
        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False,
            operation_completed=True,
        )

        self.assertEqual(policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 4)
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)

    def test_calibration_home_completed_entries_block_at_visit_limit(self):
        needs = [TownNeed(STORE_HOME, "deposit", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        policy._calibration_phase = "deposit"
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",), result=None,
        )
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

        for entry in range(CALIBRATION_HOME_VISIT_LIMIT - 1):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False,
                operation_completed=True,
            )
            self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
            self.assertEqual(
                policy._town_visit_ledger.unsatisfied_passes[STORE_HOME],
                entry + 1,
            )

        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False,
            operation_completed=True,
        )

        self.assertIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME],
            CALIBRATION_HOME_VISIT_LIMIT,
        )

    def test_calibration_home_approach_bound_is_visit_limit(self):
        policy = HengbotPolicy()
        policy._calibration_phase = "deposit"
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",), result=None,
        )
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            CALIBRATION_HOME_VISIT_LIMIT - 1
        )
        policy._shopping_approach_step(self._snapshot(), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        policy._town_visit_ledger.approach_fails[STORE_HOME] += 1
        policy._shopping_approach_step(self._snapshot(), STORE_HOME)
        self.assertIn(STORE_HOME, policy._town_store_attempted)

    def _settle_failed_store_walk(self, policy, snapshot, store_type):
        step = policy._shopping_approach_step(snapshot, store_type)
        self.assertIsNotNone(step)
        policy.last_reason = "shop:approach"
        key = policy._shopping_approach_key(snapshot, step, "shop:travel")
        policy.confirm_key_posted(key)
        policy._observe(snapshot)

    def test_calibration_home_oscillation_yields_to_entry_bound(self):
        needs = [TownNeed(STORE_HOME, "deposit", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot(width=80, height=40)
        home = replace(grid(10, 13), store_number=STORE_HOME)
        snapshot = replace(
            snapshot,
            grids={
                **snapshot.grids,
                home.position: home,
            },
            town_flag=True,
        )
        policy._calibration_phase = "deposit"
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",), result=None,
        )
        policy._recent.extend([snapshot.player.position] * STUCK_WINDOW)
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

        for entry in range(CALIBRATION_HOME_VISIT_LIMIT):
            self._settle_failed_store_walk(policy, snapshot, STORE_HOME)
            policy._shop_approach_stuck_count = SHOP_APPROACH_STUCK_LIMIT - 1
            self._settle_failed_store_walk(policy, snapshot, STORE_HOME)
            self.assertNotIn(STORE_HOME, policy._town_store_attempted)
            self.assertEqual(
                policy._town_visit_ledger.approach_fails[STORE_HOME], 0
            )
            policy._report_town_stop_pass(
                snapshot,
                STORE_HOME,
                goal_satisfied=False,
                operation_completed=True,
            )

        self.assertIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME],
            CALIBRATION_HOME_VISIT_LIMIT,
        )

    def test_turn_2956451_scan_pipeline_oscillation_preserves_home_claim(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot(turn=2956451, width=80, height=40)
        home = replace(grid(10, 13), store_number=STORE_HOME)
        snapshot = replace(
            snapshot,
            grids={**snapshot.grids, home.position: home},
            town_flag=True,
        )
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("home-scan-incomplete",), result=None,
        )
        policy._recent.extend([snapshot.player.position] * STUCK_WINDOW)
        self._settle_failed_store_walk(policy, snapshot, STORE_HOME)
        policy._shop_approach_stuck_count = SHOP_APPROACH_STUCK_LIMIT - 1

        self.assertIsNone(policy._calibration_phase)
        self._settle_failed_store_walk(policy, snapshot, STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._town_visit_ledger.approach_fails[STORE_HOME], 0)
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

    def test_home_oscillation_with_optimizer_blocker_preserves_equipment_work(self):
        policy = self._policy(
            [TownNeed(STORE_HOME, "safe-weapon", "home-first")]
        )
        snapshot = self._snapshot(width=80, height=40)
        home = replace(grid(10, 13), store_number=STORE_HOME)
        snapshot = replace(
            snapshot,
            grids={**snapshot.grids, home.position: home},
            town_flag=True,
        )
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("no-valid-loadout",), result=None,
        )
        policy._recent.extend([snapshot.player.position] * STUCK_WINDOW)
        self._settle_failed_store_walk(policy, snapshot, STORE_HOME)
        policy._shop_approach_stuck_count = SHOP_APPROACH_STUCK_LIMIT - 1

        self._settle_failed_store_walk(policy, snapshot, STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._town_visit_ledger.approach_fails[STORE_HOME], 0)

    def test_home_oscillation_outside_pipeline_marks_store_attempted(self):
        policy = self._policy([])
        snapshot = self._snapshot(width=80, height=40)
        home = replace(grid(10, 13), store_number=STORE_HOME)
        snapshot = replace(
            snapshot,
            grids={**snapshot.grids, home.position: home},
            town_flag=True,
        )
        policy._equipment_optimization_preparation = None
        policy._recent.extend([snapshot.player.position] * STUCK_WINDOW)
        self._settle_failed_store_walk(policy, snapshot, STORE_HOME)
        policy._shop_approach_stuck_count = SHOP_APPROACH_STUCK_LIMIT - 1

        self._settle_failed_store_walk(policy, snapshot, STORE_HOME)
        self.assertIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._town_visit_ledger.approach_fails[STORE_HOME], 1)

    def test_identically_replaced_counterfactual_approach_is_discarded(self):
        policy = self._policy([])
        snapshot = self._snapshot(width=80, height=40)
        home = replace(grid(10, 13), store_number=STORE_HOME)
        snapshot = replace(
            snapshot, grids={**snapshot.grids, home.position: home}, town_flag=True
        )
        step = policy._shopping_approach_step(snapshot, STORE_HOME)
        self.assertIsNotNone(step)
        policy.last_reason = "shop:approach"
        staged = policy._shopping_approach_key(snapshot, step, "shop:travel")

        replacement = "".join(staged)
        self.assertEqual(replacement, staged)
        self.assertFalse(hasattr(replacement, "approach_provenance"))
        policy.confirm_key_posted(replacement)
        policy._observe(snapshot)

        self.assertIsNone(policy._pending_shop_approach)
        self.assertEqual(policy._shop_approach_stuck_count, 0)

    def test_store_episode_switch_clears_previous_origin(self):
        policy = self._policy([])
        base = self._snapshot(width=80, height=40)
        home = replace(grid(10, 13), store_number=STORE_HOME)
        general = replace(grid(13, 10), store_number=STORE_GENERAL)
        base = replace(
            base,
            grids={**base.grids, home.position: home, general.position: general},
            town_flag=True,
        )

        def emitted_walk(snapshot, store_type):
            step = policy._shopping_approach_step(snapshot, store_type)
            self.assertIsNotNone(step)
            policy.last_reason = "shop:approach"
            key = policy._shopping_approach_key(snapshot, step, "shop:travel")
            policy.confirm_key_posted(key)
            dy, dx = {
                "1": (1, -1), "2": (1, 0), "3": (1, 1),
                "4": (0, -1), "6": (0, 1),
                "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
            }[key]
            origin = snapshot.player.position
            return Position(origin.y + dy, origin.x + dx)

        first_step = emitted_walk(base, STORE_HOME)
        after_home = replace(
            base, player=replace(base.player, position=first_step), turn=base.turn + 1
        )
        policy._observe(after_home)
        policy._arbiter_close_store_visit("town-errand", "test-store-switch")
        second_step = emitted_walk(after_home, STORE_GENERAL)
        after_general = replace(
            after_home,
            player=replace(after_home.player, position=second_step),
            turn=base.turn + 2,
        )
        policy._observe(after_general)
        policy._arbiter_close_store_visit("town-errand", "test-store-switch-back")
        emitted_walk(after_general, STORE_HOME)
        returned_to_prior_origin = replace(
            after_general,
            player=replace(after_general.player, position=after_home.player.position),
            turn=base.turn + 3,
        )
        policy._observe(returned_to_prior_origin)

        self.assertEqual(policy._shop_approach_stuck_store, STORE_HOME)
        self.assertEqual(policy._shop_approach_stuck_count, 0)

    def test_store_arrival_resets_approach_episode(self):
        policy = self._policy([])
        base = self._snapshot(width=80, height=40)
        intermediate = Position(base.player.position.y, base.player.position.x + 1)
        entrance = Position(base.player.position.y, base.player.position.x + 2)
        store_grid = replace(grid(entrance.y, entrance.x), store_number=STORE_HOME)
        base = replace(
            base,
            grids={
                **base.grids,
                intermediate: grid(intermediate.y, intermediate.x),
                entrance: store_grid,
            },
            town_flag=True,
        )

        policy._shopping_approach_goal = entrance
        policy._shopping_approach_store_type = STORE_HOME
        policy.last_reason = "shop:approach"
        key = policy._shopping_approach_key(base, entrance, "shop:travel")
        policy.confirm_key_posted(key)
        arrived = replace(
            base,
            player=replace(base.player, position=entrance),
            turn=base.turn + 1,
        )
        policy._observe(arrived)

        self.assertEqual(policy._shop_approach_stuck_count, 0)
        self.assertIsNone(policy._shop_approach_stuck_store)
        self.assertIsNone(policy._shop_approach_previous_origin)
        self.assertIsNone(policy._pending_shop_approach)

    def test_blocked_home_releases_departure_latches(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        pending = ("unknown sword", 23, 2)
        policy._home_candidate_waiting = True
        policy._home_pending_item = pending
        policy._home_pending_batch = [pending]
        pending_item = store_item("a", 23, 2, name="unknown sword")
        policy._home_atomic_withdraw_pending = (pending, 0, pending_item, 1)
        policy._equipment_catalog.home_scan_complete = True
        policy._recall_departure_ready = lambda candidate: True
        policy._food_ready = lambda candidate: True
        policy._light_ready = lambda candidate: True
        policy._teleport_ready = lambda candidate: True
        policy._cure_critical_ready = lambda candidate: True
        policy._identify_staff_ready = lambda candidate: True
        policy._town_pack_space_ready = lambda candidate: True
        policy._inventory_overweight = lambda candidate: False
        policy._home_available = lambda candidate: True
        policy._equipment_departure_ready = lambda candidate: True
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertFalse(policy._town_departure_ready(snapshot))

        for _ in range(CALIBRATION_HOME_VISIT_LIMIT):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )

        self.assertFalse(policy._home_candidate_waiting)
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual(policy._home_pending_batch, [])
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertTrue(policy._town_departure_ready(snapshot))
        self.assertNotIn(
            "home_candidate_waiting",
            policy._departure_block_state(
                snapshot
            )["failed"],
        )

    def test_withdrawal_unfulfilled_fires_and_forces_one_rescan(self):
        """Repeated same-X route claims produce the outcome defect artifact."""
        policy = self._policy(
            [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        )
        snapshot = self._snapshot()
        target = ("captured armour", 36, 14)
        policy._home_pending_item = target
        policy._next_required_store_type(snapshot)
        original_invalidate = policy._invalidate_home_observation
        policy._invalidate_home_observation = Mock(wraps=original_invalidate)

        for _ in range(6):
            policy.last_reason = "home:route-claim-unfulfilled"
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )

        defect = policy._withdrawal_unfulfilled_defect
        self.assertEqual(defect["marker"], "WITHDRAWAL_UNFULFILLED_DEFECT")
        self.assertEqual(defect["item"], target)
        self.assertEqual(
            defect["reason"], "home:route-claim-unfulfilled"
        )
        self.assertTrue(policy._home_knowledge_invalidated)
        self.assertEqual(policy._invalidate_home_observation.call_count, 1)
        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False
        )
        self.assertEqual(policy._invalidate_home_observation.call_count, 1)

    def test_withdrawal_gain_and_target_change_reset_without_flag(self):
        policy = self._policy(
            [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        )
        snapshot = self._snapshot()
        first = ("first armour", 36, 14)
        second = ("second armour", 36, 15)
        policy._home_pending_item = first
        policy._next_required_store_type(snapshot)
        for _ in range(5):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )
        policy._home_pending_item = second
        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False
        )
        self.assertEqual(policy._withdrawal_unsatisfied_for[0], second)
        self.assertEqual(policy._withdrawal_unsatisfied_for[2], 1)

        landed = replace(
            snapshot,
            inventory=(item("a", 36, 15, name="second armour"),),
        )
        policy._observe_withdrawal_unsatisfied_pass(landed)
        self.assertIsNone(policy._withdrawal_unsatisfied_for)
        self.assertEqual(policy._withdrawal_unfulfilled_defect, {})
        self.assertFalse(policy._home_knowledge_invalidated)

    def test_withdrawal_defect_is_flag_only(self):
        policy = HengbotPolicy()
        snapshot = replace(self._snapshot(), town_flag=False)
        target = ("flag-only armour", 36, 14)
        policy._home_pending_item = target
        policy._withdrawal_unsatisfied_for = (
            target, 0, 5, False
        )

        def normal_policy(candidate):
            policy.last_reason = "home:route-claim-unfulfilled"
            policy._observe_withdrawal_unsatisfied_pass(candidate)
            return "6"

        policy._choose_key_with_latch_capture = normal_policy
        key = policy.choose_key(snapshot)

        self.assertEqual(key, "6")
        self.assertIsNone(policy._town_blocked_reason)
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(policy.last_reason, "home:route-claim-unfulfilled")
        self.assertEqual(policy._home_pending_item, target)

    def test_unblocked_home_pass_preserves_departure_latches(self):
        needs = [TownNeed(STORE_HOME, "equipment-catalog", "home-first")]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        pending = ("unknown sword", 23, 2)
        pending_item = store_item("a", 23, 2, name="unknown sword")
        inflight = (pending, 0, pending_item, 1)
        policy._home_candidate_waiting = True
        policy._home_pending_item = pending
        policy._home_pending_batch = [pending]
        policy._home_atomic_withdraw_pending = inflight
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

        for _ in range(TOWN_STOP_PASS_LIMIT - 1):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )

        self.assertTrue(policy._home_candidate_waiting)
        self.assertEqual(policy._home_pending_item, pending)
        self.assertEqual(policy._home_pending_batch, [pending])
        self.assertEqual(policy._home_atomic_withdraw_pending, inflight)

    def test_next_town_visit_does_not_rebuild_pack_item_as_home_claim(self):
        needs = [TownNeed(STORE_HOME, "safe-weapon", "home-first")]
        policy = self._policy(needs)
        town = replace(self._snapshot(), town_flag=True)
        dungeon = replace(town, town_flag=False, floor_key=(1, 1, 0))
        pending = item(
            "b", 23, 2, name="unknown sword", aware=False, known=False,
            is_equipment=True,
        )
        policy._home_pending_batch = [policy._item_signature(pending)]
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)
        for _ in range(CALIBRATION_HOME_VISIT_LIMIT):
            policy._report_town_stop_pass(
                town, STORE_HOME, goal_satisfied=False
            )
        self.assertEqual(policy._home_pending_batch, [])

        policy._observe(dungeon)
        next_visit = replace(town, inventory=(pending,), turn=town.turn + 1)
        policy.prime(next_visit)

        self.assertEqual(policy._home_pending_batch, [])

    def test_unsatisfied_stop_blocks_across_plan_rebuild(self):
        needs = [
            TownNeed(STORE_HOME, "safe-weapon", "home-first"),
            TownNeed(STORE_GENERAL, "food", "normal"),
        ]
        policy = self._policy(needs)
        snapshot = self._snapshot()
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)

        for _ in range(TOWN_STOP_PASS_LIMIT - 1):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )
        policy._town_errand_plan = None
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False
        )

        self.assertIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)

    def test_home_category_rearms_once_per_visit_and_resets_next_visit(self):
        needs = [TownNeed(STORE_HOME, "deposit", "home-first")]
        policy = self._policy(needs)
        town = replace(self._snapshot(), town_flag=True)
        dungeon = replace(town, town_flag=False, floor_key=(1, 1, 0))
        policy._observe(town)
        policy._town_store_attempted[STORE_HOME] = town.turn

        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_HOME], ("deposit",)
        )
        policy._town_store_attempted[STORE_HOME] = town.turn
        policy._town_errand_plan = None
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)

        policy._observe(dungeon)
        policy._observe(town)
        policy._town_store_attempted[STORE_HOME] = town.turn
        policy._town_errand_plan = None
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)

    def test_approach_failure_bound_survives_rearm_until_next_visit(self):
        needs = [TownNeed(STORE_HOME, "deposit", "home-first")]
        policy = self._policy(needs)
        town = replace(self._snapshot(), town_flag=True)
        dungeon = replace(town, town_flag=False, floor_key=(1, 1, 0))
        policy._observe(town)
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            TOWN_STOP_PASS_LIMIT
        )
        policy._town_store_attempted.pop(STORE_HOME, None)

        self.assertIsNone(policy._next_required_store_type(town))
        policy._town_store_attempted.pop(STORE_HOME, None)
        self.assertIsNone(policy._shopping_approach_step(town))

        policy._observe(dungeon)
        policy._observe(town)
        policy._town_errand_plan = None
        self.assertEqual(policy._next_required_store_type(town), STORE_HOME)

    def test_non_home_leave_blocks_reopened_out_of_stock_stop(self):
        # Regression for the 2026-07-23 Alchemist loop.  A pending *Identify*
        # request re-opened the attempted latch after every empty visit, while
        # the errand plan remained pinned at the same stop forever.
        needs = [
            TownNeed(
                STORE_ALCHEMIST,
                "identification-source",
                "before-withdrawal",
            )
        ]
        policy = self._policy(needs)
        town = self._snapshot()
        shop = replace(
            town,
            store=StoreState(store_type=STORE_ALCHEMIST, items=[]),
        )
        self.assertEqual(
            policy._next_required_store_type(town), STORE_ALCHEMIST
        )

        self.assertEqual(policy.choose_key(shop), LEAVE_STORE_KEY)
        policy._town_store_attempted.pop(STORE_ALCHEMIST, None)
        first_outside = replace(town, turn=town.turn + 10)
        policy.choose_key(first_outside)

        self.assertIn(
            STORE_ALCHEMIST,
            policy._town_visit_ledger.nonhome_attempted_without_effect,
        )
        self.assertIsNone(policy._next_required_store_type(town))
        self.assertEqual(
            policy._town_blocked_reason, "departure-unsatisfiable"
        )

        # WAIT advances the real game turn, and ordinary wandering can change
        # position.  Neither is a store effect, so neither may release the
        # refusal or make the Alchemist route live again.
        route_reasons = []
        for decision in range(1, 9):
            advanced = replace(
                town,
                turn=first_outside.turn + decision * 10,
                player=replace(
                    town.player,
                    position=Position(
                        town.player.position.y,
                        town.player.position.x + decision,
                    ),
                ),
            )
            key = policy.choose_key(advanced)
            route_reasons.append(policy.last_reason)
            self.assertEqual(key, WAIT_KEY)
            self.assertIn(
                policy.last_reason,
                {
                    "town:blocked:departure-unsatisfiable",
                    "town:blocked:owner-retired",
                },
            )
            self.assertIn(
                STORE_ALCHEMIST,
                policy._town_visit_ledger.nonhome_attempted_without_effect,
            )

        self.assertFalse(
            any("alchemist" in reason.lower() for reason in route_reasons),
            route_reasons,
        )

    def test_terminal_router_honors_completed_identification_stop(self):
        # The errand plan can finish while a full-identification request remains
        # (fundraising needs intentionally own the plan).  The terminal router
        # must not ignore that completed Alchemist visit and reacquire it.
        policy = HengbotPolicy()
        town = self._snapshot()
        policy._identification_need = "full"
        policy._identification_candidate = ("ego blade", 23, 4)
        policy._home_candidate_waiting = False
        policy._fundraising_mode = "prepare"
        policy._town_errand_plan = TownErrandPlan(
            [STORE_ALCHEMIST],
            index=1,
            completed_this_visit=[STORE_ALCHEMIST],
        )

        self.assertNotEqual(
            policy._town_terminal_transitions(town), STORE_ALCHEMIST
        )

    def test_registry_cannot_reacquire_a_completed_plan_stop(self):
        # Revert-proof T4 regression: the only live producer still names the
        # completed stop, but the visit ledger/plan authority suppresses it.
        policy = HengbotPolicy()
        town = self._snapshot()
        policy._town_errand_plan = TownErrandPlan(
            [STORE_BLACK],
            index=1,
            completed_this_visit=[STORE_BLACK],
        )
        policy._town_need_candidates = lambda snapshot: [
            TownNeed(STORE_BLACK, "black-market", "normal")
        ]

        self.assertEqual(policy._next_required_store_type(town), STORE_BLACK)
        self.assertNotIn(STORE_BLACK, policy._town_store_attempted)

    def test_completed_stop_has_no_terminal_router_recheck(self):
        # Restock rechecks must now be exposed by a registry producer after the
        # transition step; a second routing result cannot bypass the registry.
        policy = HengbotPolicy()
        town = self._snapshot(turn=2000)
        policy._town_errand_plan = TownErrandPlan(
            [STORE_ALCHEMIST],
            index=1,
            completed_this_visit=[STORE_ALCHEMIST],
        )
        policy._town_restock_rechecked.add(STORE_ALCHEMIST)
        transition_calls = []
        candidate_calls = []

        def transition(snapshot):
            transition_calls.append(snapshot.turn)

        def candidates(snapshot):
            candidate_calls.append(snapshot.turn)
            return [
                TownNeed(STORE_ALCHEMIST, "teleport", "normal")
            ] if transition_calls else []

        policy._town_terminal_transitions = transition
        policy._town_need_candidates = candidates
        policy._town_store_attempted[STORE_ALCHEMIST] = town.turn

        self.assertIsNone(policy._next_required_store_type(town))
        self.assertEqual(transition_calls, [town.turn])
        self.assertGreaterEqual(len(candidate_calls), 1)

    def test_transaction_home_override_uses_equipment_work_hard_ceiling(self):
        needs = [TownNeed(STORE_GENERAL, "food", "normal")]
        policy = self._policy(needs)
        snapshot = self._snapshot(turn=512170)
        policy._equipment_transaction_session = SimpleNamespace(
            executable=True,
            required_context="home",
            pending_action=None,
            current_action=None,
        )

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        for _ in range(CALIBRATION_HOME_VISIT_LIMIT):
            policy._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )

        self.assertIsNone(policy._equipment_transaction_session)
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertIn(STORE_HOME, policy._town_store_attempted)

    def test_transaction_home_override_is_blocked_by_same_three_pass_owner(self):
        """Historical name retained; the same owner has the calibration ceiling."""
        self.test_transaction_home_override_uses_equipment_work_hard_ceiling()

    def test_transaction_deposit_then_withdraw_keeps_home_owner_between_visits(self):
        policy = self._policy([])
        snapshot = self._snapshot(turn=512170)
        session = SimpleNamespace(
            executable=True,
            required_context="home",
            pending_action=None,
            current_action=None,
        )
        policy._equipment_transaction_session = session

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        session.required_context = "outside_home"  # deposit confirmed; equip next
        policy._report_town_stop_pass(snapshot, STORE_HOME, goal_satisfied=False)
        session.required_context = "home"  # later withdrawal in the same transaction

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 1
        )

    def test_registry_keeps_still_produced_need_unsatisfied_after_handler_pass(self):
        policy = HengbotPolicy()
        snapshot = self._snapshot()
        policy._home_disposal_pass = True

        self.assertNotEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_errand_plan.stops)
        home = replace(snapshot, store=StoreState(STORE_HOME, []))
        self.assertIn(
            TownNeed(STORE_HOME, "idle-consumable-scan", "home-first"),
            policy._enumerate_town_needs(home),
        )
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME],
            need_categories={STORE_HOME: ("idle-consumable-scan",)},
        )
        policy._report_town_stop_pass(
            home, STORE_HOME, goal_satisfied=True
        )

        self.assertEqual(policy._town_errand_plan.index, 0)
        self.assertNotIn(
            (STORE_HOME, "idle-consumable-scan"),
            policy._town_visit_ledger.satisfied_needs,
        )
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 1
        )

    def test_registry_enumerator_matches_extracted_predicates(self):
        base = self._snapshot()
        cases = []

        disposal_pass = HengbotPolicy()
        disposal_pass._home_disposal_pass = True
        cases.append(("disposal-pass", disposal_pass, base))

        pending_item = item(
            "q", TVAL_POTION, SV_POTION_CURE_CRITICAL,
            name="known surplus cure", known=True,
        )
        disposal_pending = HengbotPolicy()
        disposal_pending._home_disposal_pending = (
            disposal_pending._item_signature(pending_item),
            "sell",
        )
        cases.append((
            "disposal-pending",
            disposal_pending,
            replace(base, inventory=[pending_item]),
        ))

        opening = HengbotPolicy()
        opening._opening_q34_torch_shortage = lambda snapshot: 1
        cases.append(("opening-q34-torch-shortage", opening, base))

        post_alchemist = HengbotPolicy()
        post_alchemist._home_candidate_waiting = True
        cases.append(("post-alchemist-home", post_alchemist, base))

        cases.append((
            "birth",
            HengbotPolicy(),
            replace(base, player=replace(base.player, class_id=-1)),
        ))

        for mode in ("prepare", "mine", "scavenge"):
            fundraising = HengbotPolicy()
            fundraising._fundraising_mode = mode
            cases.append((f"fundraising-{mode}", fundraising, base))

        for label, policy, snapshot in cases:
            with self.subTest(case=label):
                self.assertEqual(
                    policy._enumerate_town_needs(snapshot),
                    policy._town_need_candidates(snapshot),
                )

class ProbePurityIncidentPinsTest(unittest.TestCase):
    """Pin the captured Home-first ownership-veto incident."""

    def test_pin_vacuity_full_window_keeps_probe_results_out_of_final_stops(self):
        if os.environ.get("HENGBOT_PROBE_PURITY_REPLAY_CHILD") != "1":
            environment = os.environ.copy()
            environment["HENGBOT_PROBE_PURITY_REPLAY_CHILD"] = "1"
            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    f"{__name__}.ProbePurityIncidentPinsTest."
                    "test_pin_vacuity_full_window_keeps_probe_results_out_of_final_stops",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=80,
            )
            self.assertEqual(run.returncode, 0, run.stdout)
            return
        root = Path(__file__).resolve().parents[1]
        capture = root / "tests" / "fixtures" / "probe-purity-incident-surviving-rows.jsonl.gz"
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            policy = HengbotPolicy()
            policy._character_calibration_path = directory / "character-calibration.json"
            policy._confirmed_loadout_path = directory / "confirmed-loadout.json"
            policy._character_calibration_path.write_bytes(
                (root / "tests" / "fixtures" / "probe-purity-character-calibration.json").read_bytes()
            )
            policy._confirmed_loadout_path.write_bytes(
                (root / "tests" / "fixtures" / "probe-purity-confirmed-loadout.json").read_bytes()
            )
            agreements = []
            stateful_gate = policy._purchase_has_fresh_home_absence

            def agreeing_gate(snapshot, selected):
                pure = policy._evaluate_purchase_home_gate(snapshot, selected)
                stateful = stateful_gate(snapshot, selected)
                agreements.append((pure, stateful))
                return stateful

            policy._purchase_has_fresh_home_absence = agreeing_gate
            reasons = []
            replayed = 0
            final_snapshot = None
            with gzip.open(capture, "rt", encoding="utf-8-sig") as stream:
                for line_number, line in enumerate(stream, 1):
                    raw = json.loads(line)
                    if raw.get("type") in {"player_turn", "store"}:
                        final_snapshot = parse_snapshot(raw)
                        policy.choose_key(final_snapshot)
                        reasons.append(policy.last_reason)
                        replayed += 1

            self.assertEqual(replayed, 2)
            self.assertIsNotNone(final_snapshot)
            self.assertGreater(len(agreements), 0)
            self.assertTrue(all(left is right for left, right in agreements), agreements)
            self.assertFalse(POLICY_FINAL_STOP_REASONS.intersection(reasons))
    def test_probe_records_genuine_block_until_in_store_wait_publishes_it(self):
        ration = store_item("a", TVAL_FOOD, 35, price=1, name="ration")
        snapshot = _supply_test_case("HiddenInfoFallbackTest")._mana_starvation_snapshot(
            store=StoreState(STORE_GENERAL, [ration]), gold=500
        )
        snapshot = replace(
            snapshot,
            town_id=0,
            player=replace(snapshot.player, food_type=0),
        )
        policy = HengbotPolicy()
        policy._decision_sequence = 1
        gate = policy._purchase_has_fresh_home_absence(snapshot, ration)
        self.assertIs(gate, policy_module.ProcurementHomeGate.BLOCKED)
        self.assertNotIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)
        self.assertEqual(
            policy._shop_selector_diagnostics["composition_refusal"],
            "town:blocked:procurement-home-unavailable",
        )
        self.assertEqual(policy._shop(snapshot), WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "town:blocked:procurement-home-unavailable"
        )

    def test_probe_diagnostics_publish_only_when_the_decider_requests_it(self):
        policy = HengbotPolicy()
        policy._decision_sequence = 4
        policy.last_reason = "shop:approach"

        policy._record_purchase_home_refusal(
            "town:blocked:procurement-home-unroutable"
        )
        self.assertEqual(policy.last_reason, "shop:approach")
        policy._publish_purchase_home_block()
        self.assertEqual(
            policy.last_reason, "town:blocked:procurement-home-unroutable"
        )

    def test_ordinary_purchase_wait_publishes_the_genuine_home_block(self):
        oil = store_item("a", TVAL_FLASK, SV_FLASK_OIL, price=3)
        snapshot = _supply_test_case("HiddenInfoFallbackTest")._mana_starvation_snapshot(
            store=StoreState(STORE_GENERAL, [oil]), food=10000, gold=500
        )
        snapshot = replace(
            snapshot,
            town_id=0,
            player=replace(snapshot.player, food_type=0),
        )
        policy = HengbotPolicy()
        policy._deepest_level = 2

        self.assertEqual(policy._shop(snapshot), WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "town:blocked:procurement-home-unavailable"
        )

    def test_pin_vacuity_composer_keeps_the_gate_refusal_for_the_resolver(self):
        fixture = _supply_test_case("QuestCarryVisitAbandonmentTest")
        bolts = store_item("a", TVAL_BOLT, 0, count=99, price=3)
        outside = replace(
            fixture._q2_town(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_WEAPON
                ),
                Position(20, 20): replace(
                    grid(20, 20), store_number=STORE_HOME
                ),
            },
        )
        policy = fixture._q2_policy()
        policy._home_knowledge_current = False
        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON],
            need_categories={STORE_WEAPON: ("quest-ranged-kit",)},
        )
        policy._store_visit = StoreVisit(
            "town-errand",
            "shopping",
            STORE_WEAPON,
            phase=StoreVisitPhase.LEAVING,
        )
        policy._shop_observation = (
            StoreState(STORE_WEAPON, [bolts], page_top=0),
            policy._decision_sequence,
        )

        first_key = policy.choose_key(outside)

        self.assertEqual(
            policy._shop_selector_diagnostics["composition_refusal"],
            "shop:home-first-yields-to-current-visit",
        )
        self.assertNotEqual(first_key, WAIT_KEY)
        second_key = policy.choose_key(replace(outside, turn=outside.turn + 1))
        self.assertNotEqual(
            (policy.last_reason, second_key),
            ("shop:home-first-before-purchase", WAIT_KEY),
        )

    def test_prior_generation_home_first_refusal_yields_at_shared_boundary(self):
        fixture = _supply_test_case("QuestCarryVisitAbandonmentTest")
        bolts = store_item("a", TVAL_BOLT, 0, count=99, price=3)
        outside = replace(
            fixture._q2_town(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_WEAPON
                ),
                Position(20, 20): replace(
                    grid(20, 20), store_number=STORE_HOME
                ),
            },
        )
        policy = fixture._q2_policy()
        policy._decision_sequence = 9
        policy._home_knowledge_current = False
        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON],
            need_categories={STORE_WEAPON: ("quest-ranged-kit",)},
        )
        policy._store_visit = StoreVisit(
            "town-errand",
            "shopping",
            STORE_WEAPON,
            phase=StoreVisitPhase.LEAVING,
        )
        policy._shop_observation = (
            StoreState(STORE_WEAPON, [bolts], page_top=0),
            policy._decision_sequence - 1,
        )

        self.assertIsNone(policy._atomic_shop_transaction_key(outside))
        self.assertEqual(policy._town_errand_plan.index, 1)
        self.assertIsNone(policy._store_visit)

    def test_pin_vacuity_resolver_guard_preserves_the_refused_supplier_stop(self):
        fixture = _supply_test_case("QuestCarryVisitAbandonmentTest")
        bolts = store_item("a", TVAL_BOLT, 0, count=99, price=3)
        inside = replace(
            fixture._q2_town(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_WEAPON
                ),
                Position(20, 20): replace(
                    grid(20, 20), store_number=STORE_HOME
                ),
            },
        )
        policy = fixture._q2_policy()
        policy._home_knowledge_current = False
        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON],
            need_categories={STORE_WEAPON: ("quest-ranged-kit",)},
        )
        policy._shopping_approach_store_type = STORE_WEAPON
        policy._shop_observation = (
            StoreState(STORE_WEAPON, [bolts], page_top=0),
            policy._decision_sequence,
        )

        self.assertTrue(policy._resolve_observed_uncomposable_stop(inside))
        self.assertEqual(policy._town_errand_plan.index, 0)
        self.assertNotIn(STORE_WEAPON, policy._town_errand_plan.blocked_this_visit)

    def test_discarded_composer_wait_revokes_the_published_terminal(self):
        fixture = _supply_test_case("QuestCarryVisitAbandonmentTest")
        bolts = store_item("a", TVAL_BOLT, 0, count=99, price=3)
        outside = replace(
            fixture._q2_town(),
            town_id=0,
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_WEAPON
                ),
            },
        )
        policy = fixture._q2_policy()
        policy.last_reason = "town:shopping-approach"
        policy._home_knowledge_current = False
        policy._shop_observation = (
            StoreState(STORE_WEAPON, [bolts], page_top=0),
            policy._decision_sequence,
        )
        policy._resolve_observed_uncomposable_stop = lambda _snapshot: False

        self.assertIsNone(policy._atomic_shop_transaction_key(outside))
        self.assertEqual(policy.last_reason, "town:shopping-approach")
        self.assertNotIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_unroutable_probe_does_not_publish_the_incident_terminal(self):
        ration = store_item("a", TVAL_FOOD, 35, price=1, name="ration")
        snapshot = _supply_test_case("HiddenInfoFallbackTest")._mana_starvation_snapshot(
            store=StoreState(STORE_GENERAL, [ration]), gold=500
        )
        snapshot = replace(
            snapshot,
            town_id=1,
            player=replace(snapshot.player, food_type=0),
            grids={
                **snapshot.grids,
                Position(30, 30): replace(
                    grid(30, 30), store_number=STORE_HOME
                ),
            },
        )
        policy = HengbotPolicy()
        policy._decision_sequence = 7
        policy._town_blocked_reason = "genuinely-unroutable"
        policy.last_reason = "shop:probe-start"

        self.assertIs(
            policy._purchase_has_fresh_home_absence(snapshot, ration),
            policy_module.ProcurementHomeGate.BLOCKED,
        )
        self.assertEqual(policy.last_reason, "shop:probe-start")
        self.assertEqual(
            policy._shop_selector_diagnostics["composition_refusal"],
            "town:blocked:procurement-home-unroutable",
        )

    def test_pure_and_stateful_home_gate_matrix_agree_on_all_outcomes(self):
        ration = store_item("a", TVAL_FOOD, 35, price=1, name="ration")
        base = _supply_test_case("HiddenInfoFallbackTest")._mana_starvation_snapshot(
            store=StoreState(STORE_GENERAL, [ration]), gold=500
        )
        base = replace(base, player=replace(base.player, food_type=0))

        def classify(policy, snapshot):
            pure = policy._evaluate_purchase_home_gate(snapshot, ration)
            stateful = policy._purchase_has_fresh_home_absence(snapshot, ration)
            self.assertIs(pure, stateful)
            return pure

        no_home = replace(base, town_id=policy_module.ZUL_TOWN_ID)
        self.assertIs(
            classify(HengbotPolicy(), no_home),
            policy_module.ProcurementHomeGate.ALLOW_PURCHASE,
        )

        fresh = HengbotPolicy()
        fresh._home_knowledge_current = True
        self.assertIs(
            classify(fresh, replace(base, town_id=1)),
            policy_module.ProcurementHomeGate.ALLOW_PURCHASE,
        )

        routed = HengbotPolicy()
        routed_snapshot = replace(
            base,
            town_id=1,
            grids={
                **base.grids,
                Position(30, 30): replace(
                    grid(30, 30), store_number=STORE_HOME
                ),
            },
        )
        self.assertIs(
            classify(routed, routed_snapshot),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )

        vetoed = HengbotPolicy()
        vetoed._store_visit = StoreVisit(
            "town-errand", "shopping", STORE_WEAPON
        )
        self.assertIs(
            classify(vetoed, routed_snapshot),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )

        unroutable = HengbotPolicy()
        unroutable._town_blocked_reason = "genuinely-unroutable"
        self.assertIs(
            classify(unroutable, routed_snapshot),
            policy_module.ProcurementHomeGate.BLOCKED,
        )

        self.assertIs(
            classify(HengbotPolicy(), replace(base, town_id=0)),
            policy_module.ProcurementHomeGate.BLOCKED,
        )

class OptionalBlackMarketPotionTest(unittest.TestCase):
    def _supplies(self):
        return [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=3),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL),
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
        ]

    def _town(self, *, inventory=None, store=None, gold=10000):
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory if inventory is not None else self._supplies(),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
            store=store,
        )

    def test_black_market_is_checked_once_per_town_visit(self):
        policy = HengbotPolicy()
        snapshot = self._town()

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_BLACK)
        policy._town_store_attempted[STORE_BLACK] = 0
        self.assertIsNone(policy._next_required_store_type(snapshot))

    def test_existing_stockpile_does_not_cap_black_market_purchases(self):
        inventory = [
            *self._supplies(),
            item("s", TVAL_POTION, SV_POTION_SPEED, count=20),
            item("h", TVAL_POTION, SV_POTION_HEALING, count=20),
        ]
        wares = [
            store_item("a", TVAL_POTION, SV_POTION_SPEED, price=1000, count=5),
            store_item("b", TVAL_POTION, SV_POTION_HEALING, price=1000, count=5),
        ]
        policy = HengbotPolicy()
        town = self._town(
            inventory=inventory,
            store=StoreState(STORE_BLACK, wares),
            gold=10000,
        )

        self.assertEqual(policy._next_required_store_type(replace(town, store=None)), STORE_BLACK)
        purchase = policy._next_purchase(town)
        self.assertIsNotNone(purchase)
        self.assertEqual(policy._purchase_quantity(town, purchase), 1)

    def test_speed_and_healing_surplus_is_deposited_to_carry_ten(self):
        speed = item("s", TVAL_POTION, SV_POTION_SPEED, count=21)
        healing = item("h", TVAL_POTION, SV_POTION_HEALING, count=12)
        policy = HengbotPolicy()
        town = self._town(inventory=[*self._supplies(), speed, healing])

        self.assertEqual(policy._retention_reservation(town, speed), 10)
        self.assertEqual(policy._retention_surplus(town, speed), 11)
        self.assertTrue(policy._home_deposit_candidate(speed, town))
        self.assertEqual(policy._home_deposit_key(town, speed), "ds11\r")
        self.assertEqual(policy._retention_reservation(town, healing), 10)
        self.assertEqual(policy._retention_surplus(town, healing), 2)
        self.assertTrue(policy._home_deposit_candidate(healing, town))
        self.assertEqual(policy._home_deposit_key(town, healing), "dh2\r")

    def test_black_market_balances_toward_less_held_kind(self):
        inventory = [
            *self._supplies(),
            item("s", TVAL_POTION, SV_POTION_SPEED, count=10),
            item("h", TVAL_POTION, SV_POTION_HEALING, count=9),
        ]
        wares = [
            store_item("a", TVAL_POTION, SV_POTION_SPEED, price=1000, count=5),
            store_item("b", TVAL_POTION, SV_POTION_HEALING, price=1000, count=5),
        ]
        policy = HengbotPolicy()
        town = self._town(
            inventory=inventory,
            store=StoreState(STORE_BLACK, wares),
            gold=10000,
        )

        self.assertEqual(policy._next_purchase(town).sval, SV_POTION_HEALING)
        self.assertEqual(
            policy._purchase_quantity(town, policy._next_purchase(town)), 1
        )

    def test_newly_bought_potion_surplus_is_not_protected_from_home(self):
        speed = item("s", TVAL_POTION, SV_POTION_SPEED, count=11)
        policy = HengbotPolicy()
        town = self._town(inventory=[*self._supplies(), speed])
        policy._town_visit_purchases.add(policy._item_signature(speed))

        self.assertEqual(policy._retention_reservation(town, speed), 10)
        self.assertTrue(policy._home_deposit_candidate(speed, town))
        self.assertEqual(policy._home_deposit_key(town, speed), "ds")

    def test_buys_one_speed_then_one_healing_when_affordable(self):
        wares = [
            store_item("a", TVAL_POTION, SV_POTION_SPEED, price=5000),
            store_item("b", TVAL_POTION, SV_POTION_HEALING, price=6000),
        ]
        policy = HengbotPolicy()
        first = self._town(store=StoreState(STORE_BLACK, wares), gold=10000)
        self.assertEqual(policy._next_purchase(first).sval, SV_POTION_SPEED)

        second = self._town(
            inventory=[
                *self._supplies(),
                item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
                item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
                item("s", TVAL_POTION, SV_POTION_SPEED),
            ],
            store=StoreState(STORE_BLACK, wares),
            gold=6000,
        )
        self.assertEqual(policy._next_purchase(second).sval, SV_POTION_HEALING)

    def test_keeps_buying_the_remaining_type_until_funds_or_stock_run_out(self):
        policy = HengbotPolicy()
        stocked = self._town(
            inventory=[
                *self._supplies(),
                item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
                item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
                item("s", TVAL_POTION, SV_POTION_SPEED, count=3),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=2),
            ],
            store=StoreState(
                STORE_BLACK,
                [store_item("b", TVAL_POTION, SV_POTION_HEALING, price=500, count=4)],
            ),
            gold=500,
        )
        self.assertEqual(policy._next_purchase(stocked).sval, SV_POTION_HEALING)

        out_of_funds = replace(stocked, player=replace(stocked.player, gold=499))
        self.assertIsNone(policy._next_purchase(out_of_funds))

    def test_unaffordable_stock_does_not_block_departure(self):
        policy = HengbotPolicy()
        snapshot = self._town(
            store=StoreState(
                STORE_BLACK,
                [store_item("a", TVAL_POTION, SV_POTION_SPEED, price=5000)],
            ),
            gold=4999,
        )

        self.assertIsNone(policy._next_purchase(snapshot))
        policy._town_store_attempted[STORE_BLACK] = 0
        self.assertIsNone(policy._next_required_store_type(snapshot))

class StoreTravelRetryTest(unittest.TestCase):
    """Store/Home travel used to be one-shot: any interruption latched a walking
    fallback and the rest of the leg went one decision per tile. It now shares
    the progress-based gate with the entrance leg — re-issue while getting
    closer, walk only after TOWN_TRAVEL_STALL_LIMIT no-progress issues."""

    @staticmethod
    def _snap(x, turn=0, *, goal_remembered=True):
        grids = {Position(34, x): grid(34, x)}
        if goal_remembered:
            grids[Position(34, 130)] = grid(34, 130)
        return Snapshot(
            player(34, x),
            grids,
            [],
            floor_key=(0, 0, 0),
            turn=turn,
            inventory=[],
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

    @staticmethod
    def _approach(pol, snap):
        pol._shopping_approach_goal = Position(34, 130)
        pol._shopping_approach_store_type = 4
        return pol._shopping_approach_key(snap, Position(34, 95), "shop:travel")

    def test_travel_reissues_after_progress(self):
        pol = HengbotPolicy()
        self.assertEqual(self._approach(pol, self._snap(94)), "\x1b`n%.")
        # Interrupted mid-route but closer than before: travel again.
        self.assertEqual(self._approach(pol, self._snap(110)), "\x1b`n%.")

    def test_remembered_store_symbols_keep_byte_identical_travel_macros(self):
        snap = self._snap(94)
        for store_type, expected in (
            (STORE_ALCHEMIST, "\x1b`n%."),
            (STORE_TEMPLE, "\x1b`n$."),
        ):
            with self.subTest(store_type=store_type):
                pol = HengbotPolicy()
                pol._shopping_approach_goal = Position(34, 130)
                pol._shopping_approach_store_type = store_type
                self.assertEqual(
                    pol._shopping_approach_key(
                        snap, Position(34, 95), "shop:travel"
                    ),
                    expected,
                )

    def test_native_store_travel_owns_lagged_entry_observation(self):
        pol = HengbotPolicy()
        approach = self._approach(pol, self._snap(94))
        self.assertEqual(approach, "\x1b`n%.")
        self.assertTrue(pol.confirm_key_posted(approach))

        lagged_surface = self._snap(130, turn=1)
        self.assertEqual(pol.choose_key(lagged_surface), "")
        self.assertEqual(pol.last_reason, "store:entry-await-observation")

    def test_frozen_home_whiff_falls_back_after_two_followup_decisions(self):
        self.skipTest(
            "source artifact destroyed 2026-08-17; rebuild from a future capture"
        )
        artifact = Path("evidence/evidence-travel-whiff-snapshots.jsonl")
        raw = json.loads(artifact.read_text(encoding="utf-8").splitlines()[0])
        snap = parse_snapshot(raw, {})
        goal = Position(45, 123)
        self.assertEqual(snap.turn, 4684095)
        self.assertEqual(snap.player.position, Position(47, 110))
        self.assertEqual(snap.grids[goal].store_number, STORE_HOME)

        pol = HengbotPolicy()
        pol._shopping_approach_goal = goal
        pol._shopping_approach_store_type = STORE_HOME
        first = pol._shopping_approach_key(snap, goal, "shop:travel")
        decisions = [first]
        self.assertEqual(first, "\x1b`n(.")
        self.assertTrue(pol.confirm_key_posted(first))

        decisions.append(pol.choose_key(snap))
        self.assertEqual(decisions[-1], "")
        self.assertEqual(pol.last_reason, "store:entry-await-observation")
        self.assertEqual(pol._town_travel_fallback, goal)
        decisions.append(
            pol._shopping_approach_key(snap, goal, "shop:travel")
        )
        self.assertEqual(decisions[-1], "9")

        # Macro issue, lagged/recovery observation, then BFS: two follow-up
        # decisions instead of the measured eight no-progress allowances.
        self.assertEqual(len(decisions), 3)

    def test_unremembered_static_store_goal_walks_without_recording_issue(self):
        pol = HengbotPolicy()
        snap = self._snap(94, goal_remembered=False)
        pol.last_reason = "shop:approach"

        self.assertEqual(self._approach(pol, snap), "6")
        self.assertEqual(pol.last_reason, "shop:approach")
        self.assertIsNone(pol._town_travel_state)

    def test_store_travel_engages_after_walk_reveals_goal(self):
        pol = HengbotPolicy()
        self.assertEqual(
            self._approach(pol, self._snap(94, goal_remembered=False)), "6"
        )
        self.assertIsNone(pol._town_travel_state)

        self.assertEqual(self._approach(pol, self._snap(95)), "\x1b`n%.")
        self.assertEqual(pol.last_reason, "shop:travel")

    def test_unchanged_travel_observation_falls_back_to_walking(self):
        pol = HengbotPolicy()
        snap = self._snap(94, turn=1)
        self.assertEqual(self._approach(pol, snap), "\x1b`n%.")
        self.assertEqual(self._approach(pol, snap), "6")
        self.assertEqual(pol._town_travel_fallback, Position(34, 130))

class StatRestoreTest(unittest.TestCase):
    """Drained-stat recovery: quaff a carried Restore-* potion when safe, and when
    none is carried route to the Alchemist and buy the matching potion."""

    def _snap(self, *, inventory=(), store=None, drained=(), hostiles=()):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=2000, drained_stats=drained),
            {Position(10, 10): grid(10, 10)},
            list(hostiles),
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            store=store,
        )

    def test_quaffs_a_carried_restore_potion_for_the_drained_stat(self):
        inv = [
            item("a", TVAL_POTION, SV_POTION_RESTORE_CON, name="Restore Con"),
            item("b", TVAL_POTION, SV_POTION_RESTORE_STR, name="Restore Str"),
        ]
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, drained=("str",))
        self.assertEqual(pol._stat_restore_quaff_key(snap, []), "qb")
        self.assertEqual(pol.last_reason, "restore:quaff-str")

    def test_no_quaff_while_hostiles_are_present(self):
        inv = [item("b", TVAL_POTION, SV_POTION_RESTORE_STR)]
        hostile = MonsterState(
            index=1, position=Position(9, 10), hp=10, max_hp=10, distance=1,
            friendly=False, pet=False, speed=110,
        )
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, drained=("str",), hostiles=[hostile])
        self.assertIsNone(pol._stat_restore_quaff_key(snap, [hostile]))

    def test_ignores_unaware_restore_potions(self):
        # Fair-play: an unidentified potion has no emitted sval, so it is not yet
        # actionable even if it happens to be a restore potion.
        inv = [item("b", TVAL_POTION, SV_POTION_RESTORE_STR, aware=False)]
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, drained=("str",))
        self.assertIsNone(pol._stat_restore_quaff_key(snap, []))

    def test_needs_restore_routes_to_the_alchemist(self):
        pol = HengbotPolicy()
        snap = self._snap(drained=("con",))
        self.assertTrue(pol._needs_stat_restore(snap))
        # Poverty now activates fundraising before ordinary stat restoration,
        # securing the income kit at Home first; the restore errand remains in
        # the same batched plan.
        self.assertEqual(pol._next_required_store_type(snap), STORE_HOME)
        self.assertIn(STORE_ALCHEMIST, pol._town_errand_plan.stops)

    def test_carrying_the_potion_removes_the_alchemist_errand(self):
        inv = [item("a", TVAL_POTION, SV_POTION_RESTORE_CON)]
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, drained=("con",))
        self.assertFalse(pol._needs_stat_restore(snap))

    def test_buys_the_matching_restore_potion_at_the_alchemist(self):
        store = StoreState(
            store_type=STORE_ALCHEMIST,
            items=[
                store_item("h", TVAL_POTION, SV_POTION_RESTORE_STR, price=300, name="Restore Str"),
                store_item("i", TVAL_POTION, SV_POTION_RESTORE_CON, price=300, name="Restore Con"),
            ],
        )
        pol = HengbotPolicy()
        snap = self._snap(store=store, drained=("con",))
        bought = pol._restore_potion_purchase(snap)
        self.assertIsNotNone(bought)
        self.assertEqual(bought.sval, SV_POTION_RESTORE_CON)

    def test_does_not_rebuy_a_restore_potion_already_carried(self):
        store = StoreState(
            store_type=STORE_ALCHEMIST,
            items=[store_item("i", TVAL_POTION, SV_POTION_RESTORE_CON, price=300)],
        )
        inv = [item("a", TVAL_POTION, SV_POTION_RESTORE_CON)]
        pol = HengbotPolicy()
        snap = self._snap(inventory=inv, store=store, drained=("con",))
        self.assertIsNone(pol._restore_potion_purchase(snap))

class ScavengeStoreLatchTest(unittest.TestCase):
    """Leaving the Alchemist with nothing to sell used to flip scavenge->prepare
    AND blanket-clear _town_store_attempted. With unchanged gold the router then
    re-picked the same out-of-stock stores — an Alchemist<->Magic native-travel
    ping-pong the loop guard cannot see (store snapshots reset it and travel
    keeps the position changing). The latches may only be re-checked when the
    scavenge pass actually raised gold."""

    def _alchemist_snapshot(self, gold):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=gold),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[],
            store=StoreState(store_type=STORE_ALCHEMIST, items=[]),
        )

    def _scavenging_policy(self, entry_gold):
        pol = HengbotPolicy()
        pol._fundraising_mode = "scavenge"
        pol._scavenge_entry_gold = entry_gold
        pol._town_store_attempted = {STORE_ALCHEMIST: 100, STORE_GENERAL: 100}
        return pol

    def test_no_sale_keeps_the_store_latches(self):
        pol = self._scavenging_policy(entry_gold=376)
        key = pol._shop(self._alchemist_snapshot(gold=376))
        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(pol._fundraising_mode, "prepare")
        self.assertIn(STORE_GENERAL, pol._town_store_attempted)

    def test_raised_gold_rechecks_the_stores(self):
        pol = self._scavenging_policy(entry_gold=376)
        pol._shop(self._alchemist_snapshot(gold=900))
        self.assertEqual(pol._fundraising_mode, "prepare")
        self.assertNotIn(STORE_GENERAL, pol._town_store_attempted)

class StoreAttemptExpiryTest(unittest.TestCase):
    """A store visited once with nothing to buy/sell latches into
    _town_store_attempted (a dict of store_type -> the game turn it was
    latched at) for the rest of the town stay. The only OTHER reset is the
    fresh-town-visit reset in _observe, which never runs if the bot never
    departs -- during the 2026-07-15 incident's 2-hour town stay, supplies
    (oil, teleport scrolls) kept draining with no store ever re-attempted.
    Each latch now also expires on its own schedule during ordinary in-town
    _observe ticks, independent of any floor change."""

    def _town(self, turn):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=turn,
        )

    def _already_in_town_policy(self):
        # Prime _floor_key to (0, 0, 0) so the fresh-town-visit reset (a
        # SEPARATE mechanism, exercised by its own test below) does not also
        # clear _town_store_attempted and confound what is being isolated here.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        return pol

    def test_latch_is_still_skipped_just_before_the_retry_window(self):
        pol = self._already_in_town_policy()
        pol._town_store_attempted[STORE_GENERAL] = 1000

        pol._observe(self._town(1000 + STORE_RETRY_TURNS - 1))  # T+4999

        self.assertIn(STORE_GENERAL, pol._town_store_attempted)

    def test_latch_expires_just_after_the_retry_window(self):
        pol = self._already_in_town_policy()
        pol._town_store_attempted[STORE_GENERAL] = 1000

        pol._observe(self._town(1000 + STORE_RETRY_TURNS + 1))  # T+5001

        self.assertNotIn(STORE_GENERAL, pol._town_store_attempted)

    def test_only_the_individually_expired_store_is_dropped(self):
        pol = self._already_in_town_policy()
        pol._town_store_attempted[STORE_GENERAL] = 1000
        pol._town_store_attempted[STORE_ALCHEMIST] = 1000 + STORE_RETRY_TURNS

        pol._observe(self._town(1000 + STORE_RETRY_TURNS + 1))

        self.assertNotIn(STORE_GENERAL, pol._town_store_attempted)
        self.assertIn(STORE_ALCHEMIST, pol._town_store_attempted)

    def test_fresh_town_visit_still_clears_every_latch(self):
        pol = HengbotPolicy()
        pol._town_store_attempted[STORE_GENERAL] = 1000
        pol._town_store_attempted[STORE_ALCHEMIST] = 1000
        pol._floor_key = (1, 5, 0)  # was in the dungeon last observation

        pol._observe(self._town(1050))  # arriving back at town: a floor change

        self.assertEqual(pol._town_store_attempted, {})
