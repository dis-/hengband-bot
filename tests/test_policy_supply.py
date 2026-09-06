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

try:
    from trajectory_harness import drive_trajectory
except ModuleNotFoundError:
    from tests.trajectory_harness import drive_trajectory

import hengbot.policy as policy_module
import hengbot.equipment_mutation as equipment_mutation_module


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
from hengbot.policy_constants import FOOD_TYPE_MANA
import test_policy as _test_policy

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

REAL_QUEST_DEFINITIONS = find_quest_definitions(
    Path(__file__)
)

class ShoppingTest(unittest.TestCase):
    def _in_store(self, items, *, gold=1000, inv=None, eq=None):
        grids = {Position(10, 10): grid(10, 10)}
        return Snapshot(
            player(10, 10, gold=gold),
            grids,
            [],
            inventory=inv or [],
            equipment=eq or [],
            store=StoreState(store_type=STORE_GENERAL, items=items),
        )

    def test_buys_lantern_first(self):
        items = [
            store_item("a", TVAL_LITE, SV_LITE_TORCH, price=1),
            store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=120),
            store_item("c", TVAL_FLASK, SV_FLASK_OIL, price=3),
        ]
        pol = HengbotPolicy()
        self.assertEqual(_public_shop_inner(self, pol, self._in_store(items)), "pb\r")
        self.assertEqual(pol.last_reason, "shop:one-shot-buy")

    def test_mapless_store_purchase_matches_map_bearing_store(self):
        ware = store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=120)
        bearing = self._in_store([ware])
        mapless = replace(bearing, grids={})

        bearing_policy = HengbotPolicy()
        mapless_policy = HengbotPolicy()
        self.assertEqual(
            mapless_policy.choose_key(mapless),
            bearing_policy.choose_key(bearing),
        )
        self.assertEqual(mapless_policy.last_reason, bearing_policy.last_reason)

    def test_mapless_store_leave_matches_map_bearing_store(self):
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN,
            fuel=5000, is_equipment=True,
        )
        bearing = self._in_store([], eq=[lantern])
        mapless = replace(bearing, grids={})

        bearing_policy = HengbotPolicy()
        mapless_policy = HengbotPolicy()
        self.assertEqual(
            mapless_policy.choose_key(mapless),
            bearing_policy.choose_key(bearing),
        )
        self.assertEqual(mapless_policy.last_reason, bearing_policy.last_reason)

    def test_mapless_store_snapshot_cannot_reset_or_erode_surface_memory(self):
        entrance = Position(10, 10)
        neighbor = Position(10, 11)
        surface = replace(
            self._in_store([]),
            store=None,
            grids={
                entrance: replace(grid(10, 10), store_number=STORE_GENERAL),
                neighbor: grid(10, 11, terrain_id=7),
            },
            width=132,
            height=44,
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._with_grid_memory(surface)
        before = dict(policy._remembered_grids)
        # Store UI metadata is deliberately unlike the surface metadata.  With
        # no grids this is absence of observation, not a new terrain region.
        mapless = replace(
            surface,
            store=StoreState(STORE_GENERAL, []),
            grids={},
            width=0,
            height=0,
        )

        merged = policy._with_grid_memory(mapless)

        self.assertEqual(policy._remembered_grids, before)
        self.assertEqual(merged.grids, before)
        self.assertEqual(merged.grid_at(entrance).store_number, STORE_GENERAL)

    def test_stale_store_snapshot_after_leave_cannot_emit_purchase(self):
        lantern = InventoryItem(
            "e", "lantern", 1, TVAL_LITE, SV_LITE_LANTERN, True, True
        )
        pol = HengbotPolicy()
        leaving = replace(self._in_store([], inv=[lantern]), turn=100)

        self.assertEqual(pol.choose_key(leaving), LEAVE_STORE_KEY)

        stale = replace(
            self._in_store(
                [store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=120)]
            ),
            turn=99,
        )
        self.assertEqual(pol.choose_key(stale), "\r")
        self.assertEqual(pol.last_reason, "shop:await-leave-generation")
        self.assertIsNone(pol._store_buy_inflight)

    def test_captured_home_leave_stale_snapshot_cannot_drop_deposit(self):
        pol = HengbotPolicy()
        home = replace(
            self._in_store([]),
            store=StoreState(
                store_type=STORE_HOME, items=[], stock_num=0,
                page_top=0, page_size=52,
            ),
            turn=895189,
        )
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(
            pol, "_decide", side_effect=["dn\r", LEAVE_STORE_KEY, "dm\r", "dm\r"]
        ):
            self.assertEqual(pol.choose_key(home), LEAVE_STORE_KEY)
            self.assertEqual(pol.last_reason, "home:scan-complete-from-open-page")
            self.assertEqual(pol.choose_key(home), "\r")
            self.assertEqual(pol.choose_key(home), "\r")
            self.assertEqual(pol.last_reason, "shop:await-leave-confirmation")

            fresh_home = replace(home, turn=895190)
            self.assertEqual(pol.choose_key(fresh_home), LEAVE_STORE_KEY)

        self.assertIsNotNone(pol._store_leave_inflight)

    def test_stale_store_after_leave_blocks_every_item_command_family(self):
        home = replace(
            self._in_store([]),
            store=StoreState(store_type=STORE_HOME, items=[]),
            turn=100,
        )
        for macro in ("da\r", "pa\r", "sa\r"):
            with self.subTest(macro=macro):
                pol = HengbotPolicy()
                # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
                with patch.object(
                    pol, "_decide", side_effect=[LEAVE_STORE_KEY, macro]
                ):
                    self.assertEqual(pol.choose_key(home), LEAVE_STORE_KEY)
                    self.assertEqual(pol.choose_key(home), "\r")
                self.assertEqual(
                    pol.last_reason, "shop:await-leave-confirmation"
                )




    def test_buys_oil_once_lantern_owned(self):
        items = [store_item("c", TVAL_FLASK, SV_FLASK_OIL, price=3, count=42)]
        inv = [InventoryItem("e", "lantern", 1, TVAL_LITE, SV_LITE_LANTERN, True, True)]
        pol = HengbotPolicy()
        self.assertEqual(_public_shop_inner(self, pol, self._in_store(items, inv=inv)), "pc5\r\r")
        self.assertEqual(pol.last_reason, "shop:one-shot-buy")

    def test_fundraising_buys_oil_before_leaving_general_store(self):
        oil = store_item("f", TVAL_FLASK, SV_FLASK_OIL, price=1, count=15)
        inventory = [
            item("a", TVAL_FOOD, 35, count=5),
            item("d", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=5),
            item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL),
        ]
        equipment = [
            item("main_hand", 23, 1, is_equipment=True),
            item(
                "light", TVAL_LITE, SV_LITE_LANTERN,
                fuel=5000, is_equipment=True,
            ),
        ]
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertEqual(
            _public_shop_inner(self, policy,
                self._in_store([oil], gold=1654, inv=inventory, eq=equipment)
            ),
            "pf5\r\r",
        )
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")

    def test_unaffordable_mana_food_falls_through_to_incident_oil(self):
        inventory = [
            item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=4),
            item("m", TVAL_STAFF, 1, charges=14),
        ]
        equipment = [
            item(
                "light", TVAL_LITE, SV_LITE_LANTERN,
                fuel=5000, is_equipment=True,
            ),
        ]
        oil = store_item("o", TVAL_FLASK, SV_FLASK_OIL, price=3, count=20)

        for wares in (
            [oil],
            [
                oil,
                store_item(
                    "p", TVAL_DIGGING, SV_DIGGING_PICK,
                    price=50, name="Pick",
                ),
            ],
        ):
            with self.subTest(wares=[ware.name for ware in wares]):
                policy = HengbotPolicy()
                policy._fundraising_mode = "prepare"
                snapshot = replace(
                    self._in_store(wares, gold=367, inv=inventory, eq=equipment),
                    player=player(
                        10, 10, gold=367, class_id=PLAYER_CLASS_WARRIOR,
                        food_type=FOOD_TYPE_MANA,
                    ),
                )

                self.assertEqual(policy._supply_ledger(snapshot, 1)["food"].count, 14)
                self.assertEqual(policy._supply_ledger(snapshot, 1)["food"].required_departure, 15)
                self.assertEqual(policy._supply_ledger(snapshot, 1)["oil"].count, 0)
                self.assertEqual(policy._supply_ledger(snapshot, 1)["oil"].required_departure, 5)
                self.assertEqual(_public_shop_inner(self, policy, snapshot), "po5\r\r")
                self.assertEqual(policy.last_reason, "shop:one-shot-buy")

    def test_unaffordable_mana_food_falls_through_inside_magic_shop(self):
        inventory = [
            item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=4),
            item("m", TVAL_STAFF, 1, charges=14),
        ]
        equipment = [
            item(
                "light", TVAL_LITE, SV_LITE_LANTERN,
                fuel=5000, is_equipment=True,
            ),
        ]
        mana_food = store_item(
            "g", TVAL_STAFF, 4, price=1576, name="Mana food", pval=23,
        )
        detection = store_item(
            "t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            price=162, count=18,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        base = replace(
            self._in_store(
                [mana_food], gold=367, inv=inventory, eq=equipment,
            ),
            player=player(
                10, 10, gold=367, class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA,
            ),
        )
        magic = replace(
            base, store=StoreState(STORE_MAGIC, [mana_food]),
        )

        self.assertEqual(_public_shop_inner(self, policy, magic), "8")

        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        with_detection = replace(
            base, store=StoreState(STORE_MAGIC, [mana_food, detection]),
        )
        self.assertEqual(_public_shop_inner(self, policy, with_detection), "pt2\r\r")
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")

    def test_permanent_light_buys_neither_lantern_nor_oil(self):
        wares = [
            store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=120),
            store_item("c", TVAL_FLASK, SV_FLASK_OIL, price=3, count=42),
        ]
        feanorian = item(
            "light", TVAL_LITE, SV_LITE_FEANOR,
            name="Feanorian Lamp", is_equipment=True,
            known=True, fully_known=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(
            _public_shop_inner(self, policy, self._in_store(wares, eq=[feanorian])),
            "8",
        )

    def test_does_not_sell_only_lantern_while_empty_torch_is_equipped(self):
        lantern = item(
            "d", TVAL_LITE, SV_LITE_LANTERN, name="brass lantern", fuel=7500
        )
        empty_torch = item(
            "light",
            TVAL_LITE,
            SV_LITE_TORCH,
            name="empty torch",
            fuel=0,
            is_equipment=True,
        )
        snap = self._in_store([], inv=[lantern], eq=[empty_torch])

        self.assertIsNone(HengbotPolicy()._find_light_sale(snap))

    def test_sells_lantern_only_when_working_lantern_is_already_equipped(self):
        spare = item(
            "d", TVAL_LITE, SV_LITE_LANTERN, name="spare lantern", fuel=7500
        )
        equipped = item(
            "light",
            TVAL_LITE,
            SV_LITE_LANTERN,
            name="equipped lantern",
            fuel=5000,
            is_equipment=True,
        )
        snap = self._in_store([], inv=[spare], eq=[equipped])

        self.assertEqual(HengbotPolicy()._find_light_sale(snap), spare)

    def test_leaves_when_done(self):
        items = [store_item("c", TVAL_FLASK, SV_FLASK_OIL, price=3)]
        # Own a lantern and plenty of oil already → nothing to buy → leave.
        inv = [
            InventoryItem("e", "lantern", 1, TVAL_LITE, SV_LITE_LANTERN, True, True),
            InventoryItem("f", "oil", 9, TVAL_FLASK, SV_FLASK_OIL, True, True),
        ]
        pol = HengbotPolicy()
        self.assertEqual(_public_shop_inner(self, pol, self._in_store(items, inv=inv)), "8")











    def test_gives_up_when_lantern_unaffordable(self):
        items = [store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=500)]
        pol = HengbotPolicy()
        self.assertEqual(_public_shop_inner(self, pol, self._in_store(items, gold=50)), "8")
        self.assertTrue(pol._shopping_abandoned)

    def test_approaches_general_store_in_town(self):
        # Town (dungeon 0, level 0), gold, no lantern, a store tile to the east.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),
        }
        grids[Position(10, 12)] = GridState(
            position=Position(10, 12), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        snap = Snapshot(player(10, 10, gold=1000), grids, [], floor_key=(0, 0, 0))
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "shop:approach")

    def test_uses_native_travel_for_a_distant_town_store(self):
        walkable = frozenset(Position(10, x) for x in range(1, 16))
        town_map = TownMap(
            name="T",
            width=20,
            height=20,
            walkable=walkable,
            stores={STORE_GENERAL: Position(10, 15)},
        )
        grids = {Position(10, x): grid(10, x) for x in range(1, 16)}
        grids[Position(10, 15)] = GridState(
            position=Position(10, 15), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        snap = Snapshot(
            player(10, 1, gold=1000), grids, [], floor_key=(0, 0, 0),
            width=20, height=20, town_flag=True,
            inventory=[item("a", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

        pol = HengbotPolicy(town_map=town_map)
        self.assertEqual(pol.choose_key(snap), "wa")
        self.assertEqual(pol.last_reason, "wield-light")
        snap = replace(
            snap,
            inventory=[],
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        self.assertEqual(pol.choose_key(snap), "\x1b`n!.")
        self.assertEqual(pol.last_reason, "shop:travel")
        preceding_arbiter = dict(pol._town_turn_arbiter.telemetry)

        # Live 2026-08-10 shape: the unchanged board made the policy select the
        # identical native-travel macro, which the sender correctly refused.
        pol.refuse_key_posting("shop:travel", "\x1b`n!.")
        probe = pol.choose_key(snap)
        self.assertEqual(
            (probe, pol.last_reason), ("l\x1b", "shop:travel")
        )
        self.assertEqual(pol._town_turn_arbiter.telemetry, preceding_arbiter)
        self.assertEqual(pol._town_turn_arbiter.telemetry["owner"], "store-router")
        replacement = pol.choose_key(snap)
        self.assertEqual(replacement, "6")
        self.assertEqual(pol.last_reason, "shop:approach")
        self.assertNotEqual(replacement, "\x1b`n!.")

    def test_distant_store_without_any_light_walks(self):
        walkable = frozenset(Position(10, x) for x in range(1, 16))
        goal = Position(10, 15)
        town_map = TownMap(
            name="T", width=20, height=20, walkable=walkable,
            stores={STORE_GENERAL: goal},
        )
        grids = {Position(10, x): grid(10, x) for x in range(1, 16)}
        grids[goal] = replace(grid(10, 15), store_number=STORE_GENERAL)
        snap = Snapshot(
            player(10, 1, gold=1000), grids, [], floor_key=(0, 0, 0),
            width=20, height=20, town_flag=True,
        )

        pol = HengbotPolicy(town_map=town_map)
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "shop:approach")
        self.assertIsNone(pol._town_travel_state)

    def test_interrupted_town_travel_yields_after_one_unchanged_retry(self):
        walkable = frozenset(Position(10, x) for x in range(1, 16))
        goal = Position(10, 15)
        town_map = TownMap(
            name="T", width=20, height=20, walkable=walkable,
            stores={STORE_GENERAL: goal},
        )
        grids = {Position(10, x): grid(10, x) for x in range(1, 16)}
        grids[goal] = GridState(
            position=goal, known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        first = Snapshot(
            player(10, 1, gold=1000), grids, [], floor_key=(0, 0, 0),
            width=20, height=20, town_flag=True, turn=1,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        interrupted = Snapshot(
            player(10, 5, gold=1000), grids, [], floor_key=(0, 0, 0),
            width=20, height=20, town_flag=True, turn=2,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

        pol = HengbotPolicy(town_map=town_map)
        self.assertEqual(pol.choose_key(first), "\x1b`n!.")
        # Interrupted mid-route but CLOSER than before: travel again instead of
        # walking the remaining ten tiles one decision each.
        self.assertEqual(pol.choose_key(interrupted), "\x1b`n!.")
        self.assertEqual(pol.last_reason, "shop:travel")
        # A second selection against that same board must yield immediately.
        self.assertEqual(pol.choose_key(interrupted), "6")
        self.assertEqual(pol.last_reason, "shop:approach")
        self.assertEqual(pol.choose_key(interrupted), "6")

    def test_eats_before_distant_town_travel(self):
        walkable = frozenset(Position(10, x) for x in range(1, 16))
        town_map = TownMap(
            name="T", width=20, height=20, walkable=walkable,
            stores={STORE_GENERAL: Position(10, 15)},
        )
        grids = {Position(10, x): grid(10, x) for x in range(1, 16)}
        ration = InventoryItem(
            "a", "ration", 1, TVAL_FOOD, FOOD_MIN_SVAL, True, True
        )
        snap = Snapshot(
            player(10, 1, food=1500, gold=1000), grids, [],
            floor_key=(0, 0, 0), inventory=[ration],
            width=20, height=20, town_flag=True,
        )

        pol = HengbotPolicy(town_map=town_map)
        self.assertEqual(pol.choose_key(snap), "Ea")
        self.assertEqual(pol.last_reason, "town:eat-before-travel")

    def test_breaks_out_when_store_approach_move_is_rejected(self):
        grids = {
            Position(9, 10): grid(9, 10),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        snap = Snapshot(player(10, 10, gold=1000), grids, [], floor_key=(0, 0, 0))
        pol = HengbotPolicy()

        keys = [pol.choose_key(snap) for _ in range(LIVELOCK_LIMIT + 1)]

        self.assertEqual(keys[-1], "8")
        self.assertEqual(pol.last_reason, "breakout")

    def test_store_approach_paths_to_the_store_even_when_oscillating(self):
        # Regression: the old oscillation-breakout returned _least_visited_neighbor
        # (a step toward unexplored tiles), which in a fully-known town marched the
        # bot to the map edge and across into the open wilderness (a fatal Cyclops
        # run). Store-approach must now always path straight to the store instead.
        grids = {
            Position(9, 10): grid(9, 10),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        pol = HengbotPolicy()
        distances = []
        arrived = False
        for index in range(LIVELOCK_LIMIT * 3):
            x = 10 if index % 2 == 0 else 11
            snap = Snapshot(player(10, x, gold=1000), grids, [], floor_key=(0, 0, 0))
            key = pol.choose_key(snap)
            arrived = False
            goal = Position(10, 12)
            direction = next(
                (delta for delta, direction_key in policy_module.DIRECTION_KEYS.items()
                 if direction_key == key),
                None,
            )
            if direction is not None:
                after = Position(10 + direction[0], x + direction[1])
                distances.append(after.distance_to(goal))
                arrived = after == goal

        # ARB-A supersedes the old livelock:exhausted assertion: it
        # contradicted this test's pathing contract and spec section 3's
        # distance metric.  Removing R1's locomotion metric makes this fail.
        self.assertTrue(
            arrived or (
                distances
                and distances[-1]
                < Position(10, x).distance_to(Position(10, 12))
            ),
            (key, pol.last_reason, distances),
        )
        self.assertTrue(
            any(
                isinstance(entry, tuple) and entry[:2] == ("locomotion", "store-router")
                for entry in pol._town_arbiter_progress_vector(snap, "shop:approach")
            )
        )

    def test_store_approach_failure_does_not_block_later_shopping(self):
        # If the approach keeps oscillating WITHOUT arriving for long enough (a truly
        # unreachable entrance), abandon shopping this visit before the loop guard
        # stops the bot — set _shopping_stuck rather than bounce forever.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        pol = HengbotPolicy()
        for index in range(SHOP_APPROACH_STUCK_LIMIT + STUCK_WINDOW + 2):
            x = 10 if index % 2 == 0 else 11
            snap = Snapshot(player(10, x, gold=1000), grids, [], floor_key=(0, 0, 0))
            pol.choose_key(snap)
        self.assertFalse(pol._shopping_stuck)
        self.assertIn(STORE_GENERAL, pol._town_store_attempted)

    def test_no_approach_without_gold(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        grids[Position(10, 11)] = GridState(
            position=Position(10, 11), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        snap = Snapshot(player(10, 10, gold=0), grids, [], floor_key=(0, 0, 0))
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "shop:approach")

    def test_upgrades_torch_to_lantern(self):
        grids = {Position(10, 10): grid(10, 10)}
        torch_eq = InventoryItem("f", "torch", 1, TVAL_LITE, SV_LITE_TORCH, True, True, fuel=1000)
        lantern_inv = InventoryItem("e", "lantern", 1, TVAL_LITE, SV_LITE_LANTERN, True, True, fuel=7500)
        snap = Snapshot(player(10, 10), grids, [], inventory=[lantern_inv], equipment=[torch_eq])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "we")
        self.assertEqual(pol.last_reason, "wield-light")

    def test_upgrades_lantern_to_feanorian_lamp(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item(
                    "f", TVAL_LITE, SV_LITE_FEANOR,
                    name="Feanorian Lamp", fuel=0,
                )
            ],
            equipment=[
                item(
                    "light", TVAL_LITE, SV_LITE_LANTERN,
                    name="Brass Lantern", fuel=7500,
                )
            ],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "wf")
        self.assertEqual(policy.last_reason, "wield-light")

    def test_selects_feanorian_lamp_ahead_of_pack_lantern(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=7500),
                item("f", TVAL_LITE, SV_LITE_FEANOR, fuel=0),
            ],
        )

        self.assertEqual(HengbotPolicy()._light_to_wield(snap).slot, "f")

    def test_home_owned_permanent_light_makes_all_pack_oil_depositable(self):
        oil = item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=7500)
        feanorian = store_item(
            "f", TVAL_LITE, SV_LITE_FEANOR,
            name="Feanorian Lamp", is_equipment=True,
            known=True, fully_known=True,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[oil],
            equipment=[
                item(
                    "light", TVAL_LITE, SV_LITE_LANTERN,
                    name="Brass Lantern", fuel=7500,
                )
            ],
            store=StoreState(store_type=STORE_HOME, items=[feanorian]),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page(snap.store.items)

        self.assertEqual(policy._supply_ledger(snap, 18)["oil"].required_departure, 0)
        self.assertEqual(policy._retention_reservation(snap, oil), 0)
        self.assertTrue(policy._home_deposit_candidate(oil, snap))
        self.assertEqual(policy._home_deposit_key(snap, oil), "do5\r")

class WieldLightTest(unittest.TestCase):
    @staticmethod
    def _hidden_lantern() -> InventoryItem:
        return item(
            "light",
            TVAL_LITE,
            SV_LITE_LANTERN,
            name="unidentified lantern",
            known=False,
            fuel=0,
            is_equipment=True,
        )

    def test_pin_vacuity_darkness_return_never_reads_captured_recall_stack(self):
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, name="empty lantern",
            known=True, fuel=0, is_equipment=True,
        )
        recall = item(
            "d", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            name="Word of Recall", count=9, aware=True, known=True,
        )
        upstairs = replace(grid(10, 11), has_up_stairs=True, known=True)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10, lit=False), Position(10, 11): upstairs},
            [], floor_key=(DUNGEON_YEEK_CAVE, 10, 0),
            inventory=[recall], equipment=[lantern], equipment_observed=True,
            grids_observed=True,
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True

        key = policy.choose_key(snap)

        self.assertFalse(key.startswith(READ_KEY), (key, policy.last_reason))
        self.assertEqual(policy.last_reason, "dark:backtrack")

    def test_old_snapshot_omits_authoritative_own_grid_visibility(self):
        raw = json.loads(
            Path("tests/fixtures/abilities-depth34-landed-dungeon.json").read_text(
                encoding="utf-8"
            )
        )
        snap = parse_snapshot(raw, {})
        policy = HengbotPolicy()
        here = snap.grids.get(snap.player.position)
        inferred_dark = (
            snap.dungeon_level >= 1
            and not snap.player.blind
            and (
                here is not None and snap.grids_observed and not here.lit
                or here is None and snap.grids_observed
            )
        )

        self.assertIsNone(snap.can_see_own_grid)
        self.assertEqual(policy._is_dark(snap), inferred_dark)

    def test_authoritative_darkness_handles_an_absent_own_cell(self):
        snap = Snapshot(
            player(10, 10), {}, [], floor_key=(DUNGEON_YEEK_CAVE, 10, 0),
            equipment_observed=True, grids_observed=True,
            can_see_own_grid=False,
        )
        policy = HengbotPolicy()

        self.assertTrue(policy._is_dark(snap))
        self.assertFalse(policy._can_read_scrolls(snap))

    def test_authoritative_darkness_does_not_mark_the_surface_dark(self):
        snap = Snapshot(
            player(10, 10), {}, [], floor_key=(0, 0, 0),
            equipment_observed=True, grids_observed=True,
            can_see_own_grid=False,
        )

        self.assertFalse(HengbotPolicy()._is_dark(snap))

    def test_authoritative_glow_releases_latched_recall_read(self):
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, name="empty lantern",
            known=True, fuel=0, is_equipment=True,
        )
        recall = item(
            "d", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            name="Word of Recall", count=9, aware=True, known=True,
        )
        teleport = item(
            "t", TVAL_SCROLL, SV_SCROLL_TELEPORT,
            name="Teleportation", count=15, aware=True, known=True,
        )
        curing = item(
            "c", TVAL_POTION, SV_POTION_CURE_CRITICAL,
            name="Cure Critical Wounds", count=9, aware=True, known=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, lit=False)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 10, 0),
            inventory=[recall, teleport, curing],
            equipment=[lantern], equipment_observed=True, grids_observed=True,
            can_see_own_grid=True,
        )
        policy = HengbotPolicy()
        policy.choose_key(
            replace(
                snap,
                turn=snap.turn - 1,
                equipment=[replace(lantern, fuel=50)],
                can_see_own_grid=False,
            )
        )

        self.assertFalse(policy._is_dark(snap))
        self.assertTrue(policy._can_read_scrolls(snap))
        self.assertEqual(policy.choose_key(snap), READ_KEY + "d")

    def test_authoritative_visibility_does_not_override_blind_gates(self):
        recall = item(
            "d", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            name="Word of Recall", count=9, aware=True, known=True,
        )
        snap = Snapshot(
            replace(player(10, 10), blind=True),
            {Position(10, 10): grid(10, 10, lit=False)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 10, 0), inventory=[recall],
            equipment_observed=True, grids_observed=True,
            can_see_own_grid=False,
        )
        policy = HengbotPolicy()

        self.assertFalse(policy._is_dark(snap))
        self.assertIsNone(policy._darkness_recovery_key(snap))
        self.assertFalse(policy.choose_key(snap).startswith(READ_KEY))

    def test_grid_memory_merge_preserves_authoritative_visibility(self):
        snap = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 10, 0), grids_observed=True,
            can_see_own_grid=True,
        )

        self.assertTrue(HengbotPolicy()._with_grid_memory(snap).can_see_own_grid)

    def test_pin_vacuity_dim_warning_starts_light_low_return(self):
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, name="dim lantern",
            known=True, fuel=50, is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 10, 0),
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9, aware=True),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15, aware=True),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=9, aware=True),
            ],
            equipment=[lantern], equipment_observed=True,
        )
        policy = HengbotPolicy()
        self.assertTrue(policy._should_start_town_return(snap))
        self.assertEqual(policy._last_return_trigger, "light-low")
        self.assertFalse(policy._expedition_light_ready(
            replace(snap, equipment=[replace(lantern, fuel=99)])
        ))
        self.assertTrue(policy._expedition_light_ready(
            replace(snap, equipment=[replace(lantern, fuel=100)])
        ))

    def test_readability_uses_environment_light_and_current_fuel_only(self):
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, known=True, fuel=0,
            is_equipment=True,
        )
        town = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10, lit=False)}, [],
            floor_key=(0, 0, 0), town_flag=True, equipment=[lantern],
            equipment_observed=True, grids_observed=True,
        )
        lit_dungeon = replace(
            town, floor_key=(DUNGEON_YEEK_CAVE, 1, 0), town_flag=False,
            grids={Position(10, 10): grid(10, 10, lit=True)},
        )
        dark_dungeon = replace(
            lit_dungeon, grids={Position(10, 10): grid(10, 10, lit=False)},
            inventory=[item("o", TVAL_FLASK, SV_FLASK_OIL, fuel=7500)],
        )
        policy = HengbotPolicy()
        self.assertTrue(policy._can_read_scrolls(town))
        self.assertTrue(policy._can_read_scrolls(lit_dungeon))
        self.assertFalse(policy._can_read_scrolls(dark_dungeon))

    def test_emergency_refills_before_reading_then_reads_after_light_returns(self):
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3)
        oil = item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=7500)
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, known=True, fuel=0,
            is_equipment=True,
        )
        snap = _test_policy.EmergencyRecallEscapeTest()._swarm([teleport, oil])
        snap = replace(
            snap,
            grids={position: replace(cell, lit=False) for position, cell in snap.grids.items()},
            equipment=[lantern], equipment_observed=True, grids_observed=True,
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "\\Fo")
        self.assertEqual(policy.last_reason, "refill-light")
        restored = replace(
            snap, turn=snap.turn + 1,
            equipment=[replace(lantern, fuel=7500)], inventory=[teleport],
        )
        self.assertEqual(policy.choose_key(restored), READ_KEY + "t")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_known_lantern_departure_requires_oil_or_reserve_fuel(self):
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, name="lantern",
            known=True, fuel=447, is_equipment=True,
        )
        base = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True, equipment=[lantern],
        )
        policy = HengbotPolicy()
        self.assertFalse(policy._light_ready(base))
        block = policy._departure_block_state(base)
        self.assertIn("light_ready", block["failed"])
        oil = item("o", TVAL_FLASK, SV_FLASK_OIL, count=OIL_TARGET, fuel=7500)
        self.assertTrue(policy._light_ready(replace(base, inventory=[oil])))
        self.assertTrue(policy._light_ready(replace(
            base, equipment=[replace(lantern, fuel=12000)]
        )))

    def test_dark_unknown_lantern_refills_before_dungeon_work(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10, lit=False)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("o", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)
            ],
            equipment=[self._hidden_lantern()],
            grids_observed=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._darkness_recovery_key(snap), "\\Fo")
        self.assertEqual(policy.choose_key(snap), "\\Fo")
        self.assertEqual(policy.last_reason, "refill-light")

    def test_dark_unknown_lantern_wields_identified_torch_without_oil(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10, lit=False)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item(
                    "t",
                    TVAL_LITE,
                    SV_LITE_TORCH,
                    name="torch (寿命 2500 turns)",
                    fuel=2500,
                    known=True,
                )
            ],
            equipment=[self._hidden_lantern()],
            grids_observed=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "wt")
        self.assertEqual(policy.last_reason, "wield-light")

    def test_lit_or_blind_does_not_trigger_hidden_lantern_recovery(self):
        oil = item("o", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)
        lit = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10, lit=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[oil],
            equipment=[self._hidden_lantern()],
        )
        blind = replace(
            lit,
            player=player(10, 10, blind=True),
            grids={Position(10, 10): grid(10, 10, lit=False)},
        )

        for snap in (lit, blind):
            policy = HengbotPolicy()
            policy.choose_key(snap)
            self.assertNotIn(policy.last_reason, {"refill-light", "wield-light"})

    def test_unknown_lantern_readiness_requires_departure_oil_target(self):
        lantern = self._hidden_lantern()
        no_oil = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, lit=True)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            equipment=[lantern],
        )
        insured = replace(
            no_oil,
            inventory=[
                item(
                    "o",
                    TVAL_FLASK,
                    SV_FLASK_OIL,
                    name="oil",
                    count=OIL_TARGET,
                    fuel=7500,
                )
            ],
        )
        policy = HengbotPolicy()

        self.assertFalse(policy._light_ready(no_oil))
        self.assertFalse(policy._expedition_light_ready(no_oil))
        self.assertFalse(policy._fundraising_light_ready(no_oil))
        self.assertTrue(policy._light_ready(insured))
        self.assertTrue(policy._expedition_light_ready(insured))
        self.assertTrue(policy._fundraising_light_ready(insured))
        self.assertTrue(
            any(
                need.store_type == STORE_GENERAL
                and need.category in {"oil", "fundraising-oil", "fundraising-light"}
                for need in policy._enumerate_town_needs(no_oil)
            )
        )

    def test_unknown_lantern_is_topped_up_once_before_departure(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10, lit=True)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                item(
                    "o",
                    TVAL_FLASK,
                    SV_FLASK_OIL,
                    name="oil",
                    count=OIL_TARGET,
                    fuel=7500,
                )
            ],
            equipment=[self._hidden_lantern()],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "\\Fo")
        self.assertEqual(policy.last_reason, "refill-light")
        self.assertNotEqual(policy.choose_key(snap), "\\Fo")

    def test_wields_a_torch_when_nothing_is_lit(self):
        # The Half-Troll death: a stack of torches in the pack, none wielded, so it
        # walked in the dark and could not see the monster that killed it.
        grids = {Position(10, 10): grid(10, 10)}
        torch = item("e", 39, 0, name="torch", count=5, fuel=2500)
        snap = Snapshot(player(10, 10), grids, [], inventory=[torch], equipment=[])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "we")
        self.assertEqual(pol.last_reason, "wield-light")

    def test_does_not_wield_when_a_light_is_equipped(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("e", 39, 0)],
            equipment=[item("f", 39, 0)],
        )
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "wield-light")

    def test_does_not_wield_when_no_light_carried(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(player(10, 10), grids, [], inventory=[item("a", 80, 32)], equipment=[])
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "wield-light")

    def test_skips_an_expired_torch(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[
                item("a", TVAL_LITE, SV_LITE_TORCH, fuel=0),
                item("b", TVAL_LITE, SV_LITE_TORCH, fuel=2400),
            ],
        )
        self.assertEqual(HengbotPolicy().choose_key(snap), "wb")

    def test_refills_a_low_lantern_from_oil(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("b", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)],
            equipment=[item("f", TVAL_LITE, SV_LITE_LANTERN, name="lantern", fuel=900)],
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "\\Fb")
        self.assertEqual(pol.last_reason, "refill-light")

    def test_wields_fuelled_torch_when_low_lantern_has_no_oil(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[
                item("b", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=2500)
            ],
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    name="nearly empty lantern",
                    fuel=17,
                )
            ],
        )
        pol = HengbotPolicy()

        self.assertEqual(pol.choose_key(snap), "wb")
        self.assertEqual(pol.last_reason, "wield-light")

    def test_restores_empty_pack_lantern_after_oil_is_acquired(self):
        grids = {Position(10, 10): grid(10, 10)}
        torch = item(
            "light", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=640
        )
        empty_lantern = item(
            "o",
            TVAL_LITE,
            SV_LITE_LANTERN,
            name="empty ego lantern",
            fuel=0,
            known=True,
            is_equipment=True,
            is_ego=True,
        )
        oil = item("a", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)
        town = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[oil, empty_lantern],
            equipment=[torch],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        pol = HengbotPolicy()

        self.assertEqual(pol.choose_key(town), "wo")
        self.assertEqual(pol.last_reason, "restore-lantern")

        lantern_equipped = replace(
            town,
            inventory=[oil, replace(torch, slot="t")],
            equipment=[replace(empty_lantern, slot="light")],
        )
        self.assertEqual(pol.choose_key(lantern_equipped), "\\Fa")
        self.assertEqual(pol.last_reason, "refill-light")

    def test_does_not_equip_empty_pack_lantern_without_oil(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[
                item(
                    "o", TVAL_LITE, SV_LITE_LANTERN,
                    name="empty lantern", fuel=0, known=True,
                )
            ],
            equipment=[
                item("light", TVAL_LITE, SV_LITE_TORCH, fuel=640)
            ],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        pol = HengbotPolicy()

        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "restore-lantern")

    def test_does_not_refill_a_full_lantern(self):
        grids = {Position(10, 10): grid(10, 10)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("b", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)],
            equipment=[item("f", TVAL_LITE, SV_LITE_LANTERN, name="lantern", fuel=5000)],
        )
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "refill-light")

    def test_refills_an_unidentified_lantern_when_player_square_is_dark(self):
        grids = {Position(10, 10): grid(10, 10, lit=False)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("b", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)],
            equipment=[
                item(
                    "f", TVAL_LITE, SV_LITE_LANTERN,
                    name="unidentified brass lantern", aware=True, known=False,
                )
            ],
        )
        pol = HengbotPolicy()

        self.assertEqual(pol.choose_key(snap), "\\Fb")
        self.assertEqual(pol.last_reason, "refill-light")

    def test_does_not_refill_an_unidentified_light(self):
        # An unidentified equipped light reports a redacted fuel of 0, which must
        # not be mistaken for empty — refilling it would waste a flask of oil on a
        # light that is very likely full.
        grids = {Position(10, 10): grid(10, 10, lit=True)}
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("b", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)],
            equipment=[
                item("f", TVAL_LITE, SV_LITE_LANTERN, name="lantern", aware=False, fuel=0)
            ],
        )
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertNotEqual(pol.last_reason, "refill-light")

class TownRestockTest(unittest.TestCase):
    def _in_general_store(
        self, items, *, gold=500, inv=None, food_type=0, level=1, class_id=-1
    ):
        grids = {Position(10, 10): grid(10, 10)}
        return Snapshot(
            player(
                10, 10, gold=gold, food_type=food_type,
                level=level, class_id=class_id,
            ),
            grids,
            [],
            floor_key=(0, 0, 0),
            inventory=inv or [],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
            store=StoreState(store_type=STORE_GENERAL, items=items),
        )

    def test_buys_rations_when_food_stock_is_low(self):
        wares = [
            store_item("e", TVAL_FLASK, SV_FLASK_OIL, price=3),
            store_item("b", TVAL_FOOD, 35, price=5, count=60),
        ]
        inv = [item("f", TVAL_FLASK, SV_FLASK_OIL, count=8, fuel=500)]  # oil stocked
        pol = HengbotPolicy()
        self.assertEqual(_public_shop_inner(self, pol, self._in_general_store(wares, inv=inv)), "pb5\r\r")
        self.assertEqual(pol.last_reason, "shop:one-shot-buy")

    def test_mana_race_does_not_buy_rations_as_food(self):
        wares = [store_item("b", TVAL_FOOD, 35, price=3, count=60)]
        snap = self._in_general_store(
            wares, inv=[], food_type=FOOD_TYPE_MANA,
            level=4, class_id=PLAYER_CLASS_WARRIOR,
        )
        pol = HengbotPolicy()

        self.assertEqual(pol._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "shop:leave")

        # The same shortage is owned by the race-aware ledger and routes to the
        # Magic store, where charged devices are the only valid food purchase.
        town = replace(snap, store=None, town_flag=True)
        self.assertEqual(pol._supply_ledger(town, 1)["food"].stores, (STORE_MAGIC,))
        self.assertIn(
            TownNeed(STORE_MAGIC, "food", "normal"),
            pol._enumerate_town_needs(town),
        )

    def test_legacy_mana_character_does_not_buy_rations(self):
        wares = [store_item("b", TVAL_FOOD, 35, price=3, count=60)]
        snap = self._in_general_store(
            wares, inv=[], food_type=FOOD_TYPE_MANA, class_id=-1
        )

        policy = HengbotPolicy()
        self.assertIsNone(policy._next_purchase_unreserved(snap))
        town = replace(snap, store=None, town_flag=True)
        self.assertIn(
            STORE_MAGIC,
            [need.store_type for need in policy._enumerate_town_needs(town)],
        )

    def test_walks_to_the_store_for_a_food_restock(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        snap = Snapshot(
            player(10, 10, gold=200),
            grids,
            [],
            floor_key=(0, 0, 0),
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000)],
        )
        pol = HengbotPolicy()
        pol._owns_lantern = lambda s: True  # lantern equipped, food count is 0
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "shop:approach")

    def test_town_arrival_clears_an_old_store_give_up(self):
        pol = HengbotPolicy()
        pol._shopping_abandoned = True
        dungeon = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [], floor_key=(2, 3, 0)
        )
        pol.choose_key(dungeon)
        town = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0)
        )
        pol.choose_key(town)
        self.assertFalse(pol._shopping_abandoned)

class HiddenInfoFallbackTest(unittest.TestCase):
    def _mana_starvation_snapshot(
        self, *, store=None, inventory=None, food=400, gold=170
    ):
        return Snapshot(
            player(
                10, 10, food=food, gold=gold,
                food_type=FOOD_TYPE_MANA,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory or [],
            store=store,
        )

    def test_a21_gate1_magic_page_has_no_affordable_device_and_stops(self):
        # Recorded 2026-08-18 10:30 page: the cheapest charged device was the
        # 443g Magic Missile wand, while the fainting Zombie had only 170g.
        page = StoreState(
            STORE_MAGIC,
            [
                store_item("a", 96, 0, price=160, name="Arcane book"),
                store_item(
                    "g", TVAL_WAND, 15, price=443, pval=13,
                    name="Magic Missile wand (13 charges)",
                ),
                store_item(
                    "m", TVAL_STAFF, 10, price=471, pval=18,
                    name="Treasure Location staff (18 charges)",
                ),
            ],
        )
        policy = HengbotPolicy()
        policy._home_knowledge_current = True

        self.assertEqual(policy._shop(self._mana_starvation_snapshot(store=page)), WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "town:blocked:survival-mana-no-charges"
        )
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_a21_affordable_magic_device_uses_buy_then_absorb(self):
        wand = store_item(
            "b", TVAL_WAND, 1, price=80, pval=15,
            name="Slow Monster wand (15 charges)",
        )
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        in_store = self._mana_starvation_snapshot(
            store=StoreState(STORE_MAGIC, [wand])
        )

        self.assertEqual(policy._shop(in_store), "pb\r")
        self.assertEqual(policy.last_reason, "survival:buy-food")

        acquired = item("d", TVAL_WAND, 1, charges=15, name="wand")
        outside = self._mana_starvation_snapshot(inventory=[acquired])
        self.assertEqual(policy._mana_food_survival_override_key(outside), "Ed")
        self.assertEqual(policy.last_reason, "survival:mana-absorb")

    def test_a21_home_device_prevents_affordable_purchase(self):
        wand = store_item(
            "b", TVAL_WAND, 1, price=80, pval=15, name="shop wand"
        )
        stored = item("h", TVAL_STAFF, 8, charges=12, name="Home staff")
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [stored]

        self.assertEqual(
            policy._shop(self._mana_starvation_snapshot(
                store=StoreState(STORE_MAGIC, [wand]), gold=500
            )),
            LEAVE_STORE_KEY,
        )
        self.assertEqual(policy.last_reason, "survival:mana-home-before-purchase")
        self.assertEqual(policy._home_pending_item, policy._item_signature(stored))

    def test_a21_fresh_home_absence_falls_through_once(self):
        wand = store_item(
            "b", TVAL_WAND, 1, price=80, pval=15, name="shop wand"
        )
        snap = self._mana_starvation_snapshot(
            store=StoreState(STORE_MAGIC, [wand]), gold=500
        )
        snap = replace(snap, town_id=policy_module.ZUL_TOWN_ID)
        policy = HengbotPolicy()

        self.assertEqual(policy._shop(snap), "pb\r")
        self.assertEqual(policy._home_procurement_fallthrough, "town-without-home")
        policy._home_knowledge_current = True
        policy._home_knowledge_items = []
        self.assertEqual(policy._shop(snap), "pb\r")
        self.assertEqual(policy._shop(snap), "pb\r")

    def test_home_bearing_executor_rejection_is_visible_stop(self):
        ration = store_item("a", TVAL_FOOD, 35, price=1, name="ration")
        snap = replace(
            self._mana_starvation_snapshot(
                store=StoreState(STORE_GENERAL, [ration]), gold=500
            ),
            town_id=0,
            player=replace(self._mana_starvation_snapshot().player, food_type=0),
        )
        policy = HengbotPolicy()
        policy._home_available = lambda _snapshot: True
        policy._ensure_home_visit_request = lambda _snapshot: False

        self.assertEqual(policy._shop(snap), WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "town:blocked:procurement-home-unroutable"
        )
        self.assertIsNone(policy._home_procurement_fallthrough)
        self.assertIsNone(
            policy.consume_pending_home_procurement_fallthrough_report()
        )

    def test_stale_blocked_reason_cannot_turn_home_stock_into_wait(self):
        ration = store_item("a", TVAL_FOOD, 35, price=1, name="ration")
        stored = item("h", TVAL_FOOD, 35, count=20, name="Home rations")
        snap = replace(
            self._mana_starvation_snapshot(
                store=StoreState(STORE_GENERAL, [ration]), gold=500
            ),
            player=replace(self._mana_starvation_snapshot().player, food_type=0),
        )
        policy = HengbotPolicy()
        policy.last_reason = "town:blocked:repetition"
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [stored]

        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "survival:ration-home-before-purchase")
        self.assertEqual(policy._home_pending_item, policy._item_signature(stored))

    def test_procurement_consumer_classes_cover_ammo_and_remove_curse(self):
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        shot = item("h", TVAL_SHOT, 2, count=20, name="Iron Shot")
        star = item(
            "i", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE,
            name="*Remove Curse*",
        )
        policy._home_knowledge_items = [shot, star]

        self.assertIs(
            policy._home_procurement_candidate((TVAL_SHOT, 5)), shot
        )
        self.assertEqual(
            policy._procurement_equivalence((TVAL_SHOT, 5)),
            "ammo:exact-tval-any-sval",
        )
        self.assertIs(
            policy._home_procurement_candidate(
                (TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
            ),
            star,
        )
        self.assertEqual(
            policy._procurement_equivalence(
                (TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
            ),
            "remove-curse:normal-or-star",
        )

    def test_remove_curse_procurement_equivalence_is_directional(self):
        normal = item(
            "h", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="Remove Curse"
        )
        star = item(
            "i", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE,
            name="*Remove Curse*",
        )
        shop_star = store_item(
            "z", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, price=500
        )
        snap = self._mana_starvation_snapshot(
            store=StoreState(STORE_TEMPLE, [shop_star]), gold=1000
        )
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [normal]

        self.assertIs(
            policy._purchase_has_fresh_home_absence(snap, shop_star),
            policy_module.ProcurementHomeGate.ALLOW_PURCHASE,
        )
        self.assertEqual(
            policy._home_procurement_fallthrough, "fresh-catalogue-absence"
        )
        self.assertEqual(
            policy._home_procurement_fallthrough_equivalence,
            "item:exact-tval-sval",
        )

        policy._home_knowledge_items = [star]
        shop_normal = store_item(
            "y", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, price=100
        )
        self.assertIs(
            policy._purchase_has_fresh_home_absence(snap, shop_normal),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )
        self.assertEqual(policy._home_pending_item, policy._item_signature(star))

    def test_digger_procurement_matches_every_consumer_usable_sval(self):
        dwarven_pick = item(
            "h", TVAL_DIGGING, 6, name="Dwarven Pick", is_equipment=True
        )
        shovel = store_item(
            "a", TVAL_DIGGING, SV_DIGGING_SHOVEL, price=100,
            name="Shovel", is_equipment=True,
        )
        snap = self._mana_starvation_snapshot(
            store=StoreState(STORE_GENERAL, [shovel]), gold=500
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [dwarven_pick]

        self.assertIs(
            policy._purchase_has_fresh_home_absence(snap, shovel),
            policy_module.ProcurementHomeGate.HOME_FIRST,
        )
        self.assertEqual(
            policy._home_pending_item, policy._item_signature(dwarven_pick)
        )
        self.assertEqual(
            policy._home_procurement_fallthrough_equivalence,
            "digger:exact-tval-any-sval",
        )

    def test_unknown_town_fails_closed_as_home_bearing(self):
        snap = replace(self._mana_starvation_snapshot(), town_id=999)
        policy = HengbotPolicy()

        self.assertTrue(policy._current_town_has_home(snap))

    def test_food_home_lookup_uses_consumer_need_class(self):
        ration = store_item("a", TVAL_FOOD, 35, price=1, name="ration")
        biscuit = item("h", TVAL_FOOD, 32, count=30, name="Hard Biscuit")
        snap = replace(
            self._mana_starvation_snapshot(
                store=StoreState(STORE_GENERAL, [ration]), gold=500
            ),
            town_id=0,
            player=replace(self._mana_starvation_snapshot().player, food_type=0),
        )
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [biscuit]

        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(policy._home_pending_item, policy._item_signature(biscuit))
        self.assertIsNone(policy._home_procurement_fallthrough)

    def test_home_procurement_probe_clears_when_need_is_satisfied(self):
        ration = item("a", TVAL_FOOD, 35, count=20, name="ration")
        snap = replace(
            self._mana_starvation_snapshot(inventory=[ration]),
            player=replace(self._mana_starvation_snapshot().player, food_type=0),
        )
        policy = HengbotPolicy()
        policy._home_procurement_probe = (TVAL_FOOD, 35)

        needs = policy._town_need_candidates(snap)

        self.assertIsNone(policy._home_procurement_probe)
        self.assertNotIn("procurement-home-first", {need.category for need in needs})

    def test_shortage_purchase_is_home_first_too(self):
        oil = store_item("a", TVAL_FLASK, SV_FLASK_OIL, price=3, name="oil")
        stored = item("h", TVAL_FLASK, SV_FLASK_OIL, count=3, name="Home oil")
        snap = Snapshot(
            player(10, 10, food=12000, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            equipment=[
                item("L", TVAL_LITE, SV_LITE_LANTERN, fuel=1000, known=True)
            ],
            store=StoreState(STORE_GENERAL, [oil]),
        )
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [stored]

        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:home-first-before-purchase")
        self.assertEqual(policy._home_pending_item, policy._item_signature(stored))

    def test_a21_unaffordable_device_composes_surplus_sale_before_stop(self):
        shots = item("s", TVAL_SHOT, 1, count=40, name="shots")
        snap = self._mana_starvation_snapshot(
            store=StoreState(STORE_WEAPON, []),
            inventory=[shots],
            gold=170,
        )
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._mana_survival_device_price = 443

        key = policy._shop(snap)

        self.assertNotIn(key, {WAIT_KEY, LEAVE_STORE_KEY})
        self.assertIn(
            policy.last_reason,
            {
                "shop:batch-inscribe",
                "shop:sale-inscribe",
                "shop:one-shot-sale-compose",
            },
        )

    def test_a21_home_device_files_executor_withdrawal_before_waits(self):
        stored = item("h", TVAL_STAFF, 8, charges=12, name="Light staff")
        snap = self._mana_starvation_snapshot()
        snap = replace(
            snap,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_HOME
                ),
            },
        )
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_MAGIC] = snap.turn
        policy._home_knowledge_items = [stored]
        policy._home_knowledge_current = True
        policy._home_available = lambda _snapshot: True
        policy._build_grid_index(snap)

        self.assertEqual(policy._mana_food_survival_override_key(snap), "6")
        self.assertEqual(policy.last_reason, "survival:mana-home-approach")
        self.assertEqual(policy._home_pending_item, policy._item_signature(stored))
        request = policy._derived_home_visit_request(snap)
        self.assertEqual(request.kind, policy_module.HomeVisitKind.WITHDRAW)
        self.assertEqual(request.item_identity, policy._item_signature(stored))
        self.assertEqual(policy._home_visit.request, request)

    def test_a21_unroutable_home_never_rearms_magic_entry_loop(self):
        policy = HengbotPolicy()
        snap = replace(self._mana_starvation_snapshot(), town_id=0)
        policy._town_store_attempted[STORE_MAGIC] = snap.turn

        self.assertEqual(policy._mana_food_survival_override_key(snap), WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:blocked:survival-mana-no-charges")
        self.assertIsNone(policy._home_procurement_probe)
        self.assertIsNone(policy._home_procurement_fallthrough)

    def test_procurement_route_failures_are_immediate_final_stops(self):
        self.assertIn(
            "town:blocked:procurement-home-unroutable",
            POLICY_FINAL_STOP_REASONS,
        )
        self.assertIn(
            "town:blocked:procurement-home-unavailable",
            POLICY_FINAL_STOP_REASONS,
        )

    def test_a21_unroutable_home_blocks_before_magic_entry(self):
        policy = HengbotPolicy()
        outside = replace(
            self._mana_starvation_snapshot(),
            town_id=0,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_MAGIC
                ),
            },
        )
        policy._build_grid_index(outside)

        self.assertEqual(policy._mana_food_survival_override_key(outside), WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:blocked:survival-mana-no-charges")
        self.assertNotIn(STORE_MAGIC, policy._town_store_attempted)

    def test_starving_ration_race_with_home_stock_withdraws_before_buying(self):
        ration = store_item("a", TVAL_FOOD, 35, price=1, name="ration")
        stored = item("h", TVAL_FOOD, 35, count=20, name="Home rations")
        snap = replace(
            self._mana_starvation_snapshot(
                store=StoreState(STORE_GENERAL, [ration]), gold=500
            ),
            player=replace(
                self._mana_starvation_snapshot().player,
                food_type=0,
            ),
        )
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [stored]

        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "survival:ration-home-before-purchase")
        self.assertEqual(policy._home_pending_item, policy._item_signature(stored))

    def test_unknown_home_device_is_a_mana_food_withdrawal_candidate(self):
        unknown = item("h", TVAL_WAND, 1, aware=False, charges=0, name="unknown wand")
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [unknown]

        self.assertIs(policy._home_mana_food_candidate(), unknown)

    def test_a21_floor_device_pickup_preempts_terminal_wait(self):
        snap = self._mana_starvation_snapshot()
        snap = replace(
            snap,
            grids={
                Position(10, 10): grid(
                    10, 10, objects=1, object_tvals=(TVAL_WAND,)
                )
            },
        )
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_MAGIC] = snap.turn

        self.assertEqual(policy._mana_food_survival_override_key(snap), PICKUP_KEY)
        self.assertEqual(policy.last_reason, "mana-food:pickup-device")

    def test_a21_override_is_state_and_food_type_gated(self):
        policy = HengbotPolicy()
        adequate = self._mana_starvation_snapshot(food=12000)
        ration_race = replace(
            self._mana_starvation_snapshot(),
            player=player(10, 10, food=400, food_type=0),
        )

        self.assertIsNone(policy._mana_food_survival_override_key(adequate))
        self.assertIsNone(policy._mana_food_survival_override_key(ration_race))

    def test_non_ration_non_mana_race_never_composes_tval_food_purchase(self):
        ration = store_item("a", TVAL_FOOD, 35, price=1, name="ration")
        for food_type in (1, 2, 3, 5):
            snap = self._mana_starvation_snapshot(
                store=StoreState(STORE_GENERAL, [ration])
            )
            snap = replace(
                snap,
                player=replace(snap.player, food_type=food_type),
            )
            policy = HengbotPolicy()
            policy._fundraising_mode = "prepare"

            self.assertIsNone(policy._next_purchase_unreserved(snap))
            self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
            self.assertNotIn("pa", policy._shop(snap))

    def test_mana_race_eats_an_unidentified_wand(self):
        # The emitter hides charges until identified; the game lets MANA races
        # eat any wand/staff, so an unknown one must still be tried.
        grids = {Position(10, 10): grid(10, 10)}
        wand = item("d", 65, 0, aware=False)  # unknown wand, charges read as 0
        snap = Snapshot(
            player(10, 10, food=400, food_type=4), grids, [], inventory=[wand]
        )
        self.assertEqual(HengbotPolicy().choose_key(snap), "Ed")

    def test_wields_an_unidentified_light_rather_than_walking_dark(self):
        grids = {Position(10, 10): grid(10, 10)}
        torch = item("c", TVAL_LITE, SV_LITE_TORCH, aware=False)  # fuel hidden
        snap = Snapshot(player(10, 10), grids, [], inventory=[torch], equipment=[])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "wc")
        self.assertEqual(pol.last_reason, "wield-light")

    def test_chargeless_mana_race_needs_device_food_restock(self):
        snap = Snapshot(
            player(10, 10, food=400, food_type=4),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
        )
        self.assertTrue(HengbotPolicy()._needs_food_restock(snap))

    def test_mana_race_jerky_is_zero_food_and_does_not_suppress_return(self):
        jerky = item("a", TVAL_FOOD, 35, count=10, name="jerky")
        snap = Snapshot(
            player(10, 10, food=1500, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[jerky],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._supply_ledger(snap, 2)["food"].count, 0)
        self.assertIsNone(policy._find_edible(snap))
        self.assertTrue(policy._should_start_town_return(snap))
        self.assertEqual(policy._last_return_trigger, "food-hungry")
        self.assertTrue(
            policy._is_disposable_item(jerky, food_type=FOOD_TYPE_MANA)
        )
        # Food is disposable for this race, but is not an Alchemist sale;
        # the town planner/shop path routes it to the General Store.
        self.assertIsNone(policy._find_low_level_sale(snap))

    def test_mana_race_fundraising_buys_device_charges_not_biscuits(self):
        biscuit = store_item("a", TVAL_FOOD, 35, price=1, name="biscuit")
        wand = store_item("b", TVAL_WAND, 1, price=80, name="wand", pval=15)
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._home_knowledge_current = True
        general = Snapshot(
            player(
                10,
                10,
                gold=500,
                class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            store=StoreState(store_type=STORE_GENERAL, items=[biscuit]),
        )
        self.assertIsNone(policy._next_purchase(general))

        magic = replace(
            general, store=StoreState(store_type=STORE_MAGIC, items=[wand])
        )
        self.assertEqual(policy._next_purchase(magic), wand)
        self.assertEqual(_public_shop_inner(self, policy, magic), "pb\r")
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")

    def test_mana_race_with_low_device_charges_routes_to_magic_shop(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=500,
                class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL),
                item("t", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
            ],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        self.assertEqual(policy._next_required_store_type(snap), STORE_MAGIC)

    def test_mana_food_purchase_slots_then_function_then_price(self):
        identify, cheap_fillers = _parse_store({
            "store_type": STORE_MAGIC,
            "items": [
                {"letter": "a", "name": "鑑定の杖 (20回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": SV_STAFF_IDENTIFY, "price": 500},
                {"letter": "b", "name": "謎の魔法棒 (5回分)", "count": 4,
                 "tval": TVAL_WAND, "sval": 1, "price": 100},
            ],
        }).items
        snap = Snapshot(
            player(
                10, 10, gold=500, food_type=FOOD_TYPE_MANA,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            store=StoreState(STORE_MAGIC, [identify, cheap_fillers]),
        )
        policy = HengbotPolicy()
        self.assertEqual(policy._next_purchase_unreserved(snap), identify)

        functional, filler, expensive, cheap = _parse_store({
            "store_type": STORE_MAGIC,
            "items": [
                {"letter": "c", "name": "鑑定の杖 (15回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": SV_STAFF_IDENTIFY, "price": 500},
                {"letter": "d", "name": "謎の杖 (15回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": 1, "price": 100},
                {"letter": "e", "name": "謎の杖 (15回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": 1, "price": 120},
                {"letter": "f", "name": "謎の杖 (15回分)", "count": 1,
                 "tval": TVAL_STAFF, "sval": 2, "price": 80},
            ],
        }).items
        tied = replace(snap, store=StoreState(STORE_MAGIC, [filler, functional]))
        self.assertEqual(policy._mana_food_purchase(tied), functional)

        price_tie = replace(snap, store=StoreState(STORE_MAGIC, [expensive, cheap]))
        self.assertEqual(policy._mana_food_purchase(price_tie), cheap)

    def test_mana_food_purchase_accepts_chargeless_store_name_at_nominal_one(self):
        device = _parse_store({
            "store_type": STORE_MAGIC,
            "items": [{"letter": "a", "name": "謎の魔法棒", "count": 1,
                       "tval": TVAL_WAND, "sval": 1, "price": 80}],
        }).items[0]
        snap = Snapshot(
            player(10, 10, gold=100, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)}, [],
            store=StoreState(STORE_MAGIC, [device]),
        )

        self.assertEqual(HengbotPolicy()._mana_food_purchase(snap), device)

    def test_mana_food_eating_preserves_function_then_survival_overrides(self):
        policy = HengbotPolicy()
        identify = item(
            "i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=8, name="Identify"
        )
        filler = item("f", TVAL_STAFF, 1, charges=12, name="filler")

        hungry = Snapshot(
            player(10, 10, food=1500, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)}, [], inventory=[identify, filler],
        )
        self.assertEqual(policy._find_edible(hungry), filler)

        hungry_identify_only = replace(hungry, inventory=[identify])
        self.assertEqual(policy._find_edible(hungry_identify_only), identify)

        partial = replace(identify, slot="p", charges=6)
        fresh = replace(identify, slot="q", charges=18)
        partials = replace(hungry, inventory=[fresh, partial])
        self.assertEqual(policy._find_edible(partials), partial)

        with_filler = replace(hungry, inventory=[fresh, partial, filler])
        self.assertEqual(policy._find_edible(with_filler), filler)

        floor = replace(identify, charges=IDENTIFY_CHARGE_FLOOR)
        hungry_floor = replace(hungry, inventory=[floor])
        self.assertIsNone(policy._find_edible(hungry_floor))

        weak_floor = replace(
            hungry_floor,
            player=player(10, 10, food=750, food_type=FOOD_TYPE_MANA),
        )
        self.assertEqual(policy._find_edible(weak_floor), floor)
        fainting_floor = replace(
            hungry_floor,
            player=player(10, 10, food=400, food_type=FOOD_TYPE_MANA),
        )
        self.assertEqual(policy._find_edible(fainting_floor), floor)

    def test_identify_floor_and_hunger_return_use_same_edible_charge_count(self):
        policy = HengbotPolicy()
        floor = item(
            "i", TVAL_STAFF, SV_STAFF_IDENTIFY,
            charges=IDENTIFY_CHARGE_FLOOR, name="Identify",
        )
        hungry = Snapshot(
            player(10, 10, food=1500, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0), inventory=[floor],
        )
        self.assertEqual(policy._supply_ledger(hungry, 2)["food"].count, 0)
        self.assertTrue(policy._should_start_town_return(hungry))
        self.assertEqual(policy._last_return_trigger, "food-hungry")

        weak = replace(
            hungry,
            player=player(10, 10, food=750, food_type=FOOD_TYPE_MANA),
        )
        self.assertEqual(
            policy._supply_ledger(weak, 2)["food"].count,
            IDENTIFY_CHARGE_FLOOR,
        )
        self.assertFalse(policy._should_start_town_return(weak))

    def test_town_starvation_routes_to_food_store_before_other_errands(self):
        snap = Snapshot(
            player(10, 10, food=400, gold=15000, food_type=FOOD_TYPE_MANA),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_MAGIC
                ),
            },
            [],
            town_flag=True,
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "survival:mana-shop-approach")

    def test_normal_race_food_restock_contract_is_unchanged(self):
        ration = item("a", TVAL_FOOD, 35)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[ration] * 5,
        )
        self.assertFalse(HengbotPolicy()._needs_food_restock(snap))

class IdentifyStaffTest(unittest.TestCase):
    """A Staff of Identify is required in the departure kit for 10F+, and while
    the pack is filling the bot identifies unknowns so junk can be judged/shed.
    """

    def _staff(self, charges=20):
        return item(
            "s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=charges, name="Staff of Identify"
        )

    def _town(self, deepest, inventory=None):
        pol = HengbotPolicy()
        pol._deepest_level = deepest
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory or [],
        )
        return pol, snap

    def test_staff_required_for_deep_departure(self):
        pol, snap = self._town(STAFF_IDENTIFY_MIN_DEPTH)  # planned depth >= 10
        self.assertFalse(pol._identify_staff_ready(snap))
        pol2, snap2 = self._town(STAFF_IDENTIFY_MIN_DEPTH, inventory=[self._staff()])
        self.assertTrue(pol2._identify_staff_ready(snap2))

    def test_staff_not_required_when_shallow(self):
        pol, snap = self._town(3)  # planned depth 4 < 10
        self.assertTrue(pol._identify_staff_ready(snap))

    def test_depleted_staff_is_not_ready(self):
        pol, snap = self._town(STAFF_IDENTIFY_MIN_DEPTH, inventory=[self._staff(charges=0)])
        self.assertFalse(pol._identify_staff_ready(snap))

    def test_live_partial_staff_departs_after_magic_shop_is_exhausted(self):
        pol, snap = self._town(
            STAFF_IDENTIFY_MIN_DEPTH,
            inventory=[self._staff(charges=11)],
        )
        self.assertFalse(pol._identify_staff_ready(snap))

        pol._town_store_attempted[STORE_MAGIC] = snap.turn

        self.assertTrue(pol._identify_staff_ready(snap))
        self.assertNotEqual(pol._town_terminal_transitions(snap), STORE_MAGIC)
        self.assertIsNone(pol._town_restock_wait_until)

    def test_empty_staff_still_blocks_after_magic_shop_is_exhausted(self):
        pol, snap = self._town(
            STAFF_IDENTIFY_MIN_DEPTH,
            inventory=[self._staff(charges=0)],
        )
        pol._town_store_attempted[STORE_MAGIC] = snap.turn

        self.assertFalse(pol._identify_staff_ready(snap))

    def test_deep_departure_buys_staff_at_magic_shop(self):
        # Fully supplied except the staff → _next_purchase at the Magic shop must
        # pick the Staff of Identify.
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=15),  # teleport (deep target is 15)
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
        ]
        snap = Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=inv,
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)],
            store=StoreState(
                STORE_MAGIC,
                [store_item("z", TVAL_STAFF, SV_STAFF_IDENTIFY, price=500)],
            ),
        )
        pol = HengbotPolicy()
        pol._deepest_level = STAFF_IDENTIFY_MIN_DEPTH
        purchase = pol._next_purchase(snap)
        self.assertIsNotNone(purchase)
        self.assertEqual((purchase.tval, purchase.sval), (TVAL_STAFF, SV_STAFF_IDENTIFY))

    def test_store_decision_records_identify_staff_selector_evidence(self):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
        ]
        snap = Snapshot(
            player(10, 10, gold=9193, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=inv,
            equipment=[
                item(
                    "g",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
            store=StoreState(
                STORE_MAGIC,
                [
                    store_item(
                        "z",
                        TVAL_STAFF,
                        SV_STAFF_IDENTIFY,
                        price=950,
                        name="Staff of Identify",
                        charges=19,
                        count=4,
                    )
                ],
            ),
        )
        pol = HengbotPolicy()
        pol._deepest_level = STAFF_IDENTIFY_MIN_DEPTH

        key = _public_shop_inner(self, pol, snap)
        pol._record_shop_selector_diagnostics(snap, key)

        self.assertEqual(key, "pz1\r\r")
        self.assertEqual(pol.last_reason, "shop:one-shot-buy")
        self.assertEqual(
            pol._shop_selector_diagnostics,
            {
                "winning_rung": "shop:one-shot-buy",
                "gold": 9193,
                "wanted_purchase": {
                    "category": "identify-staff",
                    "name": "Staff of Identify",
                    "letter": "z",
                    "price": 950,
                    "count": 4,
                    "charges": 19,
                },
                "considered_candidate": {
                    "category": "identify-staff",
                    "name": "Staff of Identify",
                    "letter": "z",
                    "price": 950,
                    "count": 4,
                    "charges": 19,
                },
                "rejection_reason": "selected",
            },
        )

    def test_recharge_wander_evidence_keeps_obtainable_magic_buy_live(self):
        """Replay the durable fields at the evidence trace's Magic visit."""
        inventory = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            self._staff(charges=19),
        ]
        base = Snapshot(
            player(
                28, 69, gold=6830, class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA,
            ),
            {Position(28, 69): grid(28, 69)},
            [],
            turn=4034680,
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=StoreState(
                STORE_MAGIC,
                [store_item(
                    "h", TVAL_STAFF, SV_STAFF_IDENTIFY,
                    price=917, name="Staff of Identify", charges=21,
                )],
            ),
        )
        policy = HengbotPolicy()
        policy._deepest_level = STAFF_IDENTIFY_MIN_DEPTH

        operation = _public_shop_inner(self, policy, base)

        self.assertEqual(operation, "ph\r")
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")
        self.assertGreater(policy._decision_sequence, 1)

    def test_home_staff_is_withdrawn_before_buying_replacement(self):
        stored = store_item(
            "h", TVAL_STAFF, SV_STAFF_IDENTIFY,
            name="Staff of Identify", charges=25,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            store=StoreState(STORE_HOME, [stored]),
        )
        pol = HengbotPolicy()
        pol._deepest_level = STAFF_IDENTIFY_MIN_DEPTH

        self.assertEqual(pol._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home:queue-withdraw-identify-staff-reserve")
        self.assertFalse(pol._home_identify_staff_sale_pending)

    def test_ready_pack_withdraws_home_staff_for_sale(self):
        stored = store_item(
            "h", TVAL_STAFF, SV_STAFF_IDENTIFY,
            name="Staff of Identify", charges=3,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[self._staff(25)],
            store=StoreState(STORE_HOME, [stored]),
        )
        pol = HengbotPolicy()
        pol._deepest_level = STAFF_IDENTIFY_MIN_DEPTH

        self.assertEqual(pol._shop(snap), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home:queue-withdraw-surplus-identify-staff")
        self.assertTrue(pol._home_identify_staff_sale_pending)
        self.assertNotIn(STORE_MAGIC, pol._town_store_attempted)

    def test_home_withdrawn_staff_is_sellable_below_normal_pack_cap(self):
        pol = HengbotPolicy()
        pol._home_identify_staff_sale_pending = True
        staff = self._staff(3)
        reserve = replace(self._staff(25), slot="r")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[staff, reserve],
        )

        self.assertEqual(pol._find_device_sale(snap).slot, staff.slot)

    def test_home_staff_sale_rearms_completed_magic_and_home_stops(self):
        pol = HengbotPolicy()
        pol._town_errand_plan = policy_module.TownErrandPlan(
            stops=[STORE_MAGIC, STORE_HOME],
            index=2,
            completed_this_visit=[STORE_MAGIC, STORE_HOME],
            skipped_latched=[STORE_MAGIC, STORE_HOME],
        )
        pol._town_store_attempted = {STORE_MAGIC: 10, STORE_HOME: 10}

        pol._rearm_town_store_for_new_work(STORE_MAGIC)
        self.assertNotIn(STORE_MAGIC, pol._town_store_attempted)
        self.assertNotIn(
            STORE_MAGIC, pol._town_errand_plan.completed_this_visit
        )

        pol._rearm_town_store_for_new_work(STORE_HOME)
        self.assertNotIn(STORE_HOME, pol._town_store_attempted)
        self.assertNotIn(STORE_HOME, pol._town_errand_plan.completed_this_visit)
        self.assertNotIn(STORE_HOME, pol._town_errand_plan.skipped_latched)

    def test_new_work_rearm_preserves_visit_bound_unless_progress_releases_it(self):
        pol = HengbotPolicy()
        pol._town_visit_ledger.blocked_stores.update(
            {STORE_MAGIC, STORE_HOME}
        )
        pol._town_visit_ledger.approach_fails.update(
            {STORE_MAGIC: 2, STORE_HOME: 3}
        )

        pol._rearm_town_store_for_new_work(STORE_MAGIC)
        pol._rearm_town_store_for_new_work(STORE_HOME)

        self.assertEqual(
            pol._town_visit_ledger.blocked_stores,
            {STORE_MAGIC, STORE_HOME},
        )
        self.assertEqual(
            pol._town_visit_ledger.approach_fails,
            Counter({STORE_HOME: 3, STORE_MAGIC: 2}),
        )

        pol._calibration_restore_signatures = [("restore", 1, 1)]
        pol._town_visit_ledger.need_attempts["calibration-restore"] = 2
        pol._rearm_town_store_for_new_work(
            STORE_HOME, release_visit_bound=True
        )

        self.assertNotIn(STORE_HOME, pol._town_visit_ledger.blocked_stores)
        self.assertNotIn(STORE_HOME, pol._town_visit_ledger.approach_fails)
        self.assertNotIn(
            "calibration-restore", pol._town_visit_ledger.need_attempts
        )
        self.assertIn(STORE_MAGIC, pol._town_visit_ledger.blocked_stores)

    def test_home_cleanup_preserves_departure_pack_space(self):
        carried = [self._staff(25)]
        carried.extend(
            item(
                chr(ord("a") + index),
                TVAL_FOOD,
                35,
                name=f"filler-{index}",
            )
            for index in range(PACK_CAPACITY - MIN_FREE_PACK_SLOTS - 1)
        )
        stored = store_item(
            "h", TVAL_STAFF, SV_STAFF_IDENTIFY,
            name="Staff of Identify", charges=3,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=carried,
            store=StoreState(STORE_HOME, [stored]),
        )
        pol = HengbotPolicy()
        pol._deepest_level = STAFF_IDENTIFY_MIN_DEPTH

        key = pol._shop(snap)

        self.assertNotEqual(key, "ph\r")
        self.assertFalse(pol._home_identify_staff_sale_pending)

    def test_home_staff_sale_does_not_buy_back_mana_food_same_visit(self):
        ware = store_item(
            "z", TVAL_STAFF, SV_STAFF_IDENTIFY,
            name="Staff of Identify", charges=12, price=100,
        )
        snap = Snapshot(
            player(
                10, 10, class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA, food=5000,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            store=StoreState(STORE_MAGIC, [ware]),
        )
        pol = HengbotPolicy()
        pol._home_identify_staff_sold_this_magic_visit = True

        self.assertIsNone(pol._mana_food_purchase(snap))

    def test_starving_mana_character_may_buy_after_home_staff_sale(self):
        ware = store_item(
            "z", TVAL_STAFF, SV_STAFF_IDENTIFY,
            name="Staff of Identify", charges=12, price=100,
        )
        snap = Snapshot(
            player(
                10, 10, class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA, food=1500,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            store=StoreState(STORE_MAGIC, [ware]),
        )
        pol = HengbotPolicy()
        pol._home_identify_staff_sold_this_magic_visit = True

        self.assertEqual(pol._mana_food_purchase(snap), ware)

    def _pressured_pack(self, *extra):
        # 18 aware wand filler + the extras = a nearly-full pack (<= free slots).
        filler = [
            item(chr(ord("a") + i), TVAL_WAND, i, name=f"filler-{i}")
            for i in range(PACK_CAPACITY - IDENTIFY_PRESSURE_FREE_SLOTS - len(extra))
        ]
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 12, 0),  # deep in the dungeon
            inventory=[*filler, *extra],
        )

    def test_pack_pressure_identifies_unknown_with_staff(self):
        staff = self._staff()
        unknown = item("t", TVAL_POTION, 3, aware=False, name="murky potion")
        snap = self._pressured_pack(staff, unknown)
        pol = HengbotPolicy()
        # Original-keyset use-staff u + staff slot s + target slot t.
        self.assertEqual(pol._pack_pressure_identify_key(snap), "ust")
        self.assertEqual(pol.last_reason, "identify:pack-pressure")

    def test_pack_pressure_identifies_aware_but_unknown_equipment(self):
        # Awareness identifies the base kind (Leather Gloves), not the individual
        # item's bonuses. It still needs Identify before the bot can keep or shed it.
        staff = self._staff()
        gloves = item(
            "t", 31, 1, aware=True, known=False,
            is_equipment=True, name="Leather Gloves",
        )
        snap = self._pressured_pack(staff, gloves)

        pol = HengbotPolicy()
        self.assertEqual(pol._pack_pressure_identify_key(snap), "ust")
        self.assertEqual(pol.last_reason, "identify:pack-pressure")

    def test_pack_pressure_skips_ammunition_and_identifies_real_equipment(self):
        staff = self._staff()
        arrows = item(
            "t", TVAL_ARROW, 1, count=20, aware=False, known=False,
            is_equipment=True, name="Arrows",
        )
        gloves = item(
            "u", 31, 1, aware=True, known=False,
            is_equipment=True, name="Leather Gloves",
        )
        snap = self._pressured_pack(staff, arrows, gloves)

        pol = HengbotPolicy()
        self.assertEqual(pol._pack_pressure_identify_key(snap), "usu")
        self.assertEqual(pol.last_reason, "identify:pack-pressure")

    def test_pack_pressure_does_not_identify_ammunition(self):
        staff = self._staff()
        arrows = item(
            "t", TVAL_ARROW, 1, count=20, aware=False, known=False,
            is_equipment=True, name="Arrows",
        )
        snap = self._pressured_pack(staff, arrows)

        self.assertIsNone(HengbotPolicy()._pack_pressure_identify_key(snap))

    def test_stalled_identify_abandons_target_after_retries(self):
        # If the identify never lands (unknown count stays put), the target is
        # abandoned after the retry budget instead of looping on it forever.
        staff = self._staff()
        unknown = item("t", TVAL_POTION, 3, aware=False, name="murky")
        snap = self._pressured_pack(staff, unknown)
        pol = HengbotPolicy()
        results = [pol._pack_pressure_identify_key(snap) for _ in range(IDENTIFY_FAIL_LIMIT + 2)]
        self.assertEqual(results[0], "ust")
        self.assertIsNone(results[-1])
        self.assertIn(pol._item_signature(unknown), pol._unidentifiable_sigs)

    def test_no_identify_when_pack_has_room(self):
        staff = self._staff()
        unknown = item("t", TVAL_POTION, 3, aware=False)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 12, 0),
            inventory=[staff, unknown],  # only 2 items → lots of free slots
        )
        self.assertIsNone(HengbotPolicy()._pack_pressure_identify_key(snap))

    def test_unidentified_mushroom_is_not_identified(self):
        # Food is shed rather than identified, so a mushroom is never the target.
        staff = self._staff()
        mushroom = item("t", TVAL_FOOD, 5, aware=False, name="mushroom")
        snap = self._pressured_pack(staff, mushroom)
        self.assertIsNone(HengbotPolicy()._pack_pressure_identify_key(snap))

    def test_drained_identify_staff_becomes_sellable(self):
        # A depleted Staff of Identify can no longer identify, so it stops being a
        # "useful device" and the Magic-shop device-sale offloads it; a charged
        # one is still kept.
        pol = HengbotPolicy()
        drained = item("s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=0, name="drained")
        self.assertFalse(pol._is_useful_device(drained))
        self.assertTrue(
            pol._is_useful_device(item("t", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=3))
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[drained],
        )
        sale = pol._find_device_sale(snap)
        self.assertIsNotNone(sale)
        self.assertEqual(sale.slot, "s")

    def test_identify_staffs_above_five_sell_lowest_charge_first(self):
        pol = HengbotPolicy()
        staffs = [
            item(
                chr(ord("a") + index),
                TVAL_STAFF,
                SV_STAFF_IDENTIFY,
                charges=charges,
                name="Staff of Identify",
            )
            for index, charges in enumerate([20, 18, 16, 14, 12, 3])
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=staffs,
        )

        self.assertEqual(STAFF_IDENTIFY_MAX_COUNT, 5)
        self.assertEqual(pol._find_device_sale(snap).slot, "f")
        self.assertIsNone(pol._find_device_sale(replace(snap, inventory=staffs[:5])))

    def test_stacked_identify_staff_count_is_capped(self):
        pol = HengbotPolicy()
        stack = item(
            "s",
            TVAL_STAFF,
            SV_STAFF_IDENTIFY,
            count=6,
            charges=60,
            name="Staff of Identify",
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[stack, replace(self._staff(100), slot="t")],
        )

        self.assertEqual(pol._find_device_sale(snap).slot, "s")

    def test_mana_food_reserve_keeps_highest_charge_identify_staff(self):
        pol = HengbotPolicy()
        staffs = [
            item(
                chr(ord("a") + index),
                TVAL_STAFF,
                SV_STAFF_IDENTIFY,
                charges=charges,
                name="Staff of Identify",
            )
            for index, charges in enumerate([30, 20, 18, 16, 14, 2])
        ]
        snap = Snapshot(
            player(
                10,
                10,
                class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=staffs,
        )

        self.assertEqual(pol._device_food_reserve_slot(snap), "a")
        self.assertEqual(pol._find_device_sale(snap).slot, "f")

    def test_pending_home_sale_rechecks_captured_mana_food_obligations(self):
        # 01:58 capture: six edible charges existed before the freshly purchased
        # 18-charge Identify staff arrived; Identify was 0/20 and food was 6/15.
        filler = item("a", TVAL_WAND, 1, charges=6, name="filler")
        purchased = item(
            "b", TVAL_STAFF, SV_STAFF_IDENTIFY,
            charges=18, name="Staff of Identify",
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)}, [], inventory=[filler, purchased],
        )
        pol = HengbotPolicy()
        pol._home_identify_staff_sale_pending = True
        pol._town_visit_purchases.add(pol._item_signature(purchased))

        self.assertEqual(pol._count_mana_food_uses(replace(snap, inventory=[filler])), 6)
        self.assertEqual(pol._total_identify_staff_charges(replace(snap, inventory=[filler])), 0)
        self.assertIsNone(pol._find_device_sale(snap))

    def test_same_visit_identify_purchase_is_never_a_sale_candidate(self):
        staffs = [
            item(chr(97 + index), TVAL_STAFF, SV_STAFF_IDENTIFY,
                 charges=30, name="Staff of Identify")
            for index in range(6)
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=staffs,
        )
        pol = HengbotPolicy()
        pol._town_visit_purchases.add(pol._item_signature(staffs[-1]))

        self.assertIsNone(pol._find_surplus_identify_staff(snap))

    def test_identify_staff_sale_honours_all_obligations_and_allows_true_surplus(self):
        def mana_snapshot(charges):
            staffs = [
                item(chr(97 + index), TVAL_STAFF, SV_STAFF_IDENTIFY,
                     charges=value, name="Staff of Identify")
                for index, value in enumerate(charges)
            ]
            return Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food_type=FOOD_TYPE_MANA),
                {Position(10, 10): grid(10, 10)}, [], inventory=staffs,
            )

        pol = HengbotPolicy()
        below_identify_and_food = mana_snapshot([3] * 6)
        self.assertEqual(pol._total_identify_staff_charges(below_identify_and_food), 18)
        self.assertEqual(pol._count_mana_food_uses(below_identify_and_food), 13)
        self.assertIsNone(pol._find_surplus_identify_staff(below_identify_and_food))

        five_devices = item(
            "a", TVAL_STAFF, SV_STAFF_IDENTIFY,
            count=5, charges=1, name="Staff of Identify",
        )
        sole_device = item(
            "b", TVAL_STAFF, SV_STAFF_IDENTIFY,
            charges=40, name="Staff of Identify",
        )
        device_bound = replace(
            mana_snapshot([]), inventory=[five_devices, sole_device]
        )
        self.assertIsNone(pol._find_surplus_identify_staff(device_bound))

        surplus = mana_snapshot([30, 30, 30, 30, 30, 1])
        self.assertEqual(pol._find_surplus_identify_staff(surplus).slot, "f")
        with patch.object(pol, "_retention_surplus", return_value=0):
            self.assertIsNone(pol._find_surplus_identify_staff(surplus))

    def test_mana_food_purchase_caps_identify_slots_with_survival_exception(self):
        identify = store_item(
            "i", TVAL_STAFF, SV_STAFF_IDENTIFY,
            name="Staff of Identify", charges=18, pval=18, price=100,
        )
        wand = store_item("w", TVAL_WAND, 1, name="wand", charges=8, pval=8, price=100)
        carried = [
            item("a", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=2, name="Identify"),
            item("b", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=3, name="Identify"),
        ]
        base = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)}, [], inventory=carried,
            store=StoreState(STORE_MAGIC, [identify, wand]),
        )
        pol = HengbotPolicy()

        self.assertEqual(pol._mana_food_purchase(base), wand)
        identify_only = replace(base, store=StoreState(STORE_MAGIC, [identify]))
        self.assertIsNone(pol._mana_food_purchase(identify_only))
        weak = replace(
            identify_only,
            player=player(
                10, 10, class_id=PLAYER_CLASS_WARRIOR,
                food_type=FOOD_TYPE_MANA, food=750,
            ),
        )
        self.assertEqual(pol._mana_food_purchase(weak), identify)

    def test_no_identify_in_town(self):
        # Town has its own identify errands; the pressure path is dungeon-only.
        staff = self._staff()
        unknown = item("t", TVAL_POTION, 3, aware=False)
        filler = [
            item(chr(ord("a") + i), TVAL_WAND, i)
            for i in range(PACK_CAPACITY - IDENTIFY_PRESSURE_FREE_SLOTS - 2)
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*filler, staff, unknown],
        )
        self.assertIsNone(HengbotPolicy()._pack_pressure_identify_key(snap))

class StatGainTest(unittest.TestCase):
    """Permanent stat-gain potions (Strength ... Augmentation) are drunk on sight."""

    def _snap(self, inventory, hostiles=()):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            list(hostiles),
            floor_key=(DUNGEON_YEEK_CAVE, 3, 0),
            inventory=list(inventory),
        )

    def test_quaffs_a_strength_potion_on_sight(self):
        inv = [item("k", TVAL_POTION, SV_POTION_INC_STR, name="Strength")]
        pol = HengbotPolicy()
        self.assertEqual(pol._stat_gain_quaff_key(self._snap(inv), []), "qk")
        self.assertEqual(pol.last_reason, "stat-gain:quaff")

    def test_quaffs_augmentation(self):
        inv = [item("k", TVAL_POTION, SV_POTION_AUGMENTATION)]
        self.assertEqual(HengbotPolicy()._stat_gain_quaff_key(self._snap(inv), []), "qk")

    def test_no_quaff_with_hostiles(self):
        inv = [item("k", TVAL_POTION, SV_POTION_INC_STR)]
        h = MonsterState(index=1, position=Position(9, 10), hp=5, max_hp=5, distance=1,
                         friendly=False, pet=False, speed=110)
        self.assertIsNone(HengbotPolicy()._stat_gain_quaff_key(self._snap(inv, [h]), [h]))

    def test_ignores_unaware_gain_potion(self):
        inv = [item("k", TVAL_POTION, SV_POTION_INC_STR, aware=False)]
        self.assertIsNone(HengbotPolicy()._stat_gain_quaff_key(self._snap(inv), []))

    def test_gain_potion_is_drunk_through_the_full_decision(self):
        inv = [item("k", TVAL_POTION, SV_POTION_INC_STR)]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(self._snap(inv)), "qk")
        self.assertEqual(pol.last_reason, "stat-gain:quaff")

class DeepKitTest(unittest.TestCase):
    """10F+ departure kit and teleport-return strategy: carry 15 teleport scrolls
    and >=20 total identify charges, and head home only at the low teleport
    reserve (3) rather than the moment the big buffer dips."""

    def _pol(self, deepest):
        pol = HengbotPolicy()
        pol._deepest_level = deepest
        return pol

    def _dungeon(self, level, inventory):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, level, 0),
            inventory=inventory,
        )

    def _tp(self, count):
        return [item("t", TVAL_SCROLL, 9, count=count)]  # teleport sval 9

    def test_teleport_target_scales_with_depth(self):
        snap = self._dungeon(1, [])
        self.assertEqual(self._pol(3)._teleport_target(snap), 3)     # planned 4
        self.assertEqual(self._pol(10)._teleport_target(snap), 15)   # planned 11

    def test_deep_teleport_ready_needs_fifteen(self):
        pol = self._pol(10)
        self.assertFalse(pol._teleport_ready(self._dungeon(11, self._tp(10))))
        self.assertTrue(pol._teleport_ready(self._dungeon(11, self._tp(15))))

    def test_deep_return_only_at_low_reserve(self):
        pol = self._pol(10)
        # below the 15 target but above the reserve -> keep exploring, do not thrash
        stocked = self._dungeon(11, self._tp(10))
        low = self._dungeon(11, self._tp(3))
        stocked_teleport = pol._supply_ledger(stocked, stocked.dungeon_level)["teleport"]
        low_teleport = pol._supply_ledger(low, low.dungeon_level)["teleport"]
        self.assertFalse(pol._ledger_return_shortages(
            {"teleport": stocked_teleport}, stocked.dungeon_level
        ))
        self.assertTrue(pol._ledger_return_shortages(
            {"teleport": low_teleport}, low.dungeon_level
        ))

    def test_shallow_return_uses_plain_below_target(self):
        pol = self._pol(3)  # planned 4, target 3
        low = self._dungeon(4, self._tp(2))
        stocked = self._dungeon(4, self._tp(3))
        low_teleport = pol._supply_ledger(low, low.dungeon_level)["teleport"]
        stocked_teleport = pol._supply_ledger(stocked, stocked.dungeon_level)["teleport"]
        self.assertTrue(pol._ledger_return_shortages(
            {"teleport": low_teleport}, low.dungeon_level
        ))
        self.assertFalse(pol._ledger_return_shortages(
            {"teleport": stocked_teleport}, stocked.dungeon_level
        ))

    def test_deep_staff_needs_twenty_total_charges(self):
        pol = self._pol(10)
        one = [item("n", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=12)]
        two = [
            item("n", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=12),
            item("m", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=10),
        ]
        self.assertFalse(pol._identify_staff_ready(self._dungeon(11, one)))  # 12 < 20
        self.assertTrue(pol._identify_staff_ready(self._dungeon(11, two)))   # 22 >= 20
        self.assertEqual(pol._total_identify_staff_charges(self._dungeon(11, two)), 22)

class SupplyLedgerInvariantTest(unittest.TestCase):
    def _snapshot(self, depth, inventory=(), *, gold=500, store=None):
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, depth, 0),
            inventory=list(inventory),
            equipment=[item("L", TVAL_LITE, SV_LITE_LANTERN, fuel=7000)],
            store=store,
        )

    def test_ledger_threshold_bands_and_store_map(self):
        policy = HengbotPolicy()
        shallow = policy._supply_ledger(self._snapshot(4), 4)
        deep = policy._supply_ledger(self._snapshot(11), 11)
        self.assertEqual(shallow["teleport"].required_return, 3)
        self.assertEqual(deep["teleport"].required_return, 4)
        self.assertEqual(deep["teleport"].required_departure, 15)
        self.assertEqual(deep["cure"].required_departure, 10)
        self.assertEqual(shallow["recall"].stores, (STORE_TEMPLE, STORE_ALCHEMIST))
        self.assertEqual(shallow["food"].stores, (STORE_GENERAL,))

    def test_incident_refill_is_charged_before_oil_departure_accounting(self):
        fixture = Path("tests/fixtures/oil_remove_curse_carousel_20260718.jsonl")
        incident = fixture.read_text(encoding="utf-8")
        self.assertIn('"reason": "shop:buy-oil"', incident)
        self.assertIn('"reason": "refill-light"', incident)
        self.assertIn('"reason": "town:wait-restock"', incident)

        policy = HengbotPolicy()
        policy._deepest_level = 1
        low_lantern = replace(
            self._snapshot(0, [
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
                item("f", TVAL_FOOD, 35, count=5),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            ]),
            floor_key=(0, 0, 0), town_flag=True,
            equipment=[item("L", TVAL_LITE, SV_LITE_LANTERN, fuel=1000, known=True)],
        )
        status = policy._supply_ledger(low_lantern, policy._planned_depth())["oil"]
        self.assertEqual(status.count, 4)
        requirements = {
            entry["item"]: entry for entry in policy.procurement_requirements(low_lantern)
        }
        self.assertEqual(requirements["Flasks of oil"]["missing"], 1)
        self.assertIn(
            TownNeed(STORE_GENERAL, "oil", "normal"),
            policy._enumerate_town_needs(low_lantern),
        )

        policy._last_return_trigger = "recall-low"
        policy._break_town_cycle(low_lantern)
        self.assertFalse(policy._town_restock_suppressed)
        self.assertNotIn(STORE_GENERAL, policy._town_store_attempted)

    def test_every_departure_threshold_exceeds_return_threshold(self):
        for kind, phases in SUPPLY_THRESHOLDS.items():
            band_starts = sorted({
                depth for bands in phases.values() for depth, _value in bands
            })
            for depth in band_starts:
                with self.subTest(kind=kind, depth=depth):
                    required_return = HengbotPolicy._supply_threshold(
                        kind, "return", depth
                    )
                    required_departure = HengbotPolicy._supply_threshold(
                        kind, "departure", depth
                    )
                    self.assertGreater(required_departure, required_return)

    def test_corrected_recall_stock_does_not_latch_return_on_5f_arrival(self):
        policy = HengbotPolicy()
        policy._deepest_level = RECALL_MIN_DEPTH
        arrival = self._snapshot(RECALL_MIN_DEPTH, [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5),
        ])

        ledger = policy._supply_ledger(arrival, arrival.dungeon_level)
        self.assertEqual(ledger["recall"].required_departure, 6)
        self.assertFalse(policy._ledger_return_shortages(ledger, arrival.dungeon_level))
        self.assertFalse(policy._should_start_town_return(arrival))
        self.assertNotEqual(policy._last_return_trigger, "recall-low")

    def test_obtainable_uses_latch_live_stock_and_affordability(self):
        policy = HengbotPolicy()
        shelf = StoreState(
            store_type=STORE_ALCHEMIST,
            items=[store_item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, price=60)],
        )
        self.assertTrue(policy._supply_ledger(self._snapshot(4, store=shelf), 4)["teleport"].obtainable)
        unaffordable = self._snapshot(4, gold=10, store=shelf)
        self.assertTrue(
            policy._supply_ledger(unaffordable, 4)["teleport"].obtainable
        )
        policy._town_store_attempted[STORE_ALCHEMIST] = unaffordable.turn
        self.assertFalse(
            policy._supply_ledger(unaffordable, 4)["teleport"].obtainable
        )
        empty = replace(self._snapshot(4, store=shelf), store=replace(shelf, items=[]))
        self.assertFalse(policy._supply_ledger(empty, 4)["teleport"].obtainable)
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        self.assertFalse(policy._supply_ledger(self._snapshot(4), 4)["teleport"].obtainable)

    def test_empty_current_supplier_keeps_unchecked_alternative_obtainable(self):
        policy = HengbotPolicy()
        alchemist = StoreState(store_type=STORE_ALCHEMIST, items=[])
        snapshot = self._snapshot(4, store=alchemist)

        self.assertTrue(policy._supply_ledger(snapshot, 4)["recall"].obtainable)
        needs = policy._enumerate_town_needs(replace(snapshot, town_flag=True))
        self.assertIn(TownNeed(STORE_TEMPLE, "recall", "normal"), needs)

    def test_teleport_uses_planned_depth_at_nine_ten_boundary(self):
        policy = HengbotPolicy()
        policy._deepest_level = STAFF_IDENTIFY_MIN_DEPTH - 1
        floor_nine = self._snapshot(STAFF_IDENTIFY_MIN_DEPTH - 1)

        status = policy._supply_ledger(floor_nine, floor_nine.dungeon_level)["teleport"]
        self.assertEqual(status.required_return, TELEPORT_RETURN_THRESHOLD + 1)
        self.assertEqual(status.required_departure, TELEPORT_SCROLL_DEEP_TARGET)

    def test_unobtainable_shallow_teleport_departs_without_return_bounce(self):
        supplies = [
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=4),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=4),
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5),
        ]
        policy = HengbotPolicy()
        policy._deepest_level = 3
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        dungeon = self._snapshot(4, supplies)
        ledger = policy._supply_ledger(dungeon, dungeon.dungeon_level)
        self.assertFalse(policy._ledger_return_shortages(ledger, dungeon.dungeon_level))
        self.assertFalse(policy._should_start_town_return(dungeon))
        town = replace(dungeon, floor_key=(0, 0, 0), town_flag=True)
        self.assertTrue(policy._ledger_departure_shortages(policy._supply_ledger(town, 4)) == [])

    def test_obtainable_teleport_is_purchased_before_departure(self):
        policy = HengbotPolicy()
        policy._deepest_level = 3
        policy._equipment_catalog.home_scan_complete = True
        town = replace(
            self._snapshot(0, [
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=4),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=3),
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5),
            ]),
            town_flag=True,
        )
        ledger = policy._supply_ledger(town, 4)
        self.assertIn("teleport", [s.kind for s in policy._ledger_departure_shortages(ledger)])
        self.assertIn(
            TownNeed(STORE_ALCHEMIST, "teleport", "normal"),
            policy._enumerate_town_needs(town),
        )
        self.assertTrue(policy._descent_is_blocked(town))

    def test_deep_unobtainable_teleport_still_returns(self):
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        dungeon = self._snapshot(11, [item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3)])
        ledger = policy._supply_ledger(dungeon, dungeon.dungeon_level)
        self.assertTrue(policy._ledger_return_shortages(ledger, dungeon.dungeon_level))

    def test_next_depth_uses_return_threshold_not_departure_target(self):
        policy = HengbotPolicy()
        policy._deepest_level = 12
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        enough = self._snapshot(12, [
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=5),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=2),
        ])
        low = replace(enough, inventory=[
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=2),
        ])

        self.assertFalse(policy._next_depth_supply_shortage(enough))
        self.assertTrue(policy._next_depth_supply_shortage(low))

    def test_mana_food_purchase_restores_device_redundancy(self):
        policy = HengbotPolicy()
        staff = store_item("s", TVAL_STAFF, 1, price=100, pval=20, count=10)
        town = replace(
            self._snapshot(0, gold=1000, store=StoreState(STORE_MAGIC, [staff])),
            player=replace(
                self._snapshot(0).player, gold=1000, food_type=FOOD_TYPE_MANA
            ),
            town_flag=True,
        )

        self.assertEqual(policy._purchase_quantity(town, staff), 2)

    def test_cycle_break_pins_every_obtainable_supply_supplier(self):
        policy = HengbotPolicy()
        policy._last_return_trigger = "teleport-low"
        town = replace(self._snapshot(0), town_flag=True)
        policy._break_town_cycle(town)
        self.assertIsNotNone(policy._town_errand_plan)
        self.assertIn(STORE_ALCHEMIST, policy._town_errand_plan.stops)
        self.assertIn(STORE_GENERAL, policy._town_errand_plan.stops)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

class QuestCarryVisitAbandonmentTest(unittest.TestCase):
    FORCE = {
        "launcher": {"ammo": "equipped", "equipped": True},
        "throwing_items": {"launcher_ammo": 45},
    }

    def _town(self, *, inventory=(), store=None, gold=11525, turn=495945):
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=turn,
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            store=store,
        )

    def _q2_policy(self):
        knowledge = load_quest_knowledge(REAL_QUEST_DEFINITIONS)
        return HengbotPolicy(
            quest_strategies=load_quest_strategies(Path("strategy/quests")),
            quest_knowledge={2: knowledge[2]},
        )

    def _q2_town(self, *, store=None, gold=11887, turn=495945):
        return replace(
            self._town(store=store, gold=gold, turn=turn),
            player=replace(
                self._town().player,
                level=10,
                gold=gold,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            equipment=[item(
                "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True
            )],
            quests={
                2: QuestState(2, status=QUEST_STATUS_UNTAKEN, fixed=True)
            },
        )

    def _q1_policy_and_town(self):
        knowledge = load_quest_knowledge(REAL_QUEST_DEFINITIONS)
        policy = HengbotPolicy(
            quest_strategies=load_quest_strategies(Path("strategy/quests")),
            quest_knowledge={1: knowledge[1]},
        )
        town = replace(
            self._town(gold=11887),
            player=replace(
                self._town().player,
                level=5,
                gold=11887,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            quests={
                1: QuestState(1, status=QUEST_STATUS_UNTAKEN, fixed=True)
            },
        )
        return policy, town

    def test_exhausted_incident_quest_carry_is_abandoned_for_departure(self):
        policy = HengbotPolicy()
        profile = SimpleNamespace(required_force=self.FORCE, engagement_plan={})
        town = self._town()
        policy._town_store_attempted[STORE_WEAPON] = town.turn

        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            needs = policy._enumerate_town_needs(town)
            requirements = policy.procurement_requirements(town)

        items = {row["item"] for row in requirements}
        self.assertNotIn("Quest launcher", items)
        self.assertNotIn("Quest launcher ammunition", items)
        self.assertNotIn(
            TownNeed(STORE_WEAPON, "quest-ranged-kit", "normal"), needs
        )
        self.assertEqual(
            policy._abandoned_quest_carry_requirements,
            {
                "launcher": "all-suppliers-visited-without-affordable-stock",
                "throwing_items.launcher_ammo":
                    "all-suppliers-visited-without-affordable-stock",
            },
        )
        self.assertNotEqual(policy.last_reason, "town:blocked:repetition")

    def test_affordable_in_stock_quest_carry_is_still_purchased(self):
        sling = store_item("a", TVAL_BOW, SV_BOW_SLING, price=300)
        town = self._town(store=StoreState(STORE_WEAPON, [sling]))
        policy = HengbotPolicy()
        profile = SimpleNamespace(required_force=self.FORCE, engagement_plan={})

        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            policy.procurement_requirements(town)
            purchase = policy._quest_carry_purchase(town, profile)

        self.assertNotIn("launcher", policy._abandoned_quest_carry_requirements)
        self.assertIs(purchase, sling)

    def test_procurement_telemetry_does_not_mutate_abandonment_latch(self):
        policy = HengbotPolicy()
        profile = SimpleNamespace(required_force=self.FORCE, engagement_plan={})
        town = self._town()
        policy._town_store_attempted[STORE_WEAPON] = town.turn

        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            policy.procurement_requirements(town)

        self.assertFalse(policy._abandoned_quest_carry_requirements)

    def test_remembered_affordable_torch_prevents_false_abandonment(self):
        force = {"throwing_items": {"lit_torch": 5}}
        profile = SimpleNamespace(required_force=force, engagement_plan={})
        torch = store_item("a", TVAL_LITE, SV_LITE_TORCH, price=3)
        town = self._town(gold=9869)
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_GENERAL] = town.turn
        policy._town_supplier_stock[STORE_GENERAL] = StoreState(
            STORE_GENERAL, [torch]
        )

        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            policy._enumerate_town_needs(town)

        self.assertNotIn(
            "throwing_items.lit_torch",
            policy._abandoned_quest_carry_requirements,
        )

    def test_attempted_general_with_remembered_affordable_oil_keeps_claim(self):
        oil = store_item("a", TVAL_FLASK, SV_FLASK_OIL, price=4)
        town = replace(self._town(
            gold=9869,
            inventory=[item("o", TVAL_FLASK, SV_FLASK_OIL, count=2)],
        ), equipment=[item(
            "light", TVAL_LITE, SV_LITE_LANTERN, name="Brass Lantern",
            fuel=1, known=True, is_equipment=True,
        )])
        policy = HengbotPolicy()
        policy._deepest_level = 2
        policy._town_store_attempted[STORE_GENERAL] = town.turn
        policy._town_supplier_stock[STORE_GENERAL] = StoreState(
            STORE_GENERAL, [oil]
        )

        claims = policy._enumerate_live_store_claims(town)

        self.assertIn(
            TownNeed(STORE_GENERAL, "oil", "normal"), claims,
            policy._supply_ledger(town, policy._planned_depth())["oil"],
        )

    def test_pin_vacuity_public_visit_refusal_preserves_observed_supplier(self):
        bolts = store_item("a", TVAL_BOLT, 0, count=99, price=3)
        outside = replace(
            self._q2_town(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_WEAPON
                ),
                Position(20, 20): replace(
                    grid(20, 20), store_number=STORE_HOME
                ),
            },
        )
        policy = self._q2_policy()
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

        policy.choose_key(outside)
        self.assertEqual(
            policy._shop_selector_diagnostics["composition_refusal"],
            "shop:home-first-yields-to-current-visit",
        )
        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON],
            need_categories={STORE_WEAPON: ("quest-ranged-kit",)},
        )
        inside = replace(
            outside,
            turn=outside.turn + 1,
            store=StoreState(STORE_WEAPON, [bolts]),
        )
        policy.choose_key(inside)

        self.assertNotIn(STORE_WEAPON, policy._town_store_attempted)
        self.assertEqual(policy._town_errand_plan.index, 0)

    def test_public_leaving_pass_latches_store_with_no_wanted_stock(self):
        bolts = store_item("a", TVAL_BOLT, 0, count=99, price=3)
        outside = replace(
            self._q2_town(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_WEAPON
                ),
                Position(20, 20): replace(
                    grid(20, 20), store_number=STORE_HOME
                ),
            },
        )
        policy = self._q2_policy()
        policy._home_knowledge_current = False
        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON],
            need_categories={STORE_WEAPON: ("quest-ranged-kit",)},
        )
        policy._store_visit = StoreVisit(
            "town-errand", "shopping", STORE_WEAPON,
            phase=StoreVisitPhase.LEAVING,
        )
        policy._shop_observation = (
            StoreState(STORE_WEAPON, [bolts], page_top=0),
            policy._decision_sequence,
        )
        policy.choose_key(outside)
        self.assertEqual(
            policy._shop_selector_diagnostics["composition_refusal"],
            "shop:home-first-yields-to-current-visit",
        )

        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON],
            need_categories={STORE_WEAPON: ("quest-ranged-kit",)},
        )
        inside = replace(
            outside,
            turn=outside.turn + 1,
            store=StoreState(STORE_WEAPON, []),
        )
        policy.choose_key(inside)

        self.assertIn(STORE_WEAPON, policy._town_store_attempted)
        self.assertIn(STORE_WEAPON, policy._town_errand_plan.blocked_this_visit)
        self.assertEqual(policy._town_errand_plan.index, 1)

    def test_public_leaving_pass_latches_when_home_gate_allows_purchase(self):
        bolts = store_item("a", TVAL_BOLT, 0, count=99, price=3)
        outside = replace(
            self._q2_town(),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_WEAPON
                ),
                Position(20, 20): replace(
                    grid(20, 20), store_number=STORE_HOME
                ),
            },
        )
        policy = self._q2_policy()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = []
        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON],
            need_categories={STORE_WEAPON: ("quest-ranged-kit",)},
        )
        policy._store_visit = StoreVisit(
            "town-errand", "shopping", STORE_WEAPON,
            phase=StoreVisitPhase.LEAVING,
        )
        policy._shop_observation = (
            StoreState(STORE_WEAPON, [bolts], page_top=1),
            policy._decision_sequence,
        )
        inside = replace(
            outside,
            turn=outside.turn + 1,
            store=StoreState(STORE_WEAPON, [bolts]),
        )
        policy.choose_key(inside)

        self.assertIn(STORE_WEAPON, policy._town_store_attempted)
        self.assertIn(STORE_WEAPON, policy._town_errand_plan.blocked_this_visit)
        self.assertEqual(policy._town_errand_plan.index, 1)

    def test_pin_vacuity_remembered_bolts_restore_real_ranged_claim(self):
        bolts = store_item("a", TVAL_BOLT, 0, count=99, price=3)
        town = self._q2_town()
        policy = self._q2_policy()
        profile = policy._carry_procurement_strategy(town)
        self.assertIsNotNone(profile)
        policy._town_store_attempted[STORE_WEAPON] = town.turn
        policy._town_supplier_stock[STORE_WEAPON] = StoreState(
            STORE_WEAPON, [bolts]
        )

        policy.consume_home_knowledge(())
        active = policy._town_claims_active(town)
        supply = policy._quest_carry_obtainability(
            town,
            profile,
            "throwing_items.launcher_ammo",
            policy._quest_carry_status(town, profile.required_force)[
                "throwing_items.launcher_ammo"
            ],
        )

        self.assertTrue(supply.obtainable)
        self.assertTrue(active)
        self.assertIn("quest-ranged-kit", policy._town_claim_categories)
        self.assertNotEqual(
            policy._town_blocked_reason, "departure-unsatisfiable"
        )

    def test_sibling_claims_match_remembered_affordable_obtainability(self):
        cases = (
            (
                "throwing_items.lit_torch",
                STORE_GENERAL,
                store_item("a", TVAL_LITE, SV_LITE_TORCH, price=3),
                "quest-throwing-items",
            ),
            (
                "required_scrolls.light",
                STORE_ALCHEMIST,
                store_item("a", TVAL_SCROLL, SV_SCROLL_LIGHT, price=20),
                "quest-scrolls",
            ),
            (
                "required_scrolls.teleport",
                STORE_ALCHEMIST,
                store_item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT, price=40),
                "quest-scrolls",
            ),
            (
                "utility_tools.wall_breach",
                STORE_BLACK,
                store_item(
                    "a", TVAL_WAND, SV_WAND_STONE_TO_MUD,
                    price=500, charges=1,
                ),
                "quest-wall-breach",
            ),
            (
                "utility_tools.wall_breach",
                STORE_GENERAL,
                store_item(
                    "a", TVAL_WAND, SV_WAND_STONE_TO_MUD,
                    price=500, charges=1,
                ),
                "quest-wall-breach",
            ),
        )
        town = self._q2_town()
        for name, supplier, stock, category in cases:
            with self.subTest(name=name):
                case_town = town
                if name == "throwing_items.lit_torch":
                    policy, case_town = self._q1_policy_and_town()
                else:
                    policy = self._q2_policy()
                strategy = policy._carry_procurement_strategy(case_town)
                self.assertIsNotNone(strategy)
                for attempted in policy._quest_carry_suppliers(name):
                    policy._town_store_attempted[attempted] = case_town.turn
                policy._town_supplier_stock[supplier] = StoreState(
                    supplier, [stock]
                )

                status = policy._quest_carry_status(
                    case_town, strategy.required_force
                )[name]
                supply = policy._quest_carry_obtainability(
                    case_town, strategy, name, status
                )
                needs = policy._enumerate_town_needs(case_town)

                self.assertTrue(supply.obtainable)
                self.assertIn(TownNeed(supplier, category, "normal"), needs)
                self.assertNotIn(
                    name, policy._abandoned_quest_carry_requirements
                )

    def test_pin_vacuity_black_wall_breach_stock_restores_black_claim_only(self):
        town = self._q2_town()
        policy = self._q2_policy()
        strategy = policy._carry_procurement_strategy(town)
        self.assertIsNotNone(strategy)
        policy._town_store_attempted[STORE_BLACK] = town.turn
        policy._town_store_attempted[STORE_GENERAL] = town.turn
        policy._town_supplier_stock[STORE_BLACK] = StoreState(
            STORE_BLACK,
            [store_item(
                "a", TVAL_WAND, SV_WAND_STONE_TO_MUD,
                price=500, charges=1,
            )],
        )

        needs = policy._enumerate_town_needs(town)

        self.assertIn(TownNeed(STORE_BLACK, "quest-wall-breach", "normal"), needs)
        self.assertNotIn(
            TownNeed(STORE_GENERAL, "quest-wall-breach", "normal"), needs
        )

    def test_sibling_claims_abandon_when_no_affordable_stock_is_remembered(self):
        names = (
            "throwing_items.lit_torch",
            "required_scrolls.light",
            "required_scrolls.teleport",
            "utility_tools.wall_breach",
        )
        town = self._q2_town()
        for name in names:
            with self.subTest(name=name):
                case_town = town
                if name == "throwing_items.lit_torch":
                    policy, case_town = self._q1_policy_and_town()
                else:
                    policy = self._q2_policy()
                strategy = policy._carry_procurement_strategy(case_town)
                self.assertIsNotNone(strategy)
                for supplier in policy._quest_carry_suppliers(name):
                    policy._town_store_attempted[supplier] = case_town.turn

                status = policy._quest_carry_status(
                    case_town, strategy.required_force
                )[name]
                supply = policy._quest_carry_obtainability(
                    case_town, strategy, name, status
                )
                needs = policy._enumerate_town_needs(case_town)

                self.assertFalse(supply.obtainable)
                self.assertEqual(
                    policy._abandoned_quest_carry_requirements[name],
                    "all-suppliers-visited-without-affordable-stock",
                )
                self.assertFalse(any(
                    need.store_type in policy._quest_carry_suppliers(name)
                    and need.category.startswith("quest-")
                    for need in needs
                ))

    def test_healthy_cure_critical_one_shot_still_composes(self):
        cure = store_item(
            "a", TVAL_POTION, SV_POTION_CURE_CRITICAL, price=1650
        )
        town = replace(
            self._town(gold=11887),
            grids={
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_TEMPLE
                )
            },
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge(())
        policy._shopping_approach_store_type = STORE_TEMPLE
        policy._shop_observation = (
            StoreState(STORE_TEMPLE, [cure], page_top=0),
            policy._decision_sequence,
        )

        key = policy._atomic_shop_transaction_key(town)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")
        self.assertEqual(policy._store_visit.operation_key, "pa\r\x1b")
        self.assertEqual(
            policy._town_visit_ledger.pending_store_transaction,
            (STORE_TEMPLE, policy._decision_sequence),
        )

    def test_unattempted_remembered_unaffordable_oil_keeps_claim(self):
        oil = store_item("a", TVAL_FLASK, SV_FLASK_OIL, price=400)
        town = replace(
            self._town(
                gold=3,
                inventory=[item("o", TVAL_FLASK, SV_FLASK_OIL, count=2)],
            ),
            equipment=[item(
                "light", TVAL_LITE, SV_LITE_LANTERN,
                name="Brass Lantern", fuel=1, known=True, is_equipment=True,
            )],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 2
        policy._town_supplier_stock[STORE_GENERAL] = StoreState(
            STORE_GENERAL, [oil]
        )

        claims = policy._enumerate_live_store_claims(town)

        self.assertIn(TownNeed(STORE_GENERAL, "oil", "normal"), claims)
        oil_requirement = next(
            row for row in policy.procurement_requirements(town)
            if row["item"] == "Flasks of oil"
        )
        self.assertNotIn("blocked_reason", oil_requirement)

        policy._town_store_attempted[STORE_GENERAL] = town.turn
        attempted_requirement = next(
            row for row in policy.procurement_requirements(town)
            if row["item"] == "Flasks of oil"
        )
        self.assertEqual(
            attempted_requirement["blocked_reason"],
            "no-actionable-supplier",
        )

    def test_home_supply_is_first_in_supply_status_stores(self):
        town = self._town(
            inventory=[item("o", TVAL_FLASK, SV_FLASK_OIL, count=2)]
        )
        policy = HengbotPolicy()
        policy._deepest_level = 2
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [
            item("h", TVAL_FLASK, SV_FLASK_OIL, count=3)
        ]

        status = policy._supply_ledger(town, policy._planned_depth())["oil"]

        self.assertEqual(status.stores[0], STORE_HOME)
        self.assertIn(STORE_GENERAL, status.stores)

    def test_attempted_alchemist_keeps_one_post_alchemist_home_claim(self):
        town = self._town()
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_ALCHEMIST] = town.turn
        policy._home_candidate_waiting = True
        policy._identification_need = "normal"
        expected = TownNeed(
            STORE_HOME, "identification-withdrawal", "post-alchemist-home"
        )
        with patch.object(policy, "_home_available", return_value=True):
            candidates = policy._town_need_candidates(town)
            claims = policy._enumerate_live_store_claims(town)

        self.assertIn(expected, candidates)
        self.assertEqual(claims.count(expected), 1)

    def test_home_torch_withdrawal_owns_full_shortage(self):
        force = {"throwing_items": {"lit_torch": 5}}
        profile = SimpleNamespace(required_force=force, engagement_plan={})
        carried = item("t", TVAL_LITE, SV_LITE_TORCH, count=1, fuel=5000)
        home = item("a", TVAL_LITE, SV_LITE_TORCH, count=10, fuel=5000)
        town = self._town(inventory=[carried])
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [home]
        policy._home_scan_item_count = 1

        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            gate = policy._purchase_has_fresh_home_absence(
                town, store_item("a", TVAL_LITE, SV_LITE_TORCH, price=3)
            )

        self.assertEqual(gate, policy_module.ProcurementHomeGate.HOME_FIRST)
        self.assertEqual(policy._home_pending_quantity, 4)
        request = policy._derived_home_visit_request(town)
        self.assertEqual(request.quantity, 4)
        self.assertEqual(request.requester, "legacy-withdrawal")

    def test_home_torch_prevents_abandonment_and_preserves_queued_withdrawal(self):
        force = {"throwing_items": {"lit_torch": 5}}
        profile = SimpleNamespace(required_force=force, engagement_plan={})
        home = item("a", TVAL_LITE, SV_LITE_TORCH, count=10, fuel=5000)
        town = self._town()
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._home_knowledge_items = [home]
        existing = ("item", 20, 4)
        policy._home_scan_item_count = 1
        policy._home_pending_item = existing
        policy._home_pending_quantity = 1
        policy._town_store_attempted[STORE_GENERAL] = town.turn

        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            needs = policy._enumerate_live_store_claims(town)

        self.assertNotIn(
            "throwing_items.lit_torch",
            policy._abandoned_quest_carry_requirements,
        )
        self.assertIn(
            TownNeed(STORE_HOME, "quest-throwing-items", "home-first"), needs
        )
        self.assertEqual(policy._home_pending_item, existing)
        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            self.assertFalse(
                policy._town_departure_conjuncts(town)["quest_carry_ready"]
            )

    def test_abandonment_resets_when_the_next_town_visit_begins(self):
        policy = HengbotPolicy()
        policy._abandoned_quest_carry_requirements["launcher"] = "gone"
        policy._town_was_in_town = True
        dungeon = replace(
            self._town(turn=495946),
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            town_flag=False,
        )
        policy._observe(dungeon)
        policy._observe(self._town(turn=495947))

        self.assertFalse(policy._abandoned_quest_carry_requirements)

    def test_town_departure_names_and_enforces_quest_carry_gate(self):
        force = {"throwing_items": {"lit_torch": 5}}
        profile = SimpleNamespace(required_force=force, engagement_plan={})
        policy = HengbotPolicy()
        town = self._town(
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=1, fuel=5000)]
        )

        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            self.assertFalse(policy._town_departure_conjuncts(town)["quest_carry_ready"])
            met = replace(
                town,
                inventory=[
                    item("t", TVAL_LITE, SV_LITE_TORCH, count=5, fuel=5000)
                ],
            )
            self.assertTrue(policy._town_departure_conjuncts(met)["quest_carry_ready"])
            policy._abandoned_quest_carry_requirements[
                "throwing_items.lit_torch"
            ] = "all-suppliers-visited-without-affordable-stock"
            self.assertTrue(policy._town_departure_conjuncts(town)["quest_carry_ready"])
            policy._abandoned_quest_carry_requirements.clear()
            policy._fundraising_mode = "mine"
            self.assertTrue(policy._town_departure_conjuncts(town)["quest_carry_ready"])

    def test_level_shaped_torch_gate_survives_quest_one_acceptance(self):
        town = self._town(
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)]
        )
        for status in (
            QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN, QUEST_STATUS_COMPLETED
        ):
            policy = HengbotPolicy(
                quest_strategies=load_quest_strategies(Path("strategy/quests")),
                quest_knowledge=load_quest_knowledge(REAL_QUEST_DEFINITIONS),
            )
            case = replace(
                town,
                player=replace(town.player, level=8),
                quests={1: QuestState(1, status=status, fixed=True)},
            )
            strategy = policy._carry_procurement_strategy(case)
            self.assertIsNotNone(strategy)
            self.assertEqual(
                strategy.required_force.get("throwing_items", {}).get("lit_torch"), 5
            )
            self.assertFalse(
                policy._town_departure_conjuncts(case)["quest_carry_ready"]
            )
        for status in (
            QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN, QUEST_STATUS_COMPLETED
        ):
            policy = HengbotPolicy(
                quest_strategies=load_quest_strategies(Path("strategy/quests")),
                quest_knowledge=load_quest_knowledge(REAL_QUEST_DEFINITIONS),
            )
            level_ten = replace(
                town,
                player=replace(town.player, level=10),
                quests={1: QuestState(1, status=status, fixed=True)},
            )
            self.assertTrue(
                policy._town_departure_conjuncts(level_ten)["quest_carry_ready"]
            )

    def test_quest_strategy_still_rejects_missing_required_force(self):
        policy = HengbotPolicy()
        profile = SimpleNamespace(required_force=self.FORCE)
        policy._abandoned_quest_carry_requirements["launcher"] = "gone"

        self.assertFalse(
            policy._approved_strategy_force_ready(self._town(), profile)
        )
        self.assertIn(
            "launcher",
            policy._fixed_quest_readiness["strategy_force"]["failed"],
        )
