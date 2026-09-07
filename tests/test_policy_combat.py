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
from test_policy import FOOD, POTION, SCROLL, STAFF
import hengbot.policy_combat as policy_combat_module
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



def _supply_test_case(name):
    import test_policy_supply
    return getattr(test_policy_supply, name)()

def _is_forbidden_uppercase_call(path, node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "upper"
        # Quest knowledge normalizes display names, not input selectors.
        and not (path.name == "quest_knowledge.py" and node.lineno in {217, 251})
    )


class DetectedMonsterChannelTest(unittest.TestCase):
    @staticmethod
    def _corridor_snapshot(detected):
        grids = {
            Position(10, x): grid(10, x)
            for x in range(9, 14)
        }
        return Snapshot(
            player(10, 10, hp=100, max_hp=100),
            grids,
            [],
            detected_monsters=detected,
            floor_key=(1, 10, 0),
        )

    def test_detected_only_monster_is_neither_melee_target_nor_route_cell(self):
        behind_wall = replace(
            hostile(
                7, 10, 11, distance=1, max_melee_damage=20
            ),
            perception="detected",
        )
        snapshot = self._corridor_snapshot([behind_wall])
        policy = HengbotPolicy()

        policy._build_grid_index(snapshot)

        self.assertEqual(policy._strategic_hostiles(snapshot), [])
        self.assertEqual(policy._strategic_adjacent_hostiles(snapshot), [])
        self.assertNotIn((10, 11), policy._floor_t)
        self.assertNotIn(
            behind_wall.position,
            policy._walkable_neighbors(snapshot, snapshot.player.position),
        )

    def test_detected_breeders_count_classify_and_enter_threat_prediction(self):
        weak = replace(
            hostile(
                7, 10, 12, distance=2, can_multiply=True,
                max_melee_damage=4,
            ),
            perception="detected",
        )
        strong = replace(
            hostile(
                8, 10, 13, distance=3, can_multiply=True,
                max_melee_damage=5,
            ),
            perception="detected",
        )
        snapshot = self._corridor_snapshot([weak, strong])
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        perceived = policy._perceived_hostiles(snapshot)
        prediction = policy.threat_prediction(snapshot, perceived)
        policy._update_combat_outcome(snapshot)

        self.assertTrue(policy._is_weak_breeder(snapshot, weak))
        self.assertFalse(policy._is_weak_breeder(snapshot, strong))
        self.assertEqual(policy._breeder_engagement_start_count, 2)
        self.assertEqual(
            {row["position"]["x"] for row in prediction["monsters"]},
            {12, 13},
        )

    def test_engagement_population_is_judgement_only_not_target_selection(self):
        breeder = replace(
            hostile(7, 10, 11, distance=1, can_multiply=True),
            perception="detected",
        )
        snapshot = self._corridor_snapshot([breeder])
        policy = HengbotPolicy()

        self.assertEqual(policy._engagement_breeder_population(snapshot), [breeder])
        self.assertEqual(policy._physical_hostiles(snapshot), [])
        self.assertEqual(policy._physical_adjacent_hostiles(snapshot), [])
        self.assertEqual(policy._strategic_hostiles(snapshot), [])
        self.assertIsNone(policy._ranged_attack_key(snapshot, [], []))

    def test_transition_from_detected_to_visible_is_not_double_counted(self):
        detected = replace(
            hostile(7, 10, 12, distance=2, can_multiply=True),
            perception="detected",
        )
        visible = replace(detected, perception="direct")
        snapshot = replace(
            self._corridor_snapshot([detected]),
            visible_monsters=[visible],
        )
        policy = HengbotPolicy()

        perceived = policy._perceived_hostiles(snapshot)
        policy._update_combat_outcome(snapshot)

        self.assertEqual([monster.index for monster in perceived], [7])
        self.assertEqual(policy._breeder_engagement_start_count, 1)

    def test_detected_breeder_prepares_choke_without_targeting_it(self):
        breeder = replace(
            hostile(
                7, 10, 12, distance=2, can_multiply=True,
                max_melee_damage=4,
            ),
            perception="detected",
        )
        snapshot = replace(
            self._corridor_snapshot([breeder]),
            grids={
                Position(y, x): grid(y, x)
                for y in range(8, 13)
                for x in range(8, 13)
            },
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        with patch.object(
            policy, "_summoner_retreat_step", return_value=Position(9, 9)
        ) as retreat:
            key = policy._detected_threat_preparation_key(snapshot, [])

        self.assertEqual((key, policy.last_reason), ("7", "detected:prepare-choke"))
        retreat.assert_called_once()
        self.assertEqual(policy._strategic_hostiles(snapshot), [])

    def test_latched_town_return_outranks_detected_threat_preparation(self):
        breeder = replace(
            hostile(
                7, 10, 12, distance=2, can_multiply=True,
                max_melee_damage=4,
            ),
            perception="detected",
        )
        snapshot = replace(
            self._corridor_snapshot([breeder]),
            grids={
                Position(y, x): grid(y, x)
                for y in range(8, 13)
                for x in range(8, 13)
            },
            inventory=[item("w", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True

        with patch.object(
            policy, "_summoner_retreat_step", return_value=Position(9, 9)
        ):
            key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), ("rw", "return:recall"))

    def test_emergency_outranks_detected_threat_preparation(self):
        breeder = replace(
            hostile(
                7, 10, 12, distance=2, can_multiply=True,
                max_melee_damage=4,
            ),
            perception="detected",
        )
        snapshot = self._corridor_snapshot([breeder])
        policy = HengbotPolicy()

        def emergency(_snapshot, _hostiles):
            policy.last_reason = "emergency:teleport"
            return "rt"

        with (
            patch.object(policy, "_emergency_item", side_effect=emergency),
            patch.object(
                policy, "_detected_threat_preparation_key",
                wraps=policy._detected_threat_preparation_key,
            ) as detected_preparation,
        ):
            key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), ("rt", "emergency:teleport"))
        detected_preparation.assert_not_called()

    def test_armed_unseen_retreat_outranks_detected_threat_preparation(self):
        breeder = replace(
            hostile(
                7, 10, 12, distance=2, can_multiply=True,
                max_melee_damage=4,
            ),
            perception="detected",
        )
        snapshot = self._corridor_snapshot([breeder])
        policy = HengbotPolicy()

        with (
            patch.object(
                policy, "_unseen_retreat_intercept_key", return_value=None
            ),
            patch.object(policy, "_unseen_retreat_key", return_value=WAIT_KEY),
            patch.object(
                policy, "_detected_threat_preparation_key",
                wraps=policy._detected_threat_preparation_key,
            ) as detected_preparation,
        ):
            key = policy.choose_key(snapshot)

        self.assertEqual(key, WAIT_KEY)
        detected_preparation.assert_not_called()
class CombatTest(unittest.TestCase):
    def test_9f_water_capture_does_not_reposition_for_choke(self):
        origin = Position(13, 105)
        positions = (
            Position(13, 119), Position(19, 122), Position(17, 122),
            Position(16, 122), Position(12, 120), Position(13, 120),
            Position(12, 119), Position(12, 118),
        )
        race_ids = (160, 70, 70, 70, 70, 70, 70, 70)
        grids = {
            Position(y, x): grid(y, x, terrain_id=1)
            for y in range(10, 22)
            for x in range(102, 124)
        }
        monsters = []
        for index, (position, race_id) in enumerate(
            zip(positions, race_ids), 1
        ):
            grids[position] = replace(
                grids[position], terrain_id=84, has_monster=True
            )
            monsters.append(hostile(
                index, position.y, position.x,
                distance=origin.distance_to(position), race_id=race_id,
                max_melee_damage=14,
            ))
        snapshot = Snapshot(
            player(origin.y, origin.x, hp=461, max_hp=461),
            grids,
            monsters,
            floor_key=(1, 9, 0),
            turn=934452,
        )
        knowledge = {
            160: MonraceKnowledge(
                10, 110, False, False, flags=frozenset({"AQUATIC"})
            ),
            70: MonraceKnowledge(
                10, 120, False, False,
                flags=frozenset({"AQUATIC", "NEVER_MOVE"}),
            ),
        }
        policy = HengbotPolicy(monrace_knowledge=knowledge)

        west_origin = Position(13, 104)
        west_snapshot = replace(
            snapshot,
            player=replace(snapshot.player, position=west_origin),
            visible_monsters=[
                replace(
                    monster,
                    distance=west_origin.distance_to(monster.position),
                )
                for monster in monsters
            ],
            turn=snapshot.turn - 1,
        )
        policy.choose_key(west_snapshot)
        policy.choose_key(snapshot)

        self.assertFalse(policy.last_reason.startswith("melee:choke"))

    def test_immobile_monsters_remain_threats_in_reach(self):
        knowledge = MonraceKnowledge(
            10, 110, False, False,
            max_melee_damage=12,
            flags=frozenset({"AQUATIC", "NEVER_MOVE"}),
        )
        monster = hostile(
            1, 10, 11, distance=1, race_id=70, max_melee_damage=12
        )
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {
                Position(10, 10): grid(10, 10, terrain_id=1),
                Position(10, 11): grid(
                    10, 11, terrain_id=84, monster=True
                ),
            },
            [monster],
            floor_key=(1, 9, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={70: knowledge})

        self.assertTrue(policy._monster_can_approach(snapshot, monster))
        self.assertGreater(
            policy.threat_prediction(snapshot, [monster])["operational_total"],
            0,
        )

    def test_aquatic_monster_remains_a_ranged_target(self):
        monster = hostile(1, 10, 13, distance=3, race_id=160)
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {
                Position(10, x): grid(
                    10, x, terrain_id=84 if x == 13 else 1,
                    monster=x == 13,
                )
                for x in range(10, 14)
            },
            [monster],
            floor_key=(1, 9, 0),
            equipment=[item("bow", TVAL_BOW, SV_BOW_SHORT, is_equipment=True)],
            inventory=[item("a", TVAL_ARROW, 1, count=10)],
        )
        policy = HengbotPolicy(monrace_knowledge={
            160: MonraceKnowledge(
                10, 110, False, False, flags=frozenset({"AQUATIC"})
            )
        })
        policy._build_grid_index(snapshot)

        self.assertIsNotNone(policy._ranged_attack_key(snapshot, [monster], []))

    @staticmethod
    def _mouse_swarm_snapshot(*, at_choke=False, adjacent=False, ranged=False):
        origin = Position(10, 9) if at_choke else Position(10, 10)
        grids = {
            Position(y, x): grid(y, x)
            for y in range(8, 13)
            for x in range(10, 13)
        }
        grids.update({
            Position(10, 8): grid(10, 8),
            Position(10, 9): grid(10, 9),
            Position(9, 9): grid(9, 9, passable=False),
            Position(11, 9): grid(11, 9, passable=False),
            Position(9, 8): grid(9, 8, passable=False),
            Position(11, 8): grid(11, 8, passable=False),
        })
        positions = (
            (
                [(10, 10), (9, 11), (10, 11), (11, 11)]
                if at_choke
                else [(10, 10), (9, 10), (11, 10), (10, 11)]
            )
            if adjacent
            else [(8, 10), (8, 11), (8, 12), (9, 12)]
        )
        if at_choke:
            grids[Position(9, 10)] = grid(9, 10, passable=False)
            grids[Position(11, 10)] = grid(11, 10, passable=False)
        monsters = [
            hostile(
                index,
                y,
                x,
                distance=origin.distance_to(Position(y, x)),
                can_multiply=True,
                max_melee_damage=1,
                max_ranged_damage=6 if ranged and index == 1 else 0,
            )
            for index, (y, x) in enumerate(positions, 1)
        ]
        for monster in monsters:
            grids[monster.position] = replace(
                grids[monster.position], has_monster=True
            )
        return Snapshot(
            player(origin.y, origin.x, hp=172, max_hp=20, level=10),
            grids,
            monsters,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )

    @staticmethod
    def _weak_breeder_incident_snapshot(*, blocking=False, turn=1):
        origin = Position(10, 10)
        positions = [
            Position(12 + index // 20, 5 + index % 20)
            for index in range(83)
        ]
        if blocking:
            positions[0] = Position(10, 11)
            positions[1] = Position(9, 10)
        grids = {
            Position(y, x): grid(y, x)
            for y in range(8, 18)
            for x in range(4, 26)
        }
        breeders = [
            hostile(
                index,
                position.y,
                position.x,
                distance=origin.distance_to(position),
                race_id=79,
                can_multiply=True,
                max_melee_damage=1,
            )
            for index, position in enumerate(positions, 1)
        ]
        for breeder in breeders:
            grids[breeder.position] = replace(
                grids[breeder.position], has_monster=True
            )
        return Snapshot(
            player(10, 10, hp=300, max_hp=300, level=13),
            grids,
            breeders,
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            turn=turn,
            width=30,
            height=30,
        )

    def test_incident_weak_breeders_make_ordinary_progress(self):
        # Since the sanctioned breakthrough fix (user decision D, 2026-08-03),
        # a latched weak-breeder floor is owned by the breakthrough: progress
        # is directed at leaving (here toward the nearest frontier, as no
        # up-stairs is remembered) instead of generic exploration.  The
        # original pins stand: no disengage replay, no fruitless latch.
        snapshot = self._weak_breeder_incident_snapshot()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        key = policy.choose_key(snapshot)

        self.assertEqual(
            (key, policy.last_reason),
            ("7", "breeder-breakthrough:seek-frontier"),
        )
        self.assertFalse(policy.last_reason.startswith("combat:disengage-"))
        self.assertNotEqual(policy.last_reason, "combat:fruitless")

    def test_darkness_does_not_block_active_breeder_recall_wait(self):
        snapshot = self._weak_breeder_incident_snapshot()
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, recalling=True),
            grids={position: replace(cell, lit=False) for position, cell in snapshot.grids.items()},
            equipment=[item(
                "light", TVAL_LITE, SV_LITE_LANTERN, fuel=0,
                known=True, is_equipment=True,
            )],
            equipment_observed=True,
        )
        policy = HengbotPolicy()
        policy._breeder_breakthrough_floor = snapshot.floor_key
        self.assertEqual(policy._breeder_breakthrough_key(snapshot, []), WAIT_KEY)
        self.assertEqual(policy.last_reason, "breeder-breakthrough:wait-recall")

    def test_2230_capture_does_not_rest_among_eighteen_weak_breeders(self):
        # 2026-07-31 22:30 incident state: HP 332/461, eighteen giant white
        # lice visible, two adjacent, and the extermination-impossible latch
        # armed.  The old strategic view was empty and selected REST_MACRO.
        base = self._weak_breeder_incident_snapshot(blocking=True)
        breeders = [
            replace(monster, race_id=69)
            for monster in base.visible_monsters[:18]
        ]
        snapshot = replace(
            base,
            player=replace(base.player, hp=332, max_hp=461),
            visible_monsters=breeders,
            floor_key=(DUNGEON_ANGBAND, 9, 0),
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key
        policy._took_damage = False

        key = policy._decide(snapshot)

        self.assertEqual(len(policy._physical_hostiles(snapshot)), 18)
        self.assertEqual(len(policy._physical_adjacent_hostiles(snapshot)), 2)
        self.assertEqual(policy._strategic_hostiles(snapshot), [])
        self.assertNotEqual((key, policy.last_reason), (REST_MACRO, "rest"))

    def test_policy_exposes_no_default_hostile_accessor(self):
        policy = HengbotPolicy()

        for ambiguous_name in (
            "_hostiles",
            "_raw_hostiles",
            "_adjacent_hostiles",
        ):
            with self.subTest(name=ambiguous_name):
                self.assertFalse(hasattr(policy, ambiguous_name))

        for explicit_name in (
            "_physical_hostiles",
            "_strategic_hostiles",
            "_physical_adjacent_hostiles",
            "_strategic_adjacent_hostiles",
            "_perceived_hostiles",
        ):
            with self.subTest(name=explicit_name):
                self.assertTrue(hasattr(policy, explicit_name))

    def test_decide_routes_physical_consumers_only_physical_views(self):
        tree = ast.parse(textwrap.dedent(inspect.getsource(HengbotPolicy._decide)))
        calls = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Attribute):
                continue
            calls.setdefault(function.attr, []).append(node)

        expected_arguments = {
            "_unseen_retreat_intercept_key": (
                "physical_hostiles", "physical_adjacent",
            ),
            "_unseen_retreat_key": ("physical_hostiles",),
            "_detected_threat_preparation_key": ("physical_hostiles",),
            "_survival_gate_key": ("physical_hostiles",),
            "_wilderness_survival_key": ("physical_hostiles",),
            "_unresisted_melee_status_threats": ("physical_hostiles",),
            "_blocking_escape_melee_key": ("physical_hostiles",),
            "_stat_restore_quaff_key": ("physical_hostiles",),
            "_stat_gain_quaff_key": ("physical_hostiles",),
            "_chest_processing_key": ("physical_hostiles",),
        }
        for consumer, required_names in expected_arguments.items():
            with self.subTest(consumer=consumer):
                self.assertIn(consumer, calls)
                for call in calls[consumer]:
                    argument_names = {
                        argument.id
                        for argument in call.args
                        if isinstance(argument, ast.Name)
                    }
                    self.assertTrue(set(required_names) <= argument_names)
                    self.assertFalse(
                        {"strategic_hostiles", "strategic_adjacent"}
                        & argument_names
                    )

        decide_names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        self.assertFalse(
            {"hostiles", "adjacent", "raw_hostiles", "raw_adjacent"}
            & decide_names
        )

    def test_only_path_blocking_weak_breeder_is_attacked(self):
        # A suppressed weak breeder is only ever attacked when it stands on
        # the breakthrough's escape route.  Here a monster-free route to the
        # frontier exists, so neither adjacent breeder may be attacked — the
        # step is the free diagonal, not "6" into (10,11) or "8" into (9,10).
        snapshot = self._weak_breeder_incident_snapshot(blocking=True)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        key = policy.choose_key(snapshot)

        self.assertEqual(
            (key, policy.last_reason),
            ("7", "breeder-breakthrough:seek-frontier"),
        )
        self.assertNotIn(key, {"6", "8"})

    def test_latched_adjacent_weak_breeders_forbid_unsanctioned_wait(self):
        base = self._weak_breeder_incident_snapshot(blocking=True)
        for sval in (SV_SCROLL_PHASE_DOOR, SV_SCROLL_TELEPORT):
            with self.subTest(sval=sval):
                snapshot = replace(
                    base,
                    inventory=[item("q", TVAL_SCROLL, sval, count=1)],
                )
                policy = HengbotPolicy()
                policy._breeder_breakthrough_floor = snapshot.floor_key
                policy._took_damage = False
                policy.last_reason = "fundraise:upstairs-not-found"

                key = policy._forbid_wait_while_damaged(snapshot, WAIT_KEY)

                self.assertNotEqual(key, WAIT_KEY)
                self.assertIn(
                    policy.last_reason,
                    {"no-wait:least-visited", "no-wait:melee"},
                )

    def test_real_capture_weak_breeders_do_not_spend_escape_scroll(self):
        capture = (
            Path(__file__).parents[1]
            / "incident-captures"
            / "20260730-1543-fundraise-loot-oscillation"
            / "last-snapshots.jsonl"
        )
        monraces = Path(
            r"C:\hengband\.worktrees\bot-json-output\lib\edit"
            r"\MonraceDefinitions.jsonc"
        )
        if not capture.is_file() or not monraces.is_file():
            self.skipTest("real fundraise oscillation capture is not available")
        knowledge = load_monrace_knowledge(monraces)
        base = parse_snapshot(
            json.loads(capture.read_text(encoding="utf-8").splitlines()[-1]),
            knowledge,
        )

        for sval in (SV_SCROLL_PHASE_DOOR, SV_SCROLL_TELEPORT):
            with self.subTest(sval=sval):
                snapshot = replace(
                    base,
                    inventory=[
                        *base.inventory,
                        item("q", TVAL_SCROLL, sval, count=1),
                    ],
                )
                policy = HengbotPolicy(monrace_knowledge=knowledge)
                policy._breeder_breakthrough_floor = snapshot.floor_key
                policy._took_damage = True
                policy.last_reason = "fundraise:upstairs-not-found"

                key = policy._forbid_wait_while_damaged(snapshot, WAIT_KEY)

                self.assertNotEqual(key, WAIT_KEY)
                self.assertNotEqual(policy.last_reason, "no-wait:escape-scroll")
                self.assertNotEqual(policy.last_reason, "no-wait:flee")

    def test_genuine_hostile_still_uses_escape_scroll_under_fire(self):
        base = self._weak_breeder_incident_snapshot(blocking=True)
        genuine = replace(
            base.visible_monsters[0],
            can_multiply=False,
        )
        snapshot = replace(
            base,
            visible_monsters=[genuine, *base.visible_monsters[1:]],
            inventory=[
                item("q", TVAL_SCROLL, SV_SCROLL_PHASE_DOOR, count=1),
            ],
        )
        for took_damage in (False, True):
            with self.subTest(took_damage=took_damage):
                policy = HengbotPolicy()
                policy._breeder_breakthrough_floor = snapshot.floor_key
                policy._took_damage = took_damage
                policy.last_reason = "fundraise:upstairs-not-found"

                key = policy._forbid_wait_while_damaged(snapshot, WAIT_KEY)

                self.assertEqual(
                    (key, policy.last_reason),
                    (READ_KEY + "q", "no-wait:escape-scroll"),
                )

    def test_choke_hold_ignores_adjacent_suppressed_weak_breeder(self):
        base = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        waiting = replace(
            base.visible_monsters[0],
            position=Position(10, 12),
            distance=2,
        )
        weak = hostile(
            99, 10, 11, distance=1, race_id=79,
            can_multiply=True, max_melee_damage=1,
        )
        grids = dict(base.grids)
        grids[waiting.position] = replace(
            grids[waiting.position], has_monster=True
        )
        grids[weak.position] = replace(
            grids[weak.position], has_monster=True
        )
        snapshot = replace(
            base,
            grids=grids,
            visible_monsters=[waiting, weak],
        )
        policy = HengbotPolicy()
        policy._breeder_breakthrough_floor = snapshot.floor_key
        policy._took_damage = False
        policy.last_reason = "melee:choke-hold"

        key = policy._forbid_wait_while_damaged(snapshot, WAIT_KEY)

        self.assertEqual((key, policy.last_reason), (
            WAIT_KEY, "melee:choke-hold",
        ))

    def test_latched_weak_breeder_is_escape_route_blocker_candidate(self):
        blocker = hostile(
            1, 10, 9, hp=6, max_hp=6, distance=1, race_id=27,
            can_multiply=True, max_melee_damage=2,
        )
        snapshot = Snapshot(
            player(
                10, 10, hp=59, max_hp=172, level=10,
                main_hand_blows=2, main_hand_to_d=5,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 9): grid(10, 9, monster=True),
                Position(10, 8): grid(10, 8),
                Position(10, 7): grid(10, 7, upstairs=True),
            },
            [blocker],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1, name="Broad Sword",
                    is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._breeder_breakthrough_floor = snapshot.floor_key
        policy._build_grid_index(snapshot)

        self.assertEqual(policy._strategic_hostiles(snapshot), [])
        self.assertEqual(
            policy._blocking_escape_melee_key(
                snapshot,
                policy._physical_hostiles(snapshot),
                policy._is_upstairs_target,
            ),
            "4",
        )

    def test_incident_wait_cycle_replay_leaves_six_cell_set(self):
        capture = (
            Path(__file__).parents[1]
            / "incident-captures"
            / "20260730-1543-fundraise-loot-oscillation"
            / "last-snapshots.jsonl"
        )
        monraces = Path(
            r"C:\hengband\.worktrees\bot-json-output\lib\edit"
            r"\MonraceDefinitions.jsonc"
        )
        if not capture.is_file() or not monraces.is_file():
            self.skipTest("real fundraise oscillation capture is not available")
        knowledge = load_monrace_knowledge(monraces)
        snapshot = parse_snapshot(
            json.loads(capture.read_text(encoding="utf-8").splitlines()[-1]),
            knowledge,
        )
        policy = HengbotPolicy(monrace_knowledge=knowledge)
        policy._fundraising_mode = "mine"
        policy._breeder_breakthrough_floor = snapshot.floor_key
        cycle = {
            Position(36, 29), Position(36, 31), Position(36, 32),
            Position(37, 30), Position(37, 33), Position(38, 33),
        }
        offsets = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }
        reasons = []

        def incident_wait(_snapshot):
            policy.last_reason = "fundraise:upstairs-not-found"
            return WAIT_KEY

        for _ in range(8):
            adjacent = any(
                snapshot.player.position.distance_to(monster.position) <= 1
                for monster in snapshot.visible_monsters
            )
            if adjacent:
                # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
                with patch.object(policy, "_decide", side_effect=incident_wait):
                    key = policy.choose_key(snapshot)
            else:
                key = policy.choose_key(snapshot)
            reasons.append(policy.last_reason)
            if key not in offsets:
                continue
            dy, dx = offsets[key]
            destination = Position(
                snapshot.player.position.y + dy,
                snapshot.player.position.x + dx,
            )
            occupant = next(
                (
                    monster for monster in snapshot.visible_monsters
                    if monster.position == destination
                ),
                None,
            )
            if occupant is not None:
                grids = dict(snapshot.grids)
                grids[destination] = replace(
                    grids[destination], has_monster=False, monster_index=0
                )
                snapshot = replace(
                    snapshot,
                    grids=grids,
                    visible_monsters=[
                        monster for monster in snapshot.visible_monsters
                        if monster.position != destination
                    ],
                    turn=snapshot.turn + 1,
                )
            else:
                snapshot = replace(
                    snapshot,
                    player=replace(snapshot.player, position=destination),
                    turn=snapshot.turn + 1,
                )
            if snapshot.player.position not in cycle:
                break

        self.assertEqual(reasons[:2], ["no-wait:melee", "no-wait:melee"])
        self.assertNotIn(snapshot.player.position, cycle)

    @staticmethod
    def _forest_1616_breakthrough_snapshot():
        # 2026-08-03 16:16 Forest (dungeon 7) 20F stop, reconstructed from the
        # capture: player (17,55) at HP 615/615 in a pocket whose every open
        # neighbour is breeder-occupied, six weak breeders (race 156,
        # max_melee_damage 5 < 615 * WEAK_BREEDER_MAX_DAMAGE_RATIO 0.05), the
        # extermination latch armed for floor (7, 20, 0), and the up-stairs
        # remembered at (6, 68).  The pocket cells match the loop guard's
        # confinement set; the only escape route leaves through the adjacent
        # breeder at (18, 55).
        origin = Position(17, 55)
        pocket = [
            Position(16, 53), Position(17, 53), Position(18, 53),
            Position(17, 54), Position(18, 54), Position(18, 55),
        ]
        corridor = [
            Position(19, 56), Position(19, 57), Position(18, 58),
            Position(17, 59), Position(16, 60), Position(15, 61),
            Position(14, 62), Position(13, 63), Position(12, 64),
            Position(11, 65), Position(10, 66), Position(9, 67),
            Position(8, 68), Position(7, 68),
        ]
        upstairs = Position(6, 68)
        floor_cells = [origin, *pocket, *corridor]
        grids = {
            position: grid(position.y, position.x)
            for position in floor_cells
        }
        grids[upstairs] = grid(upstairs.y, upstairs.x, upstairs=True)
        for position in [*floor_cells, upstairs]:
            for dy, dx in (
                (-1, -1), (-1, 0), (-1, 1), (0, -1),
                (0, 1), (1, -1), (1, 0), (1, 1),
            ):
                wall = Position(position.y + dy, position.x + dx)
                if wall not in grids:
                    grids[wall] = grid(wall.y, wall.x, passable=False)
        breeders = [
            hostile(
                index, position.y, position.x,
                hp=15, max_hp=15,
                distance=origin.distance_to(position),
                race_id=156, can_multiply=True, max_melee_damage=5,
            )
            for index, position in enumerate(
                [
                    Position(17, 54), Position(18, 54), Position(18, 55),
                    Position(16, 53), Position(17, 53), Position(18, 53),
                ],
                1,
            )
        ]
        for breeder in breeders:
            grids[breeder.position] = replace(
                grids[breeder.position], has_monster=True
            )
        return Snapshot(
            player(
                origin.y, origin.x, hp=615, max_hp=615, level=30,
                main_hand_blows=3, main_hand_to_d=9,
            ),
            grids,
            breeders,
            floor_key=(7, 20, 0),
            turn=1,
            width=198,
            height=66,
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1, name="Broad Sword",
                    is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
                )
            ],
        )

    def test_forest_1616_weak_breeder_latch_executes_breakthrough(self):
        # The user's decision D: the breakthrough was selected (the latch
        # fired) but the bot never acted on it — every decision degraded to
        # no-wait:melee in the pocket.  Drive the public choose_key path
        # across the whole escape and require breakthrough intent throughout.
        snapshot = self._forest_1616_breakthrough_snapshot()
        upstairs = Position(6, 68)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key
        # The stopped session had already burned its stationary searches at
        # the pocket (reasons: search x16 before the stop); reconstruct that
        # exhaustion so the pre-fix ladder reaches its WAIT rewrite at once.
        policy._search_counts[(17, 55)] = SEARCH_LIMIT
        offsets = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }
        distances = [snapshot.player.position.distance_to(upstairs)]
        attacked = []
        reasons = []

        for _ in range(40):
            key = policy.choose_key(snapshot)
            reasons.append(policy.last_reason)
            self.assertTrue(
                policy.last_reason.startswith("breeder-breakthrough:"),
                f"decision {len(reasons)}: reason {policy.last_reason!r} "
                f"(key {key!r}) is not a breakthrough decision",
            )
            if key == UP_STAIRS_KEY:
                break
            self.assertIn(key, offsets)
            dy, dx = offsets[key]
            destination = Position(
                snapshot.player.position.y + dy,
                snapshot.player.position.x + dx,
            )
            destination_grid = snapshot.grid_at(destination)
            if destination_grid is not None and destination_grid.has_monster:
                attacked.append(destination)
                grids = dict(snapshot.grids)
                grids[destination] = replace(
                    destination_grid, has_monster=False
                )
                snapshot = replace(
                    snapshot,
                    grids=grids,
                    visible_monsters=[
                        monster
                        for monster in snapshot.visible_monsters
                        if monster.position != destination
                    ],
                    turn=snapshot.turn + 1,
                )
            else:
                snapshot = replace(
                    snapshot,
                    player=replace(snapshot.player, position=destination),
                    turn=snapshot.turn + 1,
                )
                distances.append(
                    snapshot.player.position.distance_to(upstairs)
                )

        self.assertEqual(key, UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "breeder-breakthrough:ascend")
        self.assertEqual(snapshot.player.position, upstairs)
        self.assertGreaterEqual(len(reasons), 3)
        # Purposeful melee only: the single monster attacked is the blocker
        # on the escape route, never the adjacent off-route breeders at
        # (17,54)/(18,54).
        self.assertEqual(attacked, [Position(18, 55)])
        # The distance to the upstairs never increases, and strictly
        # decreases across (far more than) three consecutive decisions.
        self.assertTrue(
            all(b <= a for a, b in zip(distances, distances[1:])),
            distances,
        )
        strict_run = longest = 0
        for earlier, later in zip(distances, distances[1:]):
            strict_run = strict_run + 1 if later < earlier else 0
            longest = max(longest, strict_run)
        self.assertGreaterEqual(longest, 3)
        self.assertEqual(distances[-1], 0)

    def test_forest_20_latched_breakthrough_reads_bound_recall_scroll(self):
        """Real-capture reconstruction: recall owns the public decision."""
        snapshot = replace(
            self._forest_1616_breakthrough_snapshot(),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        key = policy.choose_key(snapshot)

        self.assertEqual(key, READ_KEY + "r")
        self.assertEqual(policy.last_reason, "breeder-breakthrough:recall")
        self.assertIsNotNone(policy._read_binding)
        self.assertEqual(policy._read_binding[1], SV_SCROLL_WORD_OF_RECALL)
        self.assertEqual(policy._read_binding[3], "r")

    @staticmethod
    def _latched_breeder_stair_snapshot(*, depth=20, inventory=(), quests=None):
        position = Position(10, 10)
        return Snapshot(
            player(
                10, 10, hp=615, max_hp=615, level=30,
                abilities=frozenset({"free_action", "resist_fire"}),
            ),
            {position: grid(10, 10, upstairs=True)},
            [],
            floor_key=(7, depth, 0 if quests is None else 49),
            turn=depth,
            inventory=list(inventory),
            quests=quests or {},
        )

    def test_breeder_stair_escape_walks_out_without_redescending_fled_floor(self):
        policy = HengbotPolicy()
        floor_20 = self._latched_breeder_stair_snapshot()
        policy._floor_key = floor_20.floor_key
        policy._breeder_breakthrough_floor = floor_20.floor_key

        self.assertEqual(policy.choose_key(floor_20), UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "breeder-breakthrough:ascend")

        # On the next emitted floor the arrival terrain is a down-stair and a
        # distinct adjacent terrain is the up-stair. Once the ascent's existing
        # descent deferral expires, the parent chooses '>' and recreates the
        # breeder floor; the fled-floor fact keeps owning the upward walk.
        floor_19 = replace(
            floor_20,
            grids={
                Position(10, 10): grid(10, 10, downstairs=True),
                Position(10, 9): grid(10, 9, upstairs=True),
            },
            floor_key=(7, 19, 0),
            turn=21,
        )
        keys = []
        for decision in range(201):
            # Model fresh emitted coverage while the native move is pending.
            # That keeps this proof about the real post-ascent descent gate,
            # rather than letting a synthetic frozen snapshot trip livelock.
            revealed = Position(1 + decision // 100, 1 + decision % 100)
            floor_19 = replace(
                floor_19,
                grids={**floor_19.grids, revealed: grid(revealed.y, revealed.x)},
                turn=21 + decision,
            )
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            keys.append(policy.choose_key(floor_19))
        self.assertNotIn(
            policy_module.DOWN_STAIRS_KEY,
            keys,
            "a fled breeder floor must not be re-entered from its parent",
        )
        self.assertEqual(keys[0], "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

        # The observation that town was reached ends the fact-based avoidance;
        # town's ordinary entry policy remains a concrete future descent exit.
        town = replace(
            floor_19,
            player=replace(floor_19.player, position=Position(1, 1)),
            grids={Position(1, 1): grid(1, 1)},
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=floor_19.turn + 1,
        )
        policy.choose_key(town)
        self.assertIsNone(policy._breeder_fled_floor)

    def test_breeder_recall_read_waits_for_exported_flag_confirmation(self):
        recall = item(
            "r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=2
        )
        snapshot = replace(
            self._forest_1616_breakthrough_snapshot(), inventory=[recall]
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        self.assertEqual(policy.choose_key(snapshot), READ_KEY + "r")
        consumed = replace(
            snapshot, turn=snapshot.turn + 1,
            inventory=[replace(recall, count=1)],
        )
        self.assertEqual(
            policy.choose_key(consumed), WAIT_KEY,
            "a lagging recalling flag must not consume a second recall scroll",
        )
        self.assertEqual(
            policy.last_reason, "return:await-recall-confirmation"
        )

    def test_breeder_walkout_yields_to_starvation_gate(self):
        food = item("f", TVAL_FOOD, FOOD)
        snapshot = Snapshot(
            player(10, 10, hp=615, max_hp=615, level=30, food=1500),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(7, 19, 0),
            turn=21,
            inventory=[food],
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_fled_floor = (7, 20, 0)

        self.assertEqual(
            policy.choose_key(snapshot), "Ef",
            "a breeder walkout must not starve the survival gate",
        )
        self.assertEqual(policy.last_reason, "survival:eat")

    def test_breeder_walkout_keeps_navigation_livelock_exit_reachable(self):
        position = Position(10, 10)
        snapshot = Snapshot(
            player(10, 10, hp=615, max_hp=615, level=30),
            {position: grid(10, 10)},
            [],
            floor_key=(7, 19, 0),
            turn=21,
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_fled_floor = (7, 20, 0)

        reasons = []
        for _ in range(2500):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            policy.choose_key(snapshot)
            reasons.append(policy.last_reason)

        self.assertTrue(
            any(reason.startswith("livelock:") for reason in reasons),
            "a fled-floor walkout must leave the navigation-livelock exit reachable",
        )
        self.assertGreater(
            policy._nav_escape_steps, 0,
            "the navigation-livelock owner must fire while the fled fact is set",
        )

    def test_breeder_walkout_never_redescends_for_any_escape_owner(self):
        snapshot = Snapshot(
            player(10, 10, hp=615, max_hp=615, level=30),
            {
                Position(10, 10): grid(10, 10, downstairs=True),
                Position(10, 9): grid(10, 9),
            },
            [],
            floor_key=(7, 19, 0),
            turn=21,
        )
        for owner in (None, "return", "disengage", "unseen", "emergency"):
            with self.subTest(owner=owner):
                policy = HengbotPolicy()
                policy._floor_key = snapshot.floor_key
                policy._breeder_fled_floor = (7, 20, 0)
                policy._escape_state.floor = snapshot.floor_key
                if owner is not None:
                    policy._escape_state.enter(owner, f"{owner}:active")

                keys = []
                reasons = []
                current = snapshot
                for decision in range(60):
                    # Fresh observed coverage keeps this focused on the
                    # descent constraint while each owner is exercised over
                    # multiple public decisions, rather than handing control
                    # to the separately-tested navigation-livelock rung.
                    revealed = Position(1, 1 + decision)
                    current = replace(
                        current,
                        grids={
                            **current.grids,
                            revealed: grid(revealed.y, revealed.x),
                        },
                        turn=current.turn + 1,
                    )
                    keys.append(policy.choose_key(current))
                    reasons.append(policy.last_reason)

                self.assertNotIn(
                    policy_module.DOWN_STAIRS_KEY,
                    keys,
                    f"owner {owner!r} must not permit breeder-floor re-entry",
                )
                self.assertNotIn(
                    "descend",
                    reasons,
                    f"owner {owner!r} must not reach the descent decision",
                )
                if owner == "disengage":
                    self.assertFalse(
                        reasons[0].startswith("return:"),
                        "the walkout must not replace the active disengage owner",
                    )

    def test_active_random_quest_keeps_breeder_stair_exit_and_does_not_recall(self):
        quest = QuestState(
            id=49,
            status=QUEST_STATUS_TAKEN,
            type=QUEST_TYPE_RANDOM,
            level=20,
            dungeon_id=7,
            cur_num=0,
            max_num=1,
        )
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snapshot = self._latched_breeder_stair_snapshot(
            inventory=[recall], quests={49: quest}
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        self.assertEqual(policy.choose_key(snapshot), UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "breeder-breakthrough:ascend")
        self.assertIsNone(policy._breeder_fled_floor)

    def test_latched_mining_walks_upstairs_without_spending_recall(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snapshot = self._latched_breeder_stair_snapshot(inventory=[recall])
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        self.assertEqual(policy.choose_key(snapshot), UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "fundraise:ascend")
        self.assertIsNone(policy._dungeon_recall_issue_watch)

    def test_breakthrough_attacks_route_blocker_not_weakest_adjacent(self):
        # Two adjacent weak breeders: one stands on the remembered route to
        # the upstairs, the other (deliberately the weaker one, which the
        # pre-fix no-wait:melee rewrite would pick) sits in a dead-end off
        # the route.  Only the route blocker may be attacked.
        origin = Position(10, 10)
        upstairs = Position(10, 7)
        floor_cells = [
            origin, Position(10, 9), Position(10, 8), Position(9, 11),
        ]
        grids = {
            position: grid(position.y, position.x)
            for position in floor_cells
        }
        grids[upstairs] = grid(upstairs.y, upstairs.x, upstairs=True)
        for position in [*floor_cells, upstairs]:
            for dy, dx in (
                (-1, -1), (-1, 0), (-1, 1), (0, -1),
                (0, 1), (1, -1), (1, 0), (1, 1),
            ):
                wall = Position(position.y + dy, position.x + dx)
                if wall not in grids:
                    grids[wall] = grid(wall.y, wall.x, passable=False)
        blocker = hostile(
            1, 10, 9, hp=15, max_hp=15, distance=1, race_id=156,
            can_multiply=True, max_melee_damage=5,
        )
        bystander = hostile(
            2, 9, 11, hp=3, max_hp=3, distance=1, race_id=156,
            can_multiply=True, max_melee_damage=5,
        )
        for monster in (blocker, bystander):
            grids[monster.position] = replace(
                grids[monster.position], has_monster=True
            )
        snapshot = Snapshot(
            player(
                origin.y, origin.x, hp=615, max_hp=615, level=30,
                main_hand_blows=3, main_hand_to_d=9,
            ),
            grids,
            [blocker, bystander],
            floor_key=(7, 20, 0),
            turn=1,
            width=30,
            height=30,
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1, name="Broad Sword",
                    is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key
        policy._search_counts[(10, 10)] = SEARCH_LIMIT

        key = policy.choose_key(snapshot)

        self.assertEqual(
            (key, policy.last_reason),
            ("4", "breeder-breakthrough:clear-escape-path"),
        )
        self.assertNotEqual(key, "9")  # never the weaker off-route breeder

        # Blocker down: the remaining decisions walk the route and ascend.
        grids = dict(snapshot.grids)
        grids[blocker.position] = replace(
            grids[blocker.position], has_monster=False
        )
        snapshot = replace(
            snapshot, grids=grids, visible_monsters=[bystander], turn=2
        )
        for expected in (Position(10, 9), Position(10, 8), Position(10, 7)):
            self.assertEqual(policy.choose_key(snapshot), "4")
            self.assertEqual(
                policy.last_reason, "breeder-breakthrough:seek-upstairs"
            )
            snapshot = replace(
                snapshot,
                player=replace(snapshot.player, position=expected),
                turn=snapshot.turn + 1,
            )
        self.assertEqual(policy.choose_key(snapshot), UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "breeder-breakthrough:ascend")

    @staticmethod
    def _no_upstairs_pocket_snapshot(*, blocker_damage=5):
        # A sealed pocket with no remembered up-stairs: every neighbour of
        # the player is a wall except the corridor cell (10,9), which holds a
        # breeder.  The corridor ends at a frontier tile (10,5) bordering
        # unknown terrain at (10,4).
        origin = Position(10, 10)
        corridor = [
            Position(10, 9), Position(10, 8), Position(10, 7),
            Position(10, 6), Position(10, 5),
        ]
        grids = {
            position: grid(position.y, position.x)
            for position in [origin, *corridor]
        }
        unknown = Position(10, 4)
        for position in [origin, *corridor]:
            for dy, dx in (
                (-1, -1), (-1, 0), (-1, 1), (0, -1),
                (0, 1), (1, -1), (1, 0), (1, 1),
            ):
                wall = Position(position.y + dy, position.x + dx)
                if wall not in grids and wall != unknown:
                    grids[wall] = grid(wall.y, wall.x, passable=False)
        blocker = hostile(
            1, 10, 9, hp=15, max_hp=15, distance=1, race_id=156,
            can_multiply=True, max_melee_damage=blocker_damage,
        )
        grids[blocker.position] = replace(
            grids[blocker.position], has_monster=True
        )
        snapshot = Snapshot(
            player(
                origin.y, origin.x, hp=615, max_hp=615, level=30,
                main_hand_blows=3, main_hand_to_d=9,
            ),
            grids,
            [blocker],
            floor_key=(7, 20, 0),
            turn=1,
            width=30,
            height=30,
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1, name="Broad Sword",
                    is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
                )
            ],
        )
        return snapshot, corridor, unknown, blocker

    def test_breakthrough_without_known_upstairs_seeks_frontier_not_wait(self):
        # With the strong-breeder gate removed the upstairs-not-found branch
        # is reachable in the weak-breeder case; it must have a concrete exit:
        # route through the swarm to the nearest remembered frontier, let the
        # arrival reveal terrain, and hand over to the upstairs route the
        # moment one is discovered.
        snapshot, corridor, unknown, blocker = (
            self._no_upstairs_pocket_snapshot()
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key
        policy._search_counts[(10, 10)] = SEARCH_LIMIT

        key = policy.choose_key(snapshot)
        self.assertEqual(
            (key, policy.last_reason),
            ("4", "breeder-breakthrough:clear-escape-path"),
        )
        self.assertNotEqual(key, WAIT_KEY)

        grids = dict(snapshot.grids)
        grids[blocker.position] = replace(
            grids[blocker.position], has_monster=False
        )
        snapshot = replace(snapshot, grids=grids, visible_monsters=[], turn=2)
        for expected in corridor[:4]:
            self.assertEqual(policy.choose_key(snapshot), "4")
            self.assertEqual(
                policy.last_reason, "breeder-breakthrough:seek-frontier"
            )
            snapshot = replace(
                snapshot,
                player=replace(snapshot.player, position=expected),
                turn=snapshot.turn + 1,
            )

        # Step onto the frontier tile itself.
        self.assertEqual(policy.choose_key(snapshot), "4")
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-frontier"
        )
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, position=Position(10, 5)),
            turn=snapshot.turn + 1,
        )
        # The player now stands orthogonally adjacent to the unknown tile
        # with its light on it, so the game marks that one tile (radius-1
        # reveal — nothing beyond it): the corridor continues.
        grids = dict(snapshot.grids)
        grids[unknown] = grid(unknown.y, unknown.x)
        for wall in (Position(9, 4), Position(11, 4)):
            grids[wall] = grid(wall.y, wall.x, passable=False)
        snapshot = replace(snapshot, grids=grids)

        # The old goal stopped being a frontier (its unknown neighbour was
        # revealed), so nothing is retired; the next frontier is the newly
        # revealed tile.
        self.assertEqual(policy.choose_key(snapshot), "4")
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-frontier"
        )
        self.assertNotIn(Position(10, 5), policy._probed_frontiers)
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, position=unknown),
            turn=snapshot.turn + 1,
        )
        # The same radius-1 reveal from (10,4) uncovers the up-stairs, and
        # the discovery flips the breakthrough onto the upstairs route.
        revealed_stairs = Position(10, 3)
        grids = dict(snapshot.grids)
        grids[revealed_stairs] = grid(
            revealed_stairs.y, revealed_stairs.x, upstairs=True
        )
        for wall in (Position(9, 3), Position(11, 3)):
            grids[wall] = grid(wall.y, wall.x, passable=False)
        snapshot = replace(snapshot, grids=grids)

        self.assertEqual(policy.choose_key(snapshot), "4")
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-upstairs"
        )
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, position=revealed_stairs),
            turn=snapshot.turn + 1,
        )
        self.assertEqual(policy.choose_key(snapshot), UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "breeder-breakthrough:ascend")

    def test_strong_multiplied_breeders_keep_existing_breakthrough(self):
        # The original regression state: strong breeders, NO known up-stairs.
        # Before the fix this state was the absorbing upstairs-not-found WAIT
        # (rewritten by the no-wait ladder into melee); it is now pinned to
        # the intended non-WAIT behaviour — clear the route blocker and head
        # for undiscovered terrain.
        snapshot, corridor, unknown, blocker = (
            self._no_upstairs_pocket_snapshot(blocker_damage=31)
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key
        policy._search_counts[(10, 10)] = SEARCH_LIMIT

        # 31 >= 615 * WEAK_BREEDER_MAX_DAMAGE_RATIO: the blocker is strong.
        self.assertEqual(len(policy._strategic_hostiles(snapshot)), 1)
        key = policy.choose_key(snapshot)
        self.assertEqual(
            (key, policy.last_reason),
            ("4", "breeder-breakthrough:clear-escape-path"),
        )

        grids = dict(snapshot.grids)
        grids[blocker.position] = replace(
            grids[blocker.position], has_monster=False
        )
        snapshot = replace(snapshot, grids=grids, visible_monsters=[], turn=2)
        for expected in corridor[:3]:
            self.assertEqual(policy.choose_key(snapshot), "4")
            self.assertEqual(
                policy.last_reason, "breeder-breakthrough:seek-frontier"
            )
            snapshot = replace(
                snapshot,
                player=replace(snapshot.player, position=expected),
                turn=snapshot.turn + 1,
            )

    def test_strong_breeder_with_known_upstairs_route_unchanged(self):
        # Strong-breeder escape with a remembered up-stairs is byte-for-byte
        # what it was before the gate removal: the route blocker is cleared
        # and the route is walked.  This pin deliberately also passes on the
        # pre-fix parent (only the blocker is strong — a fully lethal swarm
        # belongs to the emergency ladder, before and after alike).
        snapshot = self._forest_1616_breakthrough_snapshot()
        strong = [
            replace(monster, max_melee_damage=31)
            if monster.position == Position(18, 55)
            else monster
            for monster in snapshot.visible_monsters
        ]
        snapshot = replace(snapshot, visible_monsters=strong)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        key = policy.choose_key(snapshot)

        self.assertEqual(
            (key, policy.last_reason),
            ("2", "breeder-breakthrough:clear-escape-path"),
        )

    def test_latched_mining_terminal_wait_becomes_breakthrough_escape(self):
        # A latched mine floor with only weak breeders defers to the
        # fundraising exit, but that exit's terminal (no recall to wait on,
        # no reachable stairs, nothing to explore/wander/dig) used to be the
        # absorbing fundraise:upstairs-not-found WAIT.  The _decide site now
        # backstops exactly that terminal with the breakthrough's own exits.
        snapshot, corridor, unknown, blocker = (
            self._no_upstairs_pocket_snapshot()
        )
        snapshot = replace(snapshot, floor_key=(DUNGEON_YEEK_CAVE, 1, 0))
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key
        policy._search_counts[(10, 10)] = SEARCH_LIMIT

        key = policy.choose_key(snapshot)
        self.assertEqual(
            (key, policy.last_reason),
            ("4", "breeder-breakthrough:clear-escape-path"),
        )

        # Once the blocker is down the fundraising exit has a real action
        # again (exploration toward the frontier), so the backstop steps
        # aside and mining keeps its own reviewed exit.
        grids = dict(snapshot.grids)
        grids[blocker.position] = replace(
            grids[blocker.position], has_monster=False
        )
        snapshot = replace(snapshot, grids=grids, visible_monsters=[], turn=2)
        self.assertEqual(policy.choose_key(snapshot), "4")
        self.assertNotEqual(
            policy.last_reason, "fundraise:upstairs-not-found"
        )
        self.assertFalse(
            policy.last_reason.startswith("breeder-breakthrough:")
        )

    @staticmethod
    def _occluded_frontier_snapshot(*, lit=True, blind=False, inventory=(),
                                    monsters=()):
        # Two frontier tiles whose unknown neighbours sit diagonally behind
        # wall corners — tiles the game legitimately does not memorize from
        # the frontier itself — plus a known downstairs as the ordinary
        # ladder's exit once the frontier candidates are exhausted.
        origin = Position(10, 10)
        floors = [
            origin,
            Position(10, 9), Position(10, 8),   # west arm, frontier (10,8)
            Position(10, 11), Position(10, 12),  # east arm, frontier (10,12)
            Position(11, 10), Position(12, 10),  # south arm to downstairs
        ]
        unknowns = {Position(9, 7), Position(9, 13)}
        grids = {
            position: grid(position.y, position.x, lit=lit)
            for position in floors
        }
        grids[Position(12, 10)] = grid(12, 10, downstairs=True, lit=lit)
        for position in floors:
            for dy, dx in (
                (-1, -1), (-1, 0), (-1, 1), (0, -1),
                (0, 1), (1, -1), (1, 0), (1, 1),
            ):
                wall = Position(position.y + dy, position.x + dx)
                if wall not in grids and wall not in unknowns:
                    grids[wall] = grid(wall.y, wall.x, passable=False)
        for monster in monsters:
            grids[monster.position] = replace(
                grids[monster.position], has_monster=True
            )
        return Snapshot(
            player(
                origin.y, origin.x, hp=615, max_hp=615, level=30,
                blind=blind,
            ),
            grids,
            list(monsters),
            floor_key=(7, 20, 0),
            turn=1,
            width=30,
            height=30,
            inventory=list(inventory),
        )

    def test_dark_frontier_revisits_exhaust_via_preexisting_visit_bound(self):
        # A capable (non-blind, lit) arrival cannot leave an adjacent tile
        # unknown — update_lite lights all eight neighbours
        # (specific-object/torch.cpp:159-175) and the emitter's only filter
        # is perceivability — so no arrival-retirement branch exists.  In
        # this EMITTABLE dark scenario (lampless; both unknowns are occluded
        # diagonals that legitimately stay unknown) the only frontier
        # exclusion is the pre-existing FRONTIER_EXHAUST_VISITS visit
        # bound: the breakthrough bounces between the two candidates until
        # the bound retires them, then hands the exhausted floor to the
        # ordinary ladder.  Fails on 0e2a441, whose unconditional
        # arrival-retirement discards the frontier at first arrival.
        snapshot = self._occluded_frontier_snapshot(lit=False)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key
        offsets = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }

        snapshot = self._walk_to_first_frontier(policy, snapshot)
        key = policy.choose_key(snapshot)
        # The first dark arrival must NOT retire the frontier.
        self.assertNotIn(Position(10, 8), policy._probed_frontiers)
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-frontier"
        )

        for _ in range(200):
            if not policy.last_reason.startswith("breeder-breakthrough:"):
                break
            self.assertIn(key, offsets)
            dy, dx = offsets[key]
            snapshot = replace(
                snapshot,
                player=replace(
                    snapshot.player,
                    position=Position(
                        snapshot.player.position.y + dy,
                        snapshot.player.position.x + dx,
                    ),
                ),
                turn=snapshot.turn + 1,
            )
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            key = policy.choose_key(snapshot)

        # The west frontier was retired by the pre-existing visit bound
        # (_is_frontier's FRONTIER_EXHAUST_VISITS branch), never by an
        # arrival; with the bot standing on the last remaining candidate
        # the breakthrough has no other goal and hands off to the ordinary
        # ladder, which claims a real action — no WAIT.
        self.assertIn(Position(10, 8), policy._probed_frontiers)
        self.assertEqual(policy.last_reason, "seek-downstairs")
        self.assertNotEqual(key, WAIT_KEY)

    def _walk_to_first_frontier(self, policy, snapshot):
        for expected in (Position(10, 9), Position(10, 8)):
            self.assertEqual(policy.choose_key(snapshot), "4")
            self.assertEqual(
                policy.last_reason, "breeder-breakthrough:seek-frontier"
            )
            snapshot = replace(
                snapshot,
                player=replace(snapshot.player, position=expected),
                turn=snapshot.turn + 1,
            )
        return snapshot

    def test_blind_arrival_does_not_retire_frontier(self):
        # bot-json-output.cpp:118 emits every non-REMEMBER grid unknown
        # while the player is blind, before light flags are consulted: a
        # blind arrival was incapable of revealing anything, so the frontier
        # must survive (a status cure can reveal from this very tile later).
        # The stale lit flag on the remembered square must not override the
        # blindness veto.
        snapshot = self._occluded_frontier_snapshot(lit=True, blind=True)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        snapshot = self._walk_to_first_frontier(policy, snapshot)
        key = policy.choose_key(snapshot)

        self.assertNotIn(Position(10, 8), policy._probed_frontiers)
        self.assertEqual(key, "6")
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-frontier"
        )

    def test_unlit_arrival_does_not_retire_frontier(self):
        # The emitted lite flag is grid.is_lite() — CAVE_LITE, player light
        # only (bot-json-output.cpp:191).  Its absence on the player's own
        # square means light radius 0 (cave-map.cpp update_lite): the
        # arrival could not have revealed the neighbour, so the frontier
        # must survive for a re-visit after the light is repaired.
        snapshot = self._occluded_frontier_snapshot(lit=False)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        snapshot = self._walk_to_first_frontier(policy, snapshot)
        key = policy.choose_key(snapshot)

        self.assertNotIn(Position(10, 8), policy._probed_frontiers)
        self.assertEqual(key, "6")
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-frontier"
        )

    def test_monster_lit_arrival_does_not_retire_frontier(self):
        # Grids can be known through transient monster light (CAVE_MNLT,
        # cleared and recomputed as monsters move, floor-info.cpp:690-719),
        # but the emitted lite flag never includes it — so an arrival that
        # only a nearby monster's torch made possible fails the capability
        # test and the frontier survives: the monster moving later can
        # reveal the neighbour from this same tile.
        lantern_bearer = hostile(
            1, 11, 10, hp=15, max_hp=15, distance=1, race_id=156,
            can_multiply=True, max_melee_damage=5,
        )
        snapshot = self._occluded_frontier_snapshot(
            lit=False, monsters=[lantern_bearer]
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        snapshot = self._walk_to_first_frontier(policy, snapshot)
        policy.choose_key(snapshot)

        self.assertNotIn(Position(10, 8), policy._probed_frontiers)
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-frontier"
        )

    def test_unlit_frontier_walk_yields_to_darkness_recovery(self):
        # INTENTIONAL unchanged-behaviour pin — deliberately also green on
        # the parent commit, exactly like
        # test_strong_breeder_with_known_upstairs_route_unchanged: it
        # documents (does not introduce) that the rung owning a broken
        # light precondition is the pre-existing _darkness_recovery_key,
        # consulted above the breakthrough in _decide — with a torch in the
        # pack it claims the decision before any frontier routing, so a
        # dark frontier walk cannot become a stall.
        snapshot = self._occluded_frontier_snapshot(
            lit=False,
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=5000)
            ],
        )
        snapshot = replace(snapshot, grids_observed=True)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key

        policy.choose_key(snapshot)

        self.assertEqual(policy.last_reason, "wield-light")

    def test_no_frontier_goal_tracking_state_remains(self):
        # The arrival-retirement bookkeeping was deleted outright: the C++
        # chain proves a capable arrival cannot leave an adjacent tile
        # unknown (update_lite lights all eight neighbours,
        # specific-object/torch.cpp:159-175; the emitter's only filter is
        # is_grid_perceivable; a wall beside the player's floor square
        # always passes is_revealed_wall, display-map.cpp:92), so the
        # "capable but still unknown" state the branch fired on is not
        # emittable.  Deleting the goal state also deletes the stale-goal
        # defect on a reused floor key.  This structural pin is the
        # deletion's revert-proof: it fails while the dead bookkeeping
        # exists.
        self.assertFalse(
            hasattr(HengbotPolicy(), "_breakthrough_frontier_goal")
        )

    def test_weak_breeder_replay_does_not_drain_disengage_allowance(self):
        # The latched floor is now owned by the breakthrough, which sits
        # above the disengage rung — so a weak-breeder replay can never spend
        # the fruitless allowance, and the untouched allowance decays every
        # decision instead of being drained toward the combat:fruitless stop.
        policy = HengbotPolicy()
        base = self._weak_breeder_incident_snapshot()
        policy._floor_key = base.floor_key
        policy._breeder_breakthrough_floor = base.floor_key
        policy._fruitless_disengage_floor = base.floor_key
        policy._fruitless_disengage_decisions = 99
        reasons = []

        for turn in range(1, 7):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            key = policy.choose_key(replace(base, turn=turn))
            reasons.append(policy.last_reason)
            self.assertNotEqual(key, WAIT_KEY)

        self.assertLess(policy._fruitless_disengage_decisions, 99)
        self.assertTrue(
            all(
                reason.startswith("breeder-breakthrough:")
                for reason in reasons
            )
        )
        self.assertNotIn("combat:fruitless", reasons)

    @staticmethod
    def _small_breeder_group_snapshot(*, adjacent=False, ranged=True, exp=0):
        origin = Position(10, 10)
        positions = (
            [Position(10, 11), Position(9, 12)]
            if adjacent
            else [Position(10, 12), Position(9, 12)]
        )
        grids = {
            Position(y, x): grid(y, x)
            for y in range(8, 13)
            for x in range(8, 14)
        }
        breeders = [
            hostile(
                index,
                position.y,
                position.x,
                distance=origin.distance_to(position),
                race_id=27,
                can_multiply=True,
                max_melee_damage=1,
            )
            for index, position in enumerate(positions, 1)
        ]
        for breeder in breeders:
            grids[breeder.position] = replace(
                grids[breeder.position], has_monster=True
            )
        equipment = [
            item(
                "main_hand", TVAL_SWORD, 1, name="Broad Sword",
                is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
            )
        ]
        inventory = []
        if ranged:
            equipment.append(
                item("bow", TVAL_BOW, SV_BOW_SHORT, is_equipment=True)
            )
            inventory.append(item("a", TVAL_ARROW, 1, count=20))
        return Snapshot(
            replace(
                player(
                    origin.y, origin.x, hp=100, max_hp=100, level=10,
                    main_hand_blows=2, main_hand_to_d=5,
                ),
                exp=exp,
            ),
            grids,
            breeders,
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            equipment=equipment,
            inventory=inventory,
        )

    def test_small_breeder_group_is_preempted_with_ranged_weapon(self):
        policy = HengbotPolicy()
        snapshot = self._small_breeder_group_snapshot()

        key = policy.choose_key(snapshot)

        self.assertTrue(key.startswith("fa"))
        self.assertTrue(policy.last_reason.startswith("ranged:"))

    def test_small_breeder_group_closes_for_melee_without_ranged_option(self):
        policy = HengbotPolicy()
        snapshot = self._small_breeder_group_snapshot(
            adjacent=True, ranged=False
        )

        key = policy.choose_key(snapshot)

        self.assertIn(key, {"7", "8", "9", "4", "6", "1", "2", "3"})
        self.assertTrue(policy.last_reason.startswith("melee"))

    def test_breeder_latch_requires_five_kills_and_growth(self):
        base = self._small_breeder_group_snapshot(ranged=False)

        def observe_kills(policy, count, visible_count):
            current = base
            policy._update_combat_outcome(current)
            for kill in range(1, count + 1):
                policy.last_reason = "melee"
                breeders = [
                    replace(monster, index=100 * kill + index)
                    for index, monster in enumerate(
                        (
                            base.visible_monsters
                            * ((visible_count + 1) // 2)
                        )[:visible_count],
                        1,
                    )
                ]
                current = replace(
                    base,
                    player=replace(base.player, exp=kill),
                    visible_monsters=breeders,
                )
                policy._update_combat_outcome(current)
            return current

        four_kills = HengbotPolicy()
        observe_kills(four_kills, 4, 3)
        self.assertIsNone(four_kills._breeder_breakthrough_floor)

        no_growth = HengbotPolicy()
        observe_kills(no_growth, 5, 2)
        self.assertIsNone(no_growth._breeder_breakthrough_floor)

        grown = HengbotPolicy()
        grown_snapshot = observe_kills(grown, 5, 3)
        self.assertEqual(
            grown._breeder_breakthrough_floor, grown_snapshot.floor_key
        )

    def test_breeder_stalemate_timeout_ends_mining_through_floor_exit(self):
        base = self._small_breeder_group_snapshot(ranged=False)

        def observed(turn, count):
            breeders = [
                replace(
                    base.visible_monsters[index % len(base.visible_monsters)],
                    index=100 + index,
                )
                for index in range(count)
            ]
            return replace(base, turn=turn, visible_monsters=breeders)

        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        for turn, count in ((100, 4), (900, 6), (1700, 7), (2500, 4), (3099, 5)):
            policy._update_combat_outcome(observed(turn, count))
            self.assertIsNone(policy._breeder_breakthrough_floor)

        timed_out = observed(3100, 6)
        policy._update_combat_outcome(timed_out)
        self.assertEqual(policy._breeder_breakthrough_floor, timed_out.floor_key)

        policy._floor_key = timed_out.floor_key
        with patch.object(
            policy, "_finish_mining_floor", return_value="FINISH"
        ) as finish:
            with patch.object(
                policy, "_darkness_recovery_key", return_value=None
            ):
                self.assertEqual(policy.choose_key(timed_out), "FINISH")
            finish.assert_called_once_with(timed_out)

    def test_breeder_progress_resets_stalemate_clock(self):
        base = self._small_breeder_group_snapshot(ranged=False)

        def observed(turn, count):
            breeders = [
                replace(
                    base.visible_monsters[index % len(base.visible_monsters)],
                    index=200 + index,
                )
                for index in range(count)
            ]
            return replace(base, turn=turn, visible_monsters=breeders)

        policy = HengbotPolicy()
        for turn, count in (
            (100, 4),
            (3000, 6),
            (3050, 3),
            (5900, 5),
            (5950, 2),
            (8900, 7),
        ):
            policy._update_combat_outcome(observed(turn, count))
            self.assertIsNone(policy._breeder_breakthrough_floor)

    def test_non_breeder_combat_has_no_stalemate_timeout(self):
        base = self._small_breeder_group_snapshot(ranged=False)
        ordinary = [
            replace(monster, can_multiply=False)
            for monster in base.visible_monsters
        ]
        policy = HengbotPolicy()

        policy._update_combat_outcome(
            replace(base, turn=1, visible_monsters=ordinary)
        )
        policy._update_combat_outcome(
            replace(base, turn=10000, visible_monsters=ordinary)
        )

        self.assertIsNone(policy._breeder_engagement_start_count)
        self.assertIsNone(policy._breeder_breakthrough_floor)

    def test_latched_weak_swarm_is_ignored_but_strong_swarm_leaves(self):
        # The strategic suppression of latched weak breeders is unchanged;
        # since the breakthrough gate removal (user decision D) the latch
        # itself carries the departure, so weak and strong swarms alike are
        # walked away from via breakthrough routing instead of being fought.
        weak = self._weak_breeder_incident_snapshot()
        policy = HengbotPolicy()
        policy._floor_key = weak.floor_key
        policy._breeder_breakthrough_floor = weak.floor_key
        self.assertEqual(policy._strategic_hostiles(weak), [])

        blocking = self._weak_breeder_incident_snapshot(blocking=True)
        self.assertEqual(policy.choose_key(blocking), "7")
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-frontier"
        )

        # A strong swarm this size is lethal, so the emergency ladder (which
        # sits above the breakthrough, before and after the gate removal
        # alike) owns the decision — and it, too, leaves upward.
        strong = replace(
            weak,
            visible_monsters=[
                replace(monster, max_melee_damage=20)
                for monster in weak.visible_monsters
            ],
        )
        self.assertNotEqual(policy.choose_key(strong), WAIT_KEY)
        self.assertEqual(policy.last_reason, "emergency:seek-upstairs")

    def test_open_melee_swarm_repositions_to_corridor_choke(self):
        snapshot = self._mouse_swarm_snapshot(adjacent=True)
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._melee_swarm_combat_key(
                snapshot,
                snapshot.visible_monsters,
                policy._strategic_adjacent_hostiles(snapshot),
            ),
            "4",
        )
        self.assertEqual(policy.last_reason, "melee:choke")

    @staticmethod
    def _orc_cave_choke_cycle_snapshot(position, visible_count, *, exp=25131, hp=565):
        room = Position(29, 169)
        mouth = Position(28, 170)
        choke = Position(27, 170)
        passable = {
            room, mouth, choke, Position(29, 170), Position(28, 171),
            Position(30, 168), Position(30, 169), Position(30, 170),
        }
        grids = {
            Position(y, x): grid(
                y, x, passable=Position(y, x) in passable, lit=True, in_view=True
            )
            for y in range(26, 32)
            for x in range(167, 172)
        }
        monster_cells = [
            Position(30, 168), Position(30, 169), Position(30, 170),
            Position(29, 170), Position(29, 169), Position(28, 171),
            Position(31, 168), Position(31, 169), Position(31, 170),
        ][:visible_count]
        monsters = [
            hostile(
                index, cell.y, cell.x,
                distance=position.distance_to(cell), race_id=69,
                can_multiply=True, max_melee_damage=3,
            )
            for index, cell in enumerate(monster_cells, 106)
        ]
        for monster in monsters:
            if monster.position in grids:
                grids[monster.position] = replace(
                    grids[monster.position], has_monster=True
                )
        return Snapshot(
            replace(
                player(position.y, position.x, hp=hp, max_hp=565, level=25),
                exp=exp,
            ),
            grids, monsters, floor_key=(3, 12, 0), turn=1676705,
        )

    def test_real_orc_cave_cycle_becomes_one_owned_validated_plan(self):
        room = Position(29, 169)
        mouth = Position(28, 170)
        choke = Position(27, 170)
        policy = HengbotPolicy()

        first = self._orc_cave_choke_cycle_snapshot(room, 9)
        self.assertEqual(policy.choose_key(first), "9")
        self.assertEqual(policy._choke_engagement_plan.destination, choke)

        contracted = self._orc_cave_choke_cycle_snapshot(mouth, 1)
        second = policy.choose_key(contracted)
        self.assertEqual((second, policy.last_reason), ("8", "melee:choke-reposition"))
        self.assertNotIn(policy.last_reason, {"hunt", "seek-loot", "explore"})

        unseen = self._orc_cave_choke_cycle_snapshot(choke, 0)
        self.assertEqual(policy.choose_key(unseen), WAIT_KEY)
        self.assertEqual(policy.last_reason, "melee:choke-hold")
        state = policy.choke_engagement_state()
        self.assertEqual(state["phase"], "hold")
        self.assertIsNone(state["release_cause"])

    @staticmethod
    def _quartz_choke_reposition_snapshot(position, *, visible):
        destination = Position(9, 65)
        away = Position(2, 67)
        contact = Position(3, 66)
        if position == contact:
            path = {
                contact, away, Position(3, 68), Position(4, 68),
                Position(5, 68), Position(6, 68), Position(7, 68),
                Position(8, 68), Position(9, 68), Position(9, 67),
                Position(9, 66), destination,
            }
        else:
            path = {
                away, contact, Position(4, 66), Position(5, 66),
                Position(6, 66), Position(7, 66), Position(8, 66),
                Position(9, 66), destination,
            }
        grids = {
            Position(y, x): grid(
                y, x, passable=Position(y, x) in path, lit=True, in_view=True
            )
            for y in range(1, 11)
            for x in range(64, 70)
        }
        monsters = []
        if visible:
            monsters = [
                hostile(
                    index, 4, x, distance=1, race_id=911,
                    can_multiply=True, speed=100, max_melee_damage=12,
                )
                for index, x in ((186, 66), (190, 67))
            ]
            for monster in monsters:
                grids[monster.position] = replace(
                    grids[monster.position], has_monster=True
                )
        return Snapshot(
            replace(player(position.y, position.x, hp=668, max_hp=668), exp=1),
            grids,
            monsters,
            floor_key=(7, 24, 0),
            turn=1,
        )

    def test_choke_reposition_measured_five_cell_wander_has_absolute_bound(self):
        destination = Position(9, 65)
        far_wander = [Position(5, 73), Position(6, 73)]
        middle_wander = [Position(4, 72), Position(5, 72)]
        wander = (
            far_wander * 10
            + middle_wander * 9
            + [Position(3, 71), Position(5, 73)]
        )
        policy = HengbotPolicy()
        policy._choke_engagement_plan = policy_module.ChokeEngagementPlan(
            floor=(7, 24, 0),
            phase="reposition",
            destination=destination,
            covered_retreat_direction=(-1, 1),
            trigger_last_seen={186: Position(4, 66), 190: Position(4, 67)},
            start_exp=1,
            start_gold=3000,
            start_breeder_count=2,
            last_player_hp=668,
            closest_destination_distance=9,
        )

        keys = []
        for decision, position in enumerate(wander):
            visible = []
            if decision % 10 == 0:
                visible = [
                    hostile(
                        186, 2, 64, distance=position.distance_to(Position(2, 64)),
                        race_id=911, can_multiply=True, max_melee_damage=0,
                    )
                ]
            snapshot = Snapshot(
                replace(player(position.y, position.x, hp=668, max_hp=668), exp=1),
                {
                    Position(y, x): grid(y, x, lit=True, in_view=True)
                    for y in range(2, 11) for x in range(64, 74)
                },
                visible, floor_key=(7, 24, 0), turn=decision + 1,
            )
            policy._build_grid_index(snapshot)
            key = policy._choke_engagement_key(
                snapshot,
                snapshot.visible_monsters,
                policy._physical_adjacent_hostiles(snapshot),
            )
            if policy.choke_engagement_state()["release_cause"] is not None:
                break
            keys.append(key)

        state = policy.choke_engagement_state()
        self.assertEqual(
            (state["phase"], state["release_cause"]),
            ("release", "engagement-stall-bound"),
        )
        self.assertLess(state["decisions_consumed"], 40)
        self.assertEqual(40 - state["decisions_consumed"], 16)
        self.assertEqual(state["closest_destination_distance"], 7)

    def test_multiplied_immobile_breeders_release_and_explore_elsewhere(self):
        origin = Position(10, 10)
        breeder_cells = {Position(10, 11), Position(10, 12)}
        passable = {Position(10, x) for x in range(7, 14)}
        grids = {
            position: grid(
                position.y, position.x, passable=True, lit=True,
                in_view=position.x >= 9,
            )
            for position in passable
        }
        monsters = [
            hostile(
                index, cell.y, cell.x, distance=origin.distance_to(cell),
                race_id=911, can_multiply=True, max_melee_damage=1,
            )
            for index, cell in enumerate(
                sorted(
                    breeder_cells,
                    key=lambda position: (position.y, position.x),
                ),
                1,
            )
        ]
        for monster in monsters:
            grids[monster.position] = replace(
                grids[monster.position], has_monster=True
            )
        snapshot = Snapshot(
            replace(player(origin.y, origin.x, hp=500, max_hp=500), exp=1),
            grids, monsters, floor_key=(7, 24, 0), turn=1,
        )
        policy = HengbotPolicy(monrace_knowledge={
            911: MonraceKnowledge(
                1, 100, False, False, can_multiply=True,
                flags=frozenset({"NEVER_MOVE"}),
            )
        })
        policy._choke_engagement_plan = policy_module.ChokeEngagementPlan(
            floor=snapshot.floor_key, phase="reposition",
            destination=Position(10, 9), covered_retreat_direction=(0, -1),
            trigger_last_seen={1: Position(10, 11)}, start_exp=1,
            start_gold=0, start_breeder_count=1, last_player_hp=500,
            closest_destination_distance=1,
        )
        policy._build_grid_index(snapshot)

        self.assertIsNone(
            policy._choke_engagement_key(snapshot, monsters, monsters[:1])
        )
        self.assertEqual(
            policy.choke_engagement_state()["release_cause"],
            "immobile-breeder-growth",
        )
        first = policy.choose_key(snapshot)
        self.assertEqual((first, policy.last_reason), (
            "4", "explore:immobile-breeder-giveup",
        ))
        moved = replace(
            snapshot,
            player=replace(snapshot.player, position=Position(10, 9)),
            turn=2,
        )
        policy._build_grid_index(moved)
        second = policy.choose_key(moved)
        self.assertEqual((second, policy.last_reason), (
            "4", "explore:immobile-breeder-giveup",
        ))
        self.assertTrue(breeder_cells <= policy._engagement_avoid_cells)
        self.assertEqual(moved.floor_key, snapshot.floor_key)

    def test_immobile_breeder_giveup_exhaustion_falls_through_to_progression(self):
        origin = Position(10, 10)
        breeder_cell = Position(10, 11)
        snapshot = Snapshot(
            player(
                origin.y, origin.x, hp=20, max_hp=20,
                abilities=frozenset({"free_action", "resist_conf", "resist_fire"}),
            ),
            {origin: grid(origin.y, origin.x, downstairs=True, lit=True)},
            [], floor_key=(7, 24, 0), turn=1,
        )
        policy = HengbotPolicy()
        policy._choke_engagement_plan = policy_module.ChokeEngagementPlan(
            floor=snapshot.floor_key, phase="release",
            destination=Position(10, 9), covered_retreat_direction=(0, -1),
            trigger_last_seen={1: breeder_cell}, start_exp=0,
            start_gold=0, start_breeder_count=1, last_player_hp=20,
            release_cause="immobile-breeder-growth",
        )

        key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), (">", "descend"))
        self.assertIn(breeder_cell, policy._engagement_avoid_cells)

    def test_immobile_breeder_giveup_yields_to_adjacent_mobile_hostile(self):
        origin = Position(10, 10)
        mobile_cell = Position(10, 11)
        trigger_cell = Position(10, 12)
        passable = {Position(10, x) for x in range(7, 13)}
        grids = {
            position: grid(
                position.y, position.x, passable=True, lit=True,
                in_view=position.x >= 9,
            )
            for position in passable
        }
        grids[mobile_cell] = replace(grids[mobile_cell], has_monster=True)
        mobile = hostile(
            2, mobile_cell.y, mobile_cell.x, distance=1,
            race_id=912, max_melee_damage=1,
        )
        snapshot = Snapshot(
            player(origin.y, origin.x, hp=500, max_hp=500),
            grids, [mobile], floor_key=(7, 24, 0), turn=1,
        )
        policy = HengbotPolicy()
        policy._choke_engagement_plan = policy_module.ChokeEngagementPlan(
            floor=snapshot.floor_key, phase="release",
            destination=Position(10, 9), covered_retreat_direction=(0, -1),
            trigger_last_seen={1: trigger_cell}, start_exp=0,
            start_gold=0, start_breeder_count=1, last_player_hp=500,
            release_cause="immobile-breeder-growth",
        )

        key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), ("6", "melee"))
        self.assertIn(trigger_cell, policy._engagement_avoid_cells)

    def test_mobile_breeder_growth_and_progressing_reposition_keep_prior_keys(self):
        mobile = HengbotPolicy()
        mobile.choose_key(self._orc_cave_choke_cycle_snapshot(Position(29, 169), 2))
        grown = self._orc_cave_choke_cycle_snapshot(Position(28, 170), 3)
        mobile._build_grid_index(grown)
        self.assertIsNone(mobile._choke_engagement_key(
            grown, grown.visible_monsters,
            mobile._physical_adjacent_hostiles(grown),
        ))
        mobile_state = mobile.choke_engagement_state()
        self.assertEqual((mobile_state["phase"], mobile_state["release_cause"]), (
            "release", "swarm-growth",
        ))

        progressing = HengbotPolicy()
        progressing.choose_key(
            self._orc_cave_choke_cycle_snapshot(Position(29, 169), 9)
        )
        key = progressing.choose_key(
            self._orc_cave_choke_cycle_snapshot(Position(28, 170), 1)
        )
        state = progressing.choke_engagement_state()
        self.assertEqual((key, progressing.last_reason), (
            "8", "melee:choke-reposition",
        ))
        self.assertEqual((state["phase"], state["no_progress_decisions"],
                          state["release_cause"]), (
            "reposition", 0, None,
        ))

    def test_open_capture_mouth_is_never_accepted_as_choke_hold(self):
        policy = HengbotPolicy()
        snapshot = self._orc_cave_choke_cycle_snapshot(Position(29, 169), 9)
        policy.choose_key(snapshot)

        self.assertNotEqual(policy._choke_engagement_plan.destination, Position(28, 170))
        self.assertGreater(
            policy._open_neighbor_count(snapshot, Position(28, 170)),
            policy_module.SUMMONER_CHOKE_NEIGHBORS - 1,
        )

    def test_choke_plan_records_kill_emergency_and_breakthrough_releases(self):
        room = Position(29, 169)
        mouth = Position(28, 170)

        killed = HengbotPolicy()
        killed.choose_key(self._orc_cave_choke_cycle_snapshot(room, 9))
        killed.choose_key(self._orc_cave_choke_cycle_snapshot(mouth, 1, exp=25132))
        self.assertEqual(
            killed.choke_engagement_state()["release_cause"], "kill-progress"
        )

        emergency = HengbotPolicy()
        emergency.choose_key(self._orc_cave_choke_cycle_snapshot(room, 9))
        danger = replace(
            self._orc_cave_choke_cycle_snapshot(mouth, 1, hp=20),
            inventory=[item("p", TVAL_SCROLL, SV_SCROLL_PHASE_DOOR)],
        )
        emergency.choose_key(danger)
        self.assertEqual(
            emergency.choke_engagement_state()["release_cause"], "hp-authority"
        )

        breakthrough = HengbotPolicy()
        active = self._orc_cave_choke_cycle_snapshot(room, 9)
        breakthrough.choose_key(active)
        breakthrough._breeder_breakthrough_floor = active.floor_key
        breakthrough.choose_key(self._orc_cave_choke_cycle_snapshot(mouth, 1))
        state = breakthrough.choke_engagement_state()
        self.assertEqual((state["phase"], state["release_cause"]), (
            "breakthrough", "breeder-breakthrough",
        ))

        growth = HengbotPolicy()
        growth.choose_key(self._orc_cave_choke_cycle_snapshot(room, 2))
        self.assertIsNotNone(growth._choke_engagement_plan)
        self.assertEqual(growth._choke_engagement_plan.start_breeder_count, 2)
        grown_snapshot = self._orc_cave_choke_cycle_snapshot(mouth, 3)
        growth._build_grid_index(grown_snapshot)
        growth._choke_engagement_key(
            grown_snapshot, grown_snapshot.visible_monsters,
            growth._physical_adjacent_hostiles(grown_snapshot),
        )
        self.assertEqual(
            growth.choke_engagement_state()["release_cause"], "swarm-growth"
        )

        ranged = HengbotPolicy()
        ranged.choose_key(self._orc_cave_choke_cycle_snapshot(room, 2))
        ranged_snapshot = self._orc_cave_choke_cycle_snapshot(mouth, 1)
        ranged_snapshot = replace(
            ranged_snapshot,
            visible_monsters=[
                replace(ranged_snapshot.visible_monsters[0], max_ranged_damage=1)
            ],
        )
        ranged._build_grid_index(ranged_snapshot)
        ranged._choke_engagement_key(
            ranged_snapshot, ranged_snapshot.visible_monsters,
            ranged._physical_adjacent_hostiles(ranged_snapshot),
        )
        self.assertEqual(
            ranged.choke_engagement_state()["release_cause"], "ranged-threat"
        )

    def test_detected_out_of_sight_swarm_growth_releases_choke_plan(self):
        policy = HengbotPolicy()
        policy.choose_key(
            self._orc_cave_choke_cycle_snapshot(Position(29, 169), 2)
        )
        hidden = self._orc_cave_choke_cycle_snapshot(Position(28, 170), 0)
        detected = [
            replace(monster, perception="detected")
            for monster in self._orc_cave_choke_cycle_snapshot(
                Position(28, 170), 3
            ).visible_monsters
        ]
        hidden = replace(hidden, detected_monsters=detected)
        policy._build_grid_index(hidden)

        policy._choke_engagement_key(hidden, [], [])

        self.assertEqual(
            policy.choke_engagement_state()["release_cause"], "swarm-growth"
        )

    def test_choke_sight_loss_uses_existing_extended_stuck_bound(self):
        policy = HengbotPolicy()
        policy.choose_key(
            self._orc_cave_choke_cycle_snapshot(Position(29, 169), 9)
        )
        policy._choke_engagement_plan.sight_loss_decisions = (
            policy_module.EXTENDED_STUCK_WINDOW
        )

        policy.choose_key(
            self._orc_cave_choke_cycle_snapshot(Position(28, 170), 0)
        )

        state = policy.choke_engagement_state()
        self.assertEqual(
            (state["phase"], state["release_cause"]),
            ("release", "sight-loss-bound"),
        )

    def test_released_breeder_choke_abandons_floor_instead_of_rearming(self):
        room = Position(29, 169)
        mouth = Position(28, 170)
        choke = Position(27, 170)
        policy = HengbotPolicy()
        policy.choose_key(self._orc_cave_choke_cycle_snapshot(room, 9))
        policy._choke_engagement_plan.sight_loss_decisions = (
            policy_module.EXTENDED_STUCK_WINDOW
        )

        policy.choose_key(self._orc_cave_choke_cycle_snapshot(mouth, 0))
        self.assertEqual(
            policy.choke_engagement_state()["release_cause"],
            "sight-loss-bound",
        )
        posted = []
        for turn, position in enumerate((room, mouth, choke), 2):
            snapshot = self._orc_cave_choke_cycle_snapshot(position, 9)
            snapshot = replace(
                snapshot,
                grids={
                    grid_position: replace(
                        cell,
                        has_up_stairs=grid_position == choke,
                    )
                    for grid_position, cell in snapshot.grids.items()
                },
                turn=turn,
            )
            posted.append((policy.choose_key(snapshot), policy.last_reason))

        self.assertEqual(posted, [
            ("9", "return:seek-upstairs"),
            ("8", "return:seek-upstairs"),
            ("<", "return:ascend"),
        ])
        self.assertEqual(
            policy.choke_engagement_state()["release_cause"],
            "sight-loss-bound",
        )

    def test_fresh_floor_gets_its_first_breeder_choke_attempt(self):
        snapshot = self._orc_cave_choke_cycle_snapshot(Position(29, 169), 9)
        policy = HengbotPolicy()

        key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), ("9", "melee:choke"))
        self.assertIsNone(policy._breeder_choke_attempt_ended_floor)
        self.assertIsNotNone(policy._choke_engagement_plan)

    def test_ended_breeder_choke_without_exit_falls_through_to_melee(self):
        room = Position(29, 169)
        policy = HengbotPolicy()
        policy.choose_key(self._orc_cave_choke_cycle_snapshot(room, 0))
        snapshot = self._orc_cave_choke_cycle_snapshot(room, 4)
        policy._fundraising_mode = "mine"
        policy._breeder_choke_attempt_ended_floor = snapshot.floor_key

        with patch.object(policy, "_return_to_town_key", return_value=None):
            key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), ("1", "melee"))
        self.assertIsNone(policy._choke_engagement_plan)
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(
            policy._breeder_choke_attempt_ended_floor,
            snapshot.floor_key,
        )

    def test_new_floor_visit_rearms_breeder_choke_attempt(self):
        room = Position(29, 169)
        mouth = Position(28, 170)
        policy = HengbotPolicy()
        policy.choose_key(self._orc_cave_choke_cycle_snapshot(room, 9))
        policy._choke_engagement_plan.sight_loss_decisions = (
            policy_module.EXTENDED_STUCK_WINDOW
        )
        policy.choose_key(self._orc_cave_choke_cycle_snapshot(mouth, 0))

        new_visit = replace(
            self._orc_cave_choke_cycle_snapshot(room, 9),
            floor_key=(3, 13, 0),
        )
        key = policy.choose_key(new_visit)

        self.assertEqual((key, policy.last_reason), ("9", "melee:choke"))
        self.assertIsNone(policy._breeder_choke_attempt_ended_floor)
        self.assertEqual(policy._choke_engagement_plan.floor, (3, 13, 0))

    def test_quest_floor_suppresses_repeat_choke_without_abandoning(self):
        snapshot = replace(
            self._orc_cave_choke_cycle_snapshot(Position(29, 169), 9),
            floor_key=(3, 12, 34),
        )
        policy = HengbotPolicy()
        self.assertIsNone(policy._breeder_choke_attempt_ended_floor)
        policy._breeder_choke_attempt_ended_floor = snapshot.floor_key
        policy._build_grid_index(snapshot)

        with patch.object(policy, "_active_fixed_quest_id", return_value=34):
            key = policy._melee_swarm_combat_key(
                snapshot,
                snapshot.visible_monsters,
                policy._physical_adjacent_hostiles(snapshot),
            )

        self.assertIsNone(key)
        self.assertFalse(policy._returning_to_town)
        self.assertIsNone(policy._choke_engagement_plan)
        self.assertEqual(
            policy._breeder_choke_attempt_ended_floor,
            snapshot.floor_key,
        )

    @staticmethod
    def _stationary_choke_snapshot(
        monsters, *, hp=1000, exp=1000, gold=0, turn=1
    ):
        grids = {
            Position(10, x): grid(10, x, lit=True, in_view=True)
            for x in range(6, 16)
        }
        for monster in monsters:
            grids[monster.position] = replace(
                grids[monster.position], has_monster=True
            )
        return Snapshot(
            replace(
                player(10, 10, hp=hp, max_hp=1000, level=20),
                exp=exp,
                gold=gold,
            ),
            grids,
            monsters,
            floor_key=(DUNGEON_YEEK_CAVE, 10, 0),
            turn=turn,
        )

    def test_choke_hold_releases_after_bounded_no_engagement_progress(self):
        adjacent = [
            hostile(1, 10, 11, distance=1, max_melee_damage=3, race_id=500),
            hostile(2, 10, 9, distance=1, max_melee_damage=3, race_id=500),
        ]
        far = [
            hostile(1, 10, 12, distance=2, max_melee_damage=3, race_id=500),
            hostile(2, 10, 8, distance=2, max_melee_damage=3, race_id=500),
        ]
        policy = HengbotPolicy()
        armed = self._stationary_choke_snapshot(adjacent)
        policy.prime(armed)
        self.assertEqual(policy.choose_key(armed), "6")

        for turn in range(2, policy_module.COMBAT_OUTCOME_WINDOW + 3):
            policy.choose_key(self._stationary_choke_snapshot(far, turn=turn))
            if policy.choke_engagement_state()["release_cause"] is not None:
                break

        state = policy.choke_engagement_state()
        self.assertLessEqual(
            state["no_progress_decisions"], policy_module.COMBAT_OUTCOME_WINDOW
        )
        self.assertEqual(
            (state["phase"], state["release_cause"]),
            ("release", "engagement-stall-bound"),
        )

    def test_choke_hold_adjacent_breeder_swarm_hits_outcome_bound(self):
        adjacent = [
            hostile(
                index, 10, x, distance=1, max_melee_damage=3,
                race_id=500, can_multiply=True,
            )
            for index, x in ((1, 11), (2, 9))
        ]
        far = [replace(monster, position=Position(10, 12), distance=2)
               for monster in adjacent]
        policy = HengbotPolicy()
        armed = self._stationary_choke_snapshot(adjacent)
        policy.prime(armed)
        policy.choose_key(armed)

        for decision in range(2, 798):
            monsters = adjacent if decision % 10 else far
            snapshot = self._stationary_choke_snapshot(monsters, turn=decision * 10)
            policy._build_grid_index(snapshot)
            policy._choke_engagement_key(
                snapshot, monsters, policy._physical_adjacent_hostiles(snapshot)
            )
            if policy.choke_engagement_state()["release_cause"] is not None:
                break

        state = policy.choke_engagement_state()
        self.assertLess(decision, 797)
        self.assertEqual(
            (state["no_progress_decisions"], state["release_cause"]),
            (policy_module.COMBAT_OUTCOME_WINDOW, "breeder-outcome-bound"),
        )

    def test_choke_outcome_budget_survives_release_and_same_trigger_replan(self):
        monsters = [
            hostile(
                index, 10, x, distance=1, max_melee_damage=3,
                race_id=500, can_multiply=True,
            )
            for index, x in ((1, 11), (2, 9))
        ]
        snapshot = self._stationary_choke_snapshot(monsters)
        policy = HengbotPolicy()
        plan = policy_module.ChokeEngagementPlan(
            floor=snapshot.floor_key, phase="hold", destination=Position(10, 10),
            covered_retreat_direction=(0, 0),
            trigger_last_seen={monster.index: monster.position for monster in monsters},
            start_exp=1000, start_gold=0, start_breeder_count=2,
            last_player_hp=1000,
        )
        policy._choke_engagement_plan = plan
        policy._inherit_choke_outcome_budget(snapshot, plan)
        for turn in range(1, 101):
            current = replace(snapshot, turn=turn)
            policy._build_grid_index(current)
            policy._choke_engagement_key(current, monsters, monsters)
        spent_before_release = plan.no_progress_decisions
        policy._release_choke_plan("destination-invalid")
        replacement = replace(
            plan, phase="hold", no_progress_decisions=0, release_cause=None,
        )
        policy._choke_engagement_plan = replacement
        policy._inherit_choke_outcome_budget(snapshot, replacement)

        self.assertEqual(replacement.no_progress_decisions, spent_before_release)
        self.assertGreater(spent_before_release, 0)

    def test_choke_outcome_budget_survives_replans_with_new_breeder_indices(self):
        snapshot = self._stationary_choke_snapshot([])

        def decisions_until_bound(churn_indices):
            policy = HengbotPolicy()
            for decision in range(1, policy_module.COMBAT_OUTCOME_WINDOW + 1):
                first_index = decision * 2 if churn_indices else 1
                plan = policy_module.ChokeEngagementPlan(
                    floor=snapshot.floor_key, phase="hold",
                    destination=Position(10, 10),
                    covered_retreat_direction=(0, 0),
                    trigger_last_seen={
                        first_index: Position(10, 11),
                        first_index + 1: Position(10, 9),
                    },
                    start_exp=1000, start_gold=0, start_breeder_count=2,
                    last_player_hp=1000,
                )
                policy._inherit_choke_outcome_budget(snapshot, plan)
                policy._spend_choke_outcome_budget(snapshot, plan, 2, 2)
                if plan.no_progress_decisions >= policy_module.COMBAT_OUTCOME_WINDOW:
                    return decision
            return None

        self.assertEqual(
            decisions_until_bound(churn_indices=True),
            decisions_until_bound(churn_indices=False),
        )
        self.assertEqual(
            decisions_until_bound(churn_indices=True),
            policy_module.COMBAT_OUTCOME_WINDOW,
        )

    def test_separate_choke_engagements_keep_independent_outcome_budgets(self):
        snapshot = self._stationary_choke_snapshot([])
        policy = HengbotPolicy()

        def plan_at(destination):
            return policy_module.ChokeEngagementPlan(
                floor=snapshot.floor_key, phase="hold", destination=destination,
                covered_retreat_direction=(0, 0),
                trigger_last_seen={1: Position(10, 11), 2: Position(10, 9)},
                start_exp=1000, start_gold=0, start_breeder_count=2,
                last_player_hp=1000,
            )

        first = plan_at(Position(10, 10))
        policy._inherit_choke_outcome_budget(snapshot, first)
        for _ in range(17):
            policy._spend_choke_outcome_budget(snapshot, first, 2, 2)

        second = plan_at(Position(20, 20))
        policy._inherit_choke_outcome_budget(snapshot, second)
        for _ in range(5):
            policy._spend_choke_outcome_budget(snapshot, second, 2, 2)

        first_replan = plan_at(Position(10, 10))
        second_replan = plan_at(Position(20, 20))
        policy._inherit_choke_outcome_budget(snapshot, first_replan)
        policy._inherit_choke_outcome_budget(snapshot, second_replan)

        self.assertEqual(first_replan.no_progress_decisions, 17)
        self.assertEqual(second_replan.no_progress_decisions, 5)

    def test_productive_choke_outcomes_replenish_existing_budget(self):
        monsters = [
            hostile(
                index, 10, x, distance=1, max_melee_damage=3,
                race_id=500, can_multiply=True,
            )
            for index, x in ((1, 11), (2, 9))
        ]
        policy = HengbotPolicy()
        armed = self._stationary_choke_snapshot(monsters)
        policy.prime(armed)
        policy.choose_key(armed)

        for decision in range(2, policy_module.COMBAT_OUTCOME_WINDOW * 2):
            exp = 1000 + decision // (policy_module.COMBAT_OUTCOME_WINDOW // 2)
            snapshot = self._stationary_choke_snapshot(
                monsters, exp=exp, turn=decision
            )
            policy._build_grid_index(snapshot)
            policy._choke_engagement_key(snapshot, monsters, monsters)

        state = policy.choke_engagement_state()
        self.assertIsNone(state["release_cause"])
        self.assertLess(
            state["no_progress_decisions"], policy_module.COMBAT_OUTCOME_WINDOW
        )
        self.assertGreater(state["no_progress_decisions"], 0)

    def test_breeder_outcome_giveup_explores_away_on_same_floor(self):
        origin = Position(10, 10)
        breeder_cell = Position(10, 11)
        passable = {Position(10, x) for x in range(7, 12)}
        grids = {
            position: grid(
                position.y, position.x, passable=True, lit=True,
                in_view=position.x >= 9,
            )
            for position in passable
        }
        breeder = hostile(
            1, 10, 11, distance=1, race_id=500,
            can_multiply=True, max_melee_damage=1,
        )
        grids[breeder_cell] = replace(grids[breeder_cell], has_monster=True)
        snapshot = Snapshot(
            replace(player(10, 10, hp=1000, max_hp=1000), exp=1000),
            grids, [breeder], floor_key=(DUNGEON_YEEK_CAVE, 10, 0), turn=1,
        )
        policy = HengbotPolicy()
        policy._choke_engagement_plan = policy_module.ChokeEngagementPlan(
            floor=snapshot.floor_key, phase="release", destination=origin,
            covered_retreat_direction=(0, 0),
            trigger_last_seen={1: breeder_cell}, start_exp=1000,
            start_gold=0, start_breeder_count=1, last_player_hp=1000,
            no_progress_decisions=policy_module.COMBAT_OUTCOME_WINDOW,
            release_cause="breeder-outcome-bound",
        )

        key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), ("4", "explore:breeder-giveup"))
        self.assertIn(breeder_cell, policy._engagement_avoid_cells)
        self.assertEqual(snapshot.floor_key, policy._choke_engagement_plan.floor)

    def test_moving_player_still_prepares_for_monsters_that_moved_closer(self):
        snapshot = self._mouse_swarm_snapshot()
        current_player = Position(10, 11)
        current_monsters = [
            replace(
                monster,
                position=Position(9 + index, 14),
                distance=3,
                can_multiply=False,
            )
            for index, monster in enumerate(snapshot.visible_monsters)
        ]
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, position=current_player),
            visible_monsters=current_monsters,
        )
        policy = HengbotPolicy()
        policy._position_changed = True
        previous_monsters = [
            replace(
                monster,
                position=Position(monster.position.y, 15),
                distance=5,
            )
            for monster in current_monsters
        ]
        policy._remember_swarm_distances(
            replace(snapshot, visible_monsters=previous_monsters)
        )
        policy._build_grid_index(snapshot)

        with patch.object(
            policy,
            "_validated_choke_route",
            return_value=(Position(10, 10), Position(10, 10)),
        ):
            key = policy._melee_swarm_combat_key(snapshot, current_monsters, [])

        self.assertEqual((key, policy.last_reason), ("4", "melee:choke"))

    def test_player_approach_does_not_make_stationary_monsters_converge(self):
        snapshot = self._mouse_swarm_snapshot()
        current_player = Position(10, 11)
        stationary_monsters = [
            replace(
                monster,
                distance=current_player.distance_to(monster.position),
                can_multiply=False,
            )
            for monster in snapshot.visible_monsters
        ]
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, position=current_player),
            visible_monsters=stationary_monsters,
        )
        policy = HengbotPolicy()
        policy._position_changed = True
        policy._remember_swarm_distances(
            replace(
                snapshot,
                player=replace(snapshot.player, position=Position(10, 10)),
            )
        )
        policy._build_grid_index(snapshot)

        self.assertIsNone(
            policy._melee_swarm_combat_key(snapshot, stationary_monsters, [])
        )

    def test_choke_melees_adjacent_swarm_without_chasing(self):
        snapshot = self._mouse_swarm_snapshot(at_choke=True, adjacent=True)
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._melee_swarm_combat_key(
                snapshot,
                snapshot.visible_monsters,
                policy._strategic_adjacent_hostiles(snapshot),
            ),
            "6",
        )
        self.assertEqual(policy.last_reason, "melee:choke")

    def test_ranged_swarm_bypasses_choke_logic(self):
        snapshot = self._mouse_swarm_snapshot(adjacent=True, ranged=True)
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        self.assertIsNone(
            policy._melee_swarm_combat_key(
                snapshot,
                snapshot.visible_monsters,
                policy._strategic_adjacent_hostiles(snapshot),
            )
        )

    def test_sleeping_melee_member_does_not_disable_swarm_choke(self):
        snapshot = self._mouse_swarm_snapshot(adjacent=True)
        snapshot = replace(
            snapshot,
            visible_monsters=[
                replace(snapshot.visible_monsters[0], asleep=True),
                *snapshot.visible_monsters[1:],
            ],
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        self.assertIsNotNone(
            policy._melee_swarm_combat_key(
                snapshot,
                snapshot.visible_monsters,
                policy._strategic_adjacent_hostiles(snapshot),
            )
        )
        self.assertEqual(policy.last_reason, "melee:choke")

    def test_choke_retreat_prefers_covered_corridor(self):
        monster = hostile(1, 10, 12, distance=2, max_melee_damage=1)
        grids = {
            Position(y, x): grid(y, x)
            for y in range(8, 13)
            for x in range(8, 13)
        }
        # West and north are equally far from the threat. West is narrowed by
        # real walls; north remains open, and both reach _flee_step's score.
        grids[Position(9, 8)] = grid(9, 8, passable=False)
        grids[Position(10, 8)] = grid(10, 8, passable=False)
        grids[Position(11, 8)] = grid(11, 8, passable=False)
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            grids,
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        candidates = policy._walkable_neighbors(snapshot, snapshot.player.position)
        self.assertIn(Position(10, 9), candidates)
        self.assertIn(Position(9, 10), candidates)
        self.assertEqual(
            policy._flee_step(snapshot, [monster]),
            Position(10, 9),
        )

    def test_weak_breeders_trigger_fundraise_elimination_in_state_one(self):
        sleepers = [
            hostile(
                index, 10, 10 + distance, distance=distance, asleep=True,
                can_multiply=True, max_melee_damage=1,
            )
            for index, distance in enumerate((3, 4), 1)
        ]
        snapshot = Snapshot(
            player(
                10, 10, hp=100, max_hp=100,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12),
                Position(10, 13): grid(10, 13, monster=True),
                Position(10, 14): grid(10, 14, monster=True),
            },
            sleepers,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[],
            equipment=[
                item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                item(
                    "light", TVAL_LITE, SV_LITE_LANTERN, name="lantern",
                    fuel=5000, is_equipment=True,
                ),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        throwable = replace(
            snapshot,
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=5000)
            ],
        )
        policy._build_grid_index(throwable)
        self.assertIsNone(
            policy._melee_swarm_combat_key(throwable, sleepers, [])
        )

        for decision in range(119):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            policy.choose_key(snapshot)
            if decision == 0:
                self.assertEqual(
                    policy.last_reason, "fundraise:eliminate-multiplier"
                )
            self.assertNotIn(
                policy.last_reason,
                {"melee:choke", "melee:choke-hold", "ranged:throw-torch"},
            )

    def test_escape_attacks_weak_mouse_blocking_corridor_to_stairs(self):
        mouse = hostile(
            1, 10, 9, distance=1, can_multiply=True,
            max_hp=10, max_melee_damage=2,
        )
        snapshot = Snapshot(
            player(
                10, 10, hp=59, max_hp=172, level=10,
                main_hand_blows=2, main_hand_to_d=5,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 9): grid(10, 9, monster=True),
                Position(10, 8): grid(10, 8),
                Position(10, 7): grid(10, 7, upstairs=True),
            },
            [mouse],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1, name="Broad Sword",
                    is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._blocking_escape_melee_key(
                snapshot, [mouse], policy._is_upstairs_target
            ),
            "4",
        )

    def test_low_hp_weak_breeder_does_not_preserve_declared_walkout(self):
        mouse = hostile(
            1, 10, 9, hp=6, max_hp=6, distance=1, can_multiply=True,
            max_melee_damage=2,
        )
        snapshot = Snapshot(
            player(
                10, 10, hp=59, max_hp=172, level=10,
                main_hand_blows=2, main_hand_to_d=5,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 9): grid(10, 9, monster=True),
                Position(10, 8): grid(10, 8),
                Position(10, 7): grid(10, 7, upstairs=True),
                Position(9, 10): grid(9, 10),
                Position(11, 10): grid(11, 10),
            },
            [mouse],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1, name="Broad Sword",
                    is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key
        policy._fruitless_disengage_floor = snapshot.floor_key

        key = policy.choose_key(snapshot)

        self.assertFalse(policy.last_reason.startswith("combat:disengage-"))
        self.assertNotEqual(policy.last_reason, "combat:fruitless")
        self.assertIsNone(policy._fruitless_disengage_floor)

    def test_escape_reroutes_around_dangerous_fast_blocker(self):
        blocker = hostile(
            1, 10, 9, hp=170, max_hp=170, distance=1, speed=130,
            max_melee_damage=45,
        )
        snapshot = Snapshot(
            player(
                10, 10, hp=59, max_hp=172, level=10,
                main_hand_blows=2, main_hand_to_d=5,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 9): grid(10, 9, monster=True),
                Position(10, 8): grid(10, 8),
                Position(10, 7): grid(10, 7, upstairs=True),
            },
            [blocker],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1, name="Broad Sword",
                    is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        self.assertIsNone(
            policy._blocking_escape_melee_key(
                snapshot, [blocker], policy._is_upstairs_target
            )
        )

    def test_productive_choke_hold_survives_long_breeder_window(self):
        base = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        policy = HengbotPolicy()

        for decision in range(45):
            current = replace(
                base,
                player=replace(base.player, exp=decision),
            )
            policy.choose_key(current)
            self.assertTrue(policy.last_reason.startswith("melee:choke"))

        self.assertLess(policy._breeder_engagement_score, 3)
        self.assertIsNone(policy._fruitless_disengage_floor)

    def test_choke_hold_does_not_read_escape_scroll_before_mice_arrive(self):
        base = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        mice = [
            replace(
                base.visible_monsters[index],
                position=Position(10, 11 + index),
                distance=2 + index,
            )
            for index in range(2)
        ]
        grids = dict(base.grids)
        for mouse in mice:
            grids[mouse.position] = replace(
                grids[mouse.position], has_monster=True
            )
        snapshot = replace(
            base,
            grids=grids,
            visible_monsters=mice,
            inventory=[
                item(
                    "p", TVAL_SCROLL, SV_SCROLL_PHASE_DOOR,
                    count=5,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), (
            WAIT_KEY, "melee:choke-hold",
        ))

    def test_incident_breeder_growth_forces_sticky_upstairs_breakthrough(self):
        sword = item(
            "main_hand", TVAL_SWORD, 1, name="Broad Sword",
            is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
        )
        choke = Position(9, 16)
        upstairs = Position(9, 13)
        base_grids = {
            Position(y, x): grid(y, x, lit=True)
            for y in range(7, 12)
            for x in range(13, 21)
        }
        for wall in (
            Position(8, 13), Position(10, 13),
            Position(8, 14), Position(10, 14),
            Position(8, 15), Position(10, 15),
            Position(8, 16), Position(10, 16),
            Position(8, 17), Position(10, 17),
        ):
            base_grids[wall] = grid(wall.y, wall.x, passable=False)
        base_grids[upstairs] = grid(upstairs.y, upstairs.x, upstairs=True)

        def incident_snapshot(position, positions):
            breeders = [
                hostile(
                    index, y, x,
                    distance=position.distance_to(Position(y, x)),
                    race_id=31, can_multiply=True, max_melee_damage=1,
                )
                for index, (y, x) in enumerate(positions, 1)
            ]
            grids = dict(base_grids)
            for breeder in breeders:
                grids[breeder.position] = replace(
                    grids[breeder.position], has_monster=True
                )
            return Snapshot(
                player(
                    position.y, position.x, hp=205, max_hp=20, level=10,
                    class_id=PLAYER_CLASS_WARRIOR,
                    main_hand_blows=2, main_hand_to_d=5,
                ),
                grids,
                breeders,
                floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
                equipment=[sword],
            )

        held_positions = [
            (7, 17), (7, 18), (7, 19), (8, 19),
            (9, 19), (10, 19), (11, 18), (11, 19),
        ]
        grown_positions = [
            (9, 15),
            (7, 17), (7, 18), (7, 19), (8, 19), (8, 20),
            (9, 19), (9, 20), (10, 19), (11, 18), (11, 19),
        ]
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        held = incident_snapshot(choke, held_positions)
        self.assertEqual(policy.choose_key(held), WAIT_KEY)
        self.assertEqual(policy.last_reason, "melee:choke-hold")

        grown = incident_snapshot(choke, grown_positions)
        policy._breeder_breakthrough_floor = grown.floor_key
        grown_key = policy.choose_key(grown)
        self.assertEqual(grown_key, "4")
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:clear-escape-path"
        )

        cleared_positions = grown_positions[1:]
        still_at_choke = incident_snapshot(choke, cleared_positions)
        self.assertEqual(policy.choose_key(still_at_choke), "4")
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-upstairs"
        )

        on_stairs = incident_snapshot(upstairs, cleared_positions)
        self.assertEqual(policy.choose_key(on_stairs), "<")
        self.assertEqual(policy.last_reason, "breeder-breakthrough:ascend")

    def test_shrinking_breeder_swarm_stays_at_choke(self):
        base = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertEqual(policy.choose_key(base), WAIT_KEY)
        self.assertEqual(policy.last_reason, "melee:choke-hold")

        shrinking = replace(
            base,
            visible_monsters=base.visible_monsters[:-1],
        )
        self.assertEqual(policy.choose_key(shrinking), WAIT_KEY)
        self.assertEqual(policy.last_reason, "melee:choke-hold")

    def test_incident_expired_breakthrough_latch_returns_to_ordinary_behavior(self):
        base = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        grids = {
            position: replace(grid_state, has_monster=False, monster_index=0)
            for position, grid_state in base.grids.items()
        }
        cleared = replace(base, grids=grids, visible_monsters=[])
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._observe(cleared)
        policy._breeder_engagement_floor = cleared.floor_key
        policy._breeder_engagement_score = 0
        policy._breeder_breakthrough_floor = cleared.floor_key

        policy.choose_key(cleared)

        self.assertNotEqual(
            policy.last_reason, "breeder-breakthrough:upstairs-not-found"
        )
        self.assertEqual(policy._breeder_breakthrough_floor, cleared.floor_key)

    def test_breakthrough_latch_survives_brief_breeder_visibility_flicker(self):
        visible = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        hidden = replace(visible, visible_monsters=[])
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._observe(visible)
        policy._breeder_engagement_floor = visible.floor_key
        policy._breeder_engagement_score = 12
        policy._breeder_breakthrough_floor = visible.floor_key

        for _ in range(2):
            policy.choose_key(hidden)
            self.assertEqual(
                policy._breeder_breakthrough_floor, visible.floor_key
            )

        policy.choose_key(visible)
        self.assertTrue(
            policy.last_reason.startswith("breeder-breakthrough:")
        )
        self.assertEqual(
            policy._breeder_breakthrough_floor, visible.floor_key
        )

    def test_visible_breeders_do_not_release_breakthrough_latch(self):
        visible = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._observe(visible)
        policy._breeder_engagement_floor = visible.floor_key
        policy._breeder_engagement_score = 8
        policy._breeder_breakthrough_floor = visible.floor_key

        policy.choose_key(visible)
        self.assertTrue(
            policy.last_reason.startswith("breeder-breakthrough:")
        )
        self.assertEqual(
            policy._breeder_breakthrough_floor, visible.floor_key
        )

    def test_breakthrough_can_rearm_after_expired_latch_releases(self):
        visible = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        hidden = replace(visible, visible_monsters=[])
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._observe(visible)
        policy._breeder_engagement_floor = visible.floor_key
        policy._breeder_engagement_score = 0
        policy._breeder_breakthrough_floor = visible.floor_key

        policy.choose_key(hidden)
        self.assertEqual(policy._breeder_breakthrough_floor, visible.floor_key)

        # No up-stairs is remembered here; since the upstairs-not-found WAIT
        # was replaced (user decision D) the breakthrough routes toward the
        # nearest frontier instead of holding still.
        self.assertEqual(policy.choose_key(visible), "4")
        self.assertEqual(
            policy.last_reason, "breeder-breakthrough:seek-frontier"
        )
        self.assertEqual(
            policy._breeder_breakthrough_floor, visible.floor_key
        )

    def test_incident_breakthrough_routes_advance_monotonically_to_upstairs(self):
        captures = [
            Path(__file__).parents[1]
            / "incident-captures"
            / "20260729-1943-breakthrough-oscillation"
            / "oscillation-turn.jsonl",
            Path(__file__).parents[1]
            / "incident-captures"
            / "20260729-2009-breakthrough-retreat"
            / "retreat-turn191760.jsonl",
        ]
        monraces = Path(
            r"C:\hengband\.worktrees\bot-json-output\lib\edit"
            r"\MonraceDefinitions.jsonc"
        )
        if not all(capture.is_file() for capture in captures) or not monraces.is_file():
            self.skipTest("real breakthrough incident capture is not available")
        knowledge = load_monrace_knowledge(monraces)
        offsets = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }
        upstairs = Position(14, 18)
        remembered_grids = {}

        for capture in captures:
            with self.subTest(capture=capture):
                snapshot = parse_snapshot(
                    json.loads(capture.read_text(encoding="utf-8")), knowledge
                )
                snapshot = replace(
                    snapshot,
                    inventory=[],
                    visible_monsters=[
                        replace(
                            monster,
                            max_melee_damage=max(
                                monster.max_melee_damage,
                                snapshot.player.max_hp * 0.05,
                            ),
                        )
                        for monster in snapshot.visible_monsters
                    ],
                )
                policy = HengbotPolicy(monrace_knowledge=knowledge)
                policy._fundraising_mode = "mine"
                policy._remembered_grid_region = (
                    *snapshot.floor_key,
                    snapshot.width,
                    snapshot.height,
                    snapshot.town_id,
                    snapshot.in_town,
                )
                policy._remembered_grids = dict(remembered_grids)
                policy._observe(snapshot)
                policy._breeder_breakthrough_floor = snapshot.floor_key
                policy._breeder_engagement_score = (
                    BREEDER_CONTAINMENT_WINDOW * 10
                )
                distances = [snapshot.player.position.distance_to(upstairs)]

                for _ in range(80):
                    key = policy.choose_key(snapshot)
                    if key == UP_STAIRS_KEY:
                        break
                    self.assertIn(key, offsets)
                    dy, dx = offsets[key]
                    destination = Position(
                        snapshot.player.position.y + dy,
                        snapshot.player.position.x + dx,
                    )
                    destination_grid = snapshot.grid_at(destination)
                    if destination_grid is not None and destination_grid.has_monster:
                        grids = dict(snapshot.grids)
                        grids[destination] = replace(
                            destination_grid, has_monster=False, monster_index=0
                        )
                        snapshot = replace(
                            snapshot,
                            grids=grids,
                            visible_monsters=[
                                monster
                                for monster in snapshot.visible_monsters
                                if monster.position != destination
                            ],
                            turn=snapshot.turn + 1,
                        )
                    else:
                        snapshot = replace(
                            snapshot,
                            player=replace(snapshot.player, position=destination),
                            turn=snapshot.turn + 1,
                        )
                    distances.append(snapshot.player.position.distance_to(upstairs))

                self.assertEqual(key, UP_STAIRS_KEY)
                self.assertEqual(policy.last_reason, "breeder-breakthrough:ascend")
                self.assertEqual(snapshot.player.position, upstairs)
                self.assertTrue(all(
                    later <= earlier
                    for earlier, later in zip(distances, distances[1:])
                ))
                remembered_grids.update(policy._remembered_grids)

    def test_breakthrough_retries_with_detour_only_without_monotone_route(self):
        start = Position(1, 1)
        upstairs = Position(1, 4)
        snapshot = Snapshot(
            player(1, 1),
            {
                start: grid(1, 1),
                upstairs: grid(1, 4, upstairs=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        policy._remembered_floor_t = {
            (1, 1), (1, 0), (2, 0), (3, 0), (3, 1),
            (3, 2), (3, 3), (2, 4), (1, 4),
        }

        detour = policy._breeder_breakthrough_step(snapshot)
        self.assertIsNotNone(detour)
        self.assertGreater(
            detour.distance_to(upstairs), start.distance_to(upstairs)
        )

        policy._remembered_floor_t.add((1, 2))
        policy._remembered_floor_t.add((1, 3))
        self.assertEqual(
            policy._breeder_breakthrough_step(snapshot), Position(1, 2)
        )

    def test_incident_breakthrough_replay_uses_chronological_capture_memory(self):
        captures = [
            Path(__file__).parents[1]
            / "incident-captures"
            / "20260729-1943-breakthrough-oscillation"
            / "oscillation-turn.jsonl",
            Path(__file__).parents[1]
            / "incident-captures"
            / "20260729-2009-breakthrough-retreat"
            / "retreat-turn191760.jsonl",
            Path(__file__).parents[1]
            / "incident-captures"
            / "20260729-2038-monotone-deadend"
            / "deadend.jsonl",
        ]
        monraces = Path(
            r"C:\hengband\.worktrees\bot-json-output\lib\edit"
            r"\MonraceDefinitions.jsonc"
        )
        if (
            not all(capture.is_file() for capture in captures)
            or not monraces.is_file()
        ):
            self.skipTest("real breakthrough incident captures are not available")
        knowledge = load_monrace_knowledge(monraces)
        snapshots = [
            (
                lambda snapshot: replace(
                    snapshot,
                    inventory=[],
                    visible_monsters=[
                        replace(
                            monster,
                            max_melee_damage=max(
                                monster.max_melee_damage,
                                snapshot.player.max_hp * 0.05,
                            ),
                        )
                        for monster in snapshot.visible_monsters
                    ],
                )
            )(
                parse_snapshot(
                    json.loads(capture.read_text(encoding="utf-8")), knowledge
                )
            )
            for capture in captures
        ]
        policy = HengbotPolicy(monrace_knowledge=knowledge)
        policy._fundraising_mode = "mine"
        for seed_snapshot in snapshots[:2]:
            policy._observe(seed_snapshot)
            policy._build_grid_index(seed_snapshot)

        snapshot = snapshots[2]
        policy._build_grid_index(snapshot)
        current_window = HengbotPolicy(monrace_knowledge=knowledge)
        current_window._build_grid_index(snapshot)
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
        policy._floor_t = current_window._floor_t
        policy._door_t = current_window._door_t
        policy._rubble_t = current_window._rubble_t
        policy._breeder_breakthrough_floor = snapshot.floor_key
        policy._breeder_engagement_score = BREEDER_CONTAINMENT_WINDOW * 10
        self.assertIsNotNone(policy._breeder_breakthrough_step(snapshot))
        offsets = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }
        upstairs = Position(14, 18)
        reasons = []

        for _ in range(80):
            key = policy.choose_key(snapshot)
            reasons.append(policy.last_reason)
            if key == UP_STAIRS_KEY:
                break
            self.assertIn(key, offsets)
            dy, dx = offsets[key]
            destination = Position(
                snapshot.player.position.y + dy,
                snapshot.player.position.x + dx,
            )
            destination_grid = snapshot.grid_at(destination)
            if destination_grid is not None and destination_grid.has_monster:
                grids = dict(snapshot.grids)
                grids[destination] = replace(
                    destination_grid, has_monster=False, monster_index=0
                )
                snapshot = replace(
                    snapshot,
                    grids=grids,
                    visible_monsters=[
                        monster
                        for monster in snapshot.visible_monsters
                        if monster.position != destination
                    ],
                    turn=snapshot.turn + 1,
                )
            else:
                snapshot = replace(
                    snapshot,
                    player=replace(snapshot.player, position=destination),
                    turn=snapshot.turn + 1,
                )

        self.assertEqual(snapshot.player.position, upstairs)
        self.assertEqual(key, UP_STAIRS_KEY)
        self.assertEqual(reasons[-1], "breeder-breakthrough:ascend")
        self.assertNotIn("breeder-breakthrough:upstairs-not-found", reasons)
        self.assertNotIn("no-wait:flee", reasons)

    def test_choke_hold_sanction_does_not_mask_ranged_emergency(self):
        base = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        archer = replace(
            base.visible_monsters[0],
            position=Position(10, 11),
            distance=2,
            max_ranged_damage=12,
        )
        grids = dict(base.grids)
        grids[archer.position] = replace(grids[archer.position], has_monster=True)
        snapshot = replace(
            base,
            grids=grids,
            visible_monsters=[archer, base.visible_monsters[1]],
            inventory=[
                item("p", TVAL_SCROLL, SV_SCROLL_PHASE_DOOR, count=5)
            ],
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)
        policy.last_reason = "melee:choke-hold"

        key = policy._forbid_wait_while_damaged(snapshot, WAIT_KEY)

        self.assertEqual((key, policy.last_reason), (
            READ_KEY + "p", "no-wait:escape-scroll",
        ))

    def test_kill_less_choke_hold_does_not_arm_walk_out(self):
        snapshot = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        policy = HengbotPolicy()

        for _ in range(BREEDER_CONTAINMENT_WINDOW + 1):
            policy.choose_key(snapshot)
            if policy._fruitless_disengage_floor == snapshot.floor_key:
                break

        self.assertIsNone(policy._fruitless_disengage_floor)
        self.assertFalse(policy.last_reason.startswith("combat:disengage"))
        self.assertNotEqual(policy.last_reason, "combat:fruitless")

    def test_visibility_churn_does_not_arm_breeder_walk_out(self):
        base = self._mouse_swarm_snapshot(at_choke=True, adjacent=False)
        policy = HengbotPolicy()

        for decision in range(BREEDER_CONTAINMENT_WINDOW + 2):
            visible = (
                base.visible_monsters[:-1]
                if decision % 2
                else base.visible_monsters
            )
            policy.choose_key(replace(base, visible_monsters=visible))
            if policy._fruitless_disengage_floor == base.floor_key:
                break

        self.assertIsNone(policy._fruitless_disengage_floor)

    def test_hunt_approaches_large_pack_when_aggregate_threat_is_immaterial(self):
        monsters = [
            hostile(i, 10, 10 + i, hp=40, max_hp=40, distance=i,
                    max_melee_damage=10)
            for i in range(2, 6)
        ]
        snapshot = Snapshot(
            player(10, 10, hp=232, max_hp=232, level=11),
            {Position(10, 10): grid(10, 10)},
            monsters,
            floor_key=(2, 5, 0),
        )
        policy = HengbotPolicy()
        approach = Position(10, 11)

        with (
            patch.object(policy, "_predicted_damage", return_value=48) as predicted,
            patch.object(policy, "_nearest_goal_step", return_value=approach),
        ):
            step = policy._hunt_step(snapshot, monsters)

        self.assertEqual(step, approach)
        predicted.assert_called_once_with(snapshot, monsters, 3)

    def test_hunt_bails_from_large_pack_when_aggregate_threat_is_material(self):
        monsters = [
            hostile(i, 10, 10 + i, hp=40, max_hp=40, distance=i,
                    max_melee_damage=10)
            for i in range(2, 6)
        ]
        snapshot = Snapshot(
            player(10, 10, hp=200, max_hp=200, level=11),
            {Position(10, 10): grid(10, 10)},
            monsters,
            floor_key=(2, 5, 0),
        )
        policy = HengbotPolicy()

        with (
            patch.object(policy, "_predicted_damage", return_value=100),
            patch.object(policy, "_nearest_goal_step") as nearest,
        ):
            step = policy._hunt_step(snapshot, monsters)

        self.assertIsNone(step)
        nearest.assert_not_called()

    def test_hunt_pack_midpoint_replay_cools_claim_before_cell_guard(self):
        """Capture-derived midpoint hunt releases through the public policy path."""
        policy = HengbotPolicy()
        grids = {
            Position(y, x): grid(y, x)
            for y in range(18, 27)
            for x in range(4, 9)
        }
        north = hostile(1, 19, 5, hp=12, max_hp=12, distance=3, race_id=35)
        south = hostile(2, 25, 7, hp=12, max_hp=12, distance=3, race_id=35)
        base = Snapshot(
            player(22, 6, hp=242, max_hp=242, level=12),
            grids,
            [north, south],
            floor_key=(2, 1, 0),
        )

        for decision in range(policy_module.HUNT_RANGE):
            moving = replace(
                base,
                player=replace(base.player, position=Position(22 + decision % 2, 6)),
            )
            self.assertIn(policy.choose_key(moving), set("12346789"))
            self.assertEqual(policy.last_reason, "hunt")
        policy.choose_key(replace(base, player=replace(base.player, position=Position(22, 6))))

        self.assertEqual(policy.last_reason, "explore")
        self.assertEqual(
            {(identity[0], identity[1]) for identity in policy._hunt_cooled_targets},
            {(1, 35), (2, 35)},
        )
        self.assertEqual(
            policy.consume_pending_hunt_report(),
            "hunt:abandoned-no-damage-no-closure",
        )

    def test_quest_hunt_target_is_exempt_from_opportunistic_cooling(self):
        policy = HengbotPolicy()
        monster = hostile(1, 10, 14, hp=12, max_hp=12, distance=4, race_id=35)
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, x): grid(10, x) for x in range(10, 15)},
            [monster],
            floor_key=(2, 1, 1),
        )
        for decision in range(policy_module.HUNT_RANGE + 2):
            policy._decision_sequence = decision
            policy._hunt_step(snapshot, [monster], allow_cooling=False)
        policy._decision_sequence += 1
        policy._hunt_step(snapshot, [monster])

        self.assertFalse(policy._hunt_cooled_targets)

    def test_new_hunt_target_gets_its_own_closure_baseline(self):
        policy = HengbotPolicy()
        grids = {Position(10, x): grid(10, x) for x in range(10, 16)}
        decision = 0
        for distance in (4, 3, 2, 1):
            monster = hostile(1, 10, 10 + distance, hp=12, max_hp=12,
                              distance=distance, race_id=35)
            snapshot = Snapshot(player(10, 10), grids, [monster], floor_key=(2, 1, 0))
            policy._decision_sequence = decision
            policy._hunt_step(snapshot, [monster])
            decision += 1

        for distance in (4, 3, 2):
            monster = hostile(2, 10, 10 + distance, hp=12, max_hp=12,
                              distance=distance, race_id=36)
            snapshot = Snapshot(player(10, 10), grids, [monster], floor_key=(2, 1, 0))
            policy._decision_sequence = decision
            policy._hunt_step(snapshot, [monster])
            decision += 1

        identity = policy._hunt_target_identities[2]
        self.assertEqual(policy._hunt_progress[identity]["steps"], 0)
        self.assertNotIn(identity, policy._hunt_cooled_targets)

        for _ in range(policy_module.HUNT_RANGE):
            policy._decision_sequence = decision
            policy._hunt_step(snapshot, [monster])
            decision += 1
        self.assertIn(identity, policy._hunt_cooled_targets)

    def test_hunt_blink_does_not_restore_the_full_progress_budget(self):
        policy = HengbotPolicy()
        grids = {
            Position(y, x): grid(y, x)
            for y in range(8, 13) for x in range(10, 16)
        }
        positions = (Position(10, 14), Position(11, 14), Position(9, 14))
        visible = []
        for position in positions:
            monster = hostile(
                7, position.y, position.x, hp=12, max_hp=12,
                distance=4, race_id=35,
            )
            visible.append(Snapshot(
                player(10, 10), grids, [monster], floor_key=(2, 1, 0)
            ))
        hidden = replace(visible[0], visible_monsters=[])
        hunt_decisions = 0

        for decision in range(60):
            snapshot = (
                hidden
                if decision % 5 == 4
                else visible[(decision // 5) % len(visible)]
            )
            policy.choose_key(snapshot)
            if policy.last_reason == "hunt":
                hunt_decisions += 1
            if policy._hunt_cooled_targets:
                break

        self.assertLessEqual(hunt_decisions, policy_module.HUNT_RANGE)
        self.assertTrue(policy._hunt_cooled_targets)

    def test_hunt_progress_counts_once_per_decision_not_per_call(self):
        policy = HengbotPolicy()
        monster = hostile(3, 10, 14, hp=12, max_hp=12, distance=4, race_id=37)
        snapshot = Snapshot(
            player(10, 10),
            {Position(10, x): grid(10, x) for x in range(10, 15)},
            [monster],
            floor_key=(2, 1, 0),
        )
        with patch.object(policy, "_nearest_goal_step", return_value=Position(10, 11)):
            for decision in range(policy_module.HUNT_RANGE):
                policy._decision_sequence = decision
                for _ in range(3):
                    self.assertIsNotNone(policy._hunt_step(snapshot, [monster]))
                self.assertFalse(policy._hunt_cooled_targets)
            policy._decision_sequence = policy_module.HUNT_RANGE
            self.assertIsNone(policy._hunt_step(snapshot, [monster]))

    def test_reused_monster_index_gets_a_fresh_cooldown_identity(self):
        policy = HengbotPolicy()
        grids = {Position(10, x): grid(10, x) for x in range(10, 16)}
        old = hostile(8, 10, 14, hp=12, max_hp=12, distance=4, race_id=35)
        old_snapshot = Snapshot(player(10, 10), grids, [old], floor_key=(2, 1, 0))
        for decision in range(policy_module.HUNT_RANGE + 1):
            policy._decision_sequence = decision
            policy._hunt_step(old_snapshot, [old])
        self.assertTrue(policy._hunt_cooled_targets)

        policy._decision_sequence += 1
        empty = replace(old_snapshot, visible_monsters=[])
        policy._hunt_step(empty, [])
        new = hostile(8, 10, 13, hp=12, max_hp=12, distance=3, race_id=36)
        new_snapshot = replace(old_snapshot, visible_monsters=[new])
        policy._decision_sequence += 1

        with patch.object(policy, "_nearest_goal_step", return_value=Position(10, 11)):
            self.assertIsNotNone(policy._hunt_step(new_snapshot, [new]))
        self.assertNotEqual(
            policy._hunt_target_identities[8], next(iter(policy._hunt_cooled_targets))
        )

    def test_hunt_still_rejects_individually_dangerous_target(self):
        monster = hostile(
            1, 10, 13, hp=300, max_hp=300, distance=3, speed=121,
            max_melee_damage=1,
        )
        snapshot = Snapshot(
            player(10, 10, hp=400, max_hp=200, level=11, speed=110),
            {Position(10, 10): grid(10, 10)},
            [monster],
            floor_key=(2, 5, 0),
        )
        policy = HengbotPolicy()

        with patch.object(policy, "_nearest_goal_step") as nearest:
            step = policy._hunt_step(snapshot, [monster])

        self.assertIsNone(step)
        nearest.assert_not_called()

    def test_hunt_does_not_close_with_material_sleeping_threat(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(8, 13)
            for x in range(79, 85)
        }
        monster = hostile(
            1,
            11,
            83,
            hp=100,
            max_hp=100,
            distance=3,
            asleep=True,
            max_melee_damage=60,
        )
        grids[monster.position] = grid(11, 83, monster=True)
        snapshot = Snapshot(
            player(8, 80, hp=306, max_hp=306, level=15),
            grids,
            [monster],
            floor_key=(2, 5, 0),
        )
        policy = HengbotPolicy()

        policy.choose_key(snapshot)

        self.assertEqual(policy.last_reason, "threat:avoid-engagement")

    def test_material_threat_retreat_invalidates_returning_explore_path(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(3, 7)
            for x in range(8, 19)
        }
        monster = hostile(
            1,
            4,
            18,
            hp=60,
            max_hp=60,
            distance=8,
            speed=120,
            max_melee_damage=16,
        )
        grids[monster.position] = grid(4, 18, monster=True)
        danger = Snapshot(
            player(5, 10, hp=189, max_hp=189, level=7),
            grids,
            [monster],
            floor_key=(2, 6, 0),
        )
        policy = HengbotPolicy()
        policy._explore_path = [Position(5, 9), Position(5, 10)]

        policy.choose_key(danger)

        self.assertEqual(policy.last_reason, "threat:avoid-engagement")
        self.assertIn(Position(5, 10), policy._engagement_avoid_cells)
        self.assertEqual(policy._explore_path, [])

        retreated = replace(
            danger,
            player=player(5, 9, hp=189, max_hp=189, level=7),
            visible_monsters=[replace(monster, distance=9)],
        )
        policy._explore_path = [Position(5, 10), Position(5, 11)]
        policy._build_grid_index(retreated)

        self.assertNotEqual(policy._explore_step(retreated), Position(5, 10))

    def test_material_threat_retreat_does_not_reenter_abandoned_cell(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(4, 7)
            for x in range(9, 12)
        }
        monster = hostile(
            1,
            5,
            18,
            hp=100,
            max_hp=100,
            distance=8,
            speed=115,
            max_melee_damage=88,
        )
        snapshot = Snapshot(
            player(5, 10, hp=501, max_hp=501, level=28),
            grids,
            [monster],
            floor_key=(1, 30, 0),
        )
        policy = HengbotPolicy()
        abandoned = Position(5, 9)
        policy._engagement_avoid_cells.add(abandoned)
        policy._build_grid_index(snapshot)

        step = policy._flee_step(snapshot, [monster])

        self.assertIsNotNone(step)
        self.assertNotEqual(step, abandoned)
        self.assertNotIn(step, policy._engagement_avoid_cells)

    def test_flee_step_relaxes_veto_when_fully_boxed_in(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(4, 7)
            for x in range(9, 12)
        }
        monster = hostile(
            1, 5, 18, hp=100, max_hp=100, distance=8, speed=115,
            max_melee_damage=88,
        )
        snapshot = Snapshot(
            player(5, 10, hp=501, max_hp=501, level=28),
            grids,
            [monster],
            floor_key=(1, 30, 0),
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)
        # Veto EVERY walkable neighbour: the retreat has boxed itself in.
        neighbours = policy._walkable_neighbors(snapshot, Position(5, 10))
        self.assertTrue(neighbours)
        policy._engagement_avoid_cells.update(neighbours)

        step = policy._flee_step(snapshot, [monster])

        # Rather than returning None (-> status-threat:wait deadlock), step onto
        # the least-bad vetoed neighbour to break out of the self-made box.
        self.assertIsNotNone(step)
        self.assertIn(step, neighbours)

    def test_disengage_cuts_through_when_recent_retreat_has_no_destination(self):
        from collections import deque
        policy = HengbotPolicy()
        # The last decisions ping-ponged between two corner cells.
        policy._recent = deque([Position(1, 78), Position(1, 79)] * 6, maxlen=64)
        snapshot = Snapshot(
            player(1, 78, hp=264, max_hp=264, level=13),
            {Position(1, 78): grid(1, 78)},
            [],
            floor_key=(2, 5, 0),
        )
        swarm = [
            hostile(1, 1, 79, hp=4, max_hp=4, distance=1,
                    can_multiply=True, max_melee_damage=4)
        ]
        policy._summoner_retreat_step = lambda *a: Position(1, 79)  # a recent cell
        policy._escape_by_stairs = lambda s: None
        policy._nearest_goal_step = lambda s, pred: None  # no known up-stairs
        policy._explore_step = lambda s: Position(2, 78)  # frontier: open floor
        policy.threat_prediction = lambda *a, **k: {"operational_total": 6}

        key = policy._disengage_move_or_escalate(snapshot, swarm, swarm)

        self.assertEqual(policy.last_reason, "combat:disengage-cut-through")
        self.assertEqual(key, policy._step_toward(snapshot, Position(2, 78)))

    def test_disengage_routes_to_upstairs_when_swarmed(self):
        from collections import deque
        policy = HengbotPolicy()
        policy._recent = deque([Position(1, 78), Position(1, 79)] * 6, maxlen=64)
        snapshot = Snapshot(
            player(1, 78, hp=264, max_hp=264, level=13),
            {Position(1, 78): grid(1, 78)},
            [],
            floor_key=(2, 5, 0),
        )
        swarm = [
            hostile(1, 1, 79, hp=4, max_hp=4, distance=1,
                    can_multiply=True, max_melee_damage=4)
        ]
        policy._summoner_retreat_step = lambda *a: None
        policy._escape_by_stairs = lambda s: None  # not standing on stairs
        policy._nearest_goal_step = lambda s, pred: Position(2, 78)  # step to up-stairs
        policy._blocking_escape_melee_key = lambda *a: "6"

        key = policy._disengage_move_or_escalate(snapshot, swarm, swarm)

        # A reachable staircase outranks attacking a route blocker.
        self.assertEqual(policy.last_reason, "combat:disengage-seek-upstairs")
        self.assertEqual(key, policy._step_toward(snapshot, Position(2, 78)))

    def test_disengage_clears_two_weak_blockers_before_retreating_from_exit(self):
        policy = HengbotPolicy()
        blockers = [
            hostile(
                index, 10, x, hp=4, max_hp=4, distance=x - 10,
                can_multiply=True, max_melee_damage=1,
            )
            for index, x in enumerate((11, 12), 1)
        ]
        snapshot = Snapshot(
            player(
                10, 10, hp=100, max_hp=100, level=10,
                main_hand_blows=2, main_hand_to_d=5,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
                Position(10, 12): grid(10, 12, monster=True),
                Position(10, 13): grid(10, 13, upstairs=True),
                Position(10, 9): grid(10, 9),
            },
            blockers,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1, name="Broad Sword",
                    is_equipment=True, damage_dice_num=2, damage_dice_sides=5,
                )
            ],
        )
        policy._build_grid_index(snapshot)
        with patch.object(
            policy, "_summoner_retreat_step", return_value=None
        ) as retreat, patch.object(policy, "_nearest_goal_step", return_value=None):
            key = policy._disengage_move_or_escalate(
                snapshot, blockers, blockers
            )

        self.assertEqual((key, policy.last_reason), ("6", "combat:disengage-clear-path"))
        retreat.assert_called_once()

    def test_disengage_reads_recall_to_leave_the_floor(self):
        from collections import deque
        policy = HengbotPolicy()
        policy._recent = deque(maxlen=64)
        snapshot = Snapshot(
            player(5, 5, hp=264, max_hp=264, level=13),
            {Position(5, 5): grid(5, 5)},
            [],
            floor_key=(2, 5, 0),
            inventory=[item("f", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5)],
        )
        swarm = [
            hostile(1, 5, 6, hp=4, max_hp=4, distance=1,
                    can_multiply=True, max_melee_damage=4)
        ]
        # The live failure: the return latch is unset, so the ordinary recall
        # path never issues the scroll. The disengage must read it directly.
        policy._returning_to_town = False
        key = policy._disengage_move_or_escalate(snapshot, swarm, swarm)
        self.assertEqual(policy.last_reason, "combat:disengage-recall")
        self.assertEqual(key, "rf")

    def test_disengage_retreats_normally_when_not_oscillating(self):
        from collections import deque
        policy = HengbotPolicy()
        policy._recent = deque(maxlen=64)  # empty -> not oscillating
        snapshot = Snapshot(
            player(5, 5, hp=264, max_hp=264, level=13),
            {Position(5, 5): grid(5, 5)},
            [],
            floor_key=(2, 5, 0),
        )
        swarm = [
            hostile(1, 5, 6, hp=4, max_hp=4, distance=1,
                    can_multiply=True, max_melee_damage=4)
        ]
        policy._summoner_retreat_step = lambda *a: Position(5, 6)
        policy._escape_by_stairs = lambda s: None

        key = policy._disengage_move_or_escalate(snapshot, swarm, swarm)

        # Not oscillating: the ordinary retreat step is still taken.
        self.assertEqual(policy.last_reason, "combat:disengage-step")
        self.assertEqual(key, policy._step_toward(snapshot, Position(5, 6)))

    def test_killable_large_brown_snake_is_not_a_material_threat(self):
        snake = hostile(
            1,
            4,
            18,
            hp=24,
            max_hp=24,
            distance=8,
            speed=100,
            max_melee_damage=16,
        )
        weapon = item(
            "main_hand",
            TVAL_SWORD,
            0,
            is_equipment=True,
            damage_dice_num=2,
            damage_dice_sides=6,
        )
        snapshot = Snapshot(
            player(
                5,
                10,
                hp=189,
                max_hp=189,
                level=7,
                main_hand_blows=4,
                main_hand_to_d=5,
            ),
            {
                Position(5, 10): grid(5, 10),
                snake.position: grid(4, 18, monster=True),
            },
            [snake],
            floor_key=(2, 6, 0),
            equipment=[weapon],
        )

        self.assertFalse(policy_module.HengbotPolicy()._material_melee_engagement(
            snapshot, snake
        ))

    def test_three_turn_damage_near_quarter_hp_does_not_force_retreat(self):
        monster = hostile(
            1,
            4,
            18,
            hp=100,
            max_hp=100,
            distance=8,
            speed=110,
            max_melee_damage=16,
        )
        snapshot = Snapshot(
            player(5, 10, hp=189, max_hp=189, level=7),
            {
                Position(5, 10): grid(5, 10),
                monster.position: grid(4, 18, monster=True),
            },
            [monster],
            floor_key=(2, 6, 0),
        )

        self.assertFalse(HengbotPolicy()._material_melee_engagement(
            snapshot, monster
        ))

    def test_attacks_adjacent_hostile(self):
        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, monster=True)}
        snap = Snapshot(player(10, 10), grids, [hostile(1, 10, 11, hp=3)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "6")

    def test_attacks_an_adjacent_hallucinated_monster(self):
        # A hallucinated monster arrives with unknown (sentinel) HP and no race;
        # the bot must still melee it rather than rest or wander into it.
        from hengbot.model import UNKNOWN_MONSTER_HP

        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, monster=True)}
        mon = hostile(1, 10, 11, hp=UNKNOWN_MONSTER_HP, max_hp=UNKNOWN_MONSTER_HP)
        snap = Snapshot(player(10, 10, hp=100, max_hp=100), grids, [mon])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "melee")

    def test_attacks_weakest_adjacent_first(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, monster=True),
            Position(10, 9): grid(10, 9, monster=True),
        }
        monsters = [hostile(1, 10, 11, hp=9), hostile(2, 10, 9, hp=2)]
        # The 2-hp monster to the west should be struck first.
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, monsters)), "4")

    def test_retreats_when_low_hp(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=2, max_hp=20), grids, [hostile(1, 10, 11, hp=10)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "4")

    def test_prioritizes_an_adjacent_summoner(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9, monster=True),
            Position(10, 11): grid(10, 11, monster=True),
        }
        monsters = [
            hostile(1, 10, 9, hp=100, max_hp=100, can_summon=True),
            hostile(2, 10, 11, hp=1, max_hp=10),
        ]
        self.assertEqual(
            HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, monsters)),
            "4",
        )

    def test_retreats_from_an_open_summoner_fight_to_a_corridor(self):
        grids = {}
        for y in range(9, 12):
            for x in range(9, 12):
                grids[Position(y, x)] = grid(y, x)
        grids[Position(9, 9)] = grid(9, 9, passable=False)
        grids[Position(11, 9)] = grid(11, 9, passable=False)
        grids[Position(10, 8)] = grid(10, 8)
        grids[Position(10, 7)] = grid(10, 7)
        grids[Position(10, 12)] = grid(10, 12)
        grids[Position(10, 13)] = grid(10, 13, monster=True)
        summoner = hostile(
            1, 10, 13, hp=80, max_hp=80, distance=3, can_summon=True
        )
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100), grids, [summoner],
            floor_key=(1, 5, 0),
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "4")
        self.assertEqual(pol.last_reason, "summoner:retreat")

    def test_does_not_retreat_from_a_sleeping_summoner(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(9, 12)
            for x in range(7, 14)
        }
        grids[Position(9, 9)] = grid(9, 9, passable=False)
        grids[Position(11, 9)] = grid(11, 9, passable=False)
        grids[Position(10, 13)] = grid(10, 13, monster=True)
        summoner = hostile(
            1, 10, 13, hp=80, max_hp=80, distance=3,
            asleep=True, can_summon=True,
        )
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100), grids, [summoner],
            floor_key=(1, 5, 0),
        )
        pol = HengbotPolicy()

        key = pol.choose_key(snap)

        self.assertNotEqual(pol.last_reason, "summoner:retreat")
        self.assertNotEqual(key, "4")

    def test_sleeping_quest_summoner_does_not_flip_flop_with_loot(self):
        quest_info = QuestInfo(
            14, "Warg Problem", 5, 5, 2, dungeon=0,
            num_mon=16, monrace_id=257,
        )
        quest = QuestState(
            id=14, status=QUEST_STATUS_TAKEN, type=5, level=5,
            dungeon_id=0, r_idx=257, cur_num=11, num_mon=16, fixed=True,
        )
        policy = HengbotPolicy(quest_knowledge={14: quest_info})
        loot = Position(10, 9)
        position = Position(10, 10)
        positions = [position]
        reasons = []
        direction_delta = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }

        with (
            patch.object(policy, "_emergency_item", return_value=None),
            patch.object(policy, "_fixed_quest_key", return_value=None),
        ):
            for _ in range(3):
                monster_position = Position(10, 14)
                grids = {
                    Position(y, grid_x): grid(y, grid_x)
                    for y in range(9, 12)
                    for grid_x in range(9, 15)
                }
                grids[loot] = grid(loot.y, loot.x, objects=1)
                grids[monster_position] = grid(
                    monster_position.y, monster_position.x, monster=True
                )
                summoner = hostile(
                    1, monster_position.y, monster_position.x,
                    hp=80, max_hp=80,
                    distance=position.distance_to(monster_position),
                    asleep=True, can_summon=True,
                )
                snap = Snapshot(
                    player(position.y, position.x, hp=605, max_hp=605),
                    grids, [summoner],
                    floor_key=(0, 5, 14), quests={14: quest},
                )

                key = policy.choose_key(snap)
                reasons.append(policy.last_reason)
                self.assertIn(key, direction_delta)
                dy, dx = direction_delta[key]
                next_position = Position(position.y + dy, position.x + dx)
                self.assertLess(
                    next_position.distance_to(monster_position),
                    position.distance_to(monster_position),
                )
                position = next_position
                positions.append(position)

        self.assertNotIn("summoner:retreat", reasons)
        self.assertNotIn("seek-loot", reasons)
        self.assertEqual(len(set(positions)), len(positions))

    def test_flees_even_from_an_almost_dead_enemy_when_low_hp(self):
        # Coarse visible health is useful for target choice, but must not justify
        # continuing combat once the player has crossed the survival threshold.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=20, max_hp=150), grids, [hostile(1, 10, 11, hp=36)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "4")

    def test_still_flees_strong_lone_enemy(self):
        # Same low HP, but the lone enemy is too tough to finish (hp 100 > 60), so
        # the flee still triggers and we back away west.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=20, max_hp=150), grids, [hostile(1, 10, 11, hp=100)])
        self.assertEqual(HengbotPolicy().choose_key(snap), "4")

    def test_still_flees_multiple_weak_enemies(self):
        # With no projected damage output, even two weak enemies are not
        # clearable; the open west square provides a real retreat.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
            Position(11, 11): grid(11, 11, monster=True),
        }
        monsters = [hostile(1, 10, 11, hp=20), hostile(2, 11, 11, hp=20)]
        snap = Snapshot(player(10, 10, hp=20, max_hp=150), grids, monsters)
        # Flees rather than melee because the projected fight is lost.
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertEqual(pol.last_reason, "flee")

    def test_immediately_ascends_when_surrounded_on_landing_stairs(self):
        # Live death on dl9: the bot arrived at full HP on an upstairs tile with
        # ten visible hostiles and several adjacent, but meleed until too hurt to
        # escape. A landing swarm must trigger an immediate retreat upstairs.
        grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(9, 10): grid(9, 10, monster=True),
            Position(10, 11): grid(10, 11, monster=True),
            Position(11, 10): grid(11, 10, monster=True),
        }
        # Dangerous swarm (10/hit each): three adjacent carve ~120 over the
        # lookahead — past the flee threshold (0.6*175=105) but under a lethal
        # 175, so this is the swarm-flee path (not the emergency one) and the
        # landing must retreat upstairs.
        monsters = [
            hostile(1, 9, 10, hp=20, max_melee_damage=10),
            hostile(2, 10, 11, hp=20, max_melee_damage=10),
            hostile(3, 11, 10, hp=20, max_melee_damage=10),
        ]
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(Snapshot(player(10, 10, hp=175, max_hp=175), grids, monsters)), "<")
        self.assertEqual(pol.last_reason, "flee:stairs")

    def test_stays_and_fights_a_weak_landing_swarm_at_full_hp(self):
        # Regression for over-fleeing: a clvl20 warrior landed on dl9 amid three
        # adjacent but weak (lvl-9 Skaven-class, ~10/hit) hostiles and stair-scummed
        # away every descent. At full HP a swarm this soft is not worth fleeing —
        # its predicted damage is far below the threshold — so fight, don't ascend.
        grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(9, 10): grid(9, 10, monster=True),
            Position(10, 11): grid(10, 11, monster=True),
            Position(11, 10): grid(11, 10, monster=True),
        }
        monsters = [
            hostile(1, 9, 10, hp=20, max_melee_damage=10, asleep=True),
            hostile(2, 10, 11, hp=20, max_melee_damage=10, asleep=True),
            hostile(3, 11, 10, hp=20, max_melee_damage=10, asleep=True),
        ]
        pol = HengbotPolicy()
        key = pol.choose_key(Snapshot(player(10, 10, hp=401, max_hp=401), grids, monsters))
        self.assertNotEqual(key, "<")
        self.assertNotIn("flee", pol.last_reason)

    def test_attacks_friendly_in_town(self):
        friendly = MonsterState(1, Position(10, 11), hp=10, max_hp=10, distance=1, friendly=True, pet=False)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        self.assertEqual(
            HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [friendly])),
            "+6y",
        )
class ConsumableTest(unittest.TestCase):
    def _open_room(self):
        return {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }

    def test_quaffs_healing_potion_when_hurt_in_a_fight(self):
        grids = self._open_room()
        inv = [item("c", POTION, 35)]  # Potion of Cure Serious Wounds
        threat = hostile(1, 10, 13, hp=30, max_hp=30, distance=3)  # a monster is near
        snap = Snapshot(player(10, 10, hp=20, max_hp=100), grids, [threat], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), "qc")

    def test_excludes_healing_potion_weaker_than_expected_next_turn_damage(self):
        grids = self._open_room()
        weak = item("c", POTION, 35)  # Cure Serious: expected 18 HP.
        strong = item("h", POTION, 37)  # Healing: 300 HP.
        threat = hostile(1, 10, 11, hp=30, max_hp=30, distance=1)
        snap = Snapshot(
            player(10, 10, hp=20, max_hp=400), grids, [threat],
            inventory=[weak, strong],
        )
        policy = HengbotPolicy()

        with patch.object(
            policy, "_predicted_damage",
            side_effect=lambda *_args, **kwargs: 40 if kwargs.get("expected") else 0,
        ):
            self.assertEqual(policy.choose_key(snap), "qh")
            self.assertEqual(policy.last_reason, "item:heal")

    def test_uses_no_healing_potion_when_all_restore_less_than_expected_damage(self):
        grids = self._open_room()
        weak = item("c", POTION, 35)
        threat = hostile(1, 10, 11, hp=30, max_hp=30, distance=1)
        snap = Snapshot(
            player(10, 10, hp=20, max_hp=100), grids, [threat], inventory=[weak]
        )
        policy = HengbotPolicy()

        with patch.object(
            policy, "_predicted_damage",
            side_effect=lambda *_args, **kwargs: 40 if kwargs.get("expected") else 0,
        ):
            self.assertNotEqual(policy.choose_key(snap), "qc")

    def test_rests_instead_of_quaffing_when_safe(self):
        # Hurt but no enemy in sight: rest heals for free, so don't burn a potion.
        grids = self._open_room()
        inv = [item("c", POTION, 34)]
        snap = Snapshot(player(10, 10, hp=20, max_hp=100), grids, [], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

    def test_does_not_rest_while_fainting_in_town(self):
        grids = self._open_room()
        snap = Snapshot(
            player(10, 10, hp=20, max_hp=100, food=100),
            grids,
            [],
            floor_key=(0, 0, 0),
        )
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

    def test_ignores_unidentified_potion_when_hurt(self):
        grids = self._open_room()
        inv = [item("c", POTION, 34, aware=False)]  # unknown potion — don't gamble
        threat = hostile(1, 10, 13, hp=30, max_hp=30, distance=3)
        snap = Snapshot(player(10, 10, hp=20, max_hp=100), grids, [threat], inventory=inv)
        self.assertNotIn("q", HengbotPolicy().choose_key(snap))

    def test_reads_teleport_scroll_when_about_to_die(self):
        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, monster=True)}
        inv = [item("d", SCROLL, 9)]  # Scroll of Teleport
        mon = hostile(1, 10, 11, hp=30, max_hp=30)
        snap = Snapshot(player(10, 10, hp=5, max_hp=100), grids, [mon], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), "rd")

    def test_eats_food_when_hungry_and_safe(self):
        grids = self._open_room()
        inv = [item("b", FOOD, 35)]  # Ration of Food
        snap = Snapshot(player(10, 10, food=100), grids, [], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), "Eb")

    def test_does_not_eat_when_well_fed(self):
        grids = self._open_room()
        inv = [item("b", FOOD, 35)]
        snap = Snapshot(player(10, 10, food=5000), grids, [], inventory=inv)
        self.assertNotIn("E", HengbotPolicy().choose_key(snap))

    def test_mana_race_eats_a_charged_staff_when_hungry(self):
        # A Zombie (food_type MANA) has no food but a staff with charges; it must
        # "eat" the staff to restore hunger, not starve.
        grids = self._open_room()
        inv = [item("d", STAFF, 0, charges=20)]
        snap = Snapshot(player(10, 10, food=100, food_type=FOOD_TYPE_MANA), grids, [], inventory=inv)
        self.assertEqual(HengbotPolicy().choose_key(snap), "Ed")

    def test_mana_race_ignores_a_depleted_staff(self):
        grids = self._open_room()
        inv = [item("d", STAFF, 0, charges=0)]  # no charges left → not edible
        snap = Snapshot(player(10, 10, food=100, food_type=FOOD_TYPE_MANA), grids, [], inventory=inv)
        self.assertNotIn("E", HengbotPolicy().choose_key(snap))

    def test_normal_race_does_not_eat_a_staff(self):
        grids = self._open_room()
        inv = [item("d", STAFF, 0, charges=20)]  # normal race can't eat devices
        snap = Snapshot(player(10, 10, food=100, food_type=0), grids, [], inventory=inv)
        self.assertNotIn("E", HengbotPolicy().choose_key(snap))
class PredictiveEscapeTest(unittest.TestCase):
    def _line_snapshot(self, monster, *, hp=30, inventory=None, upstairs=False):
        grids = {
            Position(10, x): grid(
                10,
                x,
                monster=(x == monster.position.x),
                upstairs=(upstairs and x == 10),
            )
            for x in range(10, monster.position.x + 1)
        }
        return Snapshot(
            player(10, 10, hp=hp, max_hp=100),
            grids,
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=inventory or [],
        )

    def test_counts_melee_enemy_that_can_reach_within_three_turns(self):
        monster = hostile(
            1, 10, 12, distance=2, max_melee_damage=20
        )
        snap = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")

    def test_escapes_before_ranged_blindness_forces_a_lethal_cure_turn(self):
        # Live 2026-07-24 regression: Dokuro's ordinary three-turn operational
        # damage (228) was below 326 HP, so the bot repositioned until BA_LITE
        # dealt 234 and blinded it.  Cure Critical then consumed the only turn
        # in which a teleport scroll could have been read, and the next cast
        # killed the character.  Budget that forced cure turn before the status
        # lands: 228 + 103 >= 326.
        monster = replace(
            hostile(
                1,
                7,
                48,
                distance=9,
                max_melee_damage=120,
                max_ranged_damage=170,
            ),
            race_id=1124,
            speed=115,
        )
        knowledge = MonraceKnowledge(
            max_hp=900,
            average_hp=900,
            speed=115,
            can_summon=False,
            friendly=False,
            level=30,
            max_melee_damage=120,
            max_ranged_damage=170,
            abilities=frozenset(
                {
                    "CONF",
                    "ANIM_DEAD",
                    "BLINK",
                    "HOLD",
                    "CAUSE_3",
                    "BLIND",
                    "SHRIEK",
                    "BA_LITE",
                }
            ),
            spell_frequency=16,
        )
        grids = {
            Position(7, x): grid(7, x, monster=(x == 48))
            for x in range(39, 49)
        }
        snapshot = Snapshot(
            player(
                7,
                39,
                hp=326,
                max_hp=533,
                abilities=frozenset(
                    {"free_action", "resist_conf", "resist_chaos"}
                ),
            ),
            grids,
            [monster],
            floor_key=(DUNGEON_ANGBAND, 40, 0),
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        policy = HengbotPolicy(monrace_knowledge={1124: knowledge})

        with patch.object(
            policy,
            "_predicted_damage",
            side_effect=lambda _snapshot, _hostiles, turns, **_kwargs: {
                3: 228,
                1: 103,
            }[turns],
        ):
            self.assertEqual(policy.choose_key(snapshot), "rt")

        self.assertEqual(policy.last_reason, "emergency:teleport")
        self.assertEqual(
            policy._last_return_trigger, "emergency-ranged-status-lock"
        )

    def test_does_not_escape_when_ranged_status_cure_turn_is_survivable(self):
        monster = replace(
            hostile(
                1, 10, 14, distance=4, max_melee_damage=0, max_ranged_damage=20
            ),
            race_id=6000,
        )
        knowledge = MonraceKnowledge(
            max_hp=20,
            speed=110,
            can_summon=False,
            friendly=False,
            level=5,
            max_ranged_damage=20,
            abilities=frozenset({"BA_LITE"}),
            spell_frequency=20,
        )
        snapshot = self._line_snapshot(
            monster,
            hp=100,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        policy = HengbotPolicy(monrace_knowledge={6000: knowledge})

        with patch.object(
            policy,
            "_predicted_damage",
            side_effect=lambda _snapshot, _hostiles, turns, **_kwargs: {
                3: 40,
                1: 20,
            }[turns],
        ):
            self.assertIsNone(
                policy._emergency_item(snapshot, snapshot.visible_monsters)
            )

    def test_unresisted_adjacent_confusion_blow_triggers_retreat(self):
        monster = replace(
            hostile(1, 10, 11, distance=1, max_melee_damage=1),
            race_id=6001,
        )
        knowledge = MonraceKnowledge(
            max_hp=20,
            average_hp=20,
            speed=110,
            can_summon=False,
            friendly=False,
            level=10,
            max_melee_damage=1,
            blows=(MonsterBlow("HIT", "CONFUSE", 1, 1),),
        )
        snap = self._line_snapshot(
            monster,
            hp=100,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        policy = HengbotPolicy(monrace_knowledge={6001: knowledge})

        self.assertEqual(policy.choose_key(snap), "rt")
        self.assertEqual(policy.last_reason, "status-threat:scroll")

        protected = replace(
            snap,
            player=replace(snap.player, abilities=frozenset({"resist_conf"})),
        )
        protected_policy = HengbotPolicy(monrace_knowledge={6001: knowledge})
        self.assertEqual(protected_policy.choose_key(protected), "6")
        self.assertEqual(protected_policy.last_reason, "melee")

    def test_unresisted_adjacent_paralysis_blow_triggers_retreat(self):
        monster = replace(
            hostile(1, 10, 11, distance=1, max_melee_damage=1),
            race_id=6002,
        )
        knowledge = MonraceKnowledge(
            max_hp=20,
            average_hp=20,
            speed=110,
            can_summon=False,
            friendly=False,
            level=10,
            max_melee_damage=1,
            blows=(MonsterBlow("TOUCH", "PARALYZE", 1, 1),),
        )
        snap = self._line_snapshot(
            monster,
            hp=100,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        policy = HengbotPolicy(monrace_knowledge={6002: knowledge})

        self.assertEqual(policy.choose_key(snap), "rt")
        self.assertEqual(policy.last_reason, "status-threat:scroll")

        protected = replace(
            snap,
            player=replace(
                snap.player,
                abilities=frozenset({"free_action"}),
                ability_sources=AbilitySources(
                    {"free_action": frozenset({"equipment"})}
                ),
            ),
        )
        protected_policy = HengbotPolicy(monrace_knowledge={6002: knowledge})
        self.assertEqual(protected_policy.choose_key(protected), "6")
        self.assertEqual(protected_policy.last_reason, "melee")

    def test_paralyzer_hunt_closure_is_vetoed_through_choose_key_after_restart(self):
        monster = replace(
            hostile(1, 10, 12, distance=2, max_melee_damage=0),
            race_id=6010,
            asleep=True,
        )
        knowledge = MonraceKnowledge(
            max_hp=20,
            average_hp=20,
            speed=110,
            can_summon=False,
            friendly=False,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {
                Position(y, x): grid(
                    y, x, monster=(y == 10 and x == 12)
                )
                for y in range(8, 13)
                for x in range(8, 14)
            },
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )

        for policy in (
            HengbotPolicy(monrace_knowledge={6010: knowledge}),
            HengbotPolicy(monrace_knowledge={6010: knowledge}),
        ):
            key = policy.choose_key(snapshot)
            self.assertNotEqual(key, "6")
            self.assertIn(Position(10, 11), policy._paralyzer_avoid_cells)

        unseen = replace(
            snapshot,
            visible_monsters=[],
            grids={
                position: replace(
                    cell, has_monster=False, monster_index=0,
                    in_view=False, currently_observed=False,
                ) if position == monster.position else cell
                for position, cell in snapshot.grids.items()
            },
        )
        policy.choose_key(unseen)
        self.assertIn(monster.position, policy._remembered_paralyzers)
        self.assertIn(Position(10, 11), policy._paralyzer_avoid_cells)

        gone = replace(
            snapshot,
            visible_monsters=[],
            grids={
                position: replace(cell, has_monster=False, monster_index=0)
                if position == monster.position else cell
                for position, cell in snapshot.grids.items()
            },
        )
        gone = replace(
            gone,
            grids={
                position: replace(
                    cell, in_view=True, currently_observed=True, lit=True
                )
                if position == monster.position else cell
                for position, cell in gone.grids.items()
            },
        )
        policy.choose_key(gone)
        self.assertNotIn(Position(10, 11), policy._engagement_avoid_cells)
        self.assertNotIn(monster.position, policy._remembered_paralyzers)

        ambiguous = replace(
            snapshot,
            player=replace(
                snapshot.player,
                abilities=frozenset({"free_action"}),
                ability_sources=AbilitySources(),
            ),
        )
        fail_closed = HengbotPolicy(monrace_knowledge={6010: knowledge})
        self.assertNotEqual(fail_closed.choose_key(ambiguous), "6")
        self.assertIn(Position(10, 11), fail_closed._paralyzer_avoid_cells)

    def test_stationary_paralyzer_guarding_loot_is_killed_with_pack_torch(self):
        monster = replace(
            hostile(1, 10, 13, distance=3, max_melee_damage=0), race_id=6011
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110,
            can_summon=False, friendly=False,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        torch = replace(
            item("t", TVAL_LITE, SV_LITE_TORCH, count=5, fuel=5000),
            is_equipment=True,
        )
        spent = replace(
            item("z", TVAL_LITE, SV_LITE_TORCH, count=7, fuel=0),
            is_equipment=True,
        )
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {
                Position(10, x): replace(
                    grid(10, x, monster=x == 13),
                    object_count=1 if x == 12 else 0,
                )
                for x in range(10, 14)
            },
            [monster], inventory=[spent, torch],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6011: knowledge})
        policy._known_loot.add(Position(10, 12))
        snapshot = replace(
            snapshot, grids={position: replace(cell, lit=True)
                             for position, cell in snapshot.grids.items()}
        )

        self.assertEqual(policy._count_throwing_torches(snapshot), 5)
        self.assertEqual(policy.choose_key(snapshot), "vt6")
        self.assertEqual(policy.last_reason, "ranged:throw-torch")
        spent_only = replace(snapshot, inventory=[spent])
        empty_policy = HengbotPolicy(monrace_knowledge={6011: knowledge})
        empty_policy._known_loot.add(Position(10, 12))
        empty_policy._refresh_paralyzer_avoidance(spent_only, [monster])
        self.assertEqual(empty_policy._count_throwing_torches(spent_only), 0)
        self.assertIsNone(empty_policy._ranged_attack_key(spent_only, [monster], []))

    def test_never_move_hurt_mold_guard_does_not_oblige_a_throw(self):
        mold = replace(
            hostile(1, 10, 13, distance=3, max_melee_damage=1), race_id=6025
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110,
            can_summon=False, friendly=False,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("HIT", "HURT", 1, 1),),
        )
        loot = Position(10, 12)
        snapshot = Snapshot(
            player(10, 10),
            {Position(10, x): replace(
                grid(10, x, monster=x == 13), lit=True,
                object_count=int(x == 12),
            ) for x in range(10, 14)},
            [mold],
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6025: knowledge})
        policy._known_loot.add(loot)

        key = policy._normal_loot_key(snapshot, [mold])

        self.assertNotEqual(key, "vt6")
        self.assertNotEqual(policy.last_reason, "ranged:throw-torch")

    def test_capture_two_cycle_breaks_through_loot_ledger(self):
        capture = Path(
            "tests/fixtures/incident-20260821-loop-capture-rows.jsonl.gz"
        )
        self.assertTrue(capture.exists())
        player_position = Position(17, 30)
        loot = Position(30, 17)
        snapshot = Snapshot(
            player(player_position.y, player_position.x),
            {
                player_position: grid(player_position.y, player_position.x),
                loot: replace(grid(loot.y, loot.x), object_count=1),
            },
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        policy._known_loot.add(loot)
        policy._loot_target = loot
        policy._nav_ledger = policy_module.NavigationLedger(stall_limit=2)

        for _ in range(3):
            policy.choose_key(snapshot)

        self.assertTrue(policy._nav_ledger.is_expired("loot", loot))
        self.assertIn(loot, policy._deferred_loot)

    def test_navigation_observes_loot_and_explore_on_silent_owner_half(self):
        snapshot = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        loot = Position(30, 17)
        frontier = Position(18, 32)
        policy._loot_target = loot
        policy._explore_goal_identity = policy_module.ExplorationGoalIdentity(
            policy_module.ExplorationGoalKind.VISIT,
            frontier,
            (-1, False, False, False, 0),
        )

        policy._observe_navigation_commitments(snapshot)

        self.assertIn(("loot", loot), policy._nav_ledger._progress)
        self.assertIn(("explore:VISIT", frontier), policy._nav_ledger._progress)

    def test_paralyzer_approach_expires_through_navigation_ledger(self):
        monster = replace(
            hostile(1, 10, 23, distance=13, max_melee_damage=0), race_id=6021
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110,
            can_summon=False, friendly=False,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        loot = Position(10, 22)
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {
                Position(10, x): replace(
                    grid(10, x, monster=x == 23), lit=True,
                    object_count=int(x == 22),
                )
                for x in range(8, 25)
            },
            [monster],
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6021: knowledge})
        policy._nav_ledger = policy_module.NavigationLedger(stall_limit=2)
        policy._known_loot.add(loot)

        self.assertIsNotNone(policy.choose_key(snapshot))
        self.assertEqual(policy.last_reason, "paralyzer-guard:approach-range")
        policy.choose_key(snapshot)
        policy.choose_key(snapshot)

        self.assertTrue(
            policy._nav_ledger.is_expired("paralyzer-guard", monster.position)
        )
        self.assertIn(loot, policy._deferred_loot)
        self.assertNotEqual(policy.last_reason, "paralyzer-guard:approach-range")

    def test_paralyzer_without_ranged_option_never_approaches_or_enters_ring(self):
        monster = replace(
            hostile(1, 10, 23, distance=13, max_melee_damage=0), race_id=6022
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110,
            can_summon=False, friendly=False,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        loot = Position(10, 22)
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, x): replace(
                grid(10, x, monster=x == 23), object_count=int(x == 22)
             ) for x in range(8, 25)},
            [monster], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6022: knowledge})
        policy._known_loot.add(loot)

        policy.choose_key(snapshot)

        self.assertIn(loot, policy._deferred_loot)
        self.assertNotEqual(policy.last_reason, "paralyzer-guard:approach-range")
        before = (set(policy._deferred_loot), policy._loot_defer_blocker)
        first = policy.loot_state(snapshot)
        second = policy.loot_state(snapshot)
        self.assertEqual(first, second)
        self.assertEqual(
            (set(policy._deferred_loot), policy._loot_defer_blocker), before
        )

    def test_torch_outside_throw_depth_defers_without_approaching(self):
        monster = replace(
            hostile(1, 10, 23, distance=13, max_melee_damage=0), race_id=6024
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110,
            can_summon=False, friendly=False,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        loot = Position(10, 22)
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, x): replace(
                grid(10, x, monster=x == 23), lit=True,
                object_count=int(x == 22),
             ) for x in range(8, 25)},
            [monster],
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
            floor_key=(
                DUNGEON_YEEK_CAVE, policy_module.TORCH_THROW_MAX_DEPTH + 1, 0
            ),
        )
        policy = HengbotPolicy(monrace_knowledge={6024: knowledge})
        policy._known_loot.add(loot)

        policy.choose_key(snapshot)

        self.assertIn(loot, policy._deferred_loot)
        self.assertEqual(policy.loot_state(snapshot)["blocker"], "paralyzer-ring")
        self.assertNotEqual(policy.last_reason, "paralyzer-guard:approach-range")

    def test_loot_ledger_expiry_uses_and_clears_navigation_blocker(self):
        snapshot = Snapshot(
            player(10, 10),
            {Position(10, x): grid(10, x) for x in range(10, 14)},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        # Anchor the floor so the later _observe exercises the blocker-clearing
        # path instead of the fresh-floor reset (which clears everything anyway).
        policy._floor_key = snapshot.floor_key
        target = Position(10, 13)
        policy._known_loot.add(target)
        policy._loot_target = target
        policy._nav_ledger = policy_module.NavigationLedger(stall_limit=1)

        policy._observe_navigation_commitments(snapshot)
        policy._observe_navigation_commitments(snapshot)

        self.assertIn(target, policy._deferred_loot)
        blocker = policy.loot_state(snapshot)["blocker"]
        self.assertEqual(blocker, "navigation-ledger:loot")
        self.assertNotEqual(blocker, "paralyzer-ring")

        observed_gone = replace(
            snapshot,
            player=replace(snapshot.player, position=Position(10, 12)),
            grids={
                **snapshot.grids,
                target: replace(
                    snapshot.grids[target], in_view=True, currently_observed=True,
                    object_count=0,
                ),
            },
        )
        policy._observe(observed_gone)

        self.assertNotIn(target, policy._deferred_loot)
        self.assertIsNone(policy.loot_state(observed_gone)["blocker"])

    def test_moving_paralyzer_memory_holds_unseen_then_releases_observed_loot(self):
        monster = replace(
            hostile(1, 10, 13, distance=3, max_melee_damage=0), race_id=6023
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110,
            can_summon=False, friendly=False,
            blows=(MonsterBlow("TOUCH", "PARALYZE"),),
        )
        loot = Position(10, 12)
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, x): replace(
                grid(10, x, monster=x == 13), object_count=int(x == 12)
             ) for x in range(8, 15)},
            [monster], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6023: knowledge})
        policy._known_loot.add(loot)
        policy.choose_key(snapshot)
        policy._deferred_loot.add(loot)
        policy._loot_defer_blocker = "paralyzer-ring"

        unseen = replace(
            snapshot, visible_monsters=[],
            grids={position: replace(
                cell, has_monster=False, monster_index=0,
                in_view=False, currently_observed=False,
            ) if position == monster.position else cell
                   for position, cell in snapshot.grids.items()},
        )
        policy.choose_key(unseen)
        self.assertIn(monster.position, policy._remembered_paralyzers)
        self.assertIn(loot, policy._deferred_loot)

        observed = replace(
            unseen,
            grids={position: replace(
                cell, in_view=True, currently_observed=True, lit=True
            ) if position == monster.position else cell
                   for position, cell in unseen.grids.items()},
        )
        policy._refresh_paralyzer_avoidance(observed, [])
        self.assertNotIn(monster.position, policy._remembered_paralyzers)
        self.assertNotIn(loot, policy._deferred_loot)

    def test_unlit_in_view_empty_cell_does_not_retire_remembered_paralyzer(self):
        position = Position(10, 13)
        snapshot = Snapshot(
            player(10, 10),
            {position: replace(
                grid(10, 13), has_monster=False, monster_index=0,
                in_view=True, currently_observed=True, lit=False,
            )},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        policy._remembered_paralyzers[position] = True

        policy._refresh_paralyzer_avoidance(snapshot, [])
        self.assertIn(position, policy._remembered_paralyzers)

        lit = replace(
            snapshot,
            grids={position: replace(snapshot.grids[position], lit=True)},
        )
        policy._refresh_paralyzer_avoidance(lit, [])
        self.assertNotIn(position, policy._remembered_paralyzers)

    def test_stationary_paralyzer_without_ranged_option_defers_guarded_loot(self):
        monster = replace(
            hostile(1, 10, 13, distance=3, max_melee_damage=0), race_id=6012
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110,
            can_summon=False, friendly=False,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        loot = Position(10, 12)
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {
                Position(10, x): replace(grid(10, x), object_count=int(x == 12))
                for x in range(10, 14)
            },
            [monster], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6012: knowledge})
        policy._known_loot.add(loot)
        policy._refresh_paralyzer_avoidance(snapshot, [monster])

        self.assertIsNone(policy._normal_loot_key(snapshot, [monster]))
        self.assertIn(loot, policy._deferred_loot)
        self.assertEqual(policy.loot_state(snapshot)["blocker"], "paralyzer-ring")
        armed = replace(
            snapshot,
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        self.assertEqual(policy._normal_loot_key(armed, [monster]), "vt6")

    def test_distant_sleeping_immobile_paralyzer_does_not_preempt_hunt(self):
        monster = replace(
            hostile(1, 10, 15, distance=5, max_melee_damage=0),
            race_id=6011,
            asleep=True,
        )
        knowledge = MonraceKnowledge(
            max_hp=20,
            average_hp=20,
            speed=110,
            can_summon=False,
            friendly=False,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        snapshot = self._line_snapshot(monster, hp=100)
        policy = HengbotPolicy(monrace_knowledge={6011: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "explore")

        protected = replace(
            snapshot,
            player=replace(
                snapshot.player,
                abilities=frozenset({"free_action"}),
                ability_sources=AbilitySources(
                    {"free_action": frozenset({"equipment"})}
                ),
            ),
            inventory=[],
            equipment=[],
        )
        protected_policy = HengbotPolicy(monrace_knowledge={6011: knowledge})
        self.assertEqual(protected_policy.choose_key(protected), "6")
        self.assertEqual(protected_policy.last_reason, "hunt")

    def test_paralyzer_ring_invalidates_cached_explore_path_through_choose_key(self):
        monster = replace(
            hostile(1, 10, 15, distance=5, max_melee_damage=0),
            race_id=6014, asleep=True,
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        orc = hostile(2, 10, 11, distance=1, max_melee_damage=1)
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, x): grid(10, x, monster=x in {11, 15})
             for x in range(8, 17)},
            [orc, monster], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6014: knowledge})
        policy._observe(snapshot)
        policy._explore_path = [Position(10, 14)]
        policy.choose_key(snapshot)

        self.assertEqual(policy._explore_path, [])

    def test_awake_mobile_adjacent_paralyzer_walks_away_first(self):
        monster = replace(
            hostile(1, 10, 11, distance=1, max_melee_damage=0), race_id=6012
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, blows=(MonsterBlow("TOUCH", "PARALYZE"),),
        )
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(y, x): grid(y, x, monster=(y, x) == (10, 11))
             for y in range(8, 13) for x in range(8, 13)},
            [monster], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6012: knowledge})

        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "threat:paralyzer-avoid")
        self.assertEqual(key, "7")

    def test_sleeping_immobile_adjacent_paralyzer_is_never_meleed(self):
        monster = replace(
            hostile(1, 10, 11, distance=1, max_melee_damage=0),
            race_id=6015,
            asleep=True,
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(y, x): grid(y, x, monster=(y, x) == (10, 11))
             for y in range(8, 13) for x in range(8, 13)},
            [monster], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6015: knowledge})

        key = policy.choose_key(snapshot)

        self.assertNotEqual(key, "6")
        self.assertEqual(policy.last_reason, "threat:paralyzer-avoid")

    def test_step_composer_refuses_every_owner_entry_into_paralyzer_ring(self):
        monster = replace(
            hostile(1, 10, 12, distance=2, max_melee_damage=0), race_id=6016
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        snapshot = Snapshot(
            player(10, 10),
            {Position(10, x): grid(10, x, monster=x == 12)
             for x in range(8, 14)},
            [monster], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6016: knowledge})
        policy._observe(snapshot)
        policy._build_grid_index(snapshot)
        policy._refresh_paralyzer_avoidance(snapshot, [monster])

        self.assertEqual(policy._step_toward(snapshot, Position(10, 11)), WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "threat:paralyzer-avoid:blocked-step"
        )

    def test_adjacent_paralyzer_flee_uses_composer_to_open_closed_door(self):
        monster = replace(
            hostile(1, 10, 11, distance=1, max_melee_damage=0), race_id=6017
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, blows=(MonsterBlow("TOUCH", "PARALYZE"),),
        )
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, monster=True),
            Position(10, 9): grid(10, 9, closed_door=True),
        }
        snapshot = Snapshot(
            player(10, 10), grids, [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6017: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "o4")
        self.assertEqual(policy.last_reason, "threat:paralyzer-avoid")

    def test_paralyzer_flee_scores_against_every_physical_adjacent(self):
        paralyzer = replace(
            hostile(1, 10, 11, distance=1, max_melee_damage=0), race_id=6018
        )
        orc = hostile(2, 9, 10, distance=1, max_melee_damage=1)
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, blows=(MonsterBlow("TOUCH", "PARALYZE"),),
        )
        snapshot = Snapshot(
            player(10, 10),
            {Position(y, x): grid(
                y, x, monster=(y, x) in {(10, 11), (9, 10)}
            ) for y in range(9, 12) for x in range(9, 12)},
            [paralyzer, orc], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6018: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "1")
        self.assertEqual(policy.last_reason, "threat:paralyzer-avoid")

    def test_only_paralyzer_retreat_may_cross_a_fully_ringed_veto(self):
        snapshot = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 9): grid(10, 9),
            },
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        policy._observe(snapshot)
        policy._build_grid_index(snapshot)
        policy._paralyzer_avoid_cells = {Position(10, 9)}

        self.assertEqual(
            policy._step_toward(snapshot, Position(10, 9)), WAIT_KEY
        )
        self.assertEqual(
            policy._step_toward(
                snapshot,
                Position(10, 9),
                allow_paralyzer_ring_escape=True,
            ),
            "4",
        )

    def test_adjacent_orc_fight_is_not_abandoned_for_distant_paralyzer(self):
        orc = hostile(1, 10, 11, distance=1, max_melee_damage=1)
        eye = replace(
            hostile(2, 10, 14, distance=4, max_melee_damage=0), race_id=6013
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, blows=(MonsterBlow("GAZE", "PARALYZE"),),
        )
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, x): grid(10, x, monster=x in {11, 14})
             for x in range(8, 16)},
            [orc, eye], floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6013: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_suppressed_weak_breeder_paralysis_remains_a_status_threat(self):
        monster = replace(
            hostile(
                1, 10, 11, distance=1, max_melee_damage=1,
                can_multiply=True,
            ),
            race_id=6004,
        )
        knowledge = MonraceKnowledge(
            max_hp=20,
            average_hp=20,
            speed=110,
            can_summon=False,
            friendly=False,
            level=10,
            max_melee_damage=1,
            blows=(MonsterBlow("TOUCH", "PARALYZE", 1, 1),),
        )
        snapshot = self._line_snapshot(
            monster,
            hp=100,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        policy = HengbotPolicy(monrace_knowledge={6004: knowledge})
        policy._breeder_breakthrough_floor = snapshot.floor_key

        self.assertEqual(policy._strategic_hostiles(snapshot), [])
        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "status-threat:scroll")

    def test_status_threat_retreat_vetoes_immediate_explore_return(self):
        monster = replace(
            hostile(1, 9, 10, distance=1, max_melee_damage=0),
            race_id=6003,
        )
        knowledge = MonraceKnowledge(
            max_hp=20,
            average_hp=20,
            speed=110,
            can_summon=False,
            friendly=False,
            level=10,
            max_melee_damage=0,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE", 0, 0),),
        )
        grids = {
            Position(y, x): grid(y, x, monster=(y == 9 and x == 10))
            for y in range(8, 13)
            for x in range(8, 13)
        }
        danger = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            grids,
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={6003: knowledge})
        policy._explore_path = [Position(10, 10), Position(9, 10)]

        policy.choose_key(danger)

        self.assertEqual(policy.last_reason, "status-threat:retreat")
        self.assertIn(Position(10, 10), policy._engagement_avoid_cells)
        self.assertEqual(policy._explore_path, [])

        retreated = replace(
            danger,
            player=player(11, 10, hp=100, max_hp=100),
            visible_monsters=[replace(monster, distance=2)],
        )
        policy._explore_path = [Position(10, 10), Position(9, 10)]
        policy._build_grid_index(retreated)
        self.assertNotEqual(
            policy._explore_step(retreated), Position(10, 10)
        )

    def test_status_threat_retreat_vetoes_loot_across_full_melee_ring(self):
        monster = replace(
            hostile(1, 5, 47, distance=1, max_melee_damage=0),
            race_id=6004,
        )
        knowledge = MonraceKnowledge(
            max_hp=20,
            average_hp=20,
            speed=110,
            can_summon=False,
            friendly=False,
            level=10,
            max_melee_damage=0,
            flags=frozenset({"NEVER_MOVE"}),
            blows=(MonsterBlow("GAZE", "PARALYZE", 0, 0),),
        )
        grids = {
            Position(y, x): grid(
                y,
                x,
                monster=(y == 5 and x == 47),
                objects=1 if (y, x) in {(5, 48), (8, 50)} else 0,
                unsafe=(y, x) == (5, 48),
            )
            for y in range(4, 10)
            for x in range(44, 52)
        }
        danger = Snapshot(
            player(6, 47, hp=197, max_hp=197, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
                item("d", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL),
            ],
            equipment=[
                item(
                    "main_hand",
                    TVAL_DIGGING,
                    SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                ),
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={6004: knowledge})
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = danger.floor_key

        self.assertEqual(policy.choose_key(danger), "1")
        self.assertEqual(policy.last_reason, "status-threat:retreat")
        self.assertIn(Position(5, 48), policy._engagement_avoid_cells)

        retreated = replace(
            danger,
            player=replace(danger.player, position=Position(7, 46)),
            visible_monsters=[replace(monster, distance=2)],
        )
        policy.choose_key(retreated)

        self.assertEqual(policy.last_reason, "fundraise:seek-loot")
        self.assertEqual(policy._loot_target, Position(8, 50))

        # The phase-1 mining sweep uses _nearest_goal_and_step rather than the
        # ordinary exploration planner. It must share the same persistent veto,
        # or it walks from the retreat cell straight back into the eye's ring.
        result = policy._nearest_goal_and_step(
            retreated,
            lambda candidate: candidate.position
            in {Position(6, 46), Position(7, 48)},
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], Position(7, 48))
        self.assertNotIn(result[1], policy._engagement_avoid_cells)

    def test_healing_potion_is_status_cure_when_cure_critical_is_exhausted(self):
        monster = hostile(1, 10, 11, distance=1, max_melee_damage=50)
        snap = self._line_snapshot(
            monster,
            hp=30,
            inventory=[item("h", TVAL_POTION, SV_POTION_HEALING)],
        )
        snap = replace(snap, player=replace(snap.player, confused=True))
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "qh")
        self.assertEqual(policy.last_reason, "emergency:cure-status-healing")

    def test_threat_prediction_records_per_monster_damage_breakdown(self):
        monster = replace(
            hostile(
                1,
                10,
                12,
                distance=2,
                max_melee_damage=20,
                max_ranged_damage=11,
            ),
            name="test orc",
            race_id=123,
        )
        snap = self._line_snapshot(monster)

        prediction = HengbotPolicy().threat_prediction(snap, [monster], turns=3)

        self.assertEqual(prediction["total"], 60)
        detail = prediction["monsters"][0]
        self.assertEqual(detail["name"], "test orc")
        self.assertEqual(detail["race_id"], 123)
        self.assertEqual(detail["actions"], 4)
        self.assertEqual(detail["path_distance"], 2)
        self.assertEqual(detail["melee_prediction"], 60)
        self.assertEqual(detail["ranged_prediction"], 44)
        self.assertEqual(detail["contribution"], 60)

    def test_monster_actions_caps_short_window_without_changing_long_window(self):
        policy = HengbotPolicy()

        self.assertEqual(policy._monster_actions(115, 110, 1), 2)
        self.assertEqual(policy._monster_actions(115, 110, 18), 28)
        # At exactly double speed, two steady actions plus one boundary-phase
        # action are physically possible in a single player turn.
        self.assertEqual(policy._monster_actions(120, 110, 1), 3)
        self.assertEqual(policy._monster_actions(110, 110, 1), 2)
        self.assertEqual(policy._monster_actions(100, 110, 1), 1)

    def test_incident_threat_uses_two_actions_and_384_operational_damage(self):
        monster = replace(
            hostile(
                1,
                10,
                11,
                distance=1,
                speed=115,
                max_melee_damage=120,
                race_id=1124,
            ),
            name="Killing angel",
        )
        knowledge = MonraceKnowledge(
            max_hp=1000,
            average_hp=1000,
            speed=115,
            can_summon=False,
            friendly=False,
            level=40,
            max_melee_damage=120,
            blows=tuple(
                MonsterBlow("HIT", "SUPERHURT", 15, 2) for _ in range(4)
            ),
        )
        snap = self._line_snapshot(monster, hp=50)
        snap = replace(snap, player=replace(snap.player, ac=50))

        prediction = HengbotPolicy(
            monrace_knowledge={1124: knowledge}
        ).threat_prediction(snap, [monster], turns=1)

        self.assertEqual(prediction["monsters"][0]["actions"], 2)
        self.assertEqual(prediction["operational_total"], 384)

    def test_corrected_incident_threat_no_longer_outpaces_healing_potion(self):
        monster = replace(
            hostile(
                1,
                10,
                11,
                distance=1,
                speed=115,
                max_melee_damage=120,
                race_id=1124,
            ),
            name="Killing angel",
        )
        knowledge = MonraceKnowledge(
            max_hp=1000,
            average_hp=1000,
            speed=115,
            can_summon=False,
            friendly=False,
            level=40,
            max_melee_damage=120,
            blows=tuple(
                MonsterBlow("HIT", "SUPERHURT", 15, 2) for _ in range(4)
            ),
        )
        healing = item("h", TVAL_POTION, SV_POTION_HEALING)
        snap = self._line_snapshot(monster, hp=100, inventory=[healing])
        snap = replace(
            snap,
            player=replace(snap.player, hp=100, max_hp=500, ac=50),
        )
        policy = HengbotPolicy(monrace_knowledge={1124: knowledge})

        expected = policy._predicted_damage(
            snap, [monster], turns=1, expected=True
        )

        self.assertEqual(expected, 294)
        self.assertIs(
            policy._find_heal_potion(snap, expected_damage=expected), healing
        )

    def test_never_move_enemy_cannot_spend_actions_approaching_for_melee(self):
        monster = replace(
            hostile(
                1,
                10,
                12,
                distance=2,
                max_melee_damage=20,
                max_ranged_damage=11,
            ),
            race_id=329,
        )
        knowledge = MonraceKnowledge(
            275,
            110,
            False,
            False,
            max_melee_damage=20,
            max_ranged_damage=11,
            flags=frozenset({"NEVER_MOVE"}),
        )
        snap = self._line_snapshot(monster)

        prediction = HengbotPolicy(
            monrace_knowledge={329: knowledge}
        ).threat_prediction(snap, [monster], turns=3)

        detail = prediction["monsters"][0]
        self.assertTrue(detail["never_moves"])
        self.assertEqual(detail["path_distance"], 2)
        self.assertEqual(detail["melee_prediction"], 0)
        self.assertEqual(detail["expected_melee_prediction"], 0)
        self.assertEqual(detail["ranged_prediction"], 44)
        self.assertEqual(prediction["total"], 44)

    def test_never_move_enemy_still_deals_melee_damage_when_adjacent(self):
        monster = replace(
            hostile(1, 10, 11, distance=1, max_melee_damage=20),
            race_id=329,
        )
        knowledge = MonraceKnowledge(
            275,
            110,
            False,
            False,
            max_melee_damage=20,
            flags=frozenset({"NEVER_MOVE"}),
        )
        snap = self._line_snapshot(monster)

        prediction = HengbotPolicy(
            monrace_knowledge={329: knowledge}
        ).threat_prediction(snap, [monster], turns=3)

        detail = prediction["monsters"][0]
        self.assertTrue(detail["never_moves"])
        self.assertEqual(detail["actions"], 4)
        self.assertEqual(detail["melee_prediction"], 80)
        self.assertEqual(prediction["total"], 80)

    def test_never_move_tele_to_enemy_can_pull_then_melee(self):
        monster = replace(
            hostile(1, 10, 15, distance=5, max_melee_damage=20),
            race_id=329,
        )
        knowledge = MonraceKnowledge(
            275,
            110,
            False,
            False,
            max_melee_damage=20,
            flags=frozenset({"NEVER_MOVE"}),
            abilities=frozenset({"TELE_TO"}),
            spell_frequency=16,
        )
        snap = self._line_snapshot(monster)

        prediction = HengbotPolicy(
            monrace_knowledge={329: knowledge}
        ).threat_prediction(snap, [monster], turns=3)

        detail = prediction["monsters"][0]
        self.assertTrue(detail["never_moves"])
        self.assertTrue(detail["can_teleport_player_to"])
        self.assertEqual(detail["actions"], 4)
        self.assertEqual(detail["melee_prediction"], 60)
        self.assertGreater(detail["expected_melee_prediction"], 0)
        self.assertLess(detail["expected_melee_prediction"], 60)
        self.assertEqual(prediction["total"], 60)

    def test_exploding_monster_contributes_at_most_one_melee_attack(self):
        monster = replace(
            hostile(
                1,
                10,
                11,
                distance=1,
                speed=120,
                max_melee_damage=64,
            ),
            name="Bouncing fire ball",
            race_id=299,
        )
        knowledge = MonraceKnowledge(
            max_hp=20,
            average_hp=20,
            speed=120,
            can_summon=False,
            friendly=False,
            level=20,
            max_melee_damage=64,
            blows=(MonsterBlow("EXPLODE", "FIRE", 8, 8),),
        )
        snap = self._line_snapshot(monster, hp=100)

        prediction = HengbotPolicy(
            monrace_knowledge={299: knowledge}
        ).threat_prediction(snap, [monster], turns=3)

        detail = prediction["monsters"][0]
        self.assertGreater(detail["actions"], 1)
        self.assertTrue(detail["self_destructs_on_melee"])
        self.assertEqual(detail["melee_prediction"], 64)
        self.assertLessEqual(detail["expected_melee_prediction"], 64)
        self.assertEqual(prediction["total"], 64)

    def test_threat_prediction_applies_ac_poison_resistance_and_hit_rate(self):
        monster = replace(
            hostile(
                1,
                10,
                11,
                distance=1,
                max_melee_damage=8,
                max_ranged_damage=98,
            ),
            name="Master yeek",
            race_id=224,
        )
        snap = self._line_snapshot(monster)
        snap = replace(
            snap,
            player=replace(
                snap.player,
                ac=100,
                abilities=frozenset({"resist_pois"}),
            ),
        )
        knowledge = MonraceKnowledge(
            max_hp=48,
            average_hp=30,
            speed=110,
            can_summon=False,
            friendly=False,
            level=12,
            max_melee_damage=8,
            max_ranged_damage=98,
            abilities=frozenset(
                {"BA_POIS", "BLINK", "CONF", "SLOW", "S_MONSTER"}
            ),
            blows=(MonsterBlow("HIT", "HURT", 1, 8),),
            spell_frequency=25,
        )

        prediction = HengbotPolicy(
            monrace_knowledge={224: knowledge}
        ).threat_prediction(snap, [monster], turns=3)

        detail = prediction["monsters"][0]
        self.assertEqual(detail["actions"], 4)
        self.assertEqual(detail["melee_prediction"], 20)
        self.assertEqual(detail["ranged_prediction"], 32)
        self.assertEqual(prediction["total"], 32)
        self.assertLess(prediction["expected_total"], prediction["total"])
        self.assertLess(detail["expected_melee_prediction"], 5)

    def test_threat_prediction_excludes_hunger_dice_from_hp_damage(self):
        monster = replace(
            hostile(
                1,
                10,
                11,
                distance=1,
                max_melee_damage=516,
            ),
            name="Polygon Spin",
            race_id=1386,
        )
        snap = self._line_snapshot(monster)
        knowledge = MonraceKnowledge(
            max_hp=264,
            average_hp=149,
            speed=110,
            can_summon=False,
            friendly=False,
            level=15,
            max_melee_damage=16,
            blows=(
                MonsterBlow("HIT", "HURT", 4, 4),
                MonsterBlow("SHOW", "HUNGRY", 500, 1),
            ),
        )

        prediction = HengbotPolicy(
            monrace_knowledge={1386: knowledge}
        ).threat_prediction(snap, [monster], turns=3)

        detail = prediction["monsters"][0]
        self.assertEqual(detail["actions"], 4)
        self.assertEqual(detail["melee_prediction"], 64)
        self.assertEqual(detail["operational_contribution"], 64)
        self.assertLessEqual(detail["expected_contribution"], 64)

    def test_cause_spell_participates_in_aggregate_operational_danger(self):
        monster = replace(
            hostile(
                1,
                10,
                12,
                distance=2,
                speed=115,
                max_melee_damage=19,
                max_ranged_damage=64,
            ),
            name="dark elven priest",
            race_id=226,
        )
        snap = self._line_snapshot(monster, hp=100)
        snap = replace(
            snap,
            player=replace(snap.player, ac=30, saving_skill=52),
        )
        knowledge = MonraceKnowledge(
            max_hp=70,
            average_hp=38,
            speed=115,
            can_summon=False,
            friendly=False,
            level=12,
            max_melee_damage=19,
            max_ranged_damage=64,
            abilities=frozenset(
                {"DARKNESS", "BLIND", "CAUSE_2", "MISSILE", "HEAL", "CONF"}
            ),
            blows=(
                MonsterBlow("HIT", "HURT", 1, 9),
                MonsterBlow("HIT", "HURT", 1, 10),
            ),
            spell_frequency=20,
        )
        policy = HengbotPolicy(monrace_knowledge={226: knowledge})

        prediction = policy.threat_prediction(snap, [monster], turns=3)

        detail = prediction["monsters"][0]
        self.assertEqual(prediction["total"], 384)
        self.assertEqual(prediction["operational_total"], 85)
        self.assertEqual(detail["melee_prediction"], 85)
        self.assertLess(detail["operational_ranged_prediction"], 85)
        self.assertGreater(
            detail["operational_ranged_probability_any_damage"], 0.0
        )
        self.assertFalse(detail["operational_ranged_floor_applied"])
        self.assertEqual(detail["cause_predictions"][0]["damage_p95"], 47)
        self.assertEqual(policy._predicted_damage(snap, [monster], 3), 85)

    def test_wall_blocks_melee_reach_and_ranged_line_of_fire(self):
        monster = hostile(
            1, 10, 12, distance=2, max_melee_damage=50, max_ranged_damage=50
        )
        snap = self._line_snapshot(monster)
        snap.grids[Position(10, 11)] = grid(10, 11, passable=False)
        pol = HengbotPolicy()
        self.assertEqual(pol._predicted_damage(snap, [monster], 3), 0)

    def test_ranged_damage_triggers_escape(self):
        monster = hostile(1, 10, 13, distance=3, max_ranged_damage=11)
        snap = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        self.assertEqual(HengbotPolicy().choose_key(snap), "rt")

    def test_upstairs_is_preferred_to_the_last_teleport_scroll(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        snap = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=1)],
            upstairs=True,
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "<")
        self.assertEqual(pol.last_reason, "emergency:stairs")

    def test_phase_door_is_the_fallback_when_full_teleport_is_missing(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        snap = self._line_snapshot(
            monster, inventory=[item("p", TVAL_SCROLL, 8)]
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rp")
        self.assertEqual(pol.last_reason, "emergency:phase")

    def test_cures_blindness_then_retains_the_escape_decision(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        potion = item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL)
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)
        pol = HengbotPolicy()
        first = self._line_snapshot(monster, inventory=[potion, teleport])
        first = Snapshot(
            player(10, 10, hp=30, max_hp=100, blind=True),
            first.grids,
            first.visible_monsters,
            floor_key=first.floor_key,
            inventory=first.inventory,
        )
        self.assertEqual(pol.choose_key(first), "qc")
        second = self._line_snapshot(monster, inventory=[teleport])
        self.assertEqual(pol.choose_key(second), "rt")

    def test_cure_critical_is_not_spent_as_low_hp_healing(self):
        monster = hostile(1, 10, 11)
        snap = self._line_snapshot(
            monster,
            hp=10,
            inventory=[item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL)],
        )
        pol = HengbotPolicy()
        self.assertNotEqual(pol.choose_key(snap), "qc")

    def test_low_hp_teleport_landing_starts_recall(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        pol = HengbotPolicy()
        first = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        self.assertEqual(pol.choose_key(first), "rt")
        safe = Snapshot(
            player(20, 20, hp=30, max_hp=100),
            {Position(20, 20): grid(20, 20)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        self.assertNotEqual(pol.choose_key(safe), "rr")
        self.assertTrue(pol._returning_to_town)

    def test_healthy_first_teleport_landing_continues_dive(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        pol = HengbotPolicy()
        first = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
        )
        self.assertEqual(pol.choose_key(first), "rt")
        safe = Snapshot(
            player(20, 20, hp=90, max_hp=100),
            {Position(20, 20): grid(20, 20)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
            ],
        )
        self.assertNotEqual(pol.choose_key(safe), "rr")
        self.assertFalse(pol._returning_to_town)
        self.assertIsNone(pol._last_return_trigger)

    def test_second_emergency_escape_starts_return(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        pol = HengbotPolicy()
        first = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3)],
        )
        self.assertEqual(pol.choose_key(first), "rt")
        safe = Snapshot(
            player(20, 20, hp=90, max_hp=100),
            {Position(20, 20): grid(20, 20)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
        )
        pol.choose_key(safe)
        second = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
        )
        self.assertEqual(pol.choose_key(second), "rt")
        self.assertTrue(pol._returning_to_town)

    def test_weak_breeder_after_teleport_does_not_start_return(self):
        monster = hostile(1, 10, 11, max_melee_damage=20)
        pol = HengbotPolicy()
        first = self._line_snapshot(
            monster,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
        )
        self.assertEqual(pol.choose_key(first), "rt")
        multiplier = hostile(2, 20, 22, max_melee_damage=1, can_multiply=True)
        landing = Snapshot(
            player(20, 20, hp=90, max_hp=100),
            {
                Position(20, 20): grid(20, 20),
                Position(20, 21): grid(20, 21),
                Position(20, 22): grid(20, 22, monster=True),
            },
            [multiplier],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
            ],
        )
        pol._breeder_breakthrough_floor = landing.floor_key
        self.assertNotEqual(pol.choose_key(landing), "rr")
        self.assertIsNone(pol._last_return_trigger)
class EmergencyRecallEscapeTest(unittest.TestCase):
    def _swarm(self, inventory):
        grids = {}
        for y in range(9, 12):
            for x in range(43, 46):
                grids[Position(y, x)] = grid(y, x, monster=not (y == 10 and x == 44))
        adj = [(9, 43), (9, 44), (9, 45), (10, 43), (10, 45), (11, 43), (11, 44), (11, 45)]
        hostiles = [
            MonsterState(
                index=i, position=Position(y, x), hp=200, max_hp=200, distance=1,
                friendly=False, pet=False, speed=120, max_melee_damage=40,
            )
            for i, (y, x) in enumerate(adj, 1)
        ]
        return Snapshot(
            player(10, 44, hp=134, max_hp=255, class_id=PLAYER_CLASS_WARRIOR),
            grids, hostiles, floor_key=(2, 11, 0), width=100, height=100,
            inventory=inventory,
        )

    def test_recalls_when_teleport_scrolls_are_exhausted(self):
        # The dl11 swarm death: teleport/phase gone, seek-upstairs/wait had no
        # exit. Now it reads Word of Recall to start the escape home instead.
        snap = self._swarm([item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5)])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rr")
        self.assertEqual(pol.last_reason, "emergency:recall")

    def test_prefers_teleport_over_recall_when_a_teleport_is_available(self):
        snap = self._swarm([
            item("t", TVAL_SCROLL, 9, count=3),  # teleport
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
        ])
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")

    def test_stale_emergency_snapshot_does_not_spend_a_second_scroll(self):
        # Live 2026-07-23 regression: the CLI reconsidered the exact summoner
        # board after its two-second duplicate interval and emitted ``rd``
        # twice.  One hazard consumed two teleports and was counted as two
        # emergencies before the post-teleport return recall began.
        snap = self._swarm([
            item("t", TVAL_SCROLL, 9, count=3),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
        ])
        pol = HengbotPolicy()

        self.assertEqual(pol._emergency_item(snap, snap.visible_monsters), "rt")
        self.assertEqual(pol._emergency_item(snap, snap.visible_monsters), WAIT_KEY)
        self.assertEqual(
            pol.last_reason, "emergency:await-consumable-confirmation"
        )

        relocated = replace(
            snap,
            turn=snap.turn + 10,
            player=replace(snap.player, position=Position(20, 20)),
            inventory=[
                replace(snap.inventory[0], count=2),
                snap.inventory[1],
            ],
        )
        self.assertIsNone(pol._emergency_item(relocated, []))
        self.assertIsNone(pol._emergency_consumable_issue_watch)

    def test_rejected_emergency_scroll_retries_after_turn_advances_unconsumed(self):
        snap = self._swarm([
            item("t", TVAL_SCROLL, 9, count=3),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
        ])
        pol = HengbotPolicy()

        self.assertEqual(pol._emergency_item(snap, snap.visible_monsters), "rt")
        rejected = replace(snap, turn=snap.turn + 1)
        self.assertEqual(
            pol._emergency_item(rejected, rejected.visible_monsters), "rt"
        )
        self.assertEqual(pol.last_reason, "emergency:teleport")

    def test_damaged_confirmation_watch_reenters_emergency_ladder_sequence(self):
        """The frozen turn-4709556 shape cannot absorb consecutive damage."""
        snap = replace(
            self._swarm([
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=8),
            ]),
            turn=4709556,
            player=replace(
                self._swarm([]).player, hp=610, max_hp=668,
            ),
        )
        pol = HengbotPolicy()

        self.assertEqual(pol.choose_key(snap), "rt")
        same_board = replace(snap, inventory=[replace(snap.inventory[0], count=2), snap.inventory[1]])
        self.assertEqual(pol.choose_key(same_board), WAIT_KEY)
        damaged = replace(
            same_board,
            turn=4709567,
            player=replace(same_board.player, hp=459),
        )
        self.assertEqual(pol.choose_key(damaged), "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")

    def test_frozen_cl30_confirmation_damage_replay_reuses_teleport(self):
        self.skipTest(
            "source artifact destroyed 2026-08-17; rebuild from a future capture"
        )
        artifact = Path("evidence/evidence-death-20260813-1130.jsonl")
        records = {
            row["decision_sequence"]: row
            for row in map(json.loads, artifact.read_text(encoding="utf-8").splitlines())
            if row.get("decision_sequence") in {2116, 2118}
        }
        self.assertEqual(
            [(seq, records[seq]["player"]["hp"]) for seq in (2116, 2118)],
            [(2116, 610), (2118, 459)],
        )
        original = self._swarm([
                item("c", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3),
                item("h", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=8),
            ])
        offset_y, offset_x = 20, 93
        translated_grids = {
            Position(position.y + offset_y, position.x + offset_x): replace(
                cell,
                position=Position(
                    cell.position.y + offset_y, cell.position.x + offset_x
                ),
            )
            for position, cell in original.grids.items()
        }
        translated_hostiles = [
            replace(
                monster,
                position=Position(
                    monster.position.y + offset_y,
                    monster.position.x + offset_x,
                ),
            )
            for monster in original.visible_monsters
        ]
        snap = replace(
            original,
            turn=records[2116]["turn"],
            player=replace(
                original.player,
                position=Position(30, 137), hp=610, max_hp=668,
            ),
            grids=translated_grids,
            visible_monsters=translated_hostiles,
        )
        pol = HengbotPolicy()

        self.assertEqual(pol.choose_key(snap), "rc")
        consumed = replace(
            snap, inventory=[replace(snap.inventory[0], count=2), snap.inventory[1]]
        )
        self.assertEqual(pol.choose_key(consumed), WAIT_KEY)
        damaged = replace(
            consumed,
            turn=records[2118]["turn"],
            player=replace(consumed.player, hp=459, hallucinated=True),
        )
        self.assertEqual(pol.choose_key(damaged), "rc")
        self.assertEqual(pol.last_reason, "emergency:teleport")

    def test_blind_damaged_confirmation_watch_quaffs_instead_of_reading(self):
        snap = replace(
            self._swarm([
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=8),
            ]),
            turn=4709556,
            player=replace(
                self._swarm([]).player, hp=610, max_hp=668,
            ),
        )
        pol = HengbotPolicy()

        self.assertEqual(pol.choose_key(snap), "rt")
        same_board = replace(snap, inventory=[replace(snap.inventory[0], count=2), snap.inventory[1]])
        self.assertEqual(pol.choose_key(same_board), WAIT_KEY)
        damaged_blind = replace(
            same_board,
            turn=4709585,
            player=replace(same_board.player, hp=401, blind=True),
        )
        self.assertEqual(pol.choose_key(damaged_blind), "qc")
        self.assertEqual(pol.last_reason, "emergency:cure-critical")

    def test_confirmation_arriving_on_next_observation_preserves_exact_wait(self):
        snap = self._swarm([
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5),
        ])
        pol = HengbotPolicy()

        self.assertEqual(pol._emergency_item(snap, snap.visible_monsters), "rt")
        self.assertFalse(pol._owner_may_select(snap, "emergency:teleport"))
        self.assertEqual(pol._emergency_item(snap, snap.visible_monsters), "5")
        arrived = replace(
            snap,
            turn=snap.turn + 1,
            player=replace(snap.player, position=Position(20, 20)),
            inventory=[replace(snap.inventory[0], count=2), snap.inventory[1]],
        )
        self.assertIsNone(pol._emergency_item(arrived, []))
        self.assertIsNone(pol._emergency_consumable_issue_watch)

    def test_unobserved_consumed_scroll_confirmation_is_bounded(self):
        snap = replace(
            self._swarm([
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=8),
            ]),
            turn=500,
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rt")
        consumed = replace(snap, inventory=[replace(snap.inventory[0], count=2), snap.inventory[1]])
        # The confirmation owner begins on the first waiting decision, so ten
        # complete decision intervals remain suppressed before it expires.
        for delta in range(10):
            waiting = replace(consumed, turn=snap.turn + delta)
            self.assertEqual(pol.choose_key(waiting), WAIT_KEY)
            self.assertEqual(pol.last_reason, "emergency:await-consumable-confirmation")
        expired = replace(consumed, turn=snap.turn + RECALL_ISSUE_CONFIRM_TURNS)
        self.assertEqual(pol.choose_key(expired), "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")

    def test_cornered_without_any_escape_attacks_instead_of_waiting(self):
        # Live Yeek 1F fundraising death: after relocation and recall supplies
        # were exhausted, a blocked route to the stairs emitted wait on six
        # consecutive turns while adjacent monsters killed the character.
        snap = self._swarm([])
        pol = HengbotPolicy()
        pol._emergency_escape_pending = True

        self.assertEqual(pol._emergency_item(snap, snap.visible_monsters), "7")
        self.assertEqual(pol.last_reason, "emergency:cornered-attack")

    def test_oscillating_emergency_walk_posts_reachable_stair_step(self):
        # Measured death shape: a breeder swarm confines the character to two
        # cells, but the first reachable up-stairs step is one of those cells.
        snap = self._swarm([])
        pol = HengbotPolicy()
        pol._emergency_escape_pending = True
        previous = Position(11, 44)
        for position in [snap.player.position, previous] * 5:
            pol._recent.append(position)

        with (
            patch.object(
                pol, "_nearest_goal_step", return_value=previous
            ),
            patch.object(pol, "_blocking_escape_melee_key", return_value="7"),
        ):
            self.assertTrue(pol._is_oscillating())
            self.assertEqual(
                pol._emergency_item(snap, snap.visible_monsters), "2"
            )
        self.assertEqual(pol.last_reason, "emergency:seek-upstairs")

    def test_non_oscillating_emergency_walk_is_unchanged(self):
        snap = self._swarm([])
        pol = HengbotPolicy()
        pol._emergency_escape_pending = True
        step = Position(11, 44)
        pol._recent.extend((snap.player.position, step))

        with patch.object(pol, "_nearest_goal_step", return_value=step):
            self.assertFalse(pol._is_oscillating())
            self.assertEqual(
                pol._emergency_item(snap, snap.visible_monsters), "2"
            )
        self.assertEqual(pol.last_reason, "emergency:seek-upstairs")

    def test_choose_key_death_shape_attacks_instead_of_destinationless_ping_pong(self):
        # Character #5's free south cell was the other half of the 2/8 loop;
        # the mouse is adjacent on a different cell and remains attackable.
        current = Position(10, 44)
        repeated = Position(11, 44)
        mouse = MonsterState(
            index=1,
            position=Position(10, 43),
            hp=10,
            max_hp=10,
            distance=1,
            friendly=False,
            pet=False,
            speed=120,
            max_melee_damage=200,
        )
        snap = Snapshot(
            player(10, 44, hp=100, max_hp=255, class_id=PLAYER_CLASS_WARRIOR),
            {
                current: grid(10, 44),
                repeated: grid(11, 44),
                mouse.position: grid(10, 43, monster=True),
            },
            [mouse],
            floor_key=(2, 1, 0),
        )
        pol = HengbotPolicy()
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(pol, "_decide", return_value=WAIT_KEY):
            pol.choose_key(snap)
        pol._emergency_escape_pending = True
        pol._recent.clear()
        pol._recent.extend([current, repeated] * 6)

        with (
            # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
            patch.object(pol, "_predicted_damage", return_value=1000),
            patch.object(pol, "_nearest_goal_step", return_value=None),
            patch.object(pol, "_flee_step", return_value=repeated),
            patch.object(
                pol, "_break_positional_oscillation", side_effect=lambda _s, key: key
            ),
        ):
            key = pol.choose_key(snap)

        self.assertEqual(
            (key, pol.last_reason),
            ("4", "emergency:cornered-attack"),
        )

    def test_choose_key_no_wait_does_not_reemit_destinationless_flee_step(self):
        current = Position(10, 10)
        repeated = Position(11, 10)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=200),
            {current: grid(10, 10), repeated: grid(11, 10)},
            [],
            floor_key=(1, 1, 0),
        )
        pol = HengbotPolicy()
        pol.choose_key(
            replace(snap, player=replace(snap.player, hp=120), turn=1)
        )
        pol._recent.clear()
        pol._recent.extend([current, repeated] * 6)

        def emergency_wait(_snapshot):
            pol.last_reason = "emergency:wait"
            pol._escape_state.enter("emergency", pol.last_reason)
            return WAIT_KEY

        with (
            # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
            patch.object(pol, "_decide", side_effect=emergency_wait),
            patch.object(pol, "_flee_step", return_value=repeated),
            patch.object(pol, "_least_visited_neighbor", return_value=None),
        ):
            key = pol.choose_key(replace(snap, turn=2))

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(pol.last_reason, "emergency:wait")

    def test_ordinary_navigation_oscillation_guard_still_breaks_cycle(self):
        west = Position(10, 9)
        east = Position(10, 10)
        exit_cell = Position(10, 11)
        grids = {
            west: grid(west.y, west.x),
            east: grid(east.y, east.x),
            exit_cell: grid(exit_cell.y, exit_cell.x),
        }
        pol = HengbotPolicy()
        pol.last_reason = "explore"
        pol._position_changed = True
        for position in grids:
            pol._visit_counts[position] = 10

        broken = None
        for index in range(policy_module.EXTENDED_STUCK_WINDOW + 2):
            position = west if index % 2 else east
            snap = Snapshot(
                player(position.y, position.x), grids, [], floor_key=(2, 1, 0)
            )
            key = pol._break_positional_oscillation(snap, "5")
            if pol.last_reason == "nav:break-oscillation":
                broken = key
                break

        self.assertEqual(broken, "6")
        self.assertEqual(pol.last_reason, "nav:break-oscillation")

    def test_exempted_escape_still_reaches_existing_visible_terminal(self):
        snap = self._swarm([])
        pol = HengbotPolicy()
        pol._nav_exhausted = True
        pol._nav_escape_steps = policy_module.NAV_ESCAPE_STEP_LIMIT

        self.assertEqual(pol._navigation_livelock_key(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "livelock:exhausted")

    def test_choose_key_unseen_recall_escalation_still_moves(self):
        current = Position(10, 10)
        first = Position(11, 10)
        escalation = Position(10, 9)
        grids = {
            current: grid(10, 10),
            first: grid(11, 10),
            escalation: grid(10, 9),
        }
        floor = (1, 5, 0)
        pol = HengbotPolicy()
        pol.choose_key(
            Snapshot(
                player(10, 10, hp=200, max_hp=200, word_recall=5),
                grids,
                [],
                turn=1,
                floor_key=floor,
            )
        )
        pol._recent.clear()
        pol._recent.extend([current, first, current, escalation] * 3)

        with (
            patch.object(pol, "_nearest_goal_step", return_value=first),
            patch.object(
                pol, "_least_visited_neighbor", return_value=escalation
            ),
        ):
            key = pol.choose_key(
                Snapshot(
                    player(10, 10, hp=170, max_hp=200, word_recall=4),
                    grids,
                    [],
                    messages=("It hits you.",),
                    turn=2,
                    floor_key=floor,
                )
            )

        self.assertEqual(key, "4")
        self.assertEqual(pol.last_reason, "unseen-recall:move")
class EmergencyHealBeforeFleeTest(unittest.TestCase):
    def _quest_emergency(self, *, hp=100, inventory=()):
        position = Position(10, 10)
        hostile = MonsterState(
            index=1,
            position=Position(10, 11),
            hp=200,
            max_hp=200,
            distance=1,
            friendly=False,
            pet=False,
            speed=120,
            max_melee_damage=400,
        )
        quest = QuestState(id=99, status=1, fixed=True)
        return Snapshot(
            player(10, 10, hp=hp, max_hp=500, word_recall=10),
            {
                position: grid(10, 10),
                Position(9, 10): grid(9, 10),
                hostile.position: grid(10, 11, monster=True),
            },
            [hostile],
            floor_key=(0, 10, 99),
            quests={99: quest},
            inventory=list(inventory),
        )

    @staticmethod
    def _predicted_damage(
        _snapshot, _hostiles, *, turns, expected=False
    ):
        return 250 if expected and turns == 1 else 500

    def test_quest_floor_lethal_emergency_heals_before_fleeing(self):
        snap = self._quest_emergency(
            inventory=[item("h", TVAL_POTION, SV_POTION_HEALING)]
        )
        policy = HengbotPolicy()

        with patch.object(
            policy, "_predicted_damage", side_effect=self._predicted_damage
        ):
            self.assertEqual(
                policy._emergency_item(snap, snap.visible_monsters), "qh"
            )
        self.assertEqual(policy.last_reason, "emergency:heal")

    def test_instant_escape_still_wins_over_emergency_heal(self):
        snap = self._quest_emergency(
            inventory=[
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
                item("h", TVAL_POTION, SV_POTION_HEALING),
            ]
        )
        policy = HengbotPolicy()

        with patch.object(
            policy, "_predicted_damage", side_effect=self._predicted_damage
        ):
            self.assertEqual(
                policy._emergency_item(snap, snap.visible_monsters), "rt"
            )
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_outpaced_heal_falls_through_to_existing_escape(self):
        snap = self._quest_emergency(
            hp=250,
            inventory=[item("h", TVAL_POTION, SV_POTION_HEALING)],
        )
        policy = HengbotPolicy()

        with patch.object(
            policy,
            "_predicted_damage",
            side_effect=lambda _snapshot, _hostiles, *, turns, expected=False:
                350 if expected and turns == 1 else 500,
        ):
            key = policy._emergency_item(snap, snap.visible_monsters)
        self.assertIsNone(
            policy._find_heal_potion(snap, expected_damage=350)
        )
        self.assertNotEqual(policy.last_reason, "emergency:heal")
        self.assertIn(
            policy.last_reason,
            {"emergency:seek-upstairs", "emergency:cornered-attack"},
        )
        self.assertIsNotNone(key)

    def test_healthy_lethal_emergency_does_not_heal(self):
        snap = self._quest_emergency(
            hp=400,
            inventory=[item("h", TVAL_POTION, SV_POTION_HEALING)],
        )
        policy = HengbotPolicy()

        with patch.object(
            policy, "_predicted_damage", side_effect=self._predicted_damage
        ):
            key = policy._emergency_item(snap, snap.visible_monsters)
        self.assertNotEqual(policy.last_reason, "emergency:heal")
        self.assertIn(
            policy.last_reason,
            {"emergency:seek-upstairs", "emergency:cornered-attack"},
        )
        self.assertIsNotNone(key)
class NoWaitUnderFireTest(unittest.TestCase):
    def test_damage_wait_guard_has_one_public_consumer_and_no_owner_release(self):
        source = Path(policy_module.__file__).read_text(encoding="utf-8")
        source += Path(policy_combat_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        consumers = [
            function.name
            for function in functions.values()
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_forbid_wait_while_damaged"
        ]

        self.assertEqual(consumers, ["choose_key"])
        watch_section = source.split(
            "issue_watch = self._emergency_consumable_issue_watch", 1
        )[1].split("# Recall takes many game turns.", 1)[0]
        self.assertNotIn("_took_damage", watch_section)

    def test_each_registered_escape_wait_has_a_visible_policy_terminal(self):
        from hengbot.policy import ESCAPE_BUDGETED_WAIT_LIMITS

        snapshot = replace(self._snapshot(include_escape=False), visible_monsters=[])
        for reason, limit in ESCAPE_BUDGETED_WAIT_LIMITS.items():
            with self.subTest(reason=reason):
                policy = HengbotPolicy()
                policy.last_reason = reason
                if reason == "combat:disengage-wait":
                    policy._fruitless_disengage_decisions = limit
                else:
                    policy._escape_wait_budget_floor = snapshot.floor_key
                    policy._escape_wait_decisions[reason] = limit - 1
                self.assertEqual(policy._bound_escape_wait(snapshot, WAIT_KEY), WAIT_KEY)
                self.assertEqual(
                    policy.escape_ladder_telemetry["budget_remaining"], 0
                )
                if reason == "combat:disengage-wait":
                    self.assertEqual(policy.last_reason, reason)
                    policy._fruitless_disengage_floor = snapshot.floor_key
                    with patch.object(
                        policy, "_fruitless_fight_is_winnable", return_value=False
                    ):
                        self.assertEqual(
                            policy._fruitless_disengage_key(snapshot, []), WAIT_KEY
                        )
                    self.assertEqual(policy.last_reason, "combat:fruitless")
                else:
                    self.assertEqual(policy.last_reason, "livelock:exhausted")

    def _snapshot(self, *, inventory=(), include_escape=True):
        attacker = hostile(
            1,
            10,
            13,
            max_ranged_damage=13,
        )
        grids = {
            Position(y, x): grid(y, x)
            for y in range(9, 12)
            for x in range(9, 14)
        }
        grids[attacker.position] = grid(
            attacker.position.y,
            attacker.position.x,
            monster=True,
        )
        return Snapshot(
            player(10, 10, hp=228, max_hp=593),
            grids,
            [attacker],
            inventory=(
                [item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)]
                if include_escape
                else list(inventory)
            ),
        )

    def test_ranged_disengage_wait_under_fire_uses_escape_scroll(self):
        snapshot = self._snapshot()
        policy = HengbotPolicy()

        def disengage_wait(_snapshot):
            policy.last_reason = "combat:disengage-wait"
            return WAIT_KEY

        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(policy, "_decide", side_effect=disengage_wait):
            key = policy.choose_key(snapshot)

        self.assertEqual(key, READ_KEY + "t")
        self.assertEqual(policy.last_reason, "no-wait:escape-scroll")

    def test_stationary_waits_are_preserved_without_damage(self):
        snapshot = self._snapshot(include_escape=False)
        policy = HengbotPolicy()

        for reason in (
            "return:wait-recall",
            "quest-strategy:hold",
            "rest",
        ):
            with self.subTest(reason=reason):
                policy.last_reason = reason
                self.assertEqual(
                    policy._forbid_wait_while_damaged(snapshot, WAIT_KEY),
                    WAIT_KEY,
                )
                self.assertEqual(policy.last_reason, reason)

    def test_wait_without_damage_or_hostile_line_of_fire_is_untouched(self):
        snapshot = replace(
            self._snapshot(include_escape=False),
            visible_monsters=[],
        )
        policy = HengbotPolicy()
        policy.last_reason = "return:wait"

        self.assertEqual(
            policy._forbid_wait_while_damaged(snapshot, WAIT_KEY),
            WAIT_KEY,
        )
        self.assertEqual(policy.last_reason, "return:wait")

    def test_boxed_wait_under_fire_attacks_observed_threat(self):
        snapshot = self._snapshot(include_escape=False)
        policy = HengbotPolicy()
        policy._took_damage = True
        policy.last_reason = "emergency:wait"

        with (
            patch.object(policy, "_flee_step", return_value=None),
            patch.object(policy, "_least_visited_neighbor", return_value=None),
            patch.object(
                policy, "_physical_adjacent_hostiles", return_value=[]
            ),
        ):
            self.assertEqual(
                policy._forbid_wait_while_damaged(snapshot, WAIT_KEY),
                "6",
            )
        self.assertEqual(policy.last_reason, "no-wait:attack")

    def test_every_bare_no_op_is_rejected_after_snapshot_damage(self):
        baseline = replace(
            self._snapshot(include_escape=False), visible_monsters=[]
        )
        damaged = replace(
            baseline,
            turn=baseline.turn + 1,
            player=replace(baseline.player, hp=baseline.player.hp - 1),
        )
        policy = HengbotPolicy()

        policy.choose_key(baseline)
        policy.choose_key(damaged)

        for bare_no_op in (WAIT_KEY,):
            with self.subTest(key=repr(bare_no_op)):
                self.assertNotEqual(
                    policy._forbid_wait_while_damaged(damaged, bare_no_op),
                    bare_no_op,
                )

        store = replace(damaged, store=StoreState(STORE_GENERAL, []))
        self.assertEqual(
            policy._forbid_wait_while_damaged(store, "\r"), LEAVE_STORE_KEY
        )

    def test_declared_walkout_no_wait_refuses_destinationless_ping_pong(self):
        from collections import deque

        snapshot = self._snapshot(include_escape=False)
        policy = HengbotPolicy()
        policy._took_damage = True
        policy.last_reason = "combat:disengage-wait"
        policy._escape_state.enter("disengage", policy.last_reason)
        repeated = Position(10, 9)
        alternate = Position(11, 10)
        policy._recent = deque(
            [repeated, snapshot.player.position] * 6,
            maxlen=64,
        )

        with (
            patch.object(policy, "_flee_step", return_value=repeated),
            patch.object(
                policy,
                "_least_visited_neighbor",
                return_value=alternate,
            ),
        ):
            key = policy._forbid_wait_while_damaged(snapshot, WAIT_KEY)

        self.assertEqual(
            key,
            policy._direction_key(snapshot.player.position, alternate),
        )
        self.assertEqual(policy.last_reason, "no-wait:least-visited")
class UniqueCombatConsumableTest(unittest.TestCase):
    def _snapshot(
        self,
        *,
        hp=120,
        max_hp=200,
        speed=110,
        monster_hp=180,
        monster_speed=120,
        monster_level=1,
        blow_sides=10,
        inventory=None,
    ):
        monster = replace(
            hostile(
                1,
                10,
                11,
                hp=monster_hp,
                max_hp=monster_hp,
                speed=monster_speed,
                max_melee_damage=blow_sides,
            ),
            race_id=9001,
            name="test unique",
            level=monster_level,
        )
        snapshot = Snapshot(
            replace(
                player(
                    10,
                    10,
                    hp=hp,
                    max_hp=max_hp,
                    main_hand_blows=5,
                    main_hand_to_h=10,
                    main_hand_to_d=10,
                ),
                speed=speed,
                melee_skill=140,
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
            },
            [monster],
            inventory=inventory or [],
            equipment=[
                item(
                    "main_hand",
                    23,
                    0,
                    is_equipment=True,
                    damage_dice_num=2,
                    damage_dice_sides=6,
                )
            ],
        )
        knowledge = MonraceKnowledge(
            max_hp=monster_hp,
            average_hp=monster_hp,
            speed=monster_speed,
            can_summon=False,
            friendly=False,
            level=monster_level,
            flags=frozenset({"UNIQUE"}),
            blows=(MonsterBlow("HIT", "HURT", 1, blow_sides),),
        )
        return snapshot, monster, knowledge

    @staticmethod
    def _active_quest_target(snapshot, knowledge):
        quest = QuestState(
            41,
            status=QUEST_STATUS_TAKEN,
            type=QUEST_TYPE_RANDOM,
            level=24,
            dungeon_id=1,
            r_idx=9001,
            max_num=1,
        )
        return (
            replace(snapshot, floor_key=(1, 24, 41), quests={41: quest}),
            replace(knowledge, flags=frozenset()),
        )

    @staticmethod
    def _live_damage(*args, **kwargs):
        snapshot = args[0]
        turns = kwargs.get("turns", 3)
        per_turn = 120 if snapshot.player.speed >= 120 else 190
        if kwargs.get("expected"):
            per_turn = 130
        return per_turn * turns

    def test_active_quest_target_commits_speed_and_suppresses_lethal_escape(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=528,
            max_hp=528,
            monster_hp=250,
            monster_speed=120,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED, count=9),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=6),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        snapshot = replace(
            snapshot,
            player=replace(
                snapshot.player,
                main_hand_to_h=11,
                main_hand_to_d=5,
            ),
            equipment=[
                item(
                    "main_hand",
                    22,
                    7,
                    is_equipment=True,
                    damage_dice_num=1,
                    damage_dice_sides=9,
                    to_h=11,
                    to_d=5,
                )
            ],
        )
        snapshot, knowledge = self._active_quest_target(snapshot, knowledge)
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        with patch.object(policy, "_predicted_damage", side_effect=self._live_damage):
            self.assertIsNone(
                policy._unique_fight_projection(
                    snapshot, [monster], monster, player_speed=110
                )
            )
            self.assertIsNotNone(
                policy._unique_fight_projection(
                    snapshot,
                    [monster],
                    monster,
                    player_speed=120,
                    extra_turns=1,
                )
            )
            self.assertEqual(policy.choose_key(snapshot), "qs")
            self.assertEqual(policy.last_reason, "unique:quaff-speed")

            continued_monster = replace(monster, hp=200, max_hp=250)
            continued = replace(
                snapshot,
                player=replace(snapshot.player, hp=372, speed=120),
                visible_monsters=[continued_monster],
                inventory=[
                    item("h", TVAL_POTION, SV_POTION_HEALING, count=6),
                    item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
                ],
            )
            self.assertTrue(
                policy._committed_unique_fight_viable(
                    continued, [continued_monster]
                )
            )
            self.assertIsNone(
                policy._emergency_item(continued, [continued_monster])
            )

    def test_nonquest_nonunique_does_not_use_combat_consumables(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=100,
            monster_speed=120,
            blow_sides=30,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=3),
            ],
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, flags=frozenset())}
        )

        self.assertIsNone(policy._unique_combat_consumable(snapshot, [monster]))
        self.assertIsNone(policy._unique_combat_committed_race_id)

    def test_unique_target_eligibility_remains_unchanged(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=100,
            monster_speed=120,
            blow_sides=30,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=3),
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertTrue(policy._consumable_fight_target(snapshot, monster))
        self.assertEqual(policy._unique_combat_consumable(snapshot, [monster]), "qs")

    def test_unwinnable_quest_target_still_teleports(self):
        snapshot, _, knowledge = self._snapshot(
            hp=80,
            monster_hp=900,
            blow_sides=50,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        snapshot, knowledge = self._active_quest_target(snapshot, knowledge)
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")
        self.assertIsNone(policy._unique_combat_committed_race_id)

    def test_unviable_random_quest_latch_does_not_force_level_based_flee(self):
        snapshot, _, knowledge = self._snapshot(
            hp=515,
            max_hp=515,
            speed=110,
            monster_hp=100000,
            monster_speed=115,
            monster_level=50,
            blow_sides=62,
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING),
            ],
        )
        snapshot, knowledge = self._active_quest_target(snapshot, knowledge)
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        key = policy.choose_key(snapshot)

        self.assertEqual(key, "6")
        self.assertEqual(policy._unviable_quest_floor, snapshot.floor_key)
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, "quest-unviable")

        flickered = replace(
            snapshot,
            turn=snapshot.turn + 1,
            visible_monsters=[],
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        self.assertEqual(policy.choose_key(flickered), "rr")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_give_up_walk_heals_before_recall_wait(self):
        snapshot, _, knowledge = self._snapshot(
            hp=515,
            max_hp=515,
            speed=110,
            monster_hp=100000,
            monster_speed=115,
            monster_level=50,
            blow_sides=62,
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING),
            ],
        )
        snapshot, knowledge = self._active_quest_target(snapshot, knowledge)
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy._unviable_quest_floor = snapshot.floor_key
        policy._returning_to_town = True
        policy._last_return_trigger = "quest-unviable"

        endangered = replace(
            snapshot,
            turn=snapshot.turn + 1,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING),
            ],
            player=replace(
                snapshot.player, hp=131, recalling=True
            ),
        )
        with patch.object(policy, "_predicted_damage", return_value=768):
            self.assertEqual(policy.choose_key(endangered), "qh")
            self.assertEqual(policy.last_reason, "emergency:heal")

    def test_unviable_quest_without_recall_keeps_return_owner_after_flicker(self):
        snapshot, _, knowledge = self._snapshot(
            hp=515,
            max_hp=515,
            speed=110,
            monster_hp=100000,
            monster_speed=115,
            monster_level=50,
            blow_sides=62,
            inventory=[],
        )
        snapshot, knowledge = self._active_quest_target(snapshot, knowledge)
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        policy.choose_key(snapshot)
        flickered = replace(
            snapshot,
            turn=snapshot.turn + 1,
            visible_monsters=[],
        )
        key = policy.choose_key(flickered)

        self.assertNotEqual(key, REST_MACRO)
        self.assertTrue(policy.last_reason.startswith("return:"))
        self.assertNotEqual(policy.last_reason, "explore")
        self.assertTrue(policy._returning_to_town)

    def test_mid_escape_quaffs_cheapest_sufficient_heal_before_walking(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=100,
            max_hp=515,
            monster_hp=1800,
            monster_speed=115,
            blow_sides=62,
            inventory=[
                item("c", TVAL_POTION, 38),
                item("h", TVAL_POTION, SV_POTION_HEALING),
            ],
        )
        snapshot = replace(snapshot, floor_key=(1, 24, 0))
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy._escape_sustain_active = True
        policy._escape_sustain_floor = snapshot.floor_key
        policy.last_reason = "emergency:seek-upstairs"

        with patch.object(policy, "_predicted_damage", return_value=768):
            key = policy._flee_sustain_key(snapshot, "4")

        self.assertEqual(key, "qc")
        self.assertEqual(policy.last_reason, "emergency:heal")

    def test_mid_escape_at_full_hp_preserves_heals_and_keeps_walking(self):
        snapshot, _, knowledge = self._snapshot(
            hp=515,
            max_hp=515,
            monster_hp=1800,
            monster_speed=115,
            blow_sides=62,
            inventory=[
                item("c", TVAL_POTION, 38),
                item("h", TVAL_POTION, SV_POTION_HEALING),
            ],
        )
        snapshot = replace(snapshot, floor_key=(1, 24, 0))
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy._escape_sustain_active = True
        policy._escape_sustain_floor = snapshot.floor_key
        policy.last_reason = "emergency:seek-upstairs"

        with patch.object(policy, "_predicted_damage", return_value=768):
            key = policy._flee_sustain_key(snapshot, "4")

        self.assertEqual(key, "4")
        self.assertEqual(policy.last_reason, "emergency:seek-upstairs")

    def test_mid_escape_with_chip_damage_preserves_heals_and_keeps_walking(self):
        snapshot, _, knowledge = self._snapshot(
            hp=511,
            max_hp=515,
            monster_hp=1800,
            monster_speed=115,
            blow_sides=62,
            inventory=[
                item("c", TVAL_POTION, 38),
                item("h", TVAL_POTION, SV_POTION_HEALING),
            ],
        )
        snapshot = replace(snapshot, floor_key=(1, 24, 0))
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy._escape_sustain_active = True
        policy._escape_sustain_floor = snapshot.floor_key
        policy.last_reason = "emergency:seek-upstairs"

        with patch.object(policy, "_predicted_damage", return_value=1200):
            key = policy._flee_sustain_key(snapshot, "4")

        self.assertEqual(key, "4")
        self.assertEqual(policy.last_reason, "emergency:seek-upstairs")

    def test_escape_start_quaffs_speed_but_active_haste_does_not(self):
        snapshot, _, knowledge = self._snapshot(
            hp=515,
            max_hp=515,
            speed=110,
            monster_hp=1800,
            monster_speed=115,
            blow_sides=20,
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
        )
        snapshot = replace(snapshot, floor_key=(1, 24, 0))
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy.last_reason = "return:seek-upstairs"

        self.assertEqual(policy._flee_sustain_key(snapshot, "4"), "qs")
        self.assertEqual(policy.last_reason, "emergency:quaff-speed")

        hasted = replace(
            snapshot,
            turn=snapshot.turn + 1,
            player=replace(snapshot.player, speed=120),
        )
        policy.last_reason = "return:seek-upstairs"
        self.assertEqual(policy._flee_sustain_key(hasted, "4"), "4")

    def test_speed_attempt_survives_one_interleaved_combat_decision(self):
        snapshot, _, knowledge = self._snapshot(
            hp=515,
            max_hp=515,
            speed=110,
            monster_hp=1800,
            monster_speed=115,
            blow_sides=20,
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
        )
        snapshot = replace(snapshot, floor_key=(1, 24, 0))
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy.last_reason = "return:seek-upstairs"
        self.assertEqual(policy._flee_sustain_key(snapshot, "4"), "qs")

        policy.last_reason = "melee"
        self.assertEqual(policy._flee_sustain_key(snapshot, "6"), "6")
        policy.last_reason = "return:seek-upstairs"
        self.assertEqual(policy._flee_sustain_key(snapshot, "4"), "4")

    def test_instant_escape_does_not_start_speed_episode(self):
        snapshot, _, knowledge = self._snapshot(
            hp=515,
            max_hp=515,
            speed=110,
            monster_hp=1800,
            monster_speed=115,
            blow_sides=20,
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
        )
        snapshot = replace(snapshot, floor_key=(1, 24, 0))
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy.last_reason = "emergency:teleport"
        self.assertEqual(policy._flee_sustain_key(snapshot, "rt"), "rt")
        self.assertFalse(policy._escape_sustain_active)

    def test_two_adjacent_quest_targets_do_not_commit(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=100,
            monster_speed=120,
            blow_sides=30,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=3),
            ],
        )
        second = replace(monster, index=2, position=Position(11, 10))
        snapshot, knowledge = self._active_quest_target(snapshot, knowledge)
        snapshot = replace(
            snapshot,
            grids={
                **snapshot.grids,
                Position(11, 10): grid(11, 10, monster=True),
            },
            visible_monsters=[monster, second],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertIsNone(
            policy._unique_combat_consumable(snapshot, [monster, second])
        )
        self.assertIsNone(policy._unique_combat_committed_race_id)

    def _cure_critical_guardian(
        self, *, hp=463, cure_count=20, monster_speed=115, blow_sides=14
    ):
        snapshot, monster, knowledge = self._snapshot(
            hp=hp,
            max_hp=463,
            monster_hp=181,
            monster_speed=monster_speed,
            blow_sides=blow_sides,
            inventory=(
                [item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=cure_count)]
                if cure_count
                else []
            ),
        )
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, main_hand_blows=1),
        )
        return snapshot, monster, replace(
            knowledge, max_melee_damage=blow_sides
        )

    def test_cure_critical_does_not_sustain_outpaced_guardian(self):
        snapshot, monster, knowledge = self._cure_critical_guardian()
        dungeon = DungeonInfo(44, "Regression guardian", 1, 18, 1, guardian_id=9001)
        policy = HengbotPolicy(
            dungeon_knowledge={44: dungeon},
            monrace_knowledge={9001: knowledge},
        )

        plan = policy._unique_fight_projection(
            snapshot, [monster], monster, player_speed=snapshot.player.speed
        )

        self.assertGreater(
            policy._predicted_damage(snapshot, [monster], turns=1),
            FIXED_QUEST_CURE_CRITICAL_HP,
        )
        self.assertIsNone(plan)
        self.assertFalse(policy._guardian_fight_viable(snapshot, dungeon))

    def test_outpaced_cure_is_not_quaffed_or_committed_viable(self):
        snapshot, monster, knowledge = self._cure_critical_guardian(hp=400)
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy._unique_combat_committed_race_id = 9001

        self.assertIsNone(policy._unique_combat_consumable(snapshot, [monster]))
        self.assertFalse(
            policy._committed_unique_fight_viable(snapshot, [monster])
        )

    def test_cure_critical_sustains_weaker_unique(self):
        snapshot, monster, knowledge = self._cure_critical_guardian(
            hp=100, monster_speed=110, blow_sides=4
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertLessEqual(
            policy._predicted_damage(snapshot, [monster], turns=1),
            FIXED_QUEST_CURE_CRITICAL_HP,
        )
        plan = policy._unique_fight_projection(
            snapshot, [monster], monster, player_speed=snapshot.player.speed
        )
        self.assertIsNotNone(plan)
        self.assertGreater(plan["healing_uses"], 0)
        self.assertEqual(
            policy._unique_combat_consumable(snapshot, [monster]), "qc"
        )

    def test_guardian_without_healing_doses_remains_nonviable(self):
        snapshot, _, knowledge = self._cure_critical_guardian(cure_count=0)
        dungeon = DungeonInfo(44, "Regression guardian", 1, 18, 1, guardian_id=9001)
        policy = HengbotPolicy(
            dungeon_knowledge={44: dungeon},
            monrace_knowledge={9001: knowledge},
        )

        self.assertFalse(policy._guardian_fight_viable(snapshot, dungeon))

    def test_does_not_quaff_speed_for_damage_reduction_without_healing_use(self):
        snapshot, _, knowledge = self._snapshot(
            monster_level=30,
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED, count=2)]
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertNotEqual(policy.last_reason, "unique:quaff-speed")

        hasted = replace(snapshot, player=replace(snapshot.player, speed=120))
        self.assertEqual(policy.choose_key(hasted), "6")
        self.assertNotEqual(policy.last_reason, "unique:quaff-speed")

        expired = replace(
            snapshot,
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
        )
        self.assertEqual(policy.choose_key(expired), "6")
        self.assertNotEqual(policy.last_reason, "unique:quaff-speed")

    def test_quaffs_speed_when_it_saves_a_healing_potion(self):
        snapshot, _, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=100,
            monster_speed=120,
            blow_sides=30,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=3),
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "qs")
        self.assertEqual(policy.last_reason, "unique:quaff-speed")

    def test_does_not_spend_speed_when_unique_needs_no_healing_potion(self):
        snapshot, _, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=60,
            monster_speed=110,
            blow_sides=10,
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_multiple_healing_potions_can_be_committed_to_one_unique_fight(self):
        inventory = [
            item("h", TVAL_POTION, SV_POTION_HEALING, count=2),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
        ]
        snapshot, monster, knowledge = self._snapshot(
            hp=80,
            monster_hp=300,
            monster_speed=110,
            blow_sides=41,
            inventory=inventory,
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        plan = policy._unique_fight_projection(
            snapshot,
            [monster],
            monster,
            player_speed=110,
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan["healing_uses"], 2)
        self.assertEqual(policy.choose_key(snapshot), "qh")
        self.assertEqual(policy.last_reason, "unique:quaff-healing")

        continued = replace(
            snapshot,
            visible_monsters=[replace(monster, hp=150, max_hp=300)],
            inventory=[
                item("h", TVAL_POTION, SV_POTION_HEALING),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        self.assertEqual(policy.choose_key(continued), "qh")
        self.assertEqual(policy.last_reason, "unique:quaff-healing")

    def test_full_hp_unique_fight_quaffs_speed_before_reserved_healing(self):
        snapshot, _, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=300,
            monster_speed=125,
            blow_sides=41,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=3),
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "qs")
        self.assertEqual(policy.last_reason, "unique:quaff-speed")

    def test_does_not_spend_speed_when_unique_fight_is_not_viable(self):
        snapshot, _, knowledge = self._snapshot(
            hp=80,
            monster_hp=500,
            blow_sides=50,
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_disengages_from_harmless_unique_that_exceeds_attack_budget(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=1500,
            monster_speed=115,
            blow_sides=0,
        )
        snapshot = replace(snapshot, floor_key=(DUNGEON_YEEK_CAVE, 1, 0))
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        key = policy.choose_key(snapshot)

        self.assertNotEqual(key, "6")
        self.assertTrue(
            policy.last_reason.startswith("combat:avoid-unprofitable-unique-")
        )
        self.assertEqual(policy._fruitless_disengage_floor, snapshot.floor_key)

    def test_tactical_melee_dps_uses_real_accuracy_below_the_old_floor(self):
        snapshot, _, _ = self._snapshot(hp=100, monster_hp=40, blow_sides=1)
        weapon = snapshot.equipment[0]
        inaccurate = replace(
            snapshot,
            player=replace(
                snapshot.player,
                melee_skill=168,
                main_hand_blows=4,
                main_hand_to_h=-70,
                main_hand_to_d=6,
            ),
        )
        accurate = replace(
            inaccurate,
            player=replace(inaccurate.player, main_hand_to_h=-20),
        )

        self.assertLess(
            HengbotPolicy._main_hand_dps(inaccurate, weapon),
            HengbotPolicy._main_hand_dps(accurate, weapon) / 2,
        )

    def test_engagement_is_not_winnable_with_catastrophic_accuracy(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=100, max_hp=100, monster_hp=40, blow_sides=1
        )
        snapshot = replace(
            snapshot,
            player=replace(
                snapshot.player,
                melee_skill=168,
                main_hand_blows=4,
                main_hand_to_h=-70,
                main_hand_to_d=6,
            ),
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy.threat_prediction = lambda _snapshot, _hostiles, turns: {
            "operational_total": turns * 10
        }

        self.assertFalse(policy._engagement_is_winnable(snapshot, [monster]))

    def test_active_recall_teleports_instead_of_waiting_among_breeders(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=20,
            blow_sides=0,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        breeder = replace(monster, can_multiply=True)
        snapshot = replace(
            snapshot,
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            player=replace(snapshot.player, recalling=True),
            visible_monsters=[breeder],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy._fruitless_disengage_floor = snapshot.floor_key

        key = policy._fruitless_disengage_key(snapshot, [breeder])

        self.assertEqual(key, "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_armed_fruitless_latch_fights_beatable_single_nonbreeder(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=507,
            max_hp=616,
            monster_hp=80,
            blow_sides=49,
        )
        snapshot = replace(
            snapshot,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            visible_monsters=[
                replace(monster, race_id=492, name="Ivory monk")
            ],
        )
        policy = HengbotPolicy(
            monrace_knowledge={
                492: replace(knowledge, flags=frozenset())
            }
        )
        policy._fruitless_disengage_floor = snapshot.floor_key

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_monster_level_does_not_force_flee_from_winnable_nonbreeder(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=616,
            max_hp=616,
            monster_hp=80,
            monster_level=33,
            blow_sides=49,
        )
        snapshot = replace(snapshot, player=replace(snapshot.player, level=27))
        knowledge = replace(knowledge, flags=frozenset())
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertTrue(
            policy._fruitless_fight_is_winnable(snapshot, [monster])
        )
        self.assertFalse(policy._should_flee(snapshot, [monster], [monster]))

    def test_monster_level_does_not_force_flee_from_unwinnable_monster(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=500,
            monster_level=33,
            blow_sides=100,
        )
        snapshot = replace(snapshot, player=replace(snapshot.player, level=27))
        knowledge = replace(knowledge, flags=frozenset())
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertFalse(
            policy._fruitless_fight_is_winnable(snapshot, [monster])
        )
        self.assertFalse(policy._should_flee(snapshot, [monster], [monster]))

    def test_low_hp_fights_winnable_monster_regardless_of_monster_level(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=79,
            max_hp=200,
            monster_hp=20,
            monster_level=33,
            blow_sides=1,
        )
        snapshot = replace(snapshot, player=replace(snapshot.player, level=27))
        knowledge = replace(knowledge, flags=frozenset())
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        self.assertTrue(
            policy._fruitless_fight_is_winnable(snapshot, [monster])
        )
        self.assertFalse(policy._should_flee(snapshot, [monster], [monster]))

    def test_captured_low_hp_dead_end_engages_and_preserves_speed_potion(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=109,
            max_hp=434,
            monster_hp=4,
            monster_speed=120,
            blow_sides=1,
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
        )
        small_kobold = replace(
            monster,
            index=1,
            race_id=9101,
            name="Small kobold",
            position=Position(20, 61),
            distance=1,
        )
        fruit_bat = replace(
            monster,
            index=2,
            race_id=9102,
            name="Fruit bat",
            position=Position(20, 62),
            distance=1,
        )
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, position=Position(21, 62)),
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            grids={
                Position(19, 61): grid(19, 61),
                Position(19, 62): grid(19, 62),
                Position(20, 61): grid(20, 61, monster=True),
                Position(20, 62): grid(20, 62, monster=True),
                Position(21, 61): grid(21, 61),
                Position(21, 62): grid(21, 62),
            },
            visible_monsters=[small_kobold, fruit_bat],
        )
        ordinary = replace(
            knowledge,
            max_hp=4,
            average_hp=4,
            max_melee_damage=1,
            flags=frozenset(),
            blows=(MonsterBlow("HIT", "HURT", 1, 1),),
        )
        policy = HengbotPolicy(
            monrace_knowledge={9101: ordinary, 9102: ordinary}
        )

        key = policy.choose_key(snapshot)

        self.assertNotEqual(policy.last_reason, "flee")
        self.assertTrue(policy.last_reason.startswith("melee"))
        self.assertNotEqual(key, "qs")
        self.assertNotEqual(policy.last_reason, "emergency:quaff-speed")

    def test_low_hp_lost_fight_with_improving_step_still_flees(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=79,
            max_hp=200,
            monster_hp=1000,
            blow_sides=10,
        )
        snapshot = replace(
            snapshot,
            grids={
                Position(10, 9): grid(10, 9),
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
            },
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, flags=frozenset())}
        )

        self.assertEqual(policy.choose_key(snapshot), "4")
        self.assertEqual(policy.last_reason, "flee")

    def test_low_hp_lost_fight_cornered_uses_existing_attack_ladder(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=79,
            max_hp=200,
            monster_hp=1000,
            blow_sides=10,
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, flags=frozenset())}
        )

        key = policy.choose_key(snapshot)
        self.assertEqual(key, "6", policy.last_reason)
        self.assertEqual(policy.last_reason, "flee:cornered-attack")

    def test_stationary_fight_does_not_suppress_an_improving_retreat(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=79,
            max_hp=200,
            monster_hp=1000,
            blow_sides=10,
        )
        snapshot = replace(
            snapshot,
            grids={
                Position(10, 9): grid(10, 9),
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
            },
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, flags=frozenset())}
        )
        policy._build_grid_index(snapshot)
        policy._recent.extend(
            [snapshot.player.position] * (STUCK_WINDOW + 1)
        )
        policy._nav_exhausted = True

        key = policy._decide(snapshot)
        self.assertEqual(key, "4", policy.last_reason)
        self.assertEqual(policy.last_reason, "flee")

    def test_monster_level_does_not_force_breeder_or_unique_flee(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=616,
            max_hp=616,
            monster_hp=20,
            monster_level=33,
            blow_sides=1,
        )
        snapshot = replace(snapshot, player=replace(snapshot.player, level=27))

        breeder = replace(monster, can_multiply=True)
        breeder_policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, flags=frozenset())}
        )
        self.assertFalse(
            breeder_policy._fruitless_fight_is_winnable(snapshot, [breeder])
        )
        self.assertFalse(
            breeder_policy._should_flee(snapshot, [breeder], [breeder])
        )

        unique_policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        self.assertFalse(
            unique_policy._fruitless_fight_is_winnable(snapshot, [monster])
        )
        self.assertFalse(
            unique_policy._should_flee(snapshot, [monster], [monster])
        )

    def test_cornered_disengage_melees_weakest_adjacent_instead_of_waiting(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=20,
            blow_sides=0,
        )
        monster = replace(
            monster, can_multiply=True, max_melee_damage=10
        )
        weaker = replace(
            monster, index=2, hp=5, max_hp=20, can_multiply=True
        )
        snapshot = replace(
            snapshot,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            visible_monsters=[monster, weaker],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy._fruitless_disengage_floor = snapshot.floor_key

        with (
            # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
            patch.object(policy, "_return_to_town_key", return_value=None),
            patch.object(policy, "_summoner_retreat_step", return_value=None),
            patch.object(policy, "_escape_by_stairs", return_value=None),
            patch.object(policy, "_nearest_goal_step", return_value=None),
            patch.object(policy, "_explore_step", return_value=None),
        ):
            key = policy._fruitless_disengage_key(
                snapshot, snapshot.visible_monsters
            )

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "combat:disengage-melee")

    def test_armed_fruitless_latch_still_disengages_from_breeder_swarm(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=50,
            max_hp=200,
            monster_hp=200,
            blow_sides=30,
        )
        breeders = [
            replace(monster, index=index, can_multiply=True)
            for index in range(1, 4)
        ]
        snapshot = replace(
            snapshot,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            visible_monsters=breeders,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy._fruitless_disengage_floor = snapshot.floor_key

        key = policy._fruitless_disengage_key(snapshot, breeders)

        self.assertNotEqual(key, "6")
        self.assertTrue(policy.last_reason.startswith("combat:disengage-"))

    def test_lethal_single_threat_still_uses_emergency_escape(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=50,
            max_hp=200,
            monster_hp=20,
            blow_sides=100,
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        snapshot = replace(
            snapshot,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        policy._fruitless_disengage_floor = snapshot.floor_key

        with patch.object(
            policy,
            "threat_prediction",
            return_value={"operational_total": snapshot.player.hp},
        ):
            self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_weak_breeder_containment_never_arms_disengage(self):
        from hengbot.cli import MULTIPLIER_COMBAT_LOOP_WINDOW

        snapshot, monster, knowledge = self._snapshot(
            hp=600, max_hp=600, monster_hp=8, blow_sides=0
        )
        breeder = replace(monster, can_multiply=True)
        snapshot = replace(
            snapshot,
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            visible_monsters=[breeder],
        )
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        for _ in range(MULTIPLIER_COMBAT_LOOP_WINDOW + 1):
            policy._update_combat_outcome(snapshot)

        self.assertTrue(policy._combat_fruitful)
        self.assertIsNone(policy._fruitless_disengage_floor)
        self.assertFalse(policy._returning_to_town)

    def test_does_not_disengage_from_current_objective_guardian(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=1500,
            monster_speed=115,
            blow_sides=0,
        )
        snapshot = replace(snapshot, floor_key=(DUNGEON_YEEK_CAVE, 13, 0))
        dungeon = DungeonInfo(
            DUNGEON_YEEK_CAVE,
            "Yeek Cave",
            1,
            13,
            1,
            guardian_id=9001,
        )
        policy = HengbotPolicy(
            dungeon_knowledge={DUNGEON_YEEK_CAVE: dungeon},
            monrace_knowledge={9001: knowledge},
        )

        self.assertIsNone(
            policy._unprofitable_unique_disengage_key(snapshot, [monster])
        )
        self.assertIsNone(policy._fruitless_disengage_floor)

    def test_does_not_disengage_from_harmless_unique_on_locked_kill_quest_floor(self):
        snapshot, monster, knowledge = self._snapshot(
            hp=200,
            max_hp=200,
            monster_hp=1500,
            monster_speed=115,
            blow_sides=0,
        )
        snapshot = replace(snapshot, floor_key=(DUNGEON_YEEK_CAVE, 5, 0))
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})

        with patch.object(
            policy, "_floor_navigation_exit_locked", return_value=True
        ):
            self.assertIsNone(
                policy._unprofitable_unique_disengage_key(
                    snapshot, [monster]
                )
            )

        self.assertIsNone(policy._fruitless_disengage_floor)

    def test_does_not_spend_rare_potions_on_an_ordinary_monster(self):
        snapshot, _, knowledge = self._snapshot(
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)]
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, flags=frozenset())}
        )

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_summoning_unique_in_a_choke_point_does_not_spend_speed_without_healing(self):
        snapshot, monster, knowledge = self._snapshot(
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)]
        )
        snapshot = replace(
            snapshot,
            visible_monsters=[replace(monster, can_summon=True)],
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, can_summon=True)}
        )

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_summoning_unique_in_open_terrain_escapes_without_spending_speed(self):
        snapshot, monster, knowledge = self._snapshot(
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ]
        )
        open_room = {
            Position(y, x): grid(y, x, monster=(y, x) == (10, 11))
            for y in range(9, 12)
            for x in range(9, 12)
        }
        snapshot = replace(
            snapshot,
            grids=open_room,
            visible_monsters=[replace(monster, can_summon=True)],
        )
        policy = HengbotPolicy(
            monrace_knowledge={9001: replace(knowledge, can_summon=True)}
        )

        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")
class ThreatPredictionMemoTest(unittest.TestCase):
    """One decision asks for the same threat prediction up to six times (the
    emergency/return gates plus the decision-log telemetry); the memo must hand
    back the identical result instead of paying the aggregate-p95 convolution
    again, and must never carry a result across snapshots."""

    @staticmethod
    def _snap(threat):
        return Snapshot(
            player(10, 10),
            {},
            [threat],
            floor_key=(DUNGEON_ANGBAND, 30, 0),
            inventory=[],
            equipment=[],
        )

    def test_repeat_calls_for_one_snapshot_reuse_the_result(self):
        threat = hostile(
            1, 10, 12, hp=30, max_hp=30, distance=2,
            max_melee_damage=10, max_ranged_damage=6,
        )
        snap = self._snap(threat)
        pol = HengbotPolicy()
        first = pol.threat_prediction(snap, [threat])
        self.assertIs(pol.threat_prediction(snap, [threat]), first)
        # A different horizon is a different prediction, not a memo hit.
        self.assertIsNot(pol.threat_prediction(snap, [threat], turns=1), first)

    def test_a_new_snapshot_is_recomputed(self):
        threat = hostile(1, 10, 12, hp=30, max_hp=30, distance=2, max_melee_damage=10)
        one = self._snap(threat)
        two = self._snap(threat)
        pol = HengbotPolicy()
        self.assertIsNot(
            pol.threat_prediction(one, [threat]),
            pol.threat_prediction(two, [threat]),
        )
class AggregateRangedCacheTest(unittest.TestCase):
    """_aggregate_ranged_percentile keys the expensive convolution on its actual
    inputs, so an unchanged engagement (same race, actions, distance, player
    profile) is computed once and reused ACROSS decisions. player_hp is in the
    key only for HAND_DOOM races; for everyone else an HP change must still
    hit the cache (the standoff/kite case the cache exists for)."""

    KNOWLEDGE = MonraceKnowledge(
        max_hp=48,
        average_hp=30,
        speed=110,
        can_summon=False,
        friendly=False,
        level=12,
        max_melee_damage=8,
        max_ranged_damage=98,
        abilities=frozenset({"BA_POIS", "BLINK", "CONF", "SLOW", "S_MONSTER"}),
        spell_frequency=25,
    )
    DOOM_KNOWLEDGE = MonraceKnowledge(
        max_hp=200,
        average_hp=150,
        speed=110,
        can_summon=False,
        friendly=False,
        level=40,
        max_melee_damage=8,
        max_ranged_damage=90,
        abilities=frozenset({"HAND_DOOM"}),
        spell_frequency=25,
    )

    @staticmethod
    def _monster(x=12, distance=2):
        return replace(
            hostile(
                1, 10, x, distance=distance,
                max_melee_damage=8, max_ranged_damage=98,
            ),
            race_id=224,
        )

    @staticmethod
    def _snap(monster, hp=30):
        grids = {
            Position(10, x): grid(10, x, monster=(x == monster.position.x))
            for x in range(10, monster.position.x + 1)
        }
        return Snapshot(
            player(10, 10, hp=hp, max_hp=100),
            grids,
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=[],
        )

    def _count_aggregate_calls(self, pol, engagements):
        from unittest import mock

        from hengbot.monster_ranged_evaluator import (
            aggregate_ranged_damage_percentile as real_aggregate,
        )

        with mock.patch(
            "hengbot.policy.aggregate_ranged_damage_percentile",
            wraps=real_aggregate,
        ) as agg:
            for snap, monster in engagements:
                pol.threat_prediction(snap, [monster])
        return agg.call_count

    def test_identical_engagement_across_snapshots_computes_once(self):
        pol = HengbotPolicy(monrace_knowledge={224: self.KNOWLEDGE})
        first, second = self._monster(), self._monster()
        hurt = self._monster()
        calls = self._count_aggregate_calls(
            pol,
            [
                (self._snap(first), first),
                (self._snap(second), second),
                # Player HP changed but the race has no HAND_DOOM: still a hit.
                (self._snap(hurt, hp=15), hurt),
            ],
        )
        self.assertEqual(calls, 1)

    def test_distance_change_recomputes(self):
        pol = HengbotPolicy(monrace_knowledge={224: self.KNOWLEDGE})
        near, far = self._monster(), self._monster(x=14, distance=4)
        calls = self._count_aggregate_calls(
            pol, [(self._snap(near), near), (self._snap(far), far)]
        )
        self.assertEqual(calls, 2)

    def test_hand_of_doom_keys_on_player_hp(self):
        pol = HengbotPolicy(monrace_knowledge={224: self.DOOM_KNOWLEDGE})
        healthy, hurt = self._monster(), self._monster()
        calls = self._count_aggregate_calls(
            pol,
            [(self._snap(healthy, hp=90), healthy), (self._snap(hurt, hp=45), hurt)],
        )
        self.assertEqual(calls, 2)
