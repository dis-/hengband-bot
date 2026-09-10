from __future__ import annotations
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
import hengbot.policy as policy_module
import hengbot.equipment_mutation as equipment_mutation_module
import test_policy as fixture
from test_policy import FOOD, REAL_QUEST_DEFINITIONS
from hengbot.policy import FOOD_TYPE_MANA
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
try:
    from trajectory_harness import drive_trajectory
except ModuleNotFoundError:
    from tests.trajectory_harness import drive_trajectory
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

class MiningGearHomeStorageTest(unittest.TestCase):
    """Treasure Detection scrolls and digging tools ride along only while
    fundraising (mining level 1); on a normal diving run they are stashed at
    home rather than hauled down as dead weight."""

    def test_deposited_when_not_fundraising(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = None
        self.assertTrue(
            pol._home_deposit_candidate(item("b", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE))
        )
        self.assertTrue(
            pol._home_deposit_candidate(item("b", TVAL_DIGGING, SV_DIGGING_SHOVEL))
        )

    def test_kept_while_fundraising(self):
        pol = HengbotPolicy()
        for mode in ("prepare", "mine", "scavenge"):
            pol._fundraising_mode = mode
            self.assertFalse(
                pol._home_deposit_candidate(item("b", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)),
                f"treasure scroll should be kept in {mode}",
            )
            self.assertFalse(
                pol._home_deposit_candidate(item("b", TVAL_DIGGING, SV_DIGGING_SHOVEL)),
                f"digger should be kept in {mode}",
            )

class WeightOverloadTownTest(unittest.TestCase):
    def _recorded_pre_ammo_purchase(self):
        actor = replace(
            player(31, 119, class_id=PLAYER_CLASS_WARRIOR, gold=15039),
            stat_index=(26, 0, 0, 0, 0, 0),
        )
        equipment = [
            replace(item("main_hand", 23, 17, is_equipment=True), weight=130),
            replace(item("bow", TVAL_BOW, 23, is_equipment=True), weight=110),
            replace(item("main_ring", 45, 8, is_equipment=True), weight=2),
            replace(item("sub_ring", 45, 38, is_equipment=True), weight=2),
            replace(item("light", 39, 1, is_equipment=True), weight=50),
            replace(item("body", 37, 4, is_equipment=True), weight=220),
            replace(item("outer", 35, 1, is_equipment=True), weight=10),
        ]
        inventory = [
            replace(item("a", 77, 0, count=12), weight=10),
            replace(item("b", 75, 29, count=6), weight=4),
            replace(item("c", 75, 30), weight=4),
            replace(item("d", 75, 36, count=10), weight=4),
            replace(item("e", 75, 37, count=4), weight=4),
            replace(item("f", TVAL_SCROLL, 8), weight=5),
            replace(
                item("g", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=45), weight=5
            ),
            replace(
                item("h", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=27),
                weight=5,
            ),
            replace(item("i", TVAL_SCROLL, 24, count=6), weight=5),
            replace(
                item("j", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=6),
                weight=5,
            ),
            replace(item("k", TVAL_ROD, 0, known=False), weight=15),
            replace(item("l", TVAL_WAND, 7), weight=10),
            replace(item("m", TVAL_STAFF, 5), weight=50),
            replace(item("n", TVAL_STAFF, 5), weight=50),
            replace(
                item("o", TVAL_SOFT_ARMOR, 0, is_equipment=True, known=False),
                weight=10,
            ),
            replace(
                item(
                    "p", TVAL_DIGGING, SV_DIGGING_SHOVEL, count=2,
                    is_equipment=True,
                ),
                weight=60,
            ),
            replace(item("q", TVAL_BOLT, 1, count=71), weight=3),
        ]
        bolts = replace(
            # Non-Home StoreItem weight is absent from production JSON.  This
            # fixture value is inert now that purchase-side weight refusal has
            # been removed; it remains only to preserve the recorded magnitude.
            store_item("n", TVAL_BOLT, 1, count=99, price=3), weight=3
        )
        return Snapshot(
            actor,
            {Position(31, 119): replace(grid(31, 119), store_number=STORE_GENERAL)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            equipment=equipment,
            store=StoreState(STORE_GENERAL, [bolts]),
        )

    def test_overweight_still_buys_departure_blocking_recall(self):
        snapshot = self._recorded_pre_ammo_purchase()
        recall = replace(
            store_item(
                "n", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                count=99, price=100,
            ),
            weight=5,
        )
        inventory = list(snapshot.inventory)
        inventory[7] = replace(inventory[7], count=0)
        inventory.append(
            replace(item("r", 9, 0, name="heavy statue"), weight=200)
        )
        snapshot = replace(
            snapshot,
            inventory=inventory,
            grids={
                snapshot.player.position: replace(
                    snapshot.grids[snapshot.player.position],
                    store_number=STORE_ALCHEMIST,
                )
            },
            store=StoreState(STORE_ALCHEMIST, [recall]),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._inventory_weight(snapshot), 1691)
        self.assertEqual(policy._inventory_weight_limit(snapshot), 1650)
        with (
            patch.object(policy, "_batch_sell_key", return_value=None),
            patch.object(policy, "_find_low_level_sale", return_value=None),
        ):
            key = policy._shop(snapshot)

        self.assertEqual(key, "pn3\r\r")
        self.assertEqual(policy.last_reason, "shop:buy-recall")

    def test_required_recall_purchase_may_newly_create_overload(self):
        snapshot = self._recorded_pre_ammo_purchase()
        recall = replace(
            store_item(
                "n", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                count=99, price=100,
            ),
            weight=10,
        )
        inventory = [
            replace(item, count=0) if item.slot == "h" else item
            for item in snapshot.inventory
        ]
        inventory.append(
            replace(item("r", 9, 0, name="recorded ballast"), weight=130)
        )
        snapshot = replace(
            snapshot,
            inventory=inventory,
            grids={
                snapshot.player.position: replace(
                    snapshot.grids[snapshot.player.position],
                    store_number=STORE_ALCHEMIST,
                )
            },
            store=StoreState(STORE_ALCHEMIST, [recall]),
        )
        policy = HengbotPolicy()

        current_weight = policy._inventory_weight(snapshot)
        limit = policy._inventory_weight_limit(snapshot)
        self.assertEqual((current_weight, limit), (1621, 1650))
        self.assertEqual(current_weight + recall.weight * 3, 1651)
        with (
            patch.object(policy, "_batch_sell_key", return_value=None),
            patch.object(policy, "_find_low_level_sale", return_value=None),
        ):
            key = policy._shop(snapshot)

        self.assertEqual(key, "pn3\r\r")
        self.assertEqual(policy.last_reason, "shop:buy-recall")

    def _snapshot(self):
        strength_18_180 = (33, 0, 0, 0, 0, 0)
        actor = replace(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=5000),
            stat_index=strength_18_180,
        )
        launcher = replace(
            item("bow", TVAL_BOW, 23, is_equipment=True),
            weight=110,
        )
        armour = replace(
            item("body", 33, 1, is_equipment=True), weight=996
        )
        inventory = [
            replace(item("a", 9, 0, name="heavy statue"), weight=200),
            replace(item("o", TVAL_BOLT, 1, count=99), weight=3),
            replace(item("p", TVAL_BOLT, 1, count=35), weight=3),
            replace(item("q", TVAL_BOLT, 1, count=27), weight=3),
            replace(
                item("n", 23, 25, name="reward sword", is_equipment=True),
                weight=200,
            ),
            replace(
                item("r", 10, 0, name="wanted remains", is_bounty=True),
                weight=435,
            ),
        ]
        home = replace(grid(10, 11), store_number=STORE_HOME)
        return Snapshot(
            actor,
            {Position(10, 10): grid(10, 10), Position(10, 11): home},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            inventory=inventory,
            equipment=[launcher, armour],
            quests={
                31: QuestState(
                    31, status=QUEST_STATUS_UNTAKEN, fixed=True, level=25
                )
            },
        )

    def test_matches_game_weight_limit_and_preserves_one_ammo_stack(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy(
            quest_strategies=load_quest_strategies(Path("strategy/quests"))
        )

        self.assertEqual(policy._inventory_weight(snapshot), 2424)
        self.assertEqual(policy._inventory_weight_limit(snapshot), 1850)
        self.assertTrue(policy._inventory_overweight(snapshot))
        self.assertEqual(
            [policy._retention_reservation(snapshot, item) for item in snapshot.inventory[1:4]],
            [99, 0, 0],
        )
        self.assertEqual(
            policy.approved_quest_strategy(31).required_force["throwing_items"]["launcher_ammo"],
            99,
        )

    def test_overweight_routes_noncombat_bulk_to_home_first(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()

        self.assertEqual(policy._find_home_deposit(snapshot).slot, "a")
        self.assertTrue(
            any(
                need.store_type == STORE_HOME and need.category == "weight-overload"
                for need in policy._enumerate_town_needs(snapshot)
            )
        )

    def test_dead_home_full_capture_value_cannot_drain_overweight_work(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()
        # Older checkpoints may still deserialize this dead historical field.
        policy._home_full = True

        selected = policy._find_home_deposit(snapshot)

        self.assertEqual(selected.slot, "a")
        self.assertEqual(selected.name, "heavy statue")

    def test_recorded_overweight_deposits_required_surplus_in_one_visit(self):
        actor = replace(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=5000),
            stat_index=(25, 0, 0, 0, 0, 0),
        )
        teleport = replace(
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=45), weight=5
        )
        recall = replace(
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=27), weight=5
        )
        rod = replace(item("d", TVAL_ROD, 1, name="unidentified rod"), weight=15)
        ballast = replace(
            item("body", 33, 1, is_equipment=True), weight=1330
        )
        snapshot = Snapshot(
            actor,
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[teleport, recall, rod],
            equipment=[ballast],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._inventory_weight(snapshot), 1705)
        self.assertEqual(policy._inventory_weight_limit(snapshot), 1650)
        self.assertEqual(policy._planned_depth(), 1)
        self.assertEqual(policy._retention_surplus(snapshot, teleport), 44)
        self.assertEqual(policy._retention_surplus(snapshot, recall), 24)

        selected = policy._overweight_home_deposit(snapshot)
        self.assertEqual(selected, teleport)  # Wrong-value pin: never the 15-weight rod.
        quantity = policy._retention_surplus(snapshot, selected)
        self.assertEqual(quantity, 44)
        operation = policy._home_deposit_key(snapshot, selected)
        self.assertEqual(operation, "dt44\r")
        deposited_quantity = int(operation[2:-1])
        self.assertLessEqual(
            deposited_quantity, policy._retention_surplus(snapshot, selected)
        )
        self.assertEqual(selected.count - deposited_quantity, 1)
        resulting_weight = (
            policy._inventory_weight(snapshot) - selected.weight * deposited_quantity
        )
        self.assertEqual(resulting_weight, 1485)
        self.assertLessEqual(resulting_weight, policy._inventory_weight_limit(snapshot))

    def test_live_pack_rejections_never_select_unreserved_blocking_supply(self):
        """Turn 1367066, live row 6399: reject exactly g, h, then a."""
        snapshot = self._recorded_pre_ammo_purchase()
        snapshot = replace(
            snapshot,
            inventory=[
                replace(item, count=99) if item.slot == "q" else item
                for item in snapshot.inventory
            ],
        )
        policy = HengbotPolicy()
        by_slot = {item.slot: item for item in snapshot.inventory}
        policy._home_rejected_deposits.update(
            policy._item_signature(by_slot[slot]) for slot in ("g", "h", "a")
        )
        blocking_categories = {
            spec.category
            for spec in policy._town_need_registry()
            if spec.departure_blocking
        }

        selected_slots = []
        while (selected := policy._overweight_home_deposit(snapshot)) is not None:
            selected_slots.append(selected.slot)
            selected_categories = set(
                policy._cross_town_item_categories(selected)
            )
            self.assertFalse(
                selected_categories & blocking_categories
                and policy._retention_reservation(snapshot, selected) == 0,
                (selected.slot, selected_categories),
            )
            policy._home_rejected_deposits.add(policy._item_signature(selected))

        self.assertEqual(selected_slots[0], "d")

    def test_suffixed_categories_are_required_by_overweight_predicate(self):
        snapshot = self._recorded_pre_ammo_purchase()
        identify = replace(
            item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify"), weight=5
        )
        restore = replace(
            item(
                "b", TVAL_POTION, SV_POTION_RESTORE_STR,
                count=4, name="Restore Str",
            ),
            weight=4,
        )
        snapshot = replace(
            snapshot,
            inventory=[identify, restore],
            equipment=[
                replace(
                    item("body", 37, 4, is_equipment=True), weight=1700
                )
            ],
        )
        policy = HengbotPolicy()

        self.assertEqual(
            policy._cross_town_item_categories(identify),
            ("identification-source:normal",),
        )
        self.assertEqual(
            policy._cross_town_item_categories(restore),
            ("stat-restore:str",),
        )
        self.assertEqual(policy._retention_reservation(snapshot, identify), 0)
        self.assertEqual(policy._retention_reservation(snapshot, restore), 0)
        self.assertEqual(policy._retention_surplus(snapshot, identify), 1)
        self.assertEqual(policy._retention_surplus(snapshot, restore), 4)
        self.assertIsNone(policy._overweight_home_deposit(snapshot))

    def test_home_attempt_latch_does_not_suppress_reducible_overweight(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_HOME] = snapshot.turn

        self.assertTrue(policy._home_available(snapshot))
        self.assertTrue(policy._inventory_overweight(snapshot))
        self.assertIsNotNone(policy._find_home_deposit(snapshot))
        self.assertTrue(
            any(
                need.store_type == STORE_HOME
                and need.category == "weight-overload"
                for need in policy._enumerate_town_needs(snapshot)
            )
        )

        while (candidate := policy._overweight_home_deposit(snapshot)) is not None:
            policy._home_rejected_deposits.add(policy._item_signature(candidate))

        self.assertFalse(
            any(
                need.store_type == STORE_HOME
                and need.category == "weight-overload"
                for need in policy._enumerate_town_needs(snapshot)
            )
        )

    def test_overweight_rearm_tracks_successful_deposit_progress_to_weight_limit(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_HOME] = snapshot.turn
        passes = 0

        while policy._inventory_overweight(snapshot):
            needs = policy._enumerate_town_needs(snapshot)
            self.assertTrue(any(
                need.store_type == STORE_HOME
                and need.category == "weight-overload"
                for need in needs
            ))
            candidate = policy._overweight_home_deposit(snapshot)
            self.assertIsNotNone(candidate)
            count = policy._retention_surplus(snapshot, candidate)
            inventory = [
                replace(item, count=item.count - count)
                if item.slot == candidate.slot and item.count > count
                else item
                for item in snapshot.inventory
                if item.slot != candidate.slot or item.count > count
            ]
            progressed = replace(snapshot, inventory=inventory)
            self.assertLess(
                policy._inventory_weight(progressed),
                policy._inventory_weight(snapshot),
            )
            snapshot = progressed
            passes += 1

        self.assertEqual(passes, 4)
        self.assertFalse(any(
            need.category == "weight-overload"
            for need in policy._enumerate_town_needs(snapshot)
        ))

    def test_overweight_home_approach_exhaustion_names_visible_terminal(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=None
        )
        limit = policy._town_store_visit_limit(STORE_HOME)
        observations = []

        with patch.object(policy, "_outstanding_equipment_work", return_value=False):
            for fails in range(limit + 1):
                policy._town_visit_ledger.approach_fails[STORE_HOME] = fails
                policy._town_claims_active(snapshot)
                observations.append(
                    (fails, "weight-overload" in policy._town_claim_categories,
                     policy._town_blocked_reason)
                )

        self.assertEqual(limit, 3)
        self.assertEqual(
            observations,
            [
                (0, True, None),
                (1, True, None),
                (2, True, None),
                (3, False, "overweight-home-unreachable"),
            ],
        )

    def test_combat_breaks_continuous_home_approach_stuck_count(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()
        policy._shop_approach_stuck_count = SHOP_APPROACH_STUCK_LIMIT - 1
        policy.last_reason = "melee"

        policy.choose_key(snapshot)

        self.assertEqual(policy._shop_approach_stuck_count, 0)
        self.assertEqual(policy._town_visit_ledger.approach_fails[STORE_HOME], 0)

    def test_noncombat_interruption_preserves_approach_count(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()
        policy._shop_approach_stuck_count = 7
        policy.last_reason = "home:request-knowledge-scan"

        with patch.object(policy, "_choose_key", return_value=WAIT_KEY):
            key = policy.choose_key(snapshot)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy._shop_approach_stuck_count, 7)

    def test_retired_weight_claim_hands_off_without_an_ownerless_pass(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            policy_module.TOWN_STOP_PASS_LIMIT
        )

        with patch.object(policy, "_outstanding_equipment_work", return_value=False):
            policy._town_claims_active(snapshot)
            key = policy._town_blocked_key(snapshot)

        self.assertNotIn("weight-overload", policy._town_claim_categories)
        self.assertEqual(policy._town_blocked_reason, "overweight-home-unreachable")
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "town:blocked:overweight-home-unreachable"
        )


    def test_overweight_blocks_fixed_quest_town_travel(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()
        policy.approved_quest_strategy = lambda _quest_id: object()

        with patch.object(
            policy, "_town_teleport_key", return_value="WRONG-TRAVEL"
        ) as travel:
            self.assertIsNone(policy._fixed_quest_key(snapshot, []))

        travel.assert_not_called()

class HomeVisitOwnershipTest(unittest.TestCase):
    """Inside Home, an active equipment-transaction session must run BEFORE the
    dominated-disposal leave. The disposal Esc used to preempt the session, whose
    town-side dispatcher then walked straight back in — an in/out bounce at the
    Home door that the harness loop guard cannot see (store snapshots reset it)."""

    def _home_snapshot(self, inventory):
        return Snapshot(
            player(45, 123),
            {Position(45, 123): grid(45, 123)},
            [],
            floor_key=(0, 0, 0),
            inventory=inventory,
            equipment=[],
            store=StoreState(store_type=STORE_HOME, items=[]),
        )

    @staticmethod
    def _dominated(pol, snap, item_obj):
        pol._pending_disposal_item = pol._item_signature(item_obj)
        pol._pending_disposal_slot = item_obj.slot
        return pol

    def test_active_home_transaction_preempts_the_disposal_leave(self):
        from unittest import mock

        sword = item("d", TVAL_SWORD, 4, is_equipment=True, name="old sword")
        snap = self._home_snapshot([sword])
        pol = self._dominated(HengbotPolicy(), snap, sword)
        with mock.patch.object(
            pol, "_equipment_transaction_home_key", return_value="dj"
        ):
            self.assertEqual(pol._shop(snap), "dj")

    def test_disposal_leave_resumes_once_the_session_is_done(self):
        sword = item("d", TVAL_SWORD, 4, is_equipment=True, name="old sword")
        snap = self._home_snapshot([sword])
        pol = self._dominated(HengbotPolicy(), snap, sword)
        # No session at all: _equipment_transaction_home_key returns None.
        key = pol._shop(snap)
        self.assertEqual(pol.last_reason, "home:leave-with-dominated")
        self.assertEqual(key, LEAVE_STORE_KEY)

    def test_new_home_transaction_cannot_reset_completed_home_visit_history(self):
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_HOME] = 512000
        policy._town_errand_plan = SimpleNamespace(stops=[STORE_HOME], index=1)
        session = SimpleNamespace(
            executable=True,
            required_context="home",
        )

        policy._set_equipment_transaction_session(session)

        self.assertIs(policy._equipment_transaction_session, session)
        self.assertEqual(policy._town_store_attempted[STORE_HOME], 512000)
        self.assertEqual(policy._town_errand_plan.index, 1)

    def test_rejected_home_visit_budget_stops_the_real_approach(self):
        policy = HengbotPolicy()
        policy._home_visit.attempts_used = policy._home_visit.attempt_limit
        outside = Snapshot(
            player(45, 122),
            {Position(45, 122): replace(
                grid(45, 122), store_number=STORE_HOME
            )},
            [], floor_key=(0, 0, 0), inventory=[], equipment=[], turn=700,
        )
        key = policy._shopping_approach_step(outside, STORE_HOME)
        self.assertIsNone(key)
        self.assertIsNone(policy._shopping_approach_store_type)
        self.assertIn(STORE_HOME, policy._town_store_attempted)
        self.assertIn("attempt-budget-exhausted",
                      policy.consume_pending_home_visit_report())

    def test_prepare_operation_lazily_rebuilds_pre_executor_checkpoint(self):
        for action in ("take", "put"):
            with self.subTest(action=action):
                policy = HengbotPolicy()
                del policy._home_visit
                del policy._pending_home_visit_report
                restored = restore_checkpoint(
                    HengbotPolicy, checkpoint(policy)
                )
                self.assertFalse(restored._prepare_home_visit_operation(
                    action, ("restart-item", action), ("fresh", 1)
                ))
                self.assertIn(
                    "restart-refile-required",
                    restored.consume_pending_home_visit_report(),
                )

    def test_prepare_operation_budget_exhaustion_is_visible(self):
        policy = HengbotPolicy()
        policy._home_visit.attempts_used = policy._home_visit.attempt_limit
        self.assertFalse(policy._prepare_home_visit_operation(
            "take", ("budgeted-item",), ("fresh", 1)
        ))
        self.assertIn(
            "home-visit:atomic-home-composer:attempt-budget-exhausted",
            policy.consume_pending_home_visit_report(),
        )

    def test_promoted_restore_request_composes_recorded_identify_staff(self):
        policy = HengbotPolicy()
        fillers = [
            store_item(chr(ord("a") + index), TVAL_SCROLL, index + 100,
                       name=f"stored filler {index}")
            for index in range(13)
        ]
        identify_staffs = [
            store_item(letter, TVAL_STAFF, SV_STAFF_IDENTIFY,
                       name=f"Identify staff {charges}", charges=charges)
            for letter, charges in zip("nopq", (19, 13, 9, 8))
        ]
        tail = [
            store_item(chr(ord("r") + index), TVAL_SCROLL, index + 200,
                       name=f"stored tail {index}")
            for index in range(22)
        ]
        home_items = [*fillers, *identify_staffs, *tail]
        self.assertEqual(len(home_items), 39)
        target = policy._item_signature(identify_staffs[0])
        stale = ("prior restore", TVAL_SCROLL, 99)
        executor = policy._home_visit
        executor.file(HomeVisitRequest(
            HomeVisitKind.CALIBRATION_RESTORE, "calibration-restore", stale,
        ))
        self.assertTrue(executor.begin_approach(4168))
        self.assertEqual(
            executor.file(HomeVisitRequest(
                HomeVisitKind.CALIBRATION_RESTORE,
                "calibration-restore",
                ("intervening restore", TVAL_SCROLL, 98),
            )),
            "queued",
        )
        self.assertEqual(
            executor.file(HomeVisitRequest(
                HomeVisitKind.CALIBRATION_RESTORE,
                "calibration-restore",
                target,
                batch=(target,),
            )),
            "queued",
        )

        policy._decision_sequence = 4169
        policy._shopping_approach_store_type = STORE_HOME
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [target]
        policy._home_knowledge_items = [
            policy._inventory_item_from_store_item(candidate)
            for candidate in home_items
        ]
        policy._home_knowledge_current = True
        policy._home_knowledge_valid_before = 39
        policy._home_page_size = 52
        wanted_purchase = store_item(
            "j", TVAL_STAFF, SV_STAFF_IDENTIFY, price=936,
            count=14, charges=18, name="shop Identify staff",
        )
        entrance = Snapshot(
            player(45, 123, gold=12452),
            {Position(45, 123): replace(
                grid(45, 123), store_number=STORE_HOME,
            )},
            [], floor_key=(0, 0, 0),
            inventory=[item("a", TVAL_FLASK, SV_FLASK_OIL, count=11)],
            equipment=[], turn=1410895,
        )

        self.assertEqual(wanted_purchase.price, 936)
        self.assertEqual(wanted_purchase.count, 14)
        self.assertEqual(wanted_purchase.charges, 18)
        self.assertEqual(entrance.player.gold, 12452)
        self.assertEqual(policy._atomic_home_withdraw_key(
            entrance, entrance.player.position,
        ), WAIT_KEY)
        self.assertEqual(executor.operation, ("take", target))
        self.assertEqual(policy._store_visit.operation_key, "pn\x1b")
        self.assertNotEqual(policy.last_reason, "home-visit:withdraw-not-authorized")

    def test_home_rearm_is_noop_after_visit_budget_exhaustion(self):
        policy = HengbotPolicy()
        policy._home_visit.attempts_used = policy._home_visit.attempt_limit
        policy._town_store_attempted[STORE_HOME] = 700
        policy._town_errand_plan = SimpleNamespace(
            completed_this_visit=[STORE_HOME],
            blocked_this_visit=[STORE_HOME],
            skipped_latched=[STORE_HOME],
        )
        policy._rearm_town_store_for_new_work(
            STORE_HOME, release_visit_bound=True
        )
        self.assertEqual(policy._town_store_attempted[STORE_HOME], 700)
        self.assertEqual(
            policy._town_errand_plan.completed_this_visit, [STORE_HOME]
        )
        self.assertEqual(
            policy._town_errand_plan.blocked_this_visit, [STORE_HOME]
        )
        self.assertEqual(
            policy._town_errand_plan.skipped_latched, [STORE_HOME]
        )

class RetentionAuthorityTest(unittest.TestCase):
    def _town(
        self, inventory, *, equipment=(), store=None,
        gold=FUNDRAISING_START_GOLD,
    ):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=gold),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            equipment=list(equipment),
            store=store,
        )

    def test_replay_just_bought_detection_and_planned_shovel_stay_in_pack(self):
        detection = item(
            "h", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            name="Scroll of Treasure Detection",
        )
        shovel = item("k", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="Shovel", pval=1)
        snap = self._town([detection, shovel], store=StoreState(STORE_HOME, []))
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._town_visit_purchases.add(policy._item_signature(detection))

        self.assertEqual(policy._retention_reservation(snap, detection), 1)
        self.assertEqual(policy._retention_reservation(snap, shovel), 1)
        self.assertIsNone(policy._find_home_deposit(snap))

    def test_town_cycle_planned_yeek_mining_keeps_last_detection_scroll(self):
        """21:38 replay: Home runs before the low-gold errand starts mining."""
        detection = item(
            "h", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            name="Scroll of Treasure Detection",
        )
        snap = self._town(
            [detection], store=StoreState(STORE_HOME, []), gold=2999
        )
        policy = HengbotPolicy()
        self.assertIsNone(policy._fundraising_mode)

        self.assertEqual(policy._retention_reservation(snap, detection), 1)
        self.assertIsNone(policy._find_home_deposit(snap))
        self.assertEqual(policy._next_required_store_type(snap), STORE_HOME)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_sale_sweep_emits_no_inscription_or_sale_for_kit_detection(self):
        detection = item(
            "h",
            TVAL_SCROLL,
            SV_SCROLL_DETECT_TREASURE,
            name="Scroll of Treasure Detection",
            aware=True,
        )
        snap = self._town(
            [detection],
            store=StoreState(STORE_ALCHEMIST, []),
            gold=FUNDRAISING_START_GOLD - 1,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._retention_reservation(snap, detection), 1)
        self.assertIsNone(policy._find_low_level_sale(snap))
        self.assertNotIn(detection, policy._current_store_sale_candidates(snap))
        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertNotEqual(policy.last_reason, "shop:batch-inscribe")

    def test_ten_torches_are_reserved_and_real_surplus_deposits_once(self):
        torches = item(
            "j", TVAL_LITE, SV_LITE_TORCH,
            count=14, name="Wooden Torches", fuel=5000,
        )
        snap = self._town([torches], store=StoreState(STORE_HOME, []))
        policy = HengbotPolicy()

        self.assertEqual(policy._retention_reservation(snap, torches), 10)
        self.assertEqual(policy._retention_surplus(snap, torches), 4)
        self.assertEqual(policy._find_home_deposit(snap), torches)
        self.assertEqual(policy._home_deposit_key(snap, torches), "dj4\r")

    def test_matching_launcher_ammo_replaces_throwing_torches(self):
        torches = item(
            "j", TVAL_LITE, SV_LITE_TORCH,
            count=10, name="Wooden Torches", fuel=5000,
        )
        shots = item("s", TVAL_SHOT, 1, count=20, name="Iron Shots")
        sling = item(
            "bow", TVAL_BOW, SV_BOW_SLING,
            name="Sling", is_equipment=True,
        )
        snap = self._town(
            [torches, shots], equipment=[sling],
            store=StoreState(STORE_HOME, []),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._retention_reservation(snap, torches), 0)
        self.assertEqual(policy._find_home_deposit(snap), torches)
        self.assertEqual(policy._home_deposit_key(snap, torches), "dj10\r")

    def test_matching_ammo_is_limited_to_two_dense_pack_stacks(self):
        sling = item(
            "bow", TVAL_BOW, SV_BOW_SLING,
            name="Sling", is_equipment=True,
        )
        shots = [
            item("m", TVAL_SHOT, 1, count=14, name="plain shots"),
            item("n", TVAL_SHOT, 1, count=51, to_h=2, to_d=4, name="bulk shots"),
            item("o", TVAL_SHOT, 1, count=3, to_h=5, to_d=3, name="shots +5,+3"),
            item("p", TVAL_SHOT, 1, count=3, to_h=5, to_d=5, name="shots +5,+5"),
            item("q", TVAL_SHOT, 1, count=6, to_h=5, to_d=6, name="shots +5,+6"),
            item("r", TVAL_SHOT, 1, count=6, to_h=4, to_d=2, name="slaying shots"),
        ]
        snap = self._town(
            shots, equipment=[sling], store=StoreState(STORE_HOME, []),
        )
        policy = HengbotPolicy()

        self.assertEqual(
            [policy._retention_reservation(snap, shot) for shot in shots],
            [0, 51, 3, 3, 6, 6],
        )
        self.assertEqual(policy._find_home_deposit(snap), shots[0])
        self.assertEqual(policy._home_deposit_key(snap, shots[0]), "dm14\r")

    def test_quest_ammo_target_does_not_reopen_a_third_pack_slot(self):
        sling = item(
            "bow", TVAL_BOW, SV_BOW_SLING,
            name="Sling", is_equipment=True,
        )
        shots = [
            item("m", TVAL_SHOT, 1, count=70, name="shots A"),
            item("n", TVAL_SHOT, 1, count=50, name="shots B"),
            item("o", TVAL_SHOT, 1, count=30, to_d=9, name="shots C"),
        ]
        snap = self._town(shots, equipment=[sling])
        policy = HengbotPolicy()
        force = {
            "launcher": {"ammo": "equipped", "equipped": True},
            "throwing_items": {"launcher_ammo": 99},
        }
        profile = SimpleNamespace(required_force=force)

        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            self.assertEqual(
                [policy._retention_reservation(snap, shot) for shot in shots],
                [0, 50, 30],
            )

    def test_inferior_crossbow_system_is_deposited_when_sling_is_selected(self):
        sling = item(
            "bow", TVAL_BOW, SV_BOW_SLING, name="artifact sling",
            is_equipment=True, is_artifact=True, to_h=11, to_d=14,
        )
        crossbow = item(
            "c", TVAL_BOW, SV_BOW_LIGHT_XBOW, name="light crossbow",
            is_equipment=True, to_h=4, to_d=8,
        )
        bolts = item("b", TVAL_BOLT, 0, count=99, name="bolts")
        shots = item("s", TVAL_SHOT, 1, count=15, name="iron shots")
        policy = HengbotPolicy()
        set_known_target(policy)
        snap = self._town(
            [crossbow, bolts, shots], equipment=[sling],
            store=StoreState(STORE_HOME, []),
        )

        self.assertEqual(policy._retention_reservation(snap, crossbow), 0)
        self.assertEqual(policy._retention_reservation(snap, bolts), 0)
        self.assertEqual(policy._retention_reservation(snap, shots), 15)
        self.assertEqual(policy._find_home_deposit(snap), crossbow)

        without_crossbow = replace(snap, inventory=[bolts, shots])
        self.assertEqual(policy._find_home_deposit(without_crossbow), bolts)
        self.assertEqual(policy._home_deposit_key(without_crossbow, bolts), "db99\r")

    def test_q2_uses_selected_sling_and_does_not_reserve_crossbow_bolts(self):
        sling = item(
            "bow", TVAL_BOW, SV_BOW_SLING, name="artifact sling",
            is_equipment=True, is_artifact=True, to_h=11, to_d=14,
        )
        shots = item("s", TVAL_SHOT, 1, count=45, name="iron shots")
        bolts = item("b", TVAL_BOLT, 0, count=99, name="bolts")
        snap = self._town([shots, bolts], equipment=[sling])
        policy = HengbotPolicy()
        force = {
            "launcher": {"ammo": "equipped", "equipped": True},
            "throwing_items": {"launcher_ammo": 45},
        }

        status = policy._quest_carry_status(snap, force)

        self.assertTrue(status["launcher"]["ready"])
        self.assertTrue(status["throwing_items.launcher_ammo"]["ready"])
        profile = SimpleNamespace(required_force=force)
        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            self.assertEqual(policy._retention_reservation(snap, shots), 45)
            self.assertEqual(policy._retention_reservation(snap, bolts), 0)

    def test_q2_equipped_launcher_releases_displaced_pack_launcher_for_deposit(self):
        """t1411595 seq 4/9: the worn Q2 launcher satisfies required:1."""
        equipped = item(
            "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
            name="Light Crossbow", is_equipment=True, to_h=2, to_d=6,
        )
        displaced = item(
            "a", TVAL_BOW, SV_BOW_LIGHT_XBOW,
            name="Light Crossbow", is_equipment=True, to_h=3, to_d=1,
        )
        snap = replace(
            self._town([displaced], equipment=[equipped]),
            town_id=0,
            visited_town_ids=(0, 1),
            quests={
                2: QuestState(2, status=QUEST_STATUS_UNTAKEN, fixed=True)
            },
        )
        policy = HengbotPolicy(
            quest_strategies=load_quest_strategies(Path("strategy/quests"))
        )
        strategy = policy._carry_procurement_strategy(snap)
        self.assertEqual(strategy.quest_id, 2)
        self.assertEqual(strategy.required_force["launcher"], {
            "ammo": "equipped", "equipped": True,
            "min_average_damage": 25,
        })
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            "pack:displaced-light-crossbow",
            item_identity=policy_module.equipment_identity(displaced),
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )

        reservation = policy._retention_reservation(snap, displaced)
        keep_set = policy._home_visit_keep_set(snap)
        request = policy._derived_home_visit_request(snap)

        self.assertEqual(
            (
                reservation,
                policy._item_signature(displaced) in keep_set,
                request is None,
            ),
            (0, False, False),
        )
        self.assertEqual(request.kind, HomeVisitKind.EQUIPMENT_MUTATION)
        self.assertEqual(request.requester, "equipment-transaction")
        self.assertEqual(request.item_identity, policy._item_signature(displaced))

    def test_q2_pack_launcher_stays_reserved_when_none_is_equipped(self):
        displaced = item(
            "a", TVAL_BOW, SV_BOW_LIGHT_XBOW,
            name="Light Crossbow", is_equipment=True, to_h=3, to_d=6,
        )
        snap = replace(
            self._town([displaced]),
            town_id=0,
            visited_town_ids=(0, 1),
            quests={
                2: QuestState(2, status=QUEST_STATUS_UNTAKEN, fixed=True)
            },
        )
        policy = HengbotPolicy(
            quest_strategies=load_quest_strategies(Path("strategy/quests"))
        )
        strategy = policy._carry_procurement_strategy(snap)

        self.assertEqual(strategy.quest_id, 2)
        self.assertEqual(policy._retention_reservation(snap, displaced), 1)

    def test_same_visit_purchase_guard_clears_on_floor_change(self):
        detection = item(
            "h", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            name="Scroll of Treasure Detection",
        )
        policy = HengbotPolicy()
        policy._town_visit_purchases.add(policy._item_signature(detection))
        town = self._town([detection])
        policy._floor_key = town.floor_key
        self.assertEqual(policy._retention_reservation(town, detection), 1)

        dungeon = replace(town, floor_key=(1, 1, 0), town_flag=False)
        policy._observe(dungeon)
        self.assertFalse(policy._town_visit_purchases)


    def test_takeoff_projection_uses_real_two_torch_pack_order(self):
        """Plan time matches inven_carry for displaced-first and -last cases."""
        cases = (
            {
                "name": "fuel-5000-torch-displaced-last",
                "pack": (
                    item(
                        "a", TVAL_LITE, 0, name="carried torch", count=10,
                        fuel=1000, known=True, fully_known=True,
                        is_equipment=True,
                    ),
                ),
                "worn": item(
                    "light", TVAL_LITE, 0, name="worn torch", count=1,
                    fuel=5000, known=True, fully_known=True,
                    is_equipment=True,
                ),
                # Equal calc_price: inven_carry places the new takeoff after
                # existing stock.  Fuel is not an object-value term.
                "insertion_index": 1,
                "retained": False,
            },
            {
                "name": "enchanted-digger-displaced-first",
                "pack": (
                    item(
                        "a", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                        name="plain shovel A", known=True, fully_known=True,
                        is_equipment=True,
                    ),
                    item(
                        "b", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                        name="plain shovel B", known=True, fully_known=True,
                        is_equipment=True,
                    ),
                ),
                "worn": item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    name="enchanted shovel", to_h=9, to_d=9,
                    known=True, fully_known=True, is_equipment=True,
                ),
                # object_value_real's DIGGING branch adds
                # (to_h + to_d + to_a) * 100, so inven_carry inserts first.
                "insertion_index": 0,
                "retained": True,
            },
        )
        for case in cases:
            with self.subTest(case=case["name"]):
                policy = HengbotPolicy()
                policy._fundraising_mode = "mine"
                worn = case["worn"]
                snapshot = self._town(case["pack"], equipment=[worn])
                policy._equipment_catalog.refresh_carried(
                    snapshot.inventory, snapshot.equipment
                )
                catalog = policy._equipment_catalog.items
                projected = policy._transaction_retain_identities(
                    snapshot, current_loadout(catalog), Loadout((), "empty")
                )

                # Independent ground truth: model inven_carry's find_if
                # insertion result directly, including its equal-key rule.
                real_order = list(case["pack"])
                real_order.insert(case["insertion_index"], worn)
                post_takeoff = replace(
                    snapshot,
                    inventory=tuple(
                        replace(it, slot=chr(ord("a") + index))
                        for index, it in enumerate(real_order)
                    ),
                    equipment=(),
                )
                retained_after = policy._home_visit_retention(post_takeoff)[1]
                identity = policy_module.equipment_identity(worn)
                self.assertEqual(identity in projected, case["retained"])
                self.assertEqual(identity in retained_after, case["retained"])

                plan = policy_module.plan_equipment_transactions(
                    catalog,
                    current_loadout(catalog),
                    Loadout((), "empty"),
                    current_pack_items=len(snapshot.inventory),
                    home_scan_complete=True,
                    retain_item_identities=projected,
                )
                deposits = {
                    action.item_identity for action in plan.phase("home_finalize")
                }
                self.assertEqual(identity not in deposits, case["retained"])

class HomeFullLatchTest(unittest.TestCase):
    """Home rejection is represented only by observed operation outcomes."""

    def _town_snap(self, inventory):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
        )

    def test_rejected_deposit_stops_all_deposits_for_the_town_visit(self):
        ring = item("k", TVAL_RING, 39, is_equipment=True, known=True)
        amulet = item("l", TVAL_AMULET, 4, is_equipment=True, known=True)
        snap = replace(
            self._town_snap([ring, amulet]),
            store=StoreState(STORE_HOME, []),
        )
        pol = HengbotPolicy()
        preparation = SimpleNamespace(
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(
                best=SimpleNamespace(loadout=SimpleNamespace(item_ids=frozenset()))
            )
        )
        pol._equipment_optimization_preparation = preparation
        pol._home_entry_operation_posted = True

        with patch.object(
            pol, "_prepare_equipment_optimization", return_value=preparation
        ):
            keys = [pol._shop(snap) for _ in range(STORE_STUCK_LIMIT + 1)]

        self.assertEqual(keys[-1], LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home:deposit-rejected")
        self.assertTrue(pol._home_deposit_abandoned)
        self.assertIn(pol._item_signature(ring), pol._home_rejected_deposits)
        self.assertIsNone(pol._find_home_deposit(snap))

    def test_arrow_home_deposit_enters_full_stack_quantity(self):
        arrows = item("m", TVAL_ARROW, 5, count=9, name="animal slayer arrows")
        snap = replace(
            self._town_snap([arrows]),
            store=StoreState(STORE_HOME, []),
        )
        pol = HengbotPolicy()

        self.assertEqual(pol._home_deposit_key(snap, arrows), "dm9\r")
        self.assertEqual(pol.last_reason, "home:deposit")

    def test_partial_arrow_stack_progress_does_not_count_as_rejection(self):
        pol = HengbotPolicy()

        for count in range(9, 2, -1):
            arrows = item("m", TVAL_ARROW, 5, count=count, name="animal slayer arrows")
            snap = replace(
                self._town_snap([arrows]),
                store=StoreState(STORE_HOME, []),
            )
            self.assertEqual(pol._home_deposit_key(snap, arrows), f"dm{count}\r")

        self.assertEqual(pol.last_reason, "home:deposit")
        self.assertFalse(pol._home_deposit_abandoned)
        self.assertEqual(pol._store_sell_stuck_count, 0)

class TownDepartureConvenienceDepositTest(unittest.TestCase):
    def _snapshot(self, inventory):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
        )

    @staticmethod
    def _make_other_departure_gates_ready(policy):
        policy._recall_departure_ready = lambda _snapshot: True
        policy._food_ready = lambda _snapshot: True
        policy._light_ready = lambda _snapshot: True
        policy._teleport_ready = lambda _snapshot: True
        policy._cure_critical_ready = lambda _snapshot: True
        policy._identify_staff_ready = lambda _snapshot: True
        policy._inventory_overweight = lambda _snapshot: False
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._fundraising_departure_ready = lambda _snapshot: True

    def test_convenience_deposit_does_not_block_departure_or_diagnostic(self):
        arrows = item("a", TVAL_ARROW, 1, count=40, name="surplus arrows")
        fillers = [
            item(chr(ord("b") + index), TVAL_FOOD, 35, name=f"ration-{index}")
            for index in range(13)
        ]
        snapshot = self._snapshot([arrows, *fillers])
        policy = HengbotPolicy()
        self._make_other_departure_gates_ready(policy)
        set_completed_equipment_optimization(policy)

        self.assertEqual(PACK_CAPACITY - len(snapshot.inventory), 9)
        self.assertIs(policy._find_home_deposit(snapshot), arrows)
        self.assertTrue(policy._home_deposit_candidate(arrows, snapshot))
        self.assertTrue(policy._town_departure_ready(snapshot))
        block = policy._departure_block_state(snapshot)
        self.assertNotIn("pending_home_deposit", block["values"])
        self.assertNotIn("pending_home_deposit", block["failed"])


    def test_pack_pressure_still_blocks_with_convenience_deposit(self):
        arrows = item("a", TVAL_ARROW, 1, count=40, name="surplus arrows")
        fillers = [
            item(chr(ord("b") + index), TVAL_FOOD, 35, name=f"ration-{index}")
            for index in range(PACK_CAPACITY - MIN_FREE_PACK_SLOTS)
        ]
        snapshot = self._snapshot([arrows, *fillers])
        policy = HengbotPolicy()
        self._make_other_departure_gates_ready(policy)

        self.assertLess(
            PACK_CAPACITY - len(snapshot.inventory), MIN_FREE_PACK_SLOTS
        )
        self.assertTrue(policy._home_deposit_candidate(arrows, snapshot))
        self.assertFalse(policy._town_departure_ready(snapshot))

    def test_calibration_deposit_skips_restore_queue_without_weakening_pack_order(self):
        """P-A2: restored supplies do not make another deposit round trip."""
        restore = item(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            count=8, known=True, name="Word of Recall",
        )
        next_pack = item("b", TVAL_FOOD, 35, count=3, name="Ration of Food")
        snapshot = self._snapshot([restore, next_pack])
        policy = HengbotPolicy()
        policy._calibration_phase = "deposit"
        policy._calibration_restore_signatures = [
            policy._item_signature(restore)
        ]

        selected = policy._find_home_deposit(snapshot)

        self.assertIs(selected, next_pack)
        self.assertEqual(selected.count, 3)
        restore_only = replace(snapshot, inventory=[restore])
        self.assertIsNone(policy._find_home_deposit(restore_only))

        def install_strip(_snapshot):
            policy._calibration_phase = "strip"
            return True

        policy._install_calibration_strip_session = install_strip
        self.assertEqual(policy._calibration_town_key(restore_only), WAIT_KEY)
        self.assertEqual(policy._calibration_phase, "strip")
        self.assertEqual(policy.last_reason, "calibration:strip-installed")

class HomeOneOperationPerEntryTest(unittest.TestCase):
    """Regression for the 2026-08-02 10:03 Home chooser incident."""

    def _advance_legacy_home_scan_world(
        self, key, current, inventory, pages, page, turn
    ):
        """Apply one posted scan decision to the minimal store protocol world."""
        if "\x1b" in key:
            return current, page, True
        if current.store is None:
            return self._home_page_snapshot(
                inventory, pages[page], turn=turn, stock_num=24,
                page_top=page * 12, page_size=12,
            ), page, False
        if key == " ":
            page = 1 - page
            return self._home_page_snapshot(
                inventory, pages[page], turn=turn, stock_num=24,
                page_top=page * 12, page_size=12,
            ), page, False
        if key == "V":
            return replace(current, messages=("Hengband 3.0",)), page, False
        return current, page, False

    def _snapshot(self, inventory, *, at_home=True, turn=2247200):
        return Snapshot(
            player(45, 123, class_id=PLAYER_CLASS_WARRIOR),
            {Position(45, 123): grid(45, 123)},
            [],
            turn=turn,
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            store=(
                StoreState(
                    STORE_HOME, [], stock_num=0, page_top=0, page_size=12,
                )
                if at_home else None
            ),
        )

    def _entrance_snapshot(self, inventory, *, turn=2247201):
        return Snapshot(
            player(45, 123, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(45, 123): replace(
                    grid(45, 123), store_number=STORE_HOME
                ),
                Position(45, 122): grid(45, 122),
            },
            [],
            turn=turn,
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            store=None,
        )

    def _post_atomic(self, policy, snapshot, target):
        policy._shopping_approach_store_type = STORE_HOME
        with patch.object(policy, "_find_home_deposit", return_value=target):
            key = policy._shopping_approach_key(
                snapshot, Position(45, 123), "shop:travel"
            )
        policy.confirm_key_posted(key)
        return key

    def _real_pack(self, *extra):
        return [
            item(
                "d", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=14,
                known=True, name="Scrolls of Teleportation",
            ),
            item(
                "e", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=8,
                known=True, name="Word of Recall",
            ),
            *extra,
        ]

    def _catalogued_withdrawal_policy(self, wares, *, page_size=12):
        policy = HengbotPolicy()
        # Expectation changed: ~9 order plus observed display geometry now
        # supplies the address; displayed-page provenance no longer exists.
        policy.consume_home_knowledge(tuple(wares))
        policy._home_page_size = page_size
        policy._shopping_approach_store_type = STORE_HOME
        return policy

    def test_restore_list_does_not_steal_unobserved_digger_failure(self):
        stored = store_item(
            "a", TVAL_DIGGING, 4, name="stored pick", is_equipment=True
        )
        other = store_item(
            "b", TVAL_POTION, 1, name="other home item"
        )
        policy = self._catalogued_withdrawal_policy([stored])
        signature = policy._item_signature(stored)
        restore_signature = policy._item_signature(
            store_item("r", TVAL_POTION, 99, name="calibration restore")
        )
        entrance = self._entrance_snapshot([])

        for attempt in range(2):
            policy._home_pending_item = signature
            policy._calibration_restore_signatures = [restore_signature]
            policy._home_knowledge_items = (other,)
            policy._home_knowledge_valid_before = 1
            policy._home_knowledge_current = True
            self.assertIn(
                policy._atomic_home_withdraw_key(
                    replace(entrance, turn=entrance.turn + attempt),
                    entrance.player.position,
                ),
                set("12346789"),
            )
            self.assertEqual(
                policy.last_reason,
                "town:entrance-step-off:home:atomic-withdraw-target-unobserved",
            )

        self.assertEqual(policy._digger_home_withdraw_failures, 2)
        self.assertTrue(policy._digger_buy_fallback_available(entrance))
        self.assertEqual(policy._withdrawable_digging_tool_count(entrance), 0)

    def test_calibration_deposit_phase_does_not_file_restore_visit(self):
        already_deposited = store_item(
            "a", TVAL_POTION, 901, name="already deposited calibration supply"
        )
        next_deposit = item(
            "b", TVAL_POTION, 902, name="next calibration supply", known=True
        )
        policy = HengbotPolicy()
        policy._calibration_phase = "deposit"
        policy._calibration_restore_signatures = [
            policy._item_signature(already_deposited)
        ]
        entrance = self._entrance_snapshot([next_deposit])

        request = policy._derived_home_visit_request(entrance)

        self.assertIsNotNone(request)
        self.assertEqual(request.requester, "calibration-deposit")
        self.assertEqual(request.item_identity, policy._item_signature(next_deposit))
        self.assertNotEqual(
            request.item_identity, policy._calibration_restore_signatures[0]
        )

    def test_gate1_captured_restore_shrink_reproduces_target_unobserved(self):
        """Gate 1: replay the legacy same-turn failure from captured facts."""
        wares = [
            store_item(str(index), TVAL_POTION, 1000 + index, name=f"home {index}")
            for index in range(34)
        ]
        restore = store_item("21", 36, 1, name="汚れたボロ服 [1] {上質}")
        best_shovel = store_item(
            "30", TVAL_DIGGING, 1,
            name="シャベル (1d2) (+3,+8) (+1) {+掘}", is_equipment=True,
        )
        wares[21] = restore
        wares[30] = best_shovel
        wares[31] = store_item("31", TVAL_DIGGING, 1, name="second shovel", is_equipment=True)
        wares[32] = store_item("32", TVAL_DIGGING, 1, name="third shovel", is_equipment=True)
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        restore_signature = policy._item_signature(restore)
        policy._calibration_restore_signatures = [restore_signature]
        entrance = self._entrance_snapshot([], turn=1178879)

        self.assertEqual(
            policy._atomic_home_withdraw_key(entrance, entrance.player.position),
            WAIT_KEY,
        )
        # The captured entrance/posted rows are seq 17672/17673 at turns
        # 1178879/1178889.  The posted restore remains owned through the stale
        # outside snapshot; only a fresh snapshot may release it.
        policy.choose_key(entrance)
        self.assertIsNotNone(policy._home_atomic_withdraw_pending)
        self.assertEqual(policy._home_atomic_withdraw_pending[2].name, restore.name)

    def test_captured_queued_digger_preempts_restore_then_restore_follows(self):
        wares = [
            store_item(str(index), TVAL_POTION, 1000 + index, name=f"home {index}")
            for index in range(34)
        ]
        restore = store_item("21", 36, 1, name="captured restore")
        shovel = store_item(
            "30", TVAL_DIGGING, 1, name="captured best shovel", is_equipment=True,
        )
        wares[21] = restore
        wares[30] = shovel
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        policy._calibration_restore_signatures = [policy._item_signature(restore)]
        policy._home_pending_item = policy._item_signature(shovel)
        entrance = self._entrance_snapshot([], turn=1178879)

        self.assertEqual(
            policy._atomic_home_withdraw_key(entrance, entrance.player.position),
            WAIT_KEY,
        )
        self.assertEqual(policy._home_atomic_withdraw_pending[2].name, shovel.name)
        policy._home_atomic_withdraw_pending = None
        policy._home_pending_item = None
        policy.consume_home_knowledge(tuple(item for item in wares if item is not shovel))
        self.assertEqual(
            policy._atomic_home_withdraw_key(
                replace(entrance, turn=entrance.turn + 1), entrance.player.position
            ),
            WAIT_KEY,
        )
        self.assertEqual(policy._home_atomic_withdraw_pending[2].name, restore.name)

    def test_calibration_restore_matches_fresh_home_equipment_identity(self):
        deposited = store_item(
            "a", TVAL_SOFT_ARMOR, 2,
            name="Leather Scale Mail [11,+0] {worn rendering}",
            known=True, fully_known=True, is_equipment=True,
        )
        policy = self._catalogued_withdrawal_policy([deposited])
        stale_pack_signature = (
            "Leather Scale Mail [11,+0] {pack rendering}",
            TVAL_SOFT_ARMOR,
            2,
        )
        policy._calibration_restore_signatures = [stale_pack_signature]
        policy._calibration_worn_before = (
            ("body", policy_module.equipment_identity(deposited)),
        )
        entrance = self._entrance_snapshot([])

        self.assertEqual(
            policy._atomic_home_withdraw_key(
                entrance, entrance.player.position
            ),
            WAIT_KEY,
        )
        self.assertEqual(
            policy.last_reason, "calibration:atomic-restore-withdraw"
        )
        self.assertEqual(policy._calibration_restore_signatures, [])
        self.assertEqual(policy._home_atomic_withdraw_pending[2], deposited)

    def test_captured_same_turn_restore_remains_owned_until_fresh_snapshot(self):
        wares = [
            store_item(str(index), TVAL_POTION, 1000 + index, name=f"home {index}")
            for index in range(34)
        ]
        restore = store_item("21", 36, 1, name="captured restore")
        wares[21] = restore
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        policy._calibration_restore_signatures = [policy._item_signature(restore)]
        entrance = self._entrance_snapshot([], turn=1178696)
        self.assertEqual(
            policy._atomic_home_withdraw_key(entrance, entrance.player.position),
            WAIT_KEY,
        )
        policy.choose_key(entrance)
        self.assertIsNotNone(policy._home_atomic_withdraw_pending)
        self.assertEqual(policy._digger_home_withdraw_failures, 0)

    def test_captured_restore_prefix_collapse_rerequests_scan_without_discard(self):
        """Gate 1: the measured pending-false capture reacquires its addresses."""
        wares = [
            store_item(str(index), TVAL_POTION, 1200 + index, name=f"home {index}")
            for index in range(35)
        ]
        restore = store_item("0", 36, 1, count=5, name="captured restore")
        shovel = store_item(
            "30", TVAL_DIGGING, 1, name="captured shovel", is_equipment=True,
        )
        second_shovel = store_item(
            "31", TVAL_DIGGING, 1, name="captured second shovel",
            is_equipment=True,
        )
        wares[0] = restore
        wares[30] = shovel
        wares[31] = second_shovel
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        policy._calibration_restore_signatures = [
            policy._item_signature(restore),
            policy._item_signature(wares[1]),
        ]
        entrance = self._entrance_snapshot([], turn=2320394)
        owners_before = tuple(policy._calibration_restore_signatures)
        deferred_before = set(policy._deferred_home_items)

        self.assertEqual(
            policy._atomic_home_withdraw_key(entrance, entrance.player.position),
            WAIT_KEY,
        )
        self.assertFalse(policy._home_digger_withdraw_pending)
        self.assertTrue(policy._home_knowledge_current)
        policy.confirm_key_posted(WAIT_KEY)
        self.assertEqual(
            policy.choose_key(self._home_page_snapshot(
                [], wares[:12], turn=2320394,
                stock_num=len(wares), page_top=0, page_size=52,
            )),
            "pbpa5\r\x1b",
        )
        policy.choose_key(replace(
            entrance,
            turn=2320395,
            inventory=[item("a", 36, 1, count=5, name=restore.name)],
        ))
        self.assertFalse(policy._home_knowledge_current)
        self.assertEqual(
            policy._calibration_restore_signatures, [owners_before[1]]
        )
        self.assertEqual(policy._deferred_home_items, deferred_before)

        # Confirmation row 1479 leaves the player outside on the Home door.
        # The existing selector first moves to a safe non-entrance square; the
        # invalid observation then makes the next decision re-request ~9.
        fresh = replace(entrance, turn=2320404)
        step = policy._town_entrance_step_off_key(
            fresh, "home:atomic-withdraw-target-unobserved"
        )
        self.assertIn(step, set("12346789"))
        self.assertEqual(
            policy.last_reason,
            "town:entrance-step-off:home:atomic-withdraw-target-unobserved",
        )
        off_door = replace(
            fresh,
            turn=fresh.turn + 1,
            player=replace(fresh.player, position=Position(45, 122)),
        )
        self.assertEqual(policy.choose_key(off_door), "~9\x1b\x1b")

        rescanned = tuple(wares[1:])
        policy.consume_home_knowledge(rescanned)
        policy._shopping_approach_store_type = STORE_HOME
        self.assertEqual(
            policy._atomic_home_withdraw_key(
                replace(entrance, turn=fresh.turn + 2), entrance.player.position
            ),
            WAIT_KEY,
        )
        self.assertFalse(policy._home_digger_withdraw_pending)
        self.assertEqual(policy._digger_home_withdraw_failures, 0)
        self.assertEqual(policy._deferred_home_items, deferred_before)

    def test_target_unobserved_step_off_uses_safe_least_visited_selector(self):
        policy = HengbotPolicy()
        entrance = self._entrance_snapshot([])
        origin = entrance.player.position
        safe = Position(origin.y, origin.x - 1)
        warning = Position(origin.y - 1, origin.x)
        policy._warning_refused_cells.add(warning)
        policy._visit_counts[safe] = 1
        policy._visit_counts[Position(origin.y + 1, origin.x)] = 9

        key = policy._town_entrance_step_off_key(
            entrance, "home:atomic-withdraw-target-unobserved"
        )

        self.assertIn(key, set("12346789"))
        self.assertEqual(key, "4")
        self.assertEqual(
            policy.last_reason,
            "town:entrance-step-off:home:atomic-withdraw-target-unobserved",
        )

    def test_captured_digger_address_composes_across_twelve_item_pages(self):
        wares = [
            store_item(str(index), TVAL_POTION, 1100 + index, name=f"home {index}")
            for index in range(34)
        ]
        shovel = store_item(
            "30", TVAL_DIGGING, 1, name="captured best shovel", is_equipment=True,
        )
        wares[30] = shovel
        policy = self._catalogued_withdrawal_policy(wares, page_size=12)
        policy._home_pending_item = policy._item_signature(shovel)
        entrance = self._entrance_snapshot([])

        self.assertEqual(
            policy._atomic_home_withdraw_key(entrance, entrance.player.position),
            WAIT_KEY,
        )

    def test_captured_zero_digger_chain_reaches_mining_claim(self):
        detection = item(
            "t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            count=5, known=True, name="Scrolls of Detect Treasure",
        )
        food = item("f", TVAL_FOOD, 35, count=10, known=True)
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN,
            name="lantern", fuel=5000, is_equipment=True,
        )
        shovel = store_item(
            "30", TVAL_DIGGING, 1, name="captured best shovel", is_equipment=True,
        )
        second_shovel = store_item(
            "31", TVAL_DIGGING, 1, name="captured second shovel", is_equipment=True,
        )
        third_shovel = store_item(
            "32", TVAL_DIGGING, 1, name="captured third shovel", is_equipment=True,
        )
        restore = store_item("21", 36, 1, name="captured restore")
        wares = [
                *[
                    store_item(str(index), TVAL_POTION, 1200 + index, name=f"home {index}")
                    for index in range(30)
                ],
                shovel, second_shovel, third_shovel,
            ]
        wares[21] = restore
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        entrance = replace(
            self._entrance_snapshot([detection, food]),
            player=replace(self._entrance_snapshot([]).player, gold=0),
            equipment=[lantern],
        )
        fundraising_seed = replace(
            entrance,
            turn=entrance.turn - 1,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            town_flag=False,
            inventory=[detection, food],
            player=replace(entrance.player, gold=0),
        )
        policy.prime(fundraising_seed)
        self.assertEqual(policy._fundraising_mode, "scavenge")
        policy._calibration_restore_signatures = [policy._item_signature(restore)]
        home_page = replace(
            self._snapshot([detection, food], turn=entrance.turn - 1),
            store=StoreState(STORE_HOME, wares),
        )
        self.assertEqual(policy._shop(home_page), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:queue-digging-tool-withdraw")
        self.assertEqual(policy.choose_key(entrance), WAIT_KEY)
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")

        carried_shovel = item(
            "u", TVAL_DIGGING, 1, name=shovel.name, known=True,
            is_equipment=True,
        )
        outside = replace(
            entrance, turn=entrance.turn + 1,
            inventory=[detection, food, carried_shovel],
        )
        self.assertTrue(policy._fundraising_supplies_ready(outside))
        town_ready = replace(
            self._snapshot(
                [detection, food, carried_shovel], at_home=False,
                turn=outside.turn + 1,
            ),
            player=outside.player,
            equipment=[lantern],
        )
        for town_turn in range(4):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: capture-derived entrance, carried-shovel outside, and town-ready rows drive fundraising selection, not locomotion effects
            policy.choose_key(replace(town_ready, turn=town_ready.turn + town_turn))
            if policy._fundraising_mode == "mine":
                break
        self.assertEqual(policy._fundraising_mode, "mine")

        target = Position(3, 4)
        mining_pack = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(3, 3): grid(3, 3),
                target: grid(3, 4, passable=False, gold=True, tunnel=True, marked=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                detection, food, carried_shovel,
            ],
            equipment=[
                lantern,
            ],
        )
        wield_key = None
        for quiet_turn in range(MINING_THREAT_FREE_LIMIT):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: capture-derived unwielded-mining and equipped-mining rows drive wield selection and claim enumeration, not locomotion effects
            wield_key = policy.choose_key(
                replace(mining_pack, turn=entrance.turn + 10 + quiet_turn)
            )
        self.assertIsNotNone(wield_key)
        self.assertEqual(
            policy.last_reason,
            "fundraise:wield-digging-tool",
            (policy._fundraising_mode, policy._returning_to_town),
        )
        mining = replace(
            mining_pack,
            inventory=[detection, food],
            equipment=[*mining_pack.equipment, carried_shovel],
        )
        # First policy decision consumes detection; the following observation
        # enumerates the visible captured vein as a mining claim.
        detection_key = policy.choose_key(mining)
        self.assertTrue(detection_key.startswith("r"), (detection_key, policy.last_reason))
        after_detection = replace(mining, turn=mining.turn + 1)
        self.assertEqual(policy.choose_key(after_detection), TUNNEL_KEY + "6")
        self.assertEqual(policy.last_reason, "fundraise:dig-to-treasure")

    def _home_page_snapshot(
        self, inventory, wares, *, turn, stock_num=None, page_top=None,
        page_size=None,
    ):
        return replace(
            self._snapshot(inventory, turn=turn),
            store=StoreState(
                STORE_HOME, list(wares), stock_num=stock_num,
                page_top=page_top, page_size=page_size,
            ),
            equipment=[item("light", TVAL_LITE, 0, name="a light")],
        )

    def _choose_atomic_withdrawal(self, policy, entrance):
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(
            policy,
            "_decide",
            side_effect=lambda snapshot: policy._shopping_approach_key(
                snapshot, snapshot.player.position, "shop:travel"
            ),
        ):
            key = policy.choose_key(entrance)
        policy.confirm_key_posted(key)
        return key

    def _assert_staged_home_operation(self, policy, entry, tail):
        self.assertEqual(entry, WAIT_KEY)
        self.assertEqual(len(entry), 1)
        self.assertIsNotNone(policy._store_visit)
        self.assertEqual(policy._store_visit.composed_key, WAIT_KEY)
        self.assertEqual(policy._store_visit.operation_key, tail)
        self.assertFalse(policy._store_visit.operation_released)

    def test_live_92_item_calibration_restore_is_one_public_decision(self):
        wares = [
            store_item(
                chr(ord("a") + (index % 12)),
                TVAL_POTION,
                100 + index,
                name=f"home item {index}",
            )
            for index in range(91)
        ]
        target = store_item(
            "h", TVAL_POTION, 999, name="catalogued restore target"
        )
        wares.append(target)
        policy = self._catalogued_withdrawal_policy(wares)
        signature = policy._item_signature(target)
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [signature]
        pack = [
            item(chr(ord("a") + index), TVAL_FOOD, index, name=f"pack {index}")
            for index in range(12)
        ]
        entrance = replace(
            self._entrance_snapshot(pack),
            equipment=[item("light", TVAL_LITE, 0, name="a light")],
        )

        key = self._choose_atomic_withdrawal(policy, entrance)

        self._assert_staged_home_operation(
            policy, key, (" " * 7) + "ph\x1b"
        )
        self.assertEqual(policy.last_reason, "calibration:atomic-restore-withdraw")
        self.assertEqual(policy._home_atomic_withdraw_pending[2].name, target.name)

    def test_entry_owned_wait_reaches_sender_without_projected_store_command(self):
        """Every character in an outside-composed withdrawal lands legally."""
        target = store_item("?", TVAL_POTION, 1351, name="target")
        policy = self._catalogued_withdrawal_policy([target])
        policy._home_pending_item = policy._item_signature(target)
        entrance = self._entrance_snapshot(self._real_pack(), turn=2247451)
        posted = []
        key = self._choose_atomic_withdrawal(policy, entrance)
        sent, _ = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            "entry-owner-snapshot",
            key,
            None,
            set(),
            in_store=False,
            decision={"reason": policy.last_reason, "key": key},
        )

        self.assertTrue(sent)
        self.assertEqual("".join(posted), WAIT_KEY)
        self.assertEqual(policy._store_visit.operation_key, "pa\x1b")
        state = "outside"
        legal = []
        for character in "".join(posted):
            legal.append((state, character))
            if (state, character) == ("outside", WAIT_KEY):
                state = "home"
            elif (state, character) == ("home", BUY_KEY):
                state = "selection"
            elif state == "selection" and character == "a":
                state = "home"
            elif (state, character) == ("home", LEAVE_STORE_KEY):
                state = "outside"
            else:
                self.fail((state, character, legal))
        self.assertEqual(state, "home")
    def test_public_calibration_restore_converges_twelve_items(self):
        base = [
            store_item("a", TVAL_POTION, 1400 + index, name=f"home {index}")
            for index in range(80)
        ]
        targets = [
            store_item(
                "a", TVAL_POTION, 1500 + index, name=f"restore {index:02d}"
            )
            for index in range(12)
        ]
        stock = [*base[:7], *targets, *base[7:]]
        policy = HengbotPolicy()
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [
            policy._item_signature(target) for target in reversed(targets)
        ]
        policy._home_candidate_waiting = True
        inventory = self._real_pack()
        target_signatures = {
            policy._item_signature(target) for target in targets
        }
        inside = False
        on_entrance = True
        top = 0
        entries = 0
        withdrawals = 0
        reasons = Counter()
        withdrawal_decisions = []

        def page_items():
            page = stock[top:top + 12]
            return [
                replace(ware, letter=chr(ord("a") + index))
                for index, ware in enumerate(page)
            ]

        for decision in range(300):
            turn = 2247500 + decision
            snapshot = (
                self._home_page_snapshot(inventory, page_items(), turn=turn)
                if inside
                else replace(
                    self._entrance_snapshot(inventory, turn=turn),
                    player=(
                        player(45, 123, class_id=PLAYER_CLASS_WARRIOR)
                        if on_entrance
                        else player(45, 122, class_id=PLAYER_CLASS_WARRIOR)
                    ),
                    grids={
                        Position(45, 123): replace(
                            grid(45, 123), store_number=STORE_HOME
                        ),
                        Position(45, 122): grid(45, 122),
                    },
                    equipment=[item("light", TVAL_LITE, 0, name="a light")],
                )
            )
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            key = policy.choose_key(snapshot)
            policy.confirm_key_posted(key)
            reasons[policy.last_reason] += 1
            if inside:
                # TEST_FAKERY_LINT_ALLOW: literal-success-predicate: the returned protocol key itself is the behavior asserted by this focused test
                if key == " ":
                    top += 12
                    if top >= len(stock):
                        top = 0
                elif key == LEAVE_STORE_KEY:
                    inside = False
                    top = 0
                elif BUY_KEY in key:
                    prefix, take = key.split(BUY_KEY, 1)
                    page = len(prefix)
                    letter = take[0]
                    index = page * 12 + ord(letter) - ord("a")
                    withdrawn = stock.pop(index)
                    inventory.append(item(
                        chr(ord("u") + withdrawals), withdrawn.tval,
                        withdrawn.sval, name=withdrawn.name,
                    ))
                    withdrawals += 1
                    withdrawal_decisions.append(decision)
                    inside = False
                    top = 0
                else:
                    self.fail((decision, "unexpected in-store key", key, policy.last_reason))
            # TEST_FAKERY_LINT_ALLOW: literal-success-predicate: the knowledge request is the public protocol event this replay must answer
            elif key == "~9\x1b\x1b":
                policy.consume_home_knowledge(tuple(stock))
                policy._home_page_size = 12
                on_entrance = True
                top = 0
            elif key == WAIT_KEY:
                inside = True
                on_entrance = True
                top = 0
                entries += 1
            # TEST_FAKERY_LINT_ALLOW: literal-success-predicate: the returned protocol key itself is the behavior asserted by this focused test
            elif on_entrance and key == "4":
                on_entrance = False
            # TEST_FAKERY_LINT_ALLOW: literal-success-predicate: the returned protocol key itself is the behavior asserted by this focused test
            elif not on_entrance and key == "6":
                inside = True
                on_entrance = True
                top = 0
                entries += 1
            elif key.startswith(WAIT_KEY) and BUY_KEY in key:
                prefix, take = key.split(BUY_KEY, 1)
                page = len(prefix) - 1
                letter = take[0]
                index = page * 12 + ord(letter) - ord("a")
                self.assertLess(index, len(stock))
                withdrawn = stock.pop(index)
                inventory.append(
                    item(
                        chr(ord("u") + withdrawals), withdrawn.tval,
                        withdrawn.sval, name=withdrawn.name,
                    )
                )
                withdrawals += 1
                entries += 1
                withdrawal_decisions.append(decision)
                top = 0
            elif key.startswith(WAIT_KEY) and SELL_KEY in key:
                # Restore convergence is reached before the following deposit
                # phase; the composed deposit merely proves the pending take
                # was observed and cleared.
                pass
            elif key == LEAVE_STORE_KEY:
                pass
            else:
                self.fail((
                    decision, "unexpected outside key", key, policy.last_reason,
                    reasons, policy._calibration_phase,
                    len(policy._calibration_restore_signatures),
                    policy._town_visit_ledger.blocked_stores,
                ))
            restored = {
                policy._item_signature(carried)
                for carried in inventory
            } & target_signatures
            if len(restored) == 12 and policy._home_atomic_withdraw_pending is None:
                break

        restored = {
            policy._item_signature(carried) for carried in inventory
        } & target_signatures
        self.assertEqual(len(restored), 12, (reasons, decision, len(inventory)))
        self.assertEqual(withdrawals, 12)
        self.assertLess(decision + 1, 300)
        self.acceptance_restore_metrics = {
            "decisions": decision + 1,
            "reasons": reasons,
            "entries": entries,
            "withdrawal_decisions": withdrawal_decisions,
        }
        # The catalogue visit is the sole Home pass; none of the twelve
        # successful atomic restore takes consumes another visit/pass.
        self.assertGreater(policy._town_visit_ledger.store_visits[STORE_HOME], 0)
        self.assertLessEqual(
            policy._town_visit_ledger.store_visits[STORE_HOME], entries
        )
        self.assertLessEqual(
            policy._town_visit_ledger.need_attempts.get(
                "calibration-restore", 0
            ),
            1,
        )
        self.assertLessEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], entries
        )
    def test_public_restore_attempt_does_not_release_home_approach_bound(self):
        policy = HengbotPolicy()
        pack = self._real_pack()
        entrance = self._entrance_snapshot(pack, turn=2247800)
        surface = replace(
            entrance,
            player=replace(entrance.player, position=Position(45, 122)),
            equipment=[item("light", TVAL_LITE, 0, name="a light")],
        )

        # Settle the visit through ordinary public decisions before reproducing
        # the approach-limit ledger state written by _shopping_approach_step.
        for decision in range(4):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            policy.choose_key(replace(surface, turn=2247800 + decision))
        policy._calibration_phase = "restore-supplies"
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",), result=None,
        )
        policy._calibration_restore_signatures = [("restore", 1, 1)]
        policy._home_candidate_waiting = True
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            TOWN_STOP_PASS_LIMIT
        )
        policy._town_visit_ledger.need_attempts["calibration-restore"] = (
            TOWN_STOP_PASS_LIMIT
        )
        policy._town_store_attempted[STORE_HOME] = 2247803

        reasons = Counter()
        maximum_approach_fails = 0
        for decision in range(600):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            policy.choose_key(
                replace(surface, turn=2247810 + decision)
            )
            reasons[policy.last_reason] += 1
            maximum_approach_fails = max(
                maximum_approach_fails,
                policy._town_visit_ledger.approach_fails[STORE_HOME],
            )

        # E1/E5 re-judgement: the exhausted Home owner self-retires and closes
        # its visit instead of preserving a cross-owner approach stamp.
        self.assertGreater(reasons["town:blocked:owner-retired"], 0)
        self.assertLessEqual(
            maximum_approach_fails, TOWN_STOP_PASS_LIMIT,
            (reasons, maximum_approach_fails),
        )
        self.assertNotIn(
            "calibration-restore", policy._town_visit_ledger.need_attempts
        )
        self.assertGreater(
            reasons["home:request-knowledge-scan"],
            0,
            "incomplete Home knowledge must preempt exhausted approach routing",
        )

    def test_atomic_withdrawal_derives_first_later_and_last_page_letters(self):
        wares = [
            store_item(
                chr(ord("a") + (index % 12)),
                TVAL_POTION,
                200 + index,
                name=f"ware {index}",
            )
            for index in range(29)
        ]
        for absolute_index, expected in ((0, "pa\x1b"), (12, " pa\x1b"), (28, "  pe\x1b")):
            policy = self._catalogued_withdrawal_policy(wares)
            policy._home_pending_item = policy._item_signature(wares[absolute_index])
            self._assert_staged_home_operation(
                policy,
                self._choose_atomic_withdrawal(policy, self._entrance_snapshot([])),
                expected,
            )

    def test_derived_withdrawal_uses_uppercase_and_live_page_three_arithmetic(self):
        wares = [
            store_item("?", TVAL_POTION, 500 + index, name=f"home {index}")
            for index in range(107)
        ]
        for absolute_index, expected in ((51, "pZ\x1b"), (106, "  pc\x1b")):
            policy = self._catalogued_withdrawal_policy(wares, page_size=52)
            policy._home_pending_item = policy._item_signature(wares[absolute_index])
            self._assert_staged_home_operation(
                policy,
                self._choose_atomic_withdrawal(policy, self._entrance_snapshot([])),
                expected,
            )

    def test_public_page_three_withdrawal_posts_one_complete_sender_key(self):
        from hengbot.cli import _send_new_decision_key

        wares = [
            store_item("?", TVAL_POTION, 700 + index, name=f"home {index}")
            for index in range(107)
        ]
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        policy._home_pending_item = policy._item_signature(wares[106])
        key = self._choose_atomic_withdrawal(policy, self._entrance_snapshot([]))
        posted = []
        sent, _ = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            "derived-page-three",
            key,
            None,
            set(),
            in_store=False,
        )
        self.assertTrue(sent)
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy._store_visit.operation_key, "  pc\x1b")
        self.assertEqual("".join(posted), key)

    def test_descending_withdrawals_share_one_home_knowledge_read(self):
        wares = [
            store_item("?", TVAL_POTION, 900 + index, name=f"home {index}")
            for index in range(60)
        ]
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        entrance = self._entrance_snapshot([])
        policy._home_pending_item = policy._item_signature(wares[55])
        self._assert_staged_home_operation(
            policy,
            policy._atomic_home_withdraw_key(entrance, Position(1, 1)),
            " pd\x1b",
        )
        policy._home_atomic_withdraw_pending = None
        policy._home_entry_operation_posted = False
        policy._home_pending_item = policy._item_signature(wares[10])
        self._assert_staged_home_operation(
            policy,
            policy._atomic_home_withdraw_key(entrance, Position(1, 1)),
            "pk\x1b",
        )

    def test_unconfirmed_ascending_withdrawal_keeps_later_index_addressable(self):
        wares = [
            store_item("?", TVAL_POTION, 1100 + index, name=f"home {index}")
            for index in range(60)
        ]
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        entrance = self._entrance_snapshot([])
        policy._home_pending_item = policy._item_signature(wares[10])
        self._assert_staged_home_operation(
            policy,
            policy._atomic_home_withdraw_key(entrance, Position(1, 1)),
            "pk\x1b",
        )
        policy._home_atomic_withdraw_pending = None
        policy._home_entry_operation_posted = False
        policy._home_pending_item = policy._item_signature(wares[55])
        self._assert_staged_home_operation(
            policy,
            policy._atomic_home_withdraw_key(entrance, Position(1, 1)),
            " pd\x1b",
        )

    def test_unlanded_highest_owner_replay_recomposes_same_take(self):
        wares = [
            store_item("?", TVAL_POTION, 1400 + index, name=f"home {index}")
            for index in range(9)
        ]
        armour = store_item(
            "?", 37, 1, name="Chain Mail [14,+0]", is_equipment=True, ac=14,
        )
        wares.append(armour)
        policy = self._catalogued_withdrawal_policy(wares)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "withdraw", "home:armour:0",
            item_identity=policy_module.equipment_identity(armour),
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )
        entrance = self._entrance_snapshot([], turn=2247900)

        first = policy.choose_key(entrance)
        self.assertEqual(first, WAIT_KEY)
        self.assertEqual(policy._store_visit.operation_key, "pj\x1b")
        self.assertEqual(policy._home_knowledge_valid_before, len(wares))

        inside = self._home_page_snapshot(
            [], wares, turn=2247901, stock_num=len(wares),
            page_top=0, page_size=12,
        )
        self.assertEqual(policy.choose_key(inside), "pj\x1b")
        replay = policy.choose_key(replace(entrance, turn=2247902))

        self.assertEqual(replay, WAIT_KEY)
        self.assertNotIn(
            policy.last_reason,
            {"equipment-transaction:withdraw-missing", "home:route-claim-unfulfilled"},
        )

    def test_confirmed_highest_owner_withdrawal_shrinks_prefix(self):
        wares = [
            store_item("?", TVAL_POTION, 1500 + index, name=f"home {index}")
            for index in range(9)
        ]
        armour = store_item(
            "?", 37, 1, name="Chain Mail [14,+0]", is_equipment=True, ac=14,
        )
        wares.append(armour)
        policy = self._catalogued_withdrawal_policy(wares)
        signature = policy._item_signature(armour)
        policy._home_pending_item = signature
        entrance = self._entrance_snapshot([], turn=2247910)

        self._assert_staged_home_operation(
            policy,
            policy._atomic_home_withdraw_key(entrance, entrance.player.position),
            "pj\x1b",
        )
        carried = item(
            "a", 37, 1, name=armour.name, is_equipment=True, ac=14,
        )
        policy.confirm_key_posted(WAIT_KEY)
        self.assertEqual(
            policy.choose_key(self._home_page_snapshot(
                [], wares, turn=2247910,
                stock_num=len(wares), page_top=0, page_size=12,
            )),
            "pj\x1b",
        )
        policy.choose_key(
            replace(entrance, turn=2247911, inventory=[carried])
        )

        self.assertEqual(policy._home_knowledge_valid_before, 9)
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertNotIn(
            signature,
            {
                policy._item_signature(item)
                for index, item in enumerate(policy._home_knowledge_items)
                if index < policy._home_knowledge_valid_before
            },
        )

    def test_derived_withdrawal_waits_when_page_size_was_never_observed(self):
        target = store_item("?", TVAL_POTION, 1300, name="target")
        policy = self._catalogued_withdrawal_policy([target])
        policy._home_page_size = None
        policy._home_pending_item = policy._item_signature(target)
        self.assertIsNone(
            policy._atomic_home_withdraw_key(
                self._entrance_snapshot([]), Position(1, 1)
            )
        )
        self.assertEqual(policy.last_reason, "home:await-page-size")

    def test_atomic_withdrawal_quantity_omits_single_prompt_and_answers_stack(self):
        single = store_item("a", TVAL_POTION, 301, count=1, name="single")
        stack = store_item("b", TVAL_POTION, 302, count=7, name="stack")
        single_policy = self._catalogued_withdrawal_policy([single, stack])
        single_policy._home_pending_item = single_policy._item_signature(single)
        self.assertEqual(
            self._choose_atomic_withdrawal(single_policy, self._entrance_snapshot([])),
            WAIT_KEY,
        )
        stack_policy = self._catalogued_withdrawal_policy([single, stack])
        stack_policy._calibration_restore_signatures = [
            stack_policy._item_signature(stack)
        ]
        self.assertEqual(
            self._choose_atomic_withdrawal(stack_policy, self._entrance_snapshot([])),
            WAIT_KEY,
        )

    def test_public_home_composer_to_sender_completes_stack_deposit_without_invalid_character(self):
        from hengbot.cli import _send_new_decision_key

        stack = item("a", TVAL_ARROW, 302, count=7, name="stack")
        policy = HengbotPolicy()
        policy._calibration_phase = "deposit"
        policy._shopping_approach_store_type = STORE_HOME
        key = policy.choose_key(self._entrance_snapshot([stack]))
        state = "outside"
        quantity = ""
        deposited = 0
        invalid = []

        def send(value, **_kwargs):
            nonlocal state, quantity, deposited
            for character in value:
                if state == "outside" and character == WAIT_KEY:
                    state = "home"
                elif state == "home" and character == SELL_KEY:
                    state = "pack-selection"
                elif state == "pack-selection" and character == "a":
                    state = "quantity"
                elif state == "quantity" and character.isdigit():
                    quantity += character
                elif state == "quantity" and character == "\r" and quantity:
                    deposited = int(quantity)
                    state = "home"
                elif state == "home" and character == LEAVE_STORE_KEY:
                    state = "outside"
                else:
                    invalid.append((state, character))
            return True

        sent, _ = _send_new_decision_key(
            send,
            "live-home-entrance-shape",
            key,
            None,
            set(),
            in_store=False,
        )

        self.assertTrue(sent)
        self.assertEqual(key, WAIT_KEY)
        send(policy._store_visit.operation_key)
        self.assertEqual(invalid, [])
        self.assertEqual(deposited, 7)
        self.assertEqual(state, "outside")

    def test_public_deposit_preserves_catalogue_or_incomplete_work_requests_it(self):
        deposited = item(
            "n", TVAL_SWORD, 3, name="proven deposited sword",
            known=True, fully_known=True, is_equipment=True,
        )
        entrance = self._entrance_snapshot([deposited], turn=2247460)

        preserved = HengbotPolicy()
        preserved._equipment_catalog.complete_home_scan(())
        preserved._calibration_phase = "deposit"
        preserved._shopping_approach_store_type = STORE_HOME
        self.assertEqual(preserved.choose_key(entrance), WAIT_KEY)
        self.assertEqual(preserved.last_reason, "home:atomic-deposit")
        self.assertTrue(preserved._equipment_catalog.home_scan_complete)
        self.assertIn(
            deposited.name,
            [owned.item.name for owned in preserved._equipment_catalog.items],
        )

        incomplete = HengbotPolicy()
        incomplete._calibration_phase = "deposit"
        incomplete._shopping_approach_store_type = STORE_HOME
        self.assertEqual(incomplete.choose_key(entrance), WAIT_KEY)
        incomplete._calibration_phase = None
        self.assertEqual(
            incomplete.choose_key(self._home_page_snapshot(
                [deposited], [], turn=2247460,
                stock_num=0, page_top=0, page_size=12,
            )),
            "dn\x1b",
        )
        incomplete._equipment_optimization_preparation = SimpleNamespace(
            blockers=("home-scan-incomplete",), result=None,
        )
        after = replace(
            self._entrance_snapshot([], turn=2247461),
            player=player(45, 122, class_id=PLAYER_CLASS_WARRIOR),
        )
        self.assertEqual(incomplete.choose_key(after), "~9\x1b\x1b")
        self.assertEqual(incomplete.last_reason, "home:request-knowledge-scan")

    def test_restore_withdraws_deposits_with_atomic_fresh_entry_contract(self):
        wares = [
            store_item("?", TVAL_POTION, 1600 + index, name=f"home {index}")
            for index in range(60)
        ]
        target = wares[55]
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [policy._item_signature(target)]
        key = policy.choose_key(self._entrance_snapshot(self._real_pack()))
        posted = []
        sent, _ = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            "calibration-restore-fresh-entry",
            key,
            None,
            set(),
            in_store=False,
            decision={"reason": policy.last_reason, "key": key},
        )

        self.assertTrue(sent)
        self.assertEqual(policy.last_reason, "calibration:atomic-restore-withdraw")
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(posted, [key])
        self.assertEqual(key.count(WAIT_KEY), 1)
        self.assertEqual(policy._store_visit.operation_key.count(BUY_KEY), 1)
        self.assertTrue(
            policy._store_visit.operation_key.endswith(LEAVE_STORE_KEY)
        )

    def test_duplicate_signature_slots_keep_their_displayed_addresses(self):
        first = store_item("a", TVAL_POTION, 350, count=99, name="duplicate")
        second = store_item("b", TVAL_POTION, 350, count=7, name="duplicate")
        later = store_item("c", TVAL_POTION, 351, name="later")
        policy = self._catalogued_withdrawal_policy([first, second, later])

        # Expectation changed: duplicate physical slots are retained by exact
        # ~9 order and count; their printed letters are deliberately ignored.
        self.assertEqual(
            [item.count for item in policy._home_knowledge_items], [99, 7, 1]
        )
        policy._home_pending_item = policy._item_signature(later)
        self.assertEqual(
            self._choose_atomic_withdrawal(policy, self._entrance_snapshot([])),
            WAIT_KEY,
        )

    def test_invalidated_address_refuses_until_home_is_reobserved(self):
        target = store_item("a", TVAL_POTION, 360, name="target")
        policy = self._catalogued_withdrawal_policy([target])
        policy._home_pending_item = policy._item_signature(target)
        policy._invalidate_home_observation()

        self.assertIsNone(
            policy._atomic_home_withdraw_key(
                self._entrance_snapshot([]), Position(45, 123)
            )
        )
        self.assertEqual(policy.last_reason, "home:await-fresh-knowledge")

    def test_in_store_stock_count_invalidates_stale_empty_knowledge(self):
        observed = store_item("a", TVAL_POTION, 361, name="observed")
        policy = HengbotPolicy()
        self.assertTrue(policy.consume_home_knowledge(()))

        policy.choose_key(
            self._home_page_snapshot(
                [], [observed], turn=76934, stock_num=1,
                page_top=0, page_size=52,
            )
        )

        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_scan_item_count, 1)

    def test_in_store_stock_count_invalidates_stale_nonempty_knowledge(self):
        stale = store_item("a", TVAL_POTION, 362, name="stale")
        policy = HengbotPolicy()
        self.assertTrue(policy.consume_home_knowledge((stale,)))

        policy.choose_key(
            self._home_page_snapshot(
                [], [], turn=76935, stock_num=0,
                page_top=0, page_size=52,
            )
        )

        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_scan_item_count, 0)

    def test_known_empty_home_completes_withdrawal_only_owner(self):
        pending = ("phantom", TVAL_SWORD, 99)
        policy = HengbotPolicy()
        policy._home_pending_batch = [pending]
        self.assertTrue(policy.consume_home_knowledge(()))
        snapshot = self._entrance_snapshot([])

        self.assertFalse(policy._home_owner_goal_pending(snapshot))
        self.assertNotIn(
            "equipment-catalog",
            {
                need.category
                for need in policy._enumerate_town_needs(snapshot)
                if need.store_type == STORE_HOME
            },
        )
        policy._town_errand_plan = policy_module.TownErrandPlan(
            stops=[STORE_HOME, STORE_MAGIC],
            need_categories={STORE_HOME: ("equipment-catalog",)},
        )
        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=True,
        )
        self.assertEqual(policy._town_errand_plan.index, 1)
        self.assertIn(STORE_HOME, policy._town_errand_plan.blocked_this_visit)
        self.assertEqual(
            policy._town_blocked_reason, "home-known-empty-withdrawal",
        )

    def test_observed_page_letter_is_authoritative_not_absolute_index(self):
        target = store_item("Q", TVAL_POTION, 370, name="unusual displayed letter")
        policy = self._catalogued_withdrawal_policy([target])
        policy._home_pending_item = policy._item_signature(target)

        # Expectation changed: the emitter letter is ignored; index zero derives a.
        self.assertEqual(
            self._choose_atomic_withdrawal(policy, self._entrance_snapshot([])),
            WAIT_KEY,
        )

    def test_failed_atomic_withdrawal_is_reported_and_never_reposted(self):
        target = store_item("a", TVAL_POTION, 401, name="target")
        policy = self._catalogued_withdrawal_policy([target])
        signature = policy._item_signature(target)
        policy._home_pending_item = signature
        entrance = self._entrance_snapshot([])
        self.assertEqual(self._choose_atomic_withdrawal(policy, entrance), WAIT_KEY)
        self.assertEqual(
            policy.choose_key(self._home_page_snapshot(
                [], [target], turn=entrance.turn,
                stock_num=1, page_top=0, page_size=12,
            )),
            "pa\x1b",
        )

        outside = replace(entrance, turn=entrance.turn + 1)
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: failed atomic-withdrawal reporting is isolated from the downstream town decision
        policy._decide = Mock(return_value=WAIT_KEY)
        self.assertEqual(policy.choose_key(outside), WAIT_KEY)
        self.assertEqual(
            policy.last_reason,
            "home:atomic-withdraw-failed",
        )
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertIn(signature, policy._deferred_home_items)
        self.assertNotIn("p", policy.choose_key(replace(outside, turn=outside.turn + 1)))

    def test_captured_q34_home_errand_requests_knowledge_and_rearms(self):
        policy = HengbotPolicy(
            quest_strategies=load_quest_strategies(Path("strategy/quests")),
        )
        weapon = store_item("a", TVAL_SWORD, 2, name="safe scimitar")
        light = item(
            "light", TVAL_LITE, 0, name="a light", is_equipment=True,
        )
        pack = self._real_pack()
        inside = replace(
            self._home_page_snapshot(
                pack, [weapon], turn=76933, stock_num=1,
                page_top=0, page_size=12,
            ),
            equipment=[light],
        )
        entrance = replace(
            self._entrance_snapshot(pack, turn=76949),
            equipment=[light],
            town_id=0,
            quests={
                34: QuestState(
                    id=34, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5,
                )
            },
        )
        entrance.grids[Position(46, 123)] = grid(
            46, 123, building_special=34,
        )
        approach = replace(
            entrance,
            # evidence-home-yield-loop-20260813.jsonl decision 6, turn 76959.
            player=replace(entrance.player, position=Position(44, 124)),
        )
        inside = replace(inside, town_id=0, quests=entrance.quests)
        inside.grids[Position(46, 123)] = grid(46, 123, building_special=34)

        no_errand = HengbotPolicy(
            quest_strategies=load_quest_strategies(Path("strategy/quests")),
        )
        equipped_weapon = item(
            "main_hand", TVAL_SWORD, 2, name="safe scimitar",
            known=True, fully_known=True, is_equipment=True,
        )
        self.assertEqual(
            no_errand.choose_key(
                replace(approach, equipment=[equipped_weapon, light])
            ),
            "~9\x1b\x1b",
        )
        self.assertEqual(no_errand.last_reason, "home:request-knowledge-scan")

        # evidence-home-yield-loop-20260813.jsonl decision 6 records this
        # queued signature; decision 8 is the matching off-tile board.
        policy._home_errand.file(
            HomeErrandRequest(
                policy._item_signature(weapon), 1,
                "captured-home-page", "combat-weapon",
            ),
            knowledge_current=False,
        )
        decisions = [policy.choose_key(approach)]
        reasons = [policy.last_reason]
        self.assertEqual(decisions, ["~9\x1b\x1b"])
        policy.confirm_key_posted("~9\x1b\x1b")
        response = json.dumps({
            "type": "knowledge",
            "knowledge": {
                "category": "home", "menu_key": "9", "items": [{
                    "slot": "a", "tval": TVAL_SWORD, "sval": 2,
                    "name": "safe scimitar", "known": True,
                    "fully_known": True, "is_equipment": True,
                }],
            },
        })
        self.assertEqual(_dispatch_response_lines([response], policy, Mock()), 1)
        policy._home_page_size = 12
        for snapshot in (
            replace(approach, turn=76960),
            replace(entrance, turn=76961),
            replace(inside, turn=76962),
        ):
            decisions.append(policy.choose_key(snapshot))
            reasons.append(policy.last_reason)

        carried = item(
            "f", TVAL_SWORD, 2, name="safe scimitar",
            known=True, fully_known=True, is_equipment=True,
        )
        outside_after = replace(
            approach, turn=76963, inventory=[*pack, carried],
        )
        decisions.append(policy.choose_key(outside_after))
        reasons.append(policy.last_reason)
        armed = replace(
            outside_after,
            turn=76964,
            inventory=pack,
            equipment=[replace(carried, slot="main_hand"), light],
        )
        decisions.append(policy.choose_key(armed))
        reasons.append(policy.last_reason)

        self.assertEqual(
            decisions[:5], ["~9\x1b\x1b", "1", WAIT_KEY, "pa\x1b", "~9\x1b\x1b"],
        )
        self.assertNotIn("home:queue-combat-weapon-withdraw", reasons)
        self.assertLessEqual(len(decisions), 6)
        self.assertNotEqual(reasons[-1], "home:queue-combat-weapon-withdraw")
        self.assertTrue(policy._combat_weapon_ready(armed))

    def test_unobserved_transaction_withdrawal_terminal_yields_unchanged_board(self):
        observed = store_item("a", TVAL_POTION, 402, name="other item")
        missing = store_item(
            "b", TVAL_POTION, 403, name="missing equipment",
            is_equipment=True,
        )
        policy = self._catalogued_withdrawal_policy([observed])
        identity = policy_module.equipment_identity(missing)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "withdraw",
            "home:missing:0",
            item_identity=identity,
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )
        entrance = self._entrance_snapshot([])

        self.assertIn(policy.choose_key(entrance), set("12346789"))
        self.assertEqual(
            policy.last_reason,
            "town:entrance-step-off:home:atomic-withdraw-target-unobserved",
        )

        passes = policy._town_visit_ledger.unsatisfied_passes[STORE_HOME]
        outside = replace(
            entrance,
            player=replace(entrance.player, position=Position(45, 122)),
        )
        terminal_reason = (
            "town:blocked:equipment-transaction:"
            "withdraw-item-unobserved:home:missing:0"
        )
        self.assertEqual(
            policy.choose_key(replace(outside, turn=entrance.turn + 2)), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, terminal_reason)
        yielded = policy.choose_key(
            replace(outside, turn=entrance.turn + 3)
        )
        self.assertEqual(yielded, WAIT_KEY)
        self.assertNotEqual(policy.last_reason, terminal_reason)
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], passes
        )

    def test_complete_open_page_repairs_unaddressable_transaction_target(self):
        other = store_item("a", TVAL_POTION, 410, name="other")
        target = store_item(
            "b", TVAL_RING, 79, name="visible target", is_equipment=True,
        )
        policy = self._catalogued_withdrawal_policy([other, target])
        policy._home_knowledge_valid_before = 1
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "withdraw", "home:visible:0",
            item_identity=policy_module.equipment_identity(target),
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )
        inside = self._home_page_snapshot(
            [], [other, target], turn=2247920, stock_num=2,
            page_top=0, page_size=12,
        )

        self.assertEqual(
            policy._equipment_transaction_home_key(inside), LEAVE_STORE_KEY
        )
        self.assertEqual(
            policy.last_reason,
            "equipment-transaction:await-fresh-knowledge",
        )
        self.assertFalse(policy._home_knowledge_current)
        self.assertIsNone(policy._town_blocked_reason)

    def test_complete_cached_open_page_repairs_atomic_prefix_mismatch(self):
        other = store_item("a", TVAL_POTION, 411, name="other")
        target = store_item("b", TVAL_POTION, 412, name="visible target")
        policy = self._catalogued_withdrawal_policy([other, target])
        policy._home_scan_source = "observed-home-page"
        policy._home_knowledge_valid_before = 1
        policy._home_pending_item = policy._item_signature(target)
        entrance = self._entrance_snapshot([], turn=2247921)

        self.assertIsNone(
            policy._atomic_home_withdraw_key(entrance, entrance.player.position)
        )
        self.assertEqual(policy.last_reason, "home:await-fresh-knowledge")
        self.assertFalse(policy._home_knowledge_current)

    def test_restore_collapse_invalidates_for_transaction_withdraw_owner(self):
        restore = store_item("0", 36, 1, name="captured restore")
        target = store_item(
            "30", TVAL_RING, 77, name="transaction target",
            known=True, fully_known=True, is_equipment=True,
        )
        wares = [restore, *[
            store_item(str(index), TVAL_POTION, 1800 + index, name=f"home {index}")
            for index in range(1, 30)
        ], target]
        policy = self._catalogued_withdrawal_policy(wares, page_size=52)
        policy._calibration_restore_signatures = [policy._item_signature(restore)]
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "withdraw", "home:target",
            item_identity=policy_module.equipment_identity(target),
        )
        policy._equipment_transaction_session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 0)
        )
        entrance = self._entrance_snapshot([], turn=2388203)

        self.assertEqual(
            policy._atomic_home_withdraw_key(entrance, entrance.player.position),
            WAIT_KEY,
        )
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(
            policy.choose_key(self._home_page_snapshot(
                [], wares, turn=2388203,
                stock_num=len(wares), page_top=0, page_size=52,
            )),
            "pa\x1b",
        )
        policy.choose_key(replace(
            entrance,
            turn=2388204,
            inventory=[item("a", 36, 1, name=restore.name)],
        ))
        self.assertFalse(policy._home_knowledge_current)
        self.assertIs(policy._equipment_transaction_session.current_action, action)

    def test_open_transaction_does_not_filter_calibration_slot_resolution(self):
        restore = store_item("0", 36, 1, name="captured restore")
        target = store_item(
            "1", TVAL_RING, 78, name="different transaction target",
            known=True, fully_known=True, is_equipment=True,
        )
        policy = self._catalogued_withdrawal_policy([restore, target], page_size=52)
        policy._calibration_restore_signatures = [policy._item_signature(restore)]
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "withdraw", "home:target",
            item_identity=policy_module.equipment_identity(target),
        )
        policy._equipment_transaction_session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 0)
        )
        entrance = self._entrance_snapshot([], turn=2388203)

        self.assertEqual(
            policy._atomic_home_withdraw_key(entrance, entrance.player.position),
            WAIT_KEY,
        )
        self.assertEqual(policy.last_reason, "calibration:atomic-restore-withdraw")
        self.assertEqual(policy._deferred_home_items, set())

    def test_captured_withdrawn_digger_is_not_transaction_deposited(self):
        shovel = item(
            "d", TVAL_DIGGING, 1, name="captured withdrawn shovel",
            known=True, fully_known=True, is_equipment=True,
        )
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "deposit", "pack:shovel",
            item_identity=policy_module.equipment_identity(shovel),
        )
        policy = HengbotPolicy()
        policy._equipment_transaction_session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 1)
        )
        entrance = self._entrance_snapshot([shovel], turn=2388220)
        policy._shopping_approach_store_type = STORE_HOME

        self.assertIsNone(
            policy._atomic_home_deposit_key(entrance, entrance.player.position)
        )
        self.assertEqual(
            policy.last_reason, "equipment-transaction:retain-digging-tool"
        )
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertIsNone(policy._home_atomic_deposit_pending)

    def test_unaddressed_equipment_work_claim_yields_on_unchanged_progress_core(self):
        observed = store_item("a", TVAL_POTION, 402, name="other item")
        policy = self._catalogued_withdrawal_policy([observed])
        missing = (
            ("missing restore one", TVAL_SWORD, 91),
            ("missing restore two", TVAL_SWORD, 92),
        )
        policy._calibration_restore_signatures[:] = missing
        entrance = self._entrance_snapshot([])
        policy._town_errand_plan = policy_module.TownErrandPlan(
            stops=[STORE_HOME],
            need_categories={STORE_HOME: ("equipment-work",)},
        )
        policy._shopping_approach_store_type = STORE_HOME

        self.assertIn(
            policy._atomic_home_withdraw_key(
                entrance, entrance.player.position
            ),
            set("12346789"),
        )
        self.assertEqual(
            policy.last_reason,
            "town:entrance-step-off:home:atomic-withdraw-target-unobserved",
        )
        self.assertEqual(policy._calibration_restore_signatures, [missing[1]])
        self.assertNotIn(
            "equipment-work",
            {
                claim.category
                for claim in policy._enumerate_live_store_claims(entrance)
            },
        )

    def test_identification_withdrawal_cannot_route_without_executor_request(self):
        records = [
            json.loads(line)
            for line in Path(
                "tests/fixtures/evidence-executor-live-gap.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        reasons = [
            record.get("reason")
            for record in records
            for _ in range(record.get("count", 1))
        ]
        self.assertEqual(reasons.count("shop:approach"), 38)
        self.assertEqual(reasons.count("home:store-context-exit"), 22)
        self.assertEqual(
            reasons.count("home:atomic-withdraw-target-unobserved"), 6
        )
        self.assertFalse(
            any(str(reason).startswith("home-errand:") for reason in reasons)
        )

        policy = HengbotPolicy()
        snapshot = self._entrance_snapshot([])
        policy._home_candidate_waiting = True
        policy._equipment_catalog.home_scan_complete = True

        self.assertFalse(policy._home_errand.active)
        policy._town_errand_plan = policy_module.TownErrandPlan(
            stops=[STORE_HOME],
            need_categories={STORE_HOME: ("identification-withdrawal",)},
        )
        self.assertIsNone(
            policy._shopping_approach_step(snapshot, STORE_HOME)
        )

    def test_observed_transaction_withdrawal_still_composes_exact_macro(self):
        target = store_item(
            "a", TVAL_POTION, 404, name="obtainable equipment",
            is_equipment=True,
        )
        policy = self._catalogued_withdrawal_policy([target])
        identity = policy_module.equipment_identity(target)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "withdraw",
            "home:obtainable:0",
            item_identity=identity,
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )

        self.assertEqual(
            policy.choose_key(self._entrance_snapshot([])), WAIT_KEY
        )
        self.assertEqual(
            policy.last_reason, "equipment-transaction:atomic-withdraw"
        )


    def test_real_capture_escape_then_posts_stay_deposit_exit_in_one_decision(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=40, name="surplus arrows")
        arrival = self._snapshot(self._real_pack(target), turn=2247200)
        entrance = self._entrance_snapshot(self._real_pack(target))

        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(policy, "_decide", return_value=SELL_KEY + "f40\r"):
            self.assertEqual(policy.choose_key(arrival), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:scan-complete-from-open-page")
        key = self._post_atomic(policy, entrance, target)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy._store_visit.operation_key, "df40\r\x1b")
        self.assertNotEqual(policy.last_reason, "home:leave-unbound-deposit")

    def test_open_home_page_mana_device_replays_store_item_crash(self):
        policy = HengbotPolicy()
        wand = store_item(
            "a", TVAL_WAND, 6, count=2, name="Stone to Mud",
            known=True, charges=7,
        )
        snapshot = replace(
            self._snapshot([]),
            player=replace(self._snapshot([]).player, food_type=FOOD_TYPE_MANA),
            store=StoreState(
                STORE_HOME, [wand], stock_num=1, page_top=0, page_size=12,
            ),
        )

        self.assertEqual(policy.choose_key(snapshot), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:scan-complete-from-open-page")
        self.assertIsInstance(policy._home_knowledge_items[0], InventoryItem)
        self.assertEqual(policy._count_mana_food_uses(snapshot), 14)

    def test_multi_page_open_home_is_not_consumed_or_attempt_latched(self):
        policy = HengbotPolicy()
        final_page_item = store_item("a", TVAL_WAND, 6, charges=7)
        snapshot = replace(
            self._snapshot([]),
            store=StoreState(
                STORE_HOME, [final_page_item], stock_num=13,
                page_top=12, page_size=12,
            ),
        )

        self.assertEqual(policy.choose_key(snapshot), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:scan-incomplete-open-page")
        self.assertFalse(policy._home_knowledge_current)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

    def test_142251_transaction_deposit_uses_atomic_entrance_visit(self):
        policy = HengbotPolicy()
        target = item(
            "n", 23, 3, count=1, name="transaction spear",
            known=True, fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(target)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            f"pack:{identity}:0",
            item_identity=identity,
        )
        session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 23)
        )
        policy._equipment_transaction_session = session
        entrance = self._entrance_snapshot(
            self._real_pack(target), turn=2242290
        )
        policy._shopping_approach_store_type = STORE_HOME

        key = policy._shopping_approach_key(
            entrance, Position(45, 123), "equipment-transaction:travel-home"
        )

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy._store_visit.operation_key, "dn\x1b")
        self.assertEqual(
            policy.last_reason, "equipment-transaction:atomic-deposit"
        )
        self.assertNotEqual(policy.last_reason, "home:leave-unbound-deposit")
        self.assertIsNone(session.pending_action)
        self.assertEqual(session.prepared_action, action)

        self.assertTrue(policy.confirm_key_posted(key))
        self.assertEqual(session.pending_action, action)
        unchanged = policy_module.observe_equipment_transactions(
            self._snapshot(self._real_pack(target), at_home=False, turn=2242291)
        )
        self.assertFalse(session.observe(unchanged))
        self.assertEqual(session.pending_action, action)
        applied = policy_module.observe_equipment_transactions(
            self._snapshot(self._real_pack(), at_home=False, turn=2242292)
        )
        self.assertTrue(session.observe(applied))
        self.assertTrue(session.complete)

    def test_transaction_atomic_visit_ends_after_one_deposit(self):
        policy = HengbotPolicy()
        target = item(
            "n", 23, 3, count=2, name="transaction spears",
            known=True, fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(target)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            f"pack:{identity}:0",
            item_identity=identity,
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 23)
            )
        )
        entrance = self._entrance_snapshot(self._real_pack(target))
        policy._shopping_approach_store_type = STORE_HOME

        key = policy._shopping_approach_key(
            entrance, Position(45, 123), "equipment-transaction:travel-home"
        )
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy._store_visit.operation_key, "dn2\r\x1b")

        inside = self._snapshot(self._real_pack(target), turn=entrance.turn + 1)
        self.assertEqual(policy.choose_key(inside), "dn2\r\x1b")
        self.assertEqual(policy.last_reason, "home:atomic-deposit")

    def test_mapless_atomic_deposit_completion_matches_map_bearing_page(self):
        target = item("n", 23, 3, name="deposited spear", is_equipment=True)
        bearing = self._snapshot(self._real_pack(target), turn=2247210)
        mapless = replace(bearing, grids={})
        outcomes = []
        for snapshot in (bearing, mapless):
            policy = HengbotPolicy()
            policy._home_entry_operation_posted = True
            outcomes.append((policy.choose_key(snapshot), policy.last_reason))

        self.assertEqual(outcomes[1], outcomes[0])
        self.assertEqual(outcomes[0], (LEAVE_STORE_KEY, "home:leave-after-one-operation"))

    def test_mapless_atomic_withdrawal_completion_matches_map_bearing_page(self):
        target = store_item("a", TVAL_POTION, 402, name="withdrawn target")
        bearing = self._home_page_snapshot([], [target], turn=2247220)
        mapless = replace(bearing, grids={})
        outcomes = []
        for snapshot in (bearing, mapless):
            policy = HengbotPolicy()
            policy._home_entry_operation_posted = True
            policy._home_atomic_withdraw_pending = (
                policy._item_signature(target), 0, target, 1
            )
            outcomes.append((policy.choose_key(snapshot), policy.last_reason))

        self.assertEqual(outcomes[1], outcomes[0])
        self.assertEqual(outcomes[0], (LEAVE_STORE_KEY, "home:leave-after-one-operation"))

    def test_replaced_transaction_atomic_key_discards_prepared_state(self):
        policy = HengbotPolicy()
        target = item(
            "n", 23, 3, name="transaction spear",
            known=True, fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(target)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            f"pack:{identity}:0",
            item_identity=identity,
        )
        session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 23)
        )
        policy._equipment_transaction_session = session
        entrance = self._entrance_snapshot(self._real_pack(target))
        policy._shopping_approach_store_type = STORE_HOME
        prepared = policy._shopping_approach_key(
            entrance, Position(45, 123), "equipment-transaction:travel-home"
        )

        policy._discard_unposted_equipment_transaction_command()

        self.assertTrue(policy.confirm_key_posted(prepared))
        self.assertIsNone(session.prepared_action)
        self.assertIsNone(session.pending_action)

    def test_133250_mixed_home_visit_yields_then_posts_atomic_deposit(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=40, name="surplus arrows")
        categories = ("equipment-catalog", "identification-withdrawal", "deposit")
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_ALCHEMIST, STORE_HOME],
            need_categories={STORE_HOME: categories},
        )
        home = self._snapshot(self._real_pack(target), turn=2323504)

        with (
            patch.object(policy, "_find_home_deposit", return_value=target),
            patch.object(policy, "_home_deposit_key") as deposit_key,
        ):
            policy._shop(home)

        deposit_key.assert_not_called()
        self.assertNotEqual(policy.last_reason, "home:leave-unbound-deposit")

        policy._town_visit_ledger.satisfied_needs.update(
            {
                (STORE_HOME, "equipment-catalog"),
                (STORE_HOME, "identification-withdrawal"),
            }
        )
        entrance = self._entrance_snapshot(self._real_pack(target), turn=2323505)
        key = self._post_atomic(policy, entrance, target)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "home:atomic-deposit")
        self.assertNotEqual(policy._town_blocked_reason, "departure-unsatisfiable")

    def test_unfinishable_home_category_blocks_then_allows_atomic_deposit(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=1, name="surplus arrow")
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME],
            need_categories={
                STORE_HOME: ("equipment-catalog", "deposit"),
            },
        )
        snapshot = self._snapshot(self._real_pack(target), turn=2323504)

        with patch.object(
            policy,
            "_enumerate_town_needs",
            return_value=[TownNeed(STORE_HOME, "equipment-catalog", "home-first")],
        ):
            for _ in range(TOWN_STOP_PASS_LIMIT):
                policy._report_town_stop_pass(
                    snapshot, STORE_HOME, goal_satisfied=False
                )

        self.assertIn(STORE_HOME, policy._town_errand_plan.blocked_this_visit)
        policy._town_errand_plan.index = 0
        key = self._post_atomic(
            policy, self._entrance_snapshot(self._real_pack(target)), target
        )

        self.assertEqual(key, WAIT_KEY)

    def test_warrior_incomplete_scan_does_not_emit_unbound_deposit(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=40, name="surplus arrows")
        policy._equipment_catalog.home_scan_complete = False
        home = self._snapshot(self._real_pack(target))

        with (
            patch.object(policy, "_find_home_deposit", return_value=target),
            patch.object(policy, "_home_deposit_key") as deposit_key,
        ):
            policy._shop(home)

        deposit_key.assert_not_called()

    def test_pending_home_operation_never_waits_inside(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=40, name="surplus arrows")
        approach = self._entrance_snapshot(self._real_pack(target))
        home = self._snapshot(self._real_pack(target), turn=approach.turn)
        self._post_atomic(policy, approach, target)
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: pending-home-operation routing is isolated from the downstream deposit decision
        policy._decide = Mock(return_value=SELL_KEY + "f40\r")

        for expected_key in ("df40\r\x1b", LEAVE_STORE_KEY, LEAVE_STORE_KEY):
            key = policy.choose_key(home)
            self.assertEqual(key, expected_key)
            self.assertNotIn(key, {WAIT_KEY, "\r"})
        policy._decide.assert_not_called()

    def test_quantity_is_present_only_for_multi_item_stack(self):
        policy = HengbotPolicy()
        single = item("f", TVAL_ARROW, 1, count=1, name="single arrow")
        stack = item("g", TVAL_ARROW, 2, count=7, name="seven arrows")

        single_key = self._post_atomic(
            policy, self._entrance_snapshot(self._real_pack(single)), single
        )
        policy._home_atomic_deposit_pending = None
        policy._home_entry_operation_posted = False
        stack_key = self._post_atomic(
            policy, self._entrance_snapshot(self._real_pack(stack)), stack
        )

        self.assertEqual(single_key, WAIT_KEY)
        self.assertEqual(stack_key, WAIT_KEY)

    def test_atomic_deposit_requires_player_on_home_entrance(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=1, name="single arrow")
        adjacent = replace(
            self._entrance_snapshot(self._real_pack(target)),
            player=player(45, 122, class_id=PLAYER_CLASS_WARRIOR),
        )

        policy._shopping_approach_store_type = STORE_HOME
        with patch.object(policy, "_find_home_deposit", return_value=target):
            self.assertIsNone(
                policy._atomic_home_deposit_key(adjacent, Position(45, 123))
            )
        self.assertFalse(policy._home_entry_operation_posted)

    def test_already_inside_without_posted_operation_leaves_not_deposits(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=40, name="surplus arrows")
        home = self._snapshot(self._real_pack(target))
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: already-inside atomic routing is isolated from the downstream deposit decision
        policy._decide = Mock(return_value=SELL_KEY + "f40\r")

        self.assertEqual(policy.choose_key(home), policy_module.LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:scan-complete-from-open-page")

    def test_real_pack_teleport_and_recall_slots_cannot_be_side_effect_deposits(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=40, name="surplus arrows")
        approach = self._entrance_snapshot(self._real_pack(target))
        home = self._snapshot(self._real_pack(target))
        atomic = self._post_atomic(policy, approach, target)
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: real-pack side-effect guarding is isolated from the downstream deposit decision
        policy._decide = Mock(return_value=SELL_KEY + "f40\r")

        keys = [atomic, *(policy.choose_key(home) for _ in range(4))]

        self.assertTrue(all("dd" not in key and "de" not in key for key in keys))
        self.assertEqual(sum("df40\r" in key for key in keys), 1)

    def test_atomic_post_is_followed_directly_by_outside_observation(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=1, name="single arrow")
        entrance = self._entrance_snapshot(self._real_pack(target))
        outside = self._snapshot(
            self._real_pack(), at_home=False, turn=entrance.turn + 1
        )

        self.assertEqual(self._post_atomic(policy, entrance, target), WAIT_KEY)
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: atomic-post observation ordering is isolated from the downstream town decision
        policy._decide = Mock(return_value=WAIT_KEY)
        self.assertEqual(policy.choose_key(outside), "")
        policy._decide.assert_not_called()
        self.assertIsNotNone(policy._home_atomic_deposit_pending)

    def test_atomic_latch_survives_interleaved_outside_snapshot_until_confirmed(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=1, name="single arrow")
        entrance = self._entrance_snapshot(self._real_pack(target))
        unchanged = self._snapshot(
            self._real_pack(target), at_home=False, turn=entrance.turn + 1
        )

        self._post_atomic(policy, entrance, target)
        pending = policy._home_atomic_deposit_pending
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: unchanged-snapshot latch retention is isolated from the downstream town decision
        policy._decide = Mock(return_value=WAIT_KEY)
        policy.choose_key(unchanged)

        self.assertTrue(policy._home_entry_operation_posted)
        self.assertEqual(policy._home_atomic_deposit_pending[:3], pending[:3])
        self.assertEqual(policy._home_atomic_deposit_pending[3], 0)

        confirmed = replace(
            unchanged,
            turn=unchanged.turn + 1,
            inventory=self._real_pack(),
        )
        policy._store_visit = None
        policy.choose_key(confirmed)
        self.assertFalse(policy._home_entry_operation_posted)
        self.assertIsNone(policy._home_atomic_deposit_pending)

    def test_same_turn_home_leave_does_not_refile_atomic_deposit(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=1, name="single arrow")
        entrance = self._entrance_snapshot(self._real_pack(target))
        unchanged = self._snapshot(
            self._real_pack(target), at_home=False, turn=entrance.turn
        )

        self._post_atomic(policy, entrance, target)
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
        policy._store_leave_inflight = (
            policy._decision_sequence,
            entrance.turn,
            STORE_HOME,
        )
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: observed-home-leave latch release is isolated from the downstream town decision
        policy._decide = Mock(return_value=WAIT_KEY)
        policy.choose_key(unchanged)

        self.assertIsNotNone(policy._home_atomic_deposit_pending)
        self.assertEqual(policy._home_atomic_deposit_pending[3], 0)
        self.assertIsNone(policy.consume_pending_home_visit_report())

    def test_home_step_off_blocks_atomic_entry_on_same_turn_snapshot(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=1, name="single arrow")
        entrance = self._entrance_snapshot(self._real_pack(target), turn=1007134)
        entrance = replace(
            entrance,
            grids={**entrance.grids, Position(44, 124): grid(44, 124)},
        )
        policy._last_snapshot_was_store = True
        policy.last_reason = "home:stale-deposit-reason"
        policy._floor_t = {(44, 124), (45, 122)}

        step = policy._shopping_approach_step(entrance, STORE_HOME)
        self.assertIsNotNone(step)
        self.assertNotEqual(step, entrance.player.position)
        self.assertIsNotNone(policy._store_entrance_step_off)
        armed_sequence = policy._decision_sequence

        same_decision = HengbotPolicy()
        same_decision._last_snapshot_was_store = True
        same_decision.last_reason = "home:stale-deposit-reason"
        same_decision._floor_t = {(44, 124), (45, 122)}
        same_step = same_decision._shopping_approach_step(entrance, STORE_HOME)
        with patch.object(same_decision, "_find_home_deposit", return_value=target):
            same_key = same_decision._shopping_approach_key(
                entrance, same_step, "shop:travel"
            )
        self.assertEqual(same_key, WAIT_KEY)
        self.assertIsNotNone(same_decision._home_atomic_deposit_pending)

        policy._decision_sequence += 1
        with patch.object(policy, "_find_home_deposit", return_value=target):
            key = policy._shopping_approach_key(entrance, step, "shop:travel")

        self.assertIsInstance(key, str)
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertIsNone(policy._store_visit.operation_key)
        self.assertEqual(
            policy._store_entrance_step_off,
            (armed_sequence, entrance.turn, entrance.player.position),
        )

        adjacent = replace(
            entrance,
            player=replace(entrance.player, position=step),
            turn=entrance.turn + 1,
        )
        policy._shopping_approach_step(adjacent, STORE_HOME)
        self.assertIsNone(policy._store_entrance_step_off)

    def test_missing_atomic_deposit_clears_stale_reason(self):
        policy = HengbotPolicy()
        entrance = self._entrance_snapshot(self._real_pack())
        policy._shopping_approach_store_type = STORE_HOME
        policy.last_reason = "home:stale-deposit-reason"

        self.assertIsNone(
            policy._atomic_home_deposit_key(entrance, entrance.player.position)
        )
        self.assertEqual(policy.last_reason, "")

    def test_unobserved_atomic_deposit_is_visibly_abandoned_at_bound(self):
        policy = HengbotPolicy()
        target = item("f", TVAL_ARROW, 1, count=84, name="surplus arrows")
        entrance = self._entrance_snapshot(self._real_pack(target), turn=500)
        knowledge_before = policy._home_knowledge_current

        self.assertEqual(
            self._post_atomic(policy, entrance, target), WAIT_KEY
        )
        policy._store_visit = None
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: bounded abandonment is isolated from unrelated downstream town routing
        policy._decide = Mock(return_value=WAIT_KEY)
        for offset in range(1, STORE_STUCK_LIMIT + 1):
            policy.choose_key(self._snapshot(
                self._real_pack(target), at_home=False, turn=500 + offset
            ))

        self.assertFalse(policy._home_entry_operation_posted)
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertEqual(policy._home_knowledge_current, knowledge_before)
        self.assertIn(
            policy._item_signature(target), policy._home_rejected_deposits
        )
        report = policy.consume_pending_home_visit_report()
        self.assertIn("unfulfilled", report)

    def test_real_capture_three_progress_leaves_keep_home_stop_available(self):
        policy = HengbotPolicy()
        snapshot = self._entrance_snapshot(self._real_pack(), turn=2247201)
        home = self._snapshot(self._real_pack(), turn=2247202)
        policy._equipment_transaction_session = SimpleNamespace(
            executable=True,
            required_context="home",
            pending_action=None,
            current_action=None,
        )
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_HOME)
        policy._equipment_transaction_session = None
        policy._equipment_catalog.home_scan_complete = True

        policy._home_entry_operation_posted = True
        with patch.object(policy, "_home_owner_goal_pending", return_value=True):
            for _ in range(3):
                self.assertEqual(policy.choose_key(home), LEAVE_STORE_KEY)
                self.assertEqual(
                    policy.last_reason, "home:leave-after-one-operation"
                )

        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 3
        )
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(policy._town_errand_plan.index, 0)
        self.assertIsNotNone(policy._next_required_store_type(snapshot))
        self.assertNotEqual(
            policy._town_blocked_reason, "departure-unsatisfiable"
        )

        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False
        )
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 3
        )

    def test_transaction_home_route_rejects_non_home_approach_target(self):
        policy = HengbotPolicy()
        snapshot = self._entrance_snapshot(self._real_pack())
        policy._equipment_transaction_session = SimpleNamespace(
            executable=True,
            required_context="home",
            pending_action=None,
            current_action=None,
        )
        policy._shopping_approach_store_type = STORE_GENERAL

        with (
            # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
            patch.object(policy, "_prepare_equipment_optimization"),
            patch.object(
                policy, "_shopping_approach_step", return_value=Position(45, 84)
            ),
            patch.object(policy, "_block_equipment_transaction") as block,
            patch.object(policy, "_shopping_approach_key") as approach_key,
        ):
            key = policy._equipment_transaction_town_key(snapshot)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "equipment-transaction:home-route-unavailable"
        )
        block.assert_called_once_with("home-route-unavailable")
        approach_key.assert_not_called()

    def test_three_deposits_use_three_entries_and_finish(self):
        policy = HengbotPolicy()
        targets = [
            item(slot, TVAL_ARROW, sval, count=40, name=f"surplus-{slot}")
            for slot, sval in zip("fgh", (1, 2, 3))
        ]
        remaining = self._real_pack(*targets)
        operations = []

        for target in targets:
            approach = self._entrance_snapshot(remaining)
            operations.append(self._post_atomic(policy, approach, target))
            remaining = [item_ for item_ in remaining if item_.slot != target.slot]
            outside = self._snapshot(remaining, at_home=False, turn=approach.turn + 1)
            # TEST_FAKERY_LINT_ALLOW: public-path-replaced: multi-deposit entry accounting is isolated from the downstream outside decision
            policy._decide = Mock(return_value=WAIT_KEY)
            policy.choose_key(outside)

        self.assertEqual(
            operations,
            [WAIT_KEY, WAIT_KEY, WAIT_KEY],
        )
        self.assertEqual([item_.slot for item_ in remaining], ["d", "e"])

    def test_pending_withdraw_hold_clears_on_turn_advance_without_loop(self):
        policy = HengbotPolicy()
        entrance = self._entrance_snapshot([], turn=700)
        seed_character_calibration(policy, entrance)
        target = store_item("a", TVAL_POTION, 1901, name="bounded target")
        policy._home_atomic_withdraw_pending = (
            policy._item_signature(target), 0, target, 1
        )
        policy._home_atomic_withdraw_posted_turn = 700

        self.assertEqual(policy.choose_key(entrance), LEAVE_STORE_KEY)
        self.assertEqual(
            policy.last_reason, "home:atomic-withdraw-await-confirmation"
        )
        advanced = replace(entrance, turn=701)
        policy.choose_key(advanced)
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertNotEqual(
            policy.last_reason, "home:atomic-withdraw-await-confirmation"
        )

    def test_pending_withdraw_hold_never_outranks_visible_hostile(self):
        policy = HengbotPolicy()
        entrance = self._entrance_snapshot([], turn=710)
        seed_character_calibration(policy, entrance)
        target = store_item("a", TVAL_POTION, 1902, name="danger target")
        policy._home_atomic_withdraw_pending = (
            policy._item_signature(target), 0, target, 1
        )
        policy._home_atomic_withdraw_posted_turn = 710
        threatened = replace(
            entrance,
            visible_monsters=[hostile(
                1, 45, 122, max_melee_damage=entrance.player.max_hp
            )],
        )

        key = policy.choose_key(threatened)

        self.assertNotEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "emergency:cornered-attack")

    def test_pending_withdraw_hold_is_legitimate_town_progress(self):
        policy = HengbotPolicy()
        entrance = self._entrance_snapshot([], turn=720)
        seed_character_calibration(policy, entrance)
        target = store_item("a", TVAL_POTION, 1903, name="progress target")
        policy._home_atomic_withdraw_pending = (
            policy._item_signature(target), 0, target, 1
        )
        policy._home_atomic_withdraw_posted_turn = 720

        self.assertEqual(policy.choose_key(entrance), LEAVE_STORE_KEY)
        self.assertEqual(policy._town_progress_invariant_defect, {})
        self.assertIsNone(policy._town_blocked_reason)
        self.assertNotIn("TOWN_OSCILLATION_DEFECT", policy.last_reason)

    def test_home_entrance_control_without_pending_is_unchanged(self):
        policy = HengbotPolicy()
        entrance = self._entrance_snapshot([], turn=730)
        seed_character_calibration(policy, entrance)

        key = policy.choose_key(entrance)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "shop:travel:await-entry")
        self.assertIsNone(policy._home_atomic_withdraw_pending)

class HomePageAdvanceCurrencyTest(unittest.TestCase):
    """Regressions for the 2026-08-02 20:03 turn-2459752 page-advance race.

    home:scan-catalog-page posted SPACE inside the Home; two seconds later
    equipment-transaction:withdraw composed ``pJ\\r`` from a 52-item page-1
    observation that predated the unobserved advance, while the game showed the
    30-item page 2 whose letters stop at ``D``.  The withdraw never confirmed
    and the stall quarantined the only resist_chaos source.  A key may only be
    composed from a page observation proven current: identity change, the
    single-page message, or the version-probe banner.

    The incident regression doubles as the two-page completion regression: its
    final decisions drive the content-addressed page seek and the withdraw
    composition from the proven-current page.
    """

    RING_NAME = "Ring of Law (+5,+0) [+5] (+2)"

    @staticmethod
    def _page_letter(index):
        # index_to_label == I2A: a..z then A..Z, page-relative.
        return chr(ord("a") + index) if index < 26 else chr(ord("A") + index - 26)

    def _ring(self):
        return store_item(
            "J", TVAL_RING, 4, name=self.RING_NAME, known=True,
            fully_known=True, is_equipment=True, known_flags=frozenset({62}),
        )

    def _page_one(self):
        # 52 stacks with the ring at page-relative letter J (index 35), the
        # letter layout the surviving flight-recorder pages show.
        return [
            self._ring() if self._page_letter(index) == "J" else store_item(
                self._page_letter(index), TVAL_FOOD, 30 + index % 5,
                name=f"stored ration {index}", price=0,
            )
            for index in range(52)
        ]

    def _page_two(self):
        # The 30-item second page: letters restart at a and stop at D.
        return [
            store_item(
                self._page_letter(index), TVAL_FOOD, 30 + index % 5,
                name=f"late stored ration {index}", price=0,
            )
            for index in range(30)
        ]

    def _snapshot(self, page, *, turn=2459752, messages=()):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=turn,
            floor_key=(0, 0, 0),
            inventory=[
                item("d", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=14, known=True),
            ],
            equipment=[
                item(
                    "main_hand", 23, 4, name="long sword", known=True,
                    fully_known=True, is_equipment=True,
                ),
                item(
                    "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000,
                    is_equipment=True, known=True, fully_known=True,
                ),
            ],
            store=StoreState(
                store_type=STORE_HOME, items=list(page),
                stock_num=82 if len(page) != 12 else 12,
                page_top=52 if len(page) == 30 else 0,
                page_size=52,
            ),
            messages=tuple(messages),
        )

    def _withdraw_session(self):
        identity = policy_module.equipment_identity(self._ring())
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "withdraw",
            "home:incident:0", item_identity=identity,
        )
        return policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 23)
        ), action

    def _one_page(self):
        return [
            store_item(
                chr(ord("a") + index), TVAL_FOOD, 30 + index % 5,
                name=f"stored ration {index}", price=0,
            )
            for index in range(12)
        ]

class UnknownTargetLoadoutSurplusTest(unittest.TestCase):
    """Irreversible target-dependent surplus decisions require a real target."""

    @staticmethod
    def _preparation(*, known):
        return SimpleNamespace(
            blockers=() if known else ("no-valid-loadout",),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(
                best=(
                    SimpleNamespace(loadout=SimpleNamespace(item_ids=frozenset()))
                    if known
                    else None
                )
            ),
        )

    @staticmethod
    def _store_snapshot(inventory, store_type):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=21922),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=2459999,
            floor_key=(0, 0, 0),
            inventory=list(inventory),
            equipment=[],
            store=StoreState(store_type=store_type, items=[]),
        )

    @staticmethod
    def _ring():
        return item(
            "b", TVAL_RING, 56,
            name="Ring of Law (+5,+0) [+5] (+2)",
            known=True, fully_known=True, is_equipment=True,
            known_flags=frozenset({62}),
        )

    def test_incident_shape_no_valid_loadout_does_not_sell_expensive_ring(self):
        policy = HengbotPolicy()
        snapshot = self._store_snapshot([self._ring()], STORE_MAGIC)
        policy.prime(snapshot)
        policy._equipment_optimization_preparation = self._preparation(known=False)

        key = policy._shop(snapshot)

        self.assertEqual(
            key, LEAVE_STORE_KEY,
            "naked no-valid-loadout incident replay sold the 13,261-gold "
            f"Ring of Law with {key!r}",
        )
        self.assertEqual(policy.last_reason, "shop:leave")

    def test_known_target_still_sells_expensive_unwanted_ring(self):
        policy = HengbotPolicy()
        snapshot = self._store_snapshot([self._ring()], STORE_MAGIC)
        policy.prime(snapshot)
        preparation = self._preparation(known=True)
        policy._equipment_optimization_preparation = preparation

        def prepare(*_args, **_kwargs):
            policy._equipment_optimization_preparation = preparation
            return preparation

        with patch.object(policy, "_prepare_equipment_optimization", side_effect=prepare):
            key = policy._shop(snapshot)

        self.assertEqual(key, "{b@0\r")

    def test_posted_deposit_does_not_reopen_sale_after_target_becomes_unknown(self):
        policy = HengbotPolicy()
        ring = self._ring()
        home = self._store_snapshot([ring], STORE_HOME)
        policy.prime(home)
        policy._equipment_optimization_preparation = self._preparation(known=True)
        self.assertEqual(policy._home_deposit_key(home, ring), "db")

        policy._equipment_optimization_preparation = self._preparation(known=False)
        shop = replace(home, store=StoreState(STORE_MAGIC, []))
        key = policy._shop(shop)

        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:leave")

    def test_calibration_deposit_does_not_arm_unknown_target_sale(self):
        policy = HengbotPolicy()
        ring = self._ring()
        home = self._store_snapshot([ring], STORE_HOME)
        policy.prime(home)
        policy._calibration_phase = "deposit"
        self.assertIs(policy._find_home_deposit(home), ring)
        self.assertEqual(policy._home_deposit_key(home, ring), "db")

        policy._calibration_phase = None
        policy._equipment_optimization_preparation = self._preparation(known=False)
        shop = replace(home, store=StoreState(STORE_MAGIC, []))
        key = policy._shop(shop)

        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:leave")

    def test_deposit_rejection_guard_exits_without_surplus_carve_out(self):
        policy = HengbotPolicy()
        ring = self._ring()
        home = self._store_snapshot([ring], STORE_HOME)
        policy.prime(home)
        policy._equipment_optimization_preparation = self._preparation(known=True)

        keys = [
            policy._home_deposit_key(home, ring)
            for _ in range(STORE_STUCK_LIMIT + 1)
        ]

        self.assertEqual(keys[-1], LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:deposit-rejected")
        self.assertIn(policy._item_signature(ring), policy._home_rejected_deposits)
        self.assertFalse(hasattr(policy, "_target_dependent_deposit_inflight"))

    def test_unknown_target_does_not_block_book_or_low_level_consumable_sales(self):
        book_policy = HengbotPolicy()
        book = item(
            "c", TVAL_CHAOS_BOOK, 2, name="Chaos spellbook", known=True
        )
        book_snapshot = self._store_snapshot([book], STORE_MAGIC)
        book_policy.prime(book_snapshot)
        book_policy._equipment_optimization_preparation = self._preparation(known=False)
        self.assertEqual(
            _public_shop_inner(self, book_policy, book_snapshot),
            "{c@0\r",
        )
        self.assertEqual(book_policy.last_reason, "shop:batch-inscribe")

        potion_policy = HengbotPolicy()
        potion = item(
            "d", TVAL_POTION, SV_POTION_SLEEP,
            name="Potion of Sleep", known=True, aware=True,
        )
        potion_snapshot = self._store_snapshot([potion], STORE_ALCHEMIST)
        potion_policy.prime(potion_snapshot)
        potion_policy._equipment_optimization_preparation = self._preparation(known=False)
        self.assertEqual(
            _public_shop_inner(self, potion_policy, potion_snapshot),
            "{d@0\r",
        )
        self.assertEqual(
            potion_policy.last_reason, "shop:batch-inscribe"
        )

    def test_calibration_states_and_missing_result_are_unknown_and_can_exit(self):
        policy = HengbotPolicy()
        snapshot = self._store_snapshot([self._ring()], STORE_MAGIC)
        policy.prime(snapshot)
        states = (
            None,
            SimpleNamespace(blockers=("calibration-required",), result=None),
            SimpleNamespace(blockers=(), result=SimpleNamespace(best=None)),
        )
        for preparation in states:
            policy._equipment_optimization_preparation = preparation
            self.assertFalse(policy._target_loadout_known())
            self.assertFalse(
                policy._home_deposit_candidate(self._ring(), snapshot)
            )
            self.assertEqual(policy.choose_key(snapshot), LEAVE_STORE_KEY)

        policy._equipment_optimization_preparation = self._preparation(known=True)
        policy._calibration_phase = "capture"
        self.assertFalse(policy._target_loadout_known())
        self.assertFalse(policy._home_deposit_candidate(self._ring(), snapshot))
        self.assertEqual(policy.choose_key(snapshot), LEAVE_STORE_KEY)

    def test_exhausted_depth_fallback_none_fails_closed(self):
        policy = HengbotPolicy()
        snapshot = self._store_snapshot([self._ring()], STORE_MAGIC)
        policy.prime(snapshot)
        failed = self._preparation(known=False)
        policy._equipment_optimization_preparation = failed
        policy._equipment_optimization_depth = Mock(return_value=3)
        policy._next_required_store_type = Mock(return_value=None)
        policy._prepare_equipment_optimization = Mock(return_value=failed)

        self.assertFalse(hasattr(policy, "_activate_loadout_depth_fallback"))
        self.assertIs(policy._equipment_optimization_preparation, failed)
        self.assertFalse(policy._target_loadout_known())
        self.assertFalse(policy._home_deposit_candidate(self._ring(), snapshot))

class RearmAndBreakoutRegressionTest(unittest.TestCase):
    @staticmethod
    def _withdraw_alternation_snapshots():
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "town-withdraw-alternation-entrance-cycle-20260825.jsonl.gz"
        )
        with gzip.open(fixture, "rt", encoding="utf-8") as stream:
            return [parse_snapshot(json.loads(line)) for line in stream]

    @staticmethod
    def _captured_withdraw_policy():
        policy = HengbotPolicy()
        target = item(
            "a", policy_module.TVAL_SOFT_ARMOR, 99, name="Home target",
            known=True, fully_known=True, is_equipment=True,
        )
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "withdraw",
            "home-target",
            item_identity=policy_module.equipment_identity(target),
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 0)
            )
        )
        policy.consume_home_knowledge((target,))
        policy._home_page_size = 12
        return policy, target

    def test_captured_repetition_entrance_composes_withdraw_before_step_off(self):
        snapshots = self._withdraw_alternation_snapshots()
        policy, _target = self._captured_withdraw_policy()
        entrance = snapshots[0].player.position
        policy._shopping_approach_store_type = STORE_HOME
        policy._shopping_approach_goal = entrance
        policy._town_blocked_reason = "repetition"
        policy._floor_key = snapshots[0].floor_key
        policy._last_snapshot_was_store = True
        policy._town_errand_plan = TownErrandPlan([STORE_HOME])

        key = policy.choose_key(snapshots[0])

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "equipment-transaction:atomic-withdraw")
        self.assertEqual(policy._store_visit.operation_key, "pa\x1b")
        self.assertNotIn(key, set("12346789"))
        expectation = policy._owner_expectations._pending["equipment-transaction"]
        self.assertEqual(
            expectation.expected_changes,
            frozenset({"inventory", "equipment", "store_type", "gold"}),
        )
        moved = replace(
            snapshots[0],
            player=replace(snapshots[0].player, position=Position(44, 123)),
        )
        self.assertFalse(policy._owner_may_select(moved, "equipment-transaction"))

    def test_atomic_withdraw_leave_attempts_block_on_third_dispatch(self):
        snapshot = self._withdraw_alternation_snapshots()[0]
        policy, target = self._captured_withdraw_policy()
        inside = replace(
            snapshot,
            store=StoreState(
                STORE_HOME,
                [store_item(
                    "a", target.tval, target.sval, name=target.name,
                    known=True, fully_known=True, is_equipment=True,
                )],
            ),
        )
        reasons = []
        policy._owner_expectations.release("equipment-transaction")
        policy._last_snapshot_was_store = False
        policy._store_visit = None
        policy.choose_key(inside)
        reasons.append(policy.last_reason)
        policy._owner_expectations.release("equipment-transaction")
        policy._last_snapshot_was_store = False
        policy._store_visit = None
        policy.choose_key(replace(inside, turn=inside.turn + 1))
        reasons.append(policy.last_reason)
        policy._owner_expectations.release("equipment-transaction")
        policy._last_snapshot_was_store = False
        policy._store_visit = None
        policy.choose_key(replace(inside, turn=inside.turn + 2))
        reasons.append(policy.last_reason)

        self.assertEqual(
            reasons[:2],
            ["equipment-transaction:leave-for-atomic-withdraw"] * 2,
        )
        self.assertEqual(
            reasons[2], "equipment-transaction:atomic-withdraw-unreachable"
        )
        self.assertEqual(
            policy._town_blocked_reason,
            "equipment-transaction:atomic-withdraw-unreachable",
        )

    def test_three_successful_atomic_withdraw_compositions_reset_leave_bound(self):
        snapshot = self._withdraw_alternation_snapshots()[0]
        policy, target = self._captured_withdraw_policy()
        identity = policy_module.equipment_identity(target)
        actions = tuple(
            policy_module.EquipmentTransaction(
                policy_module.PHASE_HOME_PREPARE,
                "withdraw",
                f"home-target-{index}",
                item_identity=identity,
            )
            for index in range(3)
        )
        session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan(actions, (), 0)
        )
        policy._equipment_transaction_session = session
        policy._shopping_approach_store_type = STORE_HOME
        policy._home_page_size = 12

        composed = []
        for index in range(3):
            policy._equipment_atomic_withdraw_leave_count = 2
            policy._home_atomic_withdraw_pending = None
            session.discard_prepared()
            session.index = index
            composed.append(
                policy._atomic_home_withdraw_key(
                    snapshot, snapshot.player.position
                )
            )
            self.assertEqual(policy._equipment_atomic_withdraw_leave_count, 0)

        session.index = len(actions)
        self.assertEqual(composed, [WAIT_KEY] * 3)
        self.assertTrue(session.complete)

    def test_equipment_expectation_ignores_position_only_change(self):
        snapshot = self._withdraw_alternation_snapshots()[2]
        policy, _target = self._captured_withdraw_policy()
        policy._shopping_approach_store_type = STORE_HOME
        policy._shopping_approach_goal = snapshot.player.position
        policy._town_errand_plan = TownErrandPlan([STORE_HOME])
        policy.choose_key(snapshot)
        pending = policy._owner_expectations._pending["equipment-transaction"]
        self.assertEqual(
            pending.expected_changes,
            frozenset({"inventory", "equipment", "store_type", "gold"}),
        )
        moved = replace(
            snapshot,
            player=replace(snapshot.player, position=Position(44, 123)),
        )
        self.assertFalse(policy._owner_may_select(moved, "equipment-transaction"))

    def test_empty_body_requests_home_withdraw_then_wield_despite_quarantine(self):
        snapshot = Snapshot(
            replace(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=8),
                stat_cur=(18, 10, 10, 18), stat_use=(18, 10, 10, 18),
                melee_skill=60, saving_skill=30,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            equipment=[item(
                "main_hand", TVAL_SWORD, 1, name="short sword",
                known=True, fully_known=True, is_equipment=True,
                damage_dice_num=1, damage_dice_sides=6,
            )],
        )
        armour = store_item(
            "a", policy_module.TVAL_SOFT_ARMOR, 2,
            name="Leather Scale Mail [14,+0]", known=True,
            fully_known=True, is_equipment=True, ac=14,
        )
        policy = HengbotPolicy()
        seed_character_calibration(policy, snapshot)
        policy.consume_home_knowledge((armour,))
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        home_owned = next(
            owned for owned in policy._equipment_catalog.items
            if owned.origin == "home"
        )
        policy._equipment_transaction_failed_items.add(home_owned.id)

        policy._request_priority_body_rearm(snapshot)

        session = policy._equipment_transaction_session
        self.assertIsNotNone(session)
        self.assertEqual(
            [(action.kind, action.target_slot) for action in session.plan.actions],
            [("withdraw", None), ("equip", "body")],
        )
        self.assertEqual(session.plan.actions[0].item_id, home_owned.id)
        self.assertGreater(armour.ac + armour.to_a, snapshot.player.ac)

        policy._equipment_transaction_session = None
        policy._request_priority_body_rearm(snapshot)
        self.assertIsNone(policy._equipment_transaction_session)

    def test_boxed_breakout_uses_distinct_landmark_travel_not_wait(self):
        position = Position(119, 31)
        snapshot = Snapshot(
            player(position.y, position.x),
            {position: replace(grid(position.y, position.x), store_number=STORE_GENERAL)},
            [], floor_key=(0, 0, 0), town_flag=True,
        )
        policy = HengbotPolicy()
        macro = "\x1b`n7."
        policy.last_reason = "breakout:least-visited"
        with patch.object(policy, "_shopping_approach_step", return_value=Position(1, 1)), patch.object(
            policy, "_shopping_approach_key", return_value=macro
        ):
            key = policy._town_procurement_decision(snapshot, policy_module.WAIT_KEY)

        self.assertEqual(key, macro)
        self.assertNotEqual(key, policy_module.WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "town-progress-invariant:boxed-breakout-travel"
        )
