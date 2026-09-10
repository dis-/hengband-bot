from __future__ import annotations
import ast
import base64
import gzip
import inspect
import json
import os
import pickle
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
import test_policy_town as town_fixture
import absorbing_state_catalog as absorbing_catalog
from test_policy import FOOD, REAL_QUEST_DEFINITIONS
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

class OverflowDisposalTest(unittest.TestCase):
    def _town(self, inventory):
        return Snapshot(
            player(10, 10, food=6000),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(0, 0, 0),
            inventory=inventory,
        )

    @staticmethod
    def _inventory(count):
        return [
            item(chr(ord("a") + i), TVAL_STAFF, i, name=f"item-{i}", charges=5)
            for i in range(count)
        ]

    def test_destroys_a_device_but_never_the_recall_scroll(self):
        # Essentials (here the Word of Recall at slot 'a') are never the overflow
        # victim — the first non-essential device is dropped instead.
        recall = item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        staves = [
            item(chr(ord("b") + i), TVAL_STAFF, 3, name="staff")
            for i in range(PACK_CAPACITY - 1)
        ]
        pol = HengbotPolicy()
        key = pol.choose_key(self._town([recall] + staves))
        self.assertEqual(pol.last_reason, "town:destroy-overflow")
        self.assertEqual(key, "01kb")

    def test_preserves_charged_identify_staff_during_overflow_disposal(self):
        identify = item(
            "a", TVAL_STAFF, SV_STAFF_IDENTIFY,
            charges=9, name="Staff of Identify",
        )
        junk = [
            item(chr(ord("b") + i), TVAL_STAFF, 3, name=f"junk-{i}")
            for i in range(PACK_CAPACITY - 1)
        ]

        pol = HengbotPolicy()
        key = pol.choose_key(self._town([identify, *junk]))

        self.assertEqual(pol.last_reason, "town:destroy-overflow")
        self.assertEqual(key, "01kb")

    def test_preserves_entire_detection_stack_when_only_part_is_surplus(self):
        detection = item(
            "a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            count=7, name="Detect Treasure",
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_detection_scroll_target = lambda snapshot: 4
        snapshot = self._town([detection])

        self.assertEqual(policy._retention_surplus(snapshot, detection), 3)
        self.assertIsNone(policy._overflow_disposal_item(snapshot))

    def test_verified_destroy_rejects_partially_reserved_stack(self):
        detection = item(
            "a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            count=7, name="Detect Treasure",
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_detection_scroll_target = lambda snapshot: 4
        snapshot = self._town([detection])

        key = policy._verified_destroy_key(
            snapshot,
            lambda current: detection,
            "town:destroy-overflow",
        )

        self.assertIsNone(key)
        self.assertNotEqual(policy.last_reason, "town:destroy-overflow")

    def test_destroys_junk_until_departure_free_slot_requirement_is_met(self):
        used = PACK_CAPACITY - MIN_FREE_PACK_SLOTS + 1
        staves = [
            item(chr(ord("a") + i), TVAL_STAFF, 3, name=f"staff-{i}")
            for i in range(used)
        ]

        pol = HengbotPolicy()
        key = pol.choose_key(self._town(staves))

        self.assertEqual(pol.last_reason, "town:destroy-overflow")
        self.assertEqual(key, "01ka")

    def test_four_slots_are_terminally_ready_when_no_safe_route_can_free_fifth(self):
        snapshot = self._town(self._inventory(PACK_CAPACITY - 4))
        policy = HengbotPolicy()

        policy._terminal_pack_space_signature = policy._town_pack_space_signature(
            snapshot
        )
        with patch.object(
            policy,
            "_next_required_store_type",
            side_effect=AssertionError("readiness must not call the town router"),
        ):
            self.assertTrue(policy._town_pack_space_ready(snapshot))

    def test_four_slots_are_not_ready_before_terminal_pipeline_confirmation(self):
        snapshot = self._town(self._inventory(PACK_CAPACITY - 4))
        policy = HengbotPolicy()

        self.assertFalse(policy._town_pack_space_ready(snapshot))

    def test_optimizer_pack_space_block_keeps_current_loadout_at_terminal_four(self):
        worn = [
            item("main_hand", TVAL_SWORD, 1, is_equipment=True),
            item("light", TVAL_LITE, SV_LITE_TORCH, is_equipment=True),
            item("body", 36, 1, is_equipment=True),
            item("head", 32, 1, is_equipment=True),
            item("arms", 31, 1, is_equipment=True),
        ]
        snapshot = replace(
            self._town(self._inventory(PACK_CAPACITY - 4)), equipment=worn
        )
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, class_id=PLAYER_CLASS_WARRIOR),
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        current = current_loadout(policy._equipment_catalog.items)
        target = Loadout((), "empty")
        transaction = policy_module.plan_equipment_transactions(
            policy._equipment_catalog.items, current, target,
            current_pack_items=len(snapshot.inventory), home_scan_complete=True,
        )
        self.assertTrue(transaction.actions)
        self.assertTrue(any(
            blocker.startswith("pack-space-required:")
            for blocker in transaction.blockers
        ))
        preparation = SimpleNamespace(
            blockers=transaction.blockers, ready=False, transaction=transaction,
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=target)),
        )
        seed_confirmed_loadout(policy, snapshot)

        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=preparation
        ), patch.object(
            policy, "_town_pack_space_ready", return_value=True
        ):
            self.assertTrue(policy._equipment_departure_ready(snapshot))

        preparation.result = None
        policy = HengbotPolicy()
        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=preparation
        ), patch.object(policy, "_town_pack_space_ready", return_value=True):
            self.assertFalse(policy._equipment_departure_ready(snapshot))

    def _incomplete_catalog_policy(self):
        policy = HengbotPolicy()
        # One Home item stuck as incomplete because it needs *Identify*.
        policy._equipment_catalog = SimpleNamespace(
            items=(SimpleNamespace(id="home:x:0", origin="home"),)
        )
        policy._identification_need = "full"
        policy._town_store_attempted = {STORE_ALCHEMIST}
        policy._home_candidate_waiting = False
        preparation = SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
            result=SimpleNamespace(incomplete_item_ids=frozenset({"home:x:0"})),
            ready=False,
            transaction=None,
        )
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[
                item("main_hand", TVAL_SWORD, 1, is_equipment=True),
                item("light", TVAL_LITE, SV_LITE_TORCH, is_equipment=True),
            ],
        )
        return policy, snapshot, preparation

    def test_unbuyable_identify_opens_confirmed_legal_escape_valve(self):
        policy, snapshot, preparation = self._incomplete_catalog_policy()
        seed_confirmed_loadout(policy, snapshot)
        # Alchemist already tried and holds no *Identify*: the need cannot be
        # satisfied this visit, so the escape valve must open (depart, retry
        # later) instead of waiting in town until the loop guard stops the bot.
        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=preparation
        ), patch.object(
            policy, "_find_identification_source", return_value=None
        ):
            self.assertTrue(policy._equipment_departure_ready(snapshot))

        refused = SimpleNamespace(
            blockers=preparation.blockers,
            result=None,
            ready=False,
            transaction=None,
        )
        policy = HengbotPolicy()
        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=refused
        ):
            self.assertFalse(policy._equipment_departure_ready(snapshot))

    def test_buyable_identify_keeps_incomplete_catalog_blocking(self):
        policy, snapshot, preparation = self._incomplete_catalog_policy()
        # A source IS obtainable: the need is still satisfiable, so the valve
        # must stay shut and the catalog remain a departure blocker.
        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=preparation
        ), patch.object(
            policy, "_find_identification_source",
            return_value=SimpleNamespace(slot="a"),
        ):
            self.assertFalse(policy._equipment_departure_ready(snapshot))

    def test_preserves_equipment_and_unidentified_consumables(self):
        # Home-depositable equipment and alchemist-sellable unknown scrolls have
        # a town economic path, so the overflow valve leaves them for those
        # actions rather than dropping them on the ground.
        gear = [
            item(chr(ord("a") + i), TVAL_RING, 0, is_equipment=True)
            for i in range(12)
        ]
        unknown = [
            item(chr(ord("m") + i), TVAL_SCROLL, 3, aware=False) for i in range(11)
        ]
        pol = HengbotPolicy()
        key = pol.choose_key(self._town(gear + unknown))
        self.assertNotEqual(pol.last_reason, "town:destroy-overflow")
        self.assertNotIn("\\d", key)

    def test_full_pack_destroys_boldness_before_returning(self):
        inventory = [item("a", TVAL_POTION, 28, name="Boldness")]
        inventory.extend(
            item(chr(ord("b") + i), TVAL_RING, 0, name=f"keep-{i}")
            for i in range(PACK_CAPACITY - 1)
        )
        snap = Snapshot(
            player(10, 10, food=6000),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "01ka")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_full_pack_destroys_cure_light_wounds(self):
        inventory = [item("a", TVAL_POTION, 34, name="Cure Light Wounds")]
        inventory.extend(
            item(chr(ord("b") + i), TVAL_RING, 0, name=f"keep-{i}")
            for i in range(PACK_CAPACITY - 1)
        )
        snap = Snapshot(
            player(10, 10, food=6000),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "01ka")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_town_compacts_surplus_diggers_before_departure(self):
        # Live regression: Home batching left 21/23 slots occupied, including
        # three shovels and a pick. Shed weaker diggers before any town departure.
        inventory = [
            item("a", TVAL_DIGGING, 1, name="shovel-1"),
            item("b", TVAL_DIGGING, 1, name="shovel-2"),
            item("c", TVAL_DIGGING, 4, name="pick"),
        ]
        inventory.extend(
            item(chr(ord("d") + i), TVAL_STAFF, i, name=f"keep-{i}", charges=1)
            for i in range(18)
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "01kb")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_town_compacts_ammo_when_no_launcher_is_owned(self):
        ammo = item("a", TVAL_ARROW, 4, name="arrows", count=14)
        filler = [
            item(chr(ord("b") + i), TVAL_STAFF, i, charges=1)
            for i in range(18)
        ]
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[ammo, *filler],
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "014ka")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_town_preserves_ammo_when_a_launcher_is_owned(self):
        ammo = item("a", TVAL_ARROW, 4, name="arrows", count=14)
        bow = item("b", TVAL_BOW, 12, name="short bow", is_equipment=True)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[ammo, bow],
        )

        self.assertIsNone(HengbotPolicy()._find_disposable_item(snap))

    def test_full_pack_destroys_new_disposable_items(self):
        cases = [
            item("a", TVAL_POTION, 11, name="Sleep"),
            item("a", TVAL_SCROLL, 30, name="Detect Invisible"),
            item("a", TVAL_LITE, SV_LITE_TORCH, name="empty torch", fuel=0),
            item("a", TVAL_BOTTLE, 1, name="Empty Bottle"),
        ]
        for disposable in cases:
            with self.subTest(item=disposable.name):
                filler = [
                    item(chr(ord("b") + i), TVAL_STAFF, i, name=f"filler-{i}")
                    for i in range(PACK_CAPACITY - 1)
                ]
                snap = Snapshot(
                    player(10, 10),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[disposable, *filler],
                )
                policy = HengbotPolicy()
                self.assertEqual(policy.choose_key(snap), "01ka")
                self.assertEqual(
                    policy.last_reason, "inventory:destroy-disposable-item"
                )

    def test_full_pack_force_destroys_an_entire_disposable_stack(self):
        disposable = item(
            "a", TVAL_POTION, 28, name="Boldness", count=3
        )
        filler = [
            item(chr(ord("b") + i), TVAL_RING, 0, name=f"keep-{i}")
            for i in range(PACK_CAPACITY - 1)
        ]
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[disposable, *filler],
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "03ka")
        self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")

    def test_full_pack_discards_average_or_cursed_pseudo_identified_items(self):
        for feeling in ("average", "cursed"):
            with self.subTest(feeling=feeling):
                disposable = item(
                    "a",
                    TVAL_RING,
                    0,
                    name=f"{feeling} ring",
                    pseudo_feeling=feeling,
                    is_equipment=True,
                )
                filler = [
                    item(chr(ord("b") + i), TVAL_STAFF, i, name=f"keep-{i}")
                    for i in range(PACK_CAPACITY - 1)
                ]
                snap = Snapshot(
                    player(10, 10),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[disposable, *filler],
                )

                policy = HengbotPolicy()
                self.assertEqual(policy.choose_key(snap), "01ka")
                self.assertEqual(
                    policy.last_reason, "inventory:destroy-disposable-item"
                )

    def test_full_pack_never_discards_a_bounty_from_pseudo_feeling(self):
        bounty = item(
            "a",
            TVAL_RING,
            0,
            pseudo_feeling="cursed",
            is_bounty=True,
        )
        filler = [
            item(chr(ord("b") + i), TVAL_STAFF, i, name=f"keep-{i}")
            for i in range(PACK_CAPACITY - 1)
        ]
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[bounty, *filler],
        )

        policy = HengbotPolicy()
        self.assertNotEqual(policy.choose_key(snap), "01ka")

    def test_does_not_destroy_unidentified_zero_fuel_torch(self):
        torch = item(
            "a", TVAL_LITE, SV_LITE_TORCH, name="unknown torch", known=False, fuel=0
        )
        filler = [
            item(chr(ord("b") + i), TVAL_STAFF, i, name=f"filler-{i}")
            for i in range(PACK_CAPACITY - 1)
        ]
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[torch, *filler],
        )
        self.assertNotEqual(HengbotPolicy().choose_key(snap), "01ka")

class LauncherEnchantTest(unittest.TestCase):
    @staticmethod
    def _captured_procurement_snapshot():
        fixture_path = (
            Path(__file__).parent
            / "fixtures"
            / "destroy-superior-digger-20260910.json.gz"
        )
        with gzip.open(fixture_path, "rt", encoding="utf-8") as stream:
            rows = json.load(stream)
        row = next(
            row for row in rows
            if row["decision"]["decision_sequence"] == 2107
        )
        return parse_snapshot(row["snapshot"], {})

    def _town(
        self, launcher=None, inventory=None, store=None, *, gold=4000
    ):
        equipment = [] if launcher is None else [launcher]
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory or [],
            equipment=equipment,
            store=store,
        )

    @staticmethod
    def _launcher(*, to_h=5, to_d=3, known=True, artifact=False):
        return item(
            "bow", TVAL_BOW, SV_BOW_SHORT, name="Short Bow",
            is_equipment=True, known=known, to_h=to_h, to_d=to_d,
            is_artifact=artifact,
        )

    @staticmethod
    def _stock():
        return StoreState(
            STORE_ALCHEMIST,
            [
                store_item(
                    "h", TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
                    name="Enchant Weapon To-Hit", price=200,
                ),
                store_item(
                    "i", TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
                    name="Enchant Weapon To-Dam", price=200,
                ),
            ],
        )

    def test_surplus_store_buys_one_scroll_for_each_needed_launcher_stat(self):
        captured = self._captured_procurement_snapshot()
        launcher = next(item for item in captured.equipment if item.is_launcher)
        policy = HengbotPolicy()
        first = replace(
            captured, inventory=[], equipment=[launcher], store=self._stock()
        )
        self.assertFalse(policy._town_departure_ready(first))
        self.assertEqual(
            policy._launcher_enchant_purchase(first).sval,
            SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
        )
        carried_hit = item(
            "h", TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
            name="Enchant Weapon To-Hit",
        )
        second = replace(first, inventory=[carried_hit])
        self.assertEqual(
            policy._launcher_enchant_purchase(second).sval,
            SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
        )

    def test_read_targets_equipped_launcher_and_bounds_failed_deltas(self):
        launcher = self._launcher()
        hit = item("h", TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_HIT)
        dam = item("i", TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_DAM)
        policy = HengbotPolicy()
        first = self._town(launcher, [hit, dam])

        self.assertEqual(policy._town_enchant_launcher_key(first), "rh/c")
        self.assertEqual(policy.last_reason, "town:enchant-launcher-tohit")
        # The scroll disappeared but the launcher did not improve: failure or a
        # wrong target. It must move to the other stat, never retry To-Hit.
        failed = self._town(launcher, [dam])
        policy._observe_launcher_enchant(failed)
        self.assertEqual(policy._town_enchant_launcher_key(failed), "ri/c")
        self.assertEqual(policy.last_reason, "town:enchant-launcher-todam")
        policy._observe_launcher_enchant(self._town(launcher))
        self.assertIsNone(policy._town_enchant_launcher_key(self._town(launcher)))

    def test_stats_above_nine_are_independently_skipped(self):
        launcher = self._launcher(to_h=10, to_d=3)
        policy = HengbotPolicy()
        snapshot = self._town(launcher, store=self._stock())
        with patch.object(policy, "_town_departure_ready", return_value=True):
            self.assertEqual(
                policy._launcher_enchant_purchase(snapshot).sval,
                SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
            )

    def test_poor_or_not_ready_town_does_not_buy_enchant_scrolls(self):
        launcher = self._launcher()
        policy = HengbotPolicy()
        poor = self._town(launcher, store=self._stock(), gold=3100)
        with patch.object(policy, "_town_departure_ready", return_value=True):
            self.assertIsNone(policy._launcher_enchant_purchase(poor))
        ready_gold = replace(poor, player=replace(poor.player, gold=4000))
        with patch.object(policy, "_town_departure_ready", return_value=False):
            self.assertEqual(
                policy._launcher_enchant_purchase(ready_gold).sval,
                SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
            )

    def test_artifact_unknown_or_missing_launcher_is_skipped(self):
        policy = HengbotPolicy()
        for launcher in (
            self._launcher(artifact=True),
            self._launcher(known=False),
            None,
        ):
            with self.subTest(launcher=launcher):
                snapshot = self._town(launcher, store=self._stock())
                with patch.object(policy, "_town_departure_ready", return_value=True):
                    self.assertIsNone(policy._launcher_enchant_purchase(snapshot))

    def _procurement_policy(self, snapshot):
        policy = HengbotPolicy()
        seed_character_calibration(policy, snapshot)
        set_completed_equipment_optimization(policy)
        seed_confirmed_loadout(policy, snapshot)
        policy._knowledge_response_log_path = None
        policy._read_batch_log_path = None
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_invalidated = False
        return policy

    def test_launcher_enchant_routes_before_town_departure_ready(self):
        captured = self._captured_procurement_snapshot()
        launcher = next(item for item in captured.equipment if item.is_launcher)
        snapshot = replace(captured, inventory=[], equipment=[launcher])
        policy = self._procurement_policy(snapshot)
        self.assertEqual(snapshot.player.gold, 3809)
        self.assertFalse(policy._town_departure_ready(snapshot))
        self.assertEqual(policy._launcher_enchant_needed_svals(snapshot), (17, 18))
        key = policy.choose_key(snapshot)
        self.assertIsNotNone(key)
        self.assertIn(
            TownNeed(STORE_ALCHEMIST, "launcher-enchant", "normal"),
            policy._enumerate_town_needs(snapshot),
        )

    def test_launcher_enchant_does_not_revive_restored_terminal_town(self):
        row = absorbing_catalog._departure_unsatisfiable_captures()[1248]
        policy = restore_checkpoint(
            HengbotPolicy, row["predecision_policy_checkpoint_pickle_b64"]
        )
        inside = pickle.loads(base64.b64decode(row["decision_snapshot_pickle_b64"]))
        outside = pickle.loads(base64.b64decode(row["next_snapshot_pickle_b64"]))

        policy._prepare_equipment_optimization(outside)
        producer_key = policy.choose_key(inside)
        self.assertEqual(producer_key, row["key"])
        self.assertEqual(policy.last_reason, row["last_reason"])
        policy.confirm_key_posted(producer_key)
        self.assertFalse(policy._town_departure_ready(outside))
        self.assertIsNone(policy._actionable_departure_supplier(outside))
        self.assertNotIn(
            TownNeed(STORE_ALCHEMIST, "launcher-enchant", "normal"),
            policy._enumerate_town_needs(outside),
        )
        next_key = policy.choose_key(outside)
        policy.confirm_key_posted(next_key)
        self.assertNotIn(
            TownNeed(STORE_ALCHEMIST, "launcher-enchant", "normal"),
            policy._enumerate_town_needs(outside),
        )

    def test_launcher_enchant_reroutes_after_real_alchemist_exhaustion(self):
        captured = self._captured_procurement_snapshot()
        launcher = next(item for item in captured.equipment if item.is_launcher)
        town = replace(captured, inventory=[], equipment=[launcher])
        producer_town = self._town(self._launcher(to_h=2, to_d=3))
        policy = self._procurement_policy(producer_town)

        exhausted_alchemist = self._town(
            self._launcher(to_h=2, to_d=3),
            store=StoreState(
                STORE_ALCHEMIST,
                [store_item("z", TVAL_SCROLL, 999, name="Unwanted", price=9999)],
            ),
        )
        _public_shop_inner(self, policy, exhausted_alchemist)
        self.assertIn(STORE_ALCHEMIST, policy._town_store_attempted)

        self.assertIn(
            TownNeed(STORE_ALCHEMIST, "launcher-enchant", "normal"),
            policy._enumerate_town_needs(town),
        )
        key = policy.choose_key(replace(town, turn=town.turn + 1))
        self.assertIsNotNone(key)

    def test_successful_launcher_enchant_rearms_same_visit(self):
        captured = self._captured_procurement_snapshot()
        launcher = next(item for item in captured.equipment if item.is_launcher)
        hit = item(
            "a", TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
            name="Enchant Weapon To-Hit",
        )
        policy = HengbotPolicy()
        first = replace(captured, inventory=[hit], equipment=[launcher])
        seed_character_calibration(policy, first)
        set_completed_equipment_optimization(policy)
        seed_confirmed_loadout(policy, first)
        policy._knowledge_response_log_path = None
        policy._read_batch_log_path = None

        scan_key = policy.choose_key(first)
        self.assertEqual(scan_key, "~9\x1b\x1b")
        self.assertTrue(policy.confirm_key_posted(scan_key))
        key = policy.choose_key(first)
        self.assertEqual(key, "ra/c")
        policy.confirm_key_posted(key)

        # Wall the already-consumed Home-catalogue collaborator after the real
        # producer, so the next public decision observes and consumes re-arming.
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_invalidated = False
        improved = replace(first, equipment=[replace(launcher, to_h=3)])
        self.assertEqual(policy.choose_key(improved), "ra/c")
        self.assertEqual(policy.last_reason, "town:enchant-launcher-tohit")

    def test_shop_reasons_name_curse_and_launcher_scrolls(self):
        cases = (
            (SV_SCROLL_REMOVE_CURSE, "shop:buy-remove-curse"),
            (SV_SCROLL_STAR_REMOVE_CURSE, "shop:buy-star-remove-curse"),
            (SV_SCROLL_ENCHANT_WEAPON_TO_HIT, "shop:buy-enchant-tohit"),
            (SV_SCROLL_ENCHANT_WEAPON_TO_DAM, "shop:buy-enchant-todam"),
        )
        for sval, reason in cases:
            with self.subTest(sval=sval):
                ware = store_item("a", TVAL_SCROLL, sval, price=100)
                snapshot = self._town(
                    self._launcher(), store=StoreState(STORE_ALCHEMIST, [ware])
                )
                policy = HengbotPolicy()
                with (
                    patch.object(policy, "_next_purchase", return_value=ware),
                    patch.object(policy, "_purchase_quantity", return_value=1),
                ):
                    self.assertEqual(policy._shop(snapshot), "pa\r")
                self.assertEqual(policy.last_reason, reason)

class WeaponSaleTest(unittest.TestCase):
    """Once an excellent+ (ego/artifact) weapon is wielded, good/average spare
    weapons are sold at the Weapon Smith instead of hoarded in the Home."""

    def _ego(self):
        return item("main_hand", 23, 0, is_equipment=True, is_ego=True, known=True, name="ego")

    def _inferior(self, slot="b", pseudo="good"):
        return item(slot, 23, 0, is_equipment=True, known=True, pseudo_feeling=pseudo, name="spare")

    def _town(self, inventory, equipment, store=None):
        return Snapshot(
            replace(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                stat_cur=(18, 10, 10, 18), stat_use=(18, 10, 10, 18),
                melee_skill=60, two_weapon_skill=4000,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            equipment=equipment,
            store=store,
        )

    def test_high_grade_and_inferior_classification(self):
        pol = HengbotPolicy()
        self.assertTrue(pol._weapon_is_high_grade(self._ego()))
        self.assertTrue(
            pol._weapon_is_high_grade(item("a", 23, 0, known=True, pseudo_feeling="excellent"))
        )
        self.assertFalse(pol._weapon_is_high_grade(self._inferior()))
        self.assertTrue(pol._weapon_is_inferior(self._inferior("b", "good")))
        self.assertTrue(pol._weapon_is_inferior(self._inferior("b", "average")))
        self.assertFalse(pol._weapon_is_inferior(self._ego()))
        self.assertFalse(
            pol._weapon_is_inferior(item("d", TVAL_DIGGING, 1, known=True, pseudo_feeling="good"))
        )
        # An *identified* plain weapon carries no pseudo_feeling, yet a mundane
        # +0,+0 spare is exactly "上質以下" and must be sold. (Live bug: Short/Broad
        # Sword, known:true, pseudo:"" were never being flagged.)
        self.assertTrue(pol._weapon_is_inferior(item("b", 23, 0, known=True, name="mundane")))
        # Still unidentified and unsensed -> do NOT blind-sell (could be an ego).
        self.assertFalse(pol._weapon_is_inferior(item("b", 23, 0, known=False)))
        # Unidentified but pseudo-sensed good/average is safe to sell.
        self.assertTrue(
            pol._weapon_is_inferior(item("b", 23, 0, known=False, pseudo_feeling="average"))
        )
        # A known ego spare is high-grade and kept even without full ID.
        self.assertFalse(pol._weapon_is_inferior(item("b", 23, 0, known=True, is_ego=True)))

    def test_sale_target_only_with_high_grade_wielded(self):
        pol = HengbotPolicy()
        inf = self._inferior()
        seed_character_calibration(pol, self._town([inf], [self._ego()]))
        self.assertEqual(pol._find_weapon_sale(self._town([inf], [self._ego()])).slot, "b")
        plain = item("main_hand", 23, 0, is_equipment=True, known=True, pseudo_feeling="good")
        self.assertIsNone(pol._find_weapon_sale(self._town([inf], [plain])))

    def test_higher_dps_plain_spare_is_not_sold_beside_ego_weapon(self):
        pol = HengbotPolicy()
        wielded = replace(
            self._ego(), damage_dice_num=1, damage_dice_sides=4, weight=50
        )
        spare = replace(
            self._inferior(), damage_dice_num=2, damage_dice_sides=6,
            to_h=5, to_d=7, weight=50,
        )
        town = self._town([spare], [wielded])
        town = replace(
            town,
            player=replace(
                town.player, level=27, stat_cur=(68, 10, 10, 68),
                stat_use=(68, 10, 10, 68), melee_skill=80,
                two_weapon_skill=4000,
            ),
        )

        self.assertIsNone(pol._find_weapon_sale(town))

    def test_sells_no_teleport_artifact_after_replacement(self):
        policy = HengbotPolicy()
        blocked = item(
            "b",
            23,
            1,
            name="artifact scimitar",
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        safe = self._ego()
        town = self._town([blocked], [safe])

        self.assertEqual(policy._find_weapon_sale(town).slot, "b")
        self.assertEqual(policy._next_required_store_type(town), STORE_WEAPON)
        shop = self._town([blocked], [safe], store=StoreState(STORE_WEAPON, []))
        self.assertEqual(policy._shop(shop), "{b@0\r")
        self.assertEqual(policy.last_reason, "shop:batch-inscribe")

    def test_inferior_spare_not_deposited_when_high_grade(self):
        pol = HengbotPolicy()
        set_known_target(pol)
        inf = self._inferior()
        self.assertIsNone(pol._find_home_deposit(self._town([inf], [self._ego()])))
        plain = item("main_hand", 23, 0, is_equipment=True, known=True, pseudo_feeling="good")
        self.assertIsNotNone(pol._find_home_deposit(self._town([inf], [plain])))

    def test_high_grade_spare_is_not_deposited_before_optimizer_compares_it(self):
        pol = HengbotPolicy()
        spare = item(
            "b", 23, 8, is_equipment=True, is_ego=True, known=True,
            name="ego spare",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [self._ego()])))

    def test_high_grade_weapon_is_protected_when_only_digger_is_equipped(self):
        pol = HengbotPolicy()
        spare = item(
            "b", 23, 8, is_equipment=True, is_ego=True, known=True,
            name="rearm weapon",
        )
        digger = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            is_equipment=True, known=True, name="Shovel",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [digger])))

    def test_good_non_ego_spare_is_not_deposited_before_loadout_search(self):
        # A spare with a real +to-hit bonus but no ego/artifact/excellent-pseudo
        # sense is "good_weapon" (see _home_deposit_candidate) yet not "high
        # grade" (see _weapon_is_high_grade) -- the gap the OLD unconditional
        # good_weapon protection left with NO disposal path at all: not shelved
        # (good_weapon blocked it outright), and _find_home_deposit's own
        # high-grade fallback only ever rescued the narrower is_ego/is_artifact/
        # excellent-pseudo subset, so a plain masterwork spare rode in the pack
        # forever. Once a real weapon is wielded it is no longer needed for
        # re-arm and becomes ordinary spare_equipment.
        pol = HengbotPolicy()
        real_sword = item(
            "main_hand", 23, 0, is_equipment=True, known=True, name="sword"
        )
        spare = item(
            "b", 23, 0, is_equipment=True, known=True, to_h=5,
            name="masterwork spare",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [real_sword])))

    def test_good_non_ego_spare_is_protected_while_digger_is_equipped(self):
        pol = HengbotPolicy()
        spare = item(
            "b", 23, 0, is_equipment=True, known=True, to_h=5,
            name="masterwork spare",
        )
        digger = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            is_equipment=True, known=True, name="Shovel",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [digger])))

    def test_good_non_ego_spare_is_protected_with_nothing_wielded(self):
        pol = HengbotPolicy()
        spare = item(
            "b", 23, 0, is_equipment=True, known=True, to_h=5,
            name="masterwork spare",
        )

        self.assertIsNone(pol._find_home_deposit(self._town([spare], [])))

    def test_active_recall_is_not_cancelled_to_strand_uncompared_weapon(self):
        pol = HengbotPolicy()
        recall = item(
            "r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            count=2, known=True, name="Word of Recall",
        )
        spare = item(
            "b", 23, 8, is_equipment=True, is_ego=True, known=True,
            name="ego spare",
        )
        snap = self._town([recall, spare], [self._ego()])
        snap = replace(snap, player=replace(snap.player, recalling=True))

        self.assertIsNone(pol._find_home_deposit(snap))
        self.assertIsNone(pol._town_cancel_unsafe_recall_key(snap))

    def test_active_recall_is_not_cancelled_only_because_scroll_was_consumed(self):
        pol = HengbotPolicy()
        recall = item(
            "r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            count=1, known=True, name="Word of Recall",
        )
        snap = self._town([recall], [self._ego()])
        snap = replace(snap, player=replace(snap.player, recalling=True))

        self.assertIsNone(pol._town_cancel_unsafe_recall_key(snap))

    def test_routes_to_and_sells_at_weapon_smith(self):
        pol = HengbotPolicy()
        inf = self._inferior()
        seed_character_calibration(pol, self._town([inf], [self._ego()]))
        self.assertEqual(
            pol._next_required_store_type(self._town([inf], [self._ego()])), STORE_WEAPON
        )
        snap = self._town([inf], [self._ego()], store=StoreState(STORE_WEAPON, []))
        self.assertEqual(pol._shop(snap), "{b@0\r")

    def test_withdraws_stored_inferior_weapon_to_sell(self):
        pol = HengbotPolicy()
        home = StoreState(
            STORE_HOME,
            [store_item("z", 23, 0, price=0, name="spare", pseudo_feeling="good")],
        )
        snap = self._town([], [self._ego()], store=home)
        key = pol._shop(snap)
        self.assertEqual(pol.last_reason, "home:queue-inferior-weapon-withdraw")
        self.assertEqual(key, LEAVE_STORE_KEY)

    def test_identified_mundane_spare_routes_and_sells(self):
        # Regression for the live miss: the character wielded an ego War Hammer but
        # kept an identified Short Sword (+0,+0) and Broad Sword (+0,+0) that carry
        # no pseudo_feeling, so they were never routed to the Weapon Smith.
        pol = HengbotPolicy()
        short = item("n", 23, 8, known=True, name="short sword")
        broad = item("o", 23, 16, known=True, name="broad sword")
        equip = [self._ego()]
        seed_character_calibration(pol, self._town([short, broad], equip))
        self.assertEqual(pol._find_weapon_sale(self._town([short, broad], equip)).slot, "n")
        self.assertEqual(
            pol._next_required_store_type(self._town([short, broad], equip)), STORE_WEAPON
        )
        snap = self._town([short, broad], equip, store=StoreState(STORE_WEAPON, []))
        self.assertEqual(_public_shop_inner(self, pol, snap), "{n@0\r")
        self.assertEqual(pol.last_reason, "shop:batch-inscribe")

class ArmorDominanceTest(unittest.TestCase):
    """Armour is ranked by DEFENSE (base AC + magic AC), never vetoed by the to-hit
    penalty that heavier armour carries."""

    def test_higher_ac_dominates_despite_a_worse_to_hit(self):
        heavy = item("k", 36, 4, ac=16, to_a=7, to_h=-2)     # Heavy Chain [16,+7] = 23
        leather = item("l", 36, 2, ac=11, to_a=-5, to_h=-1)  # Leather Scale [11,-5] = 6
        self.assertTrue(HengbotPolicy()._equipment_dominates(heavy, leather))
        self.assertFalse(HengbotPolicy()._equipment_dominates(leather, heavy))

class WieldHandSuffixTest(unittest.TestCase):
    """do_cmd_wield raises a different prompt depending on hand occupancy: both
    hands full -> "Equip which hand?" (equipment letter a/b); exactly one hand
    holding something -> "Dual wielding? [y/n]" (y = free hand, n = replace the
    occupied one). The wield macro must answer exactly the prompt that will
    appear, or the key stream stalls at the prompt until a nudge Escape."""

    @staticmethod
    def _snap(equipment):
        return Snapshot(
            player(10, 10),
            {},
            [],
            floor_key=(DUNGEON_ANGBAND, 5, 0),
            inventory=[],
            equipment=equipment,
        )

    @staticmethod
    def _weapon(slot):
        return item(
            slot, TVAL_SWORD, 4, is_equipment=True,
            damage_dice_num=1, damage_dice_sides=6,
        )

    @staticmethod
    def _shield(slot):
        return item(slot, 34, 3, is_equipment=True)  # TV_SHIELD

    @staticmethod
    def _macro(snapshot, wield, target):
        return equipment_mutation_module.EquipmentMutationExecutor().request_wield(
            snapshot, "test-loadout", wield, target,
            policy_module.EQUIPMENT_SLOT_KEY,
        ).key

    def test_both_hands_full_answers_the_which_hand_prompt(self):
        snap = self._snap([self._weapon("main_hand"), self._shield("sub_hand")])
        new = self._weapon("s")
        self.assertEqual(self._macro(snap, new, "main_hand"), "wsa")
        self.assertEqual(self._macro(snap, new, "sub_hand"), "wsb")

    def test_occupied_main_with_free_sub_answers_the_dual_wield_prompt(self):
        snap = self._snap([self._weapon("main_hand")])
        new = self._weapon("s")
        self.assertEqual(self._macro(snap, new, "main_hand"), "wsn")
        self.assertEqual(self._macro(snap, new, "sub_hand"), "wsy")

    def test_sub_hand_weapon_with_free_main_answers_the_dual_wield_prompt(self):
        snap = self._snap([self._weapon("sub_hand")])
        new = self._weapon("s")
        self.assertEqual(self._macro(snap, new, "main_hand"), "wsy")
        self.assertEqual(self._macro(snap, new, "sub_hand"), "wsn")

    def test_free_hands_or_a_lone_shield_raise_no_prompt(self):
        new = self._weapon("s")
        self.assertEqual(self._macro(self._snap([]), new, "main_hand"), "ws")
        lone_shield = self._snap([self._shield("sub_hand")])
        self.assertEqual(self._macro(lone_shield, new, "main_hand"), "ws")

    def test_shield_restore_replaces_the_sub_hand_melee_weapon(self):
        shield = item("o", 34, 3, is_equipment=True, name="Shield")
        before = self._snap(
            [
                self._weapon("main_hand"),
                item(
                    "sub_hand",
                    TVAL_DIGGING,
                    1,
                    is_equipment=True,
                    name="Shovel",
                ),
            ]
        )
        self.assertEqual(
            self._macro(before, shield, "sub_hand"), "wob"
        )

        after = self._snap(
            [
                self._weapon("main_hand"),
                item("sub_hand", 34, 3, is_equipment=True, name="Shield"),
            ]
        )
        self.assertFalse(
            any(
                equipped.slot == "sub_hand" and equipped.is_digging_tool
                for equipped in after.equipment
            )
        )

    def test_ring_restore_answers_replace_which_ring(self):
        ring = item("r", TVAL_RING, 1, is_equipment=True, name="New Ring")
        snap = self._snap(
            [
                item("main_ring", TVAL_RING, 2, is_equipment=True),
                item("sub_ring", TVAL_RING, 3, is_equipment=True),
            ]
        )
        self.assertEqual(
            self._macro(snap, ring, "sub_ring"), "wr)"
        )

class EntranceTravelTest(unittest.TestCase):
    """The surface walk to the dungeon entrance costs one bot decision per tile
    on foot; _entrance_travel_key rides Hengband's native travel instead
    (`n>. — the selector's > jump matches the entrance's STAIRS+DOWN_STAIRS
    terrain) and falls back to BFS walking only after issues that bring no
    progress. The bot never accepts castle quests, so > cannot land on a
    quest entrance."""

    GOAL = Position(34, 120)

    @staticmethod
    def _optimizer_state(*, complete):
        transaction = SimpleNamespace(actions=()) if complete else None
        return SimpleNamespace(
            ready=complete,
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=(SimpleNamespace(best=SimpleNamespace(loadout="worn"))
                    if complete else None),
            transaction=transaction,
            blockers=() if complete else ("home-scan-incomplete",),
        )

    @staticmethod
    def _surface_snap(x=94, turn=0, *, goal_remembered=True):
        grids = {Position(34, x): grid(34, x)}
        if goal_remembered:
            grids[EntranceTravelTest.GOAL] = grid(
                EntranceTravelTest.GOAL.y, EntranceTravelTest.GOAL.x,
                entrance=True, entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )
        return Snapshot(
            player(34, x),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            town_id=0,
            town_index=1,
            turn=turn,
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=3)
            ],
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

    def _travel(self, pol, snap, goal=GOAL):
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        pol.last_reason = "seek-downstairs"
        return pol._entrance_travel_key(snap, goal)

    def test_non_target_surface_goal_does_not_travel(self):
        pol = HengbotPolicy()
        snap = self._surface_snap()
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol.last_reason = "seek-downstairs"

        self.assertIsNone(pol._entrance_travel_key(snap, self.GOAL))
        self.assertIsNone(pol._town_travel_state)

    def test_far_surface_goal_travels(self):
        pol = HengbotPolicy()
        pol._prepare_equipment_optimization = lambda _snapshot: self._optimizer_state(
            complete=True
        )
        key = self._travel(pol, self._surface_snap())
        self.assertEqual(key, "\x1b`n>.")
        self.assertEqual(pol.last_reason, "town:travel-entrance")

    def test_native_entrance_travel_binds_on_entry_depth(self):
        pol = HengbotPolicy()
        pol._dungeon_knowledge[DUNGEON_YEEK_CAVE] = SimpleNamespace(
            id=DUNGEON_YEEK_CAVE, min_depth=31
        )
        pol._prepare_equipment_optimization = lambda _snapshot: self._optimizer_state(
            complete=True
        )

        self.assertIsNone(self._travel(pol, self._surface_snap()))
        self.assertEqual(
            pol.last_reason,
            "depth-gate:destination-31:missing-resist_chaos",
        )

    def test_incomplete_optimizer_blocks_native_entrance_travel(self):
        pol = HengbotPolicy()
        pol._prepare_equipment_optimization = lambda _snapshot: self._optimizer_state(
            complete=False
        )

        snap = replace(
            self._surface_snap(),
            player=replace(
                self._surface_snap().player, class_id=PLAYER_CLASS_WARRIOR
            ),
        )
        self.assertIsNone(self._travel(pol, snap))
        self.assertEqual(pol.last_reason, "seek-downstairs")

    def test_mining_walk_in_ignores_prior_floor_descent_cooldown(self):
        snap = replace(
            self._surface_snap(),
            player=replace(self._surface_snap().player, level=7, gold=303),
            grids={
                **self._surface_snap().grids,
                Position(34, 95): grid(34, 95),
            },
            inventory=[
                item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
                item(
                    "t",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=MINING_RUNS_PER_SET,
                ),
            ],
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )

        for cooldown in (False, True):
            with self.subTest(cooldown=cooldown):
                pol = HengbotPolicy()
                # TEST_FAKERY_LINT_ALLOW: subject-precompleted: test seeds an independently established loadout prerequisite before exercising a later gate
                set_completed_equipment_optimization(pol)
                pol._floor_key = snap.floor_key
                pol._fundraising_mode = "mine"
                pol._town_restock_suppressed = True
                if cooldown:
                    # Live character #5 had just escaped Yeek 1F via
                    # status-threat:stairs, which arms this 200-decision gate.
                    pol._descent_blocked = True
                    pol._descent_block_countdown = 64

                self.assertTrue(pol._fundraising_kit_secured(snap))
                self.assertFalse(pol._recall_departure_shortage(snap))
                pol._target_dungeon_id = DUNGEON_YEEK_CAVE
                self.assertTrue(pol._equipment_departure_ready(snap))
                self.assertEqual(pol.choose_key(snap), "\x1b`n>.")
                self.assertEqual(pol.last_reason, "town:travel-entrance")

    def test_non_mining_walk_in_respects_prior_floor_descent_cooldown(self):
        snap = replace(
            self._surface_snap(),
            player=replace(self._surface_snap().player, level=7),
            grids={
                **self._surface_snap().grids,
                Position(34, 95): grid(34, 95),
            },
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        pol = HengbotPolicy()
        pol._floor_key = snap.floor_key
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        pol._descent_blocked = True
        pol._descent_block_countdown = 64

        self.assertNotEqual(pol.choose_key(snap), "\x1b`n>.")
        self.assertNotEqual(pol.last_reason, "town:travel-entrance")

    def test_zero_recall_ordinary_surface_goal_does_not_enter(self):
        pol = HengbotPolicy()
        snap = replace(self._surface_snap(), inventory=[])

        self.assertIsNone(self._travel(pol, snap))
        self.assertEqual(pol.last_reason, "seek-downstairs")

    def test_surface_goal_without_equipped_light_walks_instead(self):
        pol = HengbotPolicy()
        snap = replace(self._surface_snap(), equipment=[])

        self.assertIsNone(self._travel(pol, snap))
        self.assertEqual(pol.last_reason, "seek-downstairs")
        self.assertIsNone(pol._town_travel_state)

    def test_unremembered_entrance_goal_does_not_issue_or_record_travel(self):
        pol = HengbotPolicy()
        snap = self._surface_snap(goal_remembered=False)

        self.assertIsNone(self._travel(pol, snap))
        self.assertEqual(pol.last_reason, "seek-downstairs")
        self.assertIsNone(pol._town_travel_state)

    def test_progress_reissues_travel_after_an_interruption(self):
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        self.assertEqual(self._travel(pol, self._surface_snap(x=94)), "\x1b`n>.")
        # Interrupted mid-route but closer than before: travel again.
        self.assertEqual(self._travel(pol, self._surface_snap(x=110)), "\x1b`n>.")

    def test_no_progress_latches_a_walking_fallback(self):
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        snap = self._surface_snap(turn=1)
        self.assertEqual(self._travel(pol, snap), "\x1b`n>.")
        # The duplicate is emitted only after the stall nudge waited and sent
        # Escape, so immediately give the rejected entrance back to BFS.
        self.assertIsNone(self._travel(pol, snap))
        self.assertIsNone(self._travel(pol, snap))

    def test_yeek_entrance_is_not_a_descent_target_outside_outpost(self):
        pol = HengbotPolicy()
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        entrance = grid(
            34,
            130,
            entrance=True,
            entrance_dungeon_id=DUNGEON_YEEK_CAVE,
        )
        elsewhere = replace(
            self._surface_snap(),
            grids={entrance.position: entrance},
            town_id=2,
            town_flag=True,
        )
        outpost = replace(elsewhere, town_id=0)

        self.assertFalse(pol._is_descent_target(elsewhere, entrance))
        self.assertTrue(pol._is_descent_target(outpost, entrance))

    def test_dungeon_floors_never_travel(self):
        pol = HengbotPolicy()
        snap = Snapshot(
            player(34, 94),
            {},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 3, 0),
            inventory=[],
            equipment=[],
        )
        self.assertIsNone(self._travel(pol, snap))

    def test_adjacent_goal_walks(self):
        pol = HengbotPolicy()
        self.assertIsNone(self._travel(pol, self._surface_snap(x=118)))

    def test_floor_change_clears_the_fallback_latch(self):
        pol = HengbotPolicy()
        snap = self._surface_snap(turn=1)
        self._travel(pol, snap)
        for _ in range(TOWN_TRAVEL_STALL_LIMIT - 1):
            self._travel(pol, snap)
        self.assertIsNone(self._travel(pol, snap))  # latched
        pol._floor_key = snap.floor_key  # as if _observe had seen the surface
        dungeon = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[],
            equipment=[],
        )
        pol.choose_key(dungeon)  # _observe sees the floor change and resets
        self.assertIsNone(pol._town_travel_fallback)

class EquipmentOptimizationDestructionWiringTest(unittest.TestCase):
    """prepare_warrior_optimization must receive the character's ACTUAL
    *Destruction* availability. The fail-closed False stub made
    _meets_static_requirements reject every 50F+ loadout, so a warrior already
    carrying the scroll could never become departure-ready (a town deadlock)."""

    @staticmethod
    def _town_snapshot(inventory):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=inventory,
            equipment=[],
        )

    @staticmethod
    def _captured_has_destruction(snap):
        from unittest import mock

        pol = HengbotPolicy()
        seed_character_calibration(pol, snap)
        with mock.patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            return_value=mock.Mock(ready=False),
        ) as prepare:
            pol._prepare_equipment_optimization(snap)
        return prepare.call_args.kwargs["has_destruction"]

    def test_carried_destruction_scroll_reaches_the_optimizer(self):
        snap = self._town_snapshot(
            [item("s", TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION)]
        )
        self.assertTrue(self._captured_has_destruction(snap))

    def test_without_a_destruction_source_the_optimizer_stays_fail_closed(self):
        snap = self._town_snapshot([])
        self.assertFalse(self._captured_has_destruction(snap))

    def test_reserved_throwing_torch_is_not_a_loadout_candidate(self):
        from unittest import mock

        torch = item(
            "a", TVAL_LITE, SV_LITE_TORCH, name="lit torch",
            known=True, fully_known=True, is_equipment=True, fuel=5000,
        )
        snap = self._town_snapshot([torch])
        pol = HengbotPolicy()
        seed_character_calibration(pol, snap)
        pol._equipment_catalog.refresh_carried(snap.inventory, snap.equipment)
        with mock.patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            return_value=mock.Mock(ready=False),
        ) as prepare:
            pol._prepare_equipment_optimization(snap)

        torch_id = next(
            owned.id for owned in pol._equipment_catalog.items
            if owned.item.is_torch
        )
        self.assertNotIn(
            torch_id, prepare.call_args.kwargs["search_excluded_item_ids"]
        )

    def test_owned_quest_launcher_excludes_incompatible_equipped_launcher(self):
        from unittest import mock

        sling = item(
            "bow", TVAL_BOW, SV_BOW_SLING, name="sling", is_equipment=True
        )
        crossbow = item(
            "a", TVAL_BOW, SV_BOW_LIGHT_XBOW,
            name="light crossbow", is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[crossbow],
            equipment=[sling],
        )
        pol = HengbotPolicy()
        seed_character_calibration(pol, snap)
        pol._equipment_catalog.refresh_carried(snap.inventory, snap.equipment)
        pol._equipment_catalog.observe_home_page(
            [
                store_item(
                    "b", TVAL_BOW, SV_BOW_SHORT,
                    name="home short bow", is_equipment=True,
                )
            ]
        )
        strategy = SimpleNamespace(
            required_force={"launcher": {"ammo": "bolt", "equipped": True}}
        )
        with mock.patch.object(
            pol, "_carry_procurement_strategy", return_value=strategy
        ), mock.patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            return_value=mock.Mock(ready=False),
        ) as prepare:
            pol._prepare_equipment_optimization(snap)

        ids = {
            owned.item.name: owned.id for owned in pol._equipment_catalog.items
        }
        excluded = prepare.call_args.kwargs["search_excluded_item_ids"]
        self.assertNotIn(ids["sling"], excluded)
        self.assertNotIn(ids["home short bow"], excluded)
        self.assertNotIn(ids["light crossbow"], excluded)

class EquipmentTransactionQuarantineInvariantTest(unittest.TestCase):
    """Regression for the 45-item depth-20 catalog captured at turn 1565400."""

    @staticmethod
    def _recorded_shape_snapshot():
        # Preserve the incident's important shape: the incremental-search cutoff
        # (45 equipment entries), exactly two free-action sources, and a separate
        # fire-resistance source.  The remaining entries are irrelevant rings.
        inventory = [
            item(
                chr(ord("a") + (index % 26)),
                45,
                index + 1,
                name=f"recorded filler {index}",
                known=True,
                fully_known=True,
                is_equipment=True,
            )
            for index in range(42)
        ]
        inventory.extend(
            (
                item(
                    "x", 37, 1, name="free action boots", known=True,
                    fully_known=True, is_equipment=True,
                    known_flags=frozenset({46}),
                ),
                item(
                    "y", 37, 2, name="Black Clothes", known=True,
                    fully_known=True, is_equipment=True,
                    known_flags=frozenset({46}),
                ),
                item(
                    "z", 34, 1, name="fire source", known=True,
                    fully_known=True, is_equipment=True,
                    known_flags=frozenset({50}),
                ),
            )
        )
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=inventory,
            equipment=[],
        )

    @staticmethod
    def _flag_sensitive_preparation(_snapshot, catalog, *_args, depth, **_kwargs):
        required = {
            policy_module.RESIST_FLAG_BY_ABILITY[ability]
            for ability in (
                policy_module.required_depth_gates(depth) if depth is not None else ()
            )
            if ability in policy_module.RESIST_FLAG_BY_ABILITY
        }
        available = set().union(*(owned.flags for owned in catalog))
        best = SimpleNamespace(loadout=SimpleNamespace(item_ids=frozenset())) \
            if required <= available else None
        return SimpleNamespace(
            ready=best is not None,
            result=SimpleNamespace(best=best, incomplete_item_ids=frozenset()),
            transaction=None,
            blockers=() if best is not None else ("no-valid-loadout",),
        )

    def test_both_recorded_free_action_sources_cannot_create_terminal_block(self):
        snapshot = self._recorded_shape_snapshot()
        policy = HengbotPolicy()
        seed_character_calibration(policy, snapshot)
        policy._deepest_level = 19
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        free_action_ids = {
            owned.id for owned in policy._equipment_catalog.items
            if 46 in owned.flags
        }
        policy._equipment_transaction_failed_items.update(free_action_ids)

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            side_effect=self._flag_sensitive_preparation,
        ):
            preparation = policy._prepare_equipment_optimization(snapshot)

        self.assertIsNotNone(preparation.result.best)
        self.assertTrue(
            free_action_ids.issubset(policy._equipment_transaction_failed_items)
        )
        self.assertNotIn("no-valid-loadout", preparation.blockers)

    def test_quarantining_each_mandatory_source_never_removes_the_last_one(self):
        snapshot = self._recorded_shape_snapshot()
        policy = HengbotPolicy()
        seed_character_calibration(policy, snapshot)
        policy._deepest_level = 19
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        required_sources = [
            owned.id for owned in policy._equipment_catalog.items
            if owned.flags.intersection({46, 50})
        ]

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            side_effect=self._flag_sensitive_preparation,
        ):
            for failed_id in required_sources:
                policy._equipment_transaction_failed_items.add(failed_id)
                policy._equipment_optimization_signature = None
                preparation = policy._prepare_equipment_optimization(snapshot)
                self.assertIsNotNone(preparation.result.best, failed_id)

    def test_zero_candidate_twenty_floor_search_relaxes_with_alternate_latched(self):
        policy = HengbotPolicy()
        policy._deepest_level = 19
        policy._target_dungeon_id = DUNGEON_ANGBAND
        policy._alternate_dungeon = DUNGEON_YEEK_CAVE
        snapshot = replace(
            self._recorded_shape_snapshot(),
            recall_depth=19,
            recall_dungeon_id=DUNGEON_ANGBAND,
            dungeon_recall_depths={DUNGEON_YEEK_CAVE: 19},
        )
        invalid = SimpleNamespace(
            blockers=("no-valid-loadout",), result=SimpleNamespace(best=None)
        )
        valid = SimpleNamespace(
            blockers=(),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=SimpleNamespace())),
        )

        def prepare(_snapshot, *, depth_override=None):
            return valid if depth_override == 19 else invalid

        with patch.object(
            policy, "_prepare_equipment_optimization", side_effect=prepare
        ), patch.object(
            policy, "_next_required_store_type", return_value=None
        ):
            selected = hasattr(policy, "_activate_loadout_depth_fallback")

        self.assertFalse(selected)

class JewelryKeepingTest(unittest.TestCase):
    """Found rings / amulets stay in the pack for identify-and-wear instead of being
    stashed at Home unidentified (why the character reached depth with a bare neck)."""

    def _home(self, inventory, equipment=()):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            equipment=list(equipment),
        )

    def test_keeps_an_unidentified_amulet_out_of_the_home_deposit(self):
        amulet = item("k", TVAL_AMULET, 4, aware=False, known=False, is_equipment=True)
        snap = self._home([amulet])
        pol = HengbotPolicy()
        self.assertTrue(pol._is_wanted_jewelry(snap, amulet))
        self.assertIsNone(pol._find_home_deposit(snap))

    def test_keeps_a_beneficial_amulet_for_the_empty_neck(self):
        amulet = item("k", TVAL_AMULET, 4, known_flags=frozenset({50, 86}), is_equipment=True)
        self.assertTrue(HengbotPolicy()._is_wanted_jewelry(self._home([amulet]), amulet))

    def test_stashes_a_spare_amulet_when_the_neck_is_occupied(self):
        worn = item("neck", TVAL_AMULET, 2, is_equipment=True, known_flags=frozenset({50}))
        spare = item("k", TVAL_AMULET, 4, known_flags=frozenset({86}), is_equipment=True)
        snap = self._home([spare], equipment=[worn])
        pol = HengbotPolicy()
        set_known_target(pol)
        self.assertFalse(pol._is_wanted_jewelry(snap, spare))
        self.assertEqual(pol._find_home_deposit(snap), spare)

class GlobalEquipmentOptimizationOwnershipTest(unittest.TestCase):
    def _town(self, *, inventory=(), equipment=(), store=None):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            equipment=list(equipment),
            store=store,
        )

    def _digger_withdrawal_incident(self):
        shovel = item(
            "d", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="Shovel (1d2)",
            known=True, fully_known=True, is_equipment=True,
        )
        pick = item(
            "e", TVAL_DIGGING, SV_DIGGING_PICK, name="Pick (1d3)",
            known=True, fully_known=True, is_equipment=True,
        )
        wearable = store_item(
            "a", TVAL_RING, 1, name="recorded Home wearable",
            known=True, fully_known=True, is_equipment=True,
        )
        policy = HengbotPolicy()
        snapshot = self._town(inventory=(shovel, pick))
        seed_character_calibration(policy, snapshot)
        digger_ids = (
            "pack:3de78ae78c7ba624:0",
            "pack:5b3f232ae0777c7e:0",
        )
        home_id = "home:ec2e53c16a3761bb:0"
        policy._equipment_catalog._carried = {
            digger_ids[0]: OwnedEquipment(digger_ids[0], shovel, "pack"),
            digger_ids[1]: OwnedEquipment(digger_ids[1], pick, "pack"),
        }
        policy._equipment_catalog._home = {
            home_id: OwnedEquipment(home_id, wearable, "home")
        }
        policy._equipment_catalog.home_scan_complete = True
        return policy, snapshot, digger_ids, home_id, wearable

    def test_worn_reserved_digger_projects_through_takeoff_and_never_deposits(self):
        """Seq 803-815 shape: one authority governs post-takeoff retention."""
        digger = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="Shovel (1d2)", known=True, fully_known=True,
            is_equipment=True,
        )
        sword = item(
            "a", 23, 4, name="Long Sword (2d5)", known=True,
            fully_known=True, is_equipment=True, to_h=5, to_d=8,
        )
        snapshot = self._town(inventory=(sword,), equipment=(digger,))
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        catalog = policy._equipment_catalog.items
        current = current_loadout(catalog)
        worn = next(owned for owned in catalog if owned.origin == "equipped")
        replacement = next(owned for owned in catalog if owned.origin == "pack")
        target = Loadout((("main_hand", replacement),), "one_handed")

        retained = policy._transaction_retain_identities(
            snapshot, current, target
        )
        plan = policy_module.plan_equipment_transactions(
            catalog,
            current,
            target,
            current_pack_items=len(snapshot.inventory),
            home_scan_complete=True,
            preserve_pack_item_ids=frozenset({replacement.id}),
            retain_item_identities=retained,
        )

        self.assertIn(policy_module.equipment_identity(digger), retained)
        self.assertEqual(
            [(action.kind, action.item_identity) for action in plan.actions],
            [
                ("takeoff", policy_module.equipment_identity(digger)),
                ("equip", policy_module.equipment_identity(sword)),
            ],
        )
        self.assertEqual(plan.phase("home_finalize"), ())
        self.assertEqual(plan.peak_pack_items, 2)

    def _live_worn_reserved_digger_seed(self):
        """Construct the captured 7-equipped/1-pack optimization shape."""
        digger = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="Shovel (1d2)", known=True, fully_known=True,
            is_equipment=True,
        )
        sword = item(
            "a", 23, 4, name="Long Sword (2d5)", known=True,
            fully_known=True, is_equipment=True, to_h=25, to_d=25,
        )
        worn = (
            digger,
            item("bow", TVAL_BOW, SV_BOW_SLING, name="Sling", known=True,
                 fully_known=True, is_equipment=True),
            item("light", TVAL_LITE, SV_LITE_LANTERN, name="Lantern", fuel=5000,
                 known=True, fully_known=True, is_equipment=True),
            item("body", 36, 1, name="Soft Leather Armour", known=True,
                 fully_known=True, is_equipment=True),
            item("head", 34, 1, name="Hard Leather Cap", known=True,
                 fully_known=True, is_equipment=True),
            item("hands", 31, 1, name="Leather Gloves", known=True,
                 fully_known=True, is_equipment=True),
            item("feet", 30, 1, name="Soft Leather Boots", known=True,
                 fully_known=True, is_equipment=True),
        )
        snapshot = self._town(inventory=(sword,), equipment=worn)
        snapshot = replace(
            snapshot,
            player=replace(
                snapshot.player,
                stat_cur=(18, 10, 10, 18), stat_use=(18, 10, 10, 18),
                melee_skill=60, saving_skill=40,
            ),
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=0, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 4),),
        )
        policy = HengbotPolicy(monrace_knowledge={1: knowledge})
        seed_character_calibration(policy, snapshot)
        policy._equipment_catalog.observe_home_page([])
        policy._fundraising_mode = "mine"
        policy._town_was_in_town = True
        return policy, snapshot, digger, sword, worn

    @staticmethod
    def _incident_target_preparation(snapshot, items, *_args, **_kwargs):
        current = current_loadout(items)
        replacement = next(
            owned
            for owned in items
            if owned.origin == "pack" and owned.item.is_equipment
        )
        target = Loadout(
            tuple(
                (slot, owned)
                for slot, owned in current.slots
                if slot != "main_hand"
            ) + (("main_hand", replacement),),
            "one_handed",
        )
        result = OptimizationResult(
            EvaluatedLoadout(target, LoadoutMetrics(1.0, 1.0, 1.0)),
            (), (), frozenset(), 1, 1, 0, 0.0, False, frozenset(),
        )
        return policy_module.WarriorOptimizationPreparation(
            current,
            result,
            policy_module.EquipmentTransactionPlan((), (), len(snapshot.inventory)),
            (),
        )

    def test_live_fresh_replan_retains_displaced_worn_digger_to_completion(self):
        """H2 fresh-search: choose_key owns the retained takeoff end to end."""
        policy, snapshot, digger, sword, worn = (
            self._live_worn_reserved_digger_seed()
        )

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            side_effect=self._incident_target_preparation,
        ), patch.object(policy, "_town_restore_weapon_key", return_value=None):
            first = policy.choose_key(snapshot)
            if first == WAIT_KEY:
                first = policy.choose_key(snapshot)
        self.assertTrue(first.startswith(equipment_mutation_module.TAKEOFF_KEY))
        state = policy.equipment_optimization_state(snapshot)
        self.assertEqual(
            state["search_catalog_origins"],
            {"equipped": 7, "pack": 1, "home": 0},
        )
        self.assertEqual(state["preserve_pack_items"]["total"], 0)
        session = policy._equipment_transaction_session
        self.assertIsNotNone(session)
        self.assertNotIn(
            policy_module.equipment_identity(digger),
            {
                action.item_identity
                for action in session.plan.phase("home_finalize")
            },
        )
        self.assertNotIn("home-route-unavailable", session.blockers)
        self.assertTrue(policy.confirm_key_posted(first))

        displaced = replace(digger, slot="b")
        after_takeoff = replace(
            snapshot, inventory=(sword, displaced), equipment=worn[1:], turn=1,
        )
        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            side_effect=self._incident_target_preparation,
        ), patch.object(policy, "_town_restore_weapon_key", return_value=None):
            second = policy.choose_key(after_takeoff)
        self.assertTrue(second.startswith(equipment_mutation_module.WIELD_KEY))
        self.assertNotIn(policy_module.equipment_identity(digger), second)
        self.assertTrue(policy.confirm_key_posted(second))
        policy._fundraising_mode = None

        complete = replace(
            snapshot,
            inventory=(replace(digger, slot="a"),),
            equipment=(replace(sword, slot="main_hand"),) + worn[1:],
            turn=2,
        )
        self.assertTrue(session.observe(
            policy_module.observe_equipment_transactions(complete)
        ))
        self.assertTrue(session.complete)
        self.assertFalse((policy.last_reason or "").endswith("home-route-unavailable"))

    def test_live_cache_hit_replan_retains_displaced_worn_digger(self):
        """H2 cache hit: pack-size replan keeps the displaced reservation."""
        policy, snapshot, digger, _sword, _worn = (
            self._live_worn_reserved_digger_seed()
        )
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            side_effect=self._incident_target_preparation,
        ):
            policy._prepare_equipment_optimization(snapshot)
        policy._equipment_transaction_session = None
        extra = item("b", TVAL_POTION, SV_POTION_CURE_CRITICAL, name="Cure")

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            side_effect=self._incident_target_preparation,
        ):
            policy._prepare_equipment_optimization(
                replace(snapshot, inventory=(*snapshot.inventory, extra))
            )

        self.assertEqual(
            policy._equipment_optimization_telemetry["result_source"],
            "signature-cache-hit",
        )
        session = policy._equipment_transaction_session
        self.assertIsNotNone(session)
        self.assertNotIn(
            policy_module.equipment_identity(digger),
            {
                action.item_identity
                for action in session.plan.phase("home_finalize")
            },
        )
        self.assertNotIn("home-route-unavailable", session.blockers)
        self.assertIn(
            policy_module.equipment_identity(digger),
            {action.item_identity for action in session.plan.actions},
        )

    def test_retained_incident_diggers_are_preserved_and_never_deposited(self):
        policy, snapshot, digger_ids, home_id, _ = (
            self._digger_withdrawal_incident()
        )
        captured = {}

        def prepare(snapshot_arg, items, *args, **kwargs):
            preserved = kwargs["preserve_pack_item_ids"]
            target_item = next(owned for owned in items if owned.id == home_id)
            target = Loadout((("main_ring", target_item),), "empty")
            plan = policy_module.plan_equipment_transactions(
                items, current_loadout(items), target,
                current_pack_items=len(snapshot_arg.inventory),
                home_scan_complete=True,
                preserve_pack_item_ids=preserved,
            )
            captured.update(preserve=preserved, plan=plan, target=target)
            return policy_module.WarriorOptimizationPreparation(
                current_loadout(items),
                None,
                plan,
                (),
            )

        with patch("hengbot.policy_equipment.prepare_warrior_optimization", prepare):
            preparation = policy._prepare_equipment_optimization(snapshot)

        deposits = {
            action.item_id for action in preparation.transaction.actions
            if action.kind == "deposit"
        }
        self.assertEqual(deposits.intersection(digger_ids), set())
        self.assertEqual(
            captured["preserve"].intersection(digger_ids), set(digger_ids)
        )

    def test_incident_home_replay_withdraws_before_identify_staff_work(self):
        policy, outside, digger_ids, home_id, wearable = (
            self._digger_withdrawal_incident()
        )

        def prepare(snapshot_arg, items, *args, **kwargs):
            target_item = next(item for item in items if item.id == home_id)
            target = Loadout((("main_ring", target_item),), "empty")
            transaction = policy_module.plan_equipment_transactions(
                items, current_loadout(items), target,
                current_pack_items=len(snapshot_arg.inventory),
                home_scan_complete=True,
                preserve_pack_item_ids=kwargs["preserve_pack_item_ids"],
            )
            return policy_module.WarriorOptimizationPreparation(
                current_loadout(items),
                None,
                transaction,
                (),
            )

        with patch("hengbot.policy_equipment.prepare_warrior_optimization", prepare):
            preparation = policy._prepare_equipment_optimization(outside)
        plan = preparation.transaction
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(plan)
        )
        identify_staff = store_item(
            "b", TVAL_STAFF, SV_STAFF_IDENTIFY, name="Staff of Identify",
            count=1, charges=12, pval=12, known=True, fully_known=True,
        )
        home = replace(
            outside, store=StoreState(STORE_HOME, [wearable, identify_staff])
        )
        policy.consume_home_knowledge((wearable, identify_staff))

        key = policy._equipment_transaction_home_key(home)

        self.assertTrue(plan.executable)
        self.assertEqual(policy._equipment_transaction_failed_items, set())
        self.assertNotEqual(
            policy.last_reason, "equipment-transaction:retain-digging-tool"
        )
        self.assertEqual(
            policy.last_reason,
            "equipment-transaction:leave-for-atomic-withdraw",
        )
        self.assertEqual(
            policy._equipment_transaction_session.current_action.item_id,
            home_id,
        )
        self.assertNotEqual(key, WAIT_KEY)
        self.assertNotIn("home-route-unavailable", policy.last_reason)

        policy._equipment_transaction_session = None
        self.assertEqual(policy._shop(home), LEAVE_STORE_KEY)
        self.assertIn(
            policy.last_reason,
            {
                "home:queue-withdraw-identify-staff-reserve",
                "home:queue-withdraw-surplus-identify-staff",
            },
        )
        self.assertEqual(
            policy._home_pending_item,
            policy._item_signature(identify_staff),
        )

    def test_inscribes_pack_random_teleport_item_in_town(self):
        mask = item(
            "a", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()

        key = policy._town_random_teleport_suppression_key(
            self._town(inventory=(mask,))
        )

        self.assertEqual(key, "{a.\r")
        self.assertEqual(policy.last_reason, "equipment:suppress-random-teleport")

    def test_inscribes_partial_known_uncursed_item_before_equipping(self):
        glaive = item(
            "a", 23, 1, name="Animal-Slayer Glaive", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
            known_flags=frozenset(),
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried([glaive], [])
        owned = policy._equipment_catalog.items[0]
        policy._equipment_optimization_preparation = SimpleNamespace(
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(
                best=SimpleNamespace(
                    loadout=SimpleNamespace(item_ids=frozenset({owned.id}))
                )
            )
        )
        policy._prepare_equipment_optimization = (
            lambda _snapshot: policy._equipment_optimization_preparation
        )

        key = policy._town_random_teleport_suppression_key(
            self._town(inventory=(glaive,))
        )

        self.assertEqual(key, INSCRIBE_KEY + "a.\r")
        self.assertEqual(policy.last_reason, "equipment:suppress-random-teleport")

    def test_fresh_selected_partial_artifact_suppression_matches_blocker(self):
        artifact = item(
            "a", 23, 17, name="Werewindle", known=True,
            fully_known=False, is_equipment=True, is_artifact=True,
            known_flags=frozenset({38, 74}),
        )
        snapshot = self._town(inventory=(artifact,))
        policy = HengbotPolicy()
        seed_character_calibration(policy, snapshot)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        selected_id = policy._equipment_catalog.items[0].id
        current = SimpleNamespace()
        # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
        result = SimpleNamespace(
            best=SimpleNamespace(
                loadout=SimpleNamespace(item_ids=frozenset({selected_id}))
            )
        )
        transaction = policy_module.EquipmentTransactionPlan((), (), 1)
        fresh = policy_module.WarriorOptimizationPreparation(
            current, result, transaction, (),
        )

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            return_value=fresh,
        ):
            key = policy._town_random_teleport_suppression_key(snapshot)
            preparation = policy._prepare_equipment_optimization(snapshot)

        self.assertEqual(
            preparation.blockers,
            ("pending-random-teleport-suppression",),
        )
        self.assertEqual(key, INSCRIBE_KEY + "a.\r")

    def test_inscribed_selected_partial_artifact_clears_departure_blocker(self):
        artifact = item(
            "a", 23, 17, name="Werewindle {.}", known=True,
            fully_known=False, is_equipment=True, is_artifact=True,
            known_flags=frozenset({38, 74}),
        )
        snapshot = self._town(equipment=(replace(artifact, slot="main_hand"),))
        policy = HengbotPolicy()
        seed_character_calibration(policy, snapshot)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        selected_id = policy._equipment_catalog.items[0].id
        fresh = policy_module.WarriorOptimizationPreparation(
            SimpleNamespace(),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            SimpleNamespace(
                best=SimpleNamespace(
                    loadout=SimpleNamespace(item_ids=frozenset({selected_id}))
                )
            ),
            policy_module.EquipmentTransactionPlan((), (), 1),
            (),
        )

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            return_value=fresh,
        ):
            preparation = policy._prepare_equipment_optimization(snapshot)
            ready = policy._equipment_departure_ready(snapshot)

        self.assertNotIn(
            "pending-random-teleport-suppression", preparation.blockers
        )
        self.assertTrue(ready)

    def test_unactionable_suppression_keeps_confirmed_loadout(self):
        stored = store_item(
            "b", 23, 17, name="Werewindle", known=True,
            fully_known=False, is_equipment=True, is_artifact=True,
            known_flags=frozenset({38, 74}),
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page([stored])
        worn = (
            item("main_hand", TVAL_SWORD, 1, is_equipment=True),
            item("light", TVAL_LITE, SV_LITE_TORCH, is_equipment=True),
        )
        snapshot = self._town(equipment=worn)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        owned = policy._equipment_catalog.items[0]
        current = current_loadout(policy._equipment_catalog.items)
        blocked = policy_module.WarriorOptimizationPreparation(
            current,
            SimpleNamespace(
                best=SimpleNamespace(loadout=current)
            ),
            None,
            ("pending-random-teleport-suppression",),
        )
        policy._prepare_equipment_optimization = lambda _snapshot: blocked
        seed_confirmed_loadout(policy, snapshot)

        self.assertTrue(policy._equipment_departure_ready(snapshot))

        refused = policy_module.WarriorOptimizationPreparation(
            SimpleNamespace(), None, None,
            ("pending-random-teleport-suppression",),
        )
        policy = HengbotPolicy()
        policy._prepare_equipment_optimization = lambda _snapshot: refused
        self.assertFalse(policy._equipment_departure_ready(self._town()))

    def test_blocked_home_refuses_departure_and_names_visible_exit(self):
        policy = HengbotPolicy()
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        blocked = SimpleNamespace(
            blockers=("home-withdrawal-required",),
            result=None,
            ready=False,
            transaction=None,
        )

        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=blocked
        ), patch.object(
            policy, "_activate_loadout_depth_fallback", return_value=None, create=True
        ), patch.object(policy, "_next_required_store_type", return_value=None):
            self.assertFalse(policy._equipment_departure_ready(self._town()))
            self.assertEqual(
                policy._terminal_equipment_blocker(self._town()),
                "equipment-home-unavailable",
            )

    def test_pending_home_equipment_work_blocks_when_home_is_available(self):
        policy = HengbotPolicy()
        blocked = SimpleNamespace(
            blockers=("home-withdrawal-required",),
            result=None,
            ready=False,
            transaction=None,
        )

        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=blocked
        ):
            self.assertFalse(policy._equipment_departure_ready(self._town()))

    def test_blocked_home_does_not_steal_outside_home_transaction(self):
        policy = HengbotPolicy()
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_EQUIP, "equip", "pack:upgrade"
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )
        blocked = SimpleNamespace(
            blockers=("home-withdrawal-required",),
            result=None,
            ready=False,
            transaction=None,
        )

        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=blocked
        ):
            self.assertFalse(policy._equipment_departure_ready(self._town()))

    def test_selected_home_suppression_creates_home_errand(self):
        stored = store_item(
            "b", 23, 17, name="Werewindle", known=True,
            fully_known=False, is_equipment=True, is_artifact=True,
            known_flags=frozenset({38, 74}),
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page([stored])
        policy._equipment_catalog.observe_home_page([stored])
        owned = policy._equipment_catalog.items[0]
        blocked = policy_module.WarriorOptimizationPreparation(
            SimpleNamespace(),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            SimpleNamespace(
                best=SimpleNamespace(
                    loadout=SimpleNamespace(item_ids=frozenset({owned.id}))
                )
            ),
            None,
            ("pending-random-teleport-suppression",),
        )
        policy._prepare_equipment_optimization = lambda _snapshot: blocked

        needs = policy._enumerate_town_needs(self._town())

        self.assertTrue(any(
            need.store_type == STORE_HOME
            and need.category == "equipment-catalog"
            for need in needs
        ))

    def test_withdraws_home_random_teleport_item_before_inscribing(self):
        mask = store_item(
            "b", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page([mask], allow_wrap=False)

        key = policy._town_random_teleport_suppression_key(
            self._town()
        )

        self.assertIsNone(key)
        self.assertEqual(
            policy._home_pending_item, policy._item_signature(mask)
        )

    def test_home_random_teleport_uses_derived_page_address_then_pack_inscription(self):
        evidence = [
            json.loads(line)
            for line in Path(
                "tests/fixtures/home_suppression_cycle_20260810.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        cycle = [row for row in evidence if 79 <= row["decision_sequence"] <= 85]
        self.assertEqual(
            [row["reason"] for row in cycle],
            [
                "home:store-context-exit",
                "shop:approach",
                "store:entry-await-observation",
                "shop:approach",
                "store:entry-await-observation",
                "home:store-context-exit",
            ],
        )
        self.assertTrue(all(row["town_plan"]["index"] == 0 for row in cycle))
        optimization = evidence[0]["equipment_optimization"]
        self.assertNotIn("incomplete_items", evidence[0])
        self.assertEqual(optimization["incomplete_items"], 1)
        detail = optimization["incomplete_item_details"][0]
        self.assertEqual(
            (detail["origin"], detail["tval"], detail["sval"]),
            ("home", 23, 25),
        )

        fillers = [
            store_item("a", TVAL_POTION, index, name=f"filler-{index}")
            for index in range(12)
        ]
        sword = store_item(
            "a", 23, 25, name="selected sword", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge(tuple([*fillers, sword]))
        policy._home_page_size = 12

        def preparation(_snapshot):
            matching = [
                candidate for candidate in policy._equipment_catalog.items
                if policy_module.equipment_identity(candidate.item)
                == policy_module.equipment_identity(sword)
            ]
            loadout = Loadout(
                (("main_hand", matching[0]),) if matching else (),
                "one_handed" if matching else "empty",
            )
            evaluated = EvaluatedLoadout(
                loadout, LoadoutMetrics(0.0, 0.0, 0.0)
            )
            result = OptimizationResult(
                evaluated, (), (), frozenset(), 1, 1, 0, 0.0,
                False, frozenset(),
            )
            return policy_module.WarriorOptimizationPreparation(
                loadout,
                result,
                None,
                ("pending-random-teleport-suppression",) if matching else (),
            )

        policy._prepare_equipment_optimization = preparation
        entrance = replace(
            self._town(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_HOME
                )
            },
        )

        policy._shopping_approach_store_type = STORE_HOME
        policy._town_errand_plan = policy_module.TownErrandPlan(
            [STORE_HOME],
            need_categories={STORE_HOME: ("equipment-catalog",)},
        )
        entry_key = policy.choose_key(entrance)
        self.assertEqual(entry_key, WAIT_KEY)
        self.assertTrue(policy.confirm_key_posted(entry_key))
        home_plan = policy._town_errand_plan
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")
        self.assertEqual(
            policy._home_random_teleport_withdrawal,
            policy._item_signature(sword),
        )
        registry_calls = []
        specs = []
        for spec in policy._town_need_registry():
            if spec.category != "equipment-catalog":
                specs.append(spec)
                continue
            original_satisfied = spec.satisfied

            def observed_satisfied(snapshot, original=original_satisfied):
                registry_calls.append(snapshot.turn)
                return original(snapshot)

            specs.append(replace(spec, satisfied=observed_satisfied))
        policy._town_need_specs = tuple(specs)

        carried = item(
            "q", 23, 25, name=sword.name, known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        inside = replace(
            entrance,
            store=StoreState(
                STORE_HOME, [sword], stock_num=1, page_top=0, page_size=52
            ),
        )
        self.assertEqual(policy.choose_key(inside), " pa\x1b")
        outside = replace(entrance, inventory=[carried], turn=1)
        self.assertEqual(
            policy._inventory_signature_count(
                outside, policy._item_signature(sword)
            ),
            1,
        )
        self.assertEqual(
            policy.choose_key(outside),
            INSCRIBE_KEY + "q.\r",
        )
        self.assertEqual(policy.last_reason, "equipment:suppress-random-teleport")
        self.assertEqual(registry_calls, [outside.turn])
        self.assertEqual(
            (
                policy._town_visit_ledger.store_visits[STORE_HOME],
                home_plan.index,
                home_plan.current_stop_passes,
                home_plan.completed_this_visit,
            ),
            (1, 1, 0, [STORE_HOME]),
        )
    def test_repeated_home_suppression_actions_do_not_grow_catalog(self):
        stored = store_item(
            "b", 23, 17, name="Werewindle", known=True,
            fully_known=False, is_equipment=True, is_artifact=True,
            known_flags=frozenset({38, 74}),
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page([stored], allow_wrap=False)
        catalog_size = len(policy._equipment_catalog.items)
        policy._prepare_equipment_optimization = (
            lambda _snapshot: SimpleNamespace(
                # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
                result=SimpleNamespace(
                    best=SimpleNamespace(
                        loadout=SimpleNamespace(item_ids=frozenset())
                    )
                )
            )
        )

        for inscription in ("{.}", "{.} ", "{.}  "):
            visible = replace(stored, name=f"Werewindle {inscription}")
            policy._town_random_teleport_suppression_key(
                self._town(store=StoreState(STORE_HOME, [visible]))
            )
            self.assertEqual(len(policy._equipment_catalog.items), catalog_size)

    def test_zero_pack_space_defers_home_suppression_to_existing_disposal(self):
        stored = store_item(
            "a", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((stored,))
        owned = policy._equipment_catalog.items[0]
        loadout = Loadout((("head", owned),), "empty")
        evaluated = EvaluatedLoadout(
            loadout, LoadoutMetrics(0.0, 0.0, 0.0)
        )
        result = OptimizationResult(
            evaluated, (), (), frozenset(), 1, 1, 0, 0.0,
            False, frozenset(),
        )
        preparation = policy_module.WarriorOptimizationPreparation(
            loadout,
            result,
            None,
            ("pending-random-teleport-suppression",),
        )
        policy._prepare_equipment_optimization = lambda _snapshot: preparation
        full_pack = [
            item(
                chr(ord("a") + index), TVAL_POTION, SV_POTION_SLEEP,
                name=f"sleep-{index}", known=True,
            )
            for index in range(PACK_CAPACITY)
        ]
        snapshot = self._town(inventory=full_pack)

        key = policy.choose_key(snapshot)

        self.assertTrue(key.startswith("01k"), key)
        self.assertNotIn(BUY_KEY, key)
        self.assertIsNone(policy._home_pending_item)

    def test_home_suppression_arming_is_outside_and_uses_town_pack_predicate(self):
        stored = store_item(
            "a", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((stored,))
        owned = policy._equipment_catalog.items[0]
        loadout = Loadout((("head", owned),), "empty")
        evaluated = EvaluatedLoadout(
            loadout, LoadoutMetrics(0.0, 0.0, 0.0)
        )
        result = OptimizationResult(
            evaluated, (), (), frozenset(), 1, 1, 0, 0.0,
            False, frozenset(),
        )
        preparation = policy_module.WarriorOptimizationPreparation(
            loadout,
            result,
            None,
            ("pending-random-teleport-suppression",),
        )
        policy._prepare_equipment_optimization = lambda _snapshot: preparation
        inventory = [
            item(
                chr(ord("a") + index), TVAL_POTION, SV_POTION_SLEEP,
                name=f"sleep-{index}", known=True,
            )
            for index in range(PACK_CAPACITY - MIN_FREE_PACK_SLOTS + 1)
        ]
        outside = self._town(inventory=inventory)

        self.assertFalse(policy._town_pack_space_ready(outside))
        self.assertIsNone(policy._town_random_teleport_suppression_key(outside))
        self.assertIsNone(policy._home_pending_item)

        inside = replace(outside, inventory=[], store=StoreState(STORE_HOME, [stored]))
        self.assertIsNone(policy._town_random_teleport_suppression_key(inside))
        self.assertIsNone(policy._home_pending_item)

        roomy = replace(outside, inventory=inventory[:-1])
        self.assertTrue(policy._town_pack_space_ready(roomy))
        self.assertIsNone(policy._town_random_teleport_suppression_key(roomy))
        self.assertEqual(
            policy._home_pending_item, policy._item_signature(stored)
        )

    def test_deferred_home_suppression_is_not_actionable_for_departure(self):
        stored = store_item(
            "a", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((stored,))
        owned = policy._equipment_catalog.items[0]
        loadout = Loadout((("head", owned),), "empty")
        evaluated = EvaluatedLoadout(
            loadout, LoadoutMetrics(0.0, 0.0, 0.0)
        )
        result = OptimizationResult(
            evaluated, (), (), frozenset(), 1, 1, 0, 0.0,
            False, frozenset(),
        )
        preparation = policy_module.WarriorOptimizationPreparation(
            loadout,
            result,
            None,
            ("pending-random-teleport-suppression",),
        )
        snapshot = replace(
            self._town(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_HOME
                )
            },
        )

        self.assertTrue(
            policy._random_teleport_suppression_actionable(snapshot, preparation)
        )
        policy._deferred_home_items.add(policy._item_signature(stored))
        self.assertFalse(
            policy._random_teleport_suppression_actionable(snapshot, preparation)
        )

    def test_leaves_store_before_inscribing_carried_item(self):
        mask = item(
            "a", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()

        key = policy._town_random_teleport_suppression_key(
            self._town(
                inventory=(mask,),
                store=StoreState(STORE_HOME, []),
            )
        )

        self.assertEqual(key, LEAVE_STORE_KEY)

    def test_inscribes_equipped_random_teleport_item(self):
        mask = item(
            "head", 32, 5, name="Terror Mask", known=True, fully_known=True,
            is_equipment=True, known_flags=frozenset({TR_TELEPORT}),
        )
        policy = HengbotPolicy()

        key = policy._town_random_teleport_suppression_key(
            self._town(equipment=(mask,))
        )

        self.assertEqual(key, "{/j.\r")

    def test_cursed_random_teleport_item_is_not_inscribed(self):
        mask = item(
            "a", 32, 5, name="Cursed Terror Mask", known=True,
            fully_known=True, is_equipment=True, is_cursed=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        self.assertIsNone(
            HengbotPolicy()._town_random_teleport_suppression_key(
                self._town(inventory=(mask,))
            )
        )

    def test_already_suppressed_home_item_is_not_withdrawn_again(self):
        mask = store_item(
            "b", 32, 5, name="Terror Mask {.}", known=True,
            fully_known=True, is_equipment=True, is_artifact=True,
            known_flags=frozenset({TR_TELEPORT}),
        )
        self.assertIsNone(
            HengbotPolicy()._town_random_teleport_suppression_key(
                self._town(store=StoreState(STORE_HOME, [mask]))
            )
        )

    def test_home_processing_withdraws_only_incomplete_equipment(self):
        complete = store_item(
            "a", 23, 1, name="known sword", aware=True, known=True,
            fully_known=True, is_equipment=True,
        )
        incomplete = store_item(
            "b", 23, 2, name="unknown sword", aware=False, known=False,
            is_equipment=True,
        )
        snap = self._town(store=StoreState(STORE_HOME, [complete, incomplete]))

        candidate = HengbotPolicy()._find_home_candidate(snap)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.name, "unknown sword")

    def test_prime_does_not_claim_pack_identification_candidate_is_in_home(self):
        complete = item(
            "a", 23, 1, name="known sword", known=True, fully_known=True,
            is_equipment=True,
        )
        incomplete = item(
            "b", 23, 2, name="unknown sword", aware=False, known=False,
            is_equipment=True,
        )
        policy = HengbotPolicy()

        policy.prime(self._town(inventory=(complete, incomplete)))

        self.assertEqual(policy._home_pending_batch, [])

    def test_prime_does_not_claim_pack_light_is_in_home(self):
        lamp = item(
            "n", TVAL_LITE, 2, name="unknown permanent light",
            known=False, fully_known=False, is_equipment=True,
            pseudo_feeling="excellent",
        )
        policy = HengbotPolicy()

        policy.prime(self._town(inventory=(lamp,)))

        self.assertEqual(policy._home_pending_batch, [])

    def test_identification_owner_predicate_does_not_create_home_claims(self):
        items = (
            item(
                "a", 23, 1, name="unknown ego", known=False,
                fully_known=False, is_equipment=True, pseudo_feeling="excellent",
            ),
            item(
                "b", 23, 2, name="average unknown", known=False,
                fully_known=False, is_equipment=True, pseudo_feeling="average",
            ),
            item(
                "c", 23, 3, name="partial ego", known=True,
                fully_known=False, is_equipment=True, is_ego=True,
            ),
            item(
                "d", 23, 4, name="complete ego", known=True,
                fully_known=True, is_equipment=True, is_ego=True,
            ),
            item("e", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="scroll"),
        )
        policy = HengbotPolicy()

        policy.prime(self._town(inventory=items))

        self.assertTrue(any(policy._identification_flow_candidate(item) for item in items))
        self.assertEqual(policy._home_pending_batch, [])

    def test_unidentified_scroll_belongs_to_use_flow_not_identification_flow(self):
        scroll = item(
            "a", TVAL_SCROLL, SV_SCROLL_IDENTIFY,
            name="unidentified scroll", aware=False, known=False,
        )
        policy = HengbotPolicy()

        self.assertEqual(TVAL_SCROLL, 70)
        self.assertEqual(scroll.tval, 70)
        self.assertTrue(scroll.is_scroll)
        snapshot = self._town(inventory=(scroll,))
        self.assertEqual(policy._read_key(snapshot, scroll), "ra")
        self.assertFalse(policy._identification_flow_candidate(scroll))
        self.assertFalse(policy._normal_identification_flow_candidate(scroll))
        self.assertFalse(policy._identification_flow_owns(scroll))

    def test_carried_identification_writeoff_flows_into_optimizer_preparation(self):
        unknown = item(
            "z", TVAL_RING, -1, name="terrible unknown ring", aware=False,
            known=False, fully_known=False, is_equipment=True,
        )
        snapshot = self._town(inventory=(unknown,))
        snapshot = replace(
            snapshot,
            player=replace(
                snapshot.player,
                stat_cur=(18, 10, 10, 10, 10, 10),
                stat_max=(18, 10, 10, 10, 10, 10),
                stat_use=(18, 10, 10, 10, 10, 10),
                stat_index=(15, 3, 3, 3, 3, 3),
            ),
        )
        policy = HengbotPolicy(monrace_knowledge={
            1: MonraceKnowledge(
                1, 110, False, False, level=1, max_melee_damage=1,
                average_hp=1, armor_class=1, rarity=1,
            )
        })
        seed_character_calibration(policy, snapshot)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([])

        blocked = policy._prepare_equipment_optimization(snapshot)
        self.assertNotIn("incomplete-equipment-catalog", blocked.blockers)
        self.assertEqual(blocked.result.incomplete_item_ids, frozenset())
        self.assertNotIn(
            next(
                owned.id for owned in policy._equipment_catalog.items
                if owned.item is unknown
            ),
            policy._equipment_optimization_search_surviving_ids,
        )

        policy._town_unidentifiable_carried_sigs.add(
            policy._item_signature(unknown)
        )
        policy._equipment_optimization_signature = None
        policy._equipment_optimization_preparation = None
        written_off = policy._prepare_equipment_optimization(snapshot)

        self.assertNotIn("incomplete-equipment-catalog", written_off.blockers)
        self.assertEqual(written_off.result.incomplete_item_ids, frozenset())

    def test_optimizer_preserves_identification_owned_pack_item(self):
        pending = item(
            "a", 23, 3, name="partial ego", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        policy = HengbotPolicy()
        snapshot = self._town(inventory=(pending,))
        seed_character_calibration(policy, snapshot)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        policy._home_pending_batch = [policy._item_signature(pending)]
        captured = {}

        def fake_prepare(*args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(ready=False, transaction=None)

        with patch("hengbot.policy_equipment.prepare_warrior_optimization", fake_prepare):
            policy._prepare_equipment_optimization(snapshot)

        owned = next(iter(policy._equipment_catalog.items))
        self.assertIn(owned.id, captured["preserve_pack_item_ids"])

    def test_withdraw_transaction_cycle_falls_through_without_redeposit(self):
        pending = item(
            "k", 23, 3, name="partial ego", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            "pack:pending",
            item_identity=policy_module.equipment_identity(pending),
        )
        policy = HengbotPolicy()
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )
        policy._home_pending_batch = [policy._item_signature(pending)]
        policy._prepare_equipment_optimization = lambda _snapshot: None
        snapshot = self._town(
            inventory=(pending,), store=StoreState(STORE_HOME, [])
        )

        transaction_key = policy._equipment_transaction_home_key(snapshot)
        next_home_handler_called = False
        if transaction_key is None:
            next_home_handler_called = True
            transaction_key = "identify-next"

        self.assertEqual(transaction_key, "identify-next")
        self.assertTrue(next_home_handler_called)
        self.assertEqual(
            policy.last_reason,
            "equipment-transaction:defer-identification",
        )
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertIn(
            "pack:pending", policy._equipment_transaction_failed_items
        )

    def test_home_unreachable_then_open_shop_leaves_without_crashing(self):
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            "pack:blocked",
            item_identity=("blocked",),
        )
        policy = HengbotPolicy()
        session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 1)
        )
        policy._equipment_transaction_session = session
        policy._shopping_approach_step = lambda _snapshot, _store_type: None
        outside = self._town()

        self.assertEqual(policy.choose_key(outside), "5")
        self.assertEqual(
            policy.last_reason, "equipment-transaction:home-route-unavailable"
        )

        opened_shop = replace(
            outside,
            store=StoreState(STORE_ALCHEMIST, []),
            turn=outside.turn + 1,
        )
        self.assertEqual(policy.choose_key(opened_shop), "\x1b")
        self.assertEqual(
            policy.last_reason,
            "town:blocked:equipment-transaction:home-route-unavailable",
        )
        self.assertIsNone(policy._equipment_transaction_session)

    def test_equipment_block_in_open_store_returns_visible_exit(self):
        policy = HengbotPolicy()
        policy._town_blocked_reason = "equipment-transaction:home-unreachable"
        snapshot = self._town(store=StoreState(STORE_ALCHEMIST, []))

        self.assertEqual(policy._town_blocked_key(snapshot), "\x1b")
        self.assertEqual(
            policy.last_reason,
            "town:blocked:equipment-transaction:home-unreachable",
        )

    def test_choose_key_defensively_exits_store_on_none_decision(self):
        policy = HengbotPolicy()
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        policy._decide = lambda _snapshot: None
        snapshot = self._town(store=StoreState(STORE_ALCHEMIST, []))

        self.assertEqual(policy.choose_key(snapshot), "\x1b")
        self.assertEqual(policy.last_reason, "policy:none-store-exit")


    def test_transaction_deposits_fully_known_item_unchanged(self):
        known = item(
            "k", 23, 3, name="complete ego", known=True,
            fully_known=True, is_equipment=True, is_ego=True,
        )
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            "pack:known",
            item_identity=policy_module.equipment_identity(known),
        )
        policy = HengbotPolicy()
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )
        policy._prepare_equipment_optimization = lambda _snapshot: None

        key = policy._equipment_transaction_home_key(
            self._town(inventory=(known,), store=StoreState(STORE_HOME, []))
        )

        self.assertEqual(key, "dk\r")
        self.assertEqual(policy.last_reason, "equipment-transaction:deposit")

    def test_recorded_free_action_withdrawals_survive_live_leave_latch(self):
        for item_id, name in (
            ("home:9dbac83f7ea707d2:0", "free action boots"),
            ("home:e5b4dcf79746ccda:0", "Black Clothes"),
        ):
            with self.subTest(item_id=item_id):
                ware = store_item(
                    "a", 30, 1, name=name, known=True, fully_known=True,
                    is_equipment=True, known_flags=frozenset({46}),
                )
                action = policy_module.EquipmentTransaction(
                    policy_module.PHASE_HOME_PREPARE,
                    "withdraw",
                    item_id,
                    item_identity=policy_module.equipment_identity(ware),
                )
                policy = HengbotPolicy()
                session = policy_module.EquipmentTransactionSession(
                    policy_module.EquipmentTransactionPlan((action,), (), 1)
                )
                policy._equipment_transaction_session = session
                policy._prepare_equipment_optimization = lambda _snapshot: None
                policy.consume_home_knowledge((ware,))
                home = self._town(store=StoreState(STORE_HOME, [ware]))
                # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
                policy._store_leave_inflight = (
                    policy._decision_sequence, home.turn, STORE_HOME
                )
                # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
                with patch.object(
                    policy, "_decide", side_effect=AssertionError("planned")
                ):
                    self.assertEqual(policy.choose_key(home), "\r")
                self.assertIsNone(session.pending_action)
                self.assertIsNone(session.prepared_action)
                self.assertNotIn(item_id, policy._equipment_transaction_failed_items)

                # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
                policy._store_leave_inflight = None
                key = policy._equipment_transaction_home_key(home)
                self.assertEqual(key, LEAVE_STORE_KEY)
                self.assertIsNone(session.pending_action)
                for _ in range(4):
                    session.observe(
                        policy_module.observe_equipment_transactions(home)
                    )
                self.assertEqual(session.blockers, [])
                self.assertNotIn(item_id, policy._equipment_transaction_failed_items)

    def test_unconfirmed_store_context_never_plans_item_command(self):
        home = self._town(store=StoreState(STORE_HOME, []))
        for command in ("pa\r", "da\r", "Ea", "ra", "ua", "qa"):
            policy = HengbotPolicy()
            # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
            policy._store_leave_inflight = (
                policy._decision_sequence, home.turn, STORE_HOME
            )
            # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
            with self.subTest(command=command), patch.object(
                policy, "_decide", return_value=command
            ) as decide:
                self.assertEqual(policy.choose_key(home), "\r")
                decide.assert_not_called()

    def test_optimizer_preserves_inferior_pack_weapon_for_smith_sale(self):
        policy = HengbotPolicy()
        spare = item(
            "b", 23, 0, name="mundane spare", known=True, fully_known=True,
            is_equipment=True,
        )
        snap = self._town(inventory=(spare,), equipment=(
            item(
                "main_hand", 23, 8, name="ego weapon", known=True,
                fully_known=True, is_equipment=True, is_ego=True,
            ),
        ))
        seed_character_calibration(policy, snap)
        policy._equipment_catalog.refresh_carried(snap.inventory, snap.equipment)
        captured = {}

        def fake_prepare(*args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(ready=False, transaction=None)

        with patch("hengbot.policy_equipment.prepare_warrior_optimization", fake_prepare):
            policy._prepare_equipment_optimization(snap)

        spare_id = next(
            owned.id for owned in policy._equipment_catalog.items
            if owned.origin == "pack"
        )
        self.assertIn(spare_id, captured["preserve_pack_item_ids"])

    def test_consumable_purchase_does_not_invalidate_equipment_search_cache(self):
        policy = HengbotPolicy()
        snapshot = self._town()
        seed_character_calibration(policy, snapshot)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        preparation = SimpleNamespace(ready=False, transaction=None)

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            return_value=preparation,
        ) as prepare:
            first = policy._prepare_equipment_optimization(snapshot)
            policy._town_visit_purchases.add(("Flask of oil", TVAL_FLASK, SV_FLASK_OIL))
            second = policy._prepare_equipment_optimization(snapshot)

        self.assertIs(first, second)
        prepare.assert_called_once()

    def test_pack_slot_change_replans_without_repeating_equipment_search(self):
        policy = HengbotPolicy()
        snapshot = self._town()
        seed_character_calibration(policy, snapshot)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        best = SimpleNamespace(loadout=SimpleNamespace())
        old_plan = SimpleNamespace(blockers=(), actions=())
        preparation = policy_module.WarriorOptimizationPreparation(
            current=SimpleNamespace(),
            result=SimpleNamespace(best=best),
            transaction=old_plan,
            blockers=(),
        )
        new_plan = SimpleNamespace(blockers=(), actions=())
        fuller_snapshot = replace(
            snapshot,
            inventory=[item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY)],
        )

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            return_value=preparation,
        ) as prepare, patch(
            "hengbot.policy_equipment.plan_equipment_transactions",
            return_value=new_plan,
        ) as replan:
            policy._prepare_equipment_optimization(snapshot)
            updated = policy._prepare_equipment_optimization(fuller_snapshot)

        prepare.assert_called_once()
        replan.assert_called_once()
        self.assertIs(updated.transaction, new_plan)
        self.assertEqual(replan.call_args.kwargs["current_pack_items"], 1)

    def test_pack_space_block_still_executes_leading_home_deposits(self):
        deposit = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            "pack:spare",
            item_identity="spare",
        )
        withdraw = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "withdraw",
            "home:upgrade",
            item_identity="upgrade",
        )
        plan = policy_module.EquipmentTransactionPlan(
            (deposit, withdraw),
            ("pack-space-required:5",),
            28,
        )
        preparation = SimpleNamespace(
            ready=False,
            blockers=plan.blockers,
            transaction=plan,
        )

        session = HengbotPolicy._equipment_transaction_session_for_preparation(
            preparation
        )

        self.assertIsNotNone(session)
        self.assertTrue(session.executable)
        self.assertEqual(session.plan.actions, (deposit,))

    def test_non_pack_blocker_cannot_start_partial_equipment_transaction(self):
        deposit = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            "pack:spare",
            item_identity="spare",
        )
        plan = policy_module.EquipmentTransactionPlan(
            (deposit,),
            ("incomplete-equipment-catalog",),
            22,
        )
        preparation = SimpleNamespace(
            ready=False,
            blockers=plan.blockers,
            transaction=plan,
        )

        self.assertIsNone(
            HengbotPolicy._equipment_transaction_session_for_preparation(
                preparation
            )
        )

    def test_timeout_latches_across_equipment_mutations_for_town_visit(self):
        policy = HengbotPolicy()
        snapshot = self._town(equipment=(
            item(
                "bow", TVAL_BOW, 23, name="crossbow", known=True,
                fully_known=True, is_equipment=True, to_d=4,
            ),
        ))
        seed_character_calibration(policy, snapshot)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        timed_out = SimpleNamespace(
            ready=False,
            transaction=None,
            blockers=("optimization-timeout",),
        )
        enchanted = replace(
            snapshot,
            equipment=[replace(snapshot.equipment[0], to_d=5)],
        )

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            return_value=timed_out,
        ) as prepare:
            first = policy._prepare_equipment_optimization(snapshot)
            policy._equipment_catalog.refresh_carried(
                enchanted.inventory, enchanted.equipment
            )
            second = policy._prepare_equipment_optimization(enchanted)

        self.assertIs(first, second)
        prepare.assert_called_once()

    def test_pending_fixed_quest_does_not_replace_dungeon_objective_depth(self):
        policy = HengbotPolicy()
        seed_character_calibration(policy, self._town())
        policy._deepest_level = 20
        policy._target_dungeon_id = DUNGEON_ANGBAND
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._conquest_committed = DUNGEON_YEEK_CAVE
        policy._dungeon_knowledge[DUNGEON_YEEK_CAVE] = SimpleNamespace(
            min_depth=1, max_depth=13
        )
        policy._quest_knowledge[2] = SimpleNamespace(level=15)
        snapshot = self._town()
        captured = {}

        def fake_prepare(*args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(ready=False, transaction=None, blockers=())

        with patch.object(
            policy,
            "_carry_procurement_strategy",
            return_value=SimpleNamespace(quest_id=2),
        ), patch("hengbot.policy_equipment.prepare_warrior_optimization", fake_prepare):
            policy._prepare_equipment_optimization(snapshot)

        self.assertIsNone(captured["depth"])

    def test_taken_fixed_quest_also_keeps_dungeon_objective_depth(self):
        policy = HengbotPolicy()
        policy._deepest_level = 21
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._conquest_committed = DUNGEON_YEEK_CAVE
        policy._dungeon_knowledge[DUNGEON_YEEK_CAVE] = SimpleNamespace(
            min_depth=1, max_depth=13
        )
        policy._quest_knowledge[14] = SimpleNamespace(level=5)
        snapshot = replace(
            self._town(),
            quests={
                14: QuestState(
                    id=14,
                    status=QUEST_STATUS_TAKEN,
                    fixed=True,
                    level=5,
                )
            },
        )

        with patch.object(
            policy,
            "approved_quest_strategy",
            return_value=SimpleNamespace(quest_id=14),
        ):
            self.assertEqual(policy._equipment_optimization_depth(snapshot), 19)

    def test_no_valid_loadout_is_terminal_after_store_routes_are_spent(self):
        policy = HengbotPolicy()
        snapshot = self._town()
        preparation = SimpleNamespace(blockers=("no-valid-loadout",))

        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=preparation
        ), patch.object(policy, "_next_required_store_type", return_value=None):
            self.assertEqual(
                policy._terminal_equipment_blocker(snapshot),
                "equipment-no-valid-loadout",
            )

        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=preparation
        ), patch.object(
            policy, "_next_required_store_type", return_value=STORE_WEAPON
        ):
            self.assertIsNone(policy._terminal_equipment_blocker(snapshot))

    def test_no_valid_21f_loadout_equips_owned_20f_kit_and_keeps_angband(self):
        policy = HengbotPolicy()
        policy._deepest_level = 20
        policy._target_dungeon_id = DUNGEON_ANGBAND
        policy._dungeon_knowledge[7] = SimpleNamespace(min_depth=15)
        snapshot = replace(
            self._town(),
            player=replace(
                self._town().player,
                abilities=frozenset({"free_action", "resist_conf", "resist_fire"}),
            ),
        )
        invalid = SimpleNamespace(
            blockers=("no-valid-loadout",),
            result=SimpleNamespace(best=None),
        )
        valid_20f = SimpleNamespace(
            blockers=(),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=SimpleNamespace())),
        )

        def prepare(_snapshot, *, depth_override=None):
            return valid_20f if depth_override == 20 else invalid

        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
        with patch.object(
            policy, "_carry_procurement_strategy", return_value=None
        ), patch.object(
            policy, "_prepare_equipment_optimization", side_effect=prepare
        ), patch.object(
            policy, "_next_required_store_type", return_value=None
        ), patch.object(
            policy, "_pick_alternate_dungeon", return_value=7
        ) as picker:
            self.assertFalse(hasattr(policy, "_activate_loadout_depth_fallback"))
            self.assertEqual(policy._equipment_optimization_depth(snapshot), 19)

        picker.assert_not_called()
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertIsNone(policy._alternate_dungeon)
        self.assertIsNone(policy._equipment_optimization_preparation)

    def test_no_valid_20f_loadout_equips_owned_19f_kit_and_keeps_angband(self):
        """The first resistance gate must be able to fall back below 20F."""
        policy = HengbotPolicy()
        policy._deepest_level = 19
        policy._target_dungeon_id = DUNGEON_ANGBAND
        snapshot = replace(
            self._town(),
            recall_depth=19,
            recall_dungeon_id=DUNGEON_ANGBAND,
            dungeon_recall_depths={DUNGEON_ANGBAND: 19},
        )
        invalid = SimpleNamespace(
            blockers=("no-valid-loadout",),
            result=SimpleNamespace(best=None),
        )
        valid_19f = SimpleNamespace(
            blockers=(),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=SimpleNamespace())),
        )

        def prepare(_snapshot, *, depth_override=None):
            return valid_19f if depth_override == 19 else invalid

        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
        with patch.object(
            policy, "_carry_procurement_strategy", return_value=None
        ), patch.object(
            policy, "_prepare_equipment_optimization", side_effect=prepare
        ), patch.object(
            policy, "_next_required_store_type", return_value=None
        ), patch.object(
            policy, "_pick_alternate_dungeon"
        ) as picker:
            self.assertFalse(hasattr(policy, "_activate_loadout_depth_fallback"))

        picker.assert_not_called()
        self.assertEqual(policy._equipment_optimization_depth(snapshot), 19)
        self.assertIsNone(policy._equipment_optimization_preparation)

    def test_pending_quest_procurement_does_not_create_dungeon_fallback(self):
        policy = HengbotPolicy()
        policy._deepest_level = 17
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._conquest_committed = DUNGEON_YEEK_CAVE
        policy._dungeon_knowledge[DUNGEON_YEEK_CAVE] = SimpleNamespace(
            min_depth=1, max_depth=13
        )
        policy._dungeon_knowledge[7] = SimpleNamespace(min_depth=15)
        snapshot = self._town()
        preparation = SimpleNamespace(blockers=("no-valid-loadout",))
        pending_strategy = SimpleNamespace(quest_id=31)
        policy._quest_knowledge[31] = SimpleNamespace(level=22)

        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
        with patch.object(
            policy, "_carry_procurement_strategy", return_value=pending_strategy
        ), patch.object(
            policy, "_prepare_equipment_optimization", return_value=preparation
        ), patch.object(
            policy, "_next_required_store_type", return_value=None
        ), patch.object(
            policy, "_pick_alternate_dungeon", return_value=7
        ) as picker:
            self.assertFalse(hasattr(policy, "_activate_loadout_depth_fallback"))

        picker.assert_not_called()
        self.assertEqual(policy._target_dungeon_id, DUNGEON_YEEK_CAVE)

    def test_shallow_fallback_depth_overrides_pending_quest_depth(self):
        policy = HengbotPolicy()
        policy._alternate_dungeon = 7
        policy._dungeon_knowledge[7] = SimpleNamespace(min_depth=15)
        snapshot = replace(
            self._town(),
            dungeon_recall_depths={7: 18},
        )
        pending_strategy = SimpleNamespace(quest_id=31)
        policy._quest_knowledge[31] = SimpleNamespace(level=22)

        with patch.object(
            policy, "_carry_procurement_strategy", return_value=pending_strategy
        ):
            self.assertEqual(policy._equipment_optimization_depth(snapshot), 19)

    def test_timed_out_21f_loadout_switches_to_shallower_dungeon(self):
        policy = HengbotPolicy()
        policy._deepest_level = 23
        policy._target_dungeon_id = DUNGEON_ANGBAND
        policy._dungeon_knowledge[4] = SimpleNamespace(
            id=4, min_depth=10, min_player_level=1
        )
        snapshot = replace(
            self._town(),
            entered_dungeon_ids=(DUNGEON_ANGBAND, 3, 4),
            dungeon_recall_depths={DUNGEON_ANGBAND: 31, 3: 23, 4: 18},
        )
        timed_out = SimpleNamespace(
            blockers=("optimization-timeout",),
            result=SimpleNamespace(best=None),
        )
        valid_19f = SimpleNamespace(
            blockers=(),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=SimpleNamespace())),
        )

        def prepare(_snapshot, *, depth_override=None):
            return valid_19f if depth_override == 19 else timed_out

        with patch.object(
            policy, "_carry_procurement_strategy", return_value=None
        ), patch.object(
            policy, "_prepare_equipment_optimization", side_effect=prepare
        ), patch.object(
            policy, "_next_required_store_type", return_value=None
        ):
            self.assertFalse(hasattr(policy, "_activate_loadout_depth_fallback"))

        self.assertEqual(policy._equipment_optimization_depth(snapshot), 19)

    def test_cancels_deep_recall_when_loadout_is_not_confirmed(self):
        policy = HengbotPolicy()
        recall = item(
            "r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            count=2, known=True, name="Word of Recall",
        )
        snapshot = replace(
            self._town(),
            player=player(
                10, 10, word_recall=10, class_id=PLAYER_CLASS_WARRIOR
            ),
            inventory=[recall],
            recall_dungeon_id=DUNGEON_ANGBAND,
            dungeon_recall_depths={DUNGEON_ANGBAND: 31},
        )

        with patch.object(
            policy, "_activate_loadout_depth_fallback", return_value=None, create=True
        ), patch.object(
            policy, "_equipment_departure_ready", return_value=False
        ):
            self.assertEqual(policy._town_cancel_unsafe_recall_key(snapshot), "rr")

        self.assertEqual(policy.last_reason, "town:cancel-unready-recall")

class ConfirmedLoadoutPublicPathPinTest(unittest.TestCase):
    """Pin confirmed-loadout reuse through choose_key and the real optimizer."""

    @staticmethod
    def _monster():
        return MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=0, rarity=1,
        )

    @staticmethod
    def _supplies():
        return [
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
        ]

    @staticmethod
    def _equipment(*, fuel=5000):
        return [
            item(
                "main_hand", TVAL_SWORD, 4, name="Main Gauche",
                known=True, fully_known=True, is_equipment=True,
                damage_dice_num=1, damage_dice_sides=5,
            ),
            item(
                "sub_hand", 34, 2, name="Small Metal Shield",
                known=True, fully_known=True, is_equipment=True, ac=3,
            ),
            item(
                "body", 36, 2, name="Soft Leather Armour",
                known=True, fully_known=True, is_equipment=True, ac=4,
            ),
            item(
                "light", TVAL_LITE, SV_LITE_LANTERN, name="Brass Lantern",
                fuel=fuel, known=True, fully_known=True, is_equipment=True,
            ),
        ]

    def _town(self, *, fuel=5000, inventory=(), equipment=None):
        base = replace(
            player(
                10, 10, class_id=PLAYER_CLASS_WARRIOR, level=10,
                hp=100, max_hp=100,
            ),
            stat_cur=(18, 10, 10, 18), stat_use=(18, 10, 10, 18),
            melee_skill=60, saving_skill=30, shield_skill=0,
            two_weapon_skill=0,
        )
        return Snapshot(
            base,
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*self._supplies(), *inventory],
            equipment=(
                self._equipment(fuel=fuel)
                if equipment is None
                else list(equipment)
            ),
            recall_dungeon_id=DUNGEON_ANGBAND,
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )

    def _policy(self, snapshot, path):
        policy = HengbotPolicy(monrace_knowledge={1: self._monster()})
        policy._confirmed_loadout_path = path
        policy._floor_key = snapshot.floor_key
        policy._char_dump_done_this_visit = True
        policy._equipment_catalog.home_scan_complete = True
        seed_character_calibration(policy, snapshot)
        return policy

    @staticmethod
    def _zero_budget(real_prepare):
        def prepare(*args, **kwargs):
            return real_prepare(*args, **kwargs, timeout_seconds=0.0)
        return prepare

    def test_home_upgrade_invalidates_confirmation_through_choose_key(self):
        baseline = self._town()
        carried_blade = item(
            "u", TVAL_SWORD, 17, name="Blade of Chaos (6d5) (+15,+20)",
            known=True, fully_known=True, is_equipment=True,
            to_h=15, to_d=20, damage_dice_num=6, damage_dice_sides=5,
        )
        carried_plate = item(
            "v", 37, 3, name="Mithril Plate Mail", known=True,
            fully_known=True, is_equipment=True, ac=35, to_a=15,
        )
        blade = store_item(
            "A", TVAL_SWORD, 17, name="Blade of Chaos (6d5) (+15,+20)",
            known=True, fully_known=True, is_equipment=True,
            to_h=15, to_d=20, damage_dice_num=6, damage_dice_sides=5,
        )
        plate = store_item(
            "B", 37, 3, name="Mithril Plate Mail", known=True,
            fully_known=True, is_equipment=True, ac=35, to_a=15,
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "confirmed-loadout.json"
            completed = self._policy(baseline, path)
            self.assertEqual(completed.choose_key(baseline), "R300\r")
            self.assertTrue(path.is_file())

            looted = replace(
                baseline,
                inventory=[
                    *baseline.inventory, carried_blade, carried_plate,
                ],
                turn=baseline.turn + 1,
            )
            carrying = self._policy(looted, path)
            real_prepare = policy_module.prepare_warrior_optimization
            with patch(
                "hengbot.policy_equipment.prepare_warrior_optimization",
                side_effect=self._zero_budget(real_prepare),
            ):
                carried_key = carrying.choose_key(looted)
            self.assertNotEqual(carried_key, "rra")
            self.assertEqual(
                carrying.last_reason,
                "town:blocked:equipment-optimization-timeout",
            )

            restarted = self._policy(baseline, path)
            restarted._equipment_catalog.home_scan_complete = False
            restarted._equipment_catalog.observe_home_page([blade, plate])
            restarted._equipment_catalog.observe_home_page([])
            restarted._equipment_catalog.observe_home_page([blade, plate])
            with patch(
                "hengbot.policy_equipment.prepare_warrior_optimization",
                side_effect=self._zero_budget(real_prepare),
            ):
                key = restarted.choose_key(baseline)

            self.assertNotEqual(key, "rra")
            self.assertEqual(
                restarted.last_reason,
                "town:blocked:equipment-optimization-timeout",
            )

    def test_fuel_tick_reuses_confirmation_through_choose_key(self):
        baseline = self._town(fuel=5000)
        ticked = self._town(fuel=4999)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "confirmed-loadout.json"
            completed = self._policy(baseline, path)
            self.assertEqual(completed.choose_key(baseline), "R300\r")
            self.assertTrue(path.is_file())

            restarted = self._policy(ticked, path)
            real_prepare = policy_module.prepare_warrior_optimization
            with patch(
                "hengbot.policy_equipment.prepare_warrior_optimization",
                side_effect=self._zero_budget(real_prepare),
            ):
                key = restarted.choose_key(ticked)

            self.assertEqual(key, "rra")
            self.assertEqual(restarted.last_reason, "town:recall-to-angband")

    def test_light_only_home_upgrade_refuses_through_choose_key(self):
        light = self._equipment()[-1]
        snapshot = self._town(equipment=[light])
        home_gear = [
            store_item(
                "A", TVAL_SWORD, 17,
                name="Blade of Chaos (6d5) (+15,+20)", known=True,
                fully_known=True, is_equipment=True, to_h=15, to_d=20,
                damage_dice_num=6, damage_dice_sides=5,
            ),
            store_item(
                "B", 37, 3, name="Mithril Plate Mail", known=True,
                fully_known=True, is_equipment=True, ac=35, to_a=15,
            ),
        ]
        with TemporaryDirectory() as directory:
            policy = self._policy(
                snapshot, Path(directory) / "confirmed-loadout.json"
            )
            policy._equipment_catalog.home_scan_complete = False
            policy._equipment_catalog.observe_home_page(home_gear)
            policy._equipment_catalog.observe_home_page([])
            real_prepare = policy_module.prepare_warrior_optimization
            with patch(
                "hengbot.policy_equipment.prepare_warrior_optimization",
                side_effect=self._zero_budget(real_prepare),
            ):
                key = policy.choose_key(snapshot)
        self.assertNotEqual(key, "rra")
        self.assertEqual(
            policy.last_reason, "town:blocked:equipment-optimization-timeout"
        )

    def test_dual_shovel_incident_refuses_through_choose_key(self):
        shovels = [
            item(
                letter, TVAL_DIGGING, SV_DIGGING_SHOVEL,
                name=f"Shovel {letter}", known=True, fully_known=True,
                is_equipment=True, damage_dice_num=1, damage_dice_sides=2,
            )
            for letter in ("u", "v")
        ]
        snapshot = self._town(
            inventory=shovels, equipment=[self._equipment()[-1]]
        )
        with TemporaryDirectory() as directory:
            policy = self._policy(
                snapshot, Path(directory) / "confirmed-loadout.json"
            )
            real_prepare = policy_module.prepare_warrior_optimization
            with patch(
                "hengbot.policy_equipment.prepare_warrior_optimization",
                side_effect=self._zero_budget(real_prepare),
            ):
                key = policy.choose_key(snapshot)
        self.assertNotEqual(key, "rra")
        self.assertEqual(
            policy.last_reason, "town:blocked:equipment-optimization-timeout"
        )

    def test_light_only_pack_incident_refuses_through_choose_key(self):
        packed = [
            item(
                "u", TVAL_SWORD, 1, name="packed sword", known=True,
                fully_known=True, is_equipment=True,
                damage_dice_num=1, damage_dice_sides=6,
            ),
            item(
                "v", 36, 1, name="packed armour", known=True,
                fully_known=True, is_equipment=True, ac=8,
            ),
        ]
        snapshot = self._town(
            inventory=packed, equipment=[self._equipment()[-1]]
        )
        with TemporaryDirectory() as directory:
            policy = self._policy(
                snapshot, Path(directory) / "confirmed-loadout.json"
            )
            real_prepare = policy_module.prepare_warrior_optimization
            with patch(
                "hengbot.policy_equipment.prepare_warrior_optimization",
                side_effect=self._zero_budget(real_prepare),
            ):
                key = policy.choose_key(snapshot)
        self.assertNotEqual(key, "rra")
        self.assertEqual(
            policy.last_reason, "town:blocked:equipment-optimization-timeout"
        )

    def test_changed_inputs_do_not_republish_stale_confirmation(self):
        baseline = self._town()
        upgrade = item(
            "u", TVAL_SWORD, 17,
            name="Blade of Chaos (6d5) (+15,+20)", known=True,
            fully_known=True, is_equipment=True, to_h=15, to_d=20,
            damage_dice_num=6, damage_dice_sides=5,
        )
        first = replace(
            baseline, inventory=[*baseline.inventory, upgrade],
            turn=baseline.turn + 1,
        )
        changed = replace(
            first,
            inventory=[
                *first.inventory,
                item(
                    "v", 37, 3, name="Mithril Plate Mail", known=True,
                    fully_known=True, is_equipment=True, ac=35, to_a=15,
                ),
            ],
            turn=first.turn + 1,
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "confirmed-loadout.json"
            completed = self._policy(baseline, path)
            self.assertEqual(completed.choose_key(baseline), "R300\r")

            policy = self._policy(first, path)
            real_prepare = policy_module.prepare_warrior_optimization
            with patch(
                "hengbot.policy_equipment.prepare_warrior_optimization",
                side_effect=self._zero_budget(real_prepare),
            ):
                self.assertNotEqual(policy.choose_key(first), "rra")
                key = policy.choose_key(changed)
        self.assertNotEqual(key, "rra")
        self.assertEqual(
            policy._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ],
            "stale-republished",
        )

    def test_known_best_not_worn_refuses_through_choose_key(self):
        upgrade = item(
            "u", TVAL_SWORD, 17,
            name="Blade of Chaos (6d5) (+15,+20)", known=True,
            fully_known=True, is_equipment=True, to_h=15, to_d=20,
            damage_dice_num=6, damage_dice_sides=5,
        )
        snapshot = self._town(inventory=[upgrade])
        with TemporaryDirectory() as directory:
            policy = self._policy(
                snapshot, Path(directory) / "confirmed-loadout.json"
            )
            key = policy.choose_key(snapshot)
        self.assertNotEqual(key, "rra")
        preparation = policy._equipment_optimization_preparation
        self.assertIsNotNone(preparation.result.best)
        self.assertNotEqual(
            preparation.current.item_ids,
            preparation.result.best.loadout.item_ids,
        )

    def test_public_naked_snapshot_replaces_stale_worn_catalog_and_dresses(self):
        """23:35:55 regression: one record cannot claim nine worn items and EQUIP 0."""
        packed = [
            replace(self._equipment()[0], slot="u"),
            replace(self._equipment()[3], slot="v"),
        ]
        naked = self._town(inventory=packed, equipment=[])
        stale_equipment = [
            *self._equipment(),
            item(
                "main_ring", TVAL_RING, 1, name="stale ring one",
                known=True, fully_known=True, is_equipment=True,
            ),
            item(
                "sub_ring", TVAL_RING, 2, name="stale ring two",
                known=True, fully_known=True, is_equipment=True,
            ),
            item(
                "amulet", TVAL_AMULET, 1, name="stale amulet",
                known=True, fully_known=True, is_equipment=True,
            ),
            item(
                "cloak", 35, 1, name="stale cloak",
                known=True, fully_known=True, is_equipment=True,
            ),
            item(
                "head", 32, 1, name="stale helm",
                known=True, fully_known=True, is_equipment=True,
            ),
        ]

        class BoundaryCapture:
            def __init__(self):
                self.origins = None

            def choose_key(capture, policy, snapshot):
                capture.origins = Counter(
                    owned.origin for owned in policy._equipment_catalog.items
                )
                return policy._choose_key_with_latch_capture(snapshot)

        with TemporaryDirectory() as directory:
            policy = self._policy(
                naked, Path(directory) / "confirmed-loadout.json"
            )
            policy._equipment_catalog.refresh_carried([], stale_equipment)
            capture = BoundaryCapture()
            policy._home_entry_capture = capture

            key = policy.choose_key(naked)

        self.assertEqual(
            capture.origins,
            Counter({"pack": 2}),
            "contradiction: snapshot EQUIP 0 but the decision boundary still "
            "reports the stale nine-slot equipped catalogue",
        )
        state = policy.equipment_optimization_state(None)
        self.assertEqual(
            state["search_catalog_origins"],
            {"equipped": 0, "pack": 2, "home": 0},
        )
        self.assertEqual(state["current_loadout_slots"], 0)
        self.assertTrue(state["current_loadout_empty"])
        preparation = policy._equipment_optimization_preparation
        self.assertIsNotNone(preparation)
        self.assertIsNotNone(preparation.transaction, preparation)
        self.assertTrue(preparation.transaction.actions)
        self.assertTrue(any(
            action.kind in {"equip", "reposition"}
            for action in preparation.transaction.actions
        ))
        self.assertNotEqual(state["result_source"], "signature-cache-hit")
        self.assertTrue(key.startswith(equipment_mutation_module.WIELD_KEY), key)
        self.assertEqual(policy.last_reason, "equipment-transaction:equip")

    def test_selected_loadout_derives_the_deepest_satisfied_band(self):
        def equipment_with_flags(flags):
            return [
                replace(owned, known_flags=frozenset(flags))
                if owned.slot == "body" else owned
                for owned in self._equipment()
            ]

        cases = (
            (self._equipment(), 19, "real character"),
            (equipment_with_flags({46, 50}), 20, "free action and fire"),
            (equipment_with_flags({48, 49, 50, 51, 52}), 30, "four elements"),
        )
        for equipment, expected, label in cases:
            with self.subTest(loadout=label), TemporaryDirectory() as directory:
                snapshot = replace(
                    self._town(equipment=equipment),
                    dungeon_recall_depths={DUNGEON_ANGBAND: 35},
                )
                policy = self._policy(
                    snapshot, Path(directory) / "confirmed-loadout.json"
                )

                policy.choose_key(snapshot)

                self.assertEqual(policy._equipment_optimization_last_depth, expected)

    def test_owned_loadout_target_ignores_transport_inputs_and_ends_wearing(self):
        """47 owned items, zero chaos sources: dress for the deepest feasible band."""
        light = self._equipment()[-1]
        elemental_mail = item(
            "u", 37, 3, name="Elemental Mail", known=True,
            fully_known=True, is_equipment=True, ac=12, to_a=8,
            known_flags=frozenset({48, 49, 50, 51, 52}),
        )
        town_sword = item(
            "main_hand", TVAL_SWORD, 4, name="Town Sword", known=True,
            fully_known=True, is_equipment=True,
            damage_dice_num=2, damage_dice_sides=5, to_h=5, to_d=5,
        )
        pack_gear = [
            elemental_mail,
            *[
                item(
                    chr(ord("w") + index), 45, index + 1,
                    name=f"pack ring {index}", known=True,
                    fully_known=True, is_equipment=True, is_cursed=True,
                )
                for index in range(5)
            ],
        ]
        snapshot = replace(
            self._town(
                inventory=[
                    item(
                        "s", TVAL_STAFF, SV_STAFF_IDENTIFY,
                        name="Staff of Identify", known=True,
                        fully_known=True, charges=20,
                    ),
                    *pack_gear,
                ],
                equipment=[town_sword, light],
            ),
            player=replace(self._town().player, level=29, gold=15000),
            dungeon_recall_depths={DUNGEON_ANGBAND: 30},
        )
        snapshot = replace(
            snapshot,
            inventory=[
                replace(owned, count=20)
                if owned.tval == TVAL_SCROLL
                and owned.sval == SV_SCROLL_WORD_OF_RECALL
                else owned
                for owned in snapshot.inventory
            ],
        )
        policy = self._policy(snapshot, None)
        policy._deepest_level = 29
        policy._target_dungeon_id = DUNGEON_ANGBAND
        policy._town_was_in_town = True
        policy._town_visit_ledger.approach_fails[STORE_BLACK] = (
            policy_module.TOWN_STOP_PASS_LIMIT
        )
        home_gear = [
            store_item(
                chr(ord("A") + (index % 26)), 45, index + 20,
                name=f"home ring {index}", known=True,
                fully_known=True, is_equipment=True, is_cursed=True,
            )
            for index in range(39)
        ]
        policy._equipment_catalog.home_scan_complete = False
        policy._equipment_catalog.observe_home_page(home_gear)
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.home_scan_complete = True
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        incident_preparation = policy._prepare_equipment_optimization(snapshot)
        elemental_owned = next(
            owned for owned in policy._equipment_catalog.items
            if {48, 49, 50, 51, 52}.issubset(owned.flags)
        )
        self.assertTrue({48, 49, 50, 51, 52}.issubset(elemental_owned.flags))
        self.assertNotIn("no-valid-loadout", incident_preparation.blockers)
        self.assertEqual(policy._equipment_optimization_depth(snapshot), 30)
        self.assertEqual(len(policy._equipment_catalog.items), 47)
        self.assertEqual(policy._equipment_optimization_depth(snapshot), 30)
        preparation = incident_preparation
        self.assertIsNotNone(preparation.result.best)
        best = preparation.result.best.loadout
        self.assertNotIn(62, best.flags)
        self.assertTrue({48, 49, 50, 51, 52}.issubset(best.flags))

        worn = [replace(owned.item, slot=slot) for slot, owned in best.slots]
        dressed = replace(
            snapshot,
            turn=snapshot.turn + 1,
            inventory=list(self._supplies()),
            equipment=worn,
        )
        policy.choose_key(dressed)
        dressed_preparation = (
            policy._equipment_optimization_preparation
            or policy._prepare_equipment_optimization(dressed)
        )
        def target_loadout(preparation):
            return tuple(sorted(
                (slot, policy_module.equipment_identity(owned.item))
                for slot, owned in preparation.result.best.loadout.slots
            ))

        stable_target = target_loadout(dressed_preparation)

        worn_flags = set().union(
            *(owned.known_flags for owned in dressed.equipment)
        )
        self.assertTrue({48, 49, 50, 51, 52}.issubset(worn_flags))
        self.assertIn("Elemental Mail", {owned.name for owned in dressed.equipment})
        self.assertGreater(len(dressed.equipment), 1, "fallback left the character naked")

        changed_snapshots = [
            replace(dressed, dungeon_recall_depths={DUNGEON_ANGBAND: depth})
            for depth in range(30, 36)
        ]
        changed_snapshots.extend((
            replace(dressed, inventory=[*dressed.inventory, item(
                "z", TVAL_SCROLL, 1, name="irrelevant scroll", known=True
            )]),
            replace(dressed, player=replace(dressed.player, gold=197)),
        ))
        for index, changed in enumerate(changed_snapshots):
            policy.choose_key(changed)
            changed_preparation = (
                policy._equipment_optimization_preparation
                or policy._prepare_equipment_optimization(changed)
            )
            self.assertEqual(
                target_loadout(changed_preparation),
                stable_target,
                f"target changed for transport-only variant {index}: "
                f"recall={changed.dungeon_recall_depths}, "
                f"pack={len(changed.inventory)}, gold={changed.player.gold}",
            )

    def test_write_oserror_allows_completion_but_not_fresh_process(self):
        snapshot = self._town()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "confirmed-loadout.json"
            completed = self._policy(snapshot, path)
            with patch.object(Path, "write_text", side_effect=OSError("read-only")):
                self.assertEqual(completed.choose_key(snapshot), "R300\r")
            self.assertFalse(path.exists())

            restarted = self._policy(snapshot, path)
            real_prepare = policy_module.prepare_warrior_optimization
            with patch(
                "hengbot.policy_equipment.prepare_warrior_optimization",
                side_effect=self._zero_budget(real_prepare),
            ):
                key = restarted.choose_key(snapshot)
        self.assertNotEqual(key, "rra")
        self.assertEqual(
            restarted.last_reason,
            "town:blocked:equipment-optimization-timeout",
        )

    def test_record_fail_closed_shapes_refuse_through_choose_key(self):
        snapshot = self._town()
        shapes = {
            "missing": None,
            "corrupt": "not json",
            "old-schema": json.dumps({"item_ids": ["legacy"]}),
            "empty": json.dumps({}),
            "partial": json.dumps({
                "item_ids": ["equipped:partial:0"],
                "optimizer_input_key": "short",
            }),
        }
        for name, contents in shapes.items():
            with self.subTest(name=name), TemporaryDirectory() as directory:
                path = Path(directory) / "confirmed-loadout.json"
                if contents is not None:
                    path.write_text(contents, encoding="utf-8")
                policy = self._policy(snapshot, path)
                real_prepare = policy_module.prepare_warrior_optimization
                with patch(
                    "hengbot.policy_equipment.prepare_warrior_optimization",
                    side_effect=self._zero_budget(real_prepare),
                ):
                    key = policy.choose_key(snapshot)
                self.assertNotEqual(key, "rra")
                self.assertEqual(
                    policy.last_reason,
                    "town:blocked:equipment-optimization-timeout",
                )

    def test_policy_signature_orders_duplicate_ids_by_identity_only(self):
        snapshot = self._town()
        policy = self._policy(snapshot, None)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        owned = list(policy._equipment_catalog._carried.values())
        first, second = owned[:2]
        duplicate = replace(
            second, id=first.id, origin=first.origin,
            equipped_slot=None if first.equipped_slot is not None else "light",
        )
        policy._equipment_catalog._carried = {
            "first": first,
            "duplicate": duplicate,
            **{
                f"rest-{index}": entry
                for index, entry in enumerate(owned[2:])
            },
        }

        preparation = policy._prepare_equipment_optimization(snapshot)

        self.assertIsNotNone(preparation)

class EquipmentQuarantineInvariantTest(unittest.TestCase):
    """A quarantine can never remove the last owned source of a required gate.

    2026-08-02 20:06: quarantining the only resist_chaos source at optimization
    depth 31 produced considered=0 / no-valid-loadout, equipment_departure_ready
    false, and an absorbing town state whose only exit was the loop guard.  The
    release valve could not fire because the deferred-Home filter had already
    removed the item from the catalog the valve scans.
    """

    RING_NAME = "Ring of Law (+5,+0) [+5] (+2)"

    def _monster(self):
        return MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=1, armor_class=0, rarity=1,
            blows=(MonsterBlow("HIT", "HURT", 1, 4),),
        )

    def _ring(self):
        return store_item(
            "J", TVAL_RING, 4, name=self.RING_NAME, known=True,
            fully_known=True, is_equipment=True, known_flags=frozenset({62}),
        )

    def _town(self):
        base = player(
            10, 10, class_id=PLAYER_CLASS_WARRIOR, level=30, hp=400,
            max_hp=400,
        )
        base = replace(
            base,
            stat_cur=(18, 10, 10, 18), stat_use=(18, 10, 10, 18),
            melee_skill=60, saving_skill=40, shield_skill=0,
            two_weapon_skill=0,
        )
        return Snapshot(
            base,
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[],
            equipment=[
                item(
                    "main_hand", 23, 4, name="long sword", known=True,
                    fully_known=True, is_equipment=True, to_h=5, to_d=5,
                ),
                item(
                    "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000,
                    is_equipment=True, known=True, fully_known=True,
                ),
            ],
        )

    def _policy_with_home_ring(self):
        policy = HengbotPolicy(monrace_knowledge={1: self._monster()})
        town = self._town()
        seed_character_calibration(policy, town)
        ring = self._ring()
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([ring])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([ring])
        ring_id = next(
            owned.id
            for owned in policy._equipment_catalog.items
            if owned.origin == "home"
        )
        return policy, town, ring, ring_id

    def test_deferred_quarantine_never_removes_last_required_gate_source(self):
        policy, town, ring, ring_id = self._policy_with_home_ring()
        policy._deferred_home_items.add(policy._item_signature(ring))

        preparation = policy._prepare_equipment_optimization(
            town, depth_override=31
        )

        self.assertNotIn(
            "no-valid-loadout", preparation.blockers,
            "the deferred-Home quarantine removed the only resist_chaos source "
            "from the depth-31 optimization view (the 20:06:11 absorbing state)",
        )
        self.assertIn(ring_id, policy._equipment_quarantine_readmitted_ids)
        # The quarantine itself is not mutated: readmission is view-only.
        self.assertIn(
            policy._item_signature(ring), policy._deferred_home_items
        )

    def test_deferred_and_stall_quarantine_overlap_keeps_last_gate_source(self):
        # The live-consistent state: the withdraw stall blacklisted the item id
        # while the identification deferral held its signature, which blinded
        # the pre-existing release valve (it scans the already-filtered view).
        policy, town, ring, ring_id = self._policy_with_home_ring()
        policy._deferred_home_items.add(policy._item_signature(ring))
        policy._equipment_transaction_failed_items.add(ring_id)

        preparation = policy._prepare_equipment_optimization(
            town, depth_override=31
        )

        self.assertNotIn("no-valid-loadout", preparation.blockers)
        self.assertIn(ring_id, policy._equipment_quarantine_readmitted_ids)
        self.assertIn(ring_id, policy._equipment_transaction_failed_items)

    def test_stall_abandon_cannot_absorb_last_gate_source(self):
        # End-to-end stall kind: the posted withdraw exhausts its confirmation
        # budget, _release_stalled_equipment_transaction abandons and
        # quarantines it — the next optimization pass must still see the item.
        policy, town, ring, ring_id = self._policy_with_home_ring()
        # Prime the town observation first: the fresh-town reset clears the
        # visit-scoped deferral set, and both quarantines arise mid-visit.
        policy.choose_key(town)
        policy._deferred_home_items.add(policy._item_signature(ring))
        identity = policy_module.equipment_identity(ring)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "withdraw",
            ring_id, item_identity=identity,
        )
        session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 23)
        )
        policy._equipment_transaction_session = session
        home_observation = (
            policy_module.EquipmentTransactionObservation.create(in_home=True)
        )
        self.assertTrue(session.dispatch(action, home_observation))
        for _ in range(policy_module.EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT):
            session.observe(home_observation)

        home = replace(
            town,
            store=StoreState(store_type=STORE_HOME, items=[self._ring()]),
        )
        key = policy.choose_key(home)
        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(
            policy.last_reason,
            "equipment-transaction:confirmation-stall-bound",
        )
        self.assertIn(ring_id, policy._equipment_transaction_failed_items)

        preparation = policy._prepare_equipment_optimization(
            town, depth_override=31
        )
        self.assertNotIn(
            "no-valid-loadout", preparation.blockers,
            "the confirmation-stall quarantine removed the last owned "
            "resist_chaos source from the depth-31 optimization view",
        )
        self.assertIn(ring_id, policy._equipment_quarantine_readmitted_ids)

        # The same physical kind now arrives in an equipped view with a new
        # origin-prefixed catalogue id.  The stall producer above and this
        # consumer share the same policy instance; quarantine must survive it.
        moved = item(
            "main_ring", TVAL_RING, 4, name=self.RING_NAME, known=True,
            fully_known=True, is_equipment=True, known_flags=frozenset({62}),
        )
        policy._equipment_catalog.refresh_carried(
            town.inventory, (*town.equipment, moved)
        )
        moved_owned = next(
            owned
            for owned in policy._equipment_catalog.items
            if owned.origin == "equipped" and owned.item.slot == "main_ring"
        )
        self.assertNotEqual(moved_owned.id, ring_id)
        moved_town = replace(town, equipment=(*town.equipment, moved))
        moved_preparation = policy._prepare_equipment_optimization(moved_town)
        self.assertEqual(
            moved_preparation.blockers,
            ("equipment-transaction-failed",),
            "the consumed quarantine must stop a real pack-origin target, not "
            "merely remain discoverable through a private helper",
        )

    def test_failed_equipped_takeoff_quarantines_same_item_after_pack_move(self):
        """M6 equipped->pack: a real refused takeoff changes selection."""
        policy, town, _ring, _ring_id = self._policy_with_home_ring()
        worn_ring = item(
            "main_ring", TVAL_RING, 4, name=self.RING_NAME, known=True,
            fully_known=True, is_equipment=True, known_flags=frozenset({62}),
        )
        worn = replace(town, equipment=(*town.equipment, worn_ring))
        policy = HengbotPolicy(monrace_knowledge={1: self._monster()})
        seed_character_calibration(policy, worn)
        policy._equipment_catalog.observe_home_page([])
        policy._town_was_in_town = True

        def remove_ring(snapshot, items, *_args, **_kwargs):
            current = current_loadout(items)
            target = Loadout(
                tuple(
                    (slot, owned)
                    for slot, owned in current.slots
                    if slot != "main_ring"
                ),
                current.hand_mode,
            )
            result = OptimizationResult(
                EvaluatedLoadout(target, LoadoutMetrics(1.0, 1.0, 1.0)),
                (), (), frozenset(), 1, 1, 0, 0.0, False, frozenset(),
            )
            return policy_module.WarriorOptimizationPreparation(
                current, result,
                policy_module.EquipmentTransactionPlan(
                    (), (), len(snapshot.inventory)
                ),
                (),
            )

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            side_effect=remove_ring,
        ):
            takeoff = policy.choose_key(worn)
            self.assertTrue(takeoff.startswith(equipment_mutation_module.TAKEOFF_KEY))
            self.assertTrue(policy.confirm_key_posted(takeoff))
            for turn in range(
                1, policy_module.EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT + 3
            ):
                # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: unchanged equipped observations are the real refusal evidence that exhausts the posted takeoff confirmation window
                policy.choose_key(replace(worn, turn=turn))
                if policy._equipment_transaction_failed_items:
                    break
        equipped_id = next(
            key
            for key in policy._equipment_transaction_failed_items
            if key.startswith("equipped:")
        )

        moved_ring = replace(worn_ring, slot="a")
        moved = replace(
            town, inventory=(moved_ring,), equipment=town.equipment,
            turn=worn.turn + policy_module.EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT + 4,
        )
        moved_catalog = OwnedEquipmentCatalog()
        moved_catalog.refresh_carried(moved.inventory, moved.equipment)
        moved_id = next(
            owned.id for owned in moved_catalog.items if owned.origin == "pack"
        )

        def select_ring(snapshot, items, *_args, **_kwargs):
            current = current_loadout(items)
            ring = next(
                (owned for owned in items if owned.origin == "pack"), None
            )
            if ring is None:
                return policy_module.WarriorOptimizationPreparation(
                    current, None, None, ("no-valid-loadout",),
                )
            target = Loadout(current.slots + (("main_ring", ring),), current.hand_mode)
            result = OptimizationResult(
                EvaluatedLoadout(target, LoadoutMetrics(1.0, 1.0, 1.0)),
                (), (), frozenset(), 1, 1, 0, 0.0, False, frozenset(),
            )
            return policy_module.WarriorOptimizationPreparation(
                current, result,
                policy_module.EquipmentTransactionPlan(
                    (), (), len(snapshot.inventory)
                ),
                (),
            )

        policy._equipment_transaction_session = None
        policy._equipment_catalog.refresh_carried(
            moved.inventory, moved.equipment
        )
        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            side_effect=select_ring,
        ):
            consumed = policy._prepare_equipment_optimization(moved)

        self.assertNotEqual(
            equipped_id,
            moved_id,
        )
        self.assertEqual(consumed.blockers, ("equipment-transaction-failed",))

    def _second_ring(self):
        return store_item(
            "K", TVAL_RING, 4, name="Second Ring of Law [+3]", known=True,
            fully_known=True, is_equipment=True, known_flags=frozenset({62}),
        )

    def _policy_with_two_home_rings(self):
        policy = HengbotPolicy(monrace_knowledge={1: self._monster()})
        town = self._town()
        seed_character_calibration(policy, town)
        rings = [self._ring(), self._second_ring()]
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page(rings)
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page(rings)
        ring_ids = sorted(
            owned.id
            for owned in policy._equipment_catalog.items
            if owned.origin == "home"
        )
        self.assertEqual(len(ring_ids), 2)
        return policy, town, rings, ring_ids

    def _stall_withdraw(self, policy, town, rings, ring_id):
        """Dispatch a withdraw of ring_id and exhaust its confirmation budget."""
        if policy._store_leave_inflight is not None:
            # A later outside snapshot confirms the previous stall's leave,
            # exactly as the live snapshot stream does between Home visits.
            policy.choose_key(
                replace(town, turn=town.turn + policy._decision_sequence + 10)
            )
            self.assertIsNone(policy._store_leave_inflight)
        # The one-cell fixture grid has no walkable Home approach, so the
        # intermediate town decision may have latched home-unreachable for a
        # session the optimizer built on its own.  Live towns have a real
        # route; drop the fixture artifact before dispatching our withdraw.
        policy._town_blocked_reason = None
        identity = next(
            policy_module.equipment_identity(owned.item)
            for owned in policy._equipment_catalog.items
            if owned.id == ring_id
        )
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "withdraw",
            ring_id, item_identity=identity,
        )
        session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 23)
        )
        policy._equipment_transaction_session = session
        home_observation = (
            policy_module.EquipmentTransactionObservation.create(in_home=True)
        )
        self.assertTrue(session.dispatch(action, home_observation))
        for _ in range(policy_module.EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT):
            session.observe(home_observation)
        home = replace(
            town, store=StoreState(store_type=STORE_HOME, items=list(rings)),
        )
        self.assertEqual(policy.choose_key(home), LEAVE_STORE_KEY)
        self.assertEqual(
            policy.last_reason,
            "equipment-transaction:confirmation-stall-bound",
        )
        self.assertIn(ring_id, policy._equipment_transaction_failed_items)

    def test_readmission_grants_one_source_per_missing_gate(self):
        # With SEVERAL quarantined sources of the same required flag, only ONE
        # may be readmitted: releasing the whole hidden equivalence class is
        # the rejected withdraw->stall->quarantine->release->withdraw cycle in
        # view-only form.
        policy, town, rings, ring_ids = self._policy_with_two_home_rings()
        for ring in rings:
            policy._deferred_home_items.add(policy._item_signature(ring))

        preparation = policy._prepare_equipment_optimization(
            town, depth_override=31
        )

        self.assertNotIn("no-valid-loadout", preparation.blockers)
        self.assertEqual(
            len(policy._equipment_quarantine_readmitted_ids), 1,
            "readmission released the whole quarantined equivalence class "
            "instead of the single next untried source",
        )
        self.assertIn(
            policy._equipment_quarantine_readmitted_ids[0], ring_ids
        )

    def test_burned_sources_rotate_and_exhaust_monotonically(self):
        # A readmitted source whose transaction stalls again is burned: the
        # next pass advances to a DIFFERENT source, and when every source has
        # been consumed the state is an honest no-valid-loadout owned by the
        # pre-existing depth-fallback/ledger exits — never a repeat of the
        # same failed withdrawal.
        policy, town, rings, ring_ids = self._policy_with_two_home_rings()
        policy.choose_key(town)  # fresh-town reset precedes the quarantines
        for ring in rings:
            policy._deferred_home_items.add(policy._item_signature(ring))

        first = policy._prepare_equipment_optimization(town, depth_override=31)
        self.assertNotIn("no-valid-loadout", first.blockers)
        self.assertEqual(policy._equipment_quarantine_readmitted_ids, ())
        self.assertEqual(policy._equipment_quarantine_readmitted_ids, ())
        state = policy.equipment_optimization_state(None)
        self.assertEqual(state.get("required_gate_sources", []), [])

    def test_valve_release_is_a_single_second_chance(self):
        # The pre-existing mutation valve releases a failed last source once;
        # a second stall burns it and the valve must NOT release it again —
        # otherwise the release/stall cycle continues through the valve even
        # with readmission fixed.
        policy, town, ring, ring_id = self._policy_with_home_ring()
        policy.choose_key(town)

        self._stall_withdraw(policy, town, [ring], ring_id)
        self.assertNotIn(ring_id, policy._equipment_quarantine_burned_ids)

        released = policy._prepare_equipment_optimization(
            town, depth_override=31
        )
        self.assertNotIn("no-valid-loadout", released.blockers)
        self.assertNotIn(ring_id, policy._equipment_transaction_failed_items)
        self.assertIn(
            ring_id, policy._equipment_quarantine_second_chance_ids
        )

        self._stall_withdraw(policy, town, [ring], ring_id)
        self.assertIn(ring_id, policy._equipment_quarantine_burned_ids)

        exhausted = policy._prepare_equipment_optimization(
            town, depth_override=31
        )
        self.assertIn("no-valid-loadout", exhausted.blockers)
        self.assertIn(ring_id, policy._equipment_transaction_failed_items)
        self.assertEqual(policy._equipment_quarantine_readmitted_ids, ())

    def test_no_valid_loadout_telemetry_names_missing_gate_sources(self):
        # A genuinely unowned gate is an honest no-valid-loadout; the state
        # record must say WHICH gate lacks sources and expose both quarantine
        # sets, which the 20:06:11 capture could not show.
        policy = HengbotPolicy(monrace_knowledge={1: self._monster()})
        town = self._town()
        seed_character_calibration(policy, town)
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([])

        preparation = policy._prepare_equipment_optimization(
            town, depth_override=31
        )
        self.assertIn("no-valid-loadout", preparation.blockers)

        state = policy.equipment_optimization_state(None)
        self.assertEqual(state["failed_transaction_item_ids"], [])
        self.assertEqual(state["deferred_home_item_signatures"], [])
        self.assertEqual(state["quarantine_readmitted_item_ids"], [])
        report = state["required_gate_sources"]
        self.assertEqual(report, [])

    def test_optimizer_candidate_telemetry_names_search_return_paths(self):
        policy, town, _ring, _ring_id = self._policy_with_home_ring()

        fresh = policy._prepare_equipment_optimization(town, depth_override=31)
        self.assertIsNotNone(fresh)
        state = policy.equipment_optimization_state(None)
        self.assertEqual(state["result_source"], "fresh-search")
        self.assertEqual(state["search_telemetry_freshness"], "current-inputs")
        self.assertEqual(state["search_catalog_items"], 3)
        self.assertEqual(
            state["search_catalog_origins"],
            {"equipped": 2, "pack": 0, "home": 1},
        )
        self.assertEqual(state["search_slot_candidate_counts"]["main_ring"], 1)

        policy._equipment_transaction_session = None
        cached = policy._prepare_equipment_optimization(town, depth_override=31)
        self.assertIs(cached, fresh)
        self.assertEqual(
            policy.equipment_optimization_state(None)["result_source"],
            "signature-cache-hit",
        )
        self.assertEqual(
            policy.equipment_optimization_state(None)["search_telemetry_freshness"],
            "current-inputs",
        )

        policy._equipment_transaction_session = SimpleNamespace(complete=False)
        inflight = policy._prepare_equipment_optimization(town, depth_override=31)
        self.assertIs(inflight, fresh)
        self.assertEqual(
            policy._equipment_optimization_telemetry["result_source"],
            "in-flight-session-return",
        )
        self.assertEqual(
            policy._equipment_optimization_telemetry["search_telemetry_freshness"],
            "current-inputs",
        )

        policy._equipment_transaction_session = None
        with patch.object(
            policy, "_validated_character_calibration", return_value=None
        ):
            calibration = policy._prepare_equipment_optimization(
                town, depth_override=31
            )
        self.assertIn("calibration-required", calibration.blockers)
        self.assertEqual(
            policy.equipment_optimization_state(None)["search_telemetry_freshness"],
            "current-inputs",
        )

        dungeon = replace(town, town_flag=False)
        stale = policy.equipment_optimization_state(dungeon)
        self.assertEqual(stale["search_telemetry_freshness"], "stale-republished")
        self.assertEqual(stale["result_source"], "calibration-required-return")

        policy._equipment_optimization_preparation = replace(
            fresh, blockers=("optimization-timeout",)
        )
        policy._equipment_optimization_timed_out_this_visit = True
        timed_out = policy._prepare_equipment_optimization(town)
        self.assertIs(timed_out, policy._equipment_optimization_preparation)
        timeout_state = policy.equipment_optimization_state(None)
        self.assertEqual(timeout_state["result_source"], "town-visit-timeout-return")
        self.assertEqual(
            timeout_state["search_telemetry_freshness"], "stale-republished"
        )

        guard = policy._prepare_equipment_optimization(dungeon)
        self.assertIsNone(guard)
        self.assertEqual(
            policy._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ],
            "stale-republished",
        )

    def test_optimizer_strategy_telemetry_names_full_search_nonempty_seed(self):
        from hengbot import warrior_optimization as warrior_module

        policy, town, _ring, _ring_id = self._policy_with_home_ring()

        with patch.object(
            warrior_module,
            "enumerate_warrior_loadouts",
            wraps=warrior_module.enumerate_warrior_loadouts,
        ) as selected_factory:
            policy._prepare_equipment_optimization(town, depth_override=31)
        state = policy.equipment_optimization_state(None)

        selected_factory.assert_called_once()
        self.assertEqual(state["search_strategy"], "enumerate_warrior_loadouts")
        self.assertEqual(state["search_seed"], "catalog")
        self.assertEqual(state["search_catalog_threshold"], 44)
        self.assertFalse(state["search_catalog_threshold_crossed"])
        self.assertEqual(state["current_loadout_slots"], 2)
        self.assertFalse(state["current_loadout_empty"])
        policy._prepare_equipment_optimization(replace(town, town_flag=False))
        self.assertEqual(
            policy._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ],
            "stale-republished",
        )

    def test_fresh_search_transition_diffs_successive_target_item_ids(self):
        policy, town, _ring, ring_id = self._policy_with_home_ring()
        policy.last_reason = "test:first-search"

        first = policy._prepare_equipment_optimization(town, depth_override=31)
        self.assertIsNotNone(first)
        first_transition = policy.equipment_optimization_state(None)[
            "fresh_search_transition"
        ]
        self.assertIn(ring_id, first_transition["item_ids"])
        self.assertEqual(first_transition["trigger_reason"], "test:first-search")

        policy._equipment_transaction_session = None
        policy._equipment_optimization_signature = None
        policy._equipment_catalog._home = {}
        policy._home_knowledge_items = ()
        policy.last_reason = "test:catalog-changed"
        second = policy._prepare_equipment_optimization(town, depth_override=31)
        self.assertIsNotNone(second)
        transition = policy.equipment_optimization_state(None)[
            "fresh_search_transition"
        ]
        self.assertNotIn(ring_id, transition["item_ids"])
        self.assertIn(ring_id, transition["removed_ids"])
        self.assertEqual(transition["trigger_reason"], "test:catalog-changed")

        policy._prepare_equipment_optimization(town, depth_override=31)
        cached = policy.equipment_optimization_state(None)
        self.assertEqual(cached["result_source"], "signature-cache-hit")
        self.assertNotIn("fresh_search_transition", cached)

        policy._prepare_equipment_optimization(replace(town, town_flag=False))
        stale = policy.equipment_optimization_state(None)
        self.assertNotIn("fresh_search_transition", stale)

    def test_optimizer_strategy_telemetry_names_incremental_empty_seed(self):
        from hengbot import warrior_optimization as warrior_module

        pack = [
            item(
                f"ring-{index}", TVAL_RING, index + 1,
                name=f"ring {index}", known=True, fully_known=True,
                is_equipment=True,
            )
            for index in range(PACK_CAPACITY)
        ]
        home = [
            store_item(
                f"H{index}", TVAL_RING, PACK_CAPACITY + index + 1,
                name=f"home ring {index}", known=True, fully_known=True,
                is_equipment=True,
            )
            for index in range(44 - PACK_CAPACITY)
        ]
        town = replace(
            self._town(),
            equipment=[],
            inventory=pack,
        )
        policy = HengbotPolicy(monrace_knowledge={1: self._monster()})
        seed_character_calibration(policy, town)
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page(home)
        policy._equipment_catalog.observe_home_page([])

        self.assertLessEqual(len(town.inventory), PACK_CAPACITY)
        self.assertEqual(len(policy._equipment_catalog.items), 44)

        with patch.object(
            warrior_module,
            "enumerate_single_slot_variants",
            wraps=warrior_module.enumerate_single_slot_variants,
        ) as selected_factory:
            policy._prepare_equipment_optimization(town, depth_override=1)
        state = policy.equipment_optimization_state(None)

        selected_factory.assert_called_once()
        self.assertEqual(
            state["search_strategy"], "enumerate_single_slot_variants"
        )
        self.assertEqual(state["search_seed"], "current-loadout")
        self.assertEqual(state["search_catalog_items"], 44)
        self.assertEqual(
            state["search_catalog_origins"],
            {"equipped": 0, "pack": PACK_CAPACITY, "home": 21},
        )
        self.assertTrue(state["search_catalog_threshold_crossed"])
        self.assertEqual(state["current_loadout_slots"], 0)
        self.assertTrue(state["current_loadout_empty"])
        policy._prepare_equipment_optimization(replace(town, town_flag=False))
        self.assertEqual(
            policy._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ],
            "stale-republished",
        )

    def test_optimizer_strategy_telemetry_names_full_search_empty_seed(self):
        town = replace(
            self._town(),
            equipment=[],
            inventory=[
                item(
                    f"ring-{index}", TVAL_RING, index + 1,
                    name=f"ring {index}", known=True, fully_known=True,
                    is_equipment=True,
                )
                for index in range(3)
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={1: self._monster()})
        seed_character_calibration(policy, town)
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([])

        policy._prepare_equipment_optimization(town, depth_override=1)
        state = policy.equipment_optimization_state(None)

        self.assertEqual(state["search_strategy"], "enumerate_warrior_loadouts")
        self.assertEqual(state["search_seed"], "catalog")
        self.assertFalse(state["search_catalog_threshold_crossed"])
        self.assertEqual(state["current_loadout_slots"], 0)
        self.assertTrue(state["current_loadout_empty"])

    def test_optimizer_strategy_telemetry_names_incremental_nonempty_seed(self):
        pack = [
            item(
                f"ring-{index}", TVAL_RING, index + 1,
                name=f"ring {index}", known=True, fully_known=True,
                is_equipment=True,
            )
            for index in range(PACK_CAPACITY - 2)
        ]
        home = [
            store_item(
                f"H{index}", TVAL_RING, PACK_CAPACITY + index + 1,
                name=f"home ring {index}", known=True, fully_known=True,
                is_equipment=True,
            )
            for index in range(44 - len(self._town().equipment) - len(pack))
        ]
        town = replace(
            self._town(),
            inventory=pack,
        )
        policy = HengbotPolicy(monrace_knowledge={1: self._monster()})
        seed_character_calibration(policy, town)
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page(home)
        policy._equipment_catalog.observe_home_page([])

        self.assertLessEqual(len(town.inventory), PACK_CAPACITY)
        self.assertEqual(len(policy._equipment_catalog.items), 44)

        policy._prepare_equipment_optimization(town, depth_override=1)
        state = policy.equipment_optimization_state(None)

        self.assertEqual(
            state["search_strategy"], "enumerate_single_slot_variants"
        )
        self.assertEqual(state["search_seed"], "current-loadout")
        self.assertTrue(state["search_catalog_threshold_crossed"])
        self.assertEqual(
            state["search_catalog_origins"],
            {"equipped": 2, "pack": 21, "home": 21},
        )
        self.assertEqual(state["current_loadout_slots"], 2)
        self.assertFalse(state["current_loadout_empty"])
        policy._prepare_equipment_optimization(replace(town, town_flag=False))
        self.assertEqual(
            policy._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ],
            "stale-republished",
        )

    def test_optimizer_strategy_telemetry_is_absent_when_search_is_blocked(self):
        town = self._town()
        policy = HengbotPolicy(monrace_knowledge={})
        seed_character_calibration(policy, town)
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([])

        preparation = policy._prepare_equipment_optimization(town, depth_override=1)
        state = policy.equipment_optimization_state(None)

        self.assertIn("missing-monrace-knowledge", preparation.blockers)
        self.assertNotIn("search_strategy", state)
        self.assertNotIn("search_seed", state)

    def test_search_surviving_gate_source_reports_post_exclusion_zero(self):
        town = replace(
            self._town(),
            inventory=[
                item(
                    "a", TVAL_LITE, SV_LITE_TORCH,
                    name="Torch of Chaos", fuel=5000, known=True,
                    fully_known=True, is_equipment=True,
                    known_flags=frozenset({62}),
                )
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={1: self._monster()})
        seed_character_calibration(policy, town)
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([])

        with patch.object(policy, "_retention_reservation", return_value=1):
            preparation = policy._prepare_equipment_optimization(
                town, depth_override=31
            )

        self.assertIn("no-valid-loadout", preparation.blockers)
        state = policy.equipment_optimization_state(None)
        self.assertEqual(state["required_gate_sources"], [])
        self.assertEqual(state["required_gate_search_surviving_sources"], [])
        excluded = state["search_excluded_items"]
        self.assertEqual(excluded["total"], 1)
        self.assertEqual(
            excluded["items"][0]["reasons"],
            ["torch-retention-reservation"],
        )

    def test_equipment_telemetry_characterization_does_not_change_decision(self):
        # Characterization only: the independent base-vs-tip snapshot replay is
        # the neutrality proof.  The new-field assertion keeps this pin from
        # passing if the telemetry change itself is reverted.
        for calibrated in (False, True):
            with self.subTest(calibrated=calibrated):
                if calibrated:
                    observed, town, _ring, _ring_id = self._policy_with_home_ring()
                    control, _, _, _ = self._policy_with_home_ring()
                else:
                    town = self._town()
                    observed = HengbotPolicy(
                        monrace_knowledge={1: self._monster()}
                    )
                    control = HengbotPolicy(
                        monrace_knowledge={1: self._monster()}
                    )
                    observed._equipment_catalog.refresh_carried(
                        town.inventory, town.equipment
                    )
                    control._equipment_catalog.refresh_carried(
                        town.inventory, town.equipment
                    )

                observed_state = observed.equipment_optimization_state(town)
                self.assertEqual(
                    observed_state["search_telemetry_freshness"],
                    "current-inputs",
                )
                observed_key = observed.choose_key(town)
                control_key = control.choose_key(town)

                self.assertEqual(observed_key, control_key)
                self.assertEqual(observed.last_reason, control.last_reason)

    def test_policy_state_capture_serializes_quarantine_sets(self):
        from hengbot.flight_recorder import policy_state

        policy, town, ring, ring_id = self._policy_with_home_ring()
        policy._deferred_home_items.add(policy._item_signature(ring))
        policy._equipment_transaction_failed_items.add(ring_id)

        captured = policy_state(policy)["state"]
        self.assertEqual(
            captured["_equipment_transaction_failed_items"], [ring_id]
        )
        self.assertEqual(
            captured["_deferred_home_items"],
            [[self.RING_NAME, TVAL_RING, 4]],
        )
        self.assertIn("_equipment_quarantine_readmitted_ids", captured)
        self.assertIn("_equipment_quarantine_second_chance_ids", captured)
        self.assertIn("_equipment_quarantine_burned_ids", captured)
        self.assertIn("_home_knowledge_current", captured)
        self.assertIn("_home_page_size", captured)

class EquipmentTransactionOwnershipRegressionTest(unittest.TestCase):
    """Pins for the stripped-loadout ring-sale incident."""

    def _stripped_fixture(self):
        policy, snapshot = town_fixture.NoSafeRecallDestinationTest()._fixture()
        source = snapshot.inventory[0]
        slots = tuple(policy_module.EQUIPMENT_SLOT_KEY)[:10]
        owned = []
        inventory = []
        for index, target_slot in enumerate(slots):
            item = replace(
                source,
                slot=chr(ord("a") + index),
                name=f"Transaction-owned ring {index}",
                sval=source.sval + index,
            )
            inventory.append(item)
            owned.append((policy_module.equipment_identity(item), target_slot))
        snapshot = replace(snapshot, inventory=inventory, equipment=[])
        blocked = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            "blocked-second-half",
            item_identity="missing-home-item",
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan(
                    (blocked,), ("home-route-unavailable",), len(inventory)
                )
            )
        )
        policy._equipment_transaction_owned_items = owned
        return policy, snapshot, inventory

    def test_public_blocked_mid_strip_owns_town_and_installs_full_restore(self):
        policy, snapshot, inventory = self._stripped_fixture()
        policy._shopping_approach_step = Mock(
            side_effect=AssertionError("unrelated shopping became reachable")
        )
        policy._current_store_sale_candidates = Mock(
            side_effect=AssertionError("sale classifier became reachable")
        )
        policy._town_destroy_key = Mock(
            side_effect=AssertionError("destruction became reachable")
        )

        key = policy.choose_key(snapshot)

        self.assertEqual(key, WAIT_KEY)
        self.assertTrue(policy._equipment_transaction_restoring)
        restore = policy._equipment_transaction_session
        self.assertIsNotNone(restore)
        self.assertEqual(len(restore.plan.actions), 10)
        self.assertEqual(
            {action.item_identity for action in restore.plan.actions},
            {policy_module.equipment_identity(item) for item in inventory},
        )
        self.assertTrue(all(action.kind == "equip" for action in restore.plan.actions))

    def test_transaction_owned_item_refused_by_classifier_guards(self):
        policy, snapshot, inventory = self._stripped_fixture()
        item = inventory[0]
        shop = replace(
            snapshot,
            store=StoreState(store_type=STORE_WEAPON, items=[]),
        )

        self.assertEqual(policy._retention_surplus(snapshot, item), 0)
        self.assertTrue(policy._equipment_disposal_reserved(snapshot, item))
        self.assertNotIn(item, policy._current_store_sale_candidates(shop))
        self.assertFalse(policy._entire_stack_is_surplus(snapshot, item))

    def test_restarted_inside_home_retained_digger_yields_then_exits(self):
        """The live 21:18:51 restart must pass a released owner's None onward."""
        shovel = item(
            "d", TVAL_DIGGING, 1, name="captured withdrawn shovel",
            known=True, fully_known=True, is_equipment=True,
        )
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            "pack:shovel",
            item_identity=policy_module.equipment_identity(shovel),
        )

        def restarted_inside_home():
            policy = HengbotPolicy()
            policy._equipment_transaction_session = (
                policy_module.EquipmentTransactionSession(
                    policy_module.EquipmentTransactionPlan((action,), (), 1)
                )
            )
            policy._prepare_equipment_optimization = Mock()
            _, outside = town_fixture.NoSafeRecallDestinationTest()._fixture()
            return policy, replace(
                outside,
                turn=2409461,
                inventory=[shovel],
                store=StoreState(store_type=STORE_HOME, items=[]),
            )

        owner_policy, inside = restarted_inside_home()
        self.assertIsNone(owner_policy._equipment_transaction_home_key(inside))
        self.assertEqual(
            owner_policy.last_reason,
            "equipment-transaction:retain-digging-tool",
        )
        self.assertIsNone(owner_policy._equipment_transaction_session)

        public_policy, inside = restarted_inside_home()
        self.assertEqual(public_policy.choose_key(inside), LEAVE_STORE_KEY)
        self.assertEqual(public_policy.last_reason, "policy:none-store-exit")
        self.assertIsNone(public_policy._equipment_transaction_session)

    def test_exhausted_home_route_abandonment_does_not_replan_failed_deposit(self):
        """Replay A13's checkpoint: two bounded owners must not alternate."""
        shovel = item(
            "d", TVAL_DIGGING, 1, name="captured withdrawn shovel",
            known=True, fully_known=True, is_equipment=True,
        )
        policy, outside = town_fixture.NoSafeRecallDestinationTest()._fixture()
        outside = replace(outside, inventory=[shovel])
        policy.choose_key(outside)
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: replay starts from the captured exhausted transaction checkpoint
        policy._equipment_catalog = OwnedEquipmentCatalog()
        policy._equipment_catalog.refresh_carried([shovel], [])
        policy._equipment_catalog.home_scan_complete = True
        owned = policy._equipment_catalog.items[0]
        policy._equipment_transaction_failed_items.discard(owned.id)
        seed_character_calibration(policy, outside)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            owned.id,
            item_identity=policy_module.equipment_identity(shovel),
        )
        plan = policy_module.EquipmentTransactionPlan((action,), (), 1)

        def replanning_optimizer(_snapshot, **_kwargs):
            if (
                policy._equipment_transaction_session is None
                and STORE_HOME not in policy._town_visit_ledger.blocked_stores
            ):
                policy._set_equipment_transaction_session(
                    policy_module.EquipmentTransactionSession(plan)
                )
            return SimpleNamespace(blockers=(), result=object(), transaction=plan)

        policy._prepare_equipment_optimization = Mock(side_effect=replanning_optimizer)
        replanning_optimizer(outside)
        policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = (
            CALIBRATION_HOME_VISIT_LIMIT - 1
        )
        policy._town_errand_plan = policy_module.TownErrandPlan([STORE_HOME])

        reasons = []
        for offset in range(8):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: unchanged archived town state is the A13 owner-alternation stimulus
            policy.choose_key(replace(outside, turn=outside.turn + offset + 1))
            reasons.append(policy.last_reason)

        self.assertEqual(
            reasons[:2],
            [
                "equipment-transaction:home-route-unavailable",
                "equipment-transaction:abandon-blocked",
            ],
        )
        self.assertNotIn(
            "equipment-transaction:home-route-unavailable", reasons[2:]
        )
        self.assertNotIn("equipment-transaction:abandon-blocked", reasons[2:])
        self.assertIsNone(policy._equipment_transaction_session)

    def test_restarted_exhausted_route_quarantines_captured_failed_deposit(self):
        """A restarted A13 checkpoint exits without relying on prior decisions."""
        shovel = item(
            "d", TVAL_DIGGING, 1, name="captured withdrawn shovel",
            known=True, fully_known=True, is_equipment=True,
        )
        policy, outside = town_fixture.NoSafeRecallDestinationTest()._fixture()
        outside = replace(outside, inventory=[shovel])
        policy.choose_key(outside)
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: restart pin reconstructs the captured blocked transaction checkpoint
        policy._equipment_catalog = OwnedEquipmentCatalog()
        policy._equipment_catalog.refresh_carried([shovel], [])
        policy._equipment_catalog.home_scan_complete = True
        owned = policy._equipment_catalog.items[0]
        policy._equipment_transaction_failed_items.discard(owned.id)
        seed_character_calibration(policy, outside)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit", owned.id,
            item_identity=policy_module.equipment_identity(shovel),
        )
        plan = policy_module.EquipmentTransactionPlan((action,), (), 1)
        blocked = policy_module.EquipmentTransactionSession(plan)
        blocked.block("home-route-unavailable")
        policy._equipment_transaction_session = blocked

        def replanning_optimizer(_snapshot, **_kwargs):
            if (
                policy._equipment_transaction_session is None
                and STORE_HOME not in policy._town_visit_ledger.blocked_stores
            ):
                policy._set_equipment_transaction_session(
                    policy_module.EquipmentTransactionSession(plan)
                )
            return SimpleNamespace(blockers=(), result=object(), transaction=plan)

        policy._prepare_equipment_optimization = Mock(side_effect=replanning_optimizer)
        policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = (
            CALIBRATION_HOME_VISIT_LIMIT - 1
        )
        policy._town_errand_plan = policy_module.TownErrandPlan([STORE_HOME])

        policy.choose_key(replace(outside, turn=outside.turn + 1))
        self.assertEqual(
            policy.last_reason, "equipment-transaction:abandon-blocked"
        )
        policy.choose_key(replace(outside, turn=outside.turn + 2))

        self.assertNotIn(
            policy.last_reason,
            {"equipment-transaction:home-route-unavailable",
             "equipment-transaction:abandon-blocked"},
        )
        self.assertIsNone(policy._equipment_transaction_session)

    def test_foreign_visit_is_closed_and_home_route_attempt_is_bounded(self):
        shovel = item(
            "d", TVAL_DIGGING, 1, name="captured withdrawn shovel",
            known=True, fully_known=True, is_equipment=True,
        )
        policy, outside = town_fixture.NoSafeRecallDestinationTest()._fixture()
        outside = replace(outside, inventory=[shovel])
        policy.choose_key(outside)
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: leaked-visit replay starts from the captured Home-deposit transaction
        policy._equipment_catalog = OwnedEquipmentCatalog()
        policy._equipment_catalog.refresh_carried([shovel], [])
        policy._equipment_catalog.home_scan_complete = True
        owned = policy._equipment_catalog.items[0]
        policy._equipment_transaction_failed_items.discard(owned.id)
        seed_character_calibration(policy, outside)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "deposit", owned.id,
            item_identity=policy_module.equipment_identity(shovel),
        )
        plan = policy_module.EquipmentTransactionPlan((action,), (), 1)

        def replanning_optimizer(_snapshot, **_kwargs):
            if (
                policy._equipment_transaction_session is None
                and STORE_HOME not in policy._town_visit_ledger.blocked_stores
            ):
                policy._set_equipment_transaction_session(
                    policy_module.EquipmentTransactionSession(plan)
                )
            return SimpleNamespace(blockers=(), result=object(), transaction=plan)

        policy._prepare_equipment_optimization = Mock(side_effect=replanning_optimizer)
        replanning_optimizer(outside)
        policy._town_errand_plan = policy_module.TownErrandPlan([STORE_HOME])
        foreign = StoreVisit("town-errand", "shopping", STORE_TEMPLE)
        foreign.phase = StoreVisitPhase.APPROACHING
        policy._store_visit = foreign

        reasons = []
        for offset in range(CALIBRATION_HOME_VISIT_LIMIT * 2 + 2):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: the unchanged live town snapshot reproduces the route/abandon alternation
            policy.choose_key(replace(outside, turn=outside.turn + offset + 1))
            reasons.append(policy.last_reason)
            if (
                policy._equipment_transaction_session is None
                and STORE_HOME in policy._town_visit_ledger.blocked_stores
            ):
                break

        self.assertLess(len(reasons), CALIBRATION_HOME_VISIT_LIMIT * 2 + 2)
        self.assertEqual(foreign.phase, StoreVisitPhase.CLOSED)
        self.assertNotEqual(foreign.outcome, "abandoned-with-restore")
        # E5: retirement closes the equipment owner's Home visit; no stale
        # approach ownership remains stamped after the bounded attempt.
        # Revert-proof: removing the retirement clear re-reds this cross-owner pin.
        self.assertIsNone(policy._shopping_approach_store_type)
        self.assertIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)

    def test_blocked_abandon_marks_owned_visit_but_closes_foreign_visit(self):
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE, "deposit", "pack:item"
        )

        def blocked_policy(visit):
            policy = HengbotPolicy()
            session = policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
            session.block("home-route-unavailable")
            policy._equipment_transaction_session = session
            policy._store_visit = visit
            policy._abandon_blocked_equipment_transaction()
            return policy

        foreign = StoreVisit("town-errand", "shopping", STORE_TEMPLE)
        foreign_policy = blocked_policy(foreign)
        self.assertIsNone(foreign_policy._store_visit)
        self.assertEqual(foreign.phase, StoreVisitPhase.CLOSED)
        self.assertNotEqual(foreign.outcome, "abandoned-with-restore")

        owned = StoreVisit("equipment-transaction", "equipment-work", STORE_HOME)
        owned_policy = blocked_policy(owned)
        self.assertIs(owned_policy._store_visit, owned)
        self.assertNotEqual(owned.phase, StoreVisitPhase.CLOSED)
        self.assertEqual(owned.outcome, "abandoned-with-restore")
        self.assertNotIn(
            action.item_id, owned_policy._equipment_transaction_failed_items
        )

    def test_abandon_blocked_marker_activates_no_progress_refusal(self):
        policy, outside = town_fixture.NoSafeRecallDestinationTest()._fixture()
        policy._store_visit = StoreVisit(
            "equipment-transaction", "equipment-work", STORE_HOME
        )
        policy._decision_sequence = 1
        policy.last_reason = "equipment-transaction:home-route-unavailable"
        self.assertEqual(
            policy._refuse_no_progress_cycle(outside, WAIT_KEY), WAIT_KEY
        )

        policy._decision_sequence = 3
        policy._emission_previous_state = object()
        policy.last_reason = "equipment-transaction:abandon-blocked"

        self.assertEqual(
            policy._refuse_no_progress_cycle(outside, WAIT_KEY), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "livelock:exhausted")

    def test_abandoned_deposit_is_preserved_from_every_replanned_transaction(self):
        """The failed A13 action must be absent from the next plan's deposits."""
        shovel = item(
            "d", TVAL_RING, 1, name="captured displaced ring",
            known=True, fully_known=True, is_equipment=True,
        )
        policy, outside = town_fixture.NoSafeRecallDestinationTest()._fixture()
        outside = replace(outside, inventory=[shovel])
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: planner pin starts from the captured failed-deposit quarantine state
        policy._equipment_catalog = OwnedEquipmentCatalog()
        policy._equipment_catalog.refresh_carried([shovel], outside.equipment)
        seed_character_calibration(policy, outside)
        owned = next(
            item for item in policy._equipment_catalog.items
            if item.origin == "pack"
        )
        policy._equipment_transaction_failed_items.add(owned.id)
        captured = []

        def prepare(*args, **kwargs):
            captured.append(kwargs["preserve_pack_item_ids"])
            return SimpleNamespace(ready=False, transaction=None)

        with patch("hengbot.policy_equipment.prepare_warrior_optimization", prepare):
            policy._prepare_equipment_optimization(outside)

        self.assertGreaterEqual(len(captured), 1)
        self.assertTrue(all(owned.id in preserve for preserve in captured))

    def test_public_no_session_latched_restore_dresses_pack_again(self):
        policy, snapshot, inventory = self._stripped_fixture()
        inventory = [replace(item, is_equipment=True) for item in inventory]
        snapshot = replace(snapshot, inventory=inventory)
        policy._equipment_transaction_session = None
        policy._equipment_transaction_restoring = True
        policy._equipment_transaction_restore_terminal = (
            "equipment-transaction:restore-blocked-terminal"
        )

        decisions = []
        current = snapshot
        for expected_identity, expected_slot in list(
            policy._equipment_transaction_owned_items
        ):
            key = policy.choose_key(current)
            decisions.append((key, policy.last_reason))
            session = policy._equipment_transaction_session
            self.assertIsNotNone(session)
            action = session.prepared_action
            self.assertIsNotNone(action)
            self.assertEqual(action.item_identity, expected_identity)
            self.assertEqual(action.target_slot, expected_slot)
            self.assertTrue(policy.confirm_key_posted(key))
            worn = next(
                item for item in current.inventory
                if policy_module.equipment_identity(item) == expected_identity
            )
            current = replace(
                current,
                turn=current.turn + 1,
                inventory=[item for item in current.inventory if item is not worn],
                equipment=[*current.equipment, replace(worn, slot=expected_slot)],
            )

        policy.choose_key(current)
        self.assertEqual(len(current.equipment), 10)
        self.assertEqual(policy._equipment_transaction_owned_items, [])
        self.assertTrue(
            all(
                reason == "equipment-transaction:equip"
                for _, reason in decisions
            )
        )

    def test_blocked_restore_reaches_visible_named_terminal(self):
        """Only a genuinely missing remainder reaches the CLI-stop terminal."""
        policy, snapshot, inventory = self._stripped_fixture()
        wearable = replace(inventory[0], is_equipment=True)
        missing_identity, missing_slot = policy._equipment_transaction_owned_items[1]
        policy._equipment_transaction_owned_items = [
            policy._equipment_transaction_owned_items[0],
            (missing_identity, missing_slot),
        ]
        policy._equipment_transaction_session = None
        policy._equipment_transaction_restoring = True
        snapshot = replace(snapshot, inventory=[wearable])

        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "equipment-transaction:equip")
        self.assertTrue(policy.confirm_key_posted(key))
        dressed = replace(wearable, slot=policy._equipment_transaction_owned_items[0][1])
        after = replace(
            snapshot, turn=snapshot.turn + 1, inventory=[], equipment=[dressed]
        )

        self.assertEqual(policy.choose_key(after), WAIT_KEY)
        self.assertEqual(
            policy.last_reason,
            "equipment-transaction:restore-blocked-terminal",
        )
        self.assertEqual(
            policy._equipment_transaction_restore_remainder,
            (missing_identity,),
        )
        self.assertEqual(len(after.equipment), 1)

    def test_live_inside_home_with_ten_removed_items_preserves_transaction_progress(self):
        """The retained incident shape is a Home handoff, not failure evidence."""
        policy, outside, inventory = self._stripped_fixture()
        target = item(
            "z", TVAL_RING, 99, name="Home target", known=True,
            fully_known=True, is_equipment=True,
        )
        home_target = store_item(
            "a", TVAL_RING, 99, name="Home target", known=True,
            fully_known=True, is_equipment=True,
        )
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "withdraw",
            "home-target",
            item_identity=policy_module.equipment_identity(target),
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), len(inventory))
            )
        )
        policy._equipment_transaction_restoring = False
        policy._home_knowledge_items = (target,)
        policy._home_knowledge_valid_before = 1
        policy._home_knowledge_current = True
        policy._home_page_size = 12
        inside = replace(
            outside,
            store=StoreState(store_type=STORE_HOME, items=[home_target]),
        )

        key = policy.choose_key(inside)

        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(
            policy.last_reason, "equipment-transaction:leave-for-atomic-withdraw"
        )
        self.assertIs(policy._equipment_transaction_session.current_action, action)
        self.assertFalse(policy._equipment_transaction_restoring)
        self.assertEqual(len(policy._equipment_transaction_owned_items), 10)

    def test_equipment_withdrawal_does_not_starve_queued_torch_withdrawal(self):
        """Equipment ownership yields to an already queued torch take."""
        first = item(
            "a", TVAL_RING, 201, name="First queued ring", known=True,
            fully_known=True, is_equipment=True,
        )
        second = item(
            "b", TVAL_RING, 202, name="Second queued ring", known=True,
            fully_known=True, is_equipment=True,
        )
        torches = store_item(
            "c", TVAL_LITE, SV_LITE_TORCH, name="Queued throwing torches",
            count=10,
        )
        actions = tuple(
            policy_module.EquipmentTransaction(
                policy_module.PHASE_HOME_PREPARE,
                "withdraw",
                f"home:{index}",
                item_identity=policy_module.equipment_identity(target),
            )
            for index, target in enumerate((second, first))
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((first, second, torches))
        policy._home_page_size = 12
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan(actions, (), 0)
            )
        )
        policy._home_pending_item = policy._item_signature(torches)
        policy._home_pending_quantity = 4
        policy._prepare_equipment_optimization = Mock()
        entrance = Snapshot(
            player(45, 123, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(45, 123): replace(
                    grid(45, 123), store_number=STORE_HOME
                ),
                Position(45, 122): grid(45, 122),
            },
            [],
            turn=2247900,
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[],
            store=None,
        )

        decisions = []
        first_key = policy.choose_key(entrance)
        decisions.append((first_key, policy.last_reason))
        self.assertTrue(policy.confirm_key_posted(first_key))

        first_tail = policy.choose_key(replace(
            entrance,
            store=StoreState(
                STORE_HOME, [first, second, torches], stock_num=3,
                page_top=0, page_size=12,
            ),
        ))
        decisions.append((first_tail, policy.last_reason))

        # The first outside page can precede the inventory mutation.  Holding
        # with Escape keeps the player on Home instead of spending an approach
        # that enters the store and then has to be undone.
        hold_key = policy.choose_key(replace(entrance, turn=entrance.turn + 1))
        decisions.append((hold_key, policy.last_reason))

        carrying_second = replace(
            entrance,
            turn=entrance.turn + 2,
            inventory=[replace(second, slot="a")],
        )
        policy.consume_home_knowledge((first, torches))
        policy._home_page_size = 12
        policy._home_pending_item = policy._item_signature(torches)
        policy._home_pending_quantity = 4
        self.assertTrue(policy._equipment_transaction_session.observe(
            policy_module.observe_equipment_transactions(carrying_second)
        ))
        equipment_request = policy._derived_home_visit_request(carrying_second)
        self.assertEqual(equipment_request.requester, "equipment-transaction")
        second_key = policy.choose_key(carrying_second)
        decisions.append((second_key, policy.last_reason))
        self.assertTrue(policy.confirm_key_posted(second_key))
        second_tail = policy.choose_key(replace(
            carrying_second,
            store=StoreState(
                STORE_HOME, [first, torches], stock_num=2,
                page_top=0, page_size=12,
            ),
        ))
        decisions.append((second_tail, policy.last_reason))

        carrying_equipment = replace(
            entrance,
            turn=entrance.turn + 3,
            inventory=[replace(second, slot="a"), replace(first, slot="b")],
        )
        policy.consume_home_knowledge((torches,))
        policy._home_page_size = 12
        policy._home_pending_item = policy._item_signature(torches)
        policy._home_pending_quantity = 4
        session = policy._equipment_transaction_session
        self.assertTrue(session.observe(
            policy_module.observe_equipment_transactions(carrying_equipment)
        ))
        self.assertTrue(session.complete)
        torch_request = policy._derived_home_visit_request(carrying_equipment)

        self.assertEqual(
            decisions,
            [
                (WAIT_KEY, "equipment-transaction:atomic-withdraw"),
                ("pb\x1b", "home:atomic-withdraw"),
                (
                    LEAVE_STORE_KEY,
                    "equipment-transaction:await-confirmation-on-home",
                ),
                (WAIT_KEY, "equipment-transaction:atomic-withdraw"),
                ("pa\x1b", "home:atomic-withdraw"),
            ],
        )
        self.assertEqual(len(decisions), 5)
        self.assertEqual(torch_request.requester, "legacy-withdrawal")
        self.assertEqual(torch_request.address, policy._item_signature(torches))
        self.assertEqual(torch_request.quantity, 4)
        self.assertNotIn(
            "equipment-transaction:approach-home", dict(decisions).values()
        )

    def test_route_blocked_abandonment_consumes_home_route_pass(self):
        policy, outside, _ = self._stripped_fixture()
        inside = replace(
            outside,
            store=StoreState(store_type=STORE_HOME, items=[]),
        )
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME], need_categories={STORE_HOME: ("equipment-transaction",)}
        )
        before = policy._town_visit_ledger.unsatisfied_passes[STORE_HOME]

        policy.choose_key(inside)

        self.assertEqual(policy.last_reason, "equipment-transaction:abandon-blocked-home")
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], before + 1
        )

    def test_outstanding_equipment_work_always_projects_a_home_need(self):
        policy, snapshot, _ = self._stripped_fixture()
        action = policy._equipment_transaction_session.current_action
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 10)
            )
        )
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=None, encounters_total=0,
            encounters_evaluated=0, transaction=None,
        )

        projection = policy.equipment_optimization_state(snapshot)[
            "home_route_projection"
        ]

        self.assertTrue(projection["outstanding_equipment_work"])
        self.assertTrue(projection["equipment_work_need_present"])

    def test_satisfied_zero_action_optimization_does_not_own_home(self):
        policy, snapshot = town_fixture.NoSafeRecallDestinationTest()._fixture()
        policy._home_pending_item = None
        policy._home_pending_batch = []
        policy._home_atomic_withdraw_pending = None
        policy._home_atomic_deposit_pending = None
        policy._calibration_restore_signatures = []
        current = Loadout((), "empty")
        policy._equipment_optimization_preparation = SimpleNamespace(
            current=current,
            blockers=("incomplete-equipment-catalog",),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: regression isolates routing after the measured optimizer result and does not replace the decision path
            result=SimpleNamespace(
                best=SimpleNamespace(loadout=current),
                chosen_depth=30,
                timed_out=False,
                combinations_considered=34,
                combinations_evaluated=34,
                invalid_combinations=0,
                elapsed_seconds=0.01,
                search_truncated=False,
            ),
            transaction=policy_module.EquipmentTransactionPlan((), (), 0),
            encounters_total=1,
            encounters_evaluated=1,
        )
        policy._prepare_equipment_optimization = Mock(
            return_value=policy._equipment_optimization_preparation
        )
        self.assertTrue(
            policy._optimization_already_applied(
                policy._equipment_optimization_preparation
            )
        )
        self.assertIsNotNone(snapshot.grid_at(Position(45, 123)))

        posted_keys = []
        for decision in range(6):
            current_snapshot = replace(snapshot, turn=snapshot.turn + decision)
            key = policy.choose_key(current_snapshot)
            posted_keys.append(
                (key, policy.last_reason, policy._shopping_approach_store_type)
            )

        self.assertFalse(policy._outstanding_equipment_work())
        self.assertLessEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 3
        )
        projection = policy.equipment_optimization_state(snapshot)[
            "home_route_projection"
        ]
        self.assertFalse(projection["equipment_work_need_present"])
        self.assertFalse(projection["outstanding_equipment_work"])
        self.assertTrue(
            all(store_type != STORE_HOME for _, _, store_type in posted_keys[1:])
        )

    def test_zero_action_shape_with_different_target_remains_blocked_work(self):
        policy = HengbotPolicy()
        current = Loadout((), "empty")
        target_item = OwnedEquipment(
            "home:upgrade",
            item("a", TVAL_RING, 77, known=True, fully_known=True),
            "home",
        )
        target = Loadout(((policy_module.SLOT_MAIN_RING, target_item),), "empty")
        policy._equipment_optimization_preparation = SimpleNamespace(
            current=current,
            blockers=("missing-item:home:upgrade",),
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: branch pin isolates routing after an uncomposable optimizer result and does not replace the decision path
            result=SimpleNamespace(best=SimpleNamespace(loadout=target)),
            transaction=None,
        )

        self.assertFalse(
            policy._optimization_already_applied(
                policy._equipment_optimization_preparation
            )
        )
        self.assertTrue(policy._outstanding_equipment_work())

    def test_completing_optimization_performs_zero_restores(self):
        policy, snapshot, _ = self._stripped_fixture()
        ring = item(
            "a", TVAL_RING, 101, name="Selected ring", known=True,
            fully_known=True, is_equipment=True,
        )
        identity = policy_module.equipment_identity(ring)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_EQUIP,
            "equip",
            "selected-ring",
            "main_ring",
            identity,
        )
        policy._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )
        policy._equipment_transaction_owned_items = [(identity, "main_ring")]
        carrying = replace(snapshot, inventory=[ring], equipment=[])

        with patch.object(
            policy,
            "_abandon_blocked_equipment_transaction",
            wraps=policy._abandon_blocked_equipment_transaction,
        ) as restore_trigger:
            key = policy.choose_key(carrying)
            self.assertTrue(policy.confirm_key_posted(key))
            dressed = replace(
                carrying,
                turn=carrying.turn + 1,
                inventory=[],
                equipment=[replace(ring, slot="main_ring")],
            )
            policy.choose_key(dressed)

        self.assertIsNone(policy._equipment_transaction_session)
        self.assertEqual(policy._equipment_transaction_owned_items, [])
        self.assertEqual(restore_trigger.call_count, 0)


class EquipLoopAfterE85AA8ERegressionTest(unittest.TestCase):
    FIXTURE = (
        Path(__file__).parent
        / "fixtures"
        / "equip-loop-after-e85aa8e-20260911.json.gz"
    )

    def _captured(self):
        with gzip.open(self.FIXTURE, "rt", encoding="utf-8-sig") as stream:
            return parse_snapshot(json.load(stream), {})

    def test_identification_incomplete_hammer_is_not_a_search_target(self):
        snapshot = self._captured()
        policy = HengbotPolicy()
        seed_character_calibration(policy, snapshot)
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        policy._equipment_catalog.observe_home_page([])

        preparation = policy._prepare_equipment_optimization(
            snapshot, depth_override=49
        )
        hammer = next(
            owned
            for owned in policy._equipment_catalog.items
            if policy_module.equipment_identity(owned.item) == "da9db64b3a96f3aa"
        )
        self.assertTrue(hammer.identification_incomplete)
        self.assertNotIn(
            hammer.id, policy._equipment_optimization_search_surviving_ids
        )
        self.assertNotEqual(
            getattr(
                getattr(preparation, "transaction", None), "actions", ()
            ),
            (policy_module.EquipmentTransaction(
                policy_module.PHASE_EQUIP,
                "equip",
                "restore:da9db64b3a96f3aa",
                "sub_hand",
                "da9db64b3a96f3aa",
            ),),
        )
        state = policy.equipment_optimization_state(snapshot)
        excluded = state["search_excluded_items"]["items"]
        self.assertIn(
            "identification-incomplete",
            next(row for row in excluded if row["id"] == hammer.id)["reasons"],
        )
