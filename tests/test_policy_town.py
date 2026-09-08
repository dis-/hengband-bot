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

FOOD_TYPE_MANA = 4

class ReturnToTownTest(unittest.TestCase):
    FLOOR = (1, 12, 0)

    def _pack(self, count):
        return [item(chr(ord("a") + i), TVAL_RING, 0) for i in range(count)]

    def _stairs(self):
        return {
            Position(10, 8): grid(10, 8, upstairs=True),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
        }

    def _exit_owner_snapshot(self, x, *, block_upstairs=False, turn=1):
        floors = {Position(10, column) for column in range(8, 15)}
        grids = {
            position: grid(
                position.y, position.x, upstairs=position == Position(10, 14)
            )
            for position in floors
        }
        for position in floors:
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if neighbor not in grids:
                    grids[neighbor] = grid(neighbor.y, neighbor.x, passable=False)
        if block_upstairs:
            grids[Position(10, 12)] = grid(10, 12, monster=True)
        return Snapshot(
            player(10, x, food=6000),
            grids,
            [],
            turn=turn,
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY),
            width=40,
            height=40,
        )

    def _prepare_exit_owner_policy(self, snapshot):
        policy = HengbotPolicy()
        policy._floor_key = self.FLOOR
        policy._returning_to_town = True
        policy._build_grid_index(snapshot)
        policy._visit_counts.update(
            {Position(10, column): 1 for column in range(8, 15)}
        )
        for y, x in policy._remembered_wall_t:
            if x >= 9:
                policy._wall_search_counts[(y, x)] = SEARCH_LIMIT
        return policy

    def _incident_snapshot(self, position, turn):
        route = (Position(8, 17), Position(7, 18), Position(6, 19))
        grids = {
            cell: grid(
                cell.y,
                cell.x,
                upstairs=cell == Position(6, 19),
            )
            for cell in route
        }
        for cell in route:
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(cell.y + dy, cell.x + dx)
                if neighbor not in grids:
                    grids[neighbor] = grid(
                        neighbor.y, neighbor.x, passable=False
                    )
        return Snapshot(
            player(position.y, position.x, hp=265, max_hp=265, food=6000),
            grids,
            [],
            turn=turn,
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY),
            width=40,
            height=40,
        )

    def _prepare_incident_policy(self):
        policy = HengbotPolicy()
        policy._floor_key = self.FLOOR
        policy._returning_to_town = True
        policy._last_return_trigger = "pack-full"
        policy._unseen_retreat_floor = self.FLOOR
        policy._unseen_retreat_direction = (1, -1)
        policy._unseen_retreat_target = Position(8, 17)
        return policy

    def test_latched_return_owns_consecutive_armed_unseen_decisions(self):
        policy = self._prepare_incident_policy()
        decisions = (
            self._incident_snapshot(Position(8, 17), 1),
            self._incident_snapshot(Position(7, 18), 2),
        )

        reasons = []
        for snapshot in decisions:
            policy.choose_key(snapshot)
            reasons.append(policy.last_reason)

        self.assertEqual(reasons, ["return:seek-upstairs"] * 2)
        self.assertFalse(any(reason.startswith("unseen:") for reason in reasons))

    def test_incident_replay_leaves_ping_pong_cells_and_reaches_exit(self):
        policy = self._prepare_incident_policy()
        position = Position(8, 17)
        visited = [position]
        direction = {
            "9": (-1, 1),
        }

        for turn in range(1, 4):
            key = policy.choose_key(self._incident_snapshot(position, turn))
            if key == UP_STAIRS_KEY:
                break
            dy, dx = direction[key]
            position = Position(position.y + dy, position.x + dx)
            visited.append(position)

        self.assertEqual(visited, [
            Position(8, 17),
            Position(7, 18),
            Position(6, 19),
        ])
        self.assertEqual(key, UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_emergency_still_preempts_return_and_armed_unseen_retreat(self):
        policy = self._prepare_incident_policy()
        snapshot = self._incident_snapshot(Position(8, 17), 1)

        def emergency(_snapshot, _hostiles):
            policy.last_reason = "emergency:teleport"
            return "rt"

        with (
            patch.object(policy, "_emergency_item", side_effect=emergency),
            patch.object(
                policy, "_unseen_retreat_key", wraps=policy._unseen_retreat_key
            ) as unseen,
            patch.object(
                policy, "_return_to_town_key", wraps=policy._return_to_town_key
            ) as town_return,
        ):
            self.assertEqual(policy.choose_key(snapshot), "rt")

        self.assertEqual(policy.last_reason, "emergency:teleport")
        unseen.assert_not_called()
        town_return.assert_not_called()

    def test_reads_an_identified_recall_scroll_when_pack_is_full(self):
        inventory = self._pack(PACK_CAPACITY - 1)
        inventory.append(item("w", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL))
        snap = Snapshot(
            player(10, 10, food=12000),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=self.FLOOR,
            inventory=inventory,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rw")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_full_pack_without_recall_seeks_upstairs(self):
        snap = Snapshot(
            player(10, 10, food=6000),
            self._stairs(),
            [],
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_return_exit_owners_do_not_alternate_when_a_monster_blocks_the_corridor(self):
        clear = self._exit_owner_snapshot(10, turn=1)
        blocked = self._exit_owner_snapshot(11, block_upstairs=True, turn=2)
        clear_again = self._exit_owner_snapshot(10, turn=3)
        policy = self._prepare_exit_owner_policy(clear)

        results = []
        for decision, snapshot in enumerate(
            (clear, blocked, clear_again), start=1
        ):
            policy._build_grid_index(snapshot)
            policy._escape_state.begin_decision(snapshot, decision)
            policy._return_to_town_key(snapshot, [])
            results.append(policy.last_reason)

        self.assertEqual(
            results,
            [
                "return:seek-upstairs",
                "return:seek-secret-wall",
                "return:seek-secret-wall",
            ],
        )

    def test_plainly_reachable_upstairs_ignore_the_exit_owner_latch(self):
        snapshot = self._exit_owner_snapshot(10)
        policy = self._prepare_exit_owner_policy(snapshot)

        self.assertEqual(policy._return_to_town_key(snapshot, []), "6")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_exit_owner_latch_releases_after_two_stable_upstairs_steps(self):
        blocked = self._exit_owner_snapshot(11, block_upstairs=True, turn=1)
        first_clear = self._exit_owner_snapshot(10, turn=2)
        second_clear = self._exit_owner_snapshot(9, turn=3)
        policy = self._prepare_exit_owner_policy(blocked)

        policy._escape_state.begin_decision(blocked, 1)
        self.assertEqual(policy._return_to_town_key(blocked, []), "4")
        self.assertEqual(policy.last_reason, "return:seek-secret-wall")
        policy._build_grid_index(first_clear)
        policy._escape_state.begin_decision(first_clear, 2)
        self.assertEqual(policy._return_to_town_key(first_clear, []), "4")
        self.assertEqual(policy.last_reason, "return:seek-secret-wall")
        policy._build_grid_index(second_clear)
        policy._escape_state.begin_decision(second_clear, 3)
        self.assertEqual(policy._return_to_town_key(second_clear, []), "6")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_armed_unseen_does_not_reset_exit_owner_release_hysteresis(self):
        first_clear = self._exit_owner_snapshot(10, turn=1)
        second_clear = self._exit_owner_snapshot(9, turn=2)
        policy = self._prepare_exit_owner_policy(first_clear)
        policy._escape_state.begin_decision(first_clear, 0)
        policy._escape_state.enter("return", "return:seek-secret-wall")

        with (
            patch.object(
                policy, "_unseen_retreat_intercept_key", return_value=None
            ),
            patch.object(policy, "_unseen_retreat_key", return_value=WAIT_KEY),
        ):
            self.assertEqual(policy.choose_key(first_clear), "4")
            self.assertEqual(policy.last_reason, "return:seek-secret-wall")
            self.assertEqual(policy.choose_key(second_clear), "6")

        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_armed_unseen_does_not_destroy_wall_search_owner(self):
        grids = {Position(10, 10): grid(10, 10)}
        for dy, dx in NEIGHBOR_OFFSETS:
            grids[Position(10 + dy, 10 + dx)] = grid(
                10 + dy, 10 + dx, passable=False
            )
        snapshot = Snapshot(
            player(10, 10, food=6000),
            grids,
            [],
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY),
            width=40,
            height=40,
        )
        policy = HengbotPolicy()
        policy._floor_key = self.FLOOR
        policy._returning_to_town = True
        policy._escape_state.begin_decision(snapshot, 0)
        policy._escape_state.enter("return", "return:seek-secret-wall")

        with (
            patch.object(
                policy, "_unseen_retreat_intercept_key", return_value=None
            ),
            patch.object(policy, "_unseen_retreat_key", return_value=WAIT_KEY),
        ):
            for _ in range(2):
                self.assertEqual(policy.choose_key(snapshot), "s")
                self.assertEqual(policy.last_reason, "return:search-upstairs")
                self.assertEqual(policy._escape_state.owner, "return")
                self.assertEqual(
                    policy._escape_state.rung, "return:seek-secret-wall"
                )

    def test_escape_decision_ledger_reads_reachability_once(self):
        snapshot = self._exit_owner_snapshot(10)
        policy = self._prepare_exit_owner_policy(snapshot)
        calls = 0

        def reachable():
            nonlocal calls
            calls += 1
            return Position(10, 11)

        policy._escape_state.begin_decision(snapshot, 1)
        first = policy._escape_state.read_once(snapshot, "reachable", reachable)
        second = policy._escape_state.read_once(snapshot, "reachable", reachable)

        self.assertEqual(first, Position(10, 11))
        self.assertEqual(second, first)
        self.assertEqual(calls, 1)

    def test_escape_decision_ledger_refreshes_when_same_turn_gets_new_decision(self):
        snapshot = self._exit_owner_snapshot(10, turn=280712)
        state = EscapeState()
        values = iter((Position(27, 25), Position(26, 26)))

        state.begin_decision(snapshot, 1)
        first = state.read_once(snapshot, "reachable", lambda: next(values))
        state.begin_decision(snapshot, 2)
        second = state.read_once(snapshot, "reachable", lambda: next(values))

        self.assertEqual(first, Position(27, 25))
        self.assertEqual(second, Position(26, 26))

    def test_same_turn_return_recomputes_upstairs_step_after_player_moves(self):
        positions = (Position(28, 24), Position(27, 25), Position(26, 26))
        grids = {
            position: grid(
                position.y,
                position.x,
                upstairs=position == positions[-1],
            )
            for position in positions
        }
        for position in positions:
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if neighbor not in grids:
                    grids[neighbor] = grid(
                        neighbor.y, neighbor.x, passable=False
                    )

        def at(position):
            return Snapshot(
                player(position.y, position.x, food=6000),
                grids,
                [],
                turn=280712,
                floor_key=self.FLOOR,
                inventory=self._pack(PACK_CAPACITY),
                width=40,
                height=40,
            )

        first = at(positions[0])
        second = at(positions[1])
        policy = self._prepare_exit_owner_policy(first)

        self.assertEqual(policy.choose_key(first), "9")
        self.assertEqual(policy.choose_key(second), "9")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")
        self.assertEqual(
            policy._escape_state.ledger["return:upstairs-step"],
            positions[2],
        )

    def test_step_toward_self_returns_labeled_wait(self):
        snapshot = self._exit_owner_snapshot(10)
        policy = HengbotPolicy()

        self.assertEqual(
            policy._step_toward(snapshot, snapshot.player.position), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "nav:step-self")

    def test_emergency_owner_releases_to_disengage_immediately(self):
        snapshot = self._exit_owner_snapshot(10)
        policy = self._prepare_exit_owner_policy(snapshot)
        emergency_results = iter(("t", None))

        def emergency(_snapshot, _hostiles):
            result = next(emergency_results)
            if result is not None:
                policy.last_reason = "emergency:teleport"
            return result

        disengage = Mock(return_value=WAIT_KEY)
        with (
            patch.object(policy, "_emergency_item", side_effect=emergency),
            patch.object(policy, "_fruitless_disengage_key", disengage),
        ):
            policy.choose_key(snapshot)
            policy.choose_key(replace(snapshot, turn=2))

        self.assertNotEqual(policy._escape_state.owner, "emergency")
        disengage.assert_called_once()

    def test_escape_state_tolerates_store_snapshot_without_floor_key(self):
        policy = HengbotPolicy()
        policy._escape_state.floor = (DUNGEON_YEEK_CAVE, 2, 0)
        store_snapshot = SimpleNamespace(store=StoreState(STORE_HOME, []))

        policy._escape_state.begin_decision(store_snapshot, 1)

        self.assertEqual(
            policy._escape_state.floor, (DUNGEON_YEEK_CAVE, 2, 0)
        )
        self.assertEqual(
            policy._escape_state.decision_token, 1
        )

    def test_breeder_does_not_arm_old_fruitless_counter(self):
        snapshot = self._exit_owner_snapshot(10)
        breeder = hostile(
            1, 10, 12, distance=2, can_multiply=True,
            max_melee_damage=5,
        )
        fighting = replace(snapshot, visible_monsters=[breeder])
        policy = self._prepare_exit_owner_policy(fighting)
        policy._escape_state.budgets["fruitless-disengage"] = 37
        policy._breeder_engagement_floor = fighting.floor_key
        policy._breeder_engagement_score = (
            policy_module.BREEDER_CONTAINMENT_WINDOW - 1
        )

        policy._fruitless_disengage_spent_this_decision = True
        policy._update_combat_outcome(fighting)
        policy._fruitless_disengage_spent_this_decision = False
        policy._update_combat_outcome(replace(fighting, visible_monsters=[], turn=2))
        policy._breeder_engagement_score = (
            policy_module.BREEDER_CONTAINMENT_WINDOW - 1
        )
        policy._fruitless_disengage_spent_this_decision = True
        policy._update_combat_outcome(replace(fighting, turn=3))

        self.assertEqual(policy._fruitless_disengage_decisions, 0)
        self.assertEqual(
            policy._escape_state.budgets["fruitless-disengage"], 37
        )

    def test_return_ignores_a_nonadjacent_weak_enemy_and_keeps_seeking_upstairs(self):
        grids = self._stairs()
        grids[Position(10, 12)] = grid(10, 12, monster=True)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100, food=6000),
            grids,
            [hostile(1, 10, 12, distance=2)],
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_does_not_use_an_unaware_recall_scroll_from_an_old_snapshot(self):
        inventory = self._pack(PACK_CAPACITY - 1)
        inventory.append(
            item("w", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, aware=False)
        )
        snap = Snapshot(
            player(10, 10, food=6000),
            self._stairs(),
            [],
            floor_key=self.FLOOR,
            inventory=inventory,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_does_not_return_with_one_free_pack_slot(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, food=12000),
            grids,
            [],
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY - 1),
        )

        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_does_not_return_after_refill_reduces_oil_below_town_target(self):
        snap = Snapshot(
            player(
                10, 10, level=24, hp=413, max_hp=413,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
                item("p", TVAL_SCROLL, SV_SCROLL_PHASE_DOOR),
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=4, fuel=7500),
            ],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=7000)],
        )
        policy = HengbotPolicy()

        self.assertFalse(policy._should_start_town_return(snap))

    def test_empty_escape_kit_on_recall_max_depth_reads_recall(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_ANGBAND, 24, 0),
            dungeon_recall_depths={DUNGEON_ANGBAND: 24},
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            ],
        )
        policy = HengbotPolicy()
        policy._observe(snap)
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        self.assertFalse(
            policy._supply_ledger(snap, snap.dungeon_level)["teleport"].obtainable
        )

        with patch.object(policy, "_missing_required_abilities", return_value=()):
            self.assertTrue(policy._should_start_town_return(snap))
            self.assertEqual(policy._last_return_trigger, "escape-kit-empty")
            self.assertEqual(policy.choose_key(snap), READ_KEY + "r")
        self.assertEqual(policy._last_return_trigger, "escape-kit-empty")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_teleport_prevents_escape_kit_return_on_recall_max_depth(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_ANGBAND, 1, 0),
            dungeon_recall_depths={DUNGEON_ANGBAND: 1},
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3)],
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

        self.assertFalse(policy._should_start_town_return(snap))
        self.assertIsNone(policy._last_return_trigger)

    def test_unaware_phase_scroll_does_not_count_as_escape_kit(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_ANGBAND, 24, 0),
            dungeon_recall_depths={DUNGEON_ANGBAND: 24},
            inventory=[
                item("p", TVAL_SCROLL, SV_SCROLL_PHASE_DOOR, aware=False)
            ],
        )
        policy = HengbotPolicy()

        self.assertTrue(policy._should_start_town_return(snap))
        self.assertEqual(policy._last_return_trigger, "escape-kit-empty")

    def test_empty_escape_kit_does_not_return_below_recall_max_depth(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_ANGBAND, 1, 0),
            dungeon_recall_depths={DUNGEON_ANGBAND: 2},
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

        self.assertFalse(policy._should_start_town_return(snap))
        self.assertIsNone(policy._last_return_trigger)

    def test_unobtainable_empty_escape_kit_does_not_bounce_shallow_floor(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_ANGBAND, 1, 0),
            dungeon_recall_depths={DUNGEON_ANGBAND: 1},
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
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn

        self.assertFalse(policy._should_start_town_return(snap))
        self.assertIsNone(policy._last_return_trigger)

    def test_empty_escape_kit_does_not_return_during_fundraising_walk_in(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            dungeon_recall_depths={DUNGEON_YEEK_CAVE: 1},
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertFalse(policy._should_start_town_return(snap))
        self.assertIsNone(policy._last_return_trigger)

    def test_cycle_break_preserves_escape_kit_restock_store(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._last_return_trigger = "escape-kit-empty"

        policy._break_town_cycle(snap)

        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_returns_when_equipped_light_is_empty_and_cannot_be_refilled(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
                item("f", TVAL_FOOD, 35, count=5),
            ],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=0)],
            grids_observed=True,
        )
        policy = HengbotPolicy()

        self.assertTrue(policy._should_start_town_return(snap))

    def test_refills_empty_lantern_instead_of_immediately_returning(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_ANGBAND, 1, 0),
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=3),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=3),
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=7500),
            ],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=0)],
        )
        policy = HengbotPolicy()

        self.assertFalse(policy._should_start_town_return(snap))
        self.assertEqual(policy.choose_key(snap), "\\Fo")
        self.assertEqual(policy.last_reason, "refill-light")

    def test_latched_return_refills_empty_lantern_before_reading_recall(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(4, 18, 0),
            inventory=[
                item("f", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=8),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=7500),
            ],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=0)],
            grids_observed=True,
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True

        self.assertEqual(policy.choose_key(snap), "\\Fo")
        self.assertEqual(policy.last_reason, "refill-light")

    def test_return_mode_survives_an_opened_pack_slot_and_blocks_descent(self):
        policy = HengbotPolicy()
        full = Snapshot(
            player(10, 10, food=6000),
            self._stairs(),
            [],
            floor_key=self.FLOOR,
            inventory=self._pack(PACK_CAPACITY),
        )
        policy.choose_key(full)
        grids = self._stairs()
        grids[Position(10, 10)] = grid(10, 10, downstairs=True)
        opened = Snapshot(
            player(10, 10, food=6000),
            grids,
            [],
            floor_key=self.FLOOR,
            inventory=self._pack(1),
        )

        self.assertEqual(policy.choose_key(opened), "4")
        self.assertEqual(policy.last_reason, "return:seek-upstairs")

    def test_waits_safely_after_recall_has_started(self):
        snap = Snapshot(
            player(10, 10, food=6000, word_recall=12),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=self.FLOOR,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "5")
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_walking_return_breaks_four_cell_frontier_oscillation(self):
        positions = [
            Position(26, 109), Position(27, 108),
            Position(28, 109), Position(29, 108),
        ]
        snapshot = Snapshot(
            player(27, 108, food=6000),
            {position: grid(position.y, position.x) for position in positions},
            [],
            floor_key=self.FLOOR,
            width=198,
            height=66,
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True
        policy._floor_key = self.FLOOR
        policy._recent.extend((positions * 3)[:9])

        self.assertEqual(policy.choose_key(snapshot), "8")
        self.assertEqual(policy.last_reason, "return:probe")

    def test_low_food_without_supplies_uses_identified_recall(self):
        recall = item("h", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = Snapshot(
            player(10, 10, food=1500),  # "hungry" band: out of food, time to go home
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=self.FLOOR,
            inventory=[recall],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rh")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_food_in_pack_prevents_early_food_return(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, food=2500),
            grids,
            [],
            floor_key=self.FLOOR,
            inventory=[item("b", TVAL_FOOD, 35)],
        )

        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_normal_food_band_without_supplies_no_longer_returns(self):
        # "normal" is a wide band with ample margin; a MANA character lives off its
        # identify-staff charges. Dropping below Full is no longer a reason to bail —
        # only actual hunger is (see test_hungry_without_supplies_starts_return).
        snap = Snapshot(
            player(10, 10, food=6000),
            self._stairs(),
            [],
            floor_key=self.FLOOR,
        )
        policy = HengbotPolicy()

        self.assertFalse(policy._should_start_town_return(snap))
        self.assertNotEqual(policy.choose_key(snap), "rh")

    def test_hungry_without_supplies_starts_return(self):
        # Once genuinely hungry (below the "normal" band) with nothing to eat, end
        # the run while there is still margin to reach town.
        snap = Snapshot(
            player(10, 10, food=1500),  # "hungry" band
            self._stairs(),
            [],
            floor_key=self.FLOOR,
        )
        self.assertTrue(HengbotPolicy()._should_start_town_return(snap))

    def test_full_food_band_without_supplies_can_continue(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, food=12000),
            grids,
            [],
            floor_key=self.FLOOR,
        )

        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_full_pack_of_junk_destroys_overflow_to_reenter_the_dungeon(self):
        # A pack full of items no shop buys and the Home will not take (here,
        # non-wearable rings standing in for devices/junk) must NOT strand the
        # bot in town: with no sale/deposit/purchase possible it drops one so a
        # slot frees and descent unblocks, instead of waiting forever.
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, food=6000),
            grids,
            [],
            floor_key=(0, 0, 0),
            inventory=self._pack(PACK_CAPACITY),
        )

        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "01ka")
        self.assertEqual(pol.last_reason, "town:destroy-overflow")

class TownAndFundraisingPolicyTest(shop_fixture._TownShopFixtureBase):
    def test_recovered_home_entry_charges_an_evaporated_route_claim(self):
        inside = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=self._strict_supplies(detection=5),
            store=StoreState(
                STORE_HOME, [], stock_num=0, page_top=0, page_size=52,
            ),
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(inside), LEAVE_STORE_KEY)
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_scan_source, "observed-home-page")
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

        completed = HengbotPolicy()
        stored = store_item("a", TVAL_POTION, 999, name="stored")
        completed.consume_home_knowledge((stored,))
        completed_inside = replace(
            inside, store=StoreState(
                STORE_HOME, [stored], stock_num=1, page_top=0, page_size=52,
            )
        )
        self.assertEqual(completed.choose_key(completed_inside), LEAVE_STORE_KEY)
        self.assertEqual(completed.last_reason, "home:route-claim-unfulfilled")
        self.assertEqual(
            completed._town_store_attempted[STORE_HOME], completed_inside.turn
        )

    def test_fundraising_does_not_route_to_oil_with_permanent_light(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item("d", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=5),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            equipment=[
                item(
                    "light", TVAL_LITE, SV_LITE_FEANOR,
                    name="Feanorian Lamp", is_equipment=True,
                    known=True, fully_known=True,
                )
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        categories = {
            need.category for need in policy._enumerate_town_needs(snap)
        }
        self.assertNotIn("fundraising-oil", categories)

    def test_recall_at_departure_requirement_is_ready(self):
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(recall=5),
        )
        policy = HengbotPolicy()
        policy._deepest_level = 13

        status = policy._supply_ledger(snap, policy._planned_depth())["recall"]
        snap = replace(
            snap,
            inventory=self._strict_supplies(recall=status.required_departure),
        )

        self.assertTrue(policy._recall_departure_ready(snap))

    def test_low_gold_bootstrap_can_use_walk_based_fundraising_departure(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=0,
                hp=20,
                max_hp=20,
                mp=0,
                max_mp=0,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[item("f", TVAL_FOOD, 35, count=5)],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"

        self.assertTrue(policy._recall_departure_ready(snap))
        self.assertTrue(policy._fundraising_departure_ready(snap))

    def test_queued_digger_withdrawal_blocks_departure_without_home_route(self):
        start = Position(10, 10)
        entrance = Position(10, 30)
        snap = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {
                start: grid(10, 10),
                entrance: grid(
                    10, 30, entrance=True,
                    entrance_dungeon_id=DUNGEON_YEEK_CAVE,
                ),
            }, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=self._strict_supplies(detection=5),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._home_digger_withdraw_pending = True
        policy._home_atomic_withdraw_pending = (
            ("queued pick", TVAL_DIGGING, SV_DIGGING_PICK),
            0,
            store_item(
                "H", TVAL_DIGGING, SV_DIGGING_PICK,
                name="queued pick", is_equipment=True,
            ),
            1,
        )
        leaves = policy._town_departure_conjuncts(snap)

        self.assertFalse(leaves["digger_withdrawal_resolved"])
        self.assertFalse(leaves["home_atomic_withdraw_clear"])
        self.assertFalse(policy._town_departure_ready(snap))
        policy.last_reason = "seek-downstairs"
        self.assertIsNone(
            policy._entrance_travel_key(snap, entrance),
            "a queued take must not post the incident's entrance-travel key",
        )
        policy._home_digger_withdraw_pending = False
        policy._home_atomic_withdraw_pending = None
        policy._town_blocked_reason = None
        policy.last_reason = "seek-downstairs"
        self.assertEqual(
            policy._entrance_travel_key(snap, entrance),
            policy_module.ENTRANCE_TRAVEL_MACRO,
        )

    def test_evidence_withdraw_departure_race_posts_are_held_on_both_exits(self):
        evidence = (
            Path(__file__).parent
            / "fixtures"
            / "evidence-stairwait-selfstop-20260817-0450.jsonl"
        )
        rows = [json.loads(line) for line in evidence.read_text(encoding="utf-8").splitlines()]
        incident = [
            row for row in rows
            if 56 <= row.get("decision_sequence", -1) <= 82
        ]
        posted = [(row["reason"], row.get("key", "")) for row in incident]
        self.assertIn(("home:atomic-withdraw", "5pH\x1b"), posted)
        self.assertIn(("shop:observed-operation-uncomposable", "5"), posted)
        self.assertIn(
            ("town:travel-entrance", policy_module.ENTRANCE_TRAVEL_MACRO), posted
        )
        self.assertIn(("descend", policy_module.ENTER_DUNGEON_MACRO), posted)
        self.assertEqual(
            sum(reason == "stair:await-observation" and key == ""
                for reason, key in posted),
            12,
        )
        self.assertIn(("loop-detected", ""), posted)

        entrance = Position(10, 10)
        entrance_snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {entrance: grid(
                10, 10, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[
                *self._strict_supplies(detection=5),
                item("p", TVAL_DIGGING, 1, name="carried shovel"),
            ],
            equipment=[self._lantern()],
        )
        held = HengbotPolicy()
        held._fundraising_mode = "mine"
        held._target_dungeon_id = DUNGEON_YEEK_CAVE
        held._home_digger_withdraw_pending = True
        held_key = held.choose_key(entrance_snap)
        self.assertNotEqual(held_key, policy_module.ENTER_DUNGEON_MACRO)
        self.assertFalse(held._dungeon_entry_allowed(
            entrance_snap, via_recall=False, destination_depth=1
        ))
        self.assertEqual(held._town_blocked_reason, "home-digger-withdraw-pending")

        released = HengbotPolicy()
        released._fundraising_mode = "mine"
        released._target_dungeon_id = DUNGEON_YEEK_CAVE
        released._char_dump_done_this_visit = True
        self.assertEqual(
            released.choose_key(entrance_snap),
            policy_module.ENTER_DUNGEON_MACRO,
            released.last_reason,
        )

    def test_second_failed_digger_withdrawal_releases_to_visible_fallback(self):
        digger = store_item(
            "H", TVAL_DIGGING, SV_DIGGING_PICK,
            name="stored pick", is_equipment=True,
        )
        outside = Snapshot(
            player(45, 123, gold=1030, class_id=PLAYER_CLASS_WARRIOR),
            {Position(45, 123): replace(
                grid(45, 123), store_number=STORE_HOME
            )}, [],
            floor_key=(0, 0, 0), town_flag=True, turn=2127416,
            inventory=self._strict_supplies(detection=5),
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(digger)
        policy._digger_home_withdraw_failures = 1
        policy._home_pending_item = signature
        policy._home_digger_withdraw_pending = True
        policy._home_atomic_withdraw_pending = (signature, 0, digger, 1)
        policy._home_atomic_withdraw_posted_turn = 2127406
        policy._floor_key = outside.floor_key

        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: isolate the observation transition from unrelated town routing
        policy._decide = Mock(return_value=WAIT_KEY)
        policy.choose_key(outside)

        self.assertIsNone(policy._home_pending_item)
        self.assertFalse(policy._home_digger_withdraw_pending)
        self.assertTrue(policy._digger_buy_fallback_available(outside))
        self.assertEqual(policy.last_reason, "home:atomic-withdraw-failed")

    def test_failed_digger_withdrawal_is_not_retried_after_home_ejects_to_town(self):
        digger = store_item(
            "b", TVAL_DIGGING, 1, name="shovel", is_equipment=True
        )
        inventory = self._strict_supplies(detection=5)
        snap = Snapshot(
            player(10, 10, gold=73, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=inventory,
            store=StoreState(STORE_HOME, [digger]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        signature = policy._item_signature(digger)
        policy._home_atomic_withdraw_pending = (
            signature,
            policy._inventory_signature_count(snap, signature),
            digger,
            1,
        )
        policy._home_digger_withdraw_pending = True
        # The failed command left Home, town navigation ran, and this is a new
        # entry.  Replaying the item letter here created the live town loop.
        policy._last_snapshot_was_store = False

        outside = replace(snap, store=None)
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: failed digger-withdrawal suppression is isolated from the downstream town decision
        policy._decide = Mock(return_value=WAIT_KEY)
        key = policy.choose_key(outside)

        self.assertFalse(key.startswith(BUY_KEY))
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertEqual(policy.last_reason, "home:atomic-withdraw-failed")

    def test_mining_restock_wait_names_missing_digging_tool_and_feeds_cycle_watch(self):
        snap = Snapshot(
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
        policy._floor_key = snap.floor_key
        policy._fundraising_mode = "prepare"
        policy._town_store_attempted[STORE_GENERAL] = snap.turn

        self.assertIsNone(
            policy._retry_after_store_restock(snap, (STORE_GENERAL,))
        )
        self.assertEqual(policy._town_special_key(snap), RESTOCK_WAIT_MACRO)
        self.assertEqual(
            policy.last_reason,
            "town:wait-restock:general:digging-tool",
        )

        policy._observe(snap)
        self.assertEqual(policy._town_no_progress_count, 1)
        self.assertFalse(policy._town_cycle_pending)

    def test_pending_home_digger_is_additional_mining_walk_in_conjunct(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
            town_flag=True, inventory=[],
        )
        for mode in ("mine", "scavenge"):
            with self.subTest(mode=mode):
                policy = HengbotPolicy()
                policy._target_dungeon_id = DUNGEON_YEEK_CAVE
                policy._fundraising_mode = mode
                policy._home_digger_withdraw_pending = True
                self.assertFalse(policy._dungeon_entry_allowed(
                    snap, via_recall=False, destination_depth=1
                ))
                self.assertEqual(
                    policy._town_blocked_reason, "home-digger-withdraw-pending"
                )

    def test_mining_fast_exit_does_not_preempt_idle_consumable_disposal(self):
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
            store=StoreState(
                STORE_HOME, [], stock_num=0, page_top=0, page_size=52
            ),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._home_disposal_pass = True
        pol._home_disposal_pending = (("missing", TVAL_FOOD, 1), "destroy")
        pol._town_errand_plan = TownErrandPlan([STORE_HOME])

        outside = replace(snap, store=None)
        pol.choose_key(outside)
        self.assertNotEqual(pol.last_reason, "home:leave-with-mining-supplies")
        self.assertNotIn(STORE_HOME, pol._town_store_attempted)
        self.assertEqual(pol._town_errand_plan.index, 0)
        self.assertTrue(pol._home_disposal_pass)

    def test_mining_fast_exit_does_not_preempt_pending_equipment_catalog(self):
        stored_weapon = store_item(
            "a", TVAL_SWORD, 1, name="stored sword", is_equipment=True
        )
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
            store=StoreState(STORE_HOME, [stored_weapon], stock_num=1, page_top=0, page_size=52),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._equipment_catalog.observe_home_page(
            [stored_weapon], allow_wrap=False
        )

        outside = replace(snap, store=None)
        pol.choose_key(outside)
        self.assertNotEqual(pol.last_reason, "home:leave-with-mining-supplies")
        self.assertTrue(pol._equipment_catalog.items)

    def test_scavenge_mode_promotes_to_mine_when_home_tool_is_recovered(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, 4, name="pick"),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "scavenge"

        pol._town_special_key(snap)
        self.assertEqual(pol._fundraising_mode, "mine")

    def test_suppressed_store_routes_do_not_freeze_ready_scavenge_mode(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(detection=5),
                item("z", TVAL_DIGGING, 4, name="pick"),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "scavenge"
        pol._town_restock_suppressed = True

        with patch.object(
            pol, "_fundraising_departure_ready", return_value=True
        ):
            pol._town_special_key(snap)

        self.assertEqual(pol._fundraising_mode, "mine")
        self.assertTrue(pol._town_restock_suppressed)

    def test_alchemist_buys_low_value_potions(self):
        for sval in (28, 34):
            with self.subTest(sval=sval):
                snap = Snapshot(
                    player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[item("a", TVAL_POTION, sval)],
                    store=StoreState(store_type=STORE_ALCHEMIST, items=[]),
                )
                policy = HengbotPolicy()

                self.assertEqual(_public_shop_inner(self, policy, snap), "{a@0\r")
                self.assertEqual(policy.last_reason, "shop:batch-inscribe")

    def test_alchemist_buys_sleep_and_detect_invisible(self):
        for tval, sval in ((TVAL_POTION, 11), (TVAL_SCROLL, 30)):
            with self.subTest(tval=tval, sval=sval):
                snap = Snapshot(
                    player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[item("a", tval, sval)],
                    store=StoreState(store_type=STORE_ALCHEMIST, items=[]),
                )
                policy = HengbotPolicy()

                self.assertEqual(_public_shop_inner(self, policy, snap), "{a@0\r")
                self.assertEqual(policy.last_reason, "shop:batch-inscribe")

    def test_depth_two_requirements_are_reported(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[item("f", TVAL_FOOD, 35, count=5)],
            equipment=[item(
                "light", TVAL_LITE, SV_LITE_TORCH, fuel=5000,
                is_equipment=True,
            )],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 1

        requirements = policy.procurement_requirements(snap)
        names = {entry["item"] for entry in requirements}

        self.assertIn("Brass lantern", names)
        self.assertIn("Flasks of oil", names)
        self.assertIn("Teleport scrolls", names)
        self.assertIn("Cure Critical Wounds potions", names)

    def test_town_restart_restores_depth_two_plan_for_developed_character(self):
        snap = Snapshot(
            player(10, 10, level=6, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
        )
        policy = HengbotPolicy()

        policy.prime(snap)

        names = {entry["item"] for entry in policy.procurement_requirements(snap)}
        self.assertIn("Brass lantern", names)
        self.assertIn("Teleport scrolls", names)
        self.assertIn("Cure Critical Wounds potions", names)

    def test_depth_two_departure_requires_all_new_supplies(self):
        policy = HengbotPolicy()
        set_completed_equipment_optimization(policy)
        policy._deepest_level = 1
        base = dict(
            player=player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids={Position(10, 10): grid(10, 10)},
            visible_monsters=[],
            floor_key=(0, 0, 0),
            equipment=[self._lantern()],
        )
        missing_healing = Snapshot(
            inventory=self._strict_supplies(recall=3, teleport=3), **base
        )
        complete = Snapshot(
            inventory=self._strict_supplies(recall=3, teleport=4, critical=4),
            **base,
        )

        self.assertFalse(policy._town_departure_ready(missing_healing))
        self.assertTrue(policy._town_departure_ready(complete))

    def test_depth_ten_procurement_requires_ten_cure_critical_potions(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(
                recall=3, teleport=15, critical=9
            ),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 9

        critical = next(
            requirement
            for requirement in policy.procurement_requirements(snap)
            if requirement["item"] == "Cure Critical Wounds potions"
        )

        self.assertEqual(critical["target"], 10)
        self.assertEqual(critical["missing"], 1)

    def test_one_short_cure_supply_departs_only_after_both_shops_exhausted(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=self._strict_supplies(
                recall=10, teleport=15, critical=9
            ),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 18

        self.assertFalse(policy._cure_critical_ready(snap))
        policy._town_store_attempted[STORE_TEMPLE] = snap.turn
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        self.assertTrue(policy._cure_critical_ready(snap))

        eight = replace(
            snap,
            inventory=self._strict_supplies(
                recall=10, teleport=15, critical=8
            ),
        )
        self.assertFalse(policy._cure_critical_ready(eight))

    def test_depth_ten_returns_at_one_cure_critical_but_not_two(self):
        def dungeon_snapshot(critical):
            return Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)},
                [],
                floor_key=(4, 10, 0),
                inventory=self._strict_supplies(
                    recall=4, teleport=15, critical=critical
                ),
                equipment=[self._lantern()],
            )

        policy = HengbotPolicy()
        self.assertFalse(policy._should_start_town_return(dungeon_snapshot(2)))
        self.assertTrue(policy._should_start_town_return(dungeon_snapshot(1)))
        self.assertEqual(policy._last_return_trigger, "cure-low")

    def test_ninth_floor_uses_deep_cure_return_reserve_for_next_depth(self):
        def floor_nine(critical):
            return Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10, downstairs=True)},
                [],
                floor_key=(4, 9, 0),
                inventory=self._strict_supplies(
                    recall=4, teleport=15, critical=critical
                ),
                equipment=[self._lantern()],
            )

        policy = HengbotPolicy()
        self.assertTrue(policy._next_depth_supply_shortage(floor_nine(1)))
        self.assertFalse(policy._next_depth_supply_shortage(floor_nine(2)))

    def test_buys_cure_critical_for_depth_two(self):
        snap = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=self._strict_supplies(recall=1, teleport=4),
            equipment=[self._lantern()],
            store=StoreState(
                store_type=STORE_TEMPLE,
                items=[
                    store_item(
                        "a",
                        TVAL_POTION,
                        SV_POTION_CURE_CRITICAL,
                        price=25,
                        count=20,
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        policy._deepest_level = 1

        self.assertEqual(_public_shop_inner(self, policy, snap), "pa3\r\r")
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")

    def test_does_not_descend_to_two_without_required_supplies(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertTrue(policy._descent_is_blocked(snap))

        key = policy.choose_key(snap)

        self.assertNotEqual(key, ">")
        self.assertTrue(policy.last_reason.startswith("return:"))

        ready = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=3, teleport=3, critical=3),
            equipment=[self._lantern()],
        )
        self.assertFalse(HengbotPolicy()._descent_is_blocked(ready))

    def test_yeek_four_five_recall_descends_without_next_depth_return(self):
        inventory = self._strict_supplies(recall=5, teleport=15, critical=10)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(4, 4, 0),
            inventory=inventory,
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), policy_module.DOWN_STAIRS_KEY)
        self.assertFalse(policy._returning_to_town)
        self.assertNotEqual(policy._last_return_trigger, "next-depth-kit")
        self.assertFalse(policy._descent_is_blocked(snap))

    def test_yeek_four_cure_shortage_still_latches_next_depth_return(self):
        inventory = self._strict_supplies(recall=5, teleport=15, critical=1)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 4, 0),
            inventory=inventory,
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertTrue(policy._next_depth_supply_shortage(snap))
        with patch.object(policy, "_ledger_return_shortages", return_value=[]):
            self.assertNotEqual(
                policy.choose_key(snap), policy_module.DOWN_STAIRS_KEY
            )
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, "next-depth-kit")

    def test_buys_full_treasure_detection_shortage_from_a_large_stack(self):
        snap = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            store=StoreState(
                store_type=STORE_ALCHEMIST,
                items=[
                    store_item(
                        "a",
                        TVAL_SCROLL,
                        SV_SCROLL_DETECT_TREASURE,
                        price=25,
                        count=42,
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertEqual(_public_shop_inner(self, policy, snap), "pa10\r\r")
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")

    def test_procurement_requirements_show_only_current_shortages(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=self._strict_supplies(recall=3, detection=42),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        requirements = policy.procurement_requirements(snap)

        self.assertEqual([entry["item"] for entry in requirements], ["Digging tool"])

    def test_procurement_requires_second_digger_known_in_home(self):
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy._equipment_catalog.observe_home_page(
            [
                store_item(
                    "a",
                    TVAL_DIGGING,
                    SV_DIGGING_SHOVEL,
                    name="stored shovel",
                    is_equipment=True,
                )
            ]
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[
                *self._strict_supplies(recall=1, detection=42),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            equipment=[self._lantern()],
        )

        requirements = policy.procurement_requirements(snap)

        self.assertIn(
            {"item": "Digging tool", "current": 1, "target": 2, "missing": 1},
            requirements,
        )

    def test_second_digger_remains_a_procurement_goal_but_one_can_mine(self):
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[
                *self._strict_supplies(recall=1, detection=42),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            equipment=[self._lantern()],
        )

        requirements = policy.procurement_requirements(snap)

        self.assertIn(
            {"item": "Digging tool", "current": 1, "target": 2, "missing": 1},
            requirements,
        )
        with patch.object(policy, "_fundraising_food_ready", return_value=True):
            self.assertTrue(policy._fundraising_supplies_ready(snap))

    def test_duplicate_unidentified_home_gear_is_not_skipped_by_a_processed_twin(self):
        # Two identical unidentified weapons share a (name, tval, sval) signature.
        # After one is processed, the other must still be found for processing —
        # the signature collision must not strand it in the Home.
        pol = HengbotPolicy()
        first = store_item(
            "a", 23, 5, name="a Long Sword", is_equipment=True, aware=False, known=False
        )
        twin = store_item(
            "b", 23, 5, name="a Long Sword", is_equipment=True, aware=False, known=False
        )
        pol._processed_home_items.add(pol._item_signature(first))
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[first, twin]),
        )
        self.assertIsNotNone(pol._find_home_candidate(snap))

    def test_processed_identified_home_gear_is_still_skipped(self):
        # An already-identified item that was processed must NOT be re-offered
        # (only unidentified duplicates bypass the processed set).
        pol = HengbotPolicy()
        known_gear = store_item(
            "a", 23, 5, name="a Long Sword (+1,+2)", is_equipment=True, aware=True, known=True
        )
        pol._processed_home_items.add(pol._item_signature(known_gear))
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[known_gear]),
        )
        self.assertIsNone(pol._find_home_candidate(snap))

    def test_home_ammunition_is_not_withdrawn_as_equipment(self):
        arrows = store_item(
            "a",
            TVAL_ARROW,
            1,
            name="Arrows",
            count=20,
            is_equipment=True,
            aware=True,
            known=False,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[arrows]),
        )

        self.assertIsNone(HengbotPolicy()._find_home_candidate(snap))

    def test_home_inferior_weapon_pull_stops_at_the_batch_reserve(self):
        # An unguarded pull filled the pack to zero free every Home visit; a full
        # pack then blocks town departure. The pull must leave the batch reserve.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        # Fill the pack with sellable spare weapons down to exactly the reserve.
        # High-grade-equipped inferior spares are excluded from the deposit pass,
        # so they are inert filler here — only the withdraw guard can stop a pull.
        filler = [
            item(f"p{i}", 23, 1, name="a Dagger", is_equipment=True, known=True)
            for i in range(PACK_CAPACITY - HOME_BATCH_RESERVED_SLOTS)
        ]
        spare = store_item(
            "a", 23, 1, name="a Dagger", is_equipment=True, aware=True, known=True,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=filler,
            equipment=[ego],
            store=StoreState(store_type=STORE_HOME, items=[spare]),
        )

        pol.choose_key(snap)

        self.assertNotEqual(pol.last_reason, "home:withdraw-inferior-weapon")

    def test_home_does_not_withdraw_weapon_that_would_restore_overweight(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        actor = replace(player(10, 10), stat_index=(0, 0, 0, 0, 0, 0))
        empty = Snapshot(
            actor, {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0),
        )
        limit = pol._inventory_weight_limit(empty)
        self.assertIsNotNone(limit)
        protected_weight = replace(
            item("a", 10, 1, name="wanted remains", is_bounty=True),
            weight=limit - 50,
        )
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        spare = replace(
            store_item(
                "a", 23, 16, name="a Broad Sword",
                is_equipment=True, aware=True, known=True,
            ),
            weight=100,
        )
        snap = Snapshot(
            actor,
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0),
            inventory=[protected_weight], equipment=[ego],
            store=StoreState(store_type=STORE_HOME, items=[spare]),
        )

        pol.choose_key(snap)

        self.assertNotEqual(pol.last_reason, "home:withdraw-inferior-weapon")

    def test_home_does_not_withdraw_a_spare_the_smith_refused(self):
        # A spare already refused by the Weapon Smith (unsellable) must not be
        # pulled again: no sale can clear it, so it would clog the pack.
        pol = HengbotPolicy()
        # Same town stay so the fresh-visit reset does not clear _unsellable_items.
        pol._floor_key = (0, 0, 0)
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        refused = store_item(
            "a", 23, 1, name="a Dagger", is_equipment=True, aware=True, known=True,
        )
        pol._unsellable_items.add((refused.name, refused.tval, refused.sval))
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[ego],
            store=StoreState(store_type=STORE_HOME, items=[refused]),
        )

        pol.choose_key(snap)

        self.assertNotEqual(pol.last_reason, "home:withdraw-inferior-weapon")

    def test_unsellable_inferior_weapon_can_shelve_back_home(self):
        # Fallback: once the smith has refused a spare, it is no longer held for
        # sale, so it must become depositable again — otherwise a pack of refused
        # spares blocks town departure forever.
        pol = HengbotPolicy()
        set_known_target(pol)
        ego = item(
            "main_hand", 23, 1, name="an Ego Blade", is_equipment=True,
            is_ego=True, known=True,
        )
        refused = item(
            "b", 23, 1, name="a Dagger", is_equipment=True, known=True,
        )
        pol._unsellable_items.add((refused.name, refused.tval, refused.sval))
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[refused],
            equipment=[ego],
        )

        self.assertEqual(pol._find_home_deposit(snap), refused)

    def test_prime_restores_fundraising_from_multiple_detection_scrolls(self):
        snap = Snapshot(
            player(
                10,
                10,
                class_id=PLAYER_CLASS_WARRIOR,
                gold=FUNDRAISING_START_GOLD - 1,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[
                item(
                    "t",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=4,
                )
            ],
        )
        pol = HengbotPolicy()
        pol.prime(snap)
        self.assertEqual(pol._fundraising_mode, "prepare")

    def test_prime_does_not_restore_fundraising_when_gold_is_sufficient(self):
        snap = Snapshot(
            player(
                10,
                10,
                level=6,
                gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[
                item(
                    "t",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=4,
                )
            ],
        )
        pol = HengbotPolicy()
        pol.prime(snap)
        self.assertIsNone(pol._fundraising_mode)

    def test_fundraising_uses_a_lower_restart_threshold(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_GOLD_TARGET - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
        )
        policy = HengbotPolicy()
        self.assertFalse(policy._start_fundraising(snap))

        poor = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            snap.grids,
            [],
        )
        self.assertTrue(policy._start_fundraising(poor))

    def test_repeated_fundraising_start_preserves_store_attempt_latch(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD - 1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
        )
        policy = HengbotPolicy()
        self.assertTrue(policy._start_fundraising(snap))
        policy._town_store_attempted[STORE_HOME] = 123

        self.assertTrue(policy._start_fundraising(snap))

        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._town_store_attempted[STORE_HOME], 123)

    def test_low_gold_identification_defer_still_starts_fundraising(self):
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
        policy._identification_need = "full"
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(
            store_type=STORE_ALCHEMIST, items=[]
        )
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
            policy._effective_town_id(snap), snap.turn
        )
        policy._conquest_target = lambda snapshot: 1

        policy._town_terminal_transitions(snap)

        self.assertIsNone(policy._identification_need)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_spare_equipment_shape_matches_disposal_for_its_shared_domain(self):
        samples = (
            item("a", 23, 5, is_equipment=True, aware=False, name="armour"),
            item(
                "b", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                is_equipment=True, aware=False, name="shovel",
            ),
        )

        for candidate in samples:
            with self.subTest(item=candidate.name):
                snap = Snapshot(
                    player(10, 10),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    floor_key=(0, 0, 0),
                    inventory=[candidate],
                    store=StoreState(store_type=STORE_HOME, items=[]),
                )
                pol = HengbotPolicy()
                set_known_target(pol)

                shared = pol._spare_equipment_deposit_shape(candidate)
                disposal = pol._home_deposit_candidate(candidate, snap)
                self.assertEqual(shared, disposal)

    def test_prime_binds_to_home_disposals_unknown_nonlight_equipment_class(self):
        samples = (
            item("a", 23, 5, is_equipment=True, aware=False, name="armour"),
            item(
                "b", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                is_equipment=True, aware=False, name="shovel",
            ),
        )

        for candidate in samples:
            with self.subTest(item=candidate.name):
                snap = Snapshot(
                    player(10, 10),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    floor_key=(0, 0, 0),
                    inventory=[candidate],
                    store=StoreState(store_type=STORE_HOME, items=[]),
                )
                pol = HengbotPolicy()

                pol.prime(snap)

                self.assertEqual(
                    pol._home_pending_item,
                    pol._item_signature(candidate),
                    "prime must recognize unknown non-light equipment, including diggers",
                )

        torch = item(
            "c", TVAL_LITE, SV_LITE_TORCH, is_equipment=True,
            aware=False, name="torch",
        )
        arrows = item("d", TVAL_ARROW, 1, name="arrows")
        launcher = item(
            "e", TVAL_BOW, SV_BOW_SHORT, is_equipment=True, name="bow",
        )
        torch_snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[torch, arrows],
            equipment=[launcher],
            store=StoreState(store_type=STORE_HOME, items=[]),
        )
        potion = item(
            "f", TVAL_POTION, SV_POTION_SLEEP, aware=False,
            name="unidentified potion",
        )
        potion_snap = replace(torch_snap, inventory=[potion])
        pol = HengbotPolicy()
        pol._deepest_level = 25

        # Lights and consumables belong to other disposal branches; their real
        # snapshot classifications deliberately do not define prime's class.
        self.assertFalse(pol._spare_equipment_deposit_shape(torch))
        self.assertTrue(pol._home_deposit_candidate(torch, torch_snap))
        self.assertFalse(pol._spare_equipment_deposit_shape(potion))
        self.assertTrue(pol._home_deposit_candidate(potion, potion_snap))

    def test_prime_reconstruction_only_sets_pending_withdrawal_fields(self):
        withdrawn = item(
            "e", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="a Shovel",
            is_equipment=True, aware=False, pseudo_feeling="average",
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[withdrawn],
            store=StoreState(store_type=STORE_HOME, items=[]),
        )
        pol = HengbotPolicy()

        pol.prime(snap)

        self.assertEqual(pol._home_pending_item, pol._item_signature(withdrawn))
        self.assertEqual(pol._home_pending_slot, withdrawn.slot)
        self.assertIsNone(pol._last_sell_sig)
        self.assertIsNone(pol._pending_disposal_item)
        self.assertIsNone(pol._pending_disposal_slot)

    def test_prime_does_not_rebuild_known_equipment_as_a_trial_batch(self):
        gloves = item(
            "a", 31, 1, name="known gloves", known=True,
            fully_known=True, is_equipment=True,
        )
        boots = item(
            "b", 30, 1, name="known boots", known=True,
            fully_known=True, is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            inventory=[gloves, boots],
        )
        pol = HengbotPolicy()

        pol.prime(snap)

        self.assertEqual(pol._home_pending_batch, [])
        self.assertTrue(pol._home_candidate_waiting)

    def test_recall_targets_follow_the_confirmed_depth_table(self):
        policy = HengbotPolicy()
        requirement = {
            1: 3, 4: 3, 5: 6, 10: 6, 11: 6,
            15: 6, 16: 9, 20: 9, 21: 10,
        }
        retreat = {1: 1, 5: 1, 6: 3, 10: 3, 20: 3}
        self.assertEqual(
            {depth: policy._recall_target(depth) for depth in requirement},
            requirement,
        )
        self.assertEqual(
            {
                depth: policy._recall_shortage_retreat_threshold(depth)
                for depth in retreat
            },
            retreat,
        )

        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 20, 0),
        )
        for mode in ("mine", "scavenge"):
            with self.subTest(mode=mode):
                policy._fundraising_mode = mode
                status = policy._supply_ledger(snapshot, 20)["recall"]
                self.assertEqual(status.required_return, 0)
                self.assertEqual(status.required_departure, 0)
                self.assertFalse(policy._recall_departure_shortage(snapshot))

    def test_strict_town_routine_visits_temple_for_missing_recall(self):
        grids = {
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
                store_number=STORE_TEMPLE,
            ),
        }
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_START_GOLD,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            grids,
            [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        # Keep this recall-routing test focused: an outstanding Home catalog
        # scan now correctly preempts the circuit under the Home-first rule.
        policy._equipment_catalog.home_scan_complete = True
        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "shop:approach")

    def test_buys_recall_scroll_until_target_is_met(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
            store=StoreState(
                store_type=STORE_TEMPLE,
                items=[
                    store_item(
                        "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=20
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        self.assertEqual(_public_shop_inner(self, policy, snap), "pa\r")
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")

    def test_unbuyable_recall_does_not_bounce_shallow_dive(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        ledger = policy._supply_ledger(snap, snap.dungeon_level)
        self.assertFalse(policy._ledger_return_shortages(ledger, snap.dungeon_level))
        self.assertFalse(policy._should_start_town_return(snap))

    def test_missing_recall_still_triggers_deep_return(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, RECALL_MIN_DEPTH, 0),
            inventory=self._strict_supplies(
                recall=0, teleport=15, critical=10
            ),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        policy.choose_key(snap)
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, "recall-shortage")

    def test_returns_when_recall_stock_falls_below_depth_target(self):
        grids = {Position(10, 10): grid(10, 10, upstairs=True)}
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=self._strict_supplies(recall=3),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_fifth_floor_and_deeper_return_at_three_recall_scrolls(self):
        def dungeon_snapshot(recall):
            return Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)},
                [],
                floor_key=(DUNGEON_YEEK_CAVE, 11, 0),
                inventory=self._strict_supplies(
                    recall=recall, teleport=15, critical=10
                ),
                equipment=[self._lantern()],
            )

        policy = HengbotPolicy()
        self.assertFalse(policy._should_start_town_return(dungeon_snapshot(4)))
        self.assertFalse(policy._should_start_town_return(dungeon_snapshot(3)))

    def test_deeper_stairs_do_not_restore_the_old_depth_based_recall_threshold(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 10, 0),
            inventory=self._strict_supplies(
                recall=4, teleport=15, critical=10
            ),
            equipment=[self._lantern()],
        )

        self.assertFalse(HengbotPolicy()._next_depth_supply_shortage(snap))

    def test_waits_when_required_recall_is_unavailable(self):
        snap = Snapshot(
            player(10, 10, gold=8000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=100,
            inventory=self._strict_supplies(recall=3),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._deepest_level = RECALL_MIN_DEPTH
        policy.prime(snap)
        policy._town_store_attempted.update({STORE_TEMPLE: 0, STORE_ALCHEMIST: 0})

        self.assertEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)
        self.assertIn(STORE_TEMPLE, policy._town_store_attempted)

    def test_zero_recall_scrolls_waits_for_restock_instead_of_town_wander(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=8000,
                class_id=PLAYER_CLASS_WARRIOR,
                abilities=frozenset(
                    {"resist_pois", "resist_cold", "resist_elec", "resist_acid"}
                ),
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=100,
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
            recall_dungeon_id=14,
            recall_depth=29,
            entered_dungeon_ids=(1, 14),
        )
        policy = HengbotPolicy()
        policy._deepest_level = 31
        policy._target_dungeon_id = 14
        policy._char_dump_done_this_visit = True
        policy._town_store_attempted.update(
            {STORE_TEMPLE: 0, STORE_ALCHEMIST: 0}
        )
        policy._food_ready = lambda _snapshot: True
        policy._light_ready = lambda _snapshot: True
        policy._teleport_ready = lambda _snapshot: True
        policy._cure_critical_ready = lambda _snapshot: True
        policy._identify_staff_ready = lambda _snapshot: True
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._equipment_departure_ready = lambda _snapshot: True
        policy._find_home_deposit = lambda _snapshot: None

        self.assertFalse(policy._recall_departure_ready(snap))
        self.assertEqual(policy._town_special_key(snap), RESTOCK_WAIT_MACRO)
        self.assertTrue(policy.last_reason.startswith("town:wait-restock:"))

    def test_released_store_terminal_requires_all_suppliers_unroutable(self):
        snap = Snapshot(
            player(10, 10, gold=8000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], turn=1100,
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()], width=20, height=20,
        )
        policy = HengbotPolicy(town_map=None)
        policy._town_store_attempted.update(
            {STORE_TEMPLE: 0, STORE_ALCHEMIST: 0}
        )
        policy._retry_after_store_restock(snap, (STORE_TEMPLE, STORE_ALCHEMIST))
        expiry = replace(snap, turn=2100)
        self.assertEqual(
            policy._retry_after_store_restock(
                expiry, (STORE_TEMPLE, STORE_ALCHEMIST)
            ),
            STORE_TEMPLE,
        )

        self.assertEqual(
            policy._released_restock_store_key(
                expiry, (STORE_TEMPLE, STORE_ALCHEMIST)
            ),
            WAIT_KEY,
        )
        self.assertEqual(
            policy._town_blocked_reason,
            "restock-store-unreachable",
        )

    def test_departs_instead_of_waiting_when_teleport_is_unavailable(self):
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

        self.assertNotEqual(policy.choose_key(snap), RESTOCK_WAIT_MACRO)
        self.assertIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_available_star_identify_keeps_home_latch_until_item_is_processed(self):
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
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=300,
            inventory=[*self._strict_supplies(recall=7), target, star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(target)
        policy._home_pending_item = signature
        policy._home_pending_slot = "a"
        policy._identification_candidate = signature
        policy._identification_need = "full"
        policy._town_store_attempted[STORE_ALCHEMIST] = 0

        key = policy._town_item_processing_key(snap)

        self.assertIsNotNone(key)
        self.assertEqual(policy.last_reason, "identify:full")
        self.assertEqual(policy._home_pending_item, signature)
        self.assertEqual(policy._home_pending_slot, "a")
        self.assertNotIn(signature, policy._deferred_home_items)

    def test_requires_five_free_slots_before_normal_departure(self):
        inventory = self._strict_supplies(recall=1)
        inventory.extend(
            item(chr(ord("a") + i), TVAL_FOOD, 35, name=f"extra-{i}")
            for i in range(16)
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=inventory,
            equipment=[self._lantern()],
        )
        self.assertFalse(HengbotPolicy()._town_departure_ready(snap))

    def obsolete_mining_reads_one_detection_scroll_then_sweeps_visible_gold(self):
        grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(10, 11): grid(10, 11, passable=False, rubble=True, gold=True),
            Position(20, 20): grid(20, 20, passable=False, gold=True),
            Position(21, 20): grid(21, 20, passable=False, gold=True),
            Position(22, 20): grid(22, 20, passable=False, gold=True),
            Position(23, 20): grid(23, 20, passable=False, gold=True),
        }
        tool = item(
            "main_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=5),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        self.assertEqual(policy.choose_key(snap), "rd", policy.last_reason)
        self.assertEqual(policy.last_reason, "fundraise:detect-treasure")
        self.assertEqual(policy.choose_key(snap), "T6")
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")

    def obsolete_mining_prefers_orthogonal_gold_over_blocked_diagonal_gold(self):
        grids = {
            Position(10, 10): grid(10, 10),
            # Insert the blocked diagonal first to reproduce the live dict order.
            Position(11, 9): grid(11, 9, passable=False, gold=True),
            Position(11, 10): grid(11, 10, passable=False, gold=True),
            Position(10, 9): grid(10, 9, passable=False),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=5),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        self.assertEqual(policy.choose_key(snap), "T2")
        self.assertEqual(policy.last_reason, "fundraise:mine-treasure")

    def test_mining_leaves_when_equipped_torch_is_empty(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10, upstairs=True),
                Position(10, 11): grid(10, 11, passable=False, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                *self._strict_supplies(recall=0, detection=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500),
            ],
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                item("light", TVAL_LITE, SV_LITE_TORCH, fuel=0, is_equipment=True),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")

    def test_mining_wields_carried_torch_instead_of_bouncing_to_town(self):
        torch = item(
            "t", TVAL_LITE, SV_LITE_TORCH, known=True, fuel=2500, count=10
        )
        lantern = item(
            "light",
            TVAL_LITE,
            SV_LITE_LANTERN,
            known=False,
            fuel=7500,
            is_equipment=True,
        )
        digger = item(
            "d", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): replace(
                    grid(10, 10, upstairs=True), lit=True
                )
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item(
                    "s",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=4,
                ),
                torch,
                digger,
            ],
            equipment=[lantern],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertEqual(policy.choose_key(snap), "wt", policy.last_reason)
        self.assertEqual(policy.last_reason, "fundraise:wield-light")

        after_wield = replace(
            snap,
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item(
                    "s",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=4,
                ),
                replace(lantern, slot="u", is_equipment=False),
                digger,
            ],
            equipment=[replace(torch, slot="light", count=1, is_equipment=True)],
        )
        self.assertTrue(policy._expedition_light_ready(after_wield))
        self.assertNotEqual(policy.choose_key(after_wield), "<")
        self.assertNotEqual(policy.last_reason, "fundraise:ascend")

    def test_mining_returns_immediately_when_gold_target_is_reached(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=3),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")

    def obsolete_mining_collects_detected_treasure_after_gold_target_is_reached(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {
                Position(10, 10): grid(10, 10, upstairs=True),
                Position(10, 11): grid(10, 11, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=3),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "T6")
        self.assertEqual(policy.last_reason, "fundraise:mine-treasure")

    def test_completed_shallow_partial_campaign_restores_full_set_target(self):
        snap = self._shallow_partial_mining_snapshot(0)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = 3
        policy._mining_runs_completed = 3

        self.assertIsNone(policy._town_special_key(snap))
        self.assertIsNone(policy._planned_mining_runs)
        self.assertEqual(
            policy._mining_detection_scroll_target(snap), MINING_RUNS_PER_SET
        )

    def test_deep_eligible_fundraising_walks_into_l1_instead_of_recalling(self):
        inventory = self._strict_supplies(
            recall=13,
            detection=MINING_RUNS_PER_SET,
            teleport=15,
            critical=10,
        )
        inventory.append(
            item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)
        )
        snap = Snapshot(
            player(
                10,
                10,
                hp=413,
                max_hp=413,
                level=24,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            equipment=[
                item("main_hand", 23, 1, is_equipment=True),
                self._lantern(),
            ],
            recall_depth=13,
            recall_dungeon_id=DUNGEON_ANGBAND,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._char_dump_done_this_visit = True

        self.assertIsNone(policy._town_special_key(snap))
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertFalse(hasattr(policy, "_deep_fundraising_active"))
        self.assertNotEqual(policy.last_reason, "town:recall-to-yeek-cave-mining")

    def test_blocked_fundraising_steps_off_store_instead_of_reentering(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_ALCHEMIST
                ),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._fundraising_departure_ready = lambda snapshot: False
        policy._floor_t = {(10, 10), (10, 11)}

        self.assertEqual(policy._town_special_key(snap), "6")
        self.assertEqual(
            policy.last_reason, "fundraise:departure-blocked-step-off"
        )

    def test_completed_town_plan_immediately_downgrades_blocked_fundraising(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_MAGIC, STORE_ALCHEMIST], index=3
        )

        with patch.object(
            policy, "_fundraising_departure_ready", return_value=False
        ):
            self.assertIsNone(policy._town_special_key(snap))

        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.assertTrue(policy._town_restock_suppressed)
        self.assertEqual(
            policy.last_reason, "fundraise:fallback-exhausted-plan"
        )

    def test_full_pack_fundraising_block_falls_through_to_disposal(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                item(str(index), TVAL_POTION, index)
                for index in range(PACK_CAPACITY)
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        policy._fundraising_departure_ready = lambda snapshot: False

        self.assertIsNone(policy._town_special_key(snap))

    def test_idle_disposal_pass_does_not_enter_home_for_no_operation(self):
        entrance = Position(10, 11)
        snap = Snapshot(
            player(10, 10, gold=FUNDRAISING_START_GOLD, class_id=1),
            {
                Position(10, 10): grid(10, 10),
                entrance: replace(grid(10, 11), store_number=STORE_HOME),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )
        policy = HengbotPolicy()
        policy._home_disposal_pass = True

        decisions = []
        for _ in range(6):
            key = policy.choose_key(snap)
            decisions.append((key, policy.last_reason))

        self.assertFalse(any(reason.startswith("shop:") for _, reason in decisions))
        self.assertNotIn("6", [key for key, _ in decisions])
        self.assertTrue(policy._home_disposal_pass)

    def test_shallow_warrior_mining_throws_before_generic_combat(self):
        monster = hostile(1, 10, 12, distance=2)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, monster=True),
            },
            [monster],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=5000)
            ],
            equipment=[
                item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._breeder_breakthrough_floor = snap.floor_key
        snap = replace(
            snap,
            visible_monsters=[
                replace(monster, can_multiply=True, max_melee_damage=0)
            ],
        )

        with patch.object(policy, "_darkness_recovery_key", return_value=None):
            self.assertEqual(
                (policy.choose_key(snap), policy.last_reason),
                ("vt6", "ranged:throw-torch"),
            )

    def test_mining_swarm_throws_then_restores_weapon_on_contact(self):
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=5000)
        sword = item("s", TVAL_SWORD, 1, name="Broad Sword", is_equipment=True)
        shovel = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="shovel", is_equipment=True,
        )
        approaching = hostile(1, 10, 12, distance=2, can_multiply=True)
        base = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, monster=True),
            },
            [approaching],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[torch, sword],
            equipment=[shovel],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._build_grid_index(base)

        self.assertEqual(
            policy._melee_swarm_combat_key(base, [approaching], []), "vt6"
        )
        self.assertEqual(policy.last_reason, "ranged:throw-torch")

        contact = replace(
            base,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
            },
            visible_monsters=[
                replace(approaching, position=Position(10, 11), distance=1)
            ],
        )
        policy._build_grid_index(contact)
        for _ in range(policy_module.MINING_COMBAT_CONTACT_LIMIT - 1):
            policy._update_mining_combat_streaks(
                contact, contact.visible_monsters, contact.visible_monsters
            )
            self.assertIsNone(
                policy._melee_swarm_combat_key(
                    contact, contact.visible_monsters, contact.visible_monsters
                )
            )
        policy._update_mining_combat_streaks(
            contact, contact.visible_monsters, contact.visible_monsters
        )
        self.assertEqual(
            policy._melee_swarm_combat_key(
                contact, contact.visible_monsters, contact.visible_monsters
            ),
            "wsn",
        )
        self.assertEqual(policy.last_reason, "melee:restore-weapon")

    def test_choose_key_orders_throw_restore_then_choke_melee(self):
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=5000)
        sword = item(
            "s", TVAL_SWORD, 1, name="Broad Sword", is_equipment=True,
            damage_dice_num=2, damage_dice_sides=5,
        )
        shovel = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="shovel", is_equipment=True,
        )
        room = {
            Position(y, x): grid(y, x, lit=True)
            for y in range(8, 13)
            for x in range(8, 14)
        }
        approaching_monsters = [
            hostile(
                index, y, x, distance=Position(10, 10).distance_to(Position(y, x)),
                can_multiply=True, max_melee_damage=1,
            )
            for index, (y, x) in enumerate(
                [(10, 12), (9, 12), (11, 12), (10, 13)], 1
            )
        ]
        approaching_grids = dict(room)
        for monster in approaching_monsters:
            approaching_grids[monster.position] = replace(
                approaching_grids[monster.position], has_monster=True
            )
        approaching = Snapshot(
            player(10, 10, hp=172, max_hp=20, level=10,
                   class_id=PLAYER_CLASS_WARRIOR),
            approaching_grids,
            approaching_monsters,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[torch, sword],
            equipment=[shovel, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        probe = HengbotPolicy()
        probe._fundraising_mode = "mine"
        probe._build_grid_index(approaching)
        self.assertEqual(
            probe._melee_swarm_combat_key(
                approaching, approaching_monsters, []
            ),
            "vt6",
        )
        opening_key = policy.choose_key(approaching)
        self.assertEqual(
            (opening_key, policy.last_reason),
            ("vt6", "ranged:throw-torch"),
        )

        contact_monsters = [
            replace(monster, distance=1)
            for monster in approaching_monsters
        ]
        contact_monsters[0] = replace(
            contact_monsters[0], position=Position(10, 11)
        )
        contact_grids = dict(room)
        for monster in contact_monsters:
            contact_grids[monster.position] = replace(
                contact_grids[monster.position], has_monster=True
            )
        contact = replace(
            approaching,
            grids=contact_grids,
            visible_monsters=contact_monsters,
        )
        for decision in range(1, policy_module.MINING_COMBAT_CONTACT_LIMIT):
            policy.choose_key(contact)
            self.assertNotEqual(policy.last_reason, "melee:restore-weapon")
            self.assertEqual(policy._mining_combat_contact_streak, decision)
        self.assertEqual(policy.choose_key(contact), "wsn")
        self.assertEqual(policy.last_reason, "melee:restore-weapon")

        choke_grids = dict(room)
        for pos in (
            Position(9, 9), Position(11, 9),
            Position(9, 10), Position(11, 10),
        ):
            choke_grids[pos] = grid(pos.y, pos.x, passable=False)
        choke_monsters = [
            replace(contact_monsters[0], position=Position(10, 8), distance=1),
            replace(contact_monsters[1], position=Position(9, 11), distance=2),
            replace(contact_monsters[2], position=Position(10, 11), distance=2),
            replace(contact_monsters[3], position=Position(11, 11), distance=2),
        ]
        for monster in choke_monsters:
            choke_grids[monster.position] = replace(
                choke_grids[monster.position], has_monster=True
            )
        armed = replace(
            approaching,
            player=replace(approaching.player, position=Position(10, 9),
                           main_hand_blows=2, main_hand_to_d=5),
            grids=choke_grids,
            visible_monsters=choke_monsters,
            inventory=[torch, shovel],
            equipment=[replace(sword, slot="main_hand")],
        )
        policy._recent.clear()
        policy._osc_positions.clear()
        policy._last_position = None
        armed_probe = HengbotPolicy()
        armed_probe._build_grid_index(armed)
        self.assertIsNotNone(
            armed_probe._melee_swarm_combat_key(
                armed, armed.visible_monsters, [armed.visible_monsters[0]]
            )
        )
        self.assertEqual(armed_probe.last_reason, "melee:choke")
        policy.choose_key(armed)
        self.assertEqual(policy.last_reason, "melee:choke")

    def test_choose_key_combat_restore_releases_incident_dual_wield_digger(self):
        sword = item(
            "s",
            TVAL_SWORD,
            16,
            name="Broad Sword",
            is_equipment=True,
            damage_dice_num=2,
            damage_dice_sides=5,
        )
        shovel = item(
            "sub_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            name="Shovel",
            is_equipment=True,
            pval=1,
        )
        positions = [
            (10, 11), (9, 11), (11, 11), (10, 12),
            (9, 12), (11, 12), (8, 11), (12, 11),
            (8, 12), (12, 12), (9, 13), (11, 13),
        ]
        breeders = [
            hostile(
                index,
                y,
                x,
                distance=1 if index == 1 else 2,
                race_id=31,
                can_multiply=True,
                max_melee_damage=0,
            )
            for index, (y, x) in enumerate(positions, 1)
        ]
        grids = {
            Position(y, x): grid(
                y,
                x,
                monster=any(
                    monster.position == Position(y, x) for monster in breeders
                ),
            )
            for y in range(8, 13)
            for x in range(9, 14)
        }
        mining = Snapshot(
            player(
                10,
                10,
                hp=189,
                max_hp=20,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            grids,
            breeders,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[sword],
            equipment=[
                replace(shovel, slot="main_hand"),
                replace(shovel, slot="sub_hand", name="Pick"),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = mining.floor_key
        policy._breeder_breakthrough_floor = mining.floor_key
        policy._mining_combat_contact_streak = (
            policy_module.MINING_COMBAT_CONTACT_LIMIT - 1
        )

        # The extermination-impossible latch strategically suppresses these
        # weak breeders, but mining combat must still count their real contact.
        self.assertEqual(policy._strategic_hostiles(mining), [])

        self.assertEqual(policy.choose_key(mining), "wsa")
        self.assertEqual(policy.last_reason, "melee:restore-weapon")

        main_restored = replace(
            mining,
            inventory=[replace(shovel, slot="m")],
            equipment=[
                replace(sword, slot="main_hand"),
                shovel,
            ],
        )
        self.assertEqual(policy.choose_key(main_restored), "tb")
        self.assertEqual(policy.last_reason, "melee:restore-weapon")

        combat_ready = replace(
            main_restored,
            inventory=[
                replace(shovel, slot="m"),
                replace(shovel, slot="n", name="Pick"),
            ],
            equipment=[replace(sword, slot="main_hand")],
        )
        self.assertFalse(
            any(item.is_digging_tool for item in combat_ready.equipment)
        )
        policy.choose_key(combat_ready)
        self.assertTrue(policy.last_reason.startswith("fundraise:"))

    def test_mining_breakthrough_restores_before_leaving_hostile_floor(self):
        sword = item(
            "s", TVAL_SWORD, 1, name="Broad Sword", is_equipment=True
        )
        breeder = hostile(
            1, 10, 11, distance=1, can_multiply=True, max_melee_damage=0
        )
        mining = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
            },
            [breeder],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[sword],
            equipment=[
                item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                item(
                    "sub_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._breeder_breakthrough_floor = mining.floor_key
        policy._mining_combat_contact_streak = (
            policy_module.MINING_COMBAT_CONTACT_LIMIT
        )

        with patch.object(
            policy, "_finish_mining_floor", return_value="FINISH"
        ) as finish:
            self.assertEqual(policy._fundraising_key(mining, []), "wsa")
            finish.assert_not_called()

            armed = replace(
                mining,
                inventory=[],
                equipment=[replace(sword, slot="main_hand")],
            )
            self.assertEqual(policy._fundraising_key(armed, []), "FINISH")
            finish.assert_called_once_with(armed)

    def test_five_kill_growth_judgement_ends_mining_through_floor_exit(self):
        breeders = [
            hostile(
                index, 10, 11 + index, distance=1 + index,
                can_multiply=True, max_melee_damage=0,
            )
            for index in range(2)
        ]
        mining = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            breeders,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
        policy._breeder_engagement_floor = mining.floor_key
        policy._breeder_kills = 5
        policy._breeder_engagement_start_count = 1

        policy._update_combat_outcome(mining)

        self.assertEqual(policy._breeder_breakthrough_floor, mining.floor_key)
        policy._floor_key = mining.floor_key
        with patch.object(
            policy, "_finish_mining_floor", return_value="FINISH"
        ) as finish:
            with patch.object(
                policy, "_darkness_recovery_key", return_value=None
            ):
                self.assertEqual(policy.choose_key(mining), "FINISH")
            finish.assert_called_once_with(mining)

    def test_sleeping_mouse_does_not_trigger_mining_weapon_restore(self):
        sword = item("s", TVAL_SWORD, 1, name="Broad Sword", is_equipment=True)
        shovel = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            name="shovel", is_equipment=True,
        )
        mouse = hostile(1, 10, 11, distance=1, asleep=True)
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
            },
            [mouse],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[sword],
            equipment=[shovel, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_combat_contact_streak = DIGGER_WIELD_LIMIT

        self.assertIsNone(
            policy._fundraising_combat_equipment_key(snapshot, [mouse])
        )

    def test_mining_eats_when_hungry_before_continuing(self):
        tool = item(
            "main_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, food=1500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=5),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        self.assertEqual(policy.choose_key(snap), "Ef")
        # The R1 survival gate now owns hunger-eating and runs before the
        # fundraising steps; the action (eat, same slot, same turn) is
        # unchanged, only the reason label moved.
        self.assertEqual(policy.last_reason, "survival:eat")

    def test_mining_collects_visible_item_after_detected_treasure_is_gone(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, objects=1),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-loot")

    def test_mining_collects_nearest_unsafe_drop_before_adjacent_vein(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, passable=False, gold=True),
                Position(11, 10): grid(11, 10),
                Position(12, 10): grid(12, 10, objects=1, unsafe=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "2")
        self.assertEqual(policy.last_reason, "fundraise:seek-loot")

    def test_mining_keeps_tracking_unsafe_loot_when_it_leaves_view(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        inventory = self._strict_supplies(recall=0, detection=1)
        equipment = [tool, self._lantern()]
        floor_key = (DUNGEON_YEEK_CAVE, 1, 0)
        first = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(11, 10): grid(11, 10),
                Position(12, 10): grid(12, 10, objects=1, unsafe=True),
            },
            [],
            floor_key=floor_key,
            inventory=inventory,
            equipment=equipment,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = floor_key

        self.assertEqual(policy.choose_key(first), "2")
        self.assertEqual(policy._loot_target, Position(12, 10))

        hidden = Snapshot(
            player(11, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10, upstairs=True),
                Position(11, 10): grid(11, 10),
                # A FOUND floor object remains in the JSON map while outside
                # direct view; CAVE_UNSAFE only records trap-detection coverage.
                Position(12, 10): grid(12, 10, objects=1, unsafe=True),
            },
            [],
            floor_key=floor_key,
            inventory=inventory,
            equipment=equipment,
        )

        self.assertEqual(policy.choose_key(hidden), "2")
        self.assertEqual(policy.last_reason, "fundraise:seek-loot")
        self.assertEqual(policy._loot_target, Position(12, 10))

    def test_scavenging_collects_visible_item_before_exploring(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, objects=1),
                Position(11, 10): grid(11, 10),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-loot")

    def test_scavenging_returns_at_gold_target_despite_stale_treasure_memory(self):
        snap = Snapshot(
            player(
                10,
                10,
                gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        policy._known_treasure = {Position(12, 12)}

        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")

    def test_town_restores_combat_weapon_after_mining(self):
        tool = item(
            "main_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            name="shovel",
            is_equipment=True,
        )
        sword = item("s", 23, 1, name="sword", is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[sword, *self._strict_supplies(recall=1, detection=4)],
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._normal_weapon_name = "sword"
        # n answers the "Dual wielding?" prompt (sub hand free) with "replace
        # the main hand", swapping the digger out instead of dual-wielding.
        self.assertEqual(policy.choose_key(snap), "wsn")
        self.assertEqual(policy.last_reason, "town:restore-combat-weapon")

    def test_fundraising_descends_from_matching_static_entrance(self):
        entrance = Position(10, 10)
        town_map = TownMap(
            name="test",
            width=20,
            height=20,
            walkable=frozenset({entrance}),
            entrance=entrance,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {entrance: grid(
                10, 10, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )},
            [],
            floor_key=(0, 0, 0),
            width=20,
            height=20,
            town_flag=True,
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy(town_map=town_map)
        set_completed_equipment_optimization(policy)
        policy._fundraising_mode = "scavenge"

        self.assertEqual(policy.choose_key(snap), ">\ry")
        self.assertEqual(policy.last_reason, "descend")

    def test_incomplete_optimizer_blocks_normal_direct_entrance(self):
        entrance = Position(10, 10)
        town_map = TownMap(
            name="test",
            width=20,
            height=20,
            walkable=frozenset({entrance}),
            entrance=entrance,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {entrance: grid(
                10, 10, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )},
            [],
            floor_key=(0, 0, 0),
            width=20,
            height=20,
            town_flag=True,
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy(town_map=town_map)
        policy._fundraising_mode = None
        policy._prepare_equipment_optimization = lambda _snapshot: SimpleNamespace(
            ready=False,
            result=None,
            transaction=None,
            blockers=("home-scan-incomplete",),
        )

        self.assertNotEqual(
            policy.choose_key(snap), policy_module.ENTER_DUNGEON_MACRO
        )

        self.assertFalse(policy._town_departure_ready(snap))
        self.assertFalse(
            policy._dungeon_entry_allowed(
                snap, via_recall=False, destination_depth=1
            )
        )
        self.assertIn("equipment_departure_ready", policy._departure_block["failed"])

    def test_fresh_level_one_warrior_enters_shallow_dungeon_exactly(self):
        entrance = Position(10, 10)
        town_map = TownMap(
            name="test",
            width=20,
            height=20,
            walkable=frozenset({entrance}),
            entrance=entrance,
        )
        snap = Snapshot(
            player(
                entrance.y,
                entrance.x,
                level=1,
                class_id=PLAYER_CLASS_WARRIOR,
                abilities=frozenset(),
            ),
            {
                entrance: grid(
                    entrance.y,
                    entrance.x,
                    entrance=True,
                    entrance_dungeon_id=DUNGEON_YEEK_CAVE,
                )
            },
            [],
            floor_key=(0, 0, 0),
            width=20,
            height=20,
            town_flag=True,
            inventory=self._strict_supplies(recall=10),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy(town_map=town_map)
        set_completed_equipment_optimization(policy)
        policy._town_special_key = lambda _snapshot: None
        policy._recall_departure_shortage = lambda _snapshot: False

        self.assertEqual(
            policy.choose_key(snap), policy_module.ENTER_DUNGEON_MACRO,
            (policy.last_reason, policy.departure_block_state()),
        )
        self.assertEqual(policy.last_reason, "descend")

    def test_town_restores_a_weapon_even_when_the_name_is_unknown(self):
        # A fresh bot process that inherited an already-wielded pickaxe has no recorded
        # combat-weapon name, but must STILL swap the pickaxe out for a real weapon before
        # diving/recalling — otherwise it recalls on a feeble digger. Falls back to any
        # melee weapon in the pack.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        sword = item("s", 23, 1, name="long sword", is_equipment=True)  # TV_SWORD
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[sword, *self._strict_supplies(recall=1, detection=4)],
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._normal_weapon_name = None  # unknown after a restart
        self.assertEqual(policy._town_restore_weapon_key(snap), "wsn")
        self.assertEqual(policy.last_reason, "town:restore-combat-weapon")

    def test_town_restore_after_restart_skips_unknown_and_cursed_weapons(self):
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
        safe = item(
            "s", 23, 2, name="known safe sword", is_equipment=True, known=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[unknown, cursed, safe],
            equipment=[tool, self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._normal_weapon_name = None

        self.assertEqual(policy._town_restore_weapon_key(snap), "wsn")
        self.assertEqual(policy.last_reason, "town:restore-combat-weapon")

    def test_town_restore_weapon_is_a_noop_without_any_combat_weapon(self):
        # Digger equipped but no real weapon anywhere to restore: don't hang the town
        # routine WAITing for one that will never appear — return None and carry on.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        armour = item("b", 36, 2, name="soft leather armour", is_equipment=True)  # not a weapon
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[armour, *self._strict_supplies(recall=1, detection=4)],
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._normal_weapon_name = None
        self.assertIsNone(policy._town_restore_weapon_key(snap))

    def test_pre_recall_check_is_not_ready_on_a_pickaxe(self):
        # THE essential fix: a mining pickaxe in the main hand is not a combat weapon, so
        # the pre-recall check must report "not ready" (blocking the dive) until re-armed.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=list(self._strict_supplies(recall=1)),
            equipment=[tool, self._lantern()],
        )
        self.assertFalse(HengbotPolicy()._combat_weapon_ready(snap))

    def test_pre_recall_check_is_ready_with_a_real_weapon(self):
        sword = item("main_hand", 23, 1, name="long sword", is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[sword, self._lantern()],
        )
        self.assertTrue(HengbotPolicy()._combat_weapon_ready(snap))

    def test_pre_recall_check_is_ready_with_main_hand_weapon_and_sub_hand_digger(self):
        sword = item(
            "main_hand", TVAL_SWORD, 1, name="long sword", is_equipment=True
        )
        shovel = item(
            "sub_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            name="shovel",
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[sword, shovel, self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._weapon_block_streak = 0

        self.assertTrue(policy._combat_weapon_ready(snap))

    def test_main_hand_weapon_with_sub_hand_digger_needs_no_home_combat_weapon(self):
        sword = item(
            "main_hand", TVAL_SWORD, 1, name="long sword", is_equipment=True
        )
        shovel = item(
            "sub_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            name="shovel",
            is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[sword, shovel, self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._weapon_block_streak = 0

        needs = policy._enumerate_town_needs(snap)

        self.assertFalse(
            any(
                need.store_type == STORE_HOME and need.category == "combat-weapon"
                for need in needs
            )
        )

    def test_pre_recall_check_rejects_actionably_cursed_weapon(self):
        cursed = item(
            "main_hand", 21, 5, name="cursed mace", is_equipment=True,
            known=True, is_cursed=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[cursed, self._lantern()],
            town_flag=True,
        )

        self.assertFalse(HengbotPolicy()._combat_weapon_ready(snap))

    def test_pre_recall_check_rejects_no_teleport_weapon(self):
        weapon = item(
            "main_hand",
            23,
            1,
            name="artifact scimitar",
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            equipment=[weapon, self._lantern()],
        )

        self.assertFalse(HengbotPolicy()._combat_weapon_ready(snap))

    def test_cancels_active_recall_before_disposing_no_teleport_weapon(self):
        weapon = item(
            "main_hand",
            23,
            1,
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        snap = Snapshot(
            player(10, 10, word_recall=10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=2),
            equipment=[weapon, self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rr")
        self.assertEqual(policy.last_reason, "town:cancel-unsafe-recall")

    def test_cancels_recall_when_safe_target_changes_during_countdown(self):
        recall = item(
            "r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
            count=2, known=True, name="Word of Recall",
        )
        snap = Snapshot(
            player(10, 10, word_recall=10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_ANGBAND, 3),
            recall_dungeon_id=DUNGEON_ANGBAND,
        )
        policy = HengbotPolicy()
        policy._pending_recall_dungeon_id = DUNGEON_ANGBAND
        policy._target_dungeon_id = 3

        with patch.object(policy, "_recall_destination_safe", return_value=True):
            self.assertEqual(policy._town_cancel_unsafe_recall_key(snap), "rr")

        self.assertEqual(
            policy.last_reason,
            "town:cancel-wrong-recall-destination",
        )
        self.assertIsNone(policy._pending_recall_dungeon_id)

    def test_town_replaces_no_teleport_weapon_from_pack(self):
        blocked = item(
            "main_hand",
            23,
            1,
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        safe = item("s", 23, 2, name="safe scimitar", is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[safe],
            equipment=[blocked, self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._town_restore_weapon_key(snap), "ta")
        self.assertEqual(policy.last_reason, "town:remove-no-teleport-weapon")

        removed = replace(
            snap,
            inventory=[safe, replace(blocked, slot="b")],
            equipment=[self._lantern()],
        )
        self.assertEqual(policy._town_restore_weapon_key(removed), "ws")
        self.assertEqual(policy.last_reason, "town:replace-no-teleport-weapon")

    def test_town_resumes_no_teleport_rearm_after_bot_restart(self):
        blocked = item(
            "b",
            23,
            1,
            is_equipment=True,
            is_artifact=True,
            fully_known=True,
            known_flags=frozenset({TR_NO_TELE}),
        )
        safe = item("s", 23, 2, name="safe scimitar", is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[blocked, safe],
            equipment=[self._lantern()],
        )
        restarted_policy = HengbotPolicy()

        self.assertEqual(restarted_policy._town_restore_weapon_key(snap), "ws")
        self.assertEqual(
            restarted_policy.last_reason, "town:replace-no-teleport-weapon"
        )

    def test_no_teleport_rearm_pending_survives_refused_wield(self):
        safe = item("s", 23, 2, name="safe scimitar", is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[safe],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._no_teleport_rearm_pending = True
        with patch.object(policy, "_wield_weapon_key", return_value=None):
            self.assertIsNone(policy._town_restore_weapon_key(snap))
        self.assertTrue(policy._no_teleport_rearm_pending)

        generated = policy._town_restore_weapon_key(snap)
        self.assertEqual(generated, "ws")
        policy.refuse_key_posting("town:replace-no-teleport-weapon", generated)
        self.assertTrue(policy._no_teleport_rearm_pending)
        retry = policy._town_restore_weapon_key(snap)
        self.assertEqual(retry, "ws")
        self.assertTrue(policy.confirm_key_posted(retry))
        self.assertFalse(policy._no_teleport_rearm_pending)

    def test_pre_recall_check_backstop_dives_when_no_weapon_can_be_found(self):
        # If we own no combat weapon at all, the check must eventually give up and dive on
        # the pickaxe rather than hang the bot in town forever.
        from hengbot.policy import WEAPON_BLOCK_LIMIT

        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, name="shovel", is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[tool, self._lantern()],
        )
        pol = HengbotPolicy()
        pol._weapon_block_streak = WEAPON_BLOCK_LIMIT
        self.assertTrue(pol._combat_weapon_ready(snap))

    def test_scavenging_ignores_downstairs_and_returns_upstairs(self):
        grids = {
            Position(10, 10): GridState(
                position=Position(10, 10),
                known=True,
                passable=True,
                wall=False,
                has_monster=False,
                has_down_stairs=True,
                has_up_stairs=True,
                unsafe=False,
            )
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")

    def test_scavenging_keeps_moving_when_upstairs_route_is_unknown(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        for y in range(9, 12):
            for x in range(9, 13):
                pos = Position(y, x)
                if pos not in grids:
                    grids[pos] = grid(y, x, passable=False)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:scavenge")

    def test_scavenging_confined_cycle_switches_to_floor_exit(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(14, 19)
            for x in range(48, 53)
        }
        snap = Snapshot(
            player(17, 50, gold=55, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=80,
            height=30,
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        policy._floor_key = snap.floor_key
        cycle = (
            Position(15, 50),
            Position(15, 51),
            Position(16, 51),
            Position(17, 50),
            Position(17, 49),
            Position(16, 49),
        )
        for _ in range(4):
            policy._recent.extend(cycle)
        for pos in cycle:
            policy._visit_counts[pos] = 4

        key = policy.choose_key(snap)

        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(policy._explore_path, [])

    def test_scavenging_returns_for_a_missing_tool_when_veins_are_known(self):
        grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(10, 11): grid(10, 11, gold=True),
        }
        snap = Snapshot(
            player(10, 10, gold=55, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"

        self.assertEqual(policy.choose_key(snap), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")
        self.assertTrue(policy._returning_to_town)

    def test_scavenging_crosses_open_door_instead_of_retargeting_old_door(self):
        grids = {
            Position(29, 5): grid(29, 5, open_door=True),
            Position(30, 5): grid(30, 5),
            Position(31, 5): grid(31, 5, open_door=True),
            Position(32, 5): grid(32, 5),
        }
        for y in range(28, 34):
            for x in range(4, 7):
                pos = Position(y, x)
                if pos not in grids:
                    grids[pos] = grid(y, x, passable=False)
        snap = Snapshot(
            player(31, 5, gold=55, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=40,
            height=40,
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"
        policy._floor_key = snap.floor_key
        for pos in (Position(29, 5), Position(30, 5), Position(31, 5)):
            policy._visit_counts[pos] = 1

        self.assertEqual(policy.choose_key(snap), "2")
        self.assertEqual(policy.last_reason, "fundraise:scavenge")
        self.assertIn((31, 5), policy._floor_t)
        self.assertNotIn((31, 5), policy._door_t)

    def test_mining_ignores_a_nearby_weakling_and_keeps_seeking_treasure(self):
        grids = {
            Position(10, 8): grid(10, 8, gold=True),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, upstairs=True, monster=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [hostile(1, 10, 12, distance=2)],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_does_not_ignore_a_visible_strong_multiplier(self):
        grids = {
            Position(10, 8): grid(10, 8, gold=True),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, upstairs=True, monster=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [
                hostile(
                    1, 10, 12, distance=2, can_multiply=True,
                    max_melee_damage=5,
                )
            ],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        self.assertEqual(policy.choose_key(snap), "4")
        self.assertEqual(policy.last_reason, "threat:reposition")

    def _latched_mining_breeder(self):
        grids = {
            Position(10, 8): grid(10, 8, gold=True),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, monster=True),
        }
        breeder = hostile(
            1, 10, 12, distance=2, can_multiply=True,
            max_melee_damage=9,
        )
        snapshot = Snapshot(
            player(
                10,
                10,
                hp=177,
                max_hp=177,
                level=7,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            grids,
            [breeder],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item(
                    "main_hand",
                    TVAL_DIGGING,
                    SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snapshot.floor_key
        policy._fruitless_disengage_floor = snapshot.floor_key
        policy._breeder_engagement_floor = snapshot.floor_key
        policy._breeder_engagement_score = (
            policy_module.BREEDER_CONTAINMENT_WINDOW
        )
        policy._returning_to_town = True
        return policy, snapshot

    def test_survivable_mining_breeder_preempts_latched_disengage(self):
        policy, snapshot = self._latched_mining_breeder()

        with patch.object(
            policy,
            "threat_prediction",
            return_value={"operational_total": 1.0},
        ):
            self.assertEqual(policy.choose_key(snapshot), "6")

        self.assertEqual(policy.last_reason, "fundraise:eliminate-multiplier")

    def test_unproductive_perceived_breeder_engagement_advances_score(self):
        policy, snapshot = self._latched_mining_breeder()
        policy._breeder_engagement_score = 0

        for turn in range(1, 4):
            policy._update_combat_outcome(replace(snapshot, turn=turn))

        self.assertEqual(policy._breeder_engagement_score, 3)

    def test_breeder_engagement_score_decays_in_genuine_absence(self):
        policy, snapshot = self._latched_mining_breeder()
        policy._breeder_engagement_score = 9
        absent = replace(snapshot, visible_monsters=[], detected_monsters=[])

        policy._update_combat_outcome(absent)

        self.assertEqual(policy._breeder_engagement_score, 5)

    def test_mining_preemption_stops_after_live_engagement_bound(self):
        policy, snapshot = self._latched_mining_breeder()
        policy._breeder_engagement_score = (
            policy_module.BREEDER_CONTAINMENT_WINDOW
            + policy_module.FRUITLESS_DISENGAGE_LIMIT
            - 1
        )
        policy._update_combat_outcome(snapshot)

        with patch.object(
            policy,
            "threat_prediction",
            return_value={"operational_total": 1.0},
        ):
            key = policy._fruitless_disengage_key(
                snapshot, snapshot.visible_monsters
            )

        self.assertIsNotNone(key)
        self.assertEqual(policy._escape_state.owner, "disengage")

    def test_cleared_mining_breeders_release_latched_disengage(self):
        policy, fighting = self._latched_mining_breeder()
        policy._breeder_engagement_score = (
            policy_module.BREEDER_CONTAINMENT_WINDOW - 1
        )
        snapshot = replace(
            fighting,
            grids={
                position: replace(cell, has_monster=False, monster_index=0)
                for position, cell in fighting.grids.items()
            },
            visible_monsters=[],
        )

        self.assertEqual(policy.choose_key(snapshot), "4")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_dangerous_mining_breeder_keeps_latched_disengage(self):
        policy, snapshot = self._latched_mining_breeder()

        with patch.object(
            policy,
            "threat_prediction",
            return_value={"operational_total": 90.0},
        ):
            policy.choose_key(snapshot)

        self.assertTrue(policy.last_reason.startswith("combat:disengage-"))

    def test_mining_breeder_stalemate_falls_back_after_existing_budget(self):
        policy, snapshot = self._latched_mining_breeder()
        policy._breeder_engagement_score = (
            policy_module.BREEDER_CONTAINMENT_WINDOW
            + policy_module.FRUITLESS_DISENGAGE_LIMIT
        )

        with patch.object(
            policy,
            "threat_prediction",
            return_value={"operational_total": 1.0},
        ):
            policy.choose_key(snapshot)

        self.assertTrue(policy.last_reason.startswith("combat:disengage-"))

    def test_breeder_impossible_latch_survives_transient_vanish(self):
        policy, visible = self._latched_mining_breeder()
        policy._floor_key = visible.floor_key
        policy._breeder_breakthrough_floor = visible.floor_key

        # Pre-fix, the strong-breeder breakthrough with no remembered
        # up-stairs returned the absorbing upstairs-not-found WAIT, which the
        # no-wait ladder rewrote into burning an escape scroll.  Since user
        # decision D replaced that WAIT with frontier routing, the same board
        # walks toward undiscovered terrain and keeps the scroll.
        first_key = policy.choose_key(visible)
        self.assertEqual(
            (first_key, policy.last_reason),
            ("4", "breeder-breakthrough:seek-frontier"),
        )

        hidden = replace(
            visible,
            player=replace(visible.player, position=Position(10, 9)),
            grids={
                position: replace(cell, has_monster=False, monster_index=0)
                for position, cell in visible.grids.items()
            },
            visible_monsters=[],
        )
        second_key = policy.choose_key(hidden)

        self.assertNotEqual(second_key, WAIT_KEY)
        self.assertEqual(
            policy._breeder_breakthrough_floor, visible.floor_key
        )
        self.assertNotEqual(
            policy.last_reason,
            "fundraise:eliminate-multiplier-last-seen",
        )

    def test_declared_walkout_releases_after_breeder_score_decays(self):
        policy, visible = self._latched_mining_breeder()
        policy._breeder_engagement_score = (
            policy_module.BREEDER_CONTAINMENT_WINDOW
            + policy_module.FRUITLESS_DISENGAGE_LIMIT
        )
        policy.choose_key(visible)
        self.assertEqual(policy._escape_state.owner, "disengage")

        hidden = replace(
            visible,
            grids={
                position: replace(cell, has_monster=False, monster_index=0)
                for position, cell in visible.grids.items()
            },
            visible_monsters=[],
        )
        while (
            policy._breeder_engagement_score
            >= policy_module.BREEDER_CONTAINMENT_WINDOW
        ):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            policy.choose_key(hidden)
            if (
                policy._breeder_engagement_score
                >= policy_module.BREEDER_CONTAINMENT_WINDOW
            ):
                self.assertTrue(policy.last_reason.startswith("combat:disengage-"))
                self.assertNotEqual(
                    policy.last_reason,
                    "fundraise:eliminate-multiplier-last-seen",
                )

        key = policy.choose_key(hidden)
        self.assertEqual(key, "4")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")
        self.assertIsNone(policy._escape_state.owner)

    def test_declared_walkout_still_melees_adjacent_blocker(self):
        policy, snapshot = self._latched_mining_breeder()
        blocker = replace(
            snapshot.visible_monsters[0],
            position=Position(10, 11),
            distance=1,
        )
        snapshot = replace(
            snapshot,
            grids={
                **snapshot.grids,
                Position(10, 11): replace(
                    snapshot.grids[Position(10, 11)],
                    has_monster=True,
                ),
                Position(10, 12): replace(
                    snapshot.grids[Position(10, 12)],
                    has_monster=False,
                    monster_index=0,
                ),
            },
            visible_monsters=[blocker],
        )
        policy._escape_state.enter("disengage", "combat:disengage-seek-upstairs")
        policy._fruitless_disengage_floor = None
        policy._breeder_engagement_score = 0
        policy._returning_to_town = False

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_mining_keeps_tracking_treasure_when_its_display_flickers(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        first_grids = {
            Position(10, 8): grid(10, 8, upstairs=True),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, gold=True),
        }
        second_grids = dict(first_grids)
        second_grids[Position(10, 13)] = grid(10, 13)
        inventory = self._strict_supplies(recall=0, detection=1)
        equipment = [tool, self._lantern()]
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = (DUNGEON_YEEK_CAVE, 1, 0)

        first = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            first_grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
            equipment=equipment,
        )
        second = Snapshot(
            player(10, 11, class_id=PLAYER_CLASS_WARRIOR),
            second_grids,
            [],
            floor_key=first.floor_key,
            inventory=inventory,
            equipment=equipment,
        )

        self.assertEqual(policy.choose_key(first), "6")
        self.assertEqual(policy.choose_key(second), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def obsolete_mining_commits_to_treasure_when_a_nearer_vein_appears(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        inventory = self._strict_supplies(recall=0, detection=1)
        equipment = [tool, self._lantern()]
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = (DUNGEON_YEEK_CAVE, 1, 0)

        first_grids = {
            Position(10, x): grid(10, x, gold=x == 14)
            for x in range(9, 15)
        }
        first = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            first_grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
            equipment=equipment,
        )
        self.assertEqual(policy.choose_key(first), "6")
        self.assertEqual(policy._treasure_target, Position(10, 14))

        second_grids = {
            Position(10, x): grid(10, x, gold=x in {9, 14})
            for x in range(9, 15)
        }
        second = Snapshot(
            player(10, 11, class_id=PLAYER_CLASS_WARRIOR),
            second_grids,
            [],
            floor_key=first.floor_key,
            inventory=inventory,
            equipment=equipment,
        )

        self.assertEqual(policy.choose_key(second), "6")
        self.assertEqual(policy._treasure_target, Position(10, 14))
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_remembers_the_route_after_it_leaves_the_current_view(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        inventory = self._strict_supplies(recall=0, detection=1)
        equipment = [tool, self._lantern()]
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = (DUNGEON_YEEK_CAVE, 1, 0)

        first = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, x): grid(10, x, gold=x == 15)
                for x in range(10, 16)
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=inventory,
            equipment=equipment,
        )
        self.assertEqual(policy.choose_key(first), "6")

        second = Snapshot(
            player(10, 11, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 11): grid(10, 11),
                Position(10, 15): grid(10, 15, gold=True),
            },
            [],
            floor_key=first.floor_key,
            inventory=inventory,
            equipment=equipment,
        )

        self.assertEqual(policy.choose_key(second), "6")
        self.assertEqual(policy._treasure_target, Position(10, 15))
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def obsolete_mining_sweeps_the_detected_area_before_chasing_veins(self):
        # Phase 1 of the two-phase design: unknown terrain inside the detected
        # radius is mapped FIRST, giving every cheap vein a walkable approach —
        # the old routine probed/tunnelled at one coordinate and left the rest.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 14): grid(10, 14, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key  # not a fresh floor: keep the centers
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)

    def test_mining_abandons_dry_floor_immediately_after_detection(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        base_grids = {
            Position(10, 10): grid(10, 10, upstairs=True),
            Position(10, 11): grid(10, 11),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            base_grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=80,
            height=80,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertTrue(policy.choose_key(snap).startswith(READ_KEY))
        detected = replace(snap, grids=dict(base_grids))
        self.assertEqual(policy.choose_key(detected), "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")
        self.assertLessEqual(policy._mining_sweep_steps, 3)

    def _post_detection_mining_decision(
        self, detected_total: int, detection_scrolls: int, remaining_runs: int
    ) -> tuple[str, HengbotPolicy]:
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        start = Position(10, 10)
        grids = {
            start: grid(start.y, start.x, upstairs=True),
            Position(10, 11): grid(10, 11),
        }
        treasures = set()
        for index in range(detected_total):
            position = Position(30, 30 + index)
            grids[position] = grid(
                position.y, position.x, passable=False, gold=True
            )
            treasures.add(position)
        snap = Snapshot(
            player(start.y, start.x, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=80,
            height=80,
            inventory=self._strict_supplies(
                recall=0, detection=detection_scrolls
            ),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_viability_pending_floor = snap.floor_key
        policy._known_treasure = treasures
        with patch.object(
            policy, "_mining_detection_scroll_target", return_value=remaining_runs
        ), patch.object(
            policy, "_mining_sweep_step", return_value=Position(10, 11)
        ):
            key = policy.choose_key(snap)
        return key, policy

    def test_mining_skips_threshold_floor_when_detection_scroll_is_spare(self):
        key, policy = self._post_detection_mining_decision(
            BARREN_FLOOR_SKIP_THRESHOLD, detection_scrolls=5, remaining_runs=4
        )

        self.assertEqual(key, "<")
        self.assertEqual(policy.last_reason, "fundraise:skip-barren-floor")

    def test_buffered_expedition_skips_first_barren_floor_after_detection(self):
        target = 4
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        start = Position(10, 10)
        base_grids = {
            start: grid(start.y, start.x, upstairs=True),
            Position(10, 11): grid(10, 11),
        }
        snap = Snapshot(
            player(start.y, start.x, class_id=PLAYER_CLASS_WARRIOR),
            base_grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=80,
            height=80,
            inventory=self._strict_supplies(
                recall=0, detection=target + DETECTION_SCROLL_BUFFER
            ),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = target

        self.assertTrue(policy.choose_key(snap).startswith(READ_KEY))
        detected_grids = dict(base_grids)
        for index in range(BARREN_FLOOR_SKIP_THRESHOLD):
            position = Position(30, 30 + index)
            detected_grids[position] = grid(
                position.y, position.x, passable=False, gold=True
            )
        detected = replace(
            snap,
            grids=detected_grids,
            inventory=self._strict_supplies(
                recall=0,
                detection=target + DETECTION_SCROLL_BUFFER - 1,
            ),
        )

        self.assertEqual(policy.choose_key(detected), "<")
        self.assertEqual(policy.last_reason, "fundraise:skip-barren-floor")

    def test_mining_keeps_rich_floor_after_initial_detection(self):
        key, policy = self._post_detection_mining_decision(
            12, detection_scrolls=5, remaining_runs=4
        )

        self.assertEqual(key, "3")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_keeps_barren_floor_without_spare_detection_scroll(self):
        key, policy = self._post_detection_mining_decision(
            5, detection_scrolls=4, remaining_runs=4
        )

        self.assertEqual(key, "3")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_mining_zero_treasure_still_leaves_without_spare_scroll(self):
        key, policy = self._post_detection_mining_decision(
            0, detection_scrolls=0, remaining_runs=4
        )

        self.assertEqual(key, "<")
        self.assertEqual(policy.last_reason, "fundraise:ascend")

    def obsolete_mining_viability_gate_preserves_rich_unreachable_sweep(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        start = Position(10, 10)
        snap = Snapshot(
            player(start.y, start.x, class_id=PLAYER_CLASS_WARRIOR),
            {start: grid(start.y, start.x), Position(10, 11): grid(10, 11)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=80,
            height=80,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        self.assertTrue(policy.choose_key(snap).startswith(READ_KEY))

        revealed = dict(snap.grids)
        for index in range(BARREN_FLOOR_SKIP_THRESHOLD + 1):
            position = Position(30, 30 + index)
            revealed[position] = grid(
                position.y, position.x, passable=False, gold=True
            )
        detected = replace(snap, grids=revealed)
        with patch.object(
            policy, "_mining_sweep_step", return_value=Position(10, 11)
        ):
            policy.choose_key(detected)
            policy.choose_key(detected)

        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertGreaterEqual(policy._mining_sweep_steps, 2)
        self.assertFalse(policy._mining_sweep_done)

    def obsolete_mining_oscillation_leaves_when_no_other_frontier_remains(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._recent.extend(
            [Position(10, 10), Position(10, 11)] * (STUCK_WINDOW // 2)
        )
        # The only frontier is the tile just left. It is blacklisted as view
        # flicker, and the existing evidence gate leaves because no unrelated
        # frontier remains.
        policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs-explore")
        self.assertTrue(policy._mining_sweep_done)
        self.assertIn(Position(10, 11), policy._mining_swept_dead_targets)
        self.assertEqual(list(policy._recent), [])

    def test_live_six_cell_random_quest_cycle_is_oscillation(self):
        policy = HengbotPolicy()
        cycle = [
            Position(3, 26),
            Position(4, 26),
            Position(3, 27),
            Position(4, 28),
            Position(5, 28),
            Position(5, 27),
        ]

        policy._recent.extend(cycle * 4)

        self.assertTrue(policy._is_oscillating())

        healthy = HengbotPolicy()
        healthy._recent.extend(Position(10, x) for x in range(24))
        self.assertFalse(healthy._is_oscillating())

    def obsolete_long_mining_sweep_does_not_spend_collection_leash(self):
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = (DUNGEON_YEEK_CAVE, 1, 0)
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_stall_turns = 7
        base = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)}
        with patch.object(policy, "_mining_sweep_step", return_value=Position(10, 11)):
            for index in range(MINING_STALL_LIMIT + 1):
                grids = dict(base)
                grids.update(
                    {Position(20 + n, 20): grid(20 + n, 20) for n in range(index)}
                )
                snap = Snapshot(
                    player(10, 10), grids, [],
                    floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=1000, height=1000,
                    inventory=self._strict_supplies(recall=0, detection=1),
                    equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
                )
                policy._build_grid_index(snap)
                policy._fundraising_key(snap, [])
                self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertEqual(policy._mining_stall_turns, 7)
        self.assertFalse(policy._mining_sweep_done)

        with patch.object(policy, "_mining_sweep_step", return_value=None), patch.object(
            policy, "_treasure_step", return_value=Position(10, 11)
        ):
            policy._fundraising_key(snap, [])
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def obsolete_mining_sweep_latches_done_only_when_frontier_is_exhausted(self):
        snap = Snapshot(
            player(0, 0), {Position(0, 0): grid(0, 0)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=1, height=1,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(0, 0))
        policy._build_grid_index(snap)
        policy._fundraising_key(snap, [])
        self.assertTrue(policy._mining_sweep_done)

    def obsolete_mining_sweep_no_progress_cutoff_latches_done(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._reset_mining_sweep_progress(snap)
        with patch.object(policy, "_mining_sweep_step", return_value=Position(10, 11)):
            for _ in range(MINING_SWEEP_NO_PROGRESS_LIMIT):
                policy._build_grid_index(snap)
                policy._fundraising_key(snap, [])
        self.assertTrue(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_steps, MINING_SWEEP_NO_PROGRESS_LIMIT)

    def test_known_terrain_approach_to_sweep_goal_is_progress(self):
        policy = HengbotPolicy()
        goal = Position(10, 50)
        policy._mining_sweep_goal = goal
        first = Snapshot(player(10, 10), {Position(10, 10): grid(10, 10)}, [])
        policy._reset_mining_sweep_progress(first)
        policy._mining_sweep_goal = goal
        for x in range(10, 41):
            snap = replace(first, player=player(10, x))
            policy._mining_sweep_goal = goal
            policy._record_mining_sweep_step(snap)
        self.assertEqual(policy._mining_sweep_steps, 31)
        self.assertFalse(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_no_progress, 0)

    def obsolete_sweep_escape_blacklists_goal_without_resetting_bounds(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, x): grid(10, x) for x in range(10, 14)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        bad, good = Position(10, 11), Position(10, 13)
        goals = [(bad, bad), (bad, bad), (good, good)]
        with patch.object(policy, "_nearest_goal_and_step", side_effect=goals):
            for _ in range(2):
                policy._recent.extend([Position(10, 10), bad] * (STUCK_WINDOW // 2))
                policy._build_grid_index(snap)
                policy._fundraising_key(snap, [])
        self.assertIn(bad, policy._mining_swept_dead_targets)
        self.assertEqual(policy._mining_sweep_goal, good)
        self.assertEqual(policy._mining_sweep_steps, 2)
        self.assertEqual(policy._mining_sweep_no_progress, 1)

    def test_sweep_frontier_predicate_excludes_blacklisted_goal(self):
        start = Position(10, 10)
        blacklisted = Position(10, 11)
        other_frontier = Position(11, 10)
        snap = Snapshot(
            player(start.y, start.x),
            {
                start: grid(start.y, start.x),
                blacklisted: grid(blacklisted.y, blacklisted.x),
                other_frontier: grid(other_frontier.y, other_frontier.x),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
        )
        policy = HengbotPolicy()
        policy._mining_detection_centers.append(start)
        policy._mining_swept_dead_targets.add(blacklisted)
        policy._build_grid_index(snap)

        self.assertTrue(policy._is_frontier(snap, snap.grids[blacklisted]))
        self.assertEqual(policy._mining_sweep_step(snap), other_frontier)
        self.assertEqual(policy._mining_sweep_goal, other_frontier)

    def obsolete_sweep_blacklists_real_junction_flicker_pair_and_retargets(self):
        a = Position(30, 119)
        b = Position(29, 120)
        c = Position(30, 121)
        good = Position(28, 121)
        grids = {
            position: grid(position.y, position.x)
            for position in (a, b, c, good)
        }
        base = Snapshot(
            player(a.y, a.x), grids, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=200, height=100,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = base.floor_key
        policy._mining_scroll_used_floor = base.floor_key
        policy._mining_detection_centers.append(a)

        # Real 06:09 shape: at A the goal is C with a first step to B; at B
        # the goal flickers back to A. The second escape must blacklist both
        # goals and select an unrelated frontier.
        goals = [(c, b), (a, a), (good, good)]
        with patch.object(policy, "_nearest_goal_and_step", side_effect=goals):
            policy._recent.extend([a, b] * (STUCK_WINDOW // 2))
            policy._build_grid_index(base)
            self.assertEqual(policy._fundraising_key(base, []), "9")
            # The replacement step is still inside A/B, so preserve the
            # oscillation evidence and reject another flickering goal on the
            # next decision instead of spending a fresh stuck window.
            self.assertTrue(policy._is_oscillating())

            at_b = replace(base, player=player(b.y, b.x))
            policy._recent.extend([a, b] * (STUCK_WINDOW // 2))
            policy._build_grid_index(at_b)
            policy._fundraising_key(at_b, [])

        self.assertTrue({a, c} <= policy._mining_swept_dead_targets)
        self.assertEqual(policy._mining_sweep_goal, good)
        self.assertLessEqual(len(policy._mining_sweep_escape_pairs), 3)
        self.assertFalse(policy._mining_sweep_done)

    def obsolete_mining_collection_waits_for_honest_sweep_completion(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, gold=True)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._recent.extend([Position(10, 10), Position(10, 9)] * (STUCK_WINDOW // 2))
        with patch.object(policy, "_mining_sweep_step", return_value=Position(10, 9)):
            policy._fundraising_key(snap, [])
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)

    def obsolete_mining_sweep_hard_cap_latches_done(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_steps = MINING_SWEEP_HARD_LIMIT - 1
        policy._mining_sweep_revealed_grids = 1
        with patch.object(policy, "_mining_sweep_step", return_value=Position(10, 11)):
            policy._build_grid_index(snap)
            policy._fundraising_key(snap, [])
        self.assertTrue(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_steps, MINING_SWEEP_HARD_LIMIT)

    def test_tapped_out_without_new_reveals_finishes_the_floor(self):
        # The live 06:09 macro-cycle: the sweep honestly latched done, phase 2
        # found no distance-1 vein, and tapped-out resumed the exact sweep that
        # had just dead-ended (nothing had been dug, nothing newly revealed) —
        # bouncing the same junction until the cli loop guard killed the bot.
        # Without map growth past the at-done high-water mark, tapped-out must
        # LEAVE, not resume.
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item(
                    "main_hand",
                    TVAL_DIGGING,
                    SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        policy._mining_grids_at_sweep_done = len(snap.grids)
        policy._build_grid_index(snap)

        key = policy._mining_tapped_out_key(snap)
        self.assertNotEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)
        self.assertTrue(policy._mining_sweep_done)
        self.assertIsNotNone(key)

    def test_tapped_out_resumes_after_digging_reveals_new_grids(self):
        # The legitimate resume: collection dug a vein and the map grew past
        # the at-done high-water mark — fresh frontiers may have been unsealed,
        # so the sweep restarts with reset counters.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item(
                    "main_hand",
                    TVAL_DIGGING,
                    SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        # done was latched when only two grids were known; the third grid is
        # the newly exposed floor from a dug vein.
        policy._mining_grids_at_sweep_done = 2
        policy._build_grid_index(snap)

        policy._mining_tapped_out_key(snap)
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_steps, 1)

    def obsolete_tapped_out_uses_revealed_high_water_after_tiles_leave_view(self):
        base_grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        base = Snapshot(
            player(10, 10),
            base_grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[
                item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True,
                ),
                self._lantern(),
            ],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = base.floor_key
        policy._mining_scroll_used_floor = base.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        policy._mining_grids_at_sweep_done = len(base_grids)

        expanded = replace(
            base,
            grids={
                **base_grids,
                Position(10, 12): grid(10, 12, gold=True),
            },
        )
        policy._fundraising_key(expanded, [])
        self.assertEqual(policy._mining_sweep_revealed_grids, 3)

        reduced = replace(base, grids=base_grids)
        policy._build_grid_index(reduced)
        policy._mining_tapped_out_key(reduced)
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)

    def obsolete_tapped_out_sweep_resume_resets_hard_cap_progress(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11)},
            [], floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snap.floor_key
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        policy._mining_sweep_steps = MINING_SWEEP_HARD_LIMIT

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)
        self.assertEqual(policy._mining_sweep_steps, 1)

    def test_mining_walks_to_a_reachable_vein_and_digs_it_from_the_floor(self):
        # Phase 2: collection is walk + dig-the-adjacent-vein only.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        grids = {Position(10, x): grid(10, x) for x in (10, 11, 12, 13)}
        grids[Position(10, 14)] = grid(
            10, 14, passable=False, gold=True, can_dig=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key

        # Fog is optimistically traversable, so an equally short diagonal is
        # valid before the route is reclassified by a later snapshot.
        self.assertEqual(policy.choose_key(snap), "9")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

        beside = replace(
            snap, player=player(10, 13, class_id=PLAYER_CLASS_WARRIOR)
        )
        digger = HengbotPolicy()
        digger._fundraising_mode = "mine"
        digger._mining_scroll_used_floor = snap.floor_key
        self.assertEqual(digger.choose_key(beside), TUNNEL_KEY + "6")
        self.assertEqual(digger.last_reason, "fundraise:dig-to-treasure")

    def test_mining_walks_to_a_diagonal_only_vein_approach_and_digs(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        treasure = Position(11, 12)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                treasure: grid(11, 12, passable=False, gold=True, can_dig=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0), width=30, height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_sweep_done = True

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

        beside = replace(
            snap, player=player(10, 11, class_id=PLAYER_CLASS_WARRIOR)
        )
        self.assertEqual(policy.choose_key(beside), TUNNEL_KEY + "3")
        self.assertEqual(policy.last_reason, "fundraise:dig-to-treasure")

    def obsolete_mining_never_tunnels_toward_a_vein_without_a_walkable_approach(self):
        # A vein with no walkable eight-direction approach is the EXPENSIVE kind the
        # user's design trades away: it must be left, not tunnelled at through
        # blank rock (the leash burn that used to strand the rest of the floor).
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        treasure = Position(12, 12)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 12): grid(10, 12),
                treasure: grid(
                    treasure.y, treasure.x, passable=False, gold=True, can_dig=True
                ),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {treasure}
        policy._treasure_target = treasure
        policy._build_grid_index(snap)

        key = policy._fundraising_key(snap, [])
        self.assertNotEqual(key, TUNNEL_KEY + "3")
        self.assertNotEqual(policy.last_reason, "fundraise:tunnel-to-treasure")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)

    def test_mining_peels_a_vein_chain_via_the_opened_floor(self):
        # Digging a vein leaves floor behind, so the vein BEHIND it becomes the
        # next distance-1 target through that opening — clusters get collected
        # without ever digging blank rock.
        back = Position(10, 13)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),  # the front vein, already dug out
            back: grid(10, 13, passable=False, gold=True, can_dig=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
        )
        policy = HengbotPolicy()
        policy._known_treasure = {back}
        policy._build_grid_index(snap)

        self.assertEqual(policy._treasure_step(snap), Position(10, 11))

    def obsolete_mining_resumes_the_sweep_when_digging_opens_new_frontiers(self):
        # Peeling a vein chain can unseal a whole pocket: with no reachable vein
        # left but fresh in-radius frontiers, sweep again instead of leaving.
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._mining_detection_centers.append(Position(10, 10))
        policy._mining_sweep_done = True
        policy._build_grid_index(snap)

        policy._fundraising_key(snap, [])
        self.assertEqual(policy.last_reason, "fundraise:sweep-explore")
        self.assertFalse(policy._mining_sweep_done)

    def test_redetection_restarts_the_sweep_and_forgives_dropped_veins(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_sweep_done = True
        policy._drop_mining_vein(Position(10, 14))

        key = policy._fundraising_key(snap, [])
        self.assertEqual(policy.last_reason, "fundraise:detect-treasure")
        self.assertTrue(key.startswith(READ_KEY))
        self.assertFalse(policy._mining_sweep_done)
        self.assertEqual(policy._mining_dropped_veins, set())

    def test_mined_vein_counts_as_collected_when_its_gold_disappears(self):
        # Coverage telemetry: standing next to a formerly-golden grid whose gold
        # is gone means we collected it.
        vein = Position(10, 11)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10), vein: grid(10, 11)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = HengbotPolicy()
        policy._floor_key = snap.floor_key
        policy._known_treasure = {vein}
        policy.choose_key(snap)
        self.assertEqual(policy._mining_veins_collected, 1)
        self.assertNotIn(vein, policy._known_treasure)

    def test_fundraising_recalls_after_a_trap_door_drops_player_below_level_one(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "scavenge"

        self.assertNotEqual(policy._fundraising_key(snap, []), "rr")
        self.assertTrue(policy._returning_to_town)

    def obsolete_mining_abandons_a_revisited_treasure_route_before_long_leash(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(9, 10): grid(9, 10, upstairs=True),
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 14): grid(10, 14, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {Position(10, 14)}
        policy._build_grid_index(snap)

        # Detection reveals coordinates, not routes. The sweep owns terrain
        # discovery now, so with nothing to sweep and no walkable approach the
        # floor is finished at once instead of probing blindly at the vein.
        self.assertEqual(policy._fundraising_key(snap, []), "8")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)

    def test_fundraising_upstairs_route_breaks_a_two_tile_cycle(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(9, 10): grid(9, 10),
            Position(8, 10): grid(8, 10, upstairs=True),
            Position(10, 11): grid(10, 11),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._recent.extend(
            [Position(10, 10), Position(9, 10)] * (STUCK_WINDOW // 2)
        )
        policy._visit_counts[Position(9, 10)] = STUCK_WINDOW
        policy._build_grid_index(snap)

        self.assertEqual(policy._leave_fundraising_floor(snap), "6")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")

    def test_fundraising_upstairs_search_leash_recalls_from_level_one(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        policy._build_grid_index(snap)

        self.assertEqual(policy._leave_fundraising_floor(snap), "rr")
        self.assertEqual(policy.last_reason, "fundraise:recall-stuck")
        self.assertTrue(policy._returning_to_town)

    def test_fundraising_two_tile_sealed_pocket_tunnels_out(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        for y in range(9, 12):
            for x in range(9, 13):
                pos = Position(y, x)
                if pos not in grids:
                    grids[pos] = grid(y, x, passable=False, can_dig=True)
        grids[Position(10, 13)] = grid(
            10, 13, passable=False, can_dig=True, upstairs=True
        )
        snap = Snapshot(
            player(10, 11, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._recent.extend(
            [Position(10, 11), Position(10, 10)] * (STUCK_WINDOW // 2)
        )
        policy._visit_counts[Position(10, 10)] = STUCK_WINDOW
        policy._visit_counts[Position(10, 11)] = STUCK_WINDOW
        policy._search_counts[(10, 11)] = SEARCH_LIMIT
        policy._build_grid_index(snap)

        self.assertEqual(
            policy._leave_fundraising_floor(snap), TUNNEL_KEY + "6"
        )
        self.assertEqual(policy.last_reason, "fundraise:tunnel-out")

    def obsolete_mining_abandons_route_even_when_target_churn_clears_target_counter(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(9, 10): grid(9, 10, upstairs=True),
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 14): grid(10, 14, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {Position(10, 14)}
        policy._build_grid_index(snap)

        for _ in range(MINING_NAVIGATION_REVISIT_LIMIT - 1):
            policy._fundraising_key(snap, [])
            policy._mining_route_visits.clear()
            policy._treasure_target = None

        self.assertEqual(policy._fundraising_key(snap, []), "8")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)

        moved = replace(snap, player=player(10, 11, class_id=PLAYER_CLASS_WARRIOR))
        policy._build_grid_index(moved)
        self.assertEqual(policy._fundraising_key(moved, []), "7")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")

    def obsolete_mining_retargets_after_a_walkable_treasure_route_stalls(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        east = Position(10, 14)
        south = Position(14, 10)
        grids = {
            Position(10, 10): grid(10, 10),
            east: grid(east.y, east.x, gold=True),
            south: grid(south.y, south.x, gold=True),
        }
        for x in range(11, 14):
            grids[Position(10, x)] = grid(10, x)
        for y in range(11, 14):
            grids[Position(y, 10)] = grid(y, 10)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {east, south}
        policy._build_grid_index(snap)

        for _ in range(MINING_ROUTE_REVISIT_LIMIT - 1):
            self.assertEqual(policy._fundraising_key(snap, []), "6")
            self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

        self.assertEqual(policy._fundraising_key(snap, []), "2")
        self.assertNotIn(east, policy._known_treasure)
        self.assertIn(south, policy._known_treasure)
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")
        self.assertLess(policy._mining_stall_turns, MINING_STALL_LIMIT)

    def obsolete_mining_clears_shared_route_visits_when_selecting_next_treasure(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        treasure = Position(10, 14)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12),
                Position(10, 13): grid(10, 13),
                treasure: grid(treasure.y, treasure.x, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {treasure}
        policy._mining_route_visits[snap.player.position] = (
            MINING_ROUTE_REVISIT_LIMIT - 1
        )
        policy._build_grid_index(snap)

        self.assertEqual(policy._fundraising_key(snap, []), "6")
        self.assertIn(treasure, policy._known_treasure)
        self.assertEqual(policy._treasure_target, treasure)
        self.assertEqual(policy._mining_route_visits[snap.player.position], 1)
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def obsolete_mining_retargets_instead_of_leaving_floor_on_oscillation(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        east = Position(10, 14)
        south = Position(14, 10)
        grids = {
            Position(10, 10): grid(10, 10),
            east: grid(east.y, east.x, gold=True),
            south: grid(south.y, south.x, gold=True),
        }
        for x in range(11, 14):
            grids[Position(10, x)] = grid(10, x)
        for y in range(11, 14):
            grids[Position(y, 10)] = grid(y, 10)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._known_treasure = {east, south}
        policy._treasure_target = east
        policy._recent.extend(
            [Position(10, 10), Position(10, 11)] * (STUCK_WINDOW // 2)
        )
        policy._build_grid_index(snap)

        self.assertEqual(policy._fundraising_key(snap, []), "2")
        self.assertNotIn(east, policy._known_treasure)
        self.assertIn(south, policy._known_treasure)
        self.assertEqual(policy._treasure_target, south)
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def obsolete_mining_leaves_after_retargeting_repeats_in_same_local_loop(self):
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        targets = [Position(10, 14), Position(14, 10), Position(10, 6)]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(9, 10): grid(9, 10, upstairs=True),
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(11, 10): grid(11, 10),
                Position(10, 9): grid(10, 9),
                **{target: grid(target.y, target.x, gold=True) for target in targets},
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=30,
            height=30,
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = snap.floor_key
        policy._build_grid_index(snap)

        for index, target in enumerate(targets):
            policy._known_treasure = set(targets[index:])
            policy._treasure_target = target
            policy._recent.extend(
                [Position(10, 10), Position(10, 11)] * (STUCK_WINDOW // 2)
            )
            key = policy._fundraising_key(snap, [])

        self.assertEqual(key, "8")
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs")
        self.assertEqual(policy._mining_stall_turns, MINING_STALL_LIMIT)

    def test_prime_resumes_mining_when_main_weapon_is_digger_without_scrolls(self):
        shovel = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, passable=False, gold=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=1),
            equipment=[shovel, self._lantern()],
        )
        policy = HengbotPolicy()

        policy.prime(snap)

        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertEqual(policy._mining_scroll_used_floor, snap.floor_key)
        self.assertEqual(policy.choose_key(snap), "T6")
        self.assertEqual(policy.last_reason, "fundraise:dig-to-treasure")

    def test_prime_does_not_infer_interrupted_mining_from_offhand_digger(self):
        shovel = item(
            "sub_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=1),
            equipment=[shovel, self._lantern()],
        )
        policy = HengbotPolicy()

        policy.prime(snap)

        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.assertIsNone(policy._mining_scroll_used_floor)

    def test_prime_does_not_start_fundraising_for_a_carried_digger(self):
        shovel = item(
            "h", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[shovel, *self._strict_supplies(recall=1)],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        policy.prime(snap)

        self.assertIsNone(policy._fundraising_mode)

    def test_prime_restores_mining_when_digger_and_detection_scroll_are_carried(self):
        shovel = item(
            "h", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[shovel, *self._strict_supplies(recall=1, detection=1)],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()

        policy.prime(snap)

        self.assertEqual(policy._fundraising_mode, "mine")

    def test_conquest_collects_visible_drop_before_returning(self):
        grids = {Position(10, 10): grid(10, 10, upstairs=True, objects=1)}
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            inventory=self._strict_supplies(recall=10),
            equipment=[self._lantern()],
            yeek_cave_conquered=True,
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        policy = HengbotPolicy()
        before = replace(snap, yeek_cave_conquered=False, conquered_dungeon_ids=())
        policy._observe(before)
        self.assertEqual(policy.choose_key(snap), "g")
        self.assertEqual(policy.last_reason, "victory:pickup")

        empty = Snapshot(
            snap.player,
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=snap.floor_key,
            inventory=snap.inventory,
            equipment=snap.equipment,
            yeek_cave_conquered=True,
        )
        self.assertEqual(policy.choose_key(empty), "<")
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_conquest_collects_every_item_from_a_floor_pile(self):
        grids = {Position(10, 10): grid(10, 10, upstairs=True, objects=2)}
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            inventory=self._strict_supplies(recall=10),
            equipment=[self._lantern()],
            yeek_cave_conquered=True,
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )

        policy = HengbotPolicy()
        before = replace(snap, yeek_cave_conquered=False, conquered_dungeon_ids=())
        policy._observe(before)
        self.assertEqual(policy.choose_key(snap), "gaa")
        self.assertEqual(policy.last_reason, "victory:pickup")

    def test_conquest_runs_normal_town_routine_then_listens_for_rumor(self):
        supplies = self._strict_supplies(recall=3)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=0),
        }
        snap = Snapshot(
            player(10, 10, gold=2500, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            quests={14: QuestState(14, status=QUEST_STATUS_REWARDED)},
        )
        policy = HengbotPolicy()
        set_completed_equipment_optimization(policy)
        # Adjacent inn one step east: walk on, read a bounded batch, then leave
        # so exported unlock progress is checked before another batch is sent.
        self.assertEqual(policy.choose_key(snap), "6" + "u\r" * 40 + "\x1b")
        self.assertEqual(policy.last_reason, "town:rumor-batch")

    def test_rumor_batch_size_adapts_to_affordable_gold(self):
        # Only 900g on hand: 60 reads are affordable, but one send is capped at 40.
        supplies = self._strict_supplies(recall=3)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=0),
        }
        snap = Snapshot(
            player(10, 10, gold=900, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            quests={14: QuestState(14, status=QUEST_STATUS_REWARDED)},
        )
        policy = HengbotPolicy()
        set_completed_equipment_optimization(policy)
        self.assertEqual(policy.choose_key(snap), "6" + "u\r" * 40 + "\x1b")
        self.assertEqual(policy.last_reason, "town:rumor-batch")

    def test_rumor_needs_funds_when_too_poor_for_a_batch(self):
        # Below the reserve+one-read floor, mine for gold instead of a token visit.
        supplies = self._strict_supplies(recall=3)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=0),
        }
        snap = Snapshot(
            player(10, 10, gold=20, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            quests={14: QuestState(14, status=QUEST_STATUS_REWARDED)},
        )
        policy = HengbotPolicy()
        set_completed_equipment_optimization(policy)
        self.assertEqual(policy.choose_key(snap), WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:rumor-needs-funds")

    def test_walks_to_a_distant_inn_before_sending_the_rumor_macro(self):
        # The inn is two tiles east; the first step does NOT land on it, so the
        # rumor keys must NOT ride along (they would leak into the town command
        # loop and the inn would never be entered).
        supplies = self._strict_supplies(recall=3)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, building_type=0),
        }
        snap = Snapshot(
            player(10, 10, gold=2500, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            quests={14: QuestState(14, status=QUEST_STATUS_REWARDED)},
        )
        policy = HengbotPolicy()
        set_completed_equipment_optimization(policy)
        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "town:rumor")

    def test_q14_reward_states_arm_rumor_without_yeek_conquest(self):
        for status in (QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED):
            with self.subTest(status=status):
                snap = Snapshot(
                    player(10, 10),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    quests={14: QuestState(14, status=status)},
                    yeek_cave_conquered=False,
                )
                policy = HengbotPolicy()
                policy._observe(snap)
                self.assertTrue(policy._rumor_unlock_pending)

    def test_pre_reward_or_missing_q14_does_not_arm_rumor_after_conquest(self):
        for status in (None, QUEST_STATUS_TAKEN, QUEST_STATUS_COMPLETED):
            with self.subTest(status=status):
                quests = {} if status is None else {14: QuestState(14, status=status)}
                snap = Snapshot(
                    player(10, 10),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    quests=quests,
                    yeek_cave_conquered=True,
                )
                policy = HengbotPolicy()
                policy._observe(snap)
                self.assertFalse(policy._rumor_unlock_pending)

    def test_angband_unlock_clears_q14_rumor_latch(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            quests={14: QuestState(14, status=QUEST_STATUS_FINISHED)},
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._rumor_unlock_pending = True
        policy._observe(snap)
        self.assertFalse(policy._rumor_unlock_pending)

    def test_standing_on_inn_does_not_latch_inn_not_found_block(self):
        # Regression for the town "5-loop": when already standing on the inn tile
        # (a path-to-self is empty), the old code latched a sticky inn-not-found
        # WAIT and froze forever. The fix falls through instead, so the block is
        # never set and the run can continue (recall / dive again).
        supplies = self._strict_supplies(recall=1)
        snap = Snapshot(
            player(10, 10, gold=2500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, building_type=0)},
            [],
            inventory=supplies,
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            yeek_cave_conquered=True,
        )
        policy = HengbotPolicy()
        policy._rumor_unlock_pending = True
        policy._deepest_level = RECALL_MIN_DEPTH
        policy._town_special_key(snap)
        self.assertNotEqual(policy._town_blocked_reason, "inn-not-found")
        self.assertNotEqual(policy.last_reason, "town:blocked:inn-not-found")

    def test_angband_departure_uses_recall_and_keeps_return_stock(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=6),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_ANGBAND,
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._prepare_equipment_optimization = lambda _snapshot: SimpleNamespace(
            ready=True,
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout="worn-light-loadout")),
            transaction=SimpleNamespace(actions=()),
            blockers=(),
        )
        policy._char_dump_done_this_visit = True  # past the pre-dive dump
        self.assertEqual(policy.choose_key(snap), "rra")
        self.assertEqual(policy.last_reason, "town:recall-to-angband")

    def test_live_capture_home_scan_incomplete_never_reads_recall_after_restart(self):
        """16:13:47 shape: fresh policy, only light worn, no optimizer result."""
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=6),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_ANGBAND,
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        incomplete = SimpleNamespace(
            ready=False,
            result=None,
            transaction=None,
            blockers=("home-scan-incomplete",),
        )
        policy = HengbotPolicy()
        policy.prime(snap)
        self.assertFalse(policy._calibration_stripped_unrestored)
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        policy._char_dump_done_this_visit = True
        policy._prepare_equipment_optimization = lambda _snapshot: incomplete

        keys = []
        reasons = []
        for offset in range(300):
            # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: bounded replay intentionally exercises internal timeout state without applying map movement
            key = policy.choose_key(replace(snap, turn=snap.turn + offset))
            keys.append(key)
            reasons.append(policy.last_reason)

        self.assertNotIn(
            "rra",
            keys,
            "fresh restart must not post recall while home-scan-incomplete has no result",
        )
        self.assertTrue(
            any(reason.startswith("town:blocked:equipment-") for reason in reasons),
            reasons[-10:],
        )
        self.assertIn("livelock:exhausted", reasons)
        self.assertFalse(policy._equipment_departure_ready(snap))

    def test_timed_out_optimizer_cannot_recall_while_wearable_gear_is_packed(self):
        """A real timeout shape proves no best; live gear must remain authority."""
        packed = [
            item("w", TVAL_SWORD, 1, is_equipment=True, known=True),
            item("a", 36, 1, is_equipment=True, known=True),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[*packed, *self._strict_supplies(recall=6)],
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_ANGBAND,
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        timed_out = SimpleNamespace(
            ready=False,
            result=SimpleNamespace(best=None, timed_out=True),
            transaction=None,
            blockers=("optimization-timeout",),
        )
        policy = HengbotPolicy()
        policy.prime(snap)
        policy._char_dump_done_this_visit = True
        policy._prepare_equipment_optimization = lambda _snapshot: timed_out

        self.assertNotEqual(policy.choose_key(snap), "rra")
        self.assertFalse(policy._equipment_departure_ready(snap))

    def test_stale_dressed_timeout_is_refused_for_currently_stripped_snapshot(self):
        dressed = Loadout((), "stale-dressed")
        timed_out = SimpleNamespace(
            current=dressed,
            ready=False,
            result=SimpleNamespace(best=None, timed_out=True),
            transaction=None,
            blockers=("optimization-timeout",),
        )
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            inventory=[item("w", TVAL_SWORD, 1, is_equipment=True, known=True)],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        policy._equipment_optimization_preparation = timed_out
        policy._equipment_optimization_timed_out_this_visit = True

        with patch.object(
            policy, "_prepare_equipment_optimization", return_value=timed_out
        ):
            self.assertFalse(policy._equipment_departure_ready(snapshot))

    def test_stale_home_candidate_latch_does_not_block_ready_recall(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=6),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_ANGBAND,
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._char_dump_done_this_visit = True
        policy.prime(snap)
        policy._equipment_catalog.home_scan_complete = True
        policy._home_candidate_waiting = True
        policy._home_available = lambda candidate_snapshot: True
        policy._equipment_departure_ready = lambda candidate_snapshot: True

        self.assertEqual(policy._town_special_key(snap), "rra")
        self.assertFalse(policy._home_candidate_waiting)
        self.assertEqual(policy.last_reason, "town:recall-to-angband")

    def test_incomplete_empty_home_catalog_routes_or_defers_by_visit_state(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=6),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_ANGBAND,
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        for candidate_waiting in (False, True):
            with self.subTest(
                home_attempted=False,
                candidate_waiting=candidate_waiting,
            ):
                policy = HengbotPolicy()
                policy._equipment_catalog.home_scan_complete = False
                policy._home_candidate_waiting = candidate_waiting
                policy._home_available = lambda candidate_snapshot: True

                needs = policy._enumerate_town_needs(snap)

                self.assertIn(
                    TownNeed(STORE_HOME, "equipment-catalog", "home-first"),
                    needs,
                )

            with self.subTest(
                home_attempted=True,
                candidate_waiting=candidate_waiting,
            ):
                policy = HengbotPolicy()
                policy._char_dump_done_this_visit = True
                policy.prime(snap)
                policy._equipment_catalog.home_scan_complete = False
                policy._home_candidate_waiting = candidate_waiting
                policy._town_store_attempted[STORE_HOME] = snap.turn
                policy._home_available = lambda candidate_snapshot: True
                policy._equipment_departure_ready = lambda candidate_snapshot: True

                self.assertEqual(policy._town_special_key(snap), "rra")
                self.assertFalse(policy._home_candidate_waiting)
                self.assertEqual(policy.last_reason, "town:recall-to-angband")

    def test_real_pending_home_candidate_still_defers_ready_recall(self):
        candidate = item(
            "w", 23, 2, name="awaited sword", known=True, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[*self._strict_supplies(recall=2), candidate],
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_ANGBAND,
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._char_dump_done_this_visit = True
        pending = policy._item_signature(candidate)
        policy._equipment_catalog.home_scan_complete = False
        policy._home_candidate_waiting = True
        policy._home_pending_item = pending
        policy._home_available = lambda candidate_snapshot: True

        self.assertFalse(policy._town_departure_ready(snap))
        self.assertTrue(policy._home_candidate_waiting)
        self.assertEqual(policy._home_pending_item, pending)

    def test_unsafe_angband_recall_switches_to_shallowest_entered_dungeon(self):
        snap = Snapshot(
            player(
                10,
                10,
                level=26,
                class_id=PLAYER_CLASS_WARRIOR,
                abilities=frozenset(),
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=10),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_ANGBAND,
            recall_depth=20,
            entered_dungeon_ids=(1, 2, 3, 4, 7, 12, 14),
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy(
            dungeon_knowledge={
                DUNGEON_ANGBAND: DungeonInfo(
                    DUNGEON_ANGBAND, "Angband", 1, 127, 30
                ),
                3: DungeonInfo(3, "Orc Cave", 10, 22, 5),
            }
        )
        policy._target_dungeon_id = DUNGEON_ANGBAND
        policy._char_dump_done_this_visit = True

        self.assertEqual(policy._town_special_key(snap), WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertEqual(policy._target_dungeon_id, 3)
        self.assertFalse(policy._recall_destination_safe(snap, DUNGEON_ANGBAND))

    def test_town_recall_selects_the_target_from_entered_dungeon_order(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            # Departure consumes one scroll; five leaves four in the dungeon,
            # safely above the deep-return threshold of three.
            inventory=self._strict_supplies(recall=5, teleport=4, critical=4),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
        )
        policy = HengbotPolicy()
        policy._deepest_level = RECALL_MIN_DEPTH
        policy._char_dump_done_this_visit = True  # past the pre-dive dump

        self.assertIsNone(policy._town_special_key(snap))

    def test_recall_selection_falls_back_to_current_destination(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            recall_dungeon_id=4,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE),
        )

        self.assertEqual(HengbotPolicy._recall_selection_key(snap, 4), "a")

    def test_yeek_recall_departure_keeps_dungeon_reserve_after_use(self):
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=3, teleport=3, critical=3),
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
        )
        policy = HengbotPolicy()
        policy._deepest_level = RECALL_MIN_DEPTH

        self.assertEqual(policy._recall_required_target(snap), 6)
        self.assertFalse(policy._recall_ready(snap))
        self.assertIsNone(policy._town_special_key(snap))

    def test_angband_recall_purchase_target_covers_min_depth_band_arrival(self):
        # Depths 5-10 share the single six-scroll requirement without a
        # context-dependent departure add-on.
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            angband_recall_unlocked=True,
        )
        policy = HengbotPolicy()
        policy._target_dungeon_id = DUNGEON_ANGBAND
        for planned_depth in (RECALL_MIN_DEPTH, 10):  # both ends of the 5-10 band
            policy._deepest_level = planned_depth - 1
            self.assertEqual(policy._recall_target(planned_depth), 6)
            self.assertEqual(policy._recall_required_target(snap), 6)

    def test_recall_arrival_at_min_depth_band_clears_both_thresholds(self):
        # The requirement still gates further descent, while the separate
        # recall-shortage retreat only fires below three from 6F onward.
        def arrival(count):
            return Snapshot(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)},
                [],
                floor_key=(DUNGEON_YEEK_CAVE, RECALL_MIN_DEPTH, 0),
                inventory=self._strict_supplies(
                    recall=count, teleport=15, critical=10
                ),
                equipment=[self._lantern()],
            )

        policy = HengbotPolicy()
        stocked = arrival(6)
        low = arrival(2)
        self.assertFalse(policy._ledger_return_shortages(
            policy._supply_ledger(stocked, stocked.dungeon_level), stocked.dungeon_level
        ))
        self.assertFalse(policy._next_depth_supply_shortage(stocked))
        self.assertFalse(policy._ledger_return_shortages(
            policy._supply_ledger(low, low.dungeon_level), low.dungeon_level
        ))
        self.assertFalse(policy._next_depth_supply_shortage(low))

    def test_identify_source_reservation_releases_on_success(self):
        policy = HengbotPolicy()
        target = ("unknown home sword", 23, -1)
        policy._identification_source_reservation = {
            "target": target,
            "kind": "normal",
            "source": {
                "signature": ("Identify", TVAL_SCROLL, SV_SCROLL_IDENTIFY),
                "slot": "c",
            },
            "state": "identifying",
            "baseline": {},
        }
        policy._home_pending_item = target
        known = item(
            "a", 23, -1, name="unknown home sword", aware=True, known=True,
            fully_known=True, is_equipment=True,
        )
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[known],
            equipment=[self._lantern()],
        )

        self.assertIsNone(policy._town_item_processing_key(snapshot))
        self.assertIsNone(policy._identification_source_reservation)

    def test_identify_source_reservation_releases_on_bounded_home_failure(self):
        policy = HengbotPolicy()
        target = ("unknown home sword", 23, -1)
        scroll = item("c", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify")
        policy._identification_source_reservation = {
            "target": target,
            "kind": "normal",
            "source": {
                "signature": policy._item_signature(scroll),
                "slot": scroll.slot,
            },
            "state": "acquired",
            "baseline": {},
        }
        policy._home_candidate_waiting = True
        policy._home_pending_item = target

        policy._release_blocked_store_latches(STORE_HOME)

        self.assertIsNone(policy._identification_source_reservation)
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[scroll],
            equipment=[self._lantern()],
        )
        self.assertEqual(
            policy._find_identification_source(snapshot, full=False),
            (READ_KEY, scroll),
        )

    def test_home_skips_average_pseudo_identified_equipment_for_occupied_slot(self):
        average = store_item(
            "a",
            23,
            1,
            name="average sword",
            known=False,
            fully_known=False,
            is_equipment=True,
            pseudo_feeling="average",
        )
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[
                self._lantern(),
                item("main_hand", 23, 2, is_equipment=True),
            ],
            store=StoreState(store_type=STORE_HOME, items=[average]),
        )
        policy = HengbotPolicy()

        self.assertNotEqual(policy.choose_key(home), "pa\r")
        self.assertIsNone(policy._identification_need)

    def test_home_catalog_does_not_wrap_after_non_page_action(self):
        average = store_item(
            "a", 23, 1, name="average sword", known=False,
            fully_known=False, is_equipment=True, pseudo_feeling="average",
        )
        full_page = [average] + [
            store_item(
                chr(ord("a") + index), 23, index,
                name=f"average sword {index}", known=False,
                fully_known=False, is_equipment=True,
                pseudo_feeling="average",
            )
            for index in range(1, 12)
        ]
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern(), item("main_hand", 23, 2, is_equipment=True)],
            store=StoreState(
                store_type=STORE_HOME, items=full_page, stock_num=12,
                page_top=0, page_size=12,
            ),
        )
        policy = HengbotPolicy()

        policy.choose_key(home)
        policy.last_reason = "home:withdraw-processing-item"
        policy.choose_key(home)

        self.assertTrue(policy._equipment_catalog.home_scan_complete)

    def test_home_batch_keeps_three_pack_slots_free(self):
        filler = [
            item(chr(ord("a") + i), TVAL_STAFF, i, charges=1, name=f"staff-{i}")
            for i in range(19)
        ]
        gloves = store_item(
            "a", 31, 1, name="known gloves", known=True,
            fully_known=True, is_equipment=True,
        )
        boots = store_item(
            "b", 30, 1, name="known boots", known=True,
            fully_known=True, is_equipment=True,
        )
        home = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=filler,
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_HOME, items=[gloves, boots], stock_num=2, page_top=0, page_size=52),
        )
        policy = HengbotPolicy()

        policy.consume_home_knowledge(tuple(home.store.items))
        outside = replace(home, store=None)
        policy.choose_key(outside)
        self.assertEqual(policy._home_pending_batch, [])
        self.assertGreaterEqual(PACK_CAPACITY - len(filler), HOME_BATCH_RESERVED_SLOTS)

    def test_home_batch_identification_does_not_trial_known_candidates(self):
        gloves = item(
            "a", 31, 1, name="known gloves", known=True,
            fully_known=True, is_equipment=True,
        )
        boots = item(
            "b", 30, 1, name="known boots", known=True,
            fully_known=True, is_equipment=True,
        )
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=[gloves, boots],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_pending_batch = [
            policy._item_signature(gloves),
            policy._item_signature(boots),
        ]
        policy._home_candidate_waiting = False

        self.assertIsNone(policy._town_item_processing_key(town))
        self.assertEqual(policy.last_reason, "identify:batch-complete")
        self.assertFalse(policy._home_pending_batch)
        self.assertFalse(policy._home_batch_review_items)

    def test_pending_home_batch_blocks_town_departure(self):
        gloves = item(
            "a", 31, 1, name="known gloves", known=True,
            fully_known=True, is_equipment=True,
        )
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=3),
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        # Departure now requires a duplicate-preserving full Home scan. This
        # direct private-method test bypasses choose_key(), so mark the empty
        # Home's single page as observed and wrapped explicitly.
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_departure_ready = lambda snapshot: True
        self.assertTrue(policy._town_departure_ready(town))

        policy._equipment_departure_ready = lambda snapshot: False
        self.assertFalse(policy._town_departure_ready(town))
        policy._equipment_departure_ready = lambda snapshot: True
        policy._home_pending_batch = [policy._item_signature(gloves)]
        self.assertFalse(policy._town_departure_ready(town))

    def test_full_identification_tier_preserves_blocked_alchemist(self):
        """A *Identify* escalation must not re-arm a shop that cannot sell it."""
        candidate = item(
            "m", 22, 20, name="known ego mace", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=12224),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=[candidate, *self._strict_supplies(recall=1)],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._identification_need = "normal"
        policy._home_pending_item = policy._item_signature(candidate)
        policy._home_pending_slot = candidate.slot
        policy._town_store_attempted[STORE_ALCHEMIST] = town.turn
        policy._town_errand_plan = TownErrandPlan(
            [STORE_ALCHEMIST],
            index=1,
            blocked_this_visit=[STORE_ALCHEMIST],
        )

        policy._request_identification("full")

        self.assertEqual(policy._identification_need, "full")
        self.assertIn(STORE_ALCHEMIST, policy._town_store_attempted)
        self.assertIn(
            STORE_ALCHEMIST, policy._town_errand_plan.blocked_this_visit
        )

    def test_home_normal_identify_remains_actionable_with_carried_source(self):
        candidate = store_item(
            "a", 23, 4, name="unidentified dagger", known=False,
            fully_known=False, pseudo_feeling="good", is_equipment=True,
        )
        source = item(
            "s", TVAL_SCROLL, SV_SCROLL_IDENTIFY,
            name="scroll of identify", known=True, aware=True,
        )
        home = replace(
            self._ready_home_town(gold=FUNDRAISING_START_GOLD),
            inventory=[*self._strict_supplies(recall=1), source],
            store=StoreState(store_type=STORE_HOME, items=[candidate]),
            town_flag=False,
        )
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_ALCHEMIST] = home.turn

        self.assertEqual(policy._find_home_candidate(home), candidate)
        self.assertNotIn(
            policy._item_signature(candidate), policy._deferred_home_items
        )

    def test_home_normal_identify_visits_alchemist_before_deferring(self):
        candidate = store_item(
            "a", 23, 4, name="unidentified dagger", known=False,
            fully_known=False, pseudo_feeling="good", is_equipment=True,
        )
        home = replace(
            self._ready_home_town(gold=FUNDRAISING_START_GOLD),
            store=StoreState(store_type=STORE_HOME, items=[candidate]),
            town_flag=False,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._find_home_candidate(home), candidate)
        self.assertNotIn(
            policy._item_signature(candidate), policy._deferred_home_items
        )

    def test_deferred_home_item_does_not_block_equipment_departure(self):
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
            "a", 19, 1, name="unidentified bow", known=False,
            fully_known=False, is_equipment=True,
        )
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._deferred_home_items.add(policy._item_signature(incomplete))

        preparation = policy._prepare_equipment_optimization(town)

        self.assertIsNotNone(preparation)
        self.assertNotIn("incomplete-equipment-catalog", preparation.blockers)

    def test_deferred_home_item_is_rearmed_by_a_mining_return(self):
        # A Home candidate deferred during a town stay must be offered again once
        # a completed Yeek Cave mining run establishes the retry boundary.
        candidate = store_item(
            "a", 23, 4, name="unidentified blade", is_equipment=True,
            aware=True, known=False,
        )
        pol = HengbotPolicy()
        signature = pol._item_signature(candidate)
        pol._deferred_home_items.add(signature)
        home = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[candidate]),
        )
        self.assertIsNone(pol._find_home_candidate(home))

        pol._floor_key = (DUNGEON_YEEK_CAVE, 1, 0)
        pol._fundraising_mode = "mine"
        pol._observe(self._ready_home_town())

        self.assertNotIn(signature, pol._deferred_home_items)
        self.assertIsNotNone(pol._find_home_candidate(home))

    def test_mining_return_reclears_processed_home_items(self):
        # An ego item needing *full* identification is burned into
        # _processed_home_items after one pass and thereafter skipped forever
        # (its signature never changes until it is actually *fully* identified).
        # The mining-return retry boundary must clear that cache so the item is
        # offered for a fresh identification attempt.
        candidate = store_item(
            "a", 31, 1, name="ego gloves", is_equipment=True, aware=True,
            known=True, fully_known=False, is_ego=True,
        )
        pol = HengbotPolicy()
        signature = pol._item_signature(candidate)
        pol._processed_home_items.add(signature)
        home = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            store=StoreState(store_type=STORE_HOME, items=[candidate]),
        )
        self.assertIsNone(pol._find_home_candidate(home))

        pol._floor_key = (DUNGEON_YEEK_CAVE, 1, 0)
        pol._fundraising_mode = "mine"
        pol._observe(self._ready_home_town())

        self.assertNotIn(signature, pol._processed_home_items)
        self.assertIsNotNone(pol._find_home_candidate(home))

    def test_processed_home_deadlock_enters_fundraising_not_wander(self):
        # The 2026-07-15 incident shape: the optimizer is blocked by an incomplete
        # catalog whose sole blocking item is Home gear already burned into
        # _processed_home_items (so no store route and no identify errand targets
        # it), gold sits above the auto-fundraise floor but below the target, and
        # the policy would otherwise fall through to endless stuck:wander. The
        # identification fundraising driver must instead enter mining to reach the
        # retry boundary.
        self.assertGreater(5894, FUNDRAISING_START_GOLD)
        self.assertLess(5894, FUNDRAISING_GOLD_TARGET)
        town = self._ready_home_town(gold=5894)
        incomplete = store_item(
            "a", 23, 4, name="ego blade", known=True, fully_known=False,
            is_equipment=True, is_ego=True,
        )
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._processed_home_items.add(policy._item_signature(incomplete))
        home_owned = next(
            owned for owned in policy._equipment_catalog.items
            if owned.origin == "home"
        )
        # Stub the optimizer preparation to the incident's blocker shape; the
        # real optimizer is exercised elsewhere. The driver must read the blocker
        # and the blocking item's origin/signature to decide recoverability.
        policy._prepare_equipment_optimization = lambda snapshot: SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
            result=SimpleNamespace(
                incomplete_item_ids=frozenset({home_owned.id})
            ),
        )

        # The stranded item is non-actionable: no Home route masks the deadlock,
        # and the ordinary gold-floor fundraiser refuses at this gold level.
        self.assertFalse(policy._has_actionable_incomplete_home_item(town))
        self.assertFalse(policy._start_fundraising(town))
        # The driver converts the block into a productive fundraising entry.
        self.assertTrue(policy._start_identification_fundraising(town))
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_identification_fundraising_ignores_a_non_home_blocker(self):
        # An equipped/pack unidentified item (mining does NOT re-arm it) must not
        # trigger the identification fundraiser: doing so would loop mining
        # forever without ever clearing the block.
        town = self._ready_home_town(gold=5894)
        policy = HengbotPolicy()
        policy._home_candidate_waiting = False
        equipped_owned = SimpleNamespace(id="equipped:x:0", origin="equipped")
        policy._equipment_catalog = SimpleNamespace(items=(equipped_owned,))
        policy._prepare_equipment_optimization = lambda snapshot: SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
            result=SimpleNamespace(
                incomplete_item_ids=frozenset({equipped_owned.id})
            ),
        )
        self.assertFalse(policy._start_identification_fundraising(town))
        self.assertIsNone(policy._fundraising_mode)

    def test_high_gold_rearms_processed_home_identification_once(self):
        town = self._ready_home_town(gold=FUNDRAISING_GOLD_TARGET)
        incomplete = store_item(
            "a", 23, 4, name="ego blade", known=True, fully_known=False,
            is_equipment=True, is_ego=True,
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried(town.inventory, town.equipment)
        policy._equipment_catalog.observe_home_page([incomplete])
        policy._equipment_catalog.observe_home_page([])
        policy._equipment_catalog.observe_home_page([incomplete])
        signature = policy._item_signature(incomplete)
        policy._processed_home_items.add(signature)
        policy._town_store_attempted[STORE_HOME] = town.turn
        home_owned = next(
            owned for owned in policy._equipment_catalog.items
            if owned.origin == "home"
        )
        policy._prepare_equipment_optimization = lambda snapshot: SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
            result=SimpleNamespace(
                incomplete_item_ids=frozenset({home_owned.id})
            ),
        )

        self.assertTrue(policy._retry_processed_home_identification(town))
        self.assertNotIn(signature, policy._processed_home_items)
        self.assertIn(signature, policy._retried_home_identification_items)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

        policy._processed_home_items.add(signature)
        self.assertFalse(policy._retry_processed_home_identification(town))

    def test_unavailable_full_identify_defers_confirmed_pack_candidate(self):
        town = replace(
            self._ready_home_town(gold=6411),
            equipment=(
                item("main_hand", TVAL_SWORD, 1, is_equipment=True),
                item("light", TVAL_LITE, SV_LITE_TORCH, is_equipment=True),
            ),
        )
        policy = HengbotPolicy()
        policy._identification_need = "full"
        owned = SimpleNamespace(id="pack:ego:0", origin="pack")
        policy._equipment_catalog = SimpleNamespace(items=(owned,))
        policy._prepare_equipment_optimization = lambda snapshot: SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
            result=SimpleNamespace(incomplete_item_ids=frozenset({owned.id})),
            ready=False,
            transaction=None,
        )
        seed_confirmed_loadout(policy, town)

        self.assertTrue(policy._equipment_departure_ready(town))

    def test_unavailable_full_identify_keeps_equipped_candidate_blocking(self):
        town = self._ready_home_town(gold=6411)
        policy = HengbotPolicy()
        policy._identification_need = "full"
        equipped = item(
            "neck", 40, 4, name="unknown amulet", known=False,
            pseudo_feeling="good", is_equipment=True,
        )
        town = replace(town, equipment=(*town.equipment, equipped))
        owned = SimpleNamespace(
            id="equipped:ego:0", origin="equipped", item=equipped
        )
        policy._equipment_catalog = SimpleNamespace(items=(owned,))
        policy._prepare_equipment_optimization = lambda snapshot: SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
            result=SimpleNamespace(incomplete_item_ids=frozenset({owned.id})),
            ready=False,
            transaction=None,
        )

        self.assertFalse(policy._equipment_departure_ready(town))

    def test_exhausted_identify_stock_allows_confirmed_deferred_candidate(self):
        town = self._ready_home_town(gold=6411)
        policy = HengbotPolicy()
        policy._identification_need = "full"
        equipped = item(
            "neck", 40, 4, name="unknown amulet", known=False,
            pseudo_feeling="good", is_equipment=True,
        )
        town = replace(town, equipment=(*town.equipment, equipped))
        owned = SimpleNamespace(
            id="equipped:ego:0", origin="equipped", item=equipped
        )
        policy._equipment_catalog = SimpleNamespace(items=(owned,))
        policy._deferred_home_items.add(policy._item_signature(equipped))
        policy._prepare_equipment_optimization = lambda snapshot: SimpleNamespace(
            blockers=("incomplete-equipment-catalog",),
            result=SimpleNamespace(incomplete_item_ids=frozenset({owned.id})),
            ready=False,
            transaction=None,
        )
        seed_confirmed_loadout(policy, town)

        self.assertTrue(policy._equipment_departure_ready(town))

    def test_non_mining_town_arrival_preserves_processed_home_items(self):
        # The identification retry boundary is a completed MINING trip only. A
        # plain dive-and-return (here from Angband) must not re-scan every stored
        # item, so _processed_home_items is deliberately preserved on that arrival
        # even though the deferred sets are re-armed by the fresh-town reset.
        candidate = store_item(
            "a", 31, 1, name="ego gloves", is_equipment=True, known=True,
            fully_known=False, is_ego=True,
        )
        pol = HengbotPolicy()
        signature = pol._item_signature(candidate)
        pol._processed_home_items.add(signature)
        pol._deferred_home_items.add(signature)
        pol._floor_key = (DUNGEON_ANGBAND, 20, 0)
        pol._fundraising_mode = None

        pol._observe(self._ready_home_town())

        self.assertIn(signature, pol._processed_home_items)
        self.assertNotIn(signature, pol._deferred_home_items)

    def test_home_batch_never_selects_a_per_item_armour_upgrade(self):
        weaker = item(
            "a", 31, 1, name="weaker gloves", known=True,
            fully_known=True, is_equipment=True, ac=1, to_a=1,
        )
        stronger = item(
            "b", 31, 2, name="stronger gloves", known=True,
            fully_known=True, is_equipment=True, ac=2, to_a=4,
        )
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[weaker, stronger],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_pending_batch = [
            policy._item_signature(weaker),
            policy._item_signature(stronger),
        ]

        self.assertIsNone(policy._town_item_processing_key(town))
        self.assertNotEqual(policy.last_reason, "equipment:equip-best-batch-armour")

    def test_withdrawn_average_equipment_does_not_consume_identify(self):
        target = item(
            "a",
            23,
            1,
            name="average sword",
            known=False,
            is_equipment=True,
            pseudo_feeling="average",
        )
        identify_scroll = item(
            "i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, identify_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertNotEqual(policy.choose_key(snap), "ria")
        self.assertNotEqual(policy.last_reason, "identify:normal")

    def test_identification_prefers_reliable_scroll_over_fallible_staff(self):
        target = item(
            "a", 23, -1, aware=False, known=False, is_equipment=True
        )
        staff = item(
            "u", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=2, name="staff"
        )
        scroll = item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="scroll")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, staff, scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)
        # A failed device activation never reaches the target prompt, so a
        # concatenated target letter becomes an unrelated town command.  Use
        # the scroll, whose read command reliably reaches item selection.
        self.assertEqual(policy.choose_key(snap), "ria")
        self.assertEqual(policy.last_reason, "identify:normal")

    def test_identifies_an_unknown_wand_in_town(self):
        wand = item("a", TVAL_WAND, -1, aware=False, known=False, name="unknown wand")
        scroll = item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[wand, scroll],
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "ria")
        self.assertEqual(policy.last_reason, "identify:device")

    def test_identifies_the_recorded_unknown_rod_as_a_device(self):
        rod = item(
            "a", TVAL_ROD, -1, aware=False, known=False,
            name="unknown rod carried since turn 1267045",
        )
        scroll = item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[rod, scroll],
            town_flag=True,
        )
        policy = HengbotPolicy()

        key = policy._town_device_processing_key(snap)

        self.assertIsNotNone(key)
        self.assertEqual(key, "ria")
        self.assertEqual(policy.last_reason, "identify:device")
        self.assertEqual(
            policy._device_identify_watch,
            (policy._item_signature(rod), 1),
        )

    def test_high_device_skill_uses_carried_staff_to_identify_pack_gear(self):
        # Live 2026-07-24 deadlock: a warrior carrying Staves of Identify but no
        # scroll sat in town blocked on an incomplete equipment catalog because
        # the town identify errand demanded a scroll.  When the modelled staff
        # success rate is reliable (device_skill 34 -> ~0.92), the carried staff
        # must be used so the catalog can complete.  Same setup as the only-staff
        # routing test but with a reliable device skill (revert-proof: the old
        # scroll-only errand returns None here regardless of skill).
        ring = item(
            "a", TVAL_RING, -1, name="unknown ring",
            aware=False, known=False, is_equipment=True,
        )
        staff = item(
            "u", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=9, name="staff"
        )
        snap = Snapshot(
            replace(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                device_skill=34,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[ring, staff],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()

        key = policy._town_item_processing_key(snap)
        self.assertIsNotNone(key)
        self.assertTrue(key.startswith(policy_module.USE_STAFF_KEY))
        self.assertEqual(policy.last_reason, "identify:normal")

    def test_staff_identify_success_rate_gates_on_device_skill(self):
        policy = HengbotPolicy()
        high = Snapshot(
            replace(player(10, 10), device_skill=34),
            {Position(10, 10): grid(10, 10)},
            [],
        )
        low = Snapshot(
            replace(player(10, 10), device_skill=12),
            {Position(10, 10): grid(10, 10)},
            [],
        )
        self.assertGreaterEqual(
            policy._identify_staff_success_rate(high),
            policy_module.STAFF_IDENTIFY_MIN_SUCCESS,
        )
        self.assertLess(
            policy._identify_staff_success_rate(low),
            policy_module.STAFF_IDENTIFY_MIN_SUCCESS,
        )

    def test_identify_give_up_requires_current_town_shelf_evidence(self):
        ring = item(
            "a", TVAL_RING, -1, name="unknown ring", aware=False,
            known=False, is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[ring],
            equipment=[self._lantern()], town_flag=True, town_id=1, turn=40,
        )
        policy = HengbotPolicy()
        policy._refresh_carried_equipment_catalog(snap)
        self.assertIsNone(policy._town_item_processing_key(snap))
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(
            store_type=STORE_ALCHEMIST, items=[]
        )
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (0, 39)

        policy._town_terminal_transitions(snap)

        self.assertEqual(policy._identification_need, "normal")
        self.assertNotIn(
            policy._item_signature(ring), policy._town_unidentifiable_carried_sigs
        )
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_unknown_identify_stock_waits_for_observation_before_writeoff(self):
        ring = item(
            "a", TVAL_RING, -1, name="unknown ring", aware=False,
            known=False, is_equipment=True,
        )
        outside = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[ring],
            equipment=[self._lantern()], town_flag=True, town_id=1, turn=40,
        )
        policy = HengbotPolicy()
        policy._refresh_carried_equipment_catalog(outside)
        self.assertIsNone(policy._town_item_processing_key(outside))
        policy._town_store_attempted[STORE_ALCHEMIST] = outside.turn
        plan = TownErrandPlan(
            stops=[STORE_ALCHEMIST], completed_this_visit=[STORE_ALCHEMIST]
        )
        policy._town_errand_plan = plan

        policy._town_terminal_transitions(outside)

        self.assertEqual(plan.completed_this_visit, [])
        self.assertEqual(policy._identification_need, "normal")
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

        inside = replace(
            outside,
            store=StoreState(store_type=STORE_ALCHEMIST, items=[]),
            turn=41,
        )
        policy._floor_key = outside.floor_key
        policy.choose_key(inside)
        self.assertEqual(
            policy._identification_source_obtainability(inside, full=False),
            "unavailable",
        )
        policy._town_store_attempted[STORE_ALCHEMIST] = inside.turn
        policy._town_terminal_transitions(inside)
        self.assertIsNone(policy._identification_need)
        self.assertIn(
            policy._item_signature(ring), policy._town_unidentifiable_carried_sigs
        )

    def test_stale_empty_identify_shelf_cannot_authorize_writeoff(self):
        ring = item(
            "a", TVAL_RING, -1, name="unknown ring", aware=False,
            known=False, is_equipment=True,
        )
        observed_turn = 40
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[ring],
            equipment=[self._lantern()], town_flag=True, town_id=1,
            turn=observed_turn + STORE_RESTOCK_WAIT_TURNS,
        )
        policy = HengbotPolicy()
        policy._refresh_carried_equipment_catalog(snap)
        self.assertIsNone(policy._town_item_processing_key(snap))
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(
            store_type=STORE_ALCHEMIST, items=[]
        )
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
            policy._effective_town_id(snap), observed_turn
        )

        self.assertEqual(
            policy._identification_source_obtainability(snap, full=False),
            "unknown",
        )
        policy._town_terminal_transitions(snap)
        signature = policy._item_signature(ring)
        self.assertEqual(policy._identification_need, "normal")
        self.assertNotIn(signature, policy._town_unidentifiable_carried_sigs)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_alchemist_observation_writer_drives_identify_obtainability(self):
        outside = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            town_flag=True, town_id=1, turn=40,
        )
        inside = replace(
            outside,
            store=StoreState(store_type=STORE_ALCHEMIST, items=[]),
            turn=41,
        )
        policy = HengbotPolicy()
        policy._floor_key = outside.floor_key

        self.assertEqual(
            policy._identification_source_obtainability(outside, full=False),
            "unknown",
        )
        policy.choose_key(inside)
        self.assertEqual(
            policy._identification_source_obtainability(inside, full=False),
            "unavailable",
        )

    def test_current_empty_identify_shelf_gives_up_in_first_transition_pass(self):
        ring = item(
            "a", TVAL_RING, -1, name="unknown ring", aware=False,
            known=False, is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [], inventory=[ring],
            equipment=[self._lantern()], town_flag=True, town_id=1, turn=40,
        )
        policy = HengbotPolicy()
        policy._refresh_carried_equipment_catalog(snap)
        self.assertIsNone(policy._town_item_processing_key(snap))
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
        policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(
            store_type=STORE_ALCHEMIST, items=[]
        )
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (1, 40)

        policy._town_terminal_transitions(snap)

        self.assertIsNone(policy._identification_need)
        self.assertIn(
            policy._item_signature(ring), policy._town_unidentifiable_carried_sigs
        )

    def test_magic_shop_sells_nonessential_devices(self):
        for device in (
            item("a", TVAL_WAND, 1, charges=8, name="wand"),
            item("a", TVAL_STAFF, 1, charges=8, name="staff"),
        ):
            with self.subTest(tval=device.tval):
                snap = Snapshot(
                    player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                    {Position(10, 10): grid(10, 10)},
                    [],
                    inventory=[device],
                    store=StoreState(store_type=STORE_MAGIC, items=[]),
                    town_flag=True,
                )
                policy = HengbotPolicy()
                self.assertEqual(_public_shop_inner(self, policy, snap), "{a@0\r")
                self.assertEqual(policy.last_reason, "shop:batch-inscribe")

    def test_magic_shop_sells_device_pile_with_quantity_and_confirmation(self):
        device = item(
            "j", TVAL_WAND, 1, charges=9, count=3, name="pile of wands"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[device],
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )

        self.assertEqual(_public_shop_inner(self, HengbotPolicy(), snap), "{j@0\r")

    def test_single_device_sale_answers_price_confirmation_without_quantity(self):
        device = item("j", TVAL_WAND, 1, charges=3, name="wand")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[device],
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )

        policy = HengbotPolicy()
        first = _public_shop_inner(self, policy, snap)
        self.assertEqual(first, "{j@0\r")
        self.assertNotEqual(first, "dj\r")
        observed = replace(
            snap, inventory=[replace(device, inscription="@0")], turn=snap.turn + 1
        )
        self.assertEqual(_public_shop_inner(self, policy, observed), "d0y")

    def test_preinscribed_stack_plan_build_re_resolves_current_snapshot_item(self):
        evidence = json.loads(
            Path("tests/fixtures/batch_sell_stack_quantity_20260810.json")
            .read_text(encoding="utf-8")
        )
        observed_stack = replace(
            item("j", TVAL_WAND, 1, count=2, name="wand"), inscription="@0"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[observed_stack],
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()
        key = _public_shop_inner(self, policy, snap)

        self.assertEqual(key, "d099\ry")
        self.assertNotEqual(key, evidence["attempts"][0]["key"])

    def test_live_shaped_sale_reaches_price_confirm_and_gold_delta(self):
        sale = replace(
            item("j", TVAL_WAND, 1, count=1, name="wand"), inscription="@0"
        )
        snap = Snapshot(
            player(10, 10, gold=7589, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): replace(grid(10, 10), store_number=STORE_MAGIC)}, [], inventory=[sale],
            store=StoreState(store_type=STORE_MAGIC, items=[]), town_flag=True,
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
            "door-composed-magic-store", key, None, set(), in_store=False,
            decision={"reason": policy.last_reason, "key": key},
        )
        self.assertTrue(sent)
        self.assertEqual(key, "5d0y\x1b")
        state = "surface"
        for character in posted:
            if state == "surface" and character == "5":
                state = "store"
            elif state == "store" and character == "d":
                state = "sell-selection"
            elif state == "sell-selection" and character == "0":
                state = "price-confirm"
            elif state == "price-confirm" and character == "y":
                state = "store"
            elif state == "store" and character == LEAVE_STORE_KEY:
                state = "surface"
            else:
                self.fail((state, character))
        applied = replace(
            snap,
            player=replace(snap.player, gold=7714),
            inventory=[],
            turn=snap.turn + 1,
        )
        policy.choose_key(applied)
        self.assertEqual(state, "surface")
        self.assertEqual(applied.player.gold - snap.player.gold, 125)
        self.assertEqual(len(snap.inventory) - len(applied.inventory), 1)
        self.assertEqual("".join(posted), "5d0y\x1b")

    def test_keeps_useful_devices(self):
        devices = [
            item("a", TVAL_WAND, 3, charges=2, name="Teleport Away"),
            item("b", TVAL_WAND, 6, charges=2, name="Stone to Mud"),
            item("c", TVAL_STAFF, 5, charges=2, name="Identify"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=devices,
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertIsNone(policy._find_device_sale(snap))

    def test_mana_race_keeps_highest_charge_wand_and_sells_other_devices(self):
        devices = [
            item("a", TVAL_WAND, 1, charges=3, name="small wand"),
            item("b", TVAL_WAND, 2, charges=9, name="large wand"),
            item("c", TVAL_STAFF, 1, charges=20, name="staff"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=devices,
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._device_food_reserve_slot(snap), "b")
        self.assertEqual(policy._find_device_sale(snap).slot, "a")

    def test_mana_race_keeps_highest_staff_only_without_wands(self):
        devices = [
            item("a", TVAL_STAFF, 1, charges=3, name="small staff"),
            item("b", TVAL_STAFF, 2, charges=9, name="large staff"),
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=devices,
            store=StoreState(store_type=STORE_MAGIC, items=[]),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._device_food_reserve_slot(snap), "b")
        self.assertEqual(policy._find_device_sale(snap).slot, "a")

    def test_mana_race_sells_identify_staff_when_both_reserves_survive(self):
        devices = [
            item("a", TVAL_WAND, 1, count=2, charges=30, name="food wand"),
            item("b", TVAL_STAFF, SV_STAFF_IDENTIFY, count=5, charges=25,
                 name="identify stack"),
            item("c", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=3,
                 name="surplus identify staff"),
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

        self.assertEqual(policy._find_surplus_identify_staff(snap).slot, "c")
        self.assertEqual(policy._find_device_sale(snap).slot, "c")

    def test_ego_item_requires_star_identify_after_normal_identification(self):
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
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)
        self.assertEqual(policy.choose_key(snap), "rsa" + "\x1b" * 8)
        self.assertEqual(policy.last_reason, "identify:full")

    def test_known_cursed_ego_gets_star_identify(self):
        target = item(
            "a", 23, 1, name="cursed ego sword", known=True,
            fully_known=False, is_equipment=True, is_ego=True, is_cursed=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, star_scroll],
            equipment=[self._lantern()],
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertEqual(policy._town_item_processing_key(snap), "rsa" + "\x1b" * 8)
        self.assertEqual(policy.last_reason, "identify:full")

    def test_measured_56_item_catalog_identifies_worn_heavy_curse(self):
        shield = item(
            "sub_hand", 34, 2, name="plasma shield", known=True,
            fully_known=False, is_equipment=True, is_cursed=True,
            inscription=policy_module.HEAVY_CURSE_TAG,
        )
        home_weapon = store_item(
            "a", 23, 25, name="Home weapon", known=True,
            fully_known=False, is_equipment=True, is_cursed=True,
        )
        complete_home = [
            store_item(
                chr(ord("a") + index % 26), 30 + index % 8, index,
                name=f"complete-{index}", known=True, fully_known=True,
                is_equipment=True,
            )
            for index in range(54)
        ]
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[star_scroll],
            equipment=[shield],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        policy._equipment_catalog.observe_home_page(
            [home_weapon, *complete_home], allow_wrap=False
        )

        self.assertEqual(len(policy._equipment_catalog.items), 56)
        self.assertEqual(
            sum(owned.identification_incomplete
                for owned in policy._equipment_catalog.items),
            2,
        )
        self.assertTrue(policy._curse_unremovable(shield))
        self.assertEqual(policy.choose_key(snapshot), "rs/b" + "\x1b" * 8)
        self.assertEqual(policy.last_reason, "identify:full-equipped")

    def test_cursed_artifact_still_requires_star_identify(self):
        target = item(
            "a", 23, 1, name="cursed artifact sword", known=True,
            fully_known=False, is_equipment=True, is_artifact=True, is_cursed=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertEqual(policy.choose_key(snap), "rsa" + "\x1b" * 8)
        self.assertEqual(policy.last_reason, "identify:full")

    def test_pseudo_cursed_unknown_item_still_gets_basic_identify(self):
        target = item(
            "a", 23, 1, name="cursed-feeling sword", known=False,
            fully_known=False, is_equipment=True, pseudo_feeling="cursed",
        )
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="identify")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertEqual(policy.choose_key(snap), "rsa")
        self.assertEqual(policy.last_reason, "identify:normal")

    def test_dragon_helm_requires_star_identify_for_random_resistance(self):
        target = item(
            "a",
            32,
            7,
            name="dragon helm",
            known=True,
            fully_known=False,
            is_equipment=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)

        self.assertEqual(policy.choose_key(snap), "rsa" + "\x1b" * 8)
        self.assertEqual(policy.last_reason, "identify:full")

    def test_equipped_dragon_helm_is_fully_identified_in_place(self):
        helm = item(
            "head",
            32,
            7,
            name="dragon helm",
            known=True,
            fully_known=False,
            is_equipment=True,
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[star_scroll],
            equipment=[helm, self._lantern()],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rs/j" + "\x1b" * 8)
        self.assertEqual(policy.last_reason, "identify:full-equipped")

    def test_equipped_unidentified_weapon_is_identified_in_place(self):
        # Regression for the 2026-07-15 incident: the live deadlock's dominant
        # optimizer blocker was an EQUIPPED, unidentified (known=False) Bastard
        # Sword (pseudo_feeling "good"). The equipment optimizer counts a worn
        # known=False item as identification_incomplete unless it is merely
        # pseudo "average", but _town_equipped_identification_key required
        # known=True (full-ID only) -- no town handler would touch this item,
        # so the bot held an Identify scroll it never applied.
        weapon = item(
            "main_hand",
            23,
            1,
            name="unidentified sword",
            known=False,
            pseudo_feeling="good",
            is_equipment=True,
        )
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="identify")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[scroll],
            equipment=[weapon, self._lantern()],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rs/a")
        self.assertEqual(policy.last_reason, "identify:normal-equipped")

    def test_obtainable_basic_identify_is_used_not_deferred(self):
        weapon = item(
            "a",
            23,
            4,
            name="unidentified dagger",
            known=False,
            pseudo_feeling="good",
            is_equipment=True,
        )
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="identify")
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[weapon, scroll],
            equipment=[self._lantern()],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn

        self.assertEqual(policy._town_item_processing_key(snap), "rsa")
        self.assertNotIn(
            policy._item_signature(weapon), policy._deferred_home_items
        )
        self.assertNotIn(
            policy._item_signature(weapon),
            policy._unbuyable_full_identify_sigs,
        )
        self.assertEqual(policy.last_reason, "identify:normal")

    def test_equipped_identify_buys_scroll_even_when_staff_is_held(self):
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
        scroll = store_item(
            "b", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=100, name="identify"
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[staff],
            equipment=[light],
            store=StoreState(STORE_ALCHEMIST, [scroll]),
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._identification_candidate = policy._item_signature(light)
        policy._identification_need = "normal"

        self.assertEqual(_public_shop_inner(self, policy, snap), "pb\r")
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")

    def test_carried_ego_weapon_is_fully_identified_before_departure(self):
        # Regression for the 2026-07-20 town deadlock: this known ego lance was
        # incomplete in the optimizer catalog, but only worn gear and selected
        # jewellery had an owner capable of spending a *Identify* scroll on it.
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
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[lance, star_scroll],
            equipment=[self._lantern()],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "rsl" + "\x1b" * 8)
        self.assertEqual(policy.last_reason, "identify:full")

    def test_identified_ego_is_tracked_after_scroll_shifts_its_slot(self):
        unknown_signature = ("unknown war hammer", 22, 12)
        target = item(
            "k",
            22,
            12,
            name="ego war hammer",
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        shifted_into_old_slot = item(
            "l", 20, 1, name="shovel", is_equipment=True
        )
        star_scroll = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, name="star identify"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[target, shifted_into_old_slot, star_scroll],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = unknown_signature
        policy._home_pending_slot = "l"

        self.assertEqual(policy.choose_key(snap), "rsk" + "\x1b" * 8)
        self.assertEqual(policy.last_reason, "identify:full")
        self.assertEqual(policy._home_pending_slot, "k")

    def test_buys_missing_star_identify_before_processing_ego(self):
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
            inventory=[target],
            equipment=[self._lantern()],
            store=StoreState(
                store_type=STORE_ALCHEMIST,
                items=[
                    store_item(
                        "b",
                        TVAL_SCROLL,
                        SV_SCROLL_STAR_IDENTIFY,
                        price=500,
                    )
                ],
            ),
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(target)
        policy._identification_need = "full"
        self.assertEqual(_public_shop_inner(self, policy, snap), "pb\r")
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")

    def test_complete_armour_waits_for_global_loadout_optimization(self):
        current = item(
            "body",
            36,
            1,
            name="old armour",
            fully_known=True,
            is_equipment=True,
            ac=5,
            to_a=2,
            known_flags=frozenset({10}),
        )
        candidate = item(
            "a",
            37,
            1,
            name="new armour",
            fully_known=True,
            is_equipment=True,
            ac=8,
            to_a=3,
            known_flags=frozenset({10, 11}),
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[candidate],
            equipment=[current, self._lantern()],
        )
        policy = HengbotPolicy()
        policy._home_pending_item = policy._item_signature(candidate)
        self.assertIsNone(policy._town_item_processing_key(snap))
        self.assertIsNone(policy._home_pending_item)
        self.assertNotEqual(policy.last_reason, "equipment:equip-dominating-upgrade")

    def test_legacy_armour_comparison_does_not_bypass_r1_catalog_proof(self):
        superior = item(
            "body",
            36,
            1,
            fully_known=True,
            is_equipment=True,
            ac=10,
            to_a=5,
            known_flags=frozenset({10}),
        )
        inferior = item(
            "a", 37, 1, known=True, is_equipment=True, ac=5, to_a=1
        )
        protected = item(
            "b",
            37,
            1,
            known=True,
            fully_known=True,
            is_equipment=True,
            is_artifact=True,
            ac=1,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[inferior, protected],
            equipment=[superior, self._lantern()],
        )
        policy = HengbotPolicy()
        self.assertFalse(policy._is_disposable_dominated_armour(snap, inferior))
        self.assertFalse(policy._is_disposable_dominated_armour(snap, protected))

    def test_weapon_is_not_disposed_by_armour_dominance_rule(self):
        superior = item(
            "main_hand", 23, 1, known=True, is_equipment=True, pval=2
        )
        inferior = item("a", 23, 2, known=True, is_equipment=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[inferior],
            equipment=[superior, self._lantern()],
        )

        self.assertFalse(
            HengbotPolicy()._is_disposable_dominated_armour(snap, inferior)
        )

    def test_pseudo_average_armour_is_never_disposable(self):
        superior = item(
            "body", 37, 1, known=True, fully_known=True,
            is_equipment=True, ac=5, to_a=3,
        )
        same_base = item(
            "a", 37, 1, known=False, is_equipment=True,
            pseudo_feeling="average",
        )
        different_base = replace(same_base, slot="b", sval=2)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[same_base, different_base],
            equipment=[superior, self._lantern()],
        )
        policy = HengbotPolicy()

        self.assertFalse(
            policy._is_disposable_dominated_armour(snap, same_base)
        )
        self.assertFalse(
            policy._is_disposable_dominated_armour(snap, different_base)
        )

    def test_does_not_withdraw_dominated_armour_when_pack_is_full(self):
        superior = store_item(
            "a", 37, 1, name="superior armour", known=True,
            fully_known=True, is_equipment=True, ac=10, to_a=5,
        )
        inferior = store_item(
            "b", 37, 1, name="inferior armour", known=True,
            fully_known=True, is_equipment=True, ac=5, to_a=1,
        )
        full_pack = [
            item(chr(ord("a") + index), 1, index, known=True)
            for index in range(PACK_CAPACITY)
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=full_pack,
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_HOME, items=[superior, inferior]),
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page(snap.store.items)
        policy._equipment_catalog.observe_home_page(
            snap.store.items, allow_wrap=True
        )
        policy._home_disposal_pass = True

        self.assertIsNone(policy._home_dominated_disposal_key(snap))
        self.assertIsNone(policy._pending_disposal_item)
        self.assertIsNone(policy._home_atomic_withdraw_pending)

    def test_sells_dominated_armour_at_armoury(self):
        inferior = item("a", 37, 1, known=True, is_equipment=True, ac=1)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[inferior],
            equipment=[self._lantern()],
            store=StoreState(store_type=STORE_ARMOURY, items=[]),
        )
        policy = HengbotPolicy()
        policy._pending_disposal_slot = "a"
        policy._pending_disposal_item = policy._item_signature(inferior)
        self.assertEqual(_public_shop_inner(self, policy, snap), "{a@0\r")

    def test_destroys_dominated_armour_after_armoury_refuses(self):
        inferior = item("a", 37, 1, known=True, is_equipment=True, ac=1)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[inferior],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._pending_disposal_slot = "a"
        policy._pending_disposal_item = policy._item_signature(inferior)
        policy._disposal_store_attempts.add(STORE_ARMOURY)
        self.assertEqual(policy.choose_key(snap), "01ka")
        self.assertEqual(
            policy.last_reason, "equipment:destroy-unsellable-dominated"
        )

    def test_completed_dominated_disposal_releases_idle_home_candidate_latch(self):
        inferior = item("a", 37, 1, known=True, is_equipment=True, ac=1)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[],
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        policy._equipment_catalog.home_scan_complete = True
        policy._home_candidate_waiting = True
        policy._pending_disposal_slot = inferior.slot
        policy._pending_disposal_item = policy._item_signature(inferior)
        policy._destroy_pending = True

        self.assertIsNone(policy._town_destroy_key(snap))
        self.assertFalse(policy._home_candidate_waiting)
        self.assertEqual(policy.last_reason, "equipment:destroy-complete")

class TownMapNightRoutingTest(unittest.TestCase):
    def _outpost(self):
        from hengbot.town_maps import find_outpost_map, parse_town_map

        path = find_outpost_map(Path(__file__).resolve().parent.parent)
        if path is None:
            self.skipTest("Outpost map not found")
        return parse_town_map(path)

    def _night_snapshot(self, town_map):
        # Night in the Outpost: only the player's small light radius and the
        # REMEMBER-marked store entrances are emitted; the long route between is
        # dark (absent from the snapshot).
        grids = {}
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                p = Position(31 + dy, 150 + dx)
                grids[p] = grid(p.y, p.x)
        for store_type, pos in town_map.stores.items():
            grids[pos] = GridState(
                position=pos, known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=store_type,
            )
        return Snapshot(
            player(31, 150, hp=139, max_hp=139, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=town_map.width,
            height=town_map.height,
            town_flag=True,
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)
            ],
        )

    def test_static_map_lets_the_bot_route_to_a_store_at_night(self):
        town_map = self._outpost()
        snap = self._night_snapshot(town_map)
        # Without the static map the dark gap is un-routable → it explores/wanders.
        without = HengbotPolicy(town_map=None)
        without.choose_key(snap)
        self.assertNotEqual(without.last_reason, "shop:approach")
        # With it, the bot uses the store landmark for native travel.
        with_map = HengbotPolicy(town_map=town_map)
        with_map._home_knowledge_scan_requested = True
        self.assertEqual(with_map.choose_key(snap), "\x1b`n(.")
        self.assertEqual(with_map.last_reason, "shop:travel")

class WildernessSafetyTest(unittest.TestCase):
    def _wild_grids(self):
        return {Position(10, x): grid(10, x) for x in range(8, 13)}

    def test_open_wilderness_detected_from_the_town_flag(self):
        snap = Snapshot(
            player(10, 10), self._wild_grids(), [], floor_key=(0, 0, 0), town_flag=False
        )
        self.assertFalse(snap.in_town)
        self.assertTrue(snap.on_open_wilderness)

    def test_town_flag_true_is_in_town_not_wilderness(self):
        snap = Snapshot(
            player(10, 10), self._wild_grids(), [], floor_key=(0, 0, 0), town_flag=True
        )
        self.assertTrue(snap.in_town)
        self.assertFalse(snap.on_open_wilderness)

    def test_town_pathfinding_rejects_an_ordinary_border_exit(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(3)
            for x in range(1, 4)
        }
        snap = Snapshot(
            player(1, 2),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=5,
            height=5,
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        self.assertNotIn(Position(0, 1), policy._walkable_neighbors(snap, snap.player.position))

    def test_town_pathfinding_allows_a_border_dungeon_entrance(self):
        grids = {
            Position(1, 2): grid(1, 2),
            Position(0, 1): grid(0, 1, entrance=True),
        }
        snap = Snapshot(
            player(1, 2),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=5,
            height=5,
            town_flag=True,
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        self.assertIn(Position(0, 1), policy._walkable_neighbors(snap, snap.player.position))

    def test_legacy_snapshot_without_flag_uses_the_surface_heuristic(self):
        # town_flag None (older emitter) → the (0,0) surface is treated as town.
        snap = Snapshot(player(10, 10), self._wild_grids(), [], floor_key=(0, 0, 0))
        self.assertTrue(snap.in_town)
        self.assertFalse(snap.on_open_wilderness)

    def test_flees_a_wilderness_monster_instead_of_fighting(self):
        grids = self._wild_grids()
        grids[Position(10, 11)] = grid(10, 11, monster=True)
        mon = hostile(1, 10, 11, hp=40, max_hp=40)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            grids,
            [mon],
            floor_key=(0, 0, 0),
            town_flag=False,
        )
        pol = HengbotPolicy()
        key = pol.choose_key(snap)
        self.assertEqual(pol.last_reason, "wilderness:flee")
        self.assertNotEqual(key, "6")  # never step east INTO the adjacent monster

    def test_distant_or_sleeping_monsters_do_not_block_global_map(self):
        distant = replace(hostile(1, 10, 30), distance=21)
        sleeping = replace(hostile(2, 10, 11), asleep=True)
        snap = Snapshot(
            player(10, 10), self._wild_grids(), [distant, sleeping],
            floor_key=(0, 0, 0), town_flag=False,
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "<")
        self.assertEqual(pol.last_reason, "wilderness:enter-global")

    def test_enters_global_map_from_safe_local_wilderness(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            self._wild_grids(),
            [],
            floor_key=(0, 0, 0),
            town_flag=False,
            inventory=[recall],
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "<")
        self.assertEqual(pol.last_reason, "wilderness:enter-global")

    def test_routes_on_global_map_and_enters_town(self):
        wilderness = WildernessMap(("#####", "#*1.#", "#####"))
        observed = {Position(1, 1): grid(1, 1)}
        travelling = Snapshot(
            player(1, 1), observed, [], floor_key=(0, 0, 0),
            width=5, height=3, town_flag=False,
        )
        pol = HengbotPolicy(wilderness_map=wilderness)
        self.assertEqual(pol.choose_key(travelling), "6")
        self.assertEqual(pol.last_reason, "wilderness:global-travel")

        at_town = replace(travelling, player=player(1, 2))
        self.assertEqual(pol.choose_key(at_town), ">")
        self.assertEqual(pol.last_reason, "wilderness:enter-town")

    def test_gridless_measured_global_map_routes_and_enters_town(self):
        rows = ["." * 99 for _ in range(66)]
        rows[48] = f"{rows[48][:5]}1{rows[48][6:]}"
        wilderness = WildernessMap(tuple(rows))
        measured = Snapshot(
            player(48, 5), {}, [], floor_key=(0, 0, 0),
            width=99, height=66, town_flag=False, town_id=-1, town_index=0,
        )
        pol = HengbotPolicy(wilderness_map=wilderness)

        self.assertEqual(pol.choose_key(measured), ">")
        self.assertEqual(pol.last_reason, "wilderness:enter-town")

        non_town = replace(measured, player=player(48, 4))
        routing_key = pol.choose_key(non_town)
        self.assertEqual(routing_key, "6")
        self.assertNotEqual(routing_key, ">")
        self.assertEqual(pol.last_reason, "wilderness:global-travel")

    def test_gridless_global_map_without_route_stops_safely(self):
        wilderness = WildernessMap(("###", "#1#", "###"))
        stranded = Snapshot(
            player(0, 0), {}, [], floor_key=(0, 0, 0),
            width=3, height=3, town_flag=False, town_id=-1, town_index=0,
        )
        pol = HengbotPolicy(wilderness_map=wilderness)

        self.assertEqual(pol.choose_key(stranded), WAIT_KEY)
        self.assertEqual(pol.last_reason, "wilderness:no-safe-route")
        self.assertIn(pol.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_global_route_prefers_road_and_never_uses_water(self):
        wilderness = WildernessMap((
            "#######",
            "#.._..#",
            "#*~~~1#",
            "#*****#",
            "#######",
        ))
        pos = Position(2, 1)
        keys = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
                "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
        visited = []
        for _ in range(20):
            key = wilderness.next_key_to_town(pos.y, pos.x)
            if key == ">":
                break
            self.assertIn(key, keys)
            dy, dx = keys[key]
            pos = Position(pos.y + dy, pos.x + dx)
            visited.append(wilderness.rows[pos.y][pos.x])
        self.assertEqual((pos.y, pos.x), (2, 5))
        self.assertNotIn("_", visited)
        self.assertNotIn("~", visited)

    def test_town_wander_never_steps_onto_the_border_ring(self):
        # A small walled town; from an interior tile the least-visited-neighbour
        # wander must pick an interior tile, never a border tile (which would exit
        # into the open wilderness).
        grids = {}
        for y in range(0, 5):
            for x in range(0, 7):
                grids[Position(y, x)] = grid(y, x)
        snap = Snapshot(
            player(2, 1), grids, [], floor_key=(0, 0, 0), width=7, height=5, town_flag=True
        )
        pol = HengbotPolicy()
        pol._build_grid_index(snap)
        pol._observe(snap)
        step = pol._least_visited_neighbor(snap)
        self.assertIsNotNone(step)
        self.assertFalse(
            pol._on_town_border(snap, step), f"wandered onto border tile {step}"
        )

    def test_on_town_border_only_flags_the_ring_in_a_town(self):
        grids = {Position(0, 0): grid(0, 0)}
        town = Snapshot(
            player(2, 2), grids, [], floor_key=(0, 0, 0), width=7, height=5, town_flag=True
        )
        pol = HengbotPolicy()
        self.assertTrue(pol._on_town_border(town, Position(0, 3)))  # top edge
        self.assertTrue(pol._on_town_border(town, Position(4, 3)))  # bottom edge
        self.assertTrue(pol._on_town_border(town, Position(2, 6)))  # right edge
        self.assertFalse(pol._on_town_border(town, Position(2, 3)))  # interior
        # Not a town → the ring is not special (dungeons have their own walls).
        dungeon = Snapshot(
            player(2, 2), grids, [], floor_key=(1, 5, 0), width=7, height=5
        )
        self.assertFalse(pol._on_town_border(dungeon, Position(0, 3)))

    def test_on_town_border_does_not_cache_dungeon_cells(self):
        dungeon = Snapshot(
            player(2, 2),
            {Position(0, 0): grid(0, 0)},
            [],
            floor_key=(1, 5, 0),
            width=7,
            height=5,
        )
        pol = HengbotPolicy()
        pol._begin_map_predicate_cache(dungeon)

        self.assertFalse(pol._on_town_border(dungeon, Position(0, 3)))
        self.assertEqual(pol._town_border_cache, {})

    def test_does_not_shop_or_explore_on_the_wilderness(self):
        # A store tile is visible but we are on an open wilderness tile, not the
        # town — survival overrides the town shopping routine.
        grids = self._wild_grids()
        grids[Position(10, 12)] = GridState(
            position=Position(10, 12), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_GENERAL,
        )
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100, gold=1000),
            grids,
            [],
            floor_key=(0, 0, 0),
            town_flag=False,
        )
        pol = HengbotPolicy()
        pol.choose_key(snap)
        self.assertTrue(pol.last_reason.startswith("wilderness"), pol.last_reason)

class TownRecallReturnTest(unittest.TestCase):
    def _ready_town(
        self, deepest, target, recall_dungeon, angband_unlocked=False, recall_depth=0
    ):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=9),  # teleport
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=9),  # cure critical
        ]
        snap = Snapshot(
            player(10, 10, hp=255, max_hp=255, gold=2000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            inventory=inv,
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)],
            recall_dungeon_id=recall_dungeon,
            recall_depth=recall_depth,
            angband_recall_unlocked=angband_unlocked,
        )
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        pol._deepest_level = deepest
        pol._target_dungeon_id = target
        pol._char_dump_done_this_visit = True  # past the pre-dive dump for recall tests
        return pol, snap

    def test_writes_a_character_dump_before_the_first_recall_of_a_visit(self):
        pol, snap = self._ready_town(8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True)
        pol._char_dump_done_this_visit = False  # a fresh town visit
        self.assertEqual(pol._town_special_key(snap), CHARACTER_DUMP_MACRO)
        self.assertEqual(pol.last_reason, "town:character-dump")
        # Dump written -> the very next decision commits to the recall.
        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-angband")

    def test_periodic_dump_waits_for_quiet_exploration_and_emits_once(self):
        pol = HengbotPolicy()
        quiet = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 5, 0),
        )
        pol.request_character_dump()
        pol.last_reason = "melee"
        self.assertEqual(pol._periodic_character_dump_key(quiet, "6"), "6")
        pol.last_reason = "explore"
        self.assertEqual(
            pol._periodic_character_dump_key(quiet, "6"), CHARACTER_DUMP_MACRO
        )
        pol.last_reason = "explore"
        self.assertEqual(pol._periodic_character_dump_key(quiet, "6"), "6")

    def test_periodic_save_rides_the_dump_safe_filler_path_with_own_reason(self):
        pol = HengbotPolicy()
        quiet = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 5, 0),
        )
        pol.request_game_save()
        pol.request_character_dump()
        pol.last_reason = "melee"
        self.assertEqual(pol._periodic_game_save_key(quiet, "6"), "6")
        pol.last_reason = "explore"
        self.assertEqual(pol._periodic_game_save_key(quiet, "6"), "\x13")
        self.assertEqual(pol.last_reason, "periodic:game-save")
        pol.last_reason = "explore"
        self.assertEqual(
            pol._periodic_character_dump_key(quiet, "6"), CHARACTER_DUMP_MACRO
        )
        self.assertEqual(pol.last_reason, "periodic:character-dump")

    def test_same_tick_periodic_requests_both_reach_game_in_town_once(self):
        pol, town = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pol.request_game_save()
        pol.request_character_dump()

        first = pol.choose_key(town)
        first_reason = pol.last_reason
        second = pol.choose_key(town)
        second_reason = pol.last_reason
        third = pol.choose_key(town)

        self.assertEqual(first, "\x13")
        self.assertEqual(first_reason, "periodic:game-save")
        self.assertEqual(second, CHARACTER_DUMP_MACRO)
        self.assertEqual(second_reason, "periodic:character-dump")
        self.assertNotIn(third, {"\x13", CHARACTER_DUMP_MACRO})

    def test_same_tick_periodic_requests_both_reach_game_in_dungeon_once(self):
        pol = HengbotPolicy()
        quiet = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 5, 0),
        )
        pol.request_game_save()
        pol.request_character_dump()

        posted = []
        for _ in range(3):
            pol.last_reason = "explore"
            key = pol._periodic_game_save_key(quiet, "6")
            posted.append(pol._periodic_character_dump_key(quiet, key))

        self.assertEqual(posted.count("\x13"), 1)
        self.assertEqual(posted.count(CHARACTER_DUMP_MACRO), 1)

    def test_unsafe_periodic_requests_post_neither_and_remain_outstanding(self):
        enemy = hostile(1, 10, 12)
        visible_hostile = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 12): grid(10, 12, monster=True),
            },
            [enemy],
            floor_key=(1, 5, 0),
        )
        town = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )[1]
        unsafe_snapshots = (
            visible_hostile,
            replace(
                visible_hostile,
                visible_monsters=[hostile(2, 10, 11)],
                grids={
                    Position(10, 10): grid(10, 10),
                    Position(10, 11): grid(10, 11, monster=True),
                },
            ),
            replace(town, store=StoreState(STORE_GENERAL, [])),
            replace(town, player=replace(town.player, blind=True)),
            replace(town, player=replace(town.player, confused=True)),
            replace(town, player=replace(town.player, recalling=True)),
        )

        for snapshot in unsafe_snapshots:
            with self.subTest(snapshot=snapshot):
                pol = HengbotPolicy()
                pol.request_game_save()
                pol.request_character_dump()

                key = pol.choose_key(snapshot)

                self.assertNotIn(key, {"\x13", CHARACTER_DUMP_MACRO})
                self.assertTrue(pol._periodic_save_requested)
                self.assertTrue(pol._periodic_dump_requested)

    def test_periodic_dump_never_emits_in_store_or_adjacent_combat(self):
        enemy = hostile(1, 10, 11)
        combat = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, monster=True),
            },
            [enemy],
            floor_key=(1, 5, 0),
        )
        town = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )[1]
        store = replace(town, store=StoreState(STORE_GENERAL, []))
        for snapshot in (combat, store):
            pol = HengbotPolicy()
            pol.request_character_dump()
            pol.last_reason = "explore"
            self.assertEqual(pol._periodic_character_dump_key(snapshot, "6"), "6")

    def test_periodic_dump_emits_during_safe_town_travel(self):
        pol, town = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pol.request_character_dump()
        pol.last_reason = "fixedquest:q2-travel"

        self.assertEqual(
            pol._periodic_character_dump_key(town, "6"), CHARACTER_DUMP_MACRO
        )
        self.assertEqual(pol.last_reason, "periodic:character-dump")

    def test_periodic_dump_emits_during_safe_q2_residual_patrol(self):
        pol = HengbotPolicy()
        snapshot = Snapshot(
            player(12, 62),
            {Position(12, 62): grid(12, 62)},
            [],
            floor_key=(0, 15, 2),
        )
        pol.request_character_dump()
        pol.last_reason = "quest-strategy:q2-residual-252-sweep"

        self.assertEqual(
            pol._periodic_character_dump_key(snapshot, "4"),
            CHARACTER_DUMP_MACRO,
        )
        self.assertEqual(pol.last_reason, "periodic:character-dump")

    def test_recall_depth_seeds_deepest_after_restart(self):
        # A restart zeroes the in-memory watermark. The save-backed recall depth
        # (emitted every snapshot) must restore it, or the resumed bot forgets it
        # has been to 5F and walks in from the entrance instead of recalling.
        pol, snap = self._ready_town(
            0, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE, recall_depth=RECALL_MIN_DEPTH
        )
        pol._observe(snap)
        self.assertGreaterEqual(pol._deepest_level, RECALL_MIN_DEPTH)
        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-yeek-cave")

    def test_recall_depth_only_raises_never_lowers_watermark(self):
        # recall_depth seeds via max(): a deeper in-session watermark still wins,
        # so a stale/smaller recall_depth never demotes a genuinely deep run.
        pol, snap = self._ready_town(
            8, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE, recall_depth=3
        )
        pol._observe(snap)
        self.assertEqual(pol._deepest_level, 8)

    def test_recalls_into_a_deep_yeek_cave_run(self):
        pol, snap = self._ready_town(RECALL_MIN_DEPTH, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE)
        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-yeek-cave")

    def test_six_scrolls_permit_tenth_floor_yeek_recall_departure(self):
        pol, snap = self._ready_town(
            10, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE, recall_depth=10
        )
        snap = replace(
            snap,
            inventory=[
                replace(
                    entry,
                    count=(
                        6
                        if entry.tval == TVAL_SCROLL
                        and entry.sval == SV_SCROLL_WORD_OF_RECALL
                        else 20
                    ),
                )
                for entry in snap.inventory
            ] + [item("i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20)],
            dungeon_recall_depths={DUNGEON_YEEK_CAVE: 10},
        )

        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-yeek-cave")

    def test_five_scrolls_refuse_tenth_floor_yeek_recall_departure(self):
        pol, snap = self._ready_town(
            10, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE, recall_depth=10
        )
        snap = replace(
            snap,
            inventory=[
                replace(
                    entry,
                    count=(
                        5
                        if entry.tval == TVAL_SCROLL
                        and entry.sval == SV_SCROLL_WORD_OF_RECALL
                        else 20
                    ),
                )
                for entry in snap.inventory
            ] + [item("i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20)],
            dungeon_recall_depths={DUNGEON_YEEK_CAVE: 10},
        )

        self.assertNotEqual(pol._town_special_key(snap), "rra")
        self.assertNotEqual(pol.last_reason, "town:recall-to-yeek-cave")

    def test_yeek_recall_ignores_the_games_different_default_destination(self):
        pol, snap = self._ready_town(
            10, DUNGEON_YEEK_CAVE, DUNGEON_ANGBAND, recall_depth=20
        )
        snap = replace(
            snap,
            inventory=[
                replace(
                    entry,
                    count=(
                        6
                        if entry.tval == TVAL_SCROLL
                        and entry.sval == SV_SCROLL_WORD_OF_RECALL
                        else 20
                    ),
                )
                for entry in snap.inventory
            ] + [item("i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20)],
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE, DUNGEON_ANGBAND),
            dungeon_recall_depths={DUNGEON_YEEK_CAVE: 10},
        )

        self.assertEqual(
            pol._town_recall_destination(snap),
            ("yeek-cave", DUNGEON_YEEK_CAVE),
        )
        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-yeek-cave")

    def test_shallow_run_walks_to_the_entrance_not_recall(self):
        pol, snap = self._ready_town(RECALL_MIN_DEPTH - 1, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE)
        self.assertIsNone(pol._town_special_key(snap))

    def test_recalls_to_angband_once_unlocked(self):
        pol, snap = self._ready_town(8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True)
        self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-angband")

    def test_exhausted_identify_charges_and_home_catalog_defer_to_recall(self):
        # Live 2026-07-28 shape: all hard supplies are ready, the Magic shop
        # cannot top up the usable Identify staves, and Home's bounded scan
        # ended with two incomplete items.  Both are next-visit work.
        pol, snap = self._ready_town(
            STAFF_IDENTIFY_MIN_DEPTH,
            DUNGEON_ANGBAND,
            DUNGEON_ANGBAND,
            angband_unlocked=True,
        )
        snap = replace(
            snap,
            inventory=[
                replace(snap.inventory[0], count=10),
                replace(snap.inventory[1], count=15),
                replace(snap.inventory[2], count=10),
                replace(snap.inventory[3], count=10),
                replace(snap.inventory[4], count=10),
                item(
                    "s",
                    TVAL_STAFF,
                    SV_STAFF_IDENTIFY,
                    charges=9,
                    name="Staff of Identify",
                ),
            ],
        )
        pol._town_store_attempted[STORE_MAGIC] = snap.turn
        pol._town_visit_ledger.blocked_stores.add(STORE_HOME)
        pol._equipment_catalog.home_scan_complete = False
        pol._home_candidate_waiting = False

        with patch.object(pol, "_home_available", return_value=True), patch.object(
            pol, "_equipment_departure_ready", return_value=True
        ), patch.object(pol, "_dungeon_entry_allowed", return_value=True):
            self.assertTrue(pol._identify_staff_ready(snap))
            self.assertTrue(
                pol._town_departure_ready(snap),
                pol._departure_block_state(snap),
            )
            self.assertEqual(pol._town_special_key(snap), "rra")

        self.assertEqual(pol.last_reason, "town:recall-to-angband")

    def test_pending_surplus_shovel_does_not_block_or_cancel_recall(self):
        pol, snap = self._ready_town(
            23,
            DUNGEON_ANGBAND,
            DUNGEON_ANGBAND,
            angband_unlocked=True,
        )
        shovel = replace(
            item(
                "s",
                TVAL_DIGGING,
                SV_DIGGING_SHOVEL,
                known=True,
                fully_known=True,
                name="Dwarven Shovel of Digging",
            ),
            damage_dice_num=1,
            damage_dice_sides=3,
            pval=6,
            to_h=6,
            to_d=4,
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=7452),
            inventory=[*snap.inventory, shovel],
            dungeon_recall_depths={DUNGEON_ANGBAND: 1},
        )
        pol._town_store_attempted[STORE_HOME] = snap.turn
        self.assertIsNone(pol._find_home_deposit(snap))
        with patch.object(
            pol, "_recall_town_departure_conjuncts",
            return_value={"test_ready": True},
        ), patch.object(pol, "_dungeon_entry_allowed", return_value=True):
            self.assertEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-angband")
        self.assertIn(STORE_HOME, pol._town_store_attempted)

        recalling = replace(
            snap, player=replace(snap.player, recalling=True), turn=snap.turn + 1
        )
        with patch.object(pol, "_activate_loadout_depth_fallback", return_value=None, create=True):
            self.assertIsNone(pol._town_cancel_unsafe_recall_key(recalling))
        self.assertNotEqual(pol.last_reason, "town:cancel-unready-recall")

    def test_active_recall_ignores_new_pending_surplus_deposit(self):
        pol, snap = self._ready_town(
            23,
            DUNGEON_ANGBAND,
            DUNGEON_ANGBAND,
            angband_unlocked=True,
        )
        recalling = replace(snap, player=replace(snap.player, recalling=True))
        with patch.object(
            pol, "_activate_loadout_depth_fallback", return_value=None, create=True
        ), patch.object(pol, "_find_home_deposit", return_value=object()):
            self.assertIsNone(pol._town_cancel_unsafe_recall_key(recalling))
        self.assertNotEqual(pol.last_reason, "town:cancel-unready-recall")

    def test_recall_to_34_refuses_without_chaos_and_names_requirement(self):
        pol, snap = self._ready_town(
            34, DUNGEON_ANGBAND, DUNGEON_ANGBAND,
            angband_unlocked=True, recall_depth=34,
        )
        snap = replace(
            snap, dungeon_recall_depths={DUNGEON_ANGBAND: 34}
        )
        with patch.object(
            pol, "_recall_town_departure_conjuncts",
            return_value={"test_ready": True},
        ), patch.object(pol, "_town_claims_active", return_value=False), patch.object(
            pol, "_activate_safe_recall_fallback", return_value=None
        ):
            self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
        self.assertEqual(
            pol.last_reason,
            "town:blocked:depth-gate:destination-34:missing-resist_chaos",
        )

    def test_recall_to_34_with_chaos_posts_exact_derived_characters(self):
        pol, snap = self._ready_town(
            34, DUNGEON_ANGBAND, DUNGEON_ANGBAND,
            angband_unlocked=True, recall_depth=34,
        )
        snap = replace(
            snap,
            player=replace(snap.player, abilities=frozenset({"resist_chaos"})),
            dungeon_recall_depths={DUNGEON_ANGBAND: 34},
            inventory=[
                replace(carried, count=99) if carried.is_recall_scroll else carried
                for carried in snap.inventory
            ],
        )
        with patch.object(
            pol, "_recall_town_departure_conjuncts",
            return_value={"test_ready": True},
        ), patch.object(
            pol, "_equipment_departure_ready", return_value=True
        ), patch.object(pol, "_combat_weapon_ready", return_value=True):
            self.assertTrue(
                pol._dungeon_entry_allowed(
                    snap, via_recall=True, destination_depth=34
                )
            )
            self.assertEqual(pol._town_special_key(snap), "rra", pol.last_reason)
        self.assertEqual(pol.last_reason, "town:recall-to-angband")

    def test_shallow_recall_with_met_requirements_keeps_exact_characters(self):
        pol, snap = self._ready_town(
            19, DUNGEON_ANGBAND, DUNGEON_ANGBAND,
            angband_unlocked=True, recall_depth=19,
        )
        snap = replace(
            snap, dungeon_recall_depths={DUNGEON_ANGBAND: 19}
        )
        with patch.object(
            pol, "_recall_town_departure_conjuncts",
            return_value={"test_ready": True},
        ), patch.object(pol, "_equipment_departure_ready", return_value=True):
            self.assertEqual(pol._town_special_key(snap), "rra")

    def test_recall_stock_still_blocks_entry_when_depth_gate_is_met(self):
        pol, snap = self._ready_town(
            34, DUNGEON_ANGBAND, DUNGEON_ANGBAND,
            angband_unlocked=True, recall_depth=34,
        )
        snap = replace(
            snap,
            player=replace(snap.player, abilities=frozenset({"resist_chaos"})),
            inventory=[item for item in snap.inventory if not item.is_recall_scroll],
        )
        self.assertFalse(
            pol._dungeon_entry_allowed(
                snap, via_recall=False, destination_depth=34
            )
        )

    def test_resume_preserves_an_already_active_town_recall(self):
        pol, snap = self._ready_town(
            23,
            DUNGEON_ANGBAND,
            DUNGEON_ANGBAND,
            angband_unlocked=True,
            recall_depth=23,
        )
        recalling = replace(snap, player=replace(snap.player, recalling=True))

        # A fresh policy has no Home catalog yet. That startup incompleteness
        # must not cancel the engine-owned recall before prime/follow attach.
        self.assertEqual(pol.choose_key(recalling), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:wait-recall")
        self.assertTrue(pol._startup_town_recall)

    def test_town_recall_does_not_reread_on_stale_or_consumed_snapshot(self):
        # Live 2026-07-23 regression: redraws at one game turn repeatedly showed
        # recalling=False, so seven macros consumed five scrolls before the flag
        # stabilized.  Both the unchanged command-turn snapshot and a reduced
        # stack are confirmation states, never permission to read again.
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        self.assertEqual(pol._town_special_key(snap), "rra")

        self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:await-recall-confirmation")

        consumed = replace(
            snap,
            player=replace(snap.player, position=Position(10, 11)),
            inventory=[replace(snap.inventory[0], count=8), *snap.inventory[1:]],
            turn=snap.turn + 8,
        )
        self.assertEqual(pol._town_special_key(consumed), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:await-recall-confirmation")

    def test_rejected_town_recall_retries_after_turn_advances_unconsumed(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        self.assertEqual(pol._town_special_key(snap), "rra")

        rejected = replace(snap, turn=snap.turn + 1)
        self.assertEqual(pol._town_special_key(rejected), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-angband")

    def test_departure_block_telemetry_names_failed_gate_and_values(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        conjuncts = pol._recall_town_departure_conjuncts(snap)
        conjuncts["light_ready"] = False
        pol._recall_town_departure_conjuncts = lambda _snapshot: dict(conjuncts)

        with patch.object(pol, "_town_claims_active", return_value=False):
            self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:departure-unsatisfiable")
        self.assertEqual(pol._town_wander_streak, 0)
        block = pol.departure_block_state()
        self.assertEqual(block["gate"], "town_departure_ready")
        self.assertEqual(block["failed"], ["light_ready"])
        self.assertFalse(block["values"]["light_ready"])
        self.assertEqual(
            block["diagnostics"]["free_pack_slots"], PACK_CAPACITY - len(snap.inventory)
        )

    def test_departure_block_telemetry_names_identify_staff_leaf(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pol._identify_staff_ready = lambda _snapshot: False

        pol._departure_block = pol._departure_block_state(snap)

        self.assertIn("identify_staff_ready", pol.departure_block_state()["failed"])

    def test_each_departure_conjunct_is_the_exact_failed_telemetry_leaf(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        baseline = pol._recall_town_departure_conjuncts(snap)
        self.assertTrue(all(baseline.values()), baseline)
        for failed_leaf in baseline:
            with self.subTest(failed_leaf=failed_leaf):
                candidate = dict(baseline)
                candidate[failed_leaf] = False
                current, current_snap = self._ready_town(
                    8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
                )
                current._recall_town_departure_conjuncts = (
                    lambda _snapshot, values=candidate: dict(values)
                )
                with patch.object(current, "_town_claims_active", return_value=False):
                    self.assertEqual(current.choose_key(current_snap), WAIT_KEY)
                self.assertEqual(current.last_reason, "town:blocked:departure-unsatisfiable")
                block = current.departure_block_state()
                self.assertEqual(block["values"], candidate)
                self.assertEqual(block["failed"], [failed_leaf])

    def test_surplus_device_has_the_departure_blocking_organization_owner(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            inventory=[*snap.inventory, item("m", TVAL_STAFF, 8, count=2, charges=11)],
        )
        pol._town_need_supplier_reachable = lambda _snapshot, _need: True

        surplus = pol._find_town_organization_surplus(snap)
        self.assertIsNotNone(surplus)
        self.assertEqual(surplus.slot, "m")
        needs = pol._enumerate_town_needs(snap)
        self.assertIn("organization-sale", [need.category for need in needs])
        specs = {spec.category: spec for spec in pol._town_need_registry()}
        self.assertTrue(specs["organization-sale"].departure_blocking)

    def test_cross_town_identify_capture_starts_travel_instead_of_visible_stop(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=9193),
            town_id=0,
            visited_town_ids=(0, 1, 2, 3),
        )
        pol._identification_need = "normal"
        pol._home_candidate_waiting = True
        pol._town_visit_ledger.nonhome_attempted_without_effect[
            STORE_ALCHEMIST
        ] = pol._town_observable_effect_state(snap)
        pol._town_visit_ledger.drift_warnings.append(
            "drift:alchemist:identification-source"
        )
        pol._town_visit_ledger.shelf_observations[
            (STORE_ALCHEMIST, "identification-source:normal")
        ] = ()
        pol._observed_departure_prices["identification-source:normal"] = (20, 1)
        with patch.object(pol, "_town_departure_ready", return_value=False), patch.object(
            pol,
            "_cross_town_shortages",
            return_value=[("identification-source:normal", 1)],
        ), patch.object(pol, "_town_teleport_key", return_value="6ma") as teleport:
            pol._town_special_key(snap)
        teleport.assert_called_once()
        self.assertEqual(pol.last_reason, "town:cross-town-shopping:travel-1")
        self.assertNotEqual(pol.last_reason, "town:blocked:departure-unsatisfiable")
        self.assertEqual(pol.cross_town_shopping_state()["candidate_order"], [1, 2, 3])

    @staticmethod
    def _full_identify_items(count=2):
        return [
            item(
                chr(ord("p") + index), 45, index + 1,
                name=f"ego ring {index}", known=True, is_equipment=True,
                is_ego=True,
            )
            for index in range(count)
        ]

    def test_two_carried_full_identify_items_plan_morivant_trip(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=3600),
            inventory=snap.inventory + self._full_identify_items(),
            town_id=0,
            visited_town_ids=(0, 2),
        )
        pol._identification_need = "full"
        with patch.object(pol, "_town_teleport_key", return_value="TO-MORIVANT"):
            self.assertEqual(pol._morivant_full_identify_key(snap), "TO-MORIVANT")
        self.assertEqual(pol.last_reason, "town:morivant-full-identify:travel-2")

    def test_two_home_full_identify_items_plan_trip_and_begin_batch_withdrawal(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        wares = [
            store_item(
                chr(ord("a") + index), 45, index + 1,
                name=f"home ego ring {index}", known=True,
                fully_known=False, is_equipment=True, is_ego=True,
            )
            for index in range(2)
        ]
        pol._equipment_catalog.observe_home_page(wares)
        pol._equipment_catalog.observe_home_page(wares)
        snap = replace(
            snap, player=replace(snap.player, gold=3600), town_id=0,
            visited_town_ids=(0, 2),
        )
        self.assertIsNone(pol._morivant_full_identify_key(snap))
        self.assertEqual(
            pol._morivant_full_identify.phase, "prepare-home"
        )
        home = replace(snap, store=StoreState(STORE_HOME, wares))
        self.assertEqual(pol._shop(home), LEAVE_STORE_KEY)
        self.assertEqual(pol.last_reason, "home:queue-batch-withdraw")

    def test_carried_and_home_full_identify_items_share_trip_threshold(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        carried = self._full_identify_items(1)[0]
        stored = store_item(
            "a", 45, 9, name="home ego ring", known=True,
            fully_known=False, is_equipment=True, is_ego=True,
        )
        pol._equipment_catalog.observe_home_page([stored])
        pol._equipment_catalog.observe_home_page([stored])
        snap = replace(
            snap, player=replace(snap.player, gold=3600),
            inventory=[*snap.inventory, carried], town_id=0,
            visited_town_ids=(0, 2),
        )
        self.assertIsNone(pol._morivant_full_identify_key(snap))
        self.assertEqual(
            set(pol._morivant_full_identify.target_signatures),
            {pol._item_signature(carried), pol._item_signature(stored)},
        )
        self.assertEqual(
            pol._morivant_full_identify.home_target_signatures,
            (pol._item_signature(stored),),
        )

    def test_morivant_temporary_deposit_round_trip_restores_ledger(self):
        pol = HengbotPolicy()
        targets = [
            store_item(
                "a", 45, 1, name="home ego one", known=True,
                fully_known=False, is_equipment=True, is_ego=True,
            ),
            store_item(
                "b", 45, 2, name="home ego two", known=True,
                fully_known=False, is_equipment=True, is_ego=True,
            ),
        ]
        filler = [item(chr(65 + index), TVAL_BOTTLE, index, name=f"filler {index}") for index in range(PACK_CAPACITY - 1)]
        signatures = tuple(pol._item_signature(target) for target in targets)
        expedition = policy_module.MorivantFullIdentifyExpedition(
            0, signatures, home_target_signatures=signatures,
            phase="prepare-home",
        )
        pol._morivant_full_identify = expedition
        pol._home_pending_batch.extend(signatures)
        home = Snapshot(
            player(10, 10, gold=3600), {Position(10, 10): grid(10, 10)}, [],
            inventory=filler, store=StoreState(STORE_HOME, targets),
            town_flag=True, town_id=0, visited_town_ids=(0, 2),
        )

        key = pol._morivant_home_item_key(home)
        self.assertTrue(key.startswith(SELL_KEY))
        deposited = filler[0]
        deposited_ware = store_item(
            "c", deposited.tval, deposited.sval, name=deposited.name
        )
        after_deposit = replace(
            home, inventory=filler[1:],
            store=StoreState(STORE_HOME, [*targets, deposited_ware]),
        )
        self.assertEqual(pol._morivant_home_item_key(after_deposit), LEAVE_STORE_KEY)
        self.assertEqual(
            expedition.temporary_deposits,
            [(pol._item_signature(deposited), 1)],
        )

        expedition.phase = "return-home"
        expedition.home_inflight = None
        pol._home_pending_batch.clear()
        with patch.object(pol, "_find_home_deposit", return_value=None):
            self.assertEqual(
                pol._morivant_home_item_key(after_deposit), LEAVE_STORE_KEY
            )
        restored = replace(
            after_deposit, inventory=[*after_deposit.inventory, deposited]
        )
        self.assertEqual(pol._morivant_home_item_key(restored), LEAVE_STORE_KEY)
        self.assertEqual(expedition.temporary_deposits, [])
        self.assertIsNone(pol._morivant_full_identify)

    def test_morivant_recall_scroll_ledger_blocks_every_dungeon_entry(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        recall = next(it for it in snap.inventory if it.is_recall_scroll)
        pol._morivant_full_identify = policy_module.MorivantFullIdentifyExpedition(
            0, (), temporary_deposits=[(pol._item_signature(recall), recall.count)],
            phase="restore-home",
        )

        self.assertFalse(
            pol._dungeon_entry_allowed(snap, via_recall=True, destination_depth=8)
        )
        pol._fundraising_mode = "mine"
        self.assertFalse(
            pol._dungeon_entry_allowed(snap, via_recall=False, destination_depth=1)
        )

    def test_missing_morivant_ledger_item_is_visible_bounded_and_releases_departure(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        missing = ("missing recall", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        pol._morivant_full_identify = policy_module.MorivantFullIdentifyExpedition(
            0, (), temporary_deposits=[(missing, 1)], phase="restore-home"
        )
        home = replace(snap, store=StoreState(STORE_HOME, []))

        self.assertEqual(pol._morivant_home_item_key(home), " ")
        self.assertEqual(pol._morivant_home_item_key(home), WAIT_KEY)
        self.assertIn("ledger-drop-missing", pol.last_reason)
        self.assertEqual(pol._morivant_home_item_key(home), LEAVE_STORE_KEY)
        self.assertIsNone(pol._morivant_full_identify)
        self.assertEqual(pol._town_special_key(snap), "rra")

    def test_one_carried_full_identify_item_keeps_existing_behavior(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=3600),
            inventory=snap.inventory + self._full_identify_items(1),
            town_id=0,
            visited_town_ids=(0, 2),
        )
        pol._identification_need = "full"
        with patch.object(pol, "_town_teleport_key") as travel:
            self.assertIsNone(pol._morivant_full_identify_key(snap))
        travel.assert_not_called()

    def test_morivant_full_identify_trip_requires_round_trip_and_one_service(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=2299),
            inventory=snap.inventory + self._full_identify_items(),
            town_id=0,
            visited_town_ids=(0, 2),
        )
        pol._identification_need = "full"
        with patch.object(pol, "_town_teleport_key") as travel:
            self.assertIsNone(pol._morivant_full_identify_key(snap))
        travel.assert_not_called()

    def test_unroutable_morivant_trip_resolves_and_town_still_departs(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=3600),
            inventory=snap.inventory + self._full_identify_items(),
            town_id=0,
            visited_town_ids=(0, 2),
        )
        pol._identification_need = "full"
        with patch.object(pol, "_town_teleport_key", return_value=None):
            self.assertIsNone(pol._morivant_full_identify_key(snap))
        self.assertIsNone(pol._morivant_full_identify)
        pol._identification_need = None
        departed = replace(
            snap,
            inventory=[
                carried
                for carried in snap.inventory
                if not carried.name.startswith("ego ring")
            ],
        )
        self.assertEqual(pol._town_special_key(departed), "rra")
        self.assertEqual(pol.last_reason, "town:recall-to-angband")

    def test_481_gold_morivant_capture_refuses_without_an_inn_approach_retry(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        targets = self._full_identify_items()
        inn = Position(snap.player.position.y, snap.player.position.x + 1)
        snap = replace(
            snap,
            player=replace(snap.player, gold=481),
            inventory=[*snap.inventory, *targets],
            grids={**snap.grids, inn: grid(inn.y, inn.x, building_type=0)},
            town_id=0,
            visited_town_ids=(0, 2),
        )
        pol._identification_need = "full"
        pol._build_grid_index(snap)
        pol._morivant_full_identify = policy_module.MorivantFullIdentifyExpedition(
            0, tuple(pol._item_signature(target) for target in targets)
        )

        self.assertIsNone(pol._morivant_full_identify_key(snap))
        self.assertNotEqual(pol.last_reason, "town:morivant-full-identify:travel-2")
        self.assertEqual(pol.last_reason, "town:teleport-refused-fare")
        self.assertIsNone(pol._morivant_full_identify)
        with patch.object(pol, "_town_teleport_key", wraps=pol._town_teleport_key) as travel:
            self.assertIsNone(pol._morivant_full_identify_key(snap))
        travel.assert_not_called()

    def test_morivant_library_uses_action_a_for_each_item_prompt(self):
        pol = HengbotPolicy()
        targets = self._full_identify_items()
        snap = Snapshot(
            player(10, 10, gold=3100),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, building_type=0),
            },
            [],
            inventory=targets,
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=2,
            visited_town_ids=(0, 2),
        )
        pol._identification_need = "full"
        pol._morivant_full_identify = policy_module.MorivantFullIdentifyExpedition(
            0, tuple(pol._item_signature(target) for target in targets)
        )
        dismiss = policy_module.FULL_IDENTIFY_DISMISS_SUFFIX
        with patch.object(pol, "_nearest_goal_step", return_value=Position(10, 11)):
            self.assertEqual(
                pol._morivant_full_identify_key(snap),
                "6ap" + dismiss + "aq" + dismiss + policy_module.LEAVE_STORE_KEY,
            )

    def test_carried_star_identify_scroll_remains_preferred(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        scroll = item("o", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, known=True)
        snap = replace(
            snap,
            player=replace(snap.player, gold=3600),
            inventory=snap.inventory + [scroll] + self._full_identify_items(),
            town_id=0,
            visited_town_ids=(0, 2),
        )
        with patch.object(pol, "_town_teleport_key") as travel:
            self.assertIsNone(pol._morivant_full_identify_key(snap))
        travel.assert_not_called()
        self.assertEqual(
            pol._town_item_processing_key(snap),
            "rop" + policy_module.FULL_IDENTIFY_DISMISS_SUFFIX,
        )

    def test_capture_affordable_identify_staff_vetoes_cross_town_expedition(self):
        """Rebuild the 20260731 incident's shelf and workflow evidence."""
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=9193),
            town_id=0,
            visited_town_ids=(0, 1, 2, 3),
            store=StoreState(
                STORE_MAGIC,
                [
                    StoreItem(
                        "i", "鑑定の杖 (4x 19回分)", 4,
                        TVAL_STAFF, SV_STAFF_IDENTIFY, 950,
                        charges=19, pval=19,
                    ),
                    StoreItem(
                        "j", "鑑定の杖 (2x 16回分)", 2,
                        TVAL_STAFF, SV_STAFF_IDENTIFY, 904,
                        charges=16, pval=16,
                    ),
                ],
            ),
        )
        pol._town_visit_ledger.need_attempts["identify-staff"] = 1
        pol._town_visit_ledger.drift_warnings.append(
            "drift:magic:identify-staff"
        )
        pol._town_store_attempted[STORE_MAGIC] = snap.turn
        pol._departure_blocking_town_needs = lambda _snapshot: [
            TownNeed(STORE_MAGIC, "identify-staff", "normal")
        ]
        pol._observe_departure_prices(snap)
        pol._observed_departure_prices["identify-staff"] = (904, 16)
        shortage = [("identify-staff", 20)]

        self.assertEqual(
            pol._cross_town_unobtainable_categories(snap, shortage), ()
        )
        with patch.object(pol, "_cross_town_shortages", return_value=shortage):
            self.assertIsNone(pol._cross_town_shopping_key(snap))
        self.assertIsNone(pol._cross_town_shopping)

    def test_observed_empty_supplier_proves_cross_town_stock_out(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=5000),
            town_id=0,
            visited_town_ids=(0, 1),
            store=StoreState(STORE_MAGIC, []),
        )
        pol._departure_blocking_town_needs = lambda _snapshot: [
            TownNeed(STORE_MAGIC, "identify-staff", "normal")
        ]
        pol._observe_departure_prices(snap)
        pol._observed_departure_prices["identify-staff"] = (904, 16)
        shortage = [("identify-staff", 20)]

        self.assertEqual(
            pol._cross_town_unobtainable_categories(snap, shortage),
            ("identify-staff",),
        )
        with patch.object(pol, "_cross_town_shortages", return_value=shortage), patch.object(
            pol, "_town_teleport_key", return_value="travel-1"
        ):
            self.assertEqual(pol._cross_town_shopping_key(snap), "travel-1")

    def test_visible_but_unaffordable_supplier_is_locally_unobtainable(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=903),
            store=StoreState(
                STORE_MAGIC,
                [
                    StoreItem(
                        "j", "鑑定の杖 (2x 16回分)", 2,
                        TVAL_STAFF, SV_STAFF_IDENTIFY, 904,
                        charges=16, pval=16,
                    )
                ],
            ),
        )
        pol._departure_blocking_town_needs = lambda _snapshot: [
            TownNeed(STORE_MAGIC, "identify-staff", "normal")
        ]
        pol._observe_departure_prices(snap)

        self.assertEqual(
            pol._cross_town_unobtainable_categories(
                snap, [("identify-staff", 20)]
            ),
            ("identify-staff",),
        )

    def test_consumed_need_reappearance_is_not_stock_absence(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pol._town_visit_ledger.satisfied_needs.add(
            (STORE_MAGIC, "identify-staff")
        )
        pol._town_visit_ledger.need_attempts["identify-staff"] = (
            TOWN_STOP_PASS_LIMIT
        )
        pol._town_visit_ledger.drift_warnings.append(
            "drift:magic:identify-staff"
        )
        pol._departure_blocking_town_needs = lambda _snapshot: [
            TownNeed(STORE_MAGIC, "identify-staff", "normal")
        ]

        self.assertEqual(
            pol._cross_town_unobtainable_categories(
                snap, [("identify-staff", 20)]
            ),
            (),
        )

    def test_cross_town_funds_failure_uses_ordinary_fundraising_mode(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=1019),
            town_id=0,
            visited_town_ids=(0, 1),
        )
        pol._observed_departure_prices["identification-source:normal"] = (20, 1)
        pol._identification_need = "normal"
        pol._town_visit_ledger.need_attempts["identification-source"] = 3
        pol._town_visit_ledger.shelf_observations[
            (STORE_ALCHEMIST, "identification-source:normal")
        ] = ()
        with patch.object(
            pol,
            "_cross_town_shortages",
            return_value=[("identification-source:normal", 1)],
        ):
            self.assertEqual(pol._cross_town_shopping_key(snap), WAIT_KEY)
        self.assertEqual(pol._fundraising_mode, "prepare")
        self.assertIsNone(pol._planned_mining_runs)
        self.assertIsNone(pol._cross_town_shopping)

        ordinary = HengbotPolicy()
        ordinary_snap = replace(snap, player=replace(snap.player, gold=100))
        self.assertTrue(ordinary._start_fundraising(ordinary_snap))
        self.assertEqual(
            (pol._fundraising_mode, pol._planned_mining_runs),
            (ordinary._fundraising_mode, ordinary._planned_mining_runs),
        )

    def test_cross_town_tries_each_visited_town_once_then_visible_stop_remains(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(
            snap,
            player=replace(snap.player, gold=5000),
            town_id=0,
            visited_town_ids=(0, 1, 2),
        )
        pol._observed_departure_prices["identification-source:normal"] = (20, 1)
        pol._identification_need = "normal"
        pol._town_visit_ledger.need_attempts["identification-source"] = 3
        pol._town_visit_ledger.shelf_observations[
            (STORE_ALCHEMIST, "identification-source:normal")
        ] = ()
        shortage = [("identification-source:normal", 1)]
        with patch.object(pol, "_cross_town_shortages", return_value=shortage), patch.object(
            pol, "_town_teleport_key", side_effect=lambda _snap, town: f"travel-{town}"
        ):
            self.assertEqual(pol._cross_town_shopping_key(snap), "travel-1")
            town1 = replace(snap, town_id=1)
            self.assertEqual(pol._cross_town_shopping_key(town1), "travel-2")
            town2 = replace(snap, town_id=2)
            self.assertIsNone(pol._cross_town_shopping_key(town2))
            self.assertEqual(pol._cross_town_shopping.tried_towns, [1, 2])
            self.assertIsNone(pol._cross_town_shopping_key(town2))

        pol._town_blocked_reason = "departure-unsatisfiable"
        self.assertEqual(pol._town_blocked_key(town2), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:departure-unsatisfiable")

    def test_opportunistic_need_does_not_trigger_cross_town_shopping(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        snap = replace(snap, town_id=0, visited_town_ids=(0, 1))
        pol._town_visit_ledger.need_attempts["ammo"] = 5
        with patch.object(pol, "_cross_town_shortages", return_value=[]):
            self.assertIsNone(pol._cross_town_shopping_key(snap))
        self.assertIsNone(pol._cross_town_shopping)

    def test_cross_town_expedition_never_weakens_recall_entry_invariant(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pol._cross_town_shopping = policy_module.CrossTownShoppingExpedition(
            0, ("recall",), {"recall": 20}, 1000, 1020, (1,), [1]
        )
        without_recall = replace(
            snap,
            inventory=[
                item for item in snap.inventory if not item.is_recall_scroll
            ],
        )
        self.assertFalse(
            pol._dungeon_entry_allowed(
                without_recall, via_recall=False, destination_depth=8
            )
        )

    def test_inert_home_identification_latch_is_cleared_before_recall(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pol._home_pending_item = ("stale", 23, 99)
        pol._identification_need = "stale-home-item"
        pol._identification_candidate = ("stale", 23, 99)
        pol._home_candidate_waiting = False

        self.assertEqual(
            pol._town_special_key(snap), "rra",
            (pol.last_reason, pol.departure_block_state()),
        )
        self.assertIsNone(pol._home_pending_item)
        self.assertIsNone(pol._identification_need)

    def test_active_home_latch_is_retained_and_blocks_recall(self):
        pol, snap = self._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True
        )
        pending = replace(
            item("b", 23, 8, known=True, is_equipment=True, name="pending sword"),
            damage_dice_num=2, damage_dice_sides=5, weight=80,
        )
        snap = replace(snap, inventory=[*snap.inventory, pending])
        signature = pol._item_signature(pending)
        pol._home_pending_item = signature

        self.assertNotEqual(pol._town_special_key(snap), "rra")
        self.assertEqual(pol._home_pending_item, signature)

    def test_fundraising_keeps_walking_to_mine_level_one(self):
        pol, snap = self._ready_town(8, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE)
        pol._fundraising_mode = "mine"
        self.assertNotEqual(pol._town_special_key(snap), "rr")

    def test_deep_run_drops_the_town_entrance_as_a_descent_goal(self):
        entrance = GridState(
            position=Position(10, 10), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, has_entrance=True, entrance_dungeon_id=DUNGEON_YEEK_CAVE,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): entrance}, [], floor_key=(0, 0, 0), town_flag=True,
        )
        pol = HengbotPolicy()
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        pol._deepest_level = RECALL_MIN_DEPTH
        self.assertFalse(pol._is_descent_target(snap, entrance))  # deep -> recall
        pol._deepest_level = RECALL_MIN_DEPTH - 1
        self.assertTrue(pol._is_descent_target(snap, entrance))  # shallow -> walk

    @staticmethod
    def _q14(status):
        info = QuestInfo(
            14, "Warg Problem", 1, 5, 2, dungeon=DUNGEON_YEEK_CAVE,
            max_num=1, monrace_id=257,
        )
        quest = QuestState(
            id=14, status=status, type=1, level=5,
            dungeon_id=DUNGEON_YEEK_CAVE, fixed=True,
        )
        return info, quest

    def _q14_floor(self, status, depth):
        info, quest = self._q14(status)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [], floor_key=(DUNGEON_YEEK_CAVE, depth, 0),
            quests={14: quest}, entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        return HengbotPolicy(quest_knowledge={14: info}), snap

    def _exhausted_q14_floor(self, status, depth, *, cur_num=14):
        info, quest = self._q14(status)
        info = replace(info, max_num=16)
        quest = replace(quest, cur_num=cur_num, max_num=16)
        here = grid(10, 10, upstairs=True, downstairs=True)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): here}, [],
            floor_key=(DUNGEON_YEEK_CAVE, depth, 0), quests={14: quest},
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        pol = HengbotPolicy(quest_knowledge={14: info})
        pol._explore_step = lambda _snapshot: None
        pol._is_frontier = lambda *_args: False
        return pol, snap

    def test_q14_completed_in_dungeon_reads_recall_to_claim(self):
        policy, snapshot = self._q14_floor(QUEST_STATUS_COMPLETED, 5)
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snapshot = replace(snapshot, inventory=[recall])

        self.assertEqual(policy.choose_key(snapshot), "rr")
        self.assertEqual(policy.last_reason, "fixedquest:claim:return")

    def test_q14_completed_in_dungeon_fights_adjacent_hostile_before_recall(self):
        policy, snapshot = self._q14_floor(QUEST_STATUS_COMPLETED, 5)
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        hostile = MonsterState(
            1, Position(10, 11), 1, 1, 1, False, False, race_id=257,
        )
        snapshot = replace(
            snapshot,
            inventory=[recall],
            grids={
                **snapshot.grids,
                Position(10, 11): grid(10, 11, monster=True),
            },
            visible_monsters=[hostile],
        )

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_q14_completed_in_dungeon_without_recall_steers_upstairs(self):
        policy, snapshot = self._q14_floor(QUEST_STATUS_COMPLETED, 5)
        snapshot = replace(
            snapshot,
            grids={Position(10, 10): grid(10, 10, upstairs=True, downstairs=True)},
        )

        self.assertEqual(policy.choose_key(snapshot), "<")
        self.assertEqual(policy.last_reason, "fixedquest:claim:return")

    def test_q14_completed_in_dungeon_waits_for_pending_recall(self):
        policy, snapshot = self._q14_floor(QUEST_STATUS_COMPLETED, 5)
        snapshot = replace(snapshot, player=replace(snapshot.player, recalling=True))

        self.assertEqual(policy.choose_key(snapshot), "5")
        self.assertEqual(policy.last_reason, "return:wait-recall")

    @staticmethod
    def _pending_dungeon_recall(*, turn, recall_count=1, recalling=False):
        floor_key = (DUNGEON_YEEK_CAVE, 5, 0)
        recall = item(
            "r",
            TVAL_SCROLL,
            SV_SCROLL_WORD_OF_RECALL,
            count=recall_count,
        )
        recall_player = replace(player(10, 10), recalling=recalling)
        snapshot = Snapshot(
            recall_player,
            {Position(10, 10): grid(10, 10)},
            [],
            turn=turn,
            floor_key=floor_key,
            inventory=[recall] if recall_count else [],
        )
        policy = HengbotPolicy()
        policy._returning_to_town = True
        policy._dungeon_recall_issue_watch = (floor_key, 100, 2)
        return policy, snapshot

    def test_consumed_recall_confirmation_expires_and_retries(self):
        policy, snapshot = self._pending_dungeon_recall(
            turn=100 + RECALL_ISSUE_CONFIRM_TURNS + 1,
        )

        self.assertEqual(policy._return_to_town_key(snapshot, []), "rr")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_stuck_recall_escape_awaits_consumed_scroll_confirmation(self):
        recall = item(
            "r",
            TVAL_SCROLL,
            SV_SCROLL_WORD_OF_RECALL,
            count=2,
        )
        snapshot = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=100,
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=[recall],
        )
        policy = HengbotPolicy()
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        policy.last_reason = "search"

        self.assertEqual(policy.choose_key(snapshot), READ_KEY + "r")
        self.assertEqual(policy.last_reason, "stuck:recall-escape")

        consumed = replace(
            snapshot,
            turn=101,
            inventory=[replace(recall, count=1)],
        )
        self.assertEqual(policy._return_to_town_key(consumed, []), WAIT_KEY)
        self.assertEqual(policy.last_reason, "return:await-recall-confirmation")

    def test_livelock_recall_escape_awaits_consumed_scroll_confirmation(self):
        recall = item(
            "r",
            TVAL_SCROLL,
            SV_SCROLL_WORD_OF_RECALL,
            count=2,
        )
        snapshot = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            turn=100,
            floor_key=(DUNGEON_YEEK_CAVE, 5, 0),
            inventory=[recall],
        )
        policy = HengbotPolicy()
        policy._nav_exhausted = True

        self.assertEqual(
            policy._navigation_livelock_key(snapshot),
            READ_KEY + "r",
        )
        self.assertEqual(policy.last_reason, "livelock:recall-escape")

        consumed = replace(
            snapshot,
            turn=101,
            inventory=[replace(recall, count=1)],
        )
        self.assertEqual(policy._return_to_town_key(consumed, []), WAIT_KEY)
        self.assertEqual(policy.last_reason, "return:await-recall-confirmation")

    def test_consumed_recall_confirmation_waits_within_window(self):
        policy, snapshot = self._pending_dungeon_recall(
            turn=100 + RECALL_ISSUE_CONFIRM_TURNS,
        )

        self.assertEqual(policy._return_to_town_key(snapshot, []), WAIT_KEY)
        self.assertEqual(policy.last_reason, "return:await-recall-confirmation")

    def test_recall_confirmation_waits_on_same_turn_redraw(self):
        policy, snapshot = self._pending_dungeon_recall(
            turn=100,
            recall_count=2,
        )

        self.assertEqual(policy._return_to_town_key(snapshot, []), WAIT_KEY)
        self.assertEqual(policy.last_reason, "return:await-recall-confirmation")

    def test_active_recall_still_waits_before_issue_watch(self):
        policy, snapshot = self._pending_dungeon_recall(
            turn=100 + RECALL_ISSUE_CONFIRM_TURNS + 1,
            recalling=True,
        )

        self.assertEqual(policy._return_to_town_key(snapshot, []), WAIT_KEY)
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_taken_q14_exhausted_floor_regenerates_up_instead_of_descending(self):
        pol, snap = self._exhausted_q14_floor(QUEST_STATUS_TAKEN, 5)
        self.assertEqual(pol.choose_key(snap), "<")
        self.assertEqual(pol.last_reason, "quest:regen:ascend")

    def test_untaken_q14_exhausted_floor_preserves_old_descend_fallback(self):
        pol, snap = self._exhausted_q14_floor(QUEST_STATUS_UNTAKEN, 8)
        pol._fixed_quest_key = lambda *_args: None
        snap = replace(snap, player=replace(snap.player, class_id=-1))
        self.assertEqual(pol.choose_key(snap), ">")
        self.assertEqual(pol.last_reason, "descend")

    def test_taken_q14_overshoot_recovers_up_across_multiple_floors(self):
        pol, snap = self._exhausted_q14_floor(QUEST_STATUS_TAKEN, 9)
        for depth in (9, 8, 7, 6):
            current = replace(snap, floor_key=(DUNGEON_YEEK_CAVE, depth, 0))
            self.assertFalse(
                pol._is_descent_target(
                    current, current.grid_at(current.player.position)
                )
            )
            self.assertEqual(pol.choose_key(current), "<")
            self.assertEqual(pol.last_reason, "quest:regen:ascend")
        objective = replace(snap, floor_key=(DUNGEON_YEEK_CAVE, 5, 0))
        self.assertFalse(pol._kill_quest_descent_allowed(objective))

    def test_taken_q14_regeneration_returns_down_then_resumes_hunt(self):
        pol, floor5 = self._exhausted_q14_floor(QUEST_STATUS_TAKEN, 5)
        self.assertEqual(pol.choose_key(floor5), "<")
        floor4 = replace(floor5, floor_key=(DUNGEON_YEEK_CAVE, 4, 0))
        self.assertEqual(pol.choose_key(floor4), ">")
        self.assertEqual(pol.last_reason, "quest:regen:descend")
        target = MonsterState(
            1, Position(10, 11), 1, 1, 1, False, False, race_id=257,
        )
        fresh = replace(
            floor5,
            grids={
                Position(10, 10): grid(10, 10, upstairs=True, downstairs=True),
                Position(10, 11): grid(10, 11, monster=True),
            },
            visible_monsters=[target],
        )
        self.assertNotIn(pol.choose_key(fresh), {"<", ">"})
        self.assertIn(pol.last_reason, {"melee", "ranged", "hunt"})

    def test_taken_q14_regeneration_stops_after_three_zero_kill_rounds(self):
        pol, floor5 = self._exhausted_q14_floor(QUEST_STATUS_TAKEN, 5)
        self.assertEqual(pol.choose_key(floor5), "<")
        for round_number in range(3):
            floor4 = replace(floor5, floor_key=(DUNGEON_YEEK_CAVE, 4, 0))
            self.assertEqual(pol.choose_key(floor4), ">")
            result = pol.choose_key(floor5)
            if round_number < 2:
                self.assertEqual(result, "<")
            else:
                self.assertEqual(result, "5")
                self.assertEqual(pol.last_reason, "quest:regen:exhausted")
        for _ in range(3):
            self.assertEqual(pol.choose_key(floor5), "5")
            self.assertEqual(pol.last_reason, "quest:regen:exhausted")

    def test_completed_q14_descent_predicates_and_regeneration_are_inert(self):
        completed, snap = self._exhausted_q14_floor(QUEST_STATUS_COMPLETED, 5)
        rewarded, baseline = self._exhausted_q14_floor(QUEST_STATUS_REWARDED, 5)
        completed._fixed_quest_key = lambda *_args: None

        self.assertTrue(completed._kill_quest_descent_allowed(snap))
        self.assertIsNone(completed._kill_quest_floor_recovery_key(snap))
        self.assertIsNone(completed._start_kill_quest_regeneration(snap))
        self.assertEqual(completed.choose_key(snap), rewarded.choose_key(baseline))

    def test_untaken_q14_below_objective_does_not_veto_descent(self):
        pol, snap = self._q14_floor(QUEST_STATUS_UNTAKEN, 8)
        self.assertTrue(pol._is_descent_target(snap, snap.grid_at(Position(10, 10))))

    def test_untaken_q14_shallow_steering_still_descends(self):
        pol, snap = self._q14_floor(QUEST_STATUS_UNTAKEN, 3)
        self.assertTrue(pol._is_descent_target(snap, snap.grid_at(Position(10, 10))))

    def test_taken_q14_objective_floor_vetoes_overshoot(self):
        pol, snap = self._q14_floor(QUEST_STATUS_TAKEN, 5)
        self.assertFalse(pol._is_descent_target(snap, snap.grid_at(Position(10, 10))))

    def test_rewarded_q14_does_not_veto_descent(self):
        pol, snap = self._q14_floor(QUEST_STATUS_REWARDED, 5)
        self.assertTrue(pol._is_descent_target(snap, snap.grid_at(Position(10, 10))))

    def test_taken_q14_deep_recall_uses_walk_in_entry(self):
        pol, snap = self._ready_town(
            8, DUNGEON_YEEK_CAVE, DUNGEON_YEEK_CAVE, recall_depth=8,
        )
        info, quest = self._q14(QUEST_STATUS_TAKEN)
        pol._quest_knowledge = {14: info}
        snap = replace(snap, quests={14: quest})
        entrance = GridState(
            position=Position(10, 11), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, has_entrance=True,
            entrance_dungeon_id=DUNGEON_YEEK_CAVE,
        )

        self.assertIsNone(pol._town_special_key(snap))
        self.assertTrue(pol._is_descent_target(snap, entrance))
        at_entrance = replace(
            snap,
            player=replace(snap.player, position=entrance.position),
            grids={entrance.position: entrance},
        )
        self.assertEqual(pol.choose_key(at_entrance), ">\ry")
        self.assertEqual(pol.last_reason, "descend")

class RemoveCurseTest(unittest.TestCase):
    """Town prep reads a Remove Curse scroll when a cursed item is worn (and buys
    one at the Temple when none is carried)."""

    def _town(self, equipment, inventory=None):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory or [],
            equipment=equipment,
        )

    def test_reads_remove_curse_when_cursed_and_scrolled(self):
        cursed = item("a", 23, 0, is_equipment=True, is_cursed=True, name="cursed")
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="remove curse")
        pol = HengbotPolicy()
        self.assertEqual(pol._town_remove_curse_key(self._town([cursed], [scroll])), "rs")
        self.assertEqual(pol.last_reason, "town:remove-curse")

    def test_no_remove_curse_without_cursed_equipment(self):
        plain = item("a", 23, 0, is_equipment=True, name="plain")
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        self.assertIsNone(HengbotPolicy()._town_remove_curse_key(self._town([plain], [scroll])))

    def test_no_remove_curse_without_scroll(self):
        cursed = item("a", 23, 0, is_equipment=True, is_cursed=True)
        self.assertIsNone(HengbotPolicy()._town_remove_curse_key(self._town([cursed], [])))

    def test_blind_defers_remove_curse(self):
        cursed = item("a", 23, 0, is_equipment=True, is_cursed=True)
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, blind=True),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[scroll],
            equipment=[cursed],
        )
        self.assertIsNone(HengbotPolicy()._town_remove_curse_key(snap))

    def test_buys_remove_curse_at_temple_when_cursed(self):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=9),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=9),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
        ]
        snap = Snapshot(
            player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=inv,
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("w", 23, 0, is_equipment=True, is_cursed=True, name="cursed"),
            ],
            store=StoreState(
                STORE_TEMPLE,
                [store_item("z", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, price=100)],
            ),
        )
        purchase = HengbotPolicy()._next_purchase(snap)
        self.assertIsNotNone(purchase)
        self.assertEqual(purchase.sval, SV_SCROLL_REMOVE_CURSE)

    def test_affordable_temple_curse_service_is_first_then_bought_and_read(self):
        cursed = [
            item(slot, 23, index, is_equipment=True, is_cursed=True)
            for index, slot in enumerate(("sub_hand", "arms", "feet"))
        ]
        ware = store_item(
            "z", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, price=100,
            name="remove curse",
        )
        policy = HengbotPolicy()
        policy._observe(self._town(cursed))
        temple = replace(
            self._town(cursed),
            player=player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            store=StoreState(STORE_TEMPLE, [ware]),
        )
        policy._observe(temple)
        policy._town_maps = {
            0: TownMap(
                "curse-service-order", 20, 20, frozenset(),
                {
                    STORE_GENERAL: Position(10, 11),
                    STORE_TEMPLE: Position(10, 18),
                },
            )
        }
        outside = replace(temple, store=None, width=20, height=20)
        needs = [
            TownNeed(STORE_GENERAL, "food", "normal"),
            TownNeed(STORE_TEMPLE, "remove-curse", "normal"),
        ]

        self.assertEqual(
            policy._order_town_needs(
                outside, needs, [STORE_GENERAL, STORE_TEMPLE],
                outside.player.position,
            )[0],
            STORE_TEMPLE,
        )
        self.assertEqual(policy._shop(temple), "pz\r")
        carried = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        self.assertEqual(policy._town_remove_curse_key(self._town(cursed, [carried])), "rs")

    def test_remove_curse_actionability_tracks_stock_and_current_funds(self):
        cursed = item("main_ring", 23, 0, is_equipment=True, is_cursed=True)
        ware = store_item("z", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, price=100)
        policy = HengbotPolicy()
        base = replace(
            self._town([cursed]),
            player=player(10, 10, gold=99, class_id=PLAYER_CLASS_WARRIOR),
        )
        policy._observe(base)
        policy._observe(replace(base, store=StoreState(STORE_TEMPLE, [ware])))
        self.assertFalse(policy._normal_remove_curse_actionable_this_visit(base))
        affordable = replace(
            base, player=player(10, 10, gold=100, class_id=PLAYER_CLASS_WARRIOR)
        )
        self.assertTrue(policy._normal_remove_curse_actionable_this_visit(affordable))
        policy._observe(replace(affordable, store=StoreState(STORE_TEMPLE, [])))
        self.assertFalse(policy._normal_remove_curse_actionable_this_visit(affordable))
        policy._observe(replace(affordable, store=StoreState(STORE_TEMPLE, [ware])))
        self.assertTrue(policy._normal_remove_curse_actionable_this_visit(affordable))

    def test_unchanged_normal_read_latches_and_marks_heavy_curse(self):
        cursed = item(
            "main_ring", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring", inscription="keep",
        )
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="remove curse")
        policy = HengbotPolicy()
        snapshot = self._town([cursed], [normal])
        self.assertEqual(policy._town_remove_curse_key(snapshot), "rs")
        policy._observe(self._town([cursed], []))

        self.assertIsNone(policy._town_remove_curse_key(self._town([cursed], [normal])))
        self.assertEqual(
            policy._heavy_curse_inscription_key(self._town([cursed])),
            "{/d\x05 HEAVY_CURSE\r",
        )
        self.assertIsNone(policy._heavy_curse_inscription_key(self._town([cursed])))
        needs = policy._enumerate_town_needs(self._town([cursed], []))
        self.assertNotIn(TownNeed(STORE_TEMPLE, "remove-curse", "normal"), needs)

    def test_inscription_authority_survives_restart_without_normal_read(self):
        cursed = item(
            "main_ring", 23, 0, is_equipment=True, is_cursed=True,
            inscription="keep HEAVY_CURSE", name="incident cursed ring",
        )
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        policy = HengbotPolicy()
        self.assertTrue(policy._curse_unremovable(cursed))
        self.assertIsNone(policy._town_remove_curse_key(self._town([cursed], [normal])))

    def test_uncursed_item_clears_standalone_heavy_curse_tag(self):
        cured = item(
            "main_ring", 23, 0, is_equipment=True, is_cursed=False,
            inscription="HEAVY_CURSE", name="cured ring",
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(cured)
        policy._heavy_cursed_items.add(signature)
        snapshot = self._town([cured])

        policy._observe(snapshot)

        self.assertEqual(policy._heavy_curse_inscription_key(snapshot), "}/d")
        self.assertEqual(policy.last_reason, "equipment:clear-heavy-curse-tag")
        self.assertNotIn(signature, policy._heavy_cursed_items)
        self.assertFalse(policy._curse_unremovable(replace(cured, inscription="")))

    def test_uncursed_item_preserves_meaningful_inscription_when_clearing_tag(self):
        cured = item(
            "main_ring", 23, 0, is_equipment=True, is_cursed=False,
            inscription="keep HEAVY_CURSE", name="cured ring",
        )
        policy = HengbotPolicy()

        self.assertEqual(
            policy._heavy_curse_inscription_key(self._town([cured])),
            "{/dkeep\r",
        )
        self.assertEqual(policy.last_reason, "equipment:remove-heavy-curse-tag")

    def test_uncursed_untagged_item_is_not_uninscribed(self):
        cured = item(
            "main_ring", 23, 0, is_equipment=True, is_cursed=False,
            inscription="keep", name="ordinary ring",
        )
        self.assertIsNone(
            HengbotPolicy()._heavy_curse_inscription_key(self._town([cured]))
        )

    def test_star_remove_curse_loot_is_used_for_heavy_latch(self):
        cursed = item(
            "a", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring",
        )
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="remove curse")
        star = item("t", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, name="star remove curse")
        policy = HengbotPolicy()
        for _attempt in range(2):
            policy._town_remove_curse_key(self._town([cursed], [normal]))
            policy._observe(self._town([cursed], []))

        policy._observe(self._town([cursed], [star]))
        self.assertEqual(policy._town_remove_curse_key(self._town([cursed], [star])), "rt")

    def test_heavy_curse_buys_stocked_star_scroll_then_reads_it(self):
        cursed = item(
            "a", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring",
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(cursed)
        policy._heavy_cursed_items.add(signature)
        supplies = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
        ]
        temple = replace(
            self._town([
                item("L", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                cursed,
            ], supplies),
            player=player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            store=StoreState(
                STORE_TEMPLE,
                [store_item("z", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, price=500)],
            ),
        )
        self.assertIn(
            TownNeed(STORE_TEMPLE, "star-remove-curse", "normal"),
            policy._enumerate_town_needs(temple),
        )
        self.assertEqual(policy._next_purchase(temple).sval, SV_SCROLL_STAR_REMOVE_CURSE)

        star = item("t", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, name="star remove curse")
        self.assertEqual(policy._town_remove_curse_key(self._town([cursed], [star])), "rt")
        uncursed = replace(cursed, is_cursed=False)
        policy._observe(self._town([uncursed], []))
        self.assertNotIn(signature, policy._heavy_cursed_items)

    def test_surplus_star_scroll_is_bought_once_and_deposited_at_home(self):
        ware = store_item(
            "z", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, price=500
        )
        temple = replace(
            self._town([]),
            player=player(
                10, 10, gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            store=StoreState(STORE_TEMPLE, [ware]),
        )
        policy = HengbotPolicy()
        policy._home_star_remove_curse_count = 0
        with (
            patch.object(policy, "_recall_departure_shortage", return_value=False),
        ):
            self.assertIs(policy._affordable_star_remove_curse(temple), ware)
            with (
                patch.object(policy, "_next_purchase", return_value=ware),
                patch.object(policy, "_purchase_quantity", return_value=1),
            ):
                self.assertEqual(policy._shop(temple), "pz\r")
        self.assertTrue(policy._star_remove_curse_reserve_deposit_pending)

        carried = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE,
            name="star remove curse",
        )
        home = replace(
            temple,
            inventory=[carried],
            store=StoreState(STORE_HOME, []),
        )
        policy._home_entry_operation_posted = True
        self.assertEqual(policy._shop(home), "ds")
        self.assertEqual(policy.last_reason, "home:deposit")

    def test_star_remove_curse_reserve_buy_waits_for_inventory_delta(self):
        ware = store_item(
            "z", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, price=500
        )
        temple = replace(
            self._town([]),
            player=player(
                10, 10, gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            store=StoreState(STORE_TEMPLE, [ware]),
        )
        policy = HengbotPolicy()
        policy._home_star_remove_curse_count = 0
        with (
            patch.object(policy, "_recall_departure_shortage", return_value=False),
            patch.object(policy, "_next_purchase", return_value=ware),
            patch.object(policy, "_purchase_quantity", return_value=1),
        ):
            first = policy._shop(temple)
            second = policy._shop(temple)
            self.assertEqual([first, second].count("pz\r"), 1)
            self.assertIsNotNone(
                policy._star_remove_curse_reserve_buy_inflight
            )

            carried = item(
                "s", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE,
                name=ware.name,
            )
            self.assertEqual(
                policy._shop(replace(temple, inventory=[carried])),
                "pz\r",
            )
        self.assertIsNone(policy._star_remove_curse_reserve_buy_inflight)

        # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
        policy._star_remove_curse_reserve_buy_inflight = (
            policy._item_signature(ware),
            0,
        )
        policy._observe_star_remove_curse_reserve_inflight(self._town([]))
        self.assertIsNone(policy._star_remove_curse_reserve_buy_inflight)

    def test_star_remove_curse_reserve_deposit_waits_for_inventory_delta(self):
        carried = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE,
            name="star remove curse",
        )
        home = replace(
            self._town([], [carried]),
            store=StoreState(STORE_HOME, []),
        )
        policy = HengbotPolicy()
        policy._home_star_remove_curse_count = 0
        policy._star_remove_curse_reserve_deposit_pending = True
        policy._home_entry_operation_posted = True

        first = policy._shop(home)
        second = policy._shop(home)
        self.assertEqual([first, second].count("ds"), 1)
        self.assertIsNotNone(
            policy._star_remove_curse_reserve_deposit_inflight
        )

        policy._shop(replace(home, inventory=[]))
        self.assertIsNone(
            policy._star_remove_curse_reserve_deposit_inflight
        )
        self.assertFalse(policy._star_remove_curse_reserve_deposit_pending)
        self.assertEqual(policy._home_star_remove_curse_count, 1)

        signature = policy._item_signature(carried)
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
        policy._star_remove_curse_reserve_deposit_inflight = (signature, 1)
        policy._observe_star_remove_curse_reserve_inflight(self._town([]))
        self.assertIsNone(
            policy._star_remove_curse_reserve_deposit_inflight
        )

    def test_star_remove_curse_reserve_cap_counts_home_and_carried_copy(self):
        ware = store_item(
            "z", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, price=500
        )
        temple = replace(
            self._town([]),
            player=player(
                10, 10, gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            store=StoreState(STORE_TEMPLE, [ware]),
        )
        for home_count, inventory in (
            (1, []),
            (0, [item("s", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE)]),
        ):
            with self.subTest(home_count=home_count):
                policy = HengbotPolicy()
                policy._home_star_remove_curse_count = home_count
                snap = replace(temple, inventory=inventory)
                with patch.object(
                    policy, "_recall_departure_shortage", return_value=False
                ):
                    self.assertIsNone(
                        policy._affordable_star_remove_curse(snap)
                    )

    def test_star_remove_curse_reserve_needs_surplus_and_live_shelf(self):
        ware = store_item(
            "z", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, price=500
        )
        policy = HengbotPolicy()
        policy._home_star_remove_curse_count = 0
        for gold, stock in (
            (FUNDRAISING_GOLD_TARGET - 1, [ware]),
            (FUNDRAISING_GOLD_TARGET, []),
        ):
            with self.subTest(gold=gold, stock=bool(stock)):
                temple = replace(
                    self._town([]),
                    player=player(
                        10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR
                    ),
                    store=StoreState(STORE_TEMPLE, stock),
                )
                with patch.object(
                    policy, "_recall_departure_shortage", return_value=False
                ):
                    self.assertIsNone(
                        policy._affordable_star_remove_curse(temple)
                    )

    def test_star_reserve_is_opportunistic_and_suppressed_by_recall_shortage(self):
        policy = HengbotPolicy()
        policy._home_star_remove_curse_count = 0
        policy._star_remove_curse_shelf_seen = True
        town = replace(
            self._town([]),
            player=player(
                10, 10, gold=FUNDRAISING_GOLD_TARGET,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
        )
        with (
            patch.object(policy, "_recall_departure_shortage", return_value=False),
            patch.object(policy, "_town_departure_ready", return_value=True),
            patch.object(
                policy,
                "_town_need_candidates",
                return_value=[
                    TownNeed(
                        STORE_TEMPLE,
                        "home-star-remove-curse-stock",
                        "normal",
                    )
                ],
            ),
        ):
            self.assertFalse(policy._town_claims_active(town))
        with patch.object(
            policy, "_recall_departure_shortage", return_value=True
        ):
            self.assertFalse(any(
                need.category.startswith("home-star-remove-curse")
                for need in policy._enumerate_town_needs(town)
            ))

    def test_heavy_curse_withdraws_and_reads_home_reserve_then_clears_latch(self):
        cursed = item(
            "main_ring", 23, 0, is_equipment=True, is_cursed=True,
            inscription="HEAVY_CURSE", name="incident cursed ring",
        )
        reserve = store_item(
            "z", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE,
            name="star remove curse",
        )
        policy = HengbotPolicy()
        policy._home_star_remove_curse_count = 1
        home = replace(
            self._town([cursed]),
            store=StoreState(STORE_HOME, [reserve]),
        )
        with patch.object(
            policy, "_recall_departure_shortage", return_value=False
        ):
            self.assertEqual(policy._shop(home), LEAVE_STORE_KEY)
        self.assertTrue(policy._star_remove_curse_reserve_withdraw_pending)

        carried = item(
            "s", TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE,
            name="star remove curse",
        )
        self.assertEqual(
            policy._town_remove_curse_key(self._town([cursed], [carried])),
            "rs",
        )
        cured = replace(cursed, is_cursed=False)
        policy._observe(self._town([cured], []))
        self.assertIsNone(policy._remove_curse_watch)
        self.assertEqual(
            policy._heavy_curse_inscription_key(self._town([cured])),
            "}/d",
        )

    def test_heavy_curse_checks_unknown_home_before_shop_service(self):
        cursed = item(
            "main_ring", 23, 0, is_equipment=True, is_cursed=True,
            inscription="HEAVY_CURSE",
        )
        policy = HengbotPolicy()
        town = self._town([cursed])
        with patch.object(
            policy, "_recall_departure_shortage", return_value=False
        ):
            self.assertIn(
                TownNeed(
                    STORE_HOME, "home-star-remove-curse-use", "home-first"
                ),
                policy._enumerate_town_needs(town),
            )

    def test_heavy_curse_missing_star_scroll_never_creates_temple_wait(self):
        cursed = item(
            "a", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring",
        )
        policy = HengbotPolicy()
        policy._heavy_cursed_items.add(policy._item_signature(cursed))
        temple = replace(
            self._town([cursed]),
            player=player(10, 10, gold=1000, class_id=PLAYER_CLASS_WARRIOR),
            store=StoreState(STORE_TEMPLE, []),
        )
        self.assertFalse(any(
            need.category in {"remove-curse", "star-remove-curse"}
            for need in policy._enumerate_town_needs(temple)
        ))
        self.assertIsNone(policy._next_purchase(temple))
        policy._town_store_attempted[STORE_TEMPLE] = temple.turn
        self.assertIsNone(policy._retry_after_store_restock(temple, (STORE_TEMPLE,)))

    def test_heavy_curse_optimizer_blocker_allows_confirmed_loadout(self):
        cursed = item(
            "a", 23, 0, is_equipment=True, is_cursed=True,
            known=True, name="incident cursed ring",
        )
        policy = HengbotPolicy()
        policy._heavy_cursed_items.add(policy._item_signature(cursed))
        snapshot = self._town([cursed])
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        current = current_loadout(policy._equipment_catalog.items)
        target = Loadout((), "empty")
        transaction = policy_module.plan_equipment_transactions(
            policy._equipment_catalog.items, current, target,
            current_pack_items=0, home_scan_complete=True,
        )
        self.assertTrue(transaction.actions)
        self.assertTrue(all(
            blocker.startswith("cursed-equipped:")
            for blocker in transaction.blockers
        ))
        blocked = SimpleNamespace(
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=target)),
            blockers=transaction.blockers,
            transaction=transaction,
            ready=False,
        )
        policy._prepare_equipment_optimization = lambda _snapshot: blocked
        seed_confirmed_loadout(policy, snapshot)

        self.assertTrue(policy._equipment_departure_ready(snapshot))

        blocked.result = None
        policy = HengbotPolicy()
        policy._heavy_cursed_items.add(policy._item_signature(cursed))
        policy._prepare_equipment_optimization = lambda _snapshot: blocked
        self.assertFalse(policy._equipment_departure_ready(self._town([cursed])))

    def test_absent_scroll_allows_loadout_but_affordable_stock_blocks_it(self):
        cursed = item("main_ring", 23, 0, is_equipment=True, is_cursed=True)
        policy = HengbotPolicy()
        policy._town_store_attempted[STORE_TEMPLE] = 0
        snapshot = self._town([cursed])
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        current = current_loadout(policy._equipment_catalog.items)
        target = Loadout((), "empty")
        transaction = policy_module.plan_equipment_transactions(
            policy._equipment_catalog.items, current, target,
            current_pack_items=0, home_scan_complete=True,
        )
        blocked = SimpleNamespace(
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=target)),
            blockers=transaction.blockers,
            transaction=transaction,
            ready=False,
        )
        policy._prepare_equipment_optimization = lambda _snapshot: blocked
        policy._observe(snapshot)
        policy._observe(replace(snapshot, store=StoreState(STORE_TEMPLE, [])))
        seed_confirmed_loadout(policy, snapshot)
        self.assertTrue(policy._equipment_departure_ready(snapshot))

        affordable = replace(
            self._town([cursed]),
            player=player(10, 10, gold=100, class_id=PLAYER_CLASS_WARRIOR),
        )
        policy._observe(replace(
            affordable,
            store=StoreState(
                STORE_TEMPLE,
                [store_item("z", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, price=100)],
            ),
        ))
        self.assertFalse(policy._equipment_departure_ready(affordable))

    def test_actionable_normal_scroll_keeps_departure_blocked(self):
        cursed = item("main_ring", 23, 0, is_equipment=True, is_cursed=True)
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        policy = HengbotPolicy()
        blocked = SimpleNamespace(
            blockers=("cursed-equipped:equipped:ring:0",),
            transaction=None,
            ready=False,
        )
        policy._prepare_equipment_optimization = lambda _snapshot: blocked
        self.assertFalse(
            policy._equipment_departure_ready(self._town([cursed], [normal]))
        )

    def test_templeless_town_does_not_claim_remove_curse_is_actionable(self):
        cursed = item("main_ring", 23, 0, is_equipment=True, is_cursed=True)
        snapshot = replace(self._town([cursed]), width=3, height=3)
        policy = HengbotPolicy()
        town_map = TownMap(
            name="templeless",
            width=3,
            height=3,
            walkable=frozenset({Position(10, 10)}),
            stores={},
        )
        policy._town_maps = {0: town_map}

        self.assertFalse(policy._normal_remove_curse_actionable_this_visit(snapshot))

    def test_interrupted_normal_read_does_not_advance_heavy_latch(self):
        cursed = item("a", 23, 0, is_equipment=True, is_cursed=True, name="cursed")
        normal = item("s", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="remove curse")
        policy = HengbotPolicy()
        snapshot = self._town([cursed], [normal])
        self.assertEqual(policy._town_remove_curse_key(snapshot), "rs")
        policy._observe(snapshot)
        self.assertFalse(policy._heavy_cursed_items)
        self.assertIsNone(policy._heavy_curse_inscription_pending)

class TownWanderCircuitBreakerTest(unittest.TestCase):
    """A town-only mirror of StuckEscapeTest: town positions vary across most
    of the map, so cli's position-based loop guard never catches a bot that is
    only ever wandering (a live logic deadlock paced town for 2 real hours
    before anyone noticed — see jsonlog/codex-stuck-investigation-2026-07-15.md).
    After TOWN_WANDER_LIMIT consecutive non-productive-wander decisions in
    town, enter the bounded town-cycle repair path so the first offense forces
    departure and a repeated failure stops the bot visibly."""

    def _dungeon(self):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 11, 0),
        )

    def _town(self):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )

    def test_streak_counts_both_wander_reasons_in_town(self):
        pol = HengbotPolicy()
        t = self._town()
        for reason in ("stuck:wander", "breakout:least-visited"):
            pol.last_reason = reason
            pol._observe(t)
        self.assertEqual(pol._town_wander_streak, 2)
        self.assertIsNone(pol._town_blocked_reason)

    def test_sixty_consecutive_wanders_force_departure_cycle_break(self):
        pol = HengbotPolicy()
        t = self._town()
        for _ in range(TOWN_WANDER_LIMIT):
            pol.last_reason = "stuck:wander"
            pol._observe(t)
        self.assertEqual(pol._town_wander_streak, TOWN_WANDER_LIMIT)
        self.assertTrue(pol._town_cycle_pending)
        self.assertEqual(pol._town_special_key(t), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertTrue(pol._town_restock_suppressed)
        self.assertIsNone(pol._next_required_store_type(t))

    def test_cycle_break_resets_generic_no_progress_debt_before_entrance_walk(self):
        pol = HengbotPolicy()
        t = self._town()
        for step in range(TOWN_WANDER_LIMIT):
            pol.last_reason = "stuck:wander"
            pol._observe(
                replace(t, player=replace(t.player, position=Position(10, 10 + step)))
            )

        self.assertTrue(pol._town_cycle_pending)
        self.assertEqual(pol._town_special_key(t), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")

        # The live entrance leg needed exactly the residual 96 - 60 decisions.
        # They are productive locomotion and must not be mistaken for a second
        # offense merely because the first detector's counter was retained.
        for step in range(TOWN_NO_PROGRESS_LIMIT - TOWN_WANDER_LIMIT):
            pol.last_reason = "seek-downstairs"
            pol._observe(
                replace(t, player=replace(t.player, position=Position(10, 70 + step)))
            )

        self.assertFalse(pol._town_cycle_pending)
        # The first detector now owns departure until town is left; productive
        # entrance locomotion must not clear that route or accrue old cycle debt.
        self.assertEqual(pol._town_blocked_reason, "repetition")
        self.assertEqual(
            pol._town_no_progress_count,
            TOWN_NO_PROGRESS_LIMIT - TOWN_WANDER_LIMIT,
        )

    def test_second_wander_limit_after_break_stops_visibly(self):
        pol = HengbotPolicy()
        t = self._town()
        pol._town_cycle_breaks = 1
        for _ in range(TOWN_WANDER_LIMIT):
            pol.last_reason = "stuck:wander"
            pol._observe(t)
        self.assertEqual(pol._town_special_key(t), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:repetition")

    def test_inn_travel_resets_cycle_debt_between_surface_towns(self):
        pol = HengbotPolicy()
        origin = replace(self._town(), town_id=3)
        destination = replace(self._town(), town_id=0)
        pol._observe(origin)
        pol._town_cycle_breaks = 1
        pol._town_cycle_pending = True
        pol._town_blocked_reason = "repetition"
        pol._town_no_progress_count = TOWN_NO_PROGRESS_LIMIT - 1
        pol._town_wander_streak = TOWN_WANDER_LIMIT - 1
        pol._town_store_attempted[STORE_GENERAL] = origin.turn
        pol.last_reason = None

        pol._observe(destination)

        self.assertEqual(pol._observed_town_id, 0)
        self.assertEqual(pol._town_cycle_breaks, 0)
        self.assertFalse(pol._town_cycle_pending)
        self.assertIsNone(pol._town_blocked_reason)
        self.assertEqual(pol._town_no_progress_count, 0)
        self.assertEqual(pol._town_wander_streak, 0)
        self.assertEqual(pol._town_store_attempted, {})

    def test_productive_decision_at_fifty_nine_resets_the_streak(self):
        pol = HengbotPolicy()
        t = self._town()
        for _ in range(TOWN_WANDER_LIMIT - 1):
            pol.last_reason = "stuck:wander"
            pol._observe(t)
        self.assertEqual(pol._town_wander_streak, TOWN_WANDER_LIMIT - 1)

        pol.last_reason = "shop:approach"  # any ordinary, productive reason
        pol._observe(t)

        self.assertEqual(pol._town_wander_streak, 0)
        self.assertIsNone(pol._town_blocked_reason)

    def test_never_fires_in_a_dungeon(self):
        pol = HengbotPolicy()
        d = self._dungeon()
        for _ in range(TOWN_WANDER_LIMIT + 5):
            pol.last_reason = "stuck:wander"
            pol._observe(d)
        self.assertEqual(pol._town_wander_streak, 0)
        self.assertIsNone(pol._town_blocked_reason)

    def test_streak_and_latch_reset_on_floor_change(self):
        pol = HengbotPolicy()
        t = self._town()
        for _ in range(TOWN_WANDER_LIMIT):
            pol.last_reason = "stuck:wander"
            pol._observe(t)
        self.assertTrue(pol._town_cycle_pending)

        pol.last_reason = "descend"
        pol._observe(self._dungeon())

        self.assertEqual(pol._town_wander_streak, 0)
        self.assertIsNone(pol._town_blocked_reason)
        self.assertFalse(pol._town_cycle_pending)

class TownCycleDetectorTest(unittest.TestCase):
    """User directive: auto-detect and repair town repetition loops as a CLASS.
    Every observed shape (Home-door bounce, store-to-store travel ping-pong)
    collapses to a handful of (reason, position) signatures with zero
    gold/pack/equipment progress — while staying invisible to the cell-based
    loop guard (store snapshots reset it; travel keeps the position moving)."""

    @staticmethod
    def _town_snap(y=34, x=94, gold=100):
        return Snapshot(
            player(y, x, class_id=PLAYER_CLASS_WARRIOR, gold=gold),
            {Position(y, x): grid(y, x)},
            [],
            floor_key=(0, 0, 0),
            inventory=[],
            equipment=[],
        )

    @staticmethod
    def _prime_cycle(pol):
        cycle = [
            ("shop:travel", 37, 91),
            ("shop:approach", 31, 77),
            ("shop:leave", 31, 77),
            ("shop:travel", 31, 77),
            ("shop:approach", 37, 91),
            ("shop:leave", 37, 91),
        ]
        for i in range(TOWN_CYCLE_WINDOW):
            pol._town_signature_history.append(cycle[i % len(cycle)])

    def test_cycle_detected_over_a_full_window(self):
        pol = HengbotPolicy()
        self._prime_cycle(pol)
        self.assertTrue(pol._town_cycle_detected())

    def test_varied_town_activity_is_not_a_cycle(self):
        pol = HengbotPolicy()
        for i in range(TOWN_CYCLE_WINDOW):
            pol._town_signature_history.append(("shop:approach", 30, i))
        self.assertFalse(pol._town_cycle_detected())

    def test_rejected_fixed_quest_travel_hits_fast_visible_stop(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        positions = ((37, 119), (36, 120))
        for step in range(12):
            y, x = positions[step % len(positions)]
            pol.last_reason = (
                "fixedquest:q2-travel" if step % 3 else "shop:leave"
            )
            pol._observe(self._town_snap(y=y, x=x))

        self.assertTrue(pol._town_cycle_pending)
        self.assertEqual(pol._town_cycle_breaks, TOWN_CYCLE_BREAK_LIMIT - 1)

        pol._town_departure_ready = lambda _snapshot: True
        self.assertEqual(pol._town_special_key(self._town_snap()), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:repetition")

    def test_varied_three_store_carousel_hits_no_progress_limit(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        reasons = ["shop:travel", "shop:approach", "shop:leave"]
        stores = [(37, 91), (31, 77), (30, 49)]
        for step in range(TOWN_NO_PROGRESS_LIMIT):
            y, base_x = stores[(step // 3) % len(stores)]
            # Position jitter keeps the old distinct-signature detector false.
            x = base_x + step
            pol.last_reason = reasons[step % len(reasons)]
            pol._observe(self._town_snap(y=y, x=x, gold=102))
        self.assertTrue(pol._town_cycle_pending)
        departure = replace(
            self._town_snap(gold=102),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )
        self.assertEqual(pol._town_special_key(departure), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertTrue(pol._town_restock_suppressed)
        self.assertIsNone(pol._town_special_key(departure))

    def test_progress_resets_no_progress_count(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        for step in range(TOWN_NO_PROGRESS_LIMIT - 1):
            pol.last_reason = "shop:travel"
            pol._observe(self._town_snap(y=30, x=step, gold=102))
        self.assertEqual(pol._town_no_progress_count, TOWN_NO_PROGRESS_LIMIT - 1)
        pol.last_reason = "shop:travel"
        pol._observe(self._town_snap(y=30, x=200, gold=103))
        self.assertFalse(pol._town_cycle_pending)
        self.assertEqual(pol._town_no_progress_count, 1)

    def test_workflow_progress_clears_stale_cycle_offense(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._identification_need = "full"
        pol.last_reason = "shop:travel:await-entry"
        pol._observe(self._town_snap())
        pol._town_cycle_pending = True
        pol._town_cycle_breaks = TOWN_CYCLE_BREAK_LIMIT - 1

        # The live recovery completed the Alchemist requirement without
        # changing gold or pack counts. That must start a fresh cycle epoch.
        pol._identification_need = None
        pol.last_reason = "shop:leave"
        pol._observe(self._town_snap())

        self.assertFalse(pol._town_cycle_pending)
        self.assertEqual(pol._town_cycle_breaks, 0)
        self.assertEqual(pol._town_no_progress_count, 1)

    def test_restock_timer_rechecks_again_only_after_each_full_wait(self):
        pol = HengbotPolicy()
        snap = self._town_snap(gold=102)
        pol._town_store_attempted[STORE_ALCHEMIST] = 0

        self.assertIsNone(pol._retry_after_store_restock(snap, (STORE_ALCHEMIST,)))
        self.assertIn(STORE_ALCHEMIST, pol._town_store_attempted)
        expiry = replace(snap, turn=pol._town_restock_wait_until)
        self.assertEqual(
            pol._retry_after_store_restock(expiry, (STORE_ALCHEMIST,)),
            STORE_ALCHEMIST,
        )
        pol._town_store_attempted[STORE_ALCHEMIST] = expiry.turn
        self.assertIsNone(pol._retry_after_store_restock(expiry, (STORE_ALCHEMIST,)))
        self.assertIn(STORE_ALCHEMIST, pol._town_store_attempted)
        second_expiry = replace(expiry, turn=pol._town_restock_wait_until)
        self.assertEqual(
            pol._retry_after_store_restock(second_expiry, (STORE_ALCHEMIST,)),
            STORE_ALCHEMIST,
        )
        self.assertNotIn(STORE_ALCHEMIST, pol._town_store_attempted)
        self.assertIsNone(pol._town_restock_wait_until)

    def test_live_pingpong_shape_trips_through_observe(self):
        # The exact live shape: travel/approach/leave alternating between the
        # Alchemist and Temple door tiles, gold frozen.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        positions = [(37, 91), (31, 77)]
        reasons = ["shop:travel", "shop:approach", "shop:leave"]
        steps = 0
        while not pol._town_cycle_pending and steps < TOWN_CYCLE_WINDOW + 12:
            y, x = positions[(steps // 3) % 2]
            pol.last_reason = reasons[steps % 3]
            pol._observe(self._town_snap(y=y, x=x))
            steps += 1
        self.assertTrue(pol._town_cycle_pending)

    def test_blocked_home_replay_leaves_then_waits_only_outside(self):
        # A real store snapshot is followed by one interleaved main-loop town
        # snapshot on the Home tile. Both must emit ESC; only the subsequent
        # outside snapshot may emit raw WAIT (key 5).
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        town = self._town_snap()
        position = town.player.position
        store_grid = replace(town.grids[position], store_number=STORE_HOME)
        home = replace(
            town,
            grids={position: store_grid},
            store=StoreState(
                store_type=STORE_HOME, items=[], stock_num=0,
                page_top=0, page_size=52,
            ),
            town_flag=False,
        )
        interleaved = replace(
            town,
            grids={position: store_grid},
            town_flag=True,
        )

        keys = [pol.choose_key(home), pol.choose_key(interleaved)]
        outside = self._town_snap(y=34, x=95)
        keys.append(pol._town_special_key(outside))

        self.assertEqual(keys[0], LEAVE_STORE_KEY)
        self.assertEqual(keys[1], WAIT_KEY)
        self.assertIsNone(keys[2])

    def test_blocked_latch_outside_store_owns_departure_route(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        snap = self._town_snap()
        step = Position(snap.player.position.y, snap.player.position.x + 1)
        with patch.object(pol, "_descent_step", return_value=step):
            self.assertEqual(pol._town_special_key(snap), "6")
        self.assertEqual(pol.last_reason, "town:repetition-depart")

    def test_blocked_repetition_recalls_when_entrance_route_is_unavailable(self):
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        pol._target_dungeon_id = DUNGEON_ANGBAND
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10)
        snap = replace(
            self._town_snap(),
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE, DUNGEON_ANGBAND),
            recall_dungeon_id=DUNGEON_ANGBAND,
            angband_recall_unlocked=True,
        )

        with patch.object(
            pol, "_recall_destination_safe", return_value=True
        ), patch.object(pol, "_descent_step", return_value=None):
            self.assertEqual(pol._town_special_key(snap), READ_KEY + "rb")

        self.assertEqual(pol.last_reason, "town:repetition-depart:recall")
        self.assertTrue(pol._emergency_recall_sanctioned)

    def test_yeek_recall_destination_and_repetition_departure_are_restored(self):
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        pol._deepest_level = RECALL_MIN_DEPTH
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=7)
        snap = replace(
            self._town_snap(),
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            recall_depth=RECALL_MIN_DEPTH,
            dungeon_recall_depths={
                DUNGEON_YEEK_CAVE: RECALL_MIN_DEPTH,
            },
        )

        with patch.object(
            pol, "_recall_destination_safe", return_value=True
        ), patch.object(pol, "_descent_step", return_value=None):
            self.assertEqual(
                pol._town_recall_destination(snap),
                ("yeek-cave", DUNGEON_YEEK_CAVE),
            )
            self.assertEqual(
                pol._recall_selection_key(snap, DUNGEON_YEEK_CAVE), "a"
            )
            self.assertEqual(pol._town_special_key(snap), READ_KEY + "ra")

        self.assertNotEqual(pol.last_reason, "town:blocked:repetition")

    def test_yeek_repetition_recall_refuses_five_scrolls(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        pol._deepest_level = RECALL_MIN_DEPTH
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5)
        snap = replace(
            self._town_snap(),
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            recall_depth=RECALL_MIN_DEPTH,
            dungeon_recall_depths={
                DUNGEON_YEEK_CAVE: RECALL_MIN_DEPTH,
            },
        )

        with patch.object(
            pol, "_recall_destination_safe", return_value=True
        ), patch.object(pol, "_descent_step", return_value=None):
            self.assertEqual(pol._town_special_key(snap), WAIT_KEY)

        self.assertEqual(pol.last_reason, "town:blocked:repetition")

    def test_yeek_repetition_services_affordable_recall_shortage(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        pol._deepest_level = RECALL_MIN_DEPTH
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=5)
        position = Position(27, 97)
        temple = Position(27, 100)
        snap = Snapshot(
            player(27, 97, class_id=PLAYER_CLASS_WARRIOR, gold=18129),
            {
                position: grid(27, 97),
                Position(27, 98): grid(27, 98),
                Position(27, 99): grid(27, 99),
                temple: replace(grid(27, 100), store_number=STORE_TEMPLE),
            },
            [],
            floor_key=(0, 0, 0),
            inventory=[recall],
            equipment=[],
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            recall_depth=RECALL_MIN_DEPTH,
            dungeon_recall_depths={DUNGEON_YEEK_CAVE: RECALL_MIN_DEPTH},
        )
        recall_need = TownNeed(STORE_TEMPLE, "recall", "normal")

        with patch.object(
            pol, "_town_need_candidates", return_value=[recall_need]
        ):
            pol._break_town_cycle(snap)
            pol._town_blocked_reason = "repetition"
            key = pol._town_special_key(snap)

        self.assertFalse(pol._town_restock_suppressed)
        self.assertEqual(pol._town_errand_plan.stops, [STORE_TEMPLE])
        self.assertEqual(key, "6")
        self.assertEqual(pol.last_reason, "town:repetition-required-shopping")

    def test_repetition_block_completes_departure_recall_purchase(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._deepest_level = RECALL_MIN_DEPTH
        pol._town_blocked_reason = "repetition"
        position = Position(36, 90)
        shelf = StoreState(
            STORE_TEMPLE,
            [store_item("i", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=124,
                        count=3)],
        )
        inside = replace(
            self._town_snap(y=36, x=90, gold=4096),
            grids={position: replace(grid(36, 90), store_number=STORE_TEMPLE)},
            store=shelf,
            turn=4149055,
        )

        self.assertEqual(pol.choose_key(inside), LEAVE_STORE_KEY)
        outside = replace(inside, store=None, turn=inside.turn + 1)
        self.assertEqual(pol.choose_key(outside), WAIT_KEY)
        posted = pol.choose_key(replace(inside, turn=inside.turn + 2))

        self.assertTrue(posted.startswith(BUY_KEY + "i"), posted)

    def test_repetition_block_still_leaves_for_discretionary_purchase(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        lantern = item(
            "l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True
        )
        supplies = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, FOOD_MIN_SVAL, count=15),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5),
        ]
        torch = store_item("a", TVAL_LITE, SV_LITE_TORCH, price=2, count=5)
        inside = replace(
            self._town_snap(gold=4096),
            inventory=supplies,
            equipment=[lantern],
            store=StoreState(STORE_GENERAL, [torch]),
        )

        self.assertIs(pol._next_purchase(inside), torch)
        self.assertEqual(pol.choose_key(inside), LEAVE_STORE_KEY)
        self.assertIsNone(pol._shop_observation)

    def test_equipment_transaction_block_still_leaves_store(self):
        pol = HengbotPolicy()
        pol._town_blocked_reason = "equipment-transaction:incomplete-catalog"
        inside = replace(
            self._town_snap(gold=4096),
            store=StoreState(
                STORE_TEMPLE,
                [store_item("i", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                            price=124, count=3)],
            ),
        )

        self.assertEqual(pol._town_blocked_key(inside), LEAVE_STORE_KEY)
        self.assertIsNone(pol._shop_observation)

    def test_equipment_transaction_eject_keeps_current_visit_semantics(self):
        pol = HengbotPolicy()
        pol._town_blocked_reason = "equipment-transaction:incomplete-catalog"
        visit = StoreVisit("equipment-transaction", "equipment-work", STORE_TEMPLE)
        pol._store_visit = visit
        inside = replace(
            self._town_snap(gold=4096),
            store=StoreState(STORE_TEMPLE, []),
        )

        self.assertEqual(pol._town_blocked_key(inside), LEAVE_STORE_KEY)
        self.assertIs(pol._store_visit, visit)
        self.assertNotEqual(visit.phase, StoreVisitPhase.CLOSED)
        self.assertEqual(visit.outcome, "abandoned-with-restore")

    def test_repetition_eject_closes_abandoned_store_visit(self):
        pol = HengbotPolicy()
        pol._town_blocked_reason = "repetition"
        pol._store_visit = StoreVisit("town-errand", "shopping", STORE_GENERAL)
        inside = replace(
            self._town_snap(gold=4096),
            store=StoreState(STORE_GENERAL, []),
        )

        self.assertEqual(pol._town_blocked_key(inside), LEAVE_STORE_KEY)
        self.assertIsNone(pol._store_visit)
        self.assertEqual(pol._store_visit_last_closed.phase, StoreVisitPhase.CLOSED)
        self.assertEqual(
            pol._store_visit_last_closed.outcome, "repetition-block-abandoned"
        )

    def test_repetition_departure_purchase_keeps_owning_visit_open(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._deepest_level = RECALL_MIN_DEPTH
        pol._town_blocked_reason = "repetition"
        position = Position(36, 90)
        inside = replace(
            self._town_snap(y=36, x=90, gold=4096),
            grids={position: replace(grid(36, 90), store_number=STORE_TEMPLE)},
            store=StoreState(
                STORE_TEMPLE,
                [store_item("i", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                            price=124, count=3)],
            ),
        )

        self.assertEqual(pol.choose_key(inside), LEAVE_STORE_KEY)
        outside = replace(inside, store=None, turn=inside.turn + 1)
        self.assertEqual(pol.choose_key(outside), WAIT_KEY)
        visit = pol._store_visit
        self.assertIsNotNone(visit)
        posted = pol.choose_key(replace(inside, turn=inside.turn + 2))
        self.assertTrue(posted.startswith(BUY_KEY + "i"), posted)
        self.assertIs(pol._store_visit, visit)
        self.assertNotEqual(visit.phase, StoreVisitPhase.CLOSED)
        self.assertTrue(visit.operation_posted)

    def test_repetition_purchase_progress_releases_attempt_and_restock_wait(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._deepest_level = RECALL_MIN_DEPTH
        pol._town_blocked_reason = "repetition"
        pol._town_store_attempted[STORE_TEMPLE] = 4148783
        pol._town_restock_wait_until = 4149783
        position = Position(36, 90)
        shelf = StoreState(
            STORE_TEMPLE,
            [store_item("i", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, price=124,
                        count=3)],
        )
        inside = replace(
            self._town_snap(y=36, x=90, gold=4096),
            grids={position: replace(grid(36, 90), store_number=STORE_TEMPLE)},
            store=shelf,
            turn=4149055,
        )
        pol.choose_key(inside)
        pol.choose_key(replace(inside, store=None, turn=inside.turn + 1))
        posted = pol.choose_key(replace(inside, turn=inside.turn + 2))
        self.assertTrue(posted.startswith(BUY_KEY + "i"), posted)
        confirmed = replace(
            inside,
            store=None,
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=3)],
            player=replace(inside.player, gold=3724),
            turn=inside.turn + 3,
        )
        pol.choose_key(confirmed)

        self.assertNotIn(STORE_TEMPLE, pol._town_store_attempted)
        self.assertIsNone(pol._town_restock_wait_until)

    def test_measured_repetition_restock_shape_does_not_wait_thirty_times(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._deepest_level = RECALL_MIN_DEPTH
        pol._town_blocked_reason = "repetition"
        pol._town_store_attempted = {
            store_type: 4148144 for store_type in range(9)
        }
        pol._town_restock_wait_until = 4149783
        position = Position(36, 90)
        inside = replace(
            self._town_snap(y=36, x=90, gold=4096),
            grids={position: replace(grid(36, 90), store_number=STORE_TEMPLE)},
            store=StoreState(
                STORE_TEMPLE,
                [store_item("i", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                            price=124, count=3)],
            ),
            turn=4149055,
        )

        decisions = [pol.choose_key(inside)]
        decisions.append(pol.choose_key(replace(inside, store=None,
                                                turn=inside.turn + 1)))
        decisions.append(pol.choose_key(replace(inside, turn=inside.turn + 2)))
        decisions.extend(
            pol.choose_key(replace(inside, store=None, turn=inside.turn + offset))
            for offset in range(3, 30)
        )

        self.assertNotEqual(decisions, [WAIT_KEY] * 30)
        self.assertTrue(any(key.startswith(BUY_KEY + "i") for key in decisions),
                        decisions)

    def test_measured_outside_repetition_releases_wrong_store_visit(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._deepest_level = RECALL_MIN_DEPTH
        pol._town_blocked_reason = "repetition"
        pol._town_store_attempted = {
            store_type: 4148144 for store_type in range(9)
        }
        pol._town_restock_wait_until = 4149783
        pol._store_visit = StoreVisit("town-errand", "shopping", STORE_ALCHEMIST)
        capture = (
            Path(__file__).parent
            / "fixtures"
            / "measured-outside-repetition-stall.jsonl"
        )
        with capture.open(encoding="utf-8") as records:
            outside = parse_snapshot(json.loads(deque(records, maxlen=1)[0]), {})

        self.assertEqual(outside.player.position, Position(36, 90))
        self.assertEqual(outside.player.gold, 4096)
        self.assertIsNone(outside.store)
        self.assertFalse(any(item.is_recall_scroll for item in outside.inventory))

        decisions = []
        reasons = []
        for _ in range(30):
            decisions.append(pol._town_blocked_key(outside))
            reasons.append(pol.last_reason)

        self.assertNotEqual(decisions, [WAIT_KEY] * 30)
        self.assertIn("town:repetition-required-shopping", reasons)
        self.assertEqual(pol._store_visit.store_type, STORE_HOME)

    def test_yeek_recall_destination_preserves_walk_in_exemptions(self):
        snap = replace(
            self._town_snap(),
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            recall_depth=RECALL_MIN_DEPTH,
        )

        for mode in ("mine", "scavenge"):
            with self.subTest(mode=mode):
                pol = HengbotPolicy()
                pol._target_dungeon_id = DUNGEON_YEEK_CAVE
                pol._deepest_level = RECALL_MIN_DEPTH
                pol._fundraising_mode = mode
                with patch.object(
                    pol, "_recall_destination_safe", return_value=True
                ):
                    self.assertEqual(
                        pol._town_recall_destination(snap),
                        (None, DUNGEON_YEEK_CAVE),
                    )

        shallow = HengbotPolicy()
        shallow._target_dungeon_id = DUNGEON_YEEK_CAVE
        shallow._deepest_level = RECALL_MIN_DEPTH - 1
        with patch.object(
            shallow, "_recall_destination_safe", return_value=True
        ):
            self.assertEqual(
                shallow._town_recall_destination(snap),
                (None, DUNGEON_YEEK_CAVE),
            )

        quest = HengbotPolicy()
        quest._target_dungeon_id = DUNGEON_YEEK_CAVE
        quest._deepest_level = RECALL_MIN_DEPTH
        with patch.object(
            quest, "_taken_kill_quest_requires_walk_in", return_value=True
        ), patch.object(quest, "_recall_destination_safe", return_value=True):
            self.assertEqual(
                quest._town_recall_destination(snap),
                (None, DUNGEON_YEEK_CAVE),
            )

    def test_last_scroll_repetition_recall_is_forbidden_and_stops_visibly(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        pol._target_dungeon_id = DUNGEON_ANGBAND
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = replace(
            self._town_snap(),
            player=replace(
                self._town_snap().player,
                abilities=frozenset({"free_action", "resist_conf", "resist_fire"}),
            ),
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_ANGBAND,),
            recall_dungeon_id=DUNGEON_ANGBAND,
            recall_depth=24,
            dungeon_recall_depths={DUNGEON_ANGBAND: 24},
            angband_recall_unlocked=True,
        )

        with patch.object(
            pol, "_descent_step", return_value=None
        ), patch.object(
            pol, "_recall_destination_safe", return_value=True
        ):
            for _ in range(policy_module.NAV_ESCAPE_STEP_LIMIT):
                key = pol._town_blocked_key(snap)
                key = pol._bound_escape_wait(snap, key)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(pol.last_reason, "livelock:exhausted")
        self.assertFalse(pol._emergency_recall_sanctioned)

    def test_mining_walk_in_is_the_only_zero_recall_entry(self):
        snap = replace(self._town_snap(), inventory=[])
        for mode in ("mine", "scavenge"):
            with self.subTest(mode=mode):
                mining = HengbotPolicy()
                mining._target_dungeon_id = DUNGEON_YEEK_CAVE
                mining._fundraising_mode = mode
                preparation = mining._prepare_equipment_optimization(snap)
                self.assertEqual(preparation.blockers, ("calibration-required",))
                self.assertTrue(
                    mining._dungeon_entry_allowed(
                        snap, via_recall=False, destination_depth=1
                    )
                )
                self.assertFalse(
                    mining._dungeon_entry_allowed(
                        snap, via_recall=True, destination_depth=5
                    )
                )

        ordinary = HengbotPolicy()
        ordinary._target_dungeon_id = DUNGEON_YEEK_CAVE
        self.assertFalse(
            ordinary._dungeon_entry_allowed(
                snap, via_recall=False, destination_depth=1
            )
        )

    def test_last_scroll_return_to_town_is_unchanged(self):
        pol = HengbotPolicy()
        pol._returning_to_town = True
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = replace(
            self._town_snap(),
            floor_key=(DUNGEON_ANGBAND, 24, 0),
            town_flag=False,
            inventory=[recall],
        )

        self.assertEqual(pol._return_to_town_key(snap, []), READ_KEY + "r")
        self.assertEqual(pol.last_reason, "return:recall")

    def test_sanctioned_repetition_recall_ignores_readiness_cancel(self):
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        pol._target_dungeon_id = DUNGEON_ANGBAND
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10)
        snap = replace(
            self._town_snap(),
            player=replace(
                self._town_snap().player,
                abilities=frozenset({"resist_chaos"}),
            ),
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_ANGBAND,),
            recall_dungeon_id=DUNGEON_ANGBAND,
            dungeon_recall_depths={DUNGEON_ANGBAND: 31},
            angband_recall_unlocked=True,
        )
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
        with patch.object(
            pol, "_descent_step", return_value=None
        ), patch.object(
            pol, "_recall_destination_safe", return_value=True
        ):
            self.assertEqual(pol._town_blocked_key(snap), READ_KEY + "ra")

        recalling = replace(
            snap, player=replace(snap.player, recalling=True)
        )
        with patch.object(
            pol, "_activate_loadout_depth_fallback", return_value=None, create=True
        ), patch.object(
            pol, "_equipment_departure_ready", return_value=False
        ):
            self.assertIsNone(pol._town_cancel_unsafe_recall_key(recalling))

        self.assertTrue(pol._emergency_recall_sanctioned)
        self.assertNotEqual(pol.last_reason, "town:cancel-unready-recall")

    def test_sanctioned_repetition_recall_hard_hazard_still_cancels(self):
        pol = HengbotPolicy()
        pol._emergency_recall_sanctioned = True
        pol._pending_recall_dungeon_id = DUNGEON_YEEK_CAVE
        pol._target_dungeon_id = DUNGEON_ANGBAND
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=2)
        snap = replace(
            self._town_snap(),
            player=replace(self._town_snap().player, recalling=True),
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_ANGBAND,),
            recall_dungeon_id=DUNGEON_YEEK_CAVE,
            angband_recall_unlocked=True,
        )
        with patch.object(pol, "_recall_destination_safe", return_value=True):
            self.assertEqual(
                pol._town_cancel_unsafe_recall_key(snap), READ_KEY + "r"
            )

        self.assertEqual(
            pol.last_reason, "town:cancel-wrong-recall-destination"
        )
        self.assertFalse(pol._emergency_recall_sanctioned)

    def test_ordinary_unready_recall_still_cancels(self):
        pol = HengbotPolicy()
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=2)
        snap = replace(
            self._town_snap(),
            player=replace(self._town_snap().player, recalling=True),
            inventory=[recall],
            recall_dungeon_id=DUNGEON_ANGBAND,
            dungeon_recall_depths={DUNGEON_ANGBAND: 31},
        )
        with patch.object(
            pol, "_activate_loadout_depth_fallback", return_value=None, create=True
        ), patch.object(
            pol, "_equipment_departure_ready", return_value=False
        ):
            self.assertEqual(
                pol._town_cancel_unsafe_recall_key(snap), READ_KEY + "r"
            )

        self.assertEqual(pol.last_reason, "town:cancel-unready-recall")
        self.assertFalse(pol._emergency_recall_sanctioned)

    def test_sanction_does_not_leak_after_recall_floor_change(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        pol._emergency_recall_sanctioned = True
        dungeon = replace(
            self._town_snap(),
            floor_key=(DUNGEON_ANGBAND, 31, 0),
            town_flag=False,
        )
        pol._observe(dungeon)
        self.assertFalse(pol._emergency_recall_sanctioned)

        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=2)
        ordinary = replace(
            self._town_snap(),
            player=replace(self._town_snap().player, recalling=True),
            inventory=[recall],
            recall_dungeon_id=DUNGEON_ANGBAND,
            dungeon_recall_depths={DUNGEON_ANGBAND: 31},
        )
        with patch.object(
            pol, "_activate_loadout_depth_fallback", return_value=None, create=True
        ), patch.object(
            pol, "_equipment_departure_ready", return_value=False
        ):
            self.assertEqual(
                pol._town_cancel_unsafe_recall_key(ordinary), READ_KEY + "r"
            )
        self.assertEqual(pol.last_reason, "town:cancel-unready-recall")

    def test_live_blocked_repetition_with_nine_scrolls_recalls_to_angband(self):
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        pol._target_dungeon_id = DUNGEON_ANGBAND
        recall = item("d", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9)
        snap = replace(
            self._town_snap(),
            player=replace(
                self._town_snap().player,
                abilities=frozenset({"free_action", "resist_fire"}),
            ),
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_ANGBAND,),
            recall_dungeon_id=DUNGEON_ANGBAND,
            recall_depth=20,
            angband_recall_unlocked=True,
        )

        self.assertEqual(
            pol._town_recall_destination(snap), ("angband", DUNGEON_ANGBAND)
        )
        self.assertEqual(
            pol._recall_selection_key(snap, DUNGEON_ANGBAND), "a"
        )
        step = Position(snap.player.position.y, snap.player.position.x + 1)
        with patch.object(
            pol, "_descent_step", return_value=step
        ), patch.object(
            pol, "_entrance_travel_key", return_value=WAIT_KEY
        ), patch.object(
            pol, "_step_toward", return_value=WAIT_KEY
        ):
            self.assertEqual(pol._town_special_key(snap), READ_KEY + "da")

        self.assertEqual(pol.last_reason, "town:repetition-depart:recall")

    def test_blocked_repetition_stalled_entrance_leg_yields_to_recall(self):
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        pol._target_dungeon_id = DUNGEON_ANGBAND
        recall = item("d", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10)
        snap = replace(
            self._town_snap(),
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_ANGBAND,),
            recall_dungeon_id=DUNGEON_ANGBAND,
            angband_recall_unlocked=True,
        )

        step = Position(snap.player.position.y, snap.player.position.x + 1)
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
        with patch.object(
            pol, "_descent_step", return_value=step
        ), patch.object(
            pol, "_entrance_travel_key", return_value=WAIT_KEY
        ), patch.object(
            pol, "_step_toward", return_value=WAIT_KEY
        ), patch.object(
            pol, "_recall_destination_safe", return_value=True
        ):
            self.assertEqual(pol._town_special_key(snap), READ_KEY + "da")

        self.assertEqual(pol.last_reason, "town:repetition-depart:recall")

    def test_blocked_repetition_dungeon_recall_keeps_bare_read_macro(self):
        pol = HengbotPolicy()
        pol._floor_key = (DUNGEON_ANGBAND, 10, 0)
        pol._town_blocked_reason = "repetition"
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = replace(
            self._town_snap(),
            floor_key=(DUNGEON_ANGBAND, 10, 0),
            town_flag=False,
            inventory=[recall],
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE, DUNGEON_ANGBAND),
        )

        with patch.object(pol, "_descent_step", return_value=None):
            self.assertEqual(pol._town_blocked_key(snap), READ_KEY + "r")

        self.assertEqual(pol.last_reason, "town:repetition-depart:recall")

    def test_blocked_repetition_without_route_or_recall_still_waits(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        snap = self._town_snap()

        with patch.object(pol, "_descent_step", return_value=None):
            self.assertEqual(pol._town_special_key(snap), WAIT_KEY)

        self.assertEqual(pol.last_reason, "town:blocked:repetition")

    def test_blocked_equipment_transaction_yields_to_restock_wait(self):
        pol = HengbotPolicy()
        snap = self._town_snap()
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_EQUIP, "equip", "pack:upgrade"
        )
        pol._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )
        pol._block_equipment_transaction("incomplete-catalog")
        pol._town_restock_wait_until = snap.turn + 100
        pol._town_restock_wait_stores = (STORE_TEMPLE,)

        self.assertIsNone(pol._town_special_key(snap))
        self.assertIsNone(pol._equipment_transaction_session)
        self.assertIsNone(pol._town_blocked_reason)
        self.assertIn("pack:upgrade", pol._equipment_transaction_failed_items)

        self.assertEqual(pol._town_special_key(snap), RESTOCK_WAIT_MACRO)
        self.assertTrue(pol.last_reason.startswith("town:wait-restock:"))

    def test_non_equipment_blocked_reasons_keep_existing_behavior(self):
        snap = self._town_snap()
        repetition = HengbotPolicy()
        repetition._town_blocked_reason = "repetition"
        step = Position(snap.player.position.y, snap.player.position.x + 1)
        with patch.object(repetition, "_descent_step", return_value=step):
            self.assertEqual(repetition._town_blocked_key(snap), "6")
        self.assertEqual(repetition.last_reason, "town:repetition-depart")

        no_light = HengbotPolicy()
        no_light._town_blocked_reason = "departure-no-light"
        self.assertEqual(no_light._town_blocked_key(snap), WAIT_KEY)
        self.assertEqual(
            no_light.last_reason, "town:blocked:departure-no-light"
        )
        self.assertEqual(no_light._town_blocked_reason, "departure-no-light")

    def test_abandoned_equipment_item_is_excluded_for_rest_of_visit(self):
        upgrade = item(
            "a", 23, 1, name="upgrade", known=True, fully_known=True,
            is_equipment=True,
        )
        snap = replace(self._town_snap(), inventory=[upgrade])
        pol = HengbotPolicy()
        seed_character_calibration(pol, snap)
        pol._equipment_catalog.refresh_carried(
            snap.inventory, snap.equipment
        )
        upgrade_id = next(iter(pol._equipment_catalog.items)).id
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_EQUIP, "equip", upgrade_id
        )
        pol._equipment_transaction_session = (
            policy_module.EquipmentTransactionSession(
                policy_module.EquipmentTransactionPlan((action,), (), 1)
            )
        )
        pol._block_equipment_transaction("incomplete-catalog")
        self.assertIsNone(pol._town_blocked_key(snap))

        with patch(
            "hengbot.policy_equipment.prepare_warrior_optimization",
            return_value=SimpleNamespace(ready=False, transaction=None),
        ) as prepare:
            pol._prepare_equipment_optimization(snap)

        retried_ids = {owned.id for owned in prepare.call_args.args[1]}
        self.assertIn(upgrade_id, retried_ids)
        self.assertIn(upgrade_id, pol._equipment_transaction_failed_items)

    def test_blocked_repetition_walks_before_using_recall(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = replace(self._town_snap(), inventory=[recall])
        step = Position(snap.player.position.y, snap.player.position.x + 1)

        with patch.object(pol, "_descent_step", return_value=step):
            self.assertEqual(pol._town_special_key(snap), "6")

        self.assertEqual(pol.last_reason, "town:repetition-depart")

    def test_first_cycle_offense_does_not_use_recall_fallback(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_cycle_pending = True
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = replace(
            self._town_snap(gold=FUNDRAISING_START_GOLD),
            inventory=[recall],
        )

        with patch.object(pol, "_descent_step", return_value=None):
            self.assertEqual(pol._town_special_key(snap), WAIT_KEY)

        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertEqual(pol._town_cycle_breaks, 1)

    def test_blocked_repetition_enters_dungeon_at_departure_goal(self):
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        position = Position(34, 94)
        snap = replace(
            self._town_snap(),
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=3)
            ],
            grids={
                position: grid(
                    position.y,
                    position.x,
                    entrance=True,
                    entrance_dungeon_id=DUNGEON_YEEK_CAVE,
                )
            },
        )
        with patch.object(pol, "_descent_is_blocked", return_value=False):
            self.assertEqual(
                pol._town_special_key(snap), policy_module.ENTER_DUNGEON_MACRO
            )
        self.assertEqual(pol.last_reason, "town:repetition-depart:enter")

    def test_blocked_repetition_cannot_enter_with_incomplete_optimization(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_blocked_reason = "repetition"
        position = Position(34, 94)
        snap = replace(
            self._town_snap(),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=3)],
            grids={position: grid(
                position.y,
                position.x,
                entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )},
        )
        incomplete = SimpleNamespace(
            ready=False,
            result=None,
            transaction=None,
            blockers=("home-scan-incomplete",),
        )
        pol._prepare_equipment_optimization = lambda _snapshot: incomplete

        with patch.object(pol, "_descent_is_blocked", return_value=False):
            self.assertNotEqual(
                pol._town_special_key(snap), policy_module.ENTER_DUNGEON_MACRO
            )

    def test_nine_cell_resupply_carousel_hits_no_progress_limit(self):
        # Exact class of the live failure: unaffordable shopping approaches
        # advance through several town cells, with breakout decisions adding
        # enough distinct signatures to evade the compact-cycle detector, then
        # reaches the no-progress fallback.
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        cells = [
            (34, 94),
            (34, 95),
            (33, 96),
            (32, 97),
            (31, 98),
            (30, 98),
            (29, 99),
            (28, 100),
            (27, 101),
        ]
        steps = 0
        while not pol._town_cycle_pending and steps < TOWN_NO_PROGRESS_LIMIT:
            y, x = cells[(steps // 4) % len(cells)]
            pol.last_reason = (
                "breakout:least-visited" if steps % 6 == 5 else "shop:approach"
            )
            pol._observe(self._town_snap(y=y, x=x, gold=111))
            steps += 1

        self.assertTrue(pol._town_cycle_pending)
        self.assertEqual(steps, TOWN_NO_PROGRESS_LIMIT)

    def test_progress_resets_the_window(self):
        pol = HengbotPolicy()
        pol._floor_key = (0, 0, 0)
        pol._town_progress_marker = (100, 0, 0)
        self._prime_cycle(pol)
        pol.last_reason = "shop:travel"
        pol._observe(self._town_snap(gold=900))  # gold rose: not a cycle
        self.assertFalse(pol._town_cycle_pending)
        self.assertLessEqual(len(pol._town_signature_history), 1)

    def test_first_detection_breaks_the_cycle_and_latches_stores(self):
        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        key = pol._town_special_key(self._town_snap(gold=FUNDRAISING_START_GOLD))
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertIn(STORE_ALCHEMIST, pol._town_store_attempted)
        self.assertIn(STORE_HOME, pol._town_store_attempted)
        self.assertTrue(pol._shopping_stuck)
        self.assertEqual(pol._town_blocked_reason, "repetition")

    def test_first_detection_owns_departure_on_the_following_turn(self):
        # Live 01:00 replay: the first cycle break latched every shop but then
        # generic navigation emitted 167 stuck:wander decisions. Once no
        # shortage/fundraising owner remains, the entrance route must take over
        # immediately after the visible cycle-break turn.
        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = self._town_snap(gold=FUNDRAISING_START_GOLD)
        step = Position(snap.player.position.y, snap.player.position.x + 1)

        self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
        with patch.object(pol, "_descent_step", return_value=step):
            self.assertEqual(pol._town_special_key(snap), "6")

        self.assertEqual(pol.last_reason, "town:repetition-depart")
        self.assertEqual(pol._town_blocked_reason, "repetition")

    def test_pending_cycle_preempts_shopping_approach_in_decide(self):
        # The live carousel always had another shopping approach available.
        # A pending repair must run before that early return or cycle-break is
        # scheduled by _observe but never emitted.
        from unittest import mock

        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = self._town_snap(gold=FUNDRAISING_START_GOLD)
        with mock.patch.object(
            pol, "_shopping_approach_step", return_value=Position(1, 1)
        ):
            self.assertEqual(pol._decide(snap), WAIT_KEY)

        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertTrue(pol._town_restock_suppressed)

    def test_second_detection_reapplies_repair_and_forces_departure(self):
        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = self._town_snap()
        pol._town_special_key(snap)
        pol._town_cycle_pending = True
        step = Position(snap.player.position.y, snap.player.position.x + 1)
        with patch.object(pol, "_descent_step", return_value=step):
            key = pol._town_special_key(snap)
        self.assertEqual(key, "6")
        self.assertEqual(pol.last_reason, "town:repetition-depart")
        self.assertEqual(pol._town_blocked_reason, "repetition")
        self.assertTrue(pol._town_restock_suppressed)

    def test_cycle_break_suppresses_restock_waits_for_the_visit(self):
        # Without this the retry path starts a fresh in-town wait, un-latches
        # the stores when it expires, and the cycle resumes (observed live).
        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = self._town_snap()
        with patch.object(pol, "_town_need_candidates", return_value=[]):
            pol._town_special_key(snap)
        self.assertTrue(pol._town_restock_suppressed)
        self.assertIsNone(
            pol._retry_after_store_restock(snap, (STORE_ALCHEMIST,))
        )
        self.assertIsNone(pol._town_restock_wait_until)
        # And the town ladder no longer waits for restock either.
        pol._town_restock_wait_until = snap.turn + 1000
        key = pol._town_special_key(snap)
        self.assertNotEqual(pol.last_reason, "town:wait-restock")

    def test_post_break_visit_routes_to_no_store_at_all(self):
        # The choke point: after a cycle break the router yields NOTHING for the
        # rest of the visit, whatever errand branch would otherwise fire —
        # chasing individual un-gated branches left a new fuel line each time.
        from unittest import mock

        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = self._town_snap()
        catalog_need = TownNeed(STORE_HOME, "equipment-catalog", "home-first")
        with mock.patch.object(
            pol, "_town_need_candidates", return_value=[catalog_need]
        ):
            pol._town_special_key(snap)  # first break: optional work suppressed
        with mock.patch.object(
            pol,
            "_find_weapon_sale",
            return_value=item("w", TVAL_SWORD, 4, is_equipment=True),
        ), mock.patch.object(
            pol, "_town_need_candidates", return_value=[catalog_need]
        ):
            self.assertIsNone(pol._next_required_store_type(snap))

    def test_cycle_break_still_suppresses_opportunistic_equipment_catalog(self):
        pol = HengbotPolicy()
        snap = self._town_snap()
        catalog_need = TownNeed(STORE_HOME, "equipment-catalog", "home-first")

        with patch.object(
            pol, "_town_need_candidates", return_value=[catalog_need]
        ):
            pol._break_town_cycle(snap)

        self.assertTrue(pol._town_restock_suppressed)
        self.assertIsNone(pol._town_errand_plan)
        self.assertIsNone(pol._next_required_store_type(snap))

    def test_prepare_cycle_break_enters_scavenge_for_departure(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._town_cycle_pending = True
        snap = replace(
            self._town_snap(gold=102),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertEqual(pol._fundraising_mode, "scavenge")
        self.assertEqual(pol._scavenge_entry_gold, 102)

    def test_ready_mining_cycle_break_promotes_back_from_scavenge(self):
        from unittest import mock

        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._town_cycle_pending = True
        snap = replace(
            self._town_snap(gold=508),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        with mock.patch.object(
            pol, "_fundraising_departure_ready", return_value=False
        ), mock.patch.object(pol, "_fundraising_supplies_ready", return_value=True):
            self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
            self.assertEqual(pol.last_reason, "town:cycle-break")
            self.assertEqual(pol._fundraising_mode, "scavenge")
            self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
            self.assertEqual(pol._fundraising_mode, "mine")

        self.assertEqual(pol.last_reason, "fundraise:departure-blocked")
        self.assertEqual(
            pol.prompt_owner_handoff, "town:blocked:departure-no-light"
        )
        self.assertEqual(pol._fundraising_mode, "mine")

    def test_low_gold_cycle_break_starts_scavenge_and_avoids_immediate_return(self):
        pol = HengbotPolicy()
        town = replace(
            self._town_snap(gold=102),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        pol._break_town_cycle(town)

        self.assertEqual(pol._fundraising_mode, "scavenge")
        self.assertEqual(pol._scavenge_entry_gold, 102)
        yeek_one = replace(
            town,
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            town_flag=False,
            inventory=[],
        )
        self.assertFalse(pol._should_start_town_return(yeek_one))
        self.assertIsNone(pol._last_return_trigger)

    def test_broke_but_lit_fundraiser_leaves_after_first_cycle_offense(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._town_cycle_pending = True
        snap = replace(
            self._town_snap(gold=0),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        self.assertEqual(pol._town_special_key(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:cycle-break")
        self.assertIsNone(pol._town_special_key(snap))
        self.assertIsNone(pol._town_blocked_reason)

    def test_first_cycle_offense_stops_visibly_when_departure_has_no_light(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "prepare"
        pol._town_cycle_pending = True

        self.assertEqual(pol._town_special_key(self._town_snap(gold=0)), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:departure-no-light")
        self.assertEqual(pol._town_blocked_reason, "departure-no-light")

    def test_mine_cycle_first_offense_stops_visibly_when_light_died(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._town_cycle_pending = True

        self.assertEqual(pol._town_special_key(self._town_snap(gold=0)), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:blocked:departure-no-light")
        self.assertEqual(pol._town_blocked_reason, "departure-no-light")

    def test_scavenge_cycle_break_still_recovers_before_departure(self):
        pol = HengbotPolicy()
        pol._fundraising_mode = "scavenge"
        pol._town_restock_suppressed = True
        snap = replace(
            self._town_snap(),
            player=player(34, 94, hp=9, max_hp=10, class_id=PLAYER_CLASS_WARRIOR),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )

        self.assertEqual(pol._town_special_key(snap), REST_MACRO)
        self.assertEqual(pol.last_reason, "town:recover")

    def test_departure_blocked_reason_remains_cycle_detectable(self):
        self.assertNotIn("fundraise:departure-blocked", TOWN_CYCLE_IGNORED_REASONS)

    def test_bounded_entrance_travel_is_not_a_generic_town_cycle(self):
        self.assertIn("town:travel-entrance", TOWN_CYCLE_IGNORED_REASONS)

    def test_departure_only_mode_without_light_keeps_entrance_blocked(self):
        pol = HengbotPolicy()
        pol._town_restock_suppressed = True

        self.assertTrue(pol._descent_is_blocked(self._town_snap()))

    def test_cycle_break_bypasses_procurement_gate_and_exposes_entrance(self):
        from types import SimpleNamespace

        pol = HengbotPolicy()
        pol._town_cycle_pending = True
        snap = replace(
            self._town_snap(),
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                )
            ],
        )
        pol._town_special_key(snap)
        pol._town_map = SimpleNamespace(entrance=Position(34, 120))
        pol._town_map_active = lambda _snapshot: True
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE
        snap = replace(
            snap,
            grids={
                **snap.grids,
                Position(34, 120): grid(
                    34, 120, entrance=True,
                    entrance_dungeon_id=DUNGEON_YEEK_CAVE,
                ),
            },
        )

        self.assertFalse(pol._descent_is_blocked(snap))
        self.assertEqual(
            pol._town_map_descent_entrance(snap), Position(34, 120)
        )

    def test_cycle_break_does_not_commit_non_target_foot_entrance(self):
        from types import SimpleNamespace

        entrance = Position(34, 120)
        pol = HengbotPolicy()
        pol._town_restock_suppressed = True
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol._town_map = SimpleNamespace(entrance=entrance, walkable=frozenset({entrance}))
        pol._town_map_active = lambda _snapshot: True
        pol._descent_is_blocked = lambda _snapshot: False
        # Live 05:13 shape: the untaken town-based kill quest made the old
        # quest-depth early return accept every descent before entrance ID was
        # checked.  Since the entrance is also down_stairs, the router committed
        # Yeek while over-extension still targeted Angband.
        pol._quest_knowledge = {
            34: QuestInfo(
                34, "Arena kill", QUEST_TYPE_KILL_LEVEL, 34, 0,
                dungeon=0, max_num=1, monrace_id=1,
            )
        }
        snap = replace(
            self._town_snap(),
            quests={
                34: QuestState(
                    34, status=QUEST_STATUS_UNTAKEN,
                    type=QUEST_TYPE_KILL_LEVEL, level=34,
                    dungeon_id=0, fixed=True,
                )
            },
            grids={
                Position(34, 94): grid(34, 94),
                entrance: grid(
                    34, 120, downstairs=True, entrance=True,
                    entrance_dungeon_id=DUNGEON_YEEK_CAVE,
                ),
            },
        )

        self.assertIsNone(pol._town_map_descent_entrance(snap))
        self.assertIsNone(pol._descent_step(snap))
        self.assertIsNone(pol._nav_ledger.descent_target)

    def test_cycle_break_cannot_descend_from_non_target_entrance_underfoot(self):
        """Reproduce turns 2058602-2059139 after travel reached Yeek's gate.

        The route producer is stubbed as already committed so this remains a
        final step-5 regression: reverting the on-tile target check emits >\ry.
        """
        from types import SimpleNamespace

        entrance = Position(34, 120)
        pol = HengbotPolicy()
        pol._town_restock_suppressed = True
        # TEST_FAKERY_LINT_ALLOW: collaborator-wall: private branch unit isolates independent routing and readiness collaborators
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol._town_map = SimpleNamespace(
            entrance=entrance, walkable=frozenset({entrance})
        )
        pol._town_map_active = lambda _snapshot: True
        pol._town_map_descent_entrance = lambda _snapshot: entrance
        pol._descent_is_blocked = lambda _snapshot: False
        pol._quest_knowledge = {
            34: QuestInfo(
                34, "Arena kill", QUEST_TYPE_KILL_LEVEL, 34, 0,
                dungeon=0, max_num=1, monrace_id=1,
            )
        }
        snap = replace(
            self._town_snap(y=entrance.y, x=entrance.x),
            quests={
                34: QuestState(
                    34, status=QUEST_STATUS_UNTAKEN,
                    type=QUEST_TYPE_KILL_LEVEL, level=34,
                    dungeon_id=0, fixed=True,
                )
            },
            grids={entrance: grid(
                entrance.y, entrance.x, downstairs=True, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )},
        )

        key = pol.choose_key(snap)

        self.assertNotEqual(key, ">\ry")
        self.assertNotEqual(pol.last_reason, "descend")

    def test_kill_quest_still_allows_matching_mining_entrance(self):
        entrance = Position(31, 150)
        pol = HengbotPolicy()
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol._fundraising_mode = "mine"
        pol._quest_knowledge = {
            34: QuestInfo(
                34, "Arena kill", QUEST_TYPE_KILL_LEVEL, 34, 0,
                dungeon=0, max_num=1, monrace_id=1,
            )
        }
        snap = replace(
            self._town_snap(y=entrance.y, x=entrance.x),
            quests={
                34: QuestState(
                    34, status=QUEST_STATUS_UNTAKEN,
                    type=QUEST_TYPE_KILL_LEVEL, level=34,
                    dungeon_id=0, fixed=True,
                )
            },
            grids={entrance: grid(
                entrance.y, entrance.x, downstairs=True, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            )},
        )

        self.assertTrue(pol._is_descent_target(snap, snap.grids[entrance]))

    def test_sale_routes_honor_the_store_latches(self):
        # An unsellable candidate re-routed the bot to the sale store forever,
        # immune even to the cycle break (the sale routes skipped the latches).
        from unittest import mock

        pol = HengbotPolicy()
        pol._town_store_attempted[STORE_WEAPON] = 100
        snap = self._town_snap()
        with mock.patch.object(
            pol,
            "_find_weapon_sale",
            return_value=item("w", TVAL_SWORD, 4, is_equipment=True),
        ):
            self.assertNotEqual(pol._next_required_store_type(snap), STORE_WEAPON)

class TownTravelProgressTest(unittest.TestCase):
    GOAL = Position(10, 20)

    def test_progress_resets_both_counters(self):
        progress = TownTravelProgress(self.GOAL, 10, 3, 4, 7)
        self.assertEqual(progress.record(9, 8), "reissue")
        self.assertEqual(
            progress,
            TownTravelProgress(self.GOAL, 9, 0, 0, 8),
        )

    def test_new_turn_resets_same_turn_stalls_and_reissues(self):
        progress = TownTravelProgress(self.GOAL, 10, 3, 4, 7)
        self.assertEqual(progress.record(10, 8), "reissue")
        self.assertEqual(
            (progress.stalls, progress.turn_stalls, progress.last_turn),
            (0, 5, 8),
        )

    def test_new_turn_limit_falls_back(self):
        progress = TownTravelProgress(
            self.GOAL, 10, 3, TOWN_TRAVEL_TURN_STALL_LIMIT - 1, 7
        )
        self.assertEqual(progress.record(10, 8), "fallback")
        self.assertEqual(
            (progress.stalls, progress.turn_stalls, progress.last_turn),
            (0, TOWN_TRAVEL_TURN_STALL_LIMIT, 8),
        )

    def test_same_turn_increments_stalls_and_reissues(self):
        progress = TownTravelProgress(self.GOAL, 10, 3, 4, 7)
        self.assertEqual(progress.record(10, 7), "reissue")
        self.assertEqual(
            (progress.stalls, progress.turn_stalls, progress.last_turn),
            (4, 4, 7),
        )

    def test_same_turn_limit_falls_back(self):
        progress = TownTravelProgress(
            self.GOAL, 10, TOWN_TRAVEL_STALL_LIMIT - 1, 4, 7
        )
        self.assertEqual(progress.record(10, 7), "fallback")
        self.assertEqual(progress.stalls, TOWN_TRAVEL_STALL_LIMIT)

class RangedAttackTest(unittest.TestCase):
    """Direction-key firing at ray-aligned hostiles (no targeting UI)."""

    def _snap(self, *, monsters, inventory=(), equipment=(), player_kw=None):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(8, 14)
            for x in range(8, 22)
        }
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, **(player_kw or {})),
            grids,
            list(monsters),
            floor_key=(DUNGEON_YEEK_CAVE, 2, 0),
            width=30,
            height=30,
            inventory=list(inventory),
            equipment=[
                item("a", TVAL_SWORD, 17, name="sword", is_equipment=True),
                self._lantern(),
                *equipment,
            ],
        )

    @staticmethod
    def _lantern():
        return item("l", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)

    @staticmethod
    def _sling():
        return item("b", TVAL_BOW, SV_BOW_SLING, name="sling", is_equipment=True)

    @staticmethod
    def _shots(count=20):
        return item("s", TVAL_SHOT, 1, name="iron shots", count=count)

    def test_fires_matching_ammo_at_ray_aligned_hostile(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs6")
        self.assertEqual(policy.last_reason, "ranged:fire")

    def test_fires_along_a_diagonal_ray(self):
        snap = self._snap(
            monsters=[hostile(1, 13, 13, distance=3)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs3")
        self.assertEqual(policy.last_reason, "ranged:fire")

    def test_adjacent_hostile_stays_melee(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 11, distance=1)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "melee")

    def test_off_axis_hostile_uses_game_targeting(self):
        snap = self._snap(
            monsters=[hostile(1, 11, 14, distance=4)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs*t5\x1b")
        self.assertEqual(policy.last_reason, "ranged:fire-target")

    def test_blocked_ray_uses_game_targeting(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        blocked = dict(snap.grids)
        blocked[Position(10, 12)] = grid(10, 12, passable=False)
        snap = replace(snap, grids=blocked)
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs*t5\x1b")
        self.assertEqual(policy.last_reason, "ranged:fire-target")

    def test_wall_corner_uses_single_grid_offset_aim(self):
        snap = self._snap(
            monsters=[hostile(1, 7, 2, distance=8)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = {
            Position(y, x): grid(y, x)
            for y in range(1, 15)
            for x in range(1, 15)
        }
        grids[Position(7, 3)] = grid(7, 3, passable=False)
        snap = replace(snap, grids=grids)
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "fs*p777444444t5\x1b")
        self.assertEqual(policy.last_reason, "ranged:fire-offset")

    def test_ranged_fire_macros_start_with_f_and_store_purchase_posts_no_escape(self):
        cases = (
            (
                self._snap(
                    monsters=[hostile(1, 10, 15, distance=5)],
                    inventory=[self._shots()],
                    equipment=[self._sling()],
                ),
                "fs6",
                "ranged:fire",
            ),
            (
                self._snap(
                    monsters=[hostile(1, 11, 14, distance=4)],
                    inventory=[self._shots()],
                    equipment=[self._sling()],
                ),
                "fs*t5\x1b",
                "ranged:fire-target",
            ),
        )
        for snap, expected_key, expected_reason in cases:
            with self.subTest(reason=expected_reason):
                policy = HengbotPolicy()
                self.assertEqual(policy.choose_key(snap), expected_key)
                self.assertEqual(policy.last_reason, expected_reason)

        offset = self._snap(
            monsters=[hostile(1, 7, 2, distance=8)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        offset_grids = dict(offset.grids)
        offset_grids[Position(7, 3)] = grid(7, 3, passable=False)
        offset = replace(offset, grids=offset_grids)
        offset_policy = HengbotPolicy()
        self.assertEqual(
            offset_policy.choose_key(offset), "fs*p777444444t5\x1b"
        )
        self.assertEqual(offset_policy.last_reason, "ranged:fire-offset")

        store_snapshot = Snapshot(
            player(10, 10, gold=1000),
            {Position(10, 10): grid(10, 10)},
            [],
            store=StoreState(
                STORE_GENERAL,
                [store_item("b", TVAL_LITE, SV_LITE_LANTERN, price=120)],
            ),
        )
        store_key = _public_shop_inner(self, HengbotPolicy(), store_snapshot)
        self.assertEqual(store_key, "pb\r")
        self.assertFalse(store_key.startswith(LEAVE_STORE_KEY))

    def test_offset_aim_does_not_depend_on_nearest_targetable_monster(self):
        snap = self._snap(
            monsters=[
                hostile(1, 7, 2, distance=8),
                hostile(2, 10, 13, distance=3),
            ],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = dict(snap.grids)
        grids[Position(7, 3)] = grid(7, 3, passable=False)
        snap = replace(snap, grids=grids)
        policy = HengbotPolicy()

        self.assertEqual(
            policy._offset_fire_aim(snap, snap.visible_monsters[0]), Position(7, 1)
        )

    def test_near_side_neighbor_does_not_validate_as_offset_aim(self):
        snap = self._snap(
            monsters=[hostile(1, 2, 5, distance=8)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = dict(snap.grids)
        grids[Position(4, 6)] = grid(4, 6, passable=False)
        snap = replace(snap, grids=grids)
        policy = HengbotPolicy()

        near_side = Position(3, 6)
        through_path = projection_path(
            snap.player.position,
            near_side,
            RANGED_MAX_DISTANCE,
            lambda pos: pos == Position(4, 6),
            through=True,
        )
        self.assertLess(
            through_path.index(near_side),
            through_path.index(snap.visible_monsters[0].position),
        )
        self.assertNotEqual(
            policy._offset_fire_aim(snap, snap.visible_monsters[0]), near_side
        )

    def test_no_projectable_monster_still_uses_player_origin_offset(self):
        snap = self._snap(
            monsters=[hostile(1, 7, 2, distance=8)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = dict(snap.grids)
        grids[Position(7, 3)] = grid(7, 3, passable=False)
        snap = replace(snap, grids=grids)

        self.assertEqual(
            HengbotPolicy().choose_key(snap), "fs*p777444444t5\x1b"
        )

    def test_failed_targeting_is_skipped_until_player_moves(self):
        snap = self._snap(
            monsters=[hostile(1, 11, 14, distance=4)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()

        attempts = [policy.choose_key(snap) for _ in range(4)]
        self.assertEqual(attempts[:3], ["fs*t5\x1b"] * 3)
        self.assertNotEqual(attempts[3], "fs*t5\x1b")

        moved = replace(snap, player=replace(snap.player, position=Position(10, 11)))
        self.assertEqual(policy.choose_key(moved), "fs*t5\x1b")

        policy = HengbotPolicy()
        progressing = snap
        victim = snap.visible_monsters[0]
        for count, hp in zip(range(20, 15, -1), range(19, 14, -1)):
            progressing = replace(
                progressing,
                inventory=[self._shots(count)],
                visible_monsters=[replace(victim, hp=hp)],
            )
            self.assertEqual(policy.choose_key(progressing), "fs*t5\x1b")

    def test_moving_target_without_hp_loss_does_not_reset_failure_guard(self):
        base = self._snap(
            monsters=[hostile(1, 11, 14, hp=20, max_hp=20, distance=4)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        attempts = []
        for y in (11, 12, 11, 12):
            moving = replace(
                base,
                visible_monsters=[
                    replace(base.visible_monsters[0], position=Position(y, 14))
                ],
            )
            attempts.append(policy.choose_key(moving))

        self.assertEqual(attempts[:3], ["fs*t5\x1b"] * 3)
        self.assertNotEqual(attempts[3], "fs*t5\x1b")

    def test_changing_pack_indices_do_not_hide_failed_targeting_macro(self):
        base = self._snap(
            monsters=[hostile(1, 11, 14, hp=20, max_hp=20, distance=4)],
            inventory=[self._shots(20)],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        attempts = []
        for index in (1, 2, 3, 4):
            changing_pack = replace(
                base,
                visible_monsters=[
                    replace(base.visible_monsters[0], index=index)
                ],
            )
            attempts.append(policy.choose_key(changing_pack))

        self.assertEqual(attempts[:3], ["fs*t5\x1b"] * 3)
        self.assertNotEqual(attempts[3], "fs*t5\x1b")

    def test_failed_offset_targeting_is_skipped_after_three_attempts(self):
        snap = self._snap(
            monsters=[hostile(1, 7, 2, distance=8)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        grids = dict(snap.grids)
        grids[Position(7, 3)] = grid(7, 3, passable=False)
        snap = replace(snap, grids=grids)
        policy = HengbotPolicy()

        attempts = [policy.choose_key(snap) for _ in range(4)]
        self.assertEqual(attempts[:3], ["fs*p777444444t5\x1b"] * 3)
        self.assertNotEqual(attempts[3], "fs*p777444444t5\x1b")

    def test_aligned_hostile_is_preferred_when_off_axis_is_also_visible(self):
        snap = self._snap(
            monsters=[
                hostile(1, 11, 12, distance=2),
                hostile(2, 10, 15, distance=5),
            ],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs6")
        self.assertEqual(policy.last_reason, "ranged:fire")

    def test_distant_off_axis_sleeper_is_left_asleep(self):
        snap = self._snap(
            monsters=[hostile(1, 12, 18, distance=8, asleep=True)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:fire-target")

    def test_shot_targets_first_body_on_ray(self):
        snap = self._snap(
            monsters=[
                hostile(1, 10, 15, distance=5),
                hostile(2, 10, 12, distance=2),
            ],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        key = policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "ranged:fire")
        self.assertEqual(key, "fs6")

    def test_distant_sleeper_is_left_asleep(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 18, distance=8, asleep=True)],
            inventory=[self._shots()],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:fire")

    def test_afraid_player_still_fires(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[self._shots()],
            equipment=[self._sling()],
            player_kw={"afraid": True},
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "fs6")
        self.assertEqual(policy.last_reason, "ranged:fire")

    def test_confused_player_does_not_fire(self):
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[self._shots()],
            equipment=[self._sling()],
            player_kw={"confused": True},
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:fire")

    def test_mismatched_ammo_falls_back_to_oil_throw(self):
        arrows = item("s", TVAL_ARROW, 1, name="arrows", count=16)
        oil = item("o", TVAL_FLASK, 0, name="flask of oil", count=OIL_TARGET + 3)
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[arrows, oil],
            equipment=[self._sling()],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "vo6")
        self.assertEqual(policy.last_reason, "ranged:throw-oil")

    def test_early_floor_throws_cheap_torches(self):
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", count=8)
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[torch],
        )
        snap = replace(
            snap, grids={position: replace(cell, lit=True)
                         for position, cell in snap.grids.items()}
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "vt6")
        self.assertEqual(policy.last_reason, "ranged:throw-torch")

    def test_equipment_classified_pack_torch_is_throwable(self):
        torch = replace(
            item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", count=8),
            is_equipment=True,
        )
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)], inventory=[torch]
        )
        snap = replace(
            snap, grids={position: replace(cell, lit=True)
                         for position, cell in snap.grids.items()}
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "vt6")
        self.assertEqual(policy.last_reason, "ranged:throw-torch")

    def test_deep_floor_does_not_throw_torches(self):
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, name="torch", count=8)
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[torch],
        )
        snap = replace(snap, floor_key=(DUNGEON_YEEK_CAVE, 11, 0))
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:throw-torch")

    def test_potions_are_never_thrown(self):
        potions = item(
            "p", TVAL_POTION, SV_POTION_CURE_CRITICAL, name="potion", count=9
        )
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[potions],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertFalse(policy.last_reason.startswith("ranged:"))

    def test_torch_restock_for_shallow_plans(self):
        torch_ware = StoreItem("f", "torch", 99, TVAL_LITE, SV_LITE_TORCH, price=1)
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*self._strict_supplies_for_ammo()],
            equipment=[self._lantern()],
            store=StoreState(STORE_GENERAL, [torch_ware]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        selected = policy._next_purchase(snap)
        self.assertIsNotNone(selected)
        self.assertEqual(
            (selected.tval, selected.sval), (TVAL_LITE, SV_LITE_TORCH)
        )
        self.assertEqual(
            policy._purchase_quantity(snap, selected), TORCH_THROW_TARGET
        )

    def test_matching_ammo_prevents_throwing_torch_restock(self):
        torch_ware = StoreItem(
            "f", "torch", 99, TVAL_LITE, SV_LITE_TORCH, price=1
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[self._shots(), *self._strict_supplies_for_ammo()],
            equipment=[self._lantern(), self._sling()],
            store=StoreState(STORE_GENERAL, [torch_ware]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"

        self.assertIsNone(policy._next_purchase(snap))

    def test_pack_equipment_kind_torches_count_and_buy_as_one_batch(self):
        torch_ware = StoreItem("f", "torch", 99, TVAL_LITE, SV_LITE_TORCH, price=3)
        carried = item(
            "f", TVAL_LITE, SV_LITE_TORCH, name="inscribed torches",
            count=4, fuel=2500, is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=[carried, *self._strict_supplies_for_ammo()],
            equipment=[self._lantern()],
            store=StoreState(STORE_GENERAL, [torch_ware]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        self.assertEqual(policy._count_throwing_torches(snap), 4)
        self.assertEqual(policy._shop(snap), "pf6\r\r")

    def test_money_spent_without_torch_progress_leaves_within_bound(self):
        torch_ware = StoreItem("f", "torch", 99, TVAL_LITE, SV_LITE_TORCH, price=3)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        keys = []
        for attempt in range(STORE_STUCK_LIMIT + 1):
            snap = Snapshot(
                player(10, 10, gold=500 - 3 * attempt, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)}, [],
                floor_key=(0, 0, 0), town_flag=True,
                inventory=[*self._strict_supplies_for_ammo()],
                equipment=[self._lantern()],
                store=StoreState(STORE_GENERAL, [torch_ware]),
            )
            keys.append(policy._shop(snap))
        self.assertEqual(keys[-1], LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "shop:defective-target-leave")

    def test_normal_torch_restock_progress_stops_at_target(self):
        torch_ware = StoreItem("f", "torch", 99, TVAL_LITE, SV_LITE_TORCH, price=3)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        for count in range(TORCH_THROW_TARGET):
            carried = item(
                "f", TVAL_LITE, SV_LITE_TORCH, count=count + 1,
                fuel=2500, is_equipment=True,
            )
            snap = Snapshot(
                player(10, 10, gold=500 - 3 * count, class_id=PLAYER_CLASS_WARRIOR),
                {Position(10, 10): grid(10, 10)}, [],
                floor_key=(0, 0, 0), town_flag=True,
                inventory=[carried, *self._strict_supplies_for_ammo()],
                equipment=[self._lantern()],
                store=StoreState(STORE_GENERAL, [torch_ware]),
            )
            key = policy._shop(snap)
        self.assertNotEqual(policy.last_reason, "shop:defective-target-leave")
        self.assertNotEqual(policy.last_reason, "shop:buy-torch")

    def test_sells_48_inscribed_torches_down_to_target(self):
        torches = item(
            "f", TVAL_LITE, SV_LITE_TORCH,
            name="torches {@v0=g}", count=48, fuel=2500, is_equipment=True,
        )
        lantern = item("g", TVAL_LITE, SV_LITE_LANTERN, name="lantern", fuel=7500)
        equipped_torch = item(
            "light", TVAL_LITE, SV_LITE_TORCH,
            name="wield backup torch", fuel=2384, is_equipment=True,
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            inventory=[torches, lantern], equipment=[equipped_torch],
            store=StoreState(STORE_GENERAL, []),
        )
        policy = HengbotPolicy()
        self.assertEqual(policy._shop(snap), "{f@0\r")

    def test_oil_reserve_is_never_thrown(self):
        oil = item("o", TVAL_FLASK, 0, name="flask of oil", count=OIL_TARGET)
        snap = self._snap(
            monsters=[hostile(1, 10, 15, distance=5)],
            inventory=[oil],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "ranged:throw-oil")

    def test_town_depth_uses_shallowest_supply_threshold(self):
        policy = HengbotPolicy()

        self.assertEqual(policy._supply_threshold("oil", "return", 0), 0)
        self.assertEqual(
            policy._supply_threshold("oil", "departure", 0), OIL_TARGET
        )

    def test_ammo_purchase_at_weapon_smith(self):
        shots = StoreItem("d", "iron shot", 99, TVAL_SHOT, 1, price=1)
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[*self._strict_supplies_for_ammo()],
            equipment=[self._sling(), self._lantern()],
            store=StoreState(STORE_WEAPON, [shots]),
        )
        policy = HengbotPolicy()
        selected = policy._next_purchase(snap)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.tval, TVAL_SHOT)
        self.assertEqual(
            policy._purchase_quantity(snap, selected), AMMO_CARRY_TARGET
        )

    def test_sixty_matching_rounds_still_register_optional_ammo_need(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[
                item("a", TVAL_SHOT, 1, name="iron shots", count=60),
                *self._strict_supplies_for_ammo(),
            ],
            equipment=[self._sling(), self._lantern()],
        )
        policy = HengbotPolicy()

        needs = policy._enumerate_town_needs(snap)

        self.assertIn(TownNeed(STORE_WEAPON, "ammo", "normal"), needs)
        self.assertNotIn(
            "ammo",
            [need.category for need in policy._departure_blocking_town_needs(snap)],
        )
        policy._town_departure_ready = lambda candidate: True
        self.assertFalse(policy._town_claims_active(snap))

    def test_fundraising_restock_enumerates_optional_ammo_after_mandatory_supplies(self):
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[
                item("a", TVAL_SHOT, 1, name="iron shots", count=60),
                *self._strict_supplies_for_ammo(),
            ],
            equipment=[self._sling(), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertIn(
            TownNeed(STORE_WEAPON, "ammo", "normal"),
            policy._enumerate_town_needs(snap),
        )

    def test_fundraising_ammo_waits_for_kit_and_preserves_kit_reserve(self):
        shots = StoreItem("d", "iron shot", 99, TVAL_SHOT, 1, price=2)
        supplies = [
            supply for supply in self._strict_supplies_for_ammo()
            if not supply.is_digging_tool
        ]
        snap = Snapshot(
            player(10, 10, gold=100, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=supplies,
            equipment=[self._sling(), self._lantern()],
            store=StoreState(STORE_WEAPON, [shots]),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertNotIn(
            "ammo", [need.category for need in policy._enumerate_town_needs(snap)]
        )
        self.assertGreater(policy._fundraising_kit_reserve(snap), 0)
        self.assertIsNone(policy._next_purchase(snap))

    def test_fundraising_ammo_waits_for_each_mandatory_supply(self):
        ready = self._strict_supplies_for_ammo()
        cases = {
            "food": [supply for supply in ready if supply.tval != TVAL_FOOD],
            "oil": [supply for supply in ready if supply.tval != TVAL_FLASK],
            "detection": [
                supply
                for supply in ready
                if not supply.is_treasure_detection_scroll
            ],
        }
        for shortage, inventory in cases.items():
            with self.subTest(shortage=shortage):
                snap = Snapshot(
                    player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
                    {Position(10, 10): grid(10, 10)},
                    [], floor_key=(0, 0, 0), town_flag=True,
                    inventory=inventory,
                    equipment=[self._sling(), self._lantern()],
                )
                policy = HengbotPolicy()
                policy._fundraising_mode = "prepare"
                self.assertNotIn(
                    "ammo",
                    [need.category for need in policy._enumerate_town_needs(snap)],
                )

        dim_lantern = replace(self._lantern(), fuel=1)
        dim = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=ready,
            equipment=[self._sling(), dim_lantern],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        self.assertNotIn(
            "ammo", [need.category for need in policy._enumerate_town_needs(dim)]
        )

    def test_fundraising_torch_need_requires_no_matching_launcher_ammo(self):
        base = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[*self._strict_supplies_for_ammo()],
            equipment=[self._sling(), self._lantern()],
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        self.assertIn(
            TownNeed(STORE_GENERAL, "throwing-torches", "normal"),
            policy._enumerate_town_needs(base),
        )

        with_ammo = replace(
            base,
            inventory=[self._shots(), *self._strict_supplies_for_ammo()],
        )
        self.assertNotIn(
            "throwing-torches",
            [need.category for need in policy._enumerate_town_needs(with_ammo)],
        )

    def test_fundraising_optional_ammo_never_blocks_departure_without_stock_or_gold(self):
        snap = Snapshot(
            player(10, 10, gold=0, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[
                *self._strict_supplies_for_ammo(),
                item("y", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            ],
            equipment=[self._sling(), self._lantern()],
            store=StoreState(STORE_WEAPON, []),
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"

        self.assertIn(
            "ammo", [need.category for need in policy._enumerate_town_needs(snap)]
        )
        self.assertNotIn(
            "ammo",
            [need.category for need in policy._departure_blocking_town_needs(snap)],
        )
        policy._town_departure_ready = lambda candidate: True
        self.assertFalse(policy._town_claims_active(snap))

    def test_missing_96_arrows_are_bought_in_one_prompt_complete_macro(self):
        arrows = StoreItem("j", "arrows", 99, TVAL_ARROW, 1, price=1)
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[
                *self._strict_supplies_for_ammo(),
                item("a", TVAL_ARROW, 1, name="arrows", count=3),
            ],
            equipment=[
                item("b", TVAL_BOW, SV_BOW_SHORT, name="short bow", is_equipment=True),
                self._lantern(),
            ],
            store=StoreState(STORE_WEAPON, [arrows]),
        )

        key = HengbotPolicy()._shop(snap)

        # Live economy records show that purchase-order.cpp consumes the item
        # letter, quantity digits + Return, and DEFAULT_Y confirmation Return.
        # Nothing remains for the store loop.
        self.assertEqual(key, "pj96\r\r")
        self.assertEqual(key[2:], "96\r\r")


    def test_stale_sale_candidate_emits_no_sell_letter_or_prompt_tail(self):
        stale = item("o", TVAL_SWORD, 1, name="club", is_equipment=True, known=True)
        replacement = item(
            "o", TVAL_SWORD, 2, name="dagger", is_equipment=True, known=True
        )
        snap = Snapshot(
            player(10, 10, gold=500, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], floor_key=(0, 0, 0), town_flag=True,
            inventory=[replacement],
            store=StoreState(STORE_WEAPON, []),
        )
        policy = HengbotPolicy()

        key = policy._store_sell_key(snap, stale, "shop:sell-inferior-weapon")

        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertFalse(key.startswith(SELL_KEY))

    @staticmethod
    def _strict_supplies_for_ammo():
        return [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=12),
            item("f", TVAL_FOOD, FOOD_MIN_SVAL, count=5),
            item("o", TVAL_FLASK, 0, count=OIL_TARGET),
            item("z", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
            item("v", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=5),
        ]

class ResistanceGapReturnTest(unittest.TestCase):
    """_is_descent_target only ever gates the NEXT floor (dungeon_level + 1); nothing
    previously caught the character already standing somewhere its CURRENT gear no
    longer covers -- e.g. recall landing at the save-backed deepest floor after a
    resistance-granting item was swapped/stashed, or an amulet swap mid-dive dropping
    a required resistance. _should_start_town_return now retreats for that gap too."""

    def _at(self, depth, abilities):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, abilities=frozenset(abilities)),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_ANGBAND, depth, 0),
            inventory=[
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=6),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            ],
            equipment=[
                item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
            ],
        )

    def test_missing_current_depth_ability_starts_a_return(self):
        # 26F needs pois+cold+elec+acid (see DEPTH_ABILITY_REQUIREMENTS); a bare
        # character standing there already (not merely about to descend into it)
        # has none of them.
        snap = self._at(26, set())
        policy = HengbotPolicy()

        self.assertTrue(policy._should_start_town_return(snap))
        self.assertEqual(policy._last_return_trigger, "resist-gap")

    def test_fully_resisted_current_depth_does_not_return(self):
        snap = self._at(26, {"resist_pois", "resist_cold", "resist_elec", "resist_acid"})

        self.assertFalse(HengbotPolicy()._should_start_town_return(snap))

    def test_shallow_floor_below_the_table_does_not_return(self):
        # 13F is below the table's first (20-25F) band, so a character with zero
        # abilities is unaffected -- and since Yeek Cave mining never goes deeper
        # than 13F, fundraising is naturally exempt too without a special case.
        snap = self._at(13, set())

        self.assertFalse(HengbotPolicy()._should_start_town_return(snap))

class RecallShortageBehaviorRestrictionTest(unittest.TestCase):
    @staticmethod
    def _snapshot(depth, recall_count, *, town=False, downstairs=False):
        inventory = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=recall_count),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5),
        ]
        if recall_count == 0:
            inventory = inventory[1:]
        return Snapshot(
            player(10, 10, gold=5000, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(
                    10, 10, downstairs=downstairs, upstairs=not town
                )
            },
            [],
            floor_key=(0, 0, 0) if town else (DUNGEON_YEEK_CAVE, depth, 0),
            town_flag=town,
            inventory=inventory,
            equipment=[
                item(
                    "L", TVAL_LITE, SV_LITE_LANTERN,
                    fuel=7000, known=True, is_equipment=True,
                )
            ],
        )

    @staticmethod
    def _ordinary_policy():
        policy = HengbotPolicy()
        policy._deepest_level = 4
        policy._equipment_catalog.home_scan_complete = True
        policy._fixed_quest_key = lambda _snapshot, _hostiles: None
        policy._conquest_loot_key = lambda _snapshot: None
        policy._victory_loot_key = lambda _snapshot: None
        return policy

    def test_town_shortage_waits_instead_of_ordinary_departure(self):
        policy = self._ordinary_policy()
        town = self._snapshot(0, 0, town=True, downstairs=True)

        self.assertTrue(policy._recall_departure_shortage(town))
        self.assertFalse(
            policy._dungeon_entry_allowed(
                town, via_recall=False, destination_depth=1
            )
        )
        key = policy.choose_key(town)

        self.assertEqual(key, RESTOCK_WAIT_MACRO)
        self.assertIn("restock", policy.last_reason)
        self.assertNotEqual(policy.last_reason, "town:travel-entrance")
        self.assertNotEqual(key, policy_module.ENTER_DUNGEON_MACRO)

    def test_departure_shortage_does_not_block_downstairs_in_dungeon(self):
        policy = self._ordinary_policy()
        dungeon = self._snapshot(4, 5, downstairs=True)

        self.assertTrue(policy._recall_departure_shortage(dungeon))
        self.assertFalse(policy._descent_is_blocked(dungeon))
        self.assertEqual(policy.choose_key(dungeon), policy_module.DOWN_STAIRS_KEY)

    def test_recall_retreat_threshold_is_the_only_in_dungeon_shortage_trigger(self):
        for depth, recall_count, should_return in (
            (5, 0, True),
            (6, 2, True),
            (4, 5, False),
        ):
            with self.subTest(depth=depth, recall_count=recall_count):
                policy = self._ordinary_policy()
                dungeon = self._snapshot(depth, recall_count)

                policy.choose_key(dungeon)

                self.assertEqual(policy._returning_to_town, should_return)
                if should_return:
                    self.assertEqual(
                        policy._last_return_trigger, "recall-shortage"
                    )
                else:
                    self.assertNotEqual(
                        policy._last_return_trigger, "recall-shortage"
                    )

    def test_mid_dive_shortage_latches_return_and_ascends(self):
        policy = self._ordinary_policy()
        dungeon = self._snapshot(2, 0)

        key = policy.choose_key(dungeon)

        self.assertTrue(policy._returning_to_town)
        self.assertEqual(key, policy_module.UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_live_yeek_one_four_scrolls_does_not_trigger_recall_shortage(self):
        policy = self._ordinary_policy()
        dungeon = self._snapshot(1, 4)

        key = policy.choose_key(dungeon)

        self.assertFalse(policy._returning_to_town)
        self.assertNotEqual(key, READ_KEY + "r")
        self.assertNotEqual(policy.last_reason, "return:recall")
        self.assertNotEqual(policy._last_return_trigger, "recall-shortage")

    def test_sufficient_recall_preserves_departure_and_descent(self):
        policy = self._ordinary_policy()
        dungeon = self._snapshot(1, 6, downstairs=True)

        self.assertFalse(policy._recall_departure_shortage(dungeon))
        self.assertFalse(policy._descent_is_blocked(dungeon))
        self.assertEqual(policy.choose_key(dungeon), policy_module.DOWN_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "descend")

    def test_shortage_does_not_change_active_shallow_mining(self):
        policy = self._ordinary_policy()
        policy._fundraising_mode = "mine"
        dungeon = self._snapshot(1, 0, downstairs=True)
        expected = "mining-owner"
        policy._fundraising_key = lambda _snapshot, _hostiles: expected

        self.assertFalse(policy._recall_departure_shortage(dungeon))
        self.assertEqual(policy.choose_key(dungeon), expected)
        self.assertFalse(policy._returning_to_town)

    def test_shortage_does_not_restrict_character_creation_or_opening_q34(self):
        policy = self._ordinary_policy()
        birth = self._snapshot(0, 0, town=True)
        birth = replace(
            birth,
            player=replace(birth.player, class_id=-1),
        )

        self.assertTrue(policy._recall_departure_shortage(birth))
        self.assertTrue(policy._recall_shortage_opening_exempt(birth))

        quest = QuestState(
            id=34, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
        )
        opening = replace(
            self._snapshot(0, 0, town=True),
            player=replace(
                self._snapshot(0, 0, town=True).player,
                level=1,
                class_id=PLAYER_CLASS_WARRIOR,
            ),
            town_id=0,
            quests={34: quest},
        )
        policy.approved_quest_strategy = (
            lambda quest_id: object() if quest_id == 34 else None
        )
        policy._fixed_quest_is_offered = (
            lambda _snapshot, quest_id: quest_id == 34
        )

        self.assertTrue(policy._recall_departure_shortage(opening))
        self.assertTrue(policy._opening_q34_active(opening))
        self.assertTrue(policy._recall_shortage_opening_exempt(opening))

class NoSafeRecallDestinationTest(unittest.TestCase):
    def _fixture(self, *, alchemist_visible=False):
        current = grid(45, 123, lit=True, in_view=True)
        grids = {current.position: current}
        if alchemist_visible:
            entrance = replace(
                grid(45, 124, lit=True, in_view=True),
                store_number=STORE_ALCHEMIST,
            )
            grids[entrance.position] = entrance
        snapshot = Snapshot(
            player(
                45,
                123,
                level=29,
                gold=22412,
                class_id=PLAYER_CLASS_WARRIOR,
                abilities={"resist_cold", "resist_neth", "resist_pois", "see_invisible"},
            ),
            grids,
            [],
            turn=2939887,
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            recall_dungeon_id=DUNGEON_ANGBAND,
            entered_dungeon_ids=(DUNGEON_ANGBAND,),
            dungeon_recall_depths={DUNGEON_ANGBAND: 30},
            recall_depth=30,
            angband_recall_unlocked=True,
            town_flag=True,
            inventory=[
                item(
                    "a", TVAL_SCROLL, SV_SCROLL_TELEPORT,
                    count=45, known=True, fully_known=True,
                ),
                item(
                    "b", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                    count=26, known=True, fully_known=True,
                ),
                item(
                    "c", TVAL_STAFF, SV_STAFF_IDENTIFY,
                    count=3, charges=39, pval=39,
                    known=True, fully_known=True,
                ),
            ],
            equipment=[
                item(
                    "light", TVAL_LITE, SV_LITE_FEANOR,
                    known=True, fully_known=True, is_equipment=True,
                    known_flags=frozenset({122}),
                ),
            ],
        )
        policy = HengbotPolicy()
        policy._deepest_level = 31
        policy._target_dungeon_id = DUNGEON_ANGBAND
        policy._equipment_catalog.home_scan_complete = True
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",),
            result=None,
        )
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_ALCHEMIST, STORE_HOME, STORE_BLACK],
            index=1,
        )
        policy._last_in_town = True
        return policy, snapshot

    def test_live_block_replay_yields_to_real_town_claim_publicly(self):
        policy, snapshot = self._fixture()
        key = policy.choose_key(snapshot)

        self.assertEqual(key, "8")
        self.assertEqual(policy.last_reason, "probe")
        self.assertNotEqual(key, WAIT_KEY)
        self.assertIsNone(policy._town_blocked_reason)

    def test_live_block_replay_reaches_real_alchemist_step_publicly(self):
        policy, snapshot = self._fixture()
        first_key = policy.choose_key(snapshot)
        _, routeable = self._fixture(alchemist_visible=True)
        second_key = policy.choose_key(
            replace(routeable, turn=snapshot.turn + 1)
        )

        self.assertEqual((first_key, second_key), ("8", "6"))
        self.assertEqual(policy.last_reason, "explore")
        self.assertIsNone(policy._town_blocked_reason)

    def test_stale_restock_verdict_cannot_blind_black_market_approach(self):
        """Turn 4052134: recall is satisfied; the live staff need owns store 7."""
        policy, snapshot = self._fixture()
        black_market = replace(
            grid(45, 124, lit=True, in_view=True), store_number=STORE_BLACK
        )
        identify_staff = replace(
            snapshot.inventory[2], count=1, charges=19, pval=19
        )
        snapshot = replace(
            snapshot,
            turn=4052134,
            grids={**snapshot.grids, black_market.position: black_market},
            inventory=[*snapshot.inventory[:2], identify_staff],
        )
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=None
        )
        policy._town_was_in_town = True
        policy._floor_key = snapshot.floor_key
        durable_state = policy._town_observable_effect_state(snapshot)
        for store_type in (
            STORE_GENERAL, STORE_ARMOURY, STORE_WEAPON, STORE_TEMPLE,
            STORE_ALCHEMIST, STORE_MAGIC,
        ):
            policy._town_visit_ledger.nonhome_attempted_without_effect[
                store_type
            ] = durable_state
        policy._town_errand_plan = None
        policy._town_blocked_reason = "restock-store-unreachable"

        key = policy.choose_key(snapshot)

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertEqual(policy._shopping_approach_store_type, STORE_BLACK)
        self.assertEqual(policy._shopping_approach_goal, black_market.position)
        self.assertIsNone(policy._town_blocked_reason)

    def test_drive_ending_town_terminals_survive_decision_rederivation(self):
        for terminal in (
            "departure-unsatisfiable",
            "no-safe-recall-destination",
            "equipment-work-home-route-exhausted",
        ):
            with self.subTest(terminal=terminal):
                policy, snapshot = self._fixture()
                policy._town_was_in_town = True
                policy._floor_key = snapshot.floor_key
                policy._town_blocked_reason = terminal
                budget = policy._town_turn_arbiter.registry["town-plan"].budget

                for decision in range(40):
                    current = replace(
                        snapshot,
                        turn=snapshot.turn + decision,
                        messages=(f"terminal observation {decision}",),
                    )
                    key = policy.choose_key(current)

                    self.assertEqual(key, WAIT_KEY)
                    self.assertEqual(
                        policy.last_reason,
                        (
                            f"town:blocked:{terminal}"
                            if decision < budget
                            else "town:blocked:owner-retired"
                        ),
                    )
                    self.assertEqual(policy._town_blocked_reason, terminal)

    def test_no_town_work_latches_visible_terminal(self):
        policy, snapshot = self._fixture()
        seed_character_calibration(policy, snapshot)
        policy.choose_key(snapshot)
        policy._town_errand_plan = None
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=None,
        )
        stopped = replace(snapshot, turn=snapshot.turn + 1)
        for store_type in (
            STORE_GENERAL, STORE_ARMOURY, STORE_WEAPON, STORE_TEMPLE,
            STORE_ALCHEMIST, STORE_MAGIC, STORE_BLACK,
        ):
            policy._town_visit_ledger.nonhome_attempted_without_effect[store_type] = (
                policy._town_observable_effect_state(stopped)
            )
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            policy_module.TOWN_STOP_PASS_LIMIT
        )
        key = policy.choose_key(stopped)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason,
            "town:blocked:depth-gate:destination-30:missing-resist_acid,resist_elec",
        )
        self.assertEqual(
            policy._town_blocked_reason,
            "depth-gate:destination-30:missing-resist_acid,resist_elec",
        )

    def test_successful_depth_30_transaction_keeps_home_reachable_publicly(self):
        """Pin the live 21:50:07 success-revokes-allowance shape."""
        policy, snapshot = self._fixture()
        home = replace(
            grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
        )
        snapshot = replace(
            snapshot,
            grids={**snapshot.grids, home.position: home},
        )
        target = snapshot.inventory[0]
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
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=object(),
        )
        policy._set_equipment_transaction_session(session)
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            TOWN_STOP_PASS_LIMIT
        )

        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(
            policy._town_visit_ledger.approach_fails[STORE_HOME], 3
        )

        key = policy.choose_key(snapshot)

        self.assertEqual(policy._deepest_level, 31)
        self.assertEqual(
            policy._town_store_visit_limit(STORE_HOME),
            CALIBRATION_HOME_VISIT_LIMIT,
        )
        self.assertNotEqual(key, WAIT_KEY)
        self.assertIs(policy._equipment_transaction_session, session)
        self.assertTrue(session.executable)
        self.assertNotEqual(
            policy.last_reason, "equipment-transaction:abandon-blocked"
        )

    def test_depth_30_transaction_detector_refusal_keeps_home_route_publicly(self):
        """Turn-2975934 shape: detector refusal cannot destroy owned Home work."""
        policy, snapshot = self._fixture()
        home = replace(
            grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
        )
        snapshot = replace(
            snapshot,
            grids={**snapshot.grids, home.position: home},
        )
        target = snapshot.inventory[0]
        identity = policy_module.equipment_identity(target)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            f"pack:{identity}:0",
            item_identity=identity,
        )
        session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 30)
        )
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=object(),
        )
        policy._set_equipment_transaction_session(session)
        policy._town_was_in_town = True
        policy._floor_key = snapshot.floor_key
        policy._recent.extend([snapshot.player.position] * STUCK_WINDOW)
        policy._shop_approach_stuck_count = SHOP_APPROACH_STUCK_LIMIT - 1

        key = policy.choose_key(snapshot)

        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "equipment-transaction:approach-home")
        self.assertIs(policy._equipment_transaction_session, session)
        self.assertTrue(session.executable)
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._town_visit_ledger.approach_fails[STORE_HOME], 0)

    def test_no_safe_recall_terminal_waits_for_outstanding_equipment_work(self):
        policy, snapshot = self._fixture()
        policy.choose_key(snapshot)
        policy._town_errand_plan = None
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("optimization-timeout",), result=None,
        )
        for store_type in (
            STORE_GENERAL, STORE_ARMOURY, STORE_WEAPON, STORE_TEMPLE,
            STORE_ALCHEMIST, STORE_MAGIC, STORE_BLACK,
        ):
            policy._town_visit_ledger.nonhome_attempted_without_effect[store_type] = (
                policy._town_observable_effect_state(snapshot)
            )
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            policy._town_store_visit_limit(STORE_HOME) - 1
        )

        key = policy.choose_key(replace(snapshot, turn=snapshot.turn + 1))

        self.assertNotEqual(
            policy.last_reason, "town:blocked:no-safe-recall-destination"
        )
        self.assertIsNone(policy._town_blocked_reason)
        self.assertNotEqual(key, WAIT_KEY)

    def test_live_identify_staff_block_uses_equipment_work_authority(self):
        """Replay the measured 3-pass block/300-pass owner through choose_key."""
        policy, snapshot = self._fixture()
        policy.choose_key(snapshot)
        policy._town_errand_plan = None
        policy._town_blocked_reason = None
        policy._town_store_attempted.clear()
        policy._store_visit = None
        home = replace(
            grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
        )
        snapshot = replace(snapshot, grids={**snapshot.grids, home.position: home})
        target = snapshot.inventory[0]
        identity = policy_module.equipment_identity(target)
        action = policy_module.EquipmentTransaction(
            policy_module.PHASE_HOME_PREPARE,
            "deposit",
            f"pack:{identity}:0",
            item_identity=identity,
        )
        session = policy_module.EquipmentTransactionSession(
            policy_module.EquipmentTransactionPlan((action,), (), 49)
        )
        policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = 3
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        policy._town_visit_ledger.blocked_store_limits[STORE_HOME] = (
            TOWN_STOP_PASS_LIMIT
        )
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=object(),
        )
        policy._set_equipment_transaction_session(session)

        key = policy.choose_key(snapshot)

        self.assertEqual(
            policy.last_reason,
            "equipment-transaction:approach-home",
            (policy._town_errand_plan, policy._town_store_attempted,
             policy._town_blocked_reason, policy._town_claim_categories),
        )
        self.assertNotEqual(key, WAIT_KEY)
        self.assertTrue(session.executable)
        self.assertEqual(policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 4)
        self.assertNotIn(
            policy.last_reason,
            {"equipment-transaction:home-route-unavailable",
             "equipment-transaction:abandon-blocked"},
        )

    def test_calibration_authority_block_still_denies_equipment_route(self):
        policy, _snapshot = self._fixture()
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("optimization-timeout",), result=None,
        )
        policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = (
            CALIBRATION_HOME_VISIT_LIMIT
        )
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        policy._town_visit_ledger.blocked_store_limits[STORE_HOME] = (
            CALIBRATION_HOME_VISIT_LIMIT
        )

        self.assertFalse(policy._equipment_work_home_route_available())

    @staticmethod
    def _record_exhausted_equipment_decision(policy, snap, reasons, i):
        candidate = replace(snap, turn=snap.turn + 1 + i)
        state = policy._town_observable_effect_state(candidate)
        for store_type in (
            STORE_GENERAL, STORE_ARMOURY, STORE_WEAPON, STORE_TEMPLE,
            STORE_ALCHEMIST, STORE_MAGIC, STORE_BLACK,
        ):
            policy._town_visit_ledger.nonhome_attempted_without_effect[
                store_type
            ] = state
        policy.choose_key(candidate)
        reasons[policy.last_reason] += 1

    def _exhausted_equipment_home_route_probe(self):
        """Run the reviewer's verbatim public 40-decision regression probe."""
        policy, snap = self._fixture()
        policy.choose_key(snap); policy._town_errand_plan = None
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("optimization-timeout",), result=None
        )
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            policy._town_store_visit_limit(STORE_HOME)
        )
        reasons = Counter()
        for i in range(40):
            self._record_exhausted_equipment_decision(policy, snap, reasons, i)
            if policy._town_blocked_reason is not None:
                break
        return policy, reasons

    def test_exhausted_equipment_home_route_emits_named_terminal_publicly(self):
        """Reviewer probe: 9cf2eb5 waited/probed forever in this exact shape."""
        policy, reasons = self._exhausted_equipment_home_route_probe()

        self.assertEqual(
            policy._town_blocked_reason,
            "equipment-work-home-route-exhausted",
            "9cf2eb5 exhausted 40 decisions without a named terminal: "
            f"Counter({dict(reasons)}); historical Counter({{'wait': 25, 'probe': 15}})",
        )
        self.assertEqual(
            policy.last_reason,
            "town:blocked:equipment-work-home-route-exhausted",
        )
        self.assertLessEqual(sum(reasons.values()), 40)

    def test_turn_2947508_scan_checkpoint_does_not_install_latch_under_ceiling(self):
        """Embed the captured scan-incomplete state before its bad T3 latch."""
        policy, snapshot = self._fixture()
        home = replace(
            grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
        )
        snapshot = replace(
            snapshot, turn=2947508,
            grids={**snapshot.grids, home.position: home},
        )
        policy._equipment_catalog.home_scan_complete = False
        policy._town_was_in_town = True
        policy._enumerate_town_needs = lambda _snapshot: [
            TownNeed(STORE_HOME, "equipment-catalog", "home-first")
        ]
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME],
            need_categories={STORE_HOME: ("equipment-catalog",)},
        )
        policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = 2
        policy._report_town_stop_pass(
            snapshot, STORE_HOME, goal_satisfied=False,
            operation_completed=True,
        )

        key = policy.choose_key(snapshot)

        self.assertNotEqual(
            policy.last_reason, "town:blocked:no-safe-recall-destination",
            "turn-2947508 checkpoint must not install the latch while "
            "scan-incomplete Home work remains under the ceiling",
        )
        self.assertNotEqual(key, WAIT_KEY)
        self.assertIsNone(policy._town_blocked_reason)
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 3,
            "the public decision must not consume the scan's third pass via "
            "a block-and-rearm cycle",
        )

    def test_captured_calibration_deposit_survives_exhausted_claim_budget(self):
        """Embed the onset checkpoint's decision-relevant town state."""
        policy, snapshot = self._fixture()
        home = replace(
            grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
        )
        snapshot = replace(
            snapshot,
            grids={**snapshot.grids, home.position: home},
            inventory=[replace(snapshot.inventory[0], count=19), *snapshot.inventory[1:]],
        )
        policy._town_was_in_town = True
        policy._calibration_phase = "deposit"
        policy._town_visit_ledger.need_attempts["deposit"] = 3

        key = policy.choose_key(snapshot)

        self.assertEqual(key, "4")
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(
            policy._town_claim_categories, ["deposit", "equipment-work"]
        )

    def test_live_calibration_deposit_rearms_exhausted_plan_publicly(self):
        """Pin turn 3030113: live bounded work must retain its Home route."""
        policy, snapshot = self._fixture()
        home = replace(
            grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
        )
        snapshot = replace(
            snapshot,
            turn=3030113,
            grids={**snapshot.grids, home.position: home},
        )
        policy.choose_key(snapshot)
        policy._town_was_in_town = True
        policy._calibration_phase = "deposit"
        policy._equipment_catalog.home_scan_complete = True
        policy._floor_key = snapshot.floor_key
        catalog_item = OwnedEquipment(
            "captured-item", snapshot.equipment[0], "home"
        )
        policy._equipment_catalog._home = {
            f"captured-item-{index}": replace(
                catalog_item, id=f"captured-item-{index}"
            )
            for index in range(51)
        }
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",), result=None,
        )
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_TEMPLE, STORE_WEAPON, STORE_BLACK],
            index=4,
            completed_this_visit=[STORE_HOME],
        )
        # Every value below is the retained 37e07f4 blocking decision's
        # home_route_rearm block; the downstream checkpoint additionally shows
        # Home completed this visit and absent from _town_store_attempted.

        self.assertEqual(len(policy._equipment_catalog.items), 52)
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertEqual(policy._calibration_phase, "deposit")
        self.assertIsNone(policy.calibration_entry_state(snapshot)["entry_blocker"])
        self.assertEqual(policy._town_errand_plan.index, 4)
        self.assertEqual(len(policy._town_errand_plan.stops), 4)
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(policy._town_visit_ledger.approach_fails[STORE_HOME], 0)
        self.assertEqual(policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 0)
        cure_requirement = next(
            requirement
            for requirement in policy.procurement_requirements(snapshot)
            if requirement["item"] == "Cure Critical Wounds potions"
        )
        self.assertEqual(
            cure_requirement,
            {
                "item": "Cure Critical Wounds potions",
                "current": 0,
                "target": 10,
                "missing": 10,
            },
        )
        key = policy.choose_key(snapshot)

        self.assertEqual(key, "4")
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertEqual(policy._calibration_phase, "deposit")
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._town_errand_plan.stops, [STORE_HOME])
        self.assertIn(
            "equipment-work",
            policy._town_errand_plan.need_categories[STORE_HOME],
        )
        self.assertEqual(
            policy.equipment_optimization_state(snapshot)["home_route_projection"][
                "projection"
            ],
            {
                "evaluated": True,
                "plan_rebuilt": True,
                "rebuilt_stops": [STORE_HOME],
            },
        )

    def test_live_calibration_deposit_builds_home_plan_from_none_publicly(self):
        """Pin the CL30 stop: a fresh plan retains live bounded Home work."""
        policy, snapshot = self._fixture()
        home = replace(
            grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
        )
        snapshot = replace(
            snapshot,
            turn=3032798,
            player=replace(snapshot.player, level=30, gold=28651),
            grids={**snapshot.grids, home.position: home},
        )
        policy.choose_key(snapshot)
        policy._town_was_in_town = True
        policy._calibration_phase = "deposit"
        policy._equipment_catalog.home_scan_complete = True
        policy._floor_key = snapshot.floor_key
        catalog_item = OwnedEquipment(
            "captured-item", snapshot.equipment[0], "home"
        )
        policy._equipment_catalog._home = {
            f"captured-item-{index}": replace(
                catalog_item, id=f"captured-item-{index}"
            )
            for index in range(55)
        }
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",), result=None,
        )
        policy._town_errand_plan = None
        policy._town_blocked_reason = "repetition"
        policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = 16

        self.assertEqual(len(policy._equipment_catalog.items), 56)
        self.assertIsNone(policy.calibration_entry_state(snapshot)["entry_blocker"])
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[STORE_HOME], 16
        )

        key = policy.choose_key(snapshot)

        self.assertEqual(
            key,
            "4",
            "afb1d3a repeats town until town:blocked:repetition because a "
            "fresh plan omits Home",
        )
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertEqual(policy._town_errand_plan.stops, [STORE_HOME])
        self.assertIn(
            "equipment-work",
            policy._town_errand_plan.need_categories[STORE_HOME],
        )

    def test_live_calibration_new_work_after_visited_home_routes_publicly(self):
        """A new live owner supersedes the projected pass that visited Home."""
        policy, snapshot = self._fixture()
        home = replace(
            grid(45, 122, lit=True, in_view=True), store_number=STORE_HOME
        )
        snapshot = replace(
            snapshot,
            turn=3032800,
            grids={**snapshot.grids, home.position: home},
        )
        policy.choose_key(snapshot)
        policy._town_was_in_town = True
        policy._calibration_phase = "deposit"
        policy._equipment_catalog.home_scan_complete = True
        policy._floor_key = snapshot.floor_key
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_BLACK],
            index=1,
            need_categories={STORE_HOME: ("equipment-catalog",)},
            completed_this_visit=[STORE_HOME],
        )
        policy._town_store_attempted[STORE_HOME] = snapshot.turn

        key = policy.choose_key(snapshot)

        self.assertEqual(key, "4")
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertIn(
            "equipment-work",
            policy._town_errand_plan.need_categories[STORE_HOME],
        )

    def test_home_route_rearm_telemetry_exposes_every_guard_input(self):
        policy, snapshot = self._fixture()
        policy._calibration_phase = "deposit"
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_TEMPLE, STORE_WEAPON, STORE_BLACK],
            index=4,
        )
        policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=("calibration-required",),
            result=None,
            encounters_total=0,
            encounters_evaluated=0,
            transaction=None,
        )

        state = policy.equipment_optimization_state(snapshot)

        self.assertEqual(
            state["home_route_projection"],
            {
                "home_owner_goal_pending": False,
                "equipment_work_need_present": False,
                "equipment_work_home_route_available": True,
                "outstanding_equipment_work": True,
                "town_plan_exhausted": True,
                "home_approach_fails": 0,
                "home_visit_limit": CALIBRATION_HOME_VISIT_LIMIT,
                "home_unsatisfied_passes": 0,
                "home_blocked": False,
                "projection": {
                    "evaluated": False,
                    "plan_rebuilt": False,
                    "rebuilt_stops": [],
                },
            },
        )

    def test_live_calibration_exhausted_ceiling_installs_named_terminal(self):
        policy, snapshot = self._fixture()
        policy._town_was_in_town = True
        policy._calibration_phase = "deposit"
        policy._town_errand_plan = TownErrandPlan([STORE_HOME], index=1)
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        policy._town_visit_ledger.unsatisfied_passes[STORE_HOME] = (
            CALIBRATION_HOME_VISIT_LIMIT
        )

        key = policy.choose_key(snapshot)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason,
            "town:blocked:equipment-work-home-route-exhausted",
        )

    def test_calibration_restore_claim_retires_at_physical_visit_budget(self):
        """CAL-3: an unrouteable restore claim cannot authorize town wandering."""
        policy, snapshot = self._fixture()
        policy._town_was_in_town = True
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [("restore", 1, 1)]
        policy._home_visit.attempts_used = CALIBRATION_HOME_VISIT_LIMIT - 1
        claim = TownNeed(STORE_HOME, "calibration-restore", "home-first")

        with patch.object(
            policy, "_enumerate_live_store_claims", return_value=[claim]
        ):
            self.assertTrue(policy._town_claims_active(snapshot))
            self.assertFalse(
                getattr(policy, "_town_liveness_claim_retired", False)
            )

            policy._home_visit.attempts_used = CALIBRATION_HOME_VISIT_LIMIT
            self.assertFalse(policy._town_claims_active(snapshot))
            self.assertTrue(policy._town_liveness_claim_retired)
        self.assertEqual(policy._calibration_phase, "restore-supplies")
        self.assertEqual(
            policy._calibration_restore_signatures, [("restore", 1, 1)]
        )

    def test_installing_checkpoint_oscillation_preserves_calibration_claim(self):
        """Turn 2942063: the oscillation branch must not install the latch."""
        policy, snapshot = self._fixture()
        home = replace(
            grid(45, 119, lit=True, in_view=True), store_number=STORE_HOME
        )
        snapshot = replace(
            snapshot,
            turn=2942063,
            grids={**snapshot.grids, home.position: home},
            inventory=[replace(snapshot.inventory[0], count=19), *snapshot.inventory[1:]],
        )
        policy._town_was_in_town = True
        policy._floor_key = snapshot.floor_key
        policy._calibration_phase = "deposit"
        policy._town_visit_ledger.need_attempts["deposit"] = 8
        policy._recent.extend(
            [Position(45, 123), Position(45, 122)] * (STUCK_WINDOW // 2)
        )
        policy._shop_approach_stuck_count = SHOP_APPROACH_STUCK_LIMIT - 1

        key = policy.choose_key(snapshot)

        self.assertNotEqual(key, WAIT_KEY)
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(
            policy._town_claim_categories, ["deposit", "equipment-work"]
        )
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._town_visit_ledger.approach_fails[STORE_HOME], 0)

    def test_live_home_door_block_replay_never_posts_stay_publicly(self):
        """Run the retained (45,123) state beyond its 104-decision window."""
        policy, snapshot = self._fixture()
        entrance = replace(
            snapshot.grids[snapshot.player.position], store_number=STORE_HOME
        )
        safe = grid(45, 122, lit=True, in_view=True)
        snapshot = replace(
            snapshot, grids={entrance.position: entrance, safe.position: safe}
        )
        policy._town_errand_plan = None
        for store_type in (
            STORE_GENERAL, STORE_ARMOURY, STORE_WEAPON, STORE_TEMPLE,
            STORE_ALCHEMIST, STORE_MAGIC, STORE_BLACK, STORE_HOME,
        ):
            policy._town_visit_ledger.approach_fails[store_type] = (
                policy_module.TOWN_STOP_PASS_LIMIT
            )

        decisions = []
        for offset in range(105):
            key = policy.choose_key(replace(snapshot, turn=snapshot.turn + offset))
            decisions.append((key, policy.last_reason))

        self.assertFalse(any(key == LEAVE_STORE_KEY for key, _ in decisions))
        self.assertIn(
            (WAIT_KEY, "home:atomic-deposit"), decisions
        )
        # E6 re-judgement: the arbiter exhausts the ineffective owner before
        # the legacy cycle detector needs to emit its marker.
        self.assertIn((WAIT_KEY, "town:blocked:owner-retired"), decisions)
        self.assertNotIn(
            (LEAVE_STORE_KEY, "home:atomic-withdraw-await-confirmation"),
            decisions,
        )

    def test_town_recall_wait_steps_off_building_entrance_publicly(self):
        policy, snapshot = self._fixture()
        current = replace(
            snapshot.grids[snapshot.player.position], building_special=1
        )
        safe = grid(45, 122, lit=True, in_view=True)
        snapshot = replace(
            snapshot,
            player=replace(snapshot.player, recalling=True),
            grids={current.position: current, safe.position: safe},
        )

        key = policy.choose_key(snapshot)

        self.assertEqual(key, "4")
        self.assertEqual(
            policy.last_reason, "town:entrance-step-off:town:wait-recall"
        )

    def test_wait_steps_off_quest_entrances_and_never_steps_onto_one(self):
        for quest_field in ("has_quest_enter", "has_quest_exit"):
            with self.subTest(direction="off", quest_field=quest_field):
                policy, snapshot = self._fixture()
                origin = snapshot.player.position
                current = replace(snapshot.grids[origin], **{quest_field: True})
                safe = grid(45, 122, lit=True, in_view=True)
                guarded = replace(
                    snapshot,
                    player=replace(snapshot.player, recalling=True),
                    grids={current.position: current, safe.position: safe},
                )

                self.assertEqual(policy.choose_key(guarded), "4")
                self.assertEqual(
                    policy.last_reason,
                    "town:entrance-step-off:town:wait-recall",
                )

            with self.subTest(direction="onto", quest_field=quest_field):
                policy, snapshot = self._fixture()
                origin = snapshot.player.position
                current = replace(snapshot.grids[origin], building_special=1)
                quest = replace(
                    grid(45, 122, lit=True, in_view=True), **{quest_field: True}
                )
                guarded = replace(
                    snapshot,
                    player=replace(snapshot.player, recalling=True),
                    grids={current.position: current, quest.position: quest},
                )

                self.assertEqual(policy.choose_key(guarded), WAIT_KEY)
                self.assertEqual(policy.last_reason, "livelock:exhausted")

    def test_entrance_guard_preserves_visible_terminal_and_blocked_fuse(self):
        from hengbot.cli import _advance_town_blocked_streak

        policy, snapshot = self._fixture()
        origin = snapshot.player.position
        entrance = replace(snapshot.grids[origin], store_number=STORE_HOME)
        safe = grid(45, 122, lit=True, in_view=True)
        guarded = replace(
            snapshot, grids={entrance.position: entrance, safe.position: safe}
        )

        def terminal(_snapshot):
            policy.last_reason = "livelock:exhausted"
            return WAIT_KEY

        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(policy, "_decide", side_effect=terminal):
            self.assertEqual(policy.choose_key(guarded), WAIT_KEY)
        self.assertEqual(policy.last_reason, "livelock:exhausted")

        def blocked(_snapshot):
            policy.last_reason = "town:blocked:no-safe-recall-destination"
            return WAIT_KEY

        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(policy, "_decide", side_effect=blocked):
            self.assertEqual(
                policy.choose_key(replace(guarded, turn=guarded.turn + 1)), "4"
            )
        self.assertEqual(
            policy.last_reason, "town:blocked:no-safe-recall-destination"
        )
        self.assertEqual(_advance_town_blocked_streak(7, policy.last_reason), 8)

    def test_remembered_store_position_covers_missing_current_grid(self):
        policy, snapshot = self._fixture()
        origin = snapshot.player.position
        entrance = replace(snapshot.grids[origin], store_number=STORE_HOME)
        safe = grid(45, 122, lit=True, in_view=True)
        disclosed = replace(
            snapshot, grids={entrance.position: entrance, safe.position: safe}
        )
        def attack(_snapshot):
            policy.last_reason = "melee"
            return "8"

        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(policy, "_decide", side_effect=attack):
            self.assertEqual(policy.choose_key(disclosed), "8")
        omitted = replace(
            disclosed,
            turn=disclosed.turn + 1,
            width=disclosed.width + 1,
            height=disclosed.height + 1,
            town_id=disclosed.town_id + 1,
            grids={safe.position: safe},
        )

        def wait_recall(_snapshot):
            policy.last_reason = "town:wait-recall"
            return WAIT_KEY

        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(policy, "_decide", side_effect=wait_recall):
            self.assertEqual(policy.choose_key(omitted), "4")
        self.assertEqual(
            policy.last_reason, "town:entrance-step-off:town:wait-recall"
        )

    def test_non_town_building_wait_is_also_guarded(self):
        policy, snapshot = self._fixture()
        origin = snapshot.player.position
        entrance = replace(snapshot.grids[origin], building_special=1)
        safe = grid(45, 122, lit=True, in_view=True)
        outside = replace(
            snapshot,
            town_flag=False,
            grids={entrance.position: entrance, safe.position: safe},
        )
        def wait(_snapshot):
            policy.last_reason = "wait"
            return WAIT_KEY

        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: wrapper behavior is the subject; the supplied downstream decision is not asserted as its own behavior
        with patch.object(policy, "_decide", side_effect=wait):
            self.assertEqual(policy.choose_key(outside), WAIT_KEY)
        self.assertEqual(policy.last_reason, "wait")

    def test_entrance_wait_never_uses_warning_hazard_or_unexplored_grid(self):
        policy, snapshot = self._fixture()
        origin = snapshot.player.position
        entrance = replace(snapshot.grids[origin], store_number=STORE_HOME)
        snapshot = replace(
            snapshot,
            grids={entrance.position: entrance},
        )
        policy._town_errand_plan = None
        for store_type in (
            STORE_GENERAL, STORE_ARMOURY, STORE_WEAPON, STORE_TEMPLE,
            STORE_ALCHEMIST, STORE_MAGIC, STORE_BLACK, STORE_HOME,
        ):
            policy._town_visit_ledger.approach_fails[store_type] = (
                policy_module.TOWN_STOP_PASS_LIMIT
            )

        policy = HengbotPolicy()
        warning = replace(grid(45, 122, lit=True, in_view=True), passable=False)
        policy._warning_refused_cells.add(warning.position)
        guarded = replace(
            snapshot,
            turn=snapshot.turn + 1,
            player=replace(snapshot.player, recalling=True),
            grids={entrance.position: entrance, warning.position: warning},
        )
        key = policy.choose_key(guarded)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "livelock:exhausted")
