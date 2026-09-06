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
from hengbot.policy_constants import FOOD_TYPE_MANA


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


def _is_forbidden_uppercase_call(path, node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "upper"
        # Quest knowledge normalizes display names, not input selectors.
        and not (path.name == "quest_knowledge.py" and node.lineno in {217, 251})
    )


class PickupTest(unittest.TestCase):
    def test_pickup_declares_seek_loot_prompt_handoff(self):
        position = Position(10, 10)
        snapshot = Snapshot(
            player(10, 10),
            {position: grid(10, 10, objects=1)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 3, 0),
        )
        policy = HengbotPolicy()
        policy._position_changed = True

        self.assertEqual(policy._normal_loot_key(snapshot, []), PICKUP_KEY)
        self.assertEqual(policy.last_reason, "pickup")
        self.assertEqual(policy.prompt_owner_handoff, "seek-loot")

    def test_mana_food_deficit_prioritizes_device_over_known_downstairs(self):
        grids = {
            Position(10, 10): grid(10, 10, downstairs=True),
            Position(10, 11): grid(10, 11, objects=1, object_tvals=(TVAL_SCROLL,)),
            Position(11, 10): grid(11, 10, objects=1, object_tvals=(TVAL_WAND,)),
        }
        snapshot = Snapshot(
            player(10, 10, food_type=FOOD_TYPE_MANA),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=[item("a", TVAL_STAFF, 1, charges=1)],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snapshot), "2")
        self.assertEqual(policy.last_reason, "mana-food:seek-device")

    def test_mana_food_deficit_recovers_unknown_legacy_floor_item(self):
        grids = {
            Position(10, 10): grid(10, 10, downstairs=True),
            Position(10, 11): grid(10, 11, objects=1),
        }
        snapshot = Snapshot(
            player(10, 10, food_type=FOOD_TYPE_MANA), grids, [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "mana-food:seek-device")

    def test_mana_food_full_reserve_does_not_override_downstairs(self):
        grids = {
            Position(10, 10): grid(10, 10, downstairs=True),
            Position(10, 11): grid(10, 11, objects=1, object_tvals=(TVAL_WAND,)),
        }
        snapshot = Snapshot(
            player(10, 10, food_type=FOOD_TYPE_MANA), grids, [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=[
                item("a", TVAL_WAND, 1, charges=15),
                item("b", TVAL_STAFF, 1, charges=5),
            ],
        )
        policy = HengbotPolicy()

        policy._build_grid_index(snapshot)
        self.assertIsNone(policy._mana_food_loot_key(snapshot, []))

    def test_distant_weak_hostile_does_not_block_safe_loot(self):
        monster = hostile(1, 10, 13, distance=3, max_melee_damage=2)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, monster=True),
        }
        policy = HengbotPolicy()

        snapshot = Snapshot(
            player(10, 10), grids, [monster], floor_key=(1, 5, 0)
        )
        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "seek-loot")

    def test_emergency_return_active_suppresses_normal_loot_seek(self):
        loot = Position(10, 11)
        snapshot = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                loot: grid(10, 11, objects=1),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
        )
        policy = HengbotPolicy()
        policy._observe(snapshot)
        policy._emergency_return_active = True

        policy.choose_key(snapshot)

        self.assertNotEqual(policy.last_reason, "seek-loot")
        self.assertIsNone(policy._loot_target)

    def test_material_ranged_threat_blocks_loot(self):
        monster = hostile(1, 10, 13, distance=3, max_ranged_damage=100)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, monster=True),
        }
        policy = HengbotPolicy()
        snapshot = Snapshot(player(10, 10, hp=500, max_hp=500), grids, [monster])

        policy.choose_key(snapshot)

        self.assertNotEqual(policy.last_reason, "seek-loot")
        self.assertEqual(policy.loot_state(snapshot)["blocker"], "material-threat")

    def test_material_pack_repositions_instead_of_exploring_into_surround(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(9, 13)
            for x in range(8, 13)
        }
        monsters = [
            hostile(1, 12, 10, distance=2, speed=120, max_melee_damage=18),
            hostile(2, 12, 9, distance=2, speed=120, max_melee_damage=18),
            hostile(3, 11, 12, distance=2, speed=120, max_melee_damage=18),
        ]
        for monster in monsters:
            grids[monster.position] = grid(
                monster.position.y, monster.position.x, monster=True
            )
        snapshot = Snapshot(
            player(10, 10, hp=589, max_hp=616, level=27),
            grids,
            monsters,
            floor_key=(3, 19, 0),
        )
        policy = HengbotPolicy()

        key = policy.choose_key(snapshot)

        self.assertEqual(policy.last_reason, "threat:reposition")
        self.assertIn(key, {"4", "7", "8"})
        self.assertIn(Position(10, 10), policy._engagement_avoid_cells)

    def test_survival_flee_does_not_reverse_to_loot_when_threat_flickers(self):
        floor_key = (1, 40, 0)
        origin = Position(10, 10)
        abandoned = Position(10, 11)
        loot = Position(10, 12)
        policy = HengbotPolicy()
        safe = Snapshot(
            player(origin.y, origin.x, hp=600, max_hp=600, level=30),
            {
                origin: grid(origin.y, origin.x),
                abandoned: grid(abandoned.y, abandoned.x),
                loot: grid(loot.y, loot.x, objects=1),
            },
            [],
            floor_key=floor_key,
        )

        self.assertEqual(policy.choose_key(safe), "6")
        self.assertEqual(policy.last_reason, "seek-loot")

        threat = hostile(
            1,
            11,
            12,
            distance=1,
            max_melee_damage=80,
        )
        dangerous = Snapshot(
            player(
                abandoned.y,
                abandoned.x,
                hp=600,
                max_hp=600,
                level=30,
                afraid=True,
            ),
            {
                origin: grid(origin.y, origin.x),
                abandoned: grid(abandoned.y, abandoned.x),
                loot: grid(loot.y, loot.x, objects=1),
                threat.position: grid(
                    threat.position.y, threat.position.x, monster=True
                ),
            },
            [threat],
            floor_key=floor_key,
        )

        self.assertEqual(policy.choose_key(dangerous), "4")
        self.assertEqual(policy.last_reason, "flee")
        self.assertIn(abandoned, policy._engagement_avoid_cells)

        hidden_again = Snapshot(
            player(origin.y, origin.x, hp=600, max_hp=600, level=30),
            safe.grids,
            [],
            floor_key=floor_key,
        )
        policy.choose_key(hidden_again)

        self.assertNotEqual(policy.last_reason, "seek-loot")
        self.assertNotEqual(policy._loot_target, loot)

    def test_secret_wall_search_does_not_reverse_threat_retreat(self):
        abandoned = Position(4, 124)
        current = Position(4, 125)
        snapshot = Snapshot(
            player(current.y, current.x, hp=501, max_hp=501, level=28),
            {
                abandoned: grid(abandoned.y, abandoned.x),
                current: grid(current.y, current.x),
            },
            [],
            floor_key=(1, 30, 0),
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)
        policy._remembered_wall_t.add((3, 124))
        policy._engagement_avoid_cells.add(abandoned)

        self.assertIsNone(policy._secret_wall_search_step(snapshot))

    def test_multiplier_blocked_loot_stays_deferred_after_threat_leaves_view(self):
        floor_key = (DUNGEON_YEEK_CAVE, 3, 0)
        loot = Position(10, 12)
        policy = HengbotPolicy()
        safe = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                loot: grid(10, 12, objects=1),
                Position(11, 10): grid(11, 10),
            },
            [],
            floor_key=floor_key,
        )
        self.assertEqual(policy.choose_key(safe), "6")
        self.assertEqual(policy._loot_target, loot)

        multiplier = hostile(
            1, 13, 11, distance=2, can_multiply=True, max_melee_damage=1
        )
        blocked = Snapshot(
            player(10, 11),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                loot: grid(10, 12, objects=1),
                Position(11, 10): grid(11, 10),
                Position(13, 11): grid(13, 11, monster=True),
            },
            [multiplier],
            floor_key=floor_key,
        )
        policy._observe(blocked)
        self.assertIsNone(policy._normal_loot_key(blocked, [multiplier]))
        self.assertIn(loot, policy._deferred_loot)
        self.assertIsNone(policy._loot_target)

        hidden_again = Snapshot(
            player(10, 10),
            safe.grids,
            [],
            floor_key=floor_key,
        )
        policy.choose_key(hidden_again)

        self.assertNotEqual(policy.last_reason, "seek-loot")
        self.assertIsNone(policy._loot_target)
        self.assertEqual(policy.loot_state(hidden_again)["deferred"], [{"y": 10, "x": 12}])

    def test_routine_return_sweeps_nearby_safe_loot(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1),
        }
        snapshot = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True
        policy._last_return_trigger = "recall-low"

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "return:seek-loot")

    def test_emergency_return_does_not_resume_routine_loot_sweep(self):
        grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(10, 11): grid(10, 11, objects=1),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, monster=True),
        }
        snapshot = Snapshot(
            player(10, 10),
            grids,
            [hostile(10, 13, 1, distance=3, asleep=True, max_melee_damage=1)],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy()
        policy._observe(snapshot)
        policy._emergency_return_active = True
        policy._returning_to_town = True
        policy._last_return_trigger = "cure-low"

        self.assertEqual(policy.choose_key(snapshot), "<")
        self.assertEqual(policy.last_reason, "return:ascend")
        self.assertNotEqual(policy.last_reason, "return:seek-loot")

    def test_critical_return_does_not_detour_for_loot(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1),
        }
        snapshot = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True
        policy._last_return_trigger = "food-hungry"

        self.assertEqual(policy.choose_key(snapshot), "rr")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_steps_off_a_new_drop_to_trigger_autodestroy(self):
        grids = {
            Position(10, 10): grid(10, 10, objects=1),
            Position(10, 11): grid(10, 11, downstairs=True),
        }
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(Snapshot(player(10, 10), grids, [])), "6")
        self.assertEqual(policy.last_reason, "trigger-autodestroy")

    def test_picks_up_an_item_that_survived_stepping_onto_its_tile(self):
        grids = {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10, objects=1),
        }
        policy = HengbotPolicy()
        policy._floor_key = (1, 1, 0)
        policy._last_position = Position(10, 9)

        self.assertEqual(
            policy.choose_key(
                Snapshot(player(10, 10), grids, [], floor_key=(1, 1, 0))
            ),
            "g",
        )
        self.assertEqual(policy.last_reason, "pickup")

    def test_selects_every_item_from_a_floor_pile(self):
        grids = {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10, objects=3),
        }
        policy = HengbotPolicy()
        policy._floor_key = (1, 1, 0)
        policy._last_position = Position(10, 9)

        self.assertEqual(
            policy.choose_key(
                Snapshot(player(10, 10), grids, [], floor_key=(1, 1, 0))
            ),
            "gaaa",
        )
        self.assertEqual(policy.last_reason, "pickup")

    def test_failed_floor_pickup_is_deferred_on_the_next_observation(self):
        floor_key = (DUNGEON_YEEK_CAVE, 13, 0)
        loot = Position(10, 10)
        grids = {
            Position(10, 9): grid(10, 9),
            loot: grid(10, 10, objects=1),
            Position(10, 11): grid(10, 11),
        }
        policy = HengbotPolicy()
        policy._floor_key = floor_key
        policy._last_position = Position(10, 9)
        snapshot = Snapshot(player(10, 10), grids, [], floor_key=floor_key)

        self.assertEqual(policy.choose_key(snapshot), "g")
        policy._observe(snapshot)

        self.assertIn(loot, policy._deferred_loot)
        self.assertIsNone(
            policy._current_floor_item_key(
                snapshot,
                pickup_reason="fundraise:pickup",
                trigger_reason="fundraise:trigger-autodestroy",
            )
        )
        self.assertIsNone(policy._loot_step(snapshot, include_unsafe=True))

    def test_loot_step_skips_search_only_when_no_candidates_exist(self):
        start = Position(10, 10)
        loot = Position(10, 11)
        snapshot = Snapshot(
            player(start.y, start.x),
            {start: grid(start.y, start.x), loot: grid(loot.y, loot.x)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)
        policy._loot_target = Position(99, 99)

        with patch.object(
            policy, "_walkable_neighbors", wraps=policy._walkable_neighbors
        ) as neighbors:
            self.assertIsNone(policy._loot_step(snapshot))
            self.assertEqual(neighbors.call_count, 0)
        self.assertIsNone(policy._loot_target)

        policy._known_loot.add(loot)
        with patch.object(
            policy, "_walkable_neighbors", wraps=policy._walkable_neighbors
        ) as neighbors:
            self.assertEqual(policy._loot_step(snapshot), loot)
            self.assertGreater(neighbors.call_count, 0)
        self.assertEqual(policy._loot_target, loot)

    def test_partial_floor_pile_pickup_is_not_deferred(self):
        floor_key = (DUNGEON_YEEK_CAVE, 13, 0)
        loot = Position(10, 10)
        policy = HengbotPolicy()
        policy._floor_key = floor_key
        policy._last_position = Position(10, 9)
        first = Snapshot(
            player(10, 10),
            {Position(10, 9): grid(10, 9), loot: grid(10, 10, objects=2)},
            [],
            floor_key=floor_key,
        )

        self.assertEqual(policy.choose_key(first), "gaa")
        after_one = Snapshot(
            player(10, 10),
            {Position(10, 9): grid(10, 9), loot: grid(10, 10, objects=1)},
            [],
            floor_key=floor_key,
        )
        policy._observe(after_one)

        self.assertNotIn(loot, policy._deferred_loot)

class IdentifyPurchaseBatchingTest(unittest.TestCase):
    """A Home identification batch can surface several items needing Identify
    or *Identify* at once. Buying only one scroll per store trip discovered
    each further need only after a fresh Home round trip (measured: a single
    town stay spent 4 separate Alchemist visits on one Home batch).
    _purchase_quantity now covers the whole outstanding tier in one purchase
    instead (see _outstanding_identification_count), still capped and still
    gated by the ordinary affordability check."""

    def _town(self, *, inventory, gold=100000, store=None):
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            equipment=[
                item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)
            ],
            store=store,
        )

    def test_star_identify_quantity_matches_outstanding_full_targets(self):
        # 3 known ego weapons in the pack, each still missing its full traits.
        pack = [
            item(
                letter, 23, sval, name=f"ego {letter}", is_equipment=True,
                is_ego=True, known=True, fully_known=False,
            )
            for letter, sval in (("a", 1), ("b", 2), ("c", 3))
        ]
        store = StoreState(
            STORE_ALCHEMIST,
            [store_item("s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, price=500, count=99)],
        )
        town = self._town(inventory=pack, store=store)
        policy = HengbotPolicy()
        # The bot only walks into the Alchemist for this once an earlier town
        # decision (_town_item_processing_key et al.) already found a target
        # and requested this tier -- reproduce that precondition directly.
        policy._identification_need = "full"

        purchase = policy._next_purchase(town)
        self.assertIsNotNone(purchase)
        self.assertEqual(policy._purchase_quantity(town, purchase), 3)

    def test_identify_quantity_stays_one_when_nothing_outstanding(self):
        store = StoreState(
            STORE_ALCHEMIST,
            [store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=20, count=99)],
        )
        town = self._town(inventory=[], store=store)
        policy = HengbotPolicy()

        self.assertEqual(policy._purchase_quantity(town, town.store.items[0]), 1)

    def test_identify_quantity_is_capped(self):
        pack = [
            item(
                chr(ord("a") + i), 30 + (i % 4), 1, name=f"unknown {i}",
                is_equipment=True, known=False, pseudo_feeling="good",
            )
            for i in range(7)
        ]
        store = StoreState(
            STORE_ALCHEMIST,
            [store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=20, count=99)],
        )
        town = self._town(inventory=pack, store=store)
        policy = HengbotPolicy()

        self.assertEqual(
            policy._purchase_quantity(town, town.store.items[0]), IDENTIFY_PURCHASE_MAX
        )

    def test_identify_quantity_still_respects_affordability(self):
        pack = [
            item(
                chr(ord("a") + i), 30, 1, name=f"unknown {i}",
                is_equipment=True, known=False, pseudo_feeling="good",
            )
            for i in range(3)
        ]
        store = StoreState(
            STORE_ALCHEMIST,
            [store_item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=100, count=99)],
        )
        # 3 outstanding, but 250g only affords 2 scrolls at 100g each.
        town = self._town(inventory=pack, gold=250, store=store)
        policy = HengbotPolicy()

        self.assertEqual(policy._purchase_quantity(town, town.store.items[0]), 2)

    def test_outstanding_count_combines_pack_and_home_and_splits_by_tier(self):
        pack_normal = item(
            "a", 30, 1, name="unknown boots", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        pack_full = item(
            "b", 23, 1, name="ego blade", is_equipment=True,
            is_ego=True, known=True, fully_known=False,
        )
        home_normal = store_item(
            "c", 31, 1, name="unknown gloves", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        home_full = store_item(
            "d", 36, 1, name="ego mail", is_equipment=True,
            is_ego=True, known=True, fully_known=False,
        )
        policy = HengbotPolicy()
        town = self._town(inventory=[pack_normal, pack_full])
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([home_normal, home_full])
        policy._equipment_catalog.observe_home_page([])

        self.assertEqual(policy._outstanding_identification_count(town, full=False), 2)
        self.assertEqual(policy._outstanding_identification_count(town, full=True), 2)

    def test_outstanding_count_skips_deferred_and_processed_home_items(self):
        # Mirrors _has_actionable_incomplete_home_item exactly: a deferred item
        # is skipped regardless of tier, and a *known* item only needing full
        # identification is skipped once cached in _processed_home_items (an
        # unidentified twin is never skipped that way -- see that function).
        deferred = store_item(
            "a", 31, 1, name="deferred gloves", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        processed = store_item(
            "b", 36, 1, name="processed mail", is_equipment=True,
            is_ego=True, known=True, fully_known=False,
        )
        policy = HengbotPolicy()
        town = self._town(inventory=[])
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([deferred, processed])
        policy._equipment_catalog.observe_home_page([])
        policy._deferred_home_items.add(policy._item_signature(deferred))
        policy._processed_home_items.add(policy._item_signature(processed))

        self.assertEqual(policy._outstanding_identification_count(town, full=False), 0)
        self.assertEqual(policy._outstanding_identification_count(town, full=True), 0)

    def test_outstanding_count_includes_incomplete_lights_and_diggers(self):
        # The optimizer catalogs every equipment tval, including lights and
        # diggers. They must therefore share the same identification route or an
        # unknown one can leave the departure gate permanently false.
        unidentified_lantern = item(
            "a", TVAL_LITE, SV_LITE_LANTERN, name="lantern", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        unidentified_digger = item(
            "b", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True,
            known=False, pseudo_feeling="good",
        )
        policy = HengbotPolicy()
        town = self._town(inventory=[unidentified_lantern, unidentified_digger])

        self.assertEqual(policy._outstanding_identification_count(town, full=False), 2)

    def test_recorded_1286548_plain_count_matches_all_three_consumers(self):
        unknown = [
            item("a", TVAL_ROD, 0, name="unknown rod", known=False),
            item("b", TVAL_WAND, 0, name="unknown wand one", known=False),
            item("c", TVAL_WAND, 1, name="unknown wand two", known=False),
            item("d", TVAL_STAFF, 0, name="unknown staff", known=False),
            item(
                "e", TVAL_RING, 0, name="unknown ring", is_equipment=True,
                known=False, pseudo_feeling="good",
            ),
        ]
        identify = store_item(
            "i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=20, count=99
        )
        town = self._town(
            inventory=unknown,
            store=StoreState(STORE_ALCHEMIST, [identify]),
        )
        policy = HengbotPolicy()

        # Stage D assigns the formerly orphaned rod to the device flow, so the
        # final three-flow union contains all five recorded unknown items.
        self.assertEqual(
            policy._outstanding_identification_count(town, full=False), 5
        )
        self.assertEqual(policy._purchase_quantity(town, identify), 5)
        self.assertEqual(
            policy._outstanding_identification_count(town, full=True), 0
        )

class ChestProcessingTest(unittest.TestCase):
    """Drop → step beside → search → disarm → open, on fixed key budgets."""

    def _snap(self, *, inventory=(), grids=None, player_pos=(10, 10)):
        base = grids or {
            Position(y, x): grid(y, x) for y in range(9, 12) for x in range(9, 13)
        }
        return Snapshot(
            player(
                *player_pos, hp=50, max_hp=50, class_id=PLAYER_CLASS_WARRIOR
            ),
            base,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            width=30,
            height=30,
            inventory=list(inventory),
            equipment=[
                item("a", TVAL_SWORD, 17, name="sword", is_equipment=True),
                item(
                    "l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True
                ),
            ],
        )

    def test_full_pipeline_runs_on_budgets(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "dc")
        self.assertEqual(policy.last_reason, "chest:drop")
        self.assertIsNone(policy._chest_position)
        self.assertEqual(policy._chest_drop_origin, Position(10, 10))

        # The chest now sits under the player (the tile reports an object);
        # step off, then work it from the adjacent tile.
        dropped_grids = dict(snap.grids)
        dropped_grids[Position(10, 10)] = grid(10, 10, objects=1)
        dropped = replace(snap, inventory=[], grids=dropped_grids)
        key = policy.choose_key(dropped)
        self.assertEqual(policy.last_reason, "chest:step-off")

        beside = replace(
            dropped,
            player=player(
                10, 11, hp=50, max_hp=50, class_id=PLAYER_CLASS_WARRIOR
            ),
        )
        chest_grids = dict(beside.grids)
        chest_grids[Position(10, 10)] = grid(10, 10, objects=1)
        beside = replace(beside, grids=chest_grids)

        for _ in range(CHEST_SEARCH_BUDGET):
            self.assertEqual(policy.choose_key(beside), "s")
            self.assertEqual(policy.last_reason, "chest:search")
        for _ in range(CHEST_DISARM_BUDGET):
            self.assertEqual(policy.choose_key(beside), "D4")
            self.assertEqual(policy.last_reason, "chest:disarm")
        for _ in range(CHEST_OPEN_BUDGET):
            self.assertEqual(policy.choose_key(beside), "o4")
            self.assertEqual(policy.last_reason, "chest:open")

        # Budgets exhausted: the pipeline abandons and normal behavior resumes.
        policy.choose_key(beside)
        self.assertFalse(policy.last_reason.startswith("chest:"))
        self.assertIsNone(policy._chest_position)

    def test_floor_chest_is_opened_in_place_before_pickup(self):
        chest_position = Position(10, 10)
        grids = {
            Position(y, x): grid(y, x)
            for y in range(9, 12) for x in range(9, 13)
        }
        grids[chest_position] = grid(
            10, 10, objects=1, object_tvals=(TVAL_CHEST,)
        )
        snap = self._snap(grids=grids, player_pos=(10, 11))
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "s")
        self.assertEqual(policy.last_reason, "chest:search")
        self.assertEqual(policy._chest_position, chest_position)

    def test_reserved_floor_chest_is_recognized_without_visible_tval(self):
        chest_position = Position(10, 10)
        grids = {
            Position(y, x): grid(y, x)
            for y in range(9, 12) for x in range(9, 13)
        }
        grids[chest_position] = grid(10, 10, objects=1, object_tvals=())
        snap = self._snap(grids=grids, player_pos=(10, 11))
        policy = HengbotPolicy()

        self.assertEqual(
            policy._chest_processing_key(
                snap, [], allowed_positions={chest_position}
            ),
            "s",
        )
        self.assertEqual(policy.last_reason, "chest:search")
        self.assertEqual(policy._chest_position, chest_position)

    def test_carried_reserved_chest_returns_to_its_fixed_position_before_drop(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = replace(
            self._snap(inventory=[chest], player_pos=(10, 10)),
            floor_key=(0, 5, 34),
        )
        policy = HengbotPolicy()

        with patch.object(
            policy,
            "approved_quest_strategy",
            return_value=SimpleNamespace(quest_id=34),
        ), patch.object(
            policy,
            "_quest_strategy_route_step",
            return_value=Position(10, 9),
        ):
            self.assertEqual(
                policy._chest_processing_key(
                    snap, [], allowed_positions={Position(10, 8)}
                ),
                "4",
            )

        self.assertEqual(policy.last_reason, "chest:return-reserved-position")
        self.assertIsNone(policy._chest_drop_origin)

    def test_carried_reserved_chest_drops_in_place_when_position_is_unreachable(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = replace(
            self._snap(inventory=[chest], player_pos=(6, 16)),
            floor_key=(0, 5, 34),
        )
        policy = HengbotPolicy()

        with patch.object(
            policy,
            "approved_quest_strategy",
            return_value=SimpleNamespace(quest_id=34),
        ), patch.object(
            policy,
            "_quest_strategy_route_step",
            return_value=None,
        ):
            self.assertEqual(
                policy._chest_processing_key(
                    snap, [], allowed_positions={Position(10, 8)}
                ),
                "dc",
            )

        self.assertEqual(policy.last_reason, "chest:drop-unreachable-reserved")
        self.assertEqual(policy._chest_drop_origin, Position(6, 16))

    def test_opened_floor_chest_collects_contents_without_drop(self):
        chest_position = Position(10, 10)
        grids = {
            Position(y, x): grid(y, x)
            for y in range(9, 12) for x in range(9, 13)
        }
        grids[chest_position] = grid(
            10, 10,
            objects=3,
            object_tvals=(TVAL_CHEST, TVAL_POTION, TVAL_SCROLL),
        )
        snap = self._snap(grids=grids, player_pos=(10, 11))
        policy = HengbotPolicy()
        policy._floor_key = snap.floor_key
        policy._chest_position = chest_position
        policy._chest_phase_counts = {
            "search": CHEST_SEARCH_BUDGET,
            "disarm": CHEST_DISARM_BUDGET,
            "open": 1,
        }

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "chest:collect-contents")
        self.assertEqual(policy._chest_position, chest_position)

    def test_opened_chest_collects_every_scattered_content_cell(self):
        chest_position = Position(10, 10)
        grids = {
            Position(y, x): grid(y, x)
            for y in range(7, 14) for x in range(7, 14)
        }
        grids[chest_position] = grid(
            10, 10, objects=1, object_tvals=(TVAL_CHEST,)
        )
        grids[Position(9, 10)] = grid(
            9, 10, objects=1, object_tvals=(TVAL_POTION,)
        )
        grids[Position(10, 12)] = grid(
            10, 12, objects=1, object_tvals=(TVAL_SCROLL,)
        )
        snap = self._snap(grids=grids, player_pos=(10, 11))
        policy = HengbotPolicy()
        policy._floor_key = snap.floor_key
        policy._chest_position = chest_position
        policy._chest_phase_counts = {
            "search": CHEST_SEARCH_BUDGET,
            "disarm": CHEST_DISARM_BUDGET,
            "open": 1,
        }

        self.assertEqual(policy.choose_key(snap), "7")
        self.assertEqual(policy.last_reason, "chest:collect-contents")

        one_left_grids = dict(grids)
        one_left_grids[Position(9, 10)] = grid(9, 10)
        one_left = replace(
            snap,
            player=player(9, 10, hp=50, max_hp=50, class_id=PLAYER_CLASS_WARRIOR),
            grids=one_left_grids,
        )
        self.assertIn(policy.choose_key(one_left), {"1", "2", "3", "6"})
        self.assertEqual(policy.last_reason, "chest:collect-contents")

        collected_grids = dict(one_left_grids)
        collected_grids[Position(10, 12)] = grid(10, 12)
        collected = replace(one_left, grids=collected_grids)
        policy.choose_key(collected)
        self.assertFalse(policy.last_reason.startswith("chest:"))
        self.assertIsNone(policy._chest_position)

        policy.choose_key(collected)
        self.assertFalse(policy.last_reason.startswith("chest:"))
        self.assertIn(chest_position, policy._processed_chest_positions)

    def test_opened_chest_ignores_preexisting_nearby_quest_loot(self):
        chest_position = Position(10, 10)
        old_loot = Position(9, 10)
        new_content = Position(11, 10)
        grids = {
            Position(y, x): grid(y, x)
            for y in range(7, 14) for x in range(7, 14)
        }
        grids[chest_position] = grid(
            10, 10, objects=1, object_tvals=(TVAL_CHEST,)
        )
        grids[old_loot] = grid(
            9, 10, objects=1, object_tvals=(TVAL_POTION,)
        )
        before = self._snap(grids=grids, player_pos=(10, 11))
        policy = HengbotPolicy()
        policy._floor_key = before.floor_key
        policy._chest_position = chest_position
        policy._chest_phase_counts = {
            "search": CHEST_SEARCH_BUDGET,
            "disarm": CHEST_DISARM_BUDGET,
        }

        self.assertEqual(policy.choose_key(before), "o4")

        opened_grids = dict(grids)
        opened_grids[new_content] = grid(
            11, 10, objects=1, object_tvals=(TVAL_SCROLL,)
        )
        opened = replace(before, grids=opened_grids)
        self.assertEqual(policy.choose_key(opened), "1")
        self.assertEqual(policy.last_reason, "chest:collect-contents")

        collected_grids = dict(opened_grids)
        collected_grids[new_content] = grid(11, 10)
        collected = replace(opened, grids=collected_grids)
        self.assertIsNone(policy._chest_processing_key(collected, []))
        self.assertIn(chest_position, policy._processed_chest_positions)

    def test_opened_chest_picks_up_contents_when_standing_on_them(self):
        chest_position = Position(10, 10)
        content_position = Position(9, 10)
        grids = {
            Position(y, x): grid(y, x)
            for y in range(7, 14) for x in range(7, 14)
        }
        grids[chest_position] = grid(
            10, 10, objects=1, object_tvals=(TVAL_CHEST,)
        )
        grids[content_position] = grid(
            9, 10,
            objects=2,
            object_tvals=(TVAL_POTION, TVAL_SCROLL),
        )
        snapshot = self._snap(grids=grids, player_pos=(9, 10))
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._chest_position = chest_position
        policy._chest_phase_counts = {"open": 1}

        self.assertEqual(policy.choose_key(snapshot), PICKUP_KEY + "aa")
        self.assertEqual(policy.last_reason, "chest:collect-contents")

    def test_drop_locks_observed_chest_cell_not_assumed_origin(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest], player_pos=(10, 10))
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "dc")
        displaced_grids = dict(snap.grids)
        actual = Position(10, 12)
        displaced_grids[actual] = grid(
            10, 12, objects=1, object_tvals=(TVAL_CHEST,)
        )
        dropped = replace(snap, inventory=[], grids=displaced_grids)

        self.assertEqual(policy.choose_key(dropped), "9")
        self.assertEqual(policy.last_reason, "chest:approach")
        self.assertEqual(policy._chest_position, actual)
        self.assertIsNone(policy._chest_drop_origin)

    def test_pending_drop_blocks_other_actions_until_snapshot_confirms_it(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "dc")
        self.assertEqual(policy.choose_key(snap), "5")
        self.assertEqual(policy.last_reason, "chest:await-drop")

    def test_looted_chest_tile_ends_the_pipeline(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        policy = HengbotPolicy()
        policy.choose_key(snap)  # drop at (10,10)

        emptied = replace(
            snap,
            inventory=[],
            player=player(
                10, 11, hp=50, max_hp=50, class_id=PLAYER_CLASS_WARRIOR
            ),
        )
        policy.choose_key(emptied)
        self.assertFalse(policy.last_reason.startswith("chest:"))
        self.assertIsNone(policy._chest_position)

    def test_chest_hidden_under_player_steps_off_before_empty_check(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        policy = HengbotPolicy()
        policy.choose_key(snap)

        dropped_but_hidden = replace(snap, inventory=[])
        policy.choose_key(dropped_but_hidden)

        self.assertEqual(policy.last_reason, "chest:step-off")
        self.assertEqual(policy._chest_position, Position(10, 10))

    def test_empty_chest_is_not_processed(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest (empty)")
        snap = self._snap(inventory=[chest])
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "chest:drop")

    def test_hostiles_defer_the_pipeline(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        snap = replace(
            snap, visible_monsters=[hostile(1, 11, 11, distance=1)]
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertFalse(policy.last_reason.startswith("chest:"))

    def test_low_hp_defers_the_drop(self):
        chest = item("c", TVAL_CHEST, 1, name="small wooden chest")
        snap = self._snap(inventory=[chest])
        snap = replace(
            snap,
            player=player(
                10, 10, hp=20, max_hp=50, class_id=PLAYER_CLASS_WARRIOR
            ),
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "chest:drop")


if __name__ == "__main__":
    unittest.main()
