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
from test_policy import step_toward_concatenation_offenders


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
from hengbot.dungeon_knowledge import DungeonInfo, load_dungeon_knowledge
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

class UnseenAttackerTest(unittest.TestCase):
    UNSEEN_ATTACK = "何かに殴られた。"
    CURSE_MESSAGES = (
        "Your Ring of Woe drains HP from you!",
        "The Jewel of Judgement drains life from you!",
        "Something drains life from you!",
        "苦痛の指輪はあなたの体力を吸収した！",
        "「審判の宝石」はあなたの体力を吸収した！",
        "なにかがあなたの体力を吸収した！",
    )

    def _open_grids(self, cy, cx, extra=None):
        grids = {}
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                grids[Position(cy + dy, cx + dx)] = grid(cy + dy, cx + dx)
        for pos, g in (extra or {}).items():
            grids[pos] = g
        return grids

    def _reverse_choke_grids(self):
        grids = {Position(10, x): grid(10, x) for x in range(8, 15)}
        for y in (9, 11):
            for x in range(12, 15):
                grids[Position(y, x)] = grid(y, x)
        grids[Position(10, 14)] = grid(10, 14, upstairs=True)
        return grids

    def _start_reverse_choke_wait(self, pol, grids, floor):
        pol.choose_key(
            Snapshot(
                player(10, 10, hp=227, max_hp=227),
                grids,
                [],
                turn=1,
                floor_key=floor,
            )
        )
        pol.choose_key(
            Snapshot(
                player(10, 11, hp=227, max_hp=227),
                grids,
                [],
                turn=2,
                floor_key=floor,
            )
        )
        key = pol.choose_key(
            Snapshot(
                player(10, 11, hp=213, max_hp=227),
                grids,
                [],
                messages=(self.UNSEEN_ATTACK,),
                turn=3,
                floor_key=floor,
            )
        )
        self.assertEqual((key, pol.last_reason), ("4", "unseen:reverse-choke"))
        wait = pol.choose_key(
            Snapshot(
                player(10, 10, hp=213, max_hp=227),
                grids,
                [],
                turn=4,
                floor_key=floor,
            )
        )
        self.assertEqual((wait, pol.last_reason), (WAIT_KEY, "unseen:choke-wait"))

    def test_does_not_rest_while_bleeding_from_unseen(self):
        # No visible hostiles but HP fell between decisions → an unseen attacker;
        # resting would be fatal, so we must move instead.
        grids = self._open_grids(10, 10)
        pol = HengbotPolicy()
        pol.choose_key(
            Snapshot(player(10, 10, hp=120, max_hp=200), grids, [], turn=1, floor_key=(1, 5, 0))
        )
        key = pol.choose_key(
            Snapshot(
                player(10, 10, hp=95, max_hp=200),
                grids,
                [],
                messages=(self.UNSEEN_ATTACK,),
                turn=2,
                floor_key=(1, 5, 0),
            )
        )
        self.assertNotEqual(key, REST_MACRO)
        self.assertTrue(pol.last_reason.startswith("unseen"), pol.last_reason)

    def test_unseen_hit_does_not_flee_to_upstairs(self):
        grids = {Position(10, x): grid(10, x) for x in range(10, 14)}
        grids[Position(10, 14)] = grid(10, 14, upstairs=True)
        pol = HengbotPolicy()
        pol.choose_key(
            Snapshot(player(10, 10, hp=120, max_hp=200), grids, [], turn=1, floor_key=(1, 5, 0))
        )
        key = pol.choose_key(
            Snapshot(
                player(10, 10, hp=95, max_hp=200),
                grids,
                [],
                messages=(self.UNSEEN_ATTACK,),
                turn=2,
                floor_key=(1, 5, 0),
            )
        )
        self.assertIn(key, set("12346789"))
        self.assertEqual(pol.last_reason, "unseen:reverse-choke")
        self.assertNotEqual(key, "<")

    def test_real_modest_unseen_hit_reverses_toward_choke_without_return(self):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)
        pol = HengbotPolicy()

        pol.choose_key(
            Snapshot(player(10, 10, hp=227, max_hp=227), grids, [], turn=1, floor_key=floor)
        )
        pol.choose_key(
            Snapshot(player(10, 11, hp=227, max_hp=227), grids, [], turn=2, floor_key=floor)
        )
        self.assertEqual(
            pol.choose_key(
                Snapshot(
                    player(10, 11, hp=213, max_hp=227),
                    grids,
                    [],
                    messages=(self.UNSEEN_ATTACK,),
                    turn=3,
                    floor_key=floor,
                )
            ),
            "4",
        )
        self.assertEqual(pol.last_reason, "unseen:reverse-choke")
        self.assertNotIn(pol.last_reason, {"unseen:ascend", "unseen:flee-stairs"})
        self.assertFalse(pol._returning_to_town)
        self.assertNotEqual(pol._last_return_trigger, "unseen-attacker")

    def test_reverse_choke_abandons_three_nonopening_doors_in_nine_decisions(self):
        grids = {
            Position(y, x): grid(y, x)
            for y in range(5, 10)
            for x in (18, 20)
        }
        for y in range(5, 10):
            grids[Position(y, 19)] = grid(y, 19, passable=False)
        for y in (6, 7, 8):
            grids[Position(y, 19)] = grid(y, 19, closed_door=True)
        floor = (0, 5, 34)
        snapshot = Snapshot(
            player(7, 18, hp=183, max_hp=195),
            grids,
            [],
            turn=78248,
            floor_key=floor,
            width=66,
            height=22,
        )
        pol = HengbotPolicy()
        pol.prime(snapshot)
        pol._unseen_retreat_floor = floor
        pol._unseen_retreat_direction = (-1, 1)
        pol._unseen_retreat_target = Position(5, 20)

        keys = [pol.choose_key(snapshot) for _ in range(10)]

        self.assertEqual(keys[:9], ["o9"] * 3 + ["o6"] * 3 + ["o3"] * 3)
        self.assertNotIn(keys[9], {"o9", "o6", "o3"})
        self.assertEqual(
            pol._blocked_doors,
            {(6, 19), (7, 19), (8, 19)},
        )

    def test_curse_damage_never_enters_unseen_retreat_or_emergency(self):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)

        for message in self.CURSE_MESSAGES:
            with self.subTest(message=message):
                pol = HengbotPolicy()
                pol.choose_key(
                    Snapshot(
                        player(10, 10, hp=227, max_hp=227),
                        grids,
                        [],
                        turn=1,
                        floor_key=floor,
                    )
                )
                pol.choose_key(
                    Snapshot(
                        player(10, 11, hp=227, max_hp=227),
                        grids,
                        [],
                        turn=2,
                        floor_key=floor,
                    )
                )
                key = pol.choose_key(
                    Snapshot(
                        player(10, 11, hp=100, max_hp=227),
                        grids,
                        [],
                        messages=(message,),
                        turn=3,
                        floor_key=floor,
                    )
                )

                self.assertFalse(pol.last_reason.startswith("unseen:"), pol.last_reason)
                self.assertIsNone(pol._unseen_retreat_floor)
                self.assertIsNone(pol._unseen_choke_position)
                self.assertEqual(pol._unseen_wait_remaining, 0)
                self.assertFalse(pol._emergency_escape_pending)
                self.assertFalse(pol._emergency_return_active)
                self.assertNotEqual(key, WAIT_KEY)

    def _assert_attributed_damage_does_not_trigger_unseen(
        self, message, *, initial_hp=160, damaged_hp=159
    ):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)
        pol = HengbotPolicy()
        pol.choose_key(
            Snapshot(
                player(10, 10, hp=initial_hp, max_hp=227),
                grids,
                [],
                turn=1,
                floor_key=floor,
            )
        )
        pol.choose_key(
            Snapshot(
                player(10, 11, hp=initial_hp, max_hp=227),
                grids,
                [],
                turn=2,
                floor_key=floor,
            )
        )

        key = pol.choose_key(
            Snapshot(
                player(10, 11, hp=damaged_hp, max_hp=227),
                grids,
                [],
                messages=(message,),
                turn=3,
                floor_key=floor,
            )
        )

        self.assertFalse(pol.last_reason.startswith("unseen:"), pol.last_reason)
        self.assertIsNone(pol._unseen_retreat_floor)
        self.assertIsNone(pol._unseen_choke_position)
        self.assertEqual(pol._unseen_wait_remaining, 0)
        self.assertFalse(pol._emergency_escape_pending)
        self.assertFalse(pol._emergency_return_active)
        self.assertNotEqual(key, WAIT_KEY)

    def test_live_chest_trap_damage_does_not_trigger_unseen(self):
        self._assert_attributed_damage_does_not_trigger_unseen(
            "トラップが作動してしまいました！"
        )

    def test_floor_trap_damage_does_not_trigger_unseen(self):
        self._assert_attributed_damage_does_not_trigger_unseen(
            "落とし穴を作動させてしまった！"
        )

    def test_damaging_terrain_does_not_trigger_unseen(self):
        self._assert_attributed_damage_does_not_trigger_unseen(
            "溶岩で火傷した！"
        )

    def test_captured_dart_trap_damage_does_not_arm_unseen_retreat(self):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)
        pol = HengbotPolicy()
        pol.choose_key(
            Snapshot(
                player(10, 10, hp=303, max_hp=303),
                grids,
                [],
                turn=455318,
                floor_key=floor,
            )
        )

        pol.choose_key(
            Snapshot(
                player(10, 10, hp=300, max_hp=303),
                grids,
                [],
                messages=(
                    "トラップだ！",
                    "小さなダーツが飛んできて刺さった！ <x2>",
                    "ひどく不器用になった気がする。",
                ),
                turn=455319,
                floor_key=floor,
            )
        )

        self.assertIsNone(pol._unseen_attack_evidence)
        self.assertIsNone(pol._unseen_retreat_floor)
        self.assertNotEqual(pol._escape_state.owner, "unseen")

    def test_japanese_and_english_unseen_attacks_arm_retreat(self):
        for message in (
            "何かに殴られた。",
            "何かに殴られた。 <x2>",
            "It hits you.",
            "It hits you. <x3>",
        ):
            with self.subTest(message=message):
                grids = self._reverse_choke_grids()
                floor = (1, 4, 0)
                pol = HengbotPolicy()
                pol.choose_key(
                    Snapshot(
                        player(10, 10, hp=303, max_hp=303),
                        grids,
                        [],
                        turn=1,
                        floor_key=floor,
                    )
                )
                pol.choose_key(
                    Snapshot(
                        player(10, 10, hp=300, max_hp=303),
                        grids,
                        [],
                        messages=(message,),
                        turn=2,
                        floor_key=floor,
                    )
                )

                self.assertEqual(pol._unseen_attack_evidence, message)
                self.assertEqual(pol._unseen_retreat_floor, floor)
                self.assertEqual(pol._escape_state.owner, "unseen")

    def test_nonattack_hidden_actor_messages_do_not_arm_retreat(self):
        for message in (
            "何かが足下に転がってきた。",
            "何かがピカッと光った！",
        ):
            with self.subTest(message=message):
                self._assert_attributed_damage_does_not_trigger_unseen(message)

    def test_armed_retreat_owns_movement_against_opposing_exploration(self):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)
        pol = HengbotPolicy()
        with patch.object(
            pol, "_explore_step", return_value=Position(10, 12)
        ):
            pol.choose_key(
                Snapshot(
                    player(10, 10, hp=303, max_hp=303),
                    grids,
                    [],
                    turn=1,
                    floor_key=floor,
                )
            )
            pol.choose_key(
                Snapshot(
                    player(10, 11, hp=303, max_hp=303),
                    grids,
                    [],
                    turn=2,
                    floor_key=floor,
                )
            )
            retreat = pol.choose_key(
                Snapshot(
                    player(10, 11, hp=300, max_hp=303),
                    grids,
                    [],
                    messages=(self.UNSEEN_ATTACK,),
                    turn=3,
                    floor_key=floor,
                )
            )
            hold = pol.choose_key(
                Snapshot(
                    player(10, 10, hp=300, max_hp=303),
                    grids,
                    [],
                    turn=4,
                    floor_key=floor,
                )
            )

        self.assertEqual(retreat, "4")
        self.assertEqual(hold, WAIT_KEY)
        self.assertEqual(pol.last_reason, "unseen:choke-wait")
        self.assertEqual(pol._escape_state.owner, "unseen")

    def test_snapshot_without_messages_keeps_real_unseen_retreat(self):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)
        pol = HengbotPolicy()
        pol.choose_key(
            Snapshot(
                player(10, 10, hp=227, max_hp=227),
                grids,
                [],
                turn=1,
                floor_key=floor,
            )
        )
        pol.choose_key(
            Snapshot(
                player(10, 11, hp=227, max_hp=227),
                grids,
                [],
                turn=2,
                floor_key=floor,
            )
        )

        key = pol.choose_key(
            Snapshot(
                player(10, 11, hp=213, max_hp=227),
                grids,
                [],
                messages=(self.UNSEEN_ATTACK,),
                turn=3,
                floor_key=floor,
            )
        )

        self.assertEqual((key, pol.last_reason), ("4", "unseen:reverse-choke"))

    def test_weak_breeder_hit_does_not_start_unseen_retreat_or_wait(self):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)
        breeder = hostile(
            1,
            10,
            13,
            distance=2,
            can_multiply=True,
            max_melee_damage=1,
        )
        grids[breeder.position] = replace(
            grids[breeder.position], has_monster=True
        )
        pol = HengbotPolicy()

        with patch.object(
            pol, "_explore_step", return_value=Position(10, 11)
        ):
            pol.choose_key(
                Snapshot(
                    player(10, 10, hp=227, max_hp=227),
                    grids,
                    [breeder],
                    turn=1,
                    floor_key=floor,
                )
            )
            key = pol.choose_key(
                Snapshot(
                    player(10, 11, hp=226, max_hp=227),
                    grids,
                    [breeder],
                    turn=2,
                    floor_key=floor,
                )
            )

        self.assertFalse(pol.last_reason.startswith("unseen:"), pol.last_reason)
        self.assertIsNone(pol._unseen_retreat_floor)
        self.assertIsNone(pol._unseen_choke_position)
        self.assertEqual(pol._unseen_wait_remaining, 0)
        self.assertNotEqual(key, WAIT_KEY)

    def test_reverse_choke_waits_sixty_decisions_then_resumes_floor(self):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)
        pol = HengbotPolicy()

        self._start_reverse_choke_wait(pol, grids, floor)
        for turn in range(5, 64):
            self.assertEqual(
                pol.choose_key(
                    Snapshot(
                        player(10, 10, hp=213, max_hp=227),
                        grids,
                        [],
                        turn=turn,
                        floor_key=floor,
                    )
                ),
                WAIT_KEY,
            )
            self.assertEqual(pol.last_reason, "unseen:choke-wait")
        resumed = pol.choose_key(
            Snapshot(
                player(10, 10, hp=213, max_hp=227),
                grids,
                [],
                turn=64,
                floor_key=floor,
            )
        )
        self.assertNotEqual(resumed, WAIT_KEY)
        self.assertFalse(pol._returning_to_town)
        self.assertFalse(pol.last_reason.startswith("unseen:"), pol.last_reason)

    def test_interception_fights_at_choke_then_restarts_sixty_wait(self):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)
        pol = HengbotPolicy()
        self._start_reverse_choke_wait(pol, grids, floor)

        attacker = hostile(1, 10, 11, hp=10, max_melee_damage=2)
        self.assertEqual(
            pol.choose_key(
                Snapshot(
                    player(10, 10, hp=213, max_hp=227),
                    grids,
                    [attacker],
                    turn=5,
                    floor_key=floor,
                )
            ),
            "6",
        )
        self.assertEqual(pol.last_reason, "melee:choke")
        for turn in range(6, 66):
            self.assertEqual(
                pol.choose_key(
                    Snapshot(
                        player(10, 10, hp=213, max_hp=227),
                        grids,
                        [],
                        turn=turn,
                        floor_key=floor,
                    )
                ),
                WAIT_KEY,
            )
            self.assertEqual(pol.last_reason, "unseen:choke-wait")
        self.assertNotEqual(
            pol.choose_key(
                Snapshot(
                    player(10, 10, hp=213, max_hp=227),
                    grids,
                    [],
                    turn=66,
                    floor_key=floor,
                )
            ),
            WAIT_KEY,
        )

    def test_no_return_preserves_retreat_wait_and_intercept(self):
        grids = self._reverse_choke_grids()
        floor = (1, 4, 0)
        pol = HengbotPolicy()

        self._start_reverse_choke_wait(pol, grids, floor)
        for turn in range(5, 63):
            self.assertEqual(
                pol.choose_key(
                    Snapshot(
                        player(10, 10, hp=213, max_hp=227),
                        grids,
                        [],
                        turn=turn,
                        floor_key=floor,
                    )
                ),
                WAIT_KEY,
            )
            self.assertEqual(pol.last_reason, "unseen:choke-wait")

        attacker = hostile(1, 10, 11, hp=10, max_melee_damage=2)
        self.assertEqual(
            pol.choose_key(
                Snapshot(
                    player(10, 10, hp=213, max_hp=227),
                    grids,
                    [attacker],
                    turn=63,
                    floor_key=floor,
                )
            ),
            "6",
        )
        self.assertEqual(pol.last_reason, "melee:choke")

    def test_lethal_unseen_hit_uses_existing_emergency_response(self):
        grids = self._open_grids(10, 10)
        floor = (1, 4, 0)
        pol = HengbotPolicy()
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)

        pol.choose_key(
            Snapshot(
                player(10, 10, hp=227, max_hp=227),
                grids,
                [],
                inventory=[teleport],
                turn=1,
                floor_key=floor,
            )
        )
        key = pol.choose_key(
            Snapshot(
                player(10, 10, hp=100, max_hp=227),
                grids,
                [],
                messages=(self.UNSEEN_ATTACK,),
                inventory=[teleport],
                turn=2,
                floor_key=floor,
            )
        )

        self.assertEqual(key, "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")
        self.assertTrue(pol._emergency_escape_pending)
        self.assertTrue(pol._emergency_return_active)
        self.assertEqual(pol._last_return_trigger, "emergency-lethal-swarm")

    def test_unseen_damage_during_recall_teleports_instead_of_waiting(self):
        grids = self._open_grids(10, 10)
        floor = (1, 15, 0)
        pol = HengbotPolicy()
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)

        pol.choose_key(
            Snapshot(
                player(10, 10, hp=200, max_hp=200, word_recall=5),
                grids,
                [],
                inventory=[teleport],
                turn=1,
                floor_key=floor,
            )
        )
        first_hit = pol.choose_key(
            Snapshot(
                player(10, 10, hp=185, max_hp=200, word_recall=4),
                grids,
                [],
                messages=(self.UNSEEN_ATTACK,),
                inventory=[teleport],
                turn=2,
                floor_key=floor,
            )
        )
        self.assertNotEqual(first_hit, "rt")
        self.assertEqual(pol.last_reason, "unseen-recall:move")
        key = pol.choose_key(
            Snapshot(
                player(10, 11, hp=170, max_hp=200, word_recall=3),
                grids,
                [],
                messages=(self.UNSEEN_ATTACK,),
                inventory=[teleport],
                turn=3,
                floor_key=floor,
            )
        )

        self.assertEqual(key, "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")

    def test_modest_first_unseen_hit_walks_instead_of_spending_teleport(self):
        grids = {Position(10, x): grid(10, x) for x in range(10, 15)}
        grids[Position(10, 14)] = grid(10, 14, upstairs=True)
        floor = (1, 15, 0)
        pol = HengbotPolicy()
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)

        pol.choose_key(
            Snapshot(
                player(10, 10, hp=200, max_hp=200),
                grids,
                [],
                inventory=[teleport],
                turn=1,
                floor_key=floor,
            )
        )
        key = pol.choose_key(
            Snapshot(
                player(10, 10, hp=170, max_hp=200),
                grids,
                [],
                messages=(self.UNSEEN_ATTACK,),
                inventory=[teleport],
                turn=2,
                floor_key=floor,
            )
        )

        self.assertIn(key, set("12346789"))
        self.assertEqual(pol.last_reason, "unseen:reverse-choke")

    def test_unseen_damage_during_recall_moves_when_no_escape_item(self):
        grids = {Position(10, x): grid(10, x) for x in range(10, 15)}
        grids[Position(10, 14)] = grid(10, 14, upstairs=True)
        floor = (1, 15, 0)
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
        key = pol.choose_key(
            Snapshot(
                player(10, 10, hp=170, max_hp=200, word_recall=4),
                grids,
                [],
                messages=(self.UNSEEN_ATTACK,),
                turn=2,
                floor_key=floor,
            )
        )

        self.assertEqual(key, "6")
        self.assertEqual(pol.last_reason, "unseen-recall:move")

    def test_still_rests_when_hp_not_dropping(self):
        # HP steady/rising with no hostiles is the normal heal-up case.
        grids = self._open_grids(10, 10)
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(Snapshot(player(10, 10, hp=60, max_hp=200), grids, [], turn=1)), REST_MACRO)
        # HP went up (rest is working) → keep resting.
        self.assertEqual(pol.choose_key(Snapshot(player(10, 10, hp=75, max_hp=200), grids, [], turn=2)), REST_MACRO)

class RubbleTest(unittest.TestCase):
    def test_tunnels_through_rubble_frontier(self):
        # A pile of rubble to the east caps the passage; it is the only frontier,
        # so the bot digs into it with raw 'T'+direction rather than
        # treating it as a wall (which would strand it).
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, rubble=True),
        }
        snap = Snapshot(player(10, 10), grids, [], width=40, height=40)
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "T6")

    def test_gives_up_on_immovable_rubble(self):
        # Boxed by walls with only the (never-clearing) rubble to the east; after
        # RUBBLE_DIG_LIMIT digs it is abandoned so the bot doesn't grind forever.
        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, rubble=True)}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dy, dx) == (0, 0) or (dy, dx) == (0, 1):
                    continue
                grids[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        snap = Snapshot(player(10, 10), grids, [], width=40, height=40)
        pol = HengbotPolicy()
        # Enough turns for the stuck-spot searches plus RUBBLE_DIG_LIMIT digs.
        keys = [pol.choose_key(snap) for _ in range(RUBBLE_DIG_LIMIT + 20)]
        self.assertIn("T6", keys)
        self.assertIn((10, 11), pol._blocked_rubble)

class SearchTest(unittest.TestCase):
    def test_sweeps_room_perimeter_for_a_hidden_exit(self):
        grids = {}
        for y in range(9, 14):
            for x in range(9, 14):
                border = y in {9, 13} or x in {9, 13}
                grids[Position(y, x)] = grid(y, x, passable=not border)
        grids[Position(11, 11)] = grid(11, 11, upstairs=True)
        snap = Snapshot(
            player(11, 11), grids, [], floor_key=(2, 4, 0), width=30, height=30
        )
        pol = HengbotPolicy()
        pol._floor_key = snap.floor_key
        pol._build_grid_index(snap)
        pol._visit_counts.update(
            {Position(y, x): 1 for y in range(10, 13) for x in range(10, 13)}
        )

        pol.choose_key(snap)

        self.assertEqual(pol.last_reason, "seek-secret-wall")

    def _sealed_dead_end(self, floor_key):
        grids = {Position(10, 10): grid(10, 10)}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dy, dx) != (0, 0):
                    grids[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        return Snapshot(player(10, 10), grids, [], floor_key=floor_key, width=40, height=40)

    def test_searches_a_sealed_dead_end(self):
        # Walled in with no reachable frontier IN A DUNGEON: the way on must be a
        # secret door, so once it recognises it is stuck the bot searches ('s').
        snap = self._sealed_dead_end((1, 5, 0))
        pol = HengbotPolicy()
        results = [(pol.choose_key(snap), pol.last_reason) for _ in range(14)]
        self.assertIn(("s", "search"), results)

    def test_return_searches_hidden_upstairs_even_with_known_downstairs(self):
        floor_key = (DUNGEON_ANGBAND, 14, 0)
        floors = {Position(10, 10), Position(10, 11), Position(10, 12)}
        grids = {position: grid(position.y, position.x) for position in floors}
        grids[Position(10, 10)] = grid(10, 10, downstairs=True)
        for position in floors:
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if neighbor not in grids:
                    grids[neighbor] = grid(
                        neighbor.y, neighbor.x, passable=False
                    )
        snapshot = Snapshot(
            player(10, 12), grids, [], floor_key=floor_key, width=40, height=40
        )
        policy = HengbotPolicy()
        policy._floor_key = floor_key
        policy._returning_to_town = True
        policy._build_grid_index(snapshot)
        policy._visit_counts.update({position: 1 for position in floors})

        self.assertEqual(policy._return_to_town_key(snapshot, []), "s")
        self.assertEqual(policy.last_reason, "return:search-upstairs")

    def test_disengage_search_upstairs_yields_after_the_tile_budget(self):
        snapshot = self._sealed_dead_end((DUNGEON_ANGBAND, 20, 0))
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._fruitless_disengage_floor = snapshot.floor_key
        ordinary_searches = 3
        policy._search_counts[(10, 10)] = ordinary_searches
        policy._build_grid_index(snapshot)

        with patch.object(
            policy, "_least_visited_neighbor", return_value=Position(10, 11)
        ):
            keys = [
                policy._fruitless_disengage_key(snapshot, [])
                for _ in range(SEARCH_LIMIT - ordinary_searches + 1)
            ]

        remaining_budget = SEARCH_LIMIT - ordinary_searches
        self.assertEqual(keys[:remaining_budget], ["s"] * remaining_budget)
        self.assertEqual(keys[remaining_budget], "6")
        self.assertEqual(policy.last_reason, "combat:disengage-wander")

    def test_disengage_search_upstairs_still_searches_within_budget(self):
        snapshot = self._sealed_dead_end((DUNGEON_ANGBAND, 20, 0))
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._fruitless_disengage_floor = snapshot.floor_key
        policy._build_grid_index(snapshot)

        self.assertEqual(policy._fruitless_disengage_key(snapshot, []), "s")
        self.assertEqual(policy.last_reason, "combat:disengage-search-upstairs")

    def test_return_wall_search_shares_the_ordinary_tile_budget(self):
        snapshot = self._sealed_dead_end((DUNGEON_ANGBAND, 20, 0))
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._returning_to_town = True
        policy._search_counts[(10, 10)] = SEARCH_LIMIT
        policy._build_grid_index(snapshot)

        with patch.object(
            policy, "_least_visited_neighbor", return_value=Position(10, 11)
        ):
            self.assertEqual(policy._return_to_town_key(snapshot, []), "6")

        self.assertEqual(policy.last_reason, "return:wander")
        self.assertEqual(policy._wall_search_counts.total(), 0)

    def test_secret_search_prefers_corridor_end_over_room_perimeter(self):
        floors = {
            Position(10, 10),
            Position(9, 10),
            Position(11, 10),
            Position(10, 9),
            Position(10, 11),
            Position(10, 12),
            Position(10, 13),
        }
        grids = {position: grid(position.y, position.x) for position in floors}
        for position in floors:
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if neighbor not in grids:
                    grids[neighbor] = grid(
                        neighbor.y, neighbor.x, passable=False
                    )
        snapshot = Snapshot(
            player(10, 10), grids, [], floor_key=(1, 14, 0), width=40, height=40
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._secret_wall_search_step(snapshot), Position(10, 11)
        )

    def test_never_searches_in_town(self):
        # Secret doors/passages do not exist in town, so 's' there is wasted
        # turns: the same sealed dead end on a town tile must NEVER search.
        snap = self._sealed_dead_end((0, 0, 0))  # (0,0) surface => town
        pol = HengbotPolicy()
        results = [(pol.choose_key(snap), pol.last_reason) for _ in range(14)]
        self.assertNotIn("search", [reason for _, reason in results])
        self.assertNotIn("s", [key for key, _ in results])

class DescendTest(unittest.TestCase):
    def test_moves_toward_downstairs(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "6")

    def test_clears_a_visible_monster_blocking_the_only_stair_route(self):
        # Live dl5 failure: west leads to the stairs, but a monster at x=34
        # blocks the one-cell corridor. Moving east hides it and makes the bot
        # turn west again, producing a permanent 4/6 visibility-edge loop.
        grids = {Position(24, x): grid(24, x) for x in range(30, 41)}
        grids[Position(25, 30)] = grid(25, 30, downstairs=True)
        grids[Position(24, 34)] = grid(24, 34, monster=True)
        grids[Position(24, 41)] = grid(24, 41, closed_door=True)
        for x in range(29, 43):
            grids[Position(23, x)] = grid(23, x, passable=False)
            if x != 30:
                grids[Position(25, x)] = grid(25, x, passable=False)
        grids[Position(24, 29)] = grid(24, 29, passable=False)
        grids[Position(24, 42)] = grid(24, 42, passable=False)

        monster = hostile(1, 24, 34, hp=24, max_hp=24, distance=3, speed=122)
        snap = Snapshot(
            player(24, 37, hp=99, max_hp=99), grids, [monster],
            floor_key=(1, 5, 0), width=80, height=200,
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "4")
        self.assertEqual(pol.last_reason, "clear-descent")

    def test_approaches_a_less_visited_frontier_near_unreachable_stairs(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(8, 13)
            for x in range(8, 16)
        }
        origin = Position(10, 10)
        near_frontier = Position(10, 11)
        fresh_frontier = Position(11, 10)
        grids[origin] = grid(origin.y, origin.x)
        grids[near_frontier] = grid(near_frontier.y, near_frontier.x)
        grids[fresh_frontier] = grid(fresh_frontier.y, fresh_frontier.x)
        grids[Position(10, 14)] = grid(10, 14, downstairs=True)
        del grids[Position(9, 12)]
        del grids[Position(12, 11)]

        policy = HengbotPolicy()
        policy._floor_key = (2, 12, 0)
        policy._visit_counts[near_frontier] = 3
        snapshot = Snapshot(
            player(origin.y, origin.x, food=12000),
            grids,
            [],
            floor_key=(2, 12, 0),
            width=30,
            height=30,
        )
        self.assertEqual(policy.choose_key(snapshot), "2")
        self.assertEqual(policy.last_reason, "approach-descent")

    def test_unreachable_stair_cycle_keeps_one_committed_target(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(7, 13)
            for x in range(7, 14)
        }
        origin = Position(10, 10)
        cycle = {
            origin,
            Position(10, 11),
            Position(11, 11),
            Position(11, 12),
        }
        escape = Position(10, 9)
        for position in cycle | {escape, Position(10, 8)}:
            grids[position] = grid(position.y, position.x)
        grids[Position(8, 12)] = grid(8, 12, downstairs=True)
        del grids[Position(10, 7)]  # reachable frontier for the committed approach

        policy = HengbotPolicy()
        policy._floor_key = (2, 12, 0)
        policy._recent.extend(list(cycle) * 3)
        for position in cycle:
            policy._visit_counts[position] = 5
        policy._search_counts[(origin.y, origin.x)] = SEARCH_LIMIT
        snapshot = Snapshot(
            player(origin.y, origin.x, food=12000),
            grids,
            [],
            floor_key=(2, 12, 0),
            width=30,
            height=30,
        )
        key = policy.choose_key(snapshot)
        self.assertIn(key, set("12346789"))
        self.assertEqual(policy._nav_ledger.descent_target, Position(8, 12))
        self.assertNotEqual(policy.last_reason, "breakout:descent")

    def test_releases_unreachable_committed_stair_for_reachable_alternative(self):
        origin = Position(10, 10)
        unreachable = Position(8, 10)
        alternative = Position(10, 13)
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(6, 12)
            for x in range(8, 15)
        }
        grids[origin] = grid(10, 10)
        grids[Position(10, 11)] = grid(10, 11)
        grids[Position(10, 12)] = grid(10, 12)
        grids[alternative] = grid(10, 13, downstairs=True)
        grids[unreachable] = grid(8, 10, downstairs=True)
        snapshot = Snapshot(
            player(10, 10), grids, [], floor_key=(2, 12, 0), width=30, height=30
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        policy._nav_ledger.commit_descent_route(unreachable, ())

        self.assertIsNone(policy._descent_step(snapshot))
        self.assertIsNone(policy._nav_ledger.descent_target)
        self.assertEqual(policy._descent_step(snapshot), Position(10, 11))
        self.assertEqual(policy._nav_ledger.descent_target, alternative)

    def test_committed_frontier_path_keeps_approach_reason(self):
        origin = Position(10, 10)
        step = Position(10, 11)
        frontier = Position(10, 12)
        target = Position(8, 12)
        grids = {
            origin: grid(10, 10),
            step: grid(10, 11),
            frontier: grid(10, 12),
            target: grid(8, 12, downstairs=True),
        }
        snapshot = Snapshot(
            player(10, 10), grids, [], floor_key=(2, 12, 0), width=30, height=30
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_ledger.commit_descent_route(target, (step, frontier))

        self.assertEqual(policy._descent_step(snapshot), step)
        self.assertEqual(policy.last_reason, "approach-descent")

    def test_descends_when_standing_on_downstairs_and_healthy(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(player(10, 10, hp=20, max_hp=20), grids, [])
        self.assertEqual(HengbotPolicy().choose_key(snap), ">")

    def test_descends_when_standing_on_expired_downstairs(self):
        position = Position(10, 10)
        grids = {position: grid(10, 10, downstairs=True)}
        snap = Snapshot(
            player(10, 10, hp=20, max_hp=20),
            grids,
            [],
            floor_key=(1, 8, 0),
        )
        policy = HengbotPolicy()
        policy._floor_key = snap.floor_key
        policy._nav_ledger.expire("descend", position)

        self.assertEqual(policy.choose_key(snap), ">")
        self.assertEqual(policy.last_reason, "descend")

    def test_rests_before_descending_when_hurt_then_descends(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        policy = HengbotPolicy()
        # A dungeon floor (not the town recover path).
        hurt = Snapshot(player(10, 10, hp=10, max_hp=100), grids, [], turn=1, floor_key=(1, 5, 0))
        self.assertEqual(policy.choose_key(hurt), REST_MACRO)  # heal up first
        healed = Snapshot(player(10, 10, hp=90, max_hp=100), grids, [], turn=2, floor_key=(1, 5, 0))
        self.assertEqual(policy.choose_key(healed), ">")

    def test_confirms_entry_on_a_dungeon_entrance(self):
        # A town/wilderness dungeon entrance first msg_print()s an entrance line
        # (a -more- prompt) then a [y/n] confirmation, so descent is the macro
        # ">\ry" (Return dismisses the -more-, y confirms), not a bare ">".
        grids = {Position(10, 10): grid(
            10, 10, entrance=True, entrance_dungeon_id=DUNGEON_YEEK_CAVE,
        )}
        policy = HengbotPolicy()
        # TEST_FAKERY_LINT_ALLOW: subject-precompleted: test seeds an independently established loadout prerequisite before exercising a later gate
        set_completed_equipment_optimization(policy)
        snapshot = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=3)
            ],
        )
        self.assertTrue(policy._equipment_departure_ready(snapshot))
        self.assertEqual(
            policy.choose_key(snapshot), ">\ry"
        )

    def test_bare_downstairs_needs_no_confirmation(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), ">")

    def test_seeks_a_dungeon_entrance(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(
                10, 12, entrance=True,
                entrance_dungeon_id=DUNGEON_YEEK_CAVE,
            ),
        }
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "6")

    def test_does_not_dive_deeper_to_flee(self):
        # Desperate on a pure downstairs with a monster near: must NOT press ">"
        # (diving to escape leads somewhere worse and can ping-pong forever).
        grids = {
            Position(10, 10): grid(10, 10, downstairs=True),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=5, max_hp=100), grids, [hostile(1, 10, 11, hp=20)])
        self.assertNotEqual(HengbotPolicy().choose_key(snap), ">")

    def test_does_not_immediately_return_after_fleeing_upstairs(self):
        policy = HengbotPolicy()
        safe_grids = {
            Position(13, 54): grid(13, 54, downstairs=True),
            Position(13, 53): grid(13, 53),
        }
        danger_grids = {
            Position(7, 16): grid(7, 16, upstairs=True),
            Position(6, 16): grid(6, 16, monster=True),
            Position(7, 17): grid(7, 17, monster=True),
            Position(8, 16): grid(8, 16, monster=True),
        }
        danger_monsters = [
            hostile(1, 6, 16, max_melee_damage=20),
            hostile(2, 7, 17, max_melee_damage=20),
            hostile(3, 8, 16, max_melee_damage=20),
        ]

        floor_nine = Snapshot(
            player(13, 54, hp=241, max_hp=241),
            safe_grids,
            [],
            turn=100,
            floor_key=(2, 9, 0),
        )
        floor_ten = Snapshot(
            player(7, 16, hp=241, max_hp=241),
            danger_grids,
            danger_monsters,
            turn=101,
            floor_key=(2, 10, 0),
        )
        returned = Snapshot(
            player(13, 54, hp=241, max_hp=241),
            safe_grids,
            [],
            turn=102,
            floor_key=(2, 9, 0),
        )

        self.assertEqual(policy.choose_key(floor_nine), ">")
        self.assertEqual(policy.choose_key(floor_ten), "<")
        self.assertNotEqual(policy.choose_key(returned), ">")

    def test_level_gain_does_not_release_descent_cooldown(self):
        policy = HengbotPolicy()
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        policy._descent_blocked = True
        policy._descent_block_countdown = 2
        snapshot = Snapshot(
            player(10, 10, level=11), grids, [], turn=300, floor_key=(2, 9, 0)
        )
        self.assertNotEqual(policy.choose_key(snapshot), ">")

        policy._descent_block_countdown = 0
        self.assertEqual(policy.choose_key(snapshot), ">")

    def test_prime_remembers_a_dangerous_landing_for_the_follow_process(self):
        policy = HengbotPolicy()
        danger_grids = {
            Position(7, 16): grid(7, 16, upstairs=True),
            Position(6, 16): grid(6, 16, monster=True),
            Position(7, 17): grid(7, 17, monster=True),
            Position(8, 16): grid(8, 16, monster=True),
        }
        initial = Snapshot(
            player(7, 16, hp=241, max_hp=241),
            danger_grids,
            [
                hostile(1, 6, 16, max_melee_damage=20),
                hostile(2, 7, 17, max_melee_damage=20),
                hostile(3, 8, 16, max_melee_damage=20),
            ],
            turn=100,
            floor_key=(2, 10, 0),
        )
        policy.prime(initial)

        safe_grids = {
            Position(13, 54): grid(13, 54, downstairs=True),
            Position(13, 53): grid(13, 53),
        }
        returned = Snapshot(
            player(13, 54, hp=241, max_hp=241),
            safe_grids,
            [],
            turn=101,
            floor_key=(2, 9, 0),
        )
        self.assertNotEqual(policy.choose_key(returned), ">")

    def test_does_not_rest_when_a_monster_is_in_sight(self):
        grids = {
            Position(10, 10): grid(10, 10, downstairs=True),
            Position(10, 12): grid(10, 12, monster=True),
        }
        snap = Snapshot(player(10, 10, hp=40, max_hp=100), grids, [hostile(1, 10, 12, distance=2)])
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

class ExplorationTest(unittest.TestCase):
    def test_steps_onto_lit_but_unvisited_floor_before_finishing_exploration(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(9, 14)
        }
        grids[Position(10, 10)] = grid(10, 10)
        grids[Position(10, 11)] = grid(10, 11)
        grids[Position(10, 12)] = grid(10, 12)
        snap = Snapshot(
            player(10, 10), grids, [], floor_key=(2, 4, 0), width=30, height=30
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "s")
        for _ in range(SEARCH_LIMIT - 1):
            self.assertEqual(policy.choose_key(snap), "s")
        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "explore")

    def test_moves_toward_in_radius_unknown(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, known=False),
        }
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "6")

    def test_explores_toward_radius_edge_instead_of_waiting(self):
        # Only the immediate row is known; tiles beyond are absent (past the view
        # radius). The old policy waited here forever; the new one walks outward.
        grids = {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        key = HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, []))
        self.assertIn(key, {"4", "6"})
        self.assertNotEqual(key, "5")

    def test_opens_a_closed_door_in_the_way(self):
        # The room's only exit east is a closed door; the bot must OPEN it
        # ("o" + direction), not just walk into it (which may not open it).
        walls = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                walls[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        walls[Position(10, 10)] = grid(10, 10)
        walls[Position(10, 11)] = grid(10, 11, closed_door=True)
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), walls, [])), "o6")

    def test_gives_up_on_a_door_that_will_not_open(self):
        # A closed door that never opens (jammed / hard lock) is abandoned after
        # DOOR_OPEN_LIMIT tries so the bot doesn't loop on it forever.
        walls = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                walls[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        walls[Position(10, 10)] = grid(10, 10)
        walls[Position(10, 11)] = grid(10, 11, closed_door=True)
        snap = Snapshot(player(10, 10), walls, [], floor_key=(1, 5, 0), width=20, height=20)
        policy = HengbotPolicy()
        keys = [policy.choose_key(snap) for _ in range(DOOR_OPEN_LIMIT + 20)]
        self.assertEqual(keys[:SEARCH_LIMIT], ["s"] * SEARCH_LIMIT)
        self.assertIn("o6", keys[SEARCH_LIMIT:])
        self.assertIn("s", keys)  # boxed in with a jammed door → searches for a secret way
        self.assertIn((10, 11), policy._blocked_doors)  # eventually abandons the door

    def test_opens_a_diagonal_closed_door(self):
        # Door interaction has no diagonal restriction.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),  # west floor
            Position(9, 9): grid(9, 9, closed_door=True),  # door NW, N of the west tile
        }
        for pos in [Position(9, 10), Position(9, 11), Position(10, 11), Position(11, 9), Position(11, 10), Position(11, 11)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        key = HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, []))
        self.assertEqual(key, "o7")

    def test_moves_diagonally_into_an_open_door(self):
        # An open door is ordinary passable terrain for pathfinding.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(9, 10): grid(9, 10, passable=False),
            Position(9, 11): grid(9, 11, open_door=True),  # open door NE
        }
        for pos in [Position(9, 9), Position(10, 9), Position(10, 11), Position(11, 9), Position(11, 10), Position(11, 11)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        key = HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, []))
        self.assertEqual(key, "9")

    def test_breaks_out_of_a_rejected_move_livelock(self):
        # Two floor exits border the unknown. If the chosen move never changes
        # the player's position (as a rejected move would), the livelock guard
        # eventually forces the other direction instead of repeating forever.
        grids = {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        policy = HengbotPolicy()
        snap = Snapshot(player(10, 10), grids, [])
        keys = [policy.choose_key(snap) for _ in range(5)]
        # First choices are the same explore move; the last is a forced breakout
        # to the opposite direction.
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(keys[-1], "6" if keys[0] == "4" else "4")
        self.assertEqual(policy.last_reason, "breakout")

    def test_explores_open_area_without_oscillating(self):
        # A one-row corridor (walls above/below) with unknown at both far ends.
        # Committing to a frontier means the bot sweeps toward one end instead of
        # ping-ponging between two adjacent tiles.
        from hengbot.policy import DIRECTION_KEYS

        grids = {}
        for x in range(6, 18):
            grids[Position(10, x)] = grid(10, x)
            grids[Position(9, x)] = grid(9, x, passable=False)
            grids[Position(11, x)] = grid(11, x, passable=False)
        grids[Position(10, 5)] = grid(10, 5, known=False)
        grids[Position(10, 18)] = grid(10, 18, known=False)
        inv = {v: k for k, v in DIRECTION_KEYS.items()}

        policy = HengbotPolicy()
        pos = Position(10, 11)
        columns = []
        for turn in range(6):
            key = policy.choose_key(Snapshot(player(pos.y, pos.x), grids, [], turn=turn))
            self.assertIn(key, inv, f"expected a move at step {turn}, got {key!r}")
            dy, dx = inv[key]
            pos = Position(pos.y + dy, pos.x + dx)
            columns.append(pos.x)
        self.assertGreaterEqual(len(set(columns)), 4)  # swept, not oscillating

    def test_map_edge_void_is_not_a_frontier(self):
        # A sealed 2x2 pocket in the top-left map corner: every non-known
        # neighbour is either a wall or past the map edge (void). With bounds
        # known, none of that counts as unexplored, so the bot must not keep
        # "exploring" the perimeter.
        grids = {}
        for y in range(0, 2):
            for x in range(0, 2):
                grids[Position(y, x)] = grid(y, x)
        for pos in [Position(0, 2), Position(1, 2), Position(2, 0), Position(2, 1), Position(2, 2)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        snap = Snapshot(player(0, 0), grids, [], width=10, height=10)
        policy = HengbotPolicy()
        policy._floor_key = snap.floor_key
        policy._visit_counts.update(
            {pos: 1 for pos, state in grids.items() if state.passable}
        )
        policy.choose_key(snap)
        self.assertNotEqual(policy.last_reason, "explore")

    def test_boxed_in_with_no_options_waits(self):
        grids = {Position(10, 10): grid(10, 10)}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                grids[Position(10 + dy, 10 + dx)] = grid(10 + dy, 10 + dx, passable=False)
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "5")


class TrapSealedFloorRegressionTest(unittest.TestCase):
    def test_live_labyrinth_floor_crosses_trap_after_safe_coverage_is_exhausted(self):
        state_path = (
            Path(__file__).with_name("fixtures")
            / "trap-sealed-floor-dungeon4-level16.jsonl.gz"
        )
        knowledge = load_monrace_knowledge(
            Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc")
        )
        dungeon_knowledge = load_dungeon_knowledge(
            Path("C:/hengband/lib/edit/DungeonDefinitions.jsonc")
        )

        with TemporaryDirectory() as scratch:
            policy = HengbotPolicy(
                dungeon_knowledge=dungeon_knowledge,
                monrace_knowledge=knowledge,
                exploration_ledger_path=Path(scratch) / "exploration-ledger.json",
            )
            snapshot_count = 0
            observed_traps = set()
            final_snapshot = None
            with gzip.open(state_path, mode="rt", encoding="utf-8") as stream:
                for line in stream:
                    data = json.loads(line)
                    floor = data.get("floor", {})
                    if (
                        floor.get("dungeon_id") != 4
                        or floor.get("level") != 16
                    ):
                        continue
                    snapshot = parse_snapshot(data, knowledge)
                    policy.prime(snapshot)
                    snapshot_count += 1
                    observed_traps.update(
                        (state.position.y, state.position.x)
                        for state in snapshot.grids.values()
                        if state.trap
                    )
                    final_snapshot = snapshot

            self.assertIsNotNone(final_snapshot)
            assert final_snapshot is not None
            merged = policy._with_grid_memory(final_snapshot)
            policy._build_grid_index(merged)

            self.assertEqual(snapshot_count, 1888)
            self.assertEqual(len(policy._remembered_known_t), 697)
            self.assertEqual(len(policy._floor_t), 301)
            self.assertEqual(len(policy._remembered_wall_t), 396)
            self.assertEqual(policy._remembered_downstairs, set())
            self.assertEqual(final_snapshot.player.position, Position(8, 14))
            self.assertEqual(
                observed_traps,
                {(7, 10), (8, 10), (8, 12), (11, 54)},
            )

            safe_path = policy._plan_explore_path_pass(
                merged, allow_damaging=False
            )
            self.assertEqual(safe_path, [Position(8, 13)])
            self.assertGreater(policy._visit_counts[safe_path[-1]], 0)

            breakout_path = policy._plan_explore_path(merged)
            self.assertEqual(breakout_path[0], Position(8, 13))
            self.assertIn(Position(8, 12), breakout_path)
            self.assertEqual(policy._visit_counts[breakout_path[-1]], 0)

            self.assertEqual(policy.choose_key(final_snapshot), "4")
            self.assertEqual(policy.last_reason, "breakout:seek-frontier")
            beside_trap = replace(
                final_snapshot,
                player=replace(
                    final_snapshot.player, position=Position(8, 13)
                ),
                turn=final_snapshot.turn + 1,
            )
            self.assertEqual(policy.choose_key(beside_trap), "D4")
            self.assertEqual(policy.last_reason, "explore")
            self.assertEqual(policy._floor_trap_disarm_attempts[(8, 12)], 1)

    def test_longer_safe_route_to_new_coverage_wins_over_short_trap_route(self):
        grids = {
            Position(10, x): grid(10, x, trap=(x == 11))
            for x in range(7, 13)
        }
        for y in (9, 11):
            for x in range(6, 14):
                grids[Position(y, x)] = grid(y, x, passable=False)
        grids[Position(10, 6)] = grid(10, 6, passable=False)
        grids[Position(10, 13)] = grid(10, 13, passable=False)

        policy = HengbotPolicy()
        for x in (8, 9, 10):
            policy.prime(
                Snapshot(
                    player(10, x),
                    grids,
                    [],
                    turn=x,
                    floor_key=(1, 5, 0),
                    width=20,
                    height=20,
                )
            )
        current = Snapshot(
            player(10, 10),
            grids,
            [],
            turn=20,
            floor_key=(1, 5, 0),
            width=20,
            height=20,
        )

        merged = policy._with_grid_memory(current)
        policy._build_grid_index(merged)
        safe_path = policy._plan_explore_path_pass(
            merged,
            allow_damaging=False,
            new_information_only=True,
        )
        short_trap_path = policy._plan_explore_path_pass(
            merged,
            allow_damaging=True,
            new_information_only=True,
        )
        self.assertGreater(len(safe_path), len(short_trap_path))
        self.assertNotIn(Position(10, 11), safe_path)
        self.assertIn(Position(10, 11), short_trap_path)
        self.assertEqual(policy.choose_key(current), "4")
        self.assertEqual(policy.last_reason, "explore")
        self.assertEqual(policy._floor_trap_disarm_attempts, Counter())


class AntiStuckTest(unittest.TestCase):
    def test_seeks_known_stairs_when_fully_explored(self):
        # A fully-known dead-end corridor (no frontier) with an upstairs known:
        # rather than freezing, head for the stairs to reach a fresh floor.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, upstairs=True),
        }
        # Wall off every other neighbour so there is no radius-edge frontier.
        for pos in [
            Position(9, 9), Position(9, 10), Position(9, 11), Position(9, 12), Position(9, 13),
            Position(11, 9), Position(11, 10), Position(11, 11), Position(11, 12), Position(11, 13),
            Position(10, 9), Position(10, 13),
        ]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        self.assertEqual(HengbotPolicy().choose_key(Snapshot(player(10, 10), grids, [])), "6")

class ProbeTest(unittest.TestCase):
    def _sole_frontier_snapshot(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(10, 14)
        }
        grids[Position(10, 10)] = grid(10, 10)
        grids[Position(10, 11)] = grid(10, 11)
        grids[Position(10, 12)] = grid(10, 12, upstairs=True)
        return Snapshot(
            player(10, 10), grids, [], width=30, height=30, floor_key=(2, 4, 0)
        )

    def test_searches_when_standing_at_dead_end_before_probing_frontier(self):
        policy = HengbotPolicy()
        snap = self._sole_frontier_snapshot()
        policy._floor_key = snap.floor_key
        policy._visit_counts.update(
            {Position(10, x): 1 for x in range(10, 13)}
        )

        self.assertEqual(policy.choose_key(snap), "s")
        self.assertEqual(policy.last_reason, "search")

    def test_searches_last_frontier_after_unknown_edge_rejects_probes(self):
        policy = HengbotPolicy()
        snap = self._sole_frontier_snapshot()
        policy._floor_key = snap.floor_key
        policy._visit_counts.update(
            {Position(10, x): 1 for x in range(10, 13)}
        )
        policy._blocked_unknown.update({(9, 9), (10, 9), (11, 9)})

        self.assertEqual(policy.choose_key(snap), "s")
        self.assertEqual(policy.last_reason, "search")

    def _corridor_snapshot(self, *, branch=False, town=False):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(9, 14)
        }
        grids[Position(10, 10)] = grid(10, 10)
        grids[Position(10, 11)] = grid(10, 11)
        grids[Position(10, 12)] = grid(10, 12, downstairs=not town)
        if branch:
            grids[Position(9, 10)] = grid(9, 10)
        return Snapshot(
            player(10, 10),
            grids,
            [],
            width=30,
            height=30,
            floor_key=(0, 0, 0) if town else (2, 4, 0),
        )

    def test_searches_corridor_dead_end_with_downstairs_known(self):
        policy = HengbotPolicy()
        snap = self._corridor_snapshot()

        with (
            patch.object(policy, "_descent_step", return_value=None),
            patch.object(policy, "_explore_step", return_value=Position(10, 11)),
        ):
            self.assertEqual(policy.choose_key(snap), "s")

        self.assertEqual(policy.last_reason, "search")

    def test_corridor_dead_end_search_is_self_bounded(self):
        policy = HengbotPolicy()
        snap = self._corridor_snapshot()
        policy._floor_key = snap.floor_key
        policy._build_grid_index(snap)
        policy._wall_search_counts.update(
            {wall: SEARCH_LIMIT for wall in policy._remembered_wall_t}
        )

        with (
            patch.object(policy, "_descent_step", return_value=None),
            patch.object(policy, "_explore_step", return_value=Position(10, 11)),
        ):
            self.assertEqual(policy.choose_key(snap), "6")

        self.assertEqual(policy.last_reason, "explore")

    def test_does_not_search_outside_corridor_dead_end(self):
        policy = HengbotPolicy()
        snap = self._corridor_snapshot(branch=True)

        with (
            patch.object(policy, "_descent_step", return_value=None),
            patch.object(policy, "_explore_step", return_value=Position(10, 11)),
        ):
            self.assertEqual(policy.choose_key(snap), "6")

        self.assertEqual(policy.last_reason, "explore")

    def test_does_not_search_corridor_dead_end_in_town(self):
        policy = HengbotPolicy()
        snap = self._corridor_snapshot(town=True)

        with patch.object(
            policy, "_explore_step", return_value=Position(10, 11)
        ):
            self.assertEqual(policy.choose_key(snap), "6")

        self.assertEqual(policy.last_reason, "explore")

    def test_probe_step_targets_orthogonal_unknown(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9, passable=False),
            Position(9, 10): grid(9, 10, passable=False),
            Position(11, 10): grid(11, 10, passable=False),
        }
        # (10,11) is absent (unknown) and in bounds → the probe target.
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        policy._build_grid_index(snap)
        self.assertEqual(policy._probe_unknown_step(snap), Position(10, 11))

    def test_probe_step_prefers_down_over_left_on_tie(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(9, 10): grid(9, 10, passable=False),
            Position(10, 11): grid(10, 11, passable=False),
        }
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        self.assertEqual(policy._probe_unknown_step(snap), Position(11, 10))

    def test_probes_into_unknown_when_oscillating(self):
        # Boxed on three sides; the fourth (east) is an unexplored tile absent
        # from the snapshot. The pathfinder can't reach it, so once the bot is
        # seen to be circling, it probes east into the unknown to reveal it.
        grids = {Position(10, 10): grid(10, 10)}
        for pos in [Position(9, 9), Position(9, 10), Position(9, 11), Position(10, 9),
                    Position(11, 9), Position(11, 10), Position(11, 11)]:
            grids[pos] = grid(pos.y, pos.x, passable=False)
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        # Needs at least STUCK_WINDOW decisions before the oscillation is detected.
        results = [(policy.choose_key(snap), policy.last_reason) for _ in range(14)]
        probes = [key for key, reason in results if reason == "probe"]
        self.assertTrue(probes, f"expected a probe once oscillating; got {results}")
        self.assertEqual(probes[0], "6")

    def test_probes_diagonal_only_unknown_neighbor(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(9, 12)
            if (y, x) != (9, 11)
        }
        grids[Position(10, 10)] = grid(10, 10)
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)

        direct_policy = HengbotPolicy()
        direct_policy._build_grid_index(snap)
        self.assertEqual(
            direct_policy._probe_unknown_step(snap), Position(9, 11)
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "9")
        self.assertEqual(policy.last_reason, "probe")

    def test_probe_prefers_orthogonal_unknown_over_diagonal(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(9, 12)
            if (y, x) not in {(9, 11), (10, 11)}
        }
        grids[Position(10, 10)] = grid(10, 10)
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        self.assertEqual(policy._probe_unknown_step(snap), Position(10, 11))

    def test_blocked_diagonal_unknown_stops_being_frontier(self):
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(9, 12)
            if (y, x) != (9, 11)
        }
        origin = Position(10, 10)
        target = Position(9, 11)
        grids[origin] = grid(10, 10)
        snap = Snapshot(player(10, 10), grids, [], width=20, height=20)
        policy = HengbotPolicy()
        policy._build_grid_index(snap)

        for _ in range(policy_module.PROBE_LIMIT):
            self.assertEqual(policy._probe_unknown_step(snap), target)

        self.assertIn((target.y, target.x), policy._blocked_unknown)
        self.assertFalse(policy._is_frontier(snap, grids[origin]))

    def test_escapes_a_searched_pocket_by_least_visited_route(self):
        # The live dl1 loop had three heavily visited cells north/east and an
        # older corridor continuing south. Once probing/searching was exhausted,
        # repeatedly seeking a flickering frontier pulled the bot north again.
        floors = {
            Position(8, 153),
            Position(9, 152),
            Position(9, 153),
            Position(10, 152),
            Position(11, 152),
            Position(12, 152),
        }
        grids = {pos: grid(pos.y, pos.x) for pos in floors}
        for pos in floors:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    neighbor = Position(pos.y + dy, pos.x + dx)
                    if neighbor not in floors and neighbor not in grids:
                        grids[neighbor] = grid(neighbor.y, neighbor.x, passable=False)

        policy = HengbotPolicy()
        policy._floor_key = (2, 1, 0)
        policy._recent.extend(
            [Position(8, 153), Position(9, 152), Position(9, 153)] * 4
        )
        policy._visit_counts.update(
            {
                Position(8, 153): 13,
                Position(9, 152): 18,
                Position(9, 153): 10,
                Position(10, 152): 9,
                Position(11, 152): 7,
            }
        )
        policy._search_counts[(9, 152)] = 8

        snap = Snapshot(
            player(9, 152), grids, [], floor_key=(2, 1, 0), width=200, height=100
        )
        self.assertEqual(policy.choose_key(snap), "2")
        self.assertEqual(policy.last_reason, "breakout:seek-frontier")

        advanced = replace(snap, player=player(10, 152))
        self.assertEqual(policy.choose_key(advanced), "2")
        self.assertEqual(policy.last_reason, "explore")

class DescentBlockCooldownTest(unittest.TestCase):
    def test_exhausted_floor_ascent_blocks_immediate_redescent(self):
        deep_grids = {
            Position(y, x): grid(
                y,
                x,
                passable=(y, x) == (10, 10),
                upstairs=(y, x) == (10, 10),
            )
            for y in range(9, 12)
            for x in range(9, 12)
        }
        deep = Snapshot(
            player(10, 10), deep_grids, [], floor_key=(2, 4, 0), width=30, height=30
        )
        pol = HengbotPolicy()
        pol._floor_key = deep.floor_key
        pol._build_grid_index(deep)
        pol._wall_search_counts.update(
            {wall: SEARCH_LIMIT for wall in pol._remembered_wall_t}
        )

        self.assertEqual(pol.choose_key(deep), "<")
        self.assertEqual(pol.last_reason, "stuck:ascend")
        self.assertTrue(pol._descent_is_blocked(deep))

        shallow = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10, downstairs=True),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=(2, 3, 0),
            width=30,
            height=30,
        )

        self.assertNotEqual(pol.choose_key(shallow), ">")
        self.assertTrue(pol._descent_is_blocked(shallow))

    def test_prime_blocks_downstairs_after_a_resume_boundary(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(2, 3, 0),
        )
        pol = HengbotPolicy()

        pol.prime(snap)

        self.assertTrue(pol._descent_is_blocked(snap))
        self.assertEqual(
            pol._descent_block_countdown, RESUME_DESCENT_BLOCK_DECISIONS
        )

    def test_block_expires_after_the_cooldown_without_a_level_up(self):
        grids = {Position(10, 10): grid(10, 10, downstairs=True)}
        snap = Snapshot(player(10, 10, food=12000), grids, [], floor_key=(2, 3, 0))
        pol = HengbotPolicy()
        pol.choose_key(snap)  # establish state
        pol._defer_descent(snap)
        self.assertTrue(pol._descent_is_blocked(snap))
        pol._descent_block_countdown = 0
        self.assertFalse(pol._descent_is_blocked(snap))
        # And once expired it stays clear.
        self.assertFalse(pol._descent_is_blocked(snap))

class SummonerMeleeTest(unittest.TestCase):
    def test_resume_landing_does_not_use_open_neighbor_summoner_gate(self):
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {
                Position(10, 10): grid(10, 10, upstairs=True),
                Position(10, 14): grid(10, 14, monster=True),
            },
            [hostile(1, 10, 14, distance=4, can_summon=True)],
            floor_key=(1, 5, 0),
        )
        policy = HengbotPolicy()

        with patch.object(policy, "_open_neighbor_count", return_value=8):
            policy.prime(snapshot)

        self.assertFalse(policy._descent_blocked)

    def test_summoner_cover_step_does_not_use_open_neighbor_gate(self):
        snapshot = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(9, 11): grid(9, 11, passable=False),
            },
            [],
            floor_key=(1, 5, 0),
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        with patch.object(policy, "_open_neighbor_count", return_value=8):
            self.assertTrue(policy._summoner_cover_in_one_step(snapshot))

    def test_killable_distant_summoner_is_shot_before_open_terrain_escape(self):
        grids = {
            Position(y, x): grid(
                y, x, monster=(y, x) == (10, 14)
            )
            for y in range(7, 14)
            for x in range(7, 15)
        }
        summoner = hostile(
            1, 10, 14, hp=24, max_hp=24, distance=4, can_summon=True
        )
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            grids,
            [summoner],
            inventory=[
                item(
                    "b", TVAL_ARROW, 1, count=20,
                    damage_dice_num=1, damage_dice_sides=4,
                ),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
            equipment=[
                item(
                    "a", TVAL_BOW, SV_BOW_SHORT,
                    is_equipment=True, to_d=2,
                )
            ],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snapshot), "fb6")
        self.assertEqual(policy.last_reason, "summoner:ranged-kill")

    def test_unkillable_summoner_retreats_with_exactly_four_open_neighbors(self):
        grids = {
            Position(y, x): grid(y, x, monster=(y, x) == (10, 14))
            for y in range(7, 14)
            for x in range(7, 15)
        }
        summoner = hostile(
            1, 10, 14, hp=100, max_hp=100, distance=4, can_summon=True
        )
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100), grids, [summoner],
            inventory=[
                item("b", TVAL_ARROW, 1, count=20,
                     damage_dice_num=1, damage_dice_sides=4),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
            equipment=[
                item("a", TVAL_BOW, SV_BOW_SHORT,
                     is_equipment=True, to_d=2),
            ],
            floor_key=(1, 5, 0),
        )
        policy = HengbotPolicy()

        with (
            patch.object(policy, "_open_neighbor_count", return_value=4),
            patch.object(policy, "_summoner_cover_in_one_step", return_value=False),
        ):
            self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_lethal_direct_damage_still_escapes_killable_summoner(self):
        grids = {
            Position(y, x): grid(y, x, monster=(y, x) == (10, 14))
            for y in range(7, 14)
            for x in range(7, 15)
        }
        summoner = hostile(
            1, 10, 14, hp=24, max_hp=24, distance=4, can_summon=True,
            max_ranged_damage=100,
        )
        snapshot = Snapshot(
            player(10, 10, hp=50, max_hp=100), grids, [summoner],
            inventory=[
                item("b", TVAL_ARROW, 1, count=20,
                     damage_dice_num=1, damage_dice_sides=4),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
            equipment=[
                item("a", TVAL_BOW, SV_BOW_SHORT,
                     is_equipment=True, to_d=2),
            ],
            floor_key=(1, 5, 0),
        )

        self.assertEqual(HengbotPolicy().choose_key(snapshot), "rt")

    def test_unkillable_summoner_is_shot_from_a_choke(self):
        grids = {
            Position(y, x): grid(y, x, monster=(y, x) == (10, 14))
            for y in range(7, 14)
            for x in range(7, 15)
        }
        snapshot = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            grids,
            [hostile(1, 10, 14, hp=100, max_hp=100,
                     distance=4, can_summon=True)],
            inventory=[
                item("b", TVAL_ARROW, 1, count=20,
                     damage_dice_num=1, damage_dice_sides=4),
            ],
            equipment=[
                item("a", TVAL_BOW, SV_BOW_SHORT,
                     is_equipment=True, to_d=2),
            ],
            floor_key=(1, 5, 0),
        )
        policy = HengbotPolicy()

        with patch.object(policy, "_open_neighbor_count", return_value=3):
            self.assertEqual(
                policy.choose_key(snapshot), "fb6", policy.last_reason
            )
        self.assertEqual(policy.last_reason, "ranged:fire")

    def test_distant_summoner_without_ranged_attack_is_not_chased(self):
        grids = {
            Position(y, x): grid(y, x, monster=(y, x) == (10, 14))
            for y in range(7, 14)
            for x in range(7, 15)
        }
        snapshot = Snapshot(
            player(10, 10), grids,
            [hostile(1, 10, 14, hp=100, max_hp=100,
                     distance=4, can_summon=True)],
            floor_key=(1, 5, 0),
        )
        policy = HengbotPolicy()

        with patch.object(policy, "_open_neighbor_count", return_value=3):
            self.assertEqual(policy.choose_key(snapshot), "5", policy.last_reason)
        self.assertEqual(policy.last_reason, "summoner:hold-choke")

    def test_summoner_within_two_cells_may_be_approached(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, monster=True),
        }
        snapshot = Snapshot(
            player(10, 10), grids,
            [hostile(1, 10, 12, hp=100, max_hp=100,
                     distance=2, can_summon=True)],
            floor_key=(1, 5, 0),
        )
        policy = HengbotPolicy()

        with (
            patch.object(policy, "_open_neighbor_count", return_value=3),
            patch.object(policy, "_hunt_step", return_value=Position(10, 11)),
        ):
            self.assertEqual(policy.choose_key(snapshot), "6")

    def test_teleports_from_adjacent_summoner_in_open_terrain(self):
        # Open terrain would normally trigger the retreat, but walking away from
        # an ALREADY-ADJACENT summoner just donates free hits — kill it.
        grids = {}
        for y in range(9, 12):
            for x in range(9, 12):
                grids[Position(y, x)] = grid(y, x)
        grids[Position(10, 11)] = grid(10, 11, monster=True)
        summoner = hostile(1, 10, 11, hp=40, max_hp=40, can_summon=True)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            grids,
            [summoner],
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)],
        )
        pol = HengbotPolicy()
        self.assertEqual(pol.choose_key(snap), "rt")
        self.assertEqual(pol.last_reason, "emergency:teleport")

class TownFrontierTest(unittest.TestCase):
    def _lone_town(self, town_map):
        snap = Snapshot(
            player(2, 2, class_id=PLAYER_CLASS_WARRIOR),
            {Position(2, 2): grid(2, 2)},
            [],
            floor_key=(0, 0, 0),
            width=7,
            height=5,
            town_flag=True,
        )
        pol = HengbotPolicy(town_map=town_map)
        pol._build_grid_index(snap)
        pol._observe(snap)
        return pol, snap

    def test_static_town_map_leaves_no_frontier_to_explore(self):
        # Night: unlit WALL tiles are absent from the emitted map, so a walkable
        # town tile borders 'unknown' walls. With the fixed town map loaded and
        # matching this floor, the whole town is known and nothing reads as a
        # frontier — the bot must not 'explore' the town aimlessly.
        tm = TownMap(name="T", width=7, height=5, walkable=frozenset({Position(2, 2), Position(2, 3)}))
        pol, snap = self._lone_town(tm)
        self.assertTrue(pol._town_map_active(snap))
        self.assertFalse(pol._is_frontier(snap, snap.grids[Position(2, 2)]))

    def test_static_town_map_disables_explore_sweep(self):
        # _plan_explore_path also picks any unvisited known-passable tile as a
        # sweep goal. The town map merges every walkable tile into the floor
        # set, so those unvisited tiles would send the bot wandering the town.
        # _explore_step must short-circuit to None when the static map is
        # active — the frontier guard alone does not cover the sweep goal.
        tm = TownMap(name="T", width=7, height=5, walkable=frozenset({Position(2, 2), Position(2, 3)}))
        pol, snap = self._lone_town(tm)
        self.assertTrue(pol._town_map_active(snap))
        self.assertIsNone(pol._explore_step(snap))

    def test_without_the_map_the_same_tile_is_a_frontier(self):
        # Proves the static map is what removes the frontier: absent it, the lone
        # tile's unlit neighbours are unknown and it DOES read as a frontier.
        pol, snap = self._lone_town(None)
        self.assertFalse(pol._town_map_active(snap))
        self.assertTrue(pol._is_frontier(snap, snap.grids[Position(2, 2)]))

class RememberedFrontierTest(unittest.TestCase):
    def test_routes_to_reachable_frontier_after_it_leaves_view(self):
        remembered_grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(10, 13)
        }
        corridor = [Position(10, 10), Position(10, 11), Position(10, 12)]
        for pos in corridor:
            remembered_grids[pos] = grid(pos.y, pos.x)
        first = Snapshot(
            player(10, 12),
            remembered_grids,
            [],
            floor_key=(1, 12, 43),
            width=40,
            height=40,
        )
        current = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(9, 10): grid(9, 10, passable=False),
                Position(11, 10): grid(11, 10, passable=False),
            },
            [],
            floor_key=(1, 12, 43),
            width=40,
            height=40,
        )
        pol = HengbotPolicy()
        pol._build_grid_index(first)
        pol._build_grid_index(current)
        for pos in corridor:
            pol._visit_counts[pos] = 1

        self.assertEqual(pol._explore_step(current), Position(10, 11))

    def test_oscillation_routes_to_remembered_frontier_before_local_wander(self):
        remembered_grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(9, 12)
            for x in range(8, 13)
        }
        west = Position(10, 9)
        start = Position(10, 10)
        east = Position(10, 11)
        frontier = Position(10, 12)
        corridor = [west, start, east, frontier]
        for pos in corridor:
            remembered_grids[pos] = grid(pos.y, pos.x)
        first = Snapshot(
            player(frontier.y, frontier.x),
            remembered_grids,
            [],
            floor_key=(1, 12, 43),
            width=40,
            height=40,
        )
        current = Snapshot(
            player(start.y, start.x, food=12000),
            {
                start: grid(start.y, start.x),
                west: grid(west.y, west.x),
                east: grid(east.y, east.x),
                Position(9, 10): grid(9, 10, passable=False),
                Position(11, 10): grid(11, 10, passable=False),
            },
            [],
            floor_key=(1, 12, 43),
            width=40,
            height=40,
        )
        pol = HengbotPolicy()
        pol._build_grid_index(first)
        pol._floor_key = first.floor_key
        pol._recent.extend([west, start] * (STUCK_WINDOW // 2))
        pol._search_counts[(start.y, start.x)] = SEARCH_LIMIT
        pol._visit_counts[west] = 1
        pol._visit_counts[start] = 2
        pol._visit_counts[east] = 5
        pol._visit_counts[frontier] = 2

        self.assertEqual(pol.choose_key(current), "6")
        self.assertEqual(pol.last_reason, "breakout:seek-frontier")

class TownNightNavigationTest(unittest.TestCase):
    """Night in a static town: only the player's own tile is lit, so every other
    town tile (stores, the '>' entrance) is dark and absent from the emitted
    grids. The bot must still route to those goals using the town map's
    remembered positions rather than stalling / wandering until dawn.
    """

    def _night_town(self, town_map, py=2, px=1):
        snap = Snapshot(
            player(py, px, class_id=PLAYER_CLASS_WARRIOR),
            {Position(py, px): grid(py, px)},  # only our own tile is emitted
            [],
            floor_key=(0, 0, 0),
            width=7,
            height=5,
            town_flag=True,
        )
        pol = HengbotPolicy(town_map=town_map)
        pol._build_grid_index(snap)
        pol._observe(snap)
        return pol, snap

    def _corridor(self):
        # A straight east-west corridor on row y=2 from x=1..5.
        return frozenset(Position(2, x) for x in range(1, 6))

    def test_goal_step_routes_across_unlit_tiles(self):
        tm = TownMap(name="T", width=7, height=5, walkable=self._corridor())
        pol, snap = self._night_town(tm)
        # Goal (2,5) is dark (not in grids) yet the corridor is remembered.
        self.assertEqual(pol._town_map_goal_step(snap, Position(2, 5)), Position(2, 2))

    def test_telmora_inn_route_avoids_q2_building_entrance(self):
        start = Position(21, 43)
        quest_entrance = Position(21, 44)
        target_inn = Position(21, 46)
        detour = {
            start,
            quest_entrance,
            Position(21, 45),
            target_inn,
            Position(20, 43),
            Position(19, 44),
            Position(19, 45),
            Position(20, 46),
        }
        tm = TownMap(
            name="Telmora",
            width=132,
            height=48,
            walkable=frozenset(detour),
            buildings={1: quest_entrance, 2: target_inn},
            quest_buildings={2: frozenset({quest_entrance})},
        )
        snap = Snapshot(
            player(start.y, start.x, class_id=PLAYER_CLASS_WARRIOR),
            {start: grid(start.y, start.x)},
            [],
            floor_key=(0, 0, 0),
            width=tm.width,
            height=tm.height,
            town_flag=True,
        )
        pol = HengbotPolicy(town_map=tm)
        pol._build_grid_index(snap)
        pol._observe(snap)

        self.assertEqual(
            pol._town_map_goal_step(snap, target_inn), Position(20, 43)
        )

    def test_town_route_uses_entrance_when_it_is_the_only_corridor(self):
        entrance = Position(2, 3)
        target = Position(2, 5)
        tm = TownMap(
            name="T",
            width=7,
            height=5,
            walkable=self._corridor(),
            buildings={1: entrance},
        )
        pol, snap = self._night_town(tm)

        self.assertEqual(pol._town_map_goal_step(snap, target), Position(2, 2))

    def test_town_route_keeps_goal_entrance_allowed(self):
        entrance = Position(2, 5)
        tm = TownMap(
            name="T",
            width=7,
            height=5,
            walkable=self._corridor(),
            stores={STORE_GENERAL: entrance},
        )
        pol, snap = self._night_town(tm)

        self.assertEqual(pol._town_map_goal_step(snap, entrance), Position(2, 2))

    def test_goal_step_none_when_already_on_target(self):
        tm = TownMap(name="T", width=7, height=5, walkable=self._corridor())
        pol, snap = self._night_town(tm, px=5)
        self.assertIsNone(pol._town_map_goal_step(snap, Position(2, 5)))

    def test_shallow_run_does_not_route_to_unverified_night_entrance(self):
        tm = TownMap(
            name="T", width=7, height=5, walkable=self._corridor(), entrance=Position(2, 5)
        )
        pol, snap = self._night_town(tm)
        pol._deepest_level = 1  # below RECALL_MIN_DEPTH -> descend on foot
        # The static map remembers only the coordinate, not its dungeon ID.  Do
        # not commit a foot-entry route until live metadata verifies the target.
        pol._descent_is_blocked = lambda _snap: False
        self.assertIsNone(pol._descent_step(snap))
        self.assertIsNone(pol._nav_ledger.descent_target)

    def test_cycle_broken_fundraising_routes_to_remembered_night_entrance(self):
        # Live town repetition after Q34: the first cycle break correctly
        # suppressed further errands, but the distant/unlit Yeek entrance was
        # absent from JSON grids.  The bot therefore discarded the static town
        # map coordinate and resumed stuck:wander instead of departing.
        entrance = Position(2, 5)
        tm = TownMap(
            name="T", width=7, height=5,
            walkable=self._corridor(), entrance=entrance,
        )
        pol, snap = self._night_town(tm)
        pol._town_restock_suppressed = True
        pol._fundraising_mode = "mine"
        pol._target_dungeon_id = DUNGEON_YEEK_CAVE

        with patch.object(pol, "_descent_is_blocked", return_value=False):
            self.assertEqual(pol._descent_step(snap), Position(2, 2))

        self.assertEqual(pol._descent_target_goal, entrance)
        self.assertEqual(pol.last_reason, "seek-downstairs")

    def test_cycle_break_rearms_normal_run_remembered_night_entrance(self):
        # Live 02:00 replay: ordinary routing had already expired the unlit
        # Angband entrance before the town cycle fired. The repair latched all
        # stores but inherited that expiry, so town:blocked:repetition could do
        # nothing except WAIT at (22,128). A cycle break is a new navigation
        # epoch and its departure owner must be able to use the static entrance.
        entrance = Position(2, 5)
        tm = TownMap(
            name="T", width=7, height=5,
            walkable=self._corridor(), entrance=entrance,
        )
        pol, snap = self._night_town(tm)
        pol._deepest_level = 40
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol._nav_ledger.expire("descend", entrance)

        pol._break_town_cycle(snap)

        self.assertTrue(pol._town_restock_suppressed)
        self.assertFalse(pol._nav_ledger.is_expired("descend", entrance))
        with patch.object(pol, "_descent_is_blocked", return_value=False):
            self.assertEqual(pol._descent_step(snap), Position(2, 2))
        self.assertEqual(pol._descent_target_goal, entrance)
        self.assertEqual(pol.last_reason, "seek-downstairs")

    def test_deep_run_does_not_route_to_entrance(self):
        # Past the recall threshold the bot returns by Word of Recall from
        # anywhere in town, so it must NOT trudge to the entrance even when it is
        # otherwise ready to descend.
        tm = TownMap(
            name="T", width=7, height=5, walkable=self._corridor(), entrance=Position(2, 5)
        )
        pol, snap = self._night_town(tm)
        pol._deepest_level = RECALL_MIN_DEPTH + 1
        pol._descent_is_blocked = lambda _snap: False
        self.assertIsNone(pol._town_map_descent_entrance(snap))
        self.assertIsNone(pol._descent_step(snap))

    def test_undersupplied_bot_is_still_blocked_from_the_entrance(self):
        # The night entrance route must not bypass the supply gate: an empty pack
        # (not departure-ready) still yields no descent step, so the bot shops
        # first instead of diving under-equipped.
        tm = TownMap(
            name="T", width=7, height=5, walkable=self._corridor(), entrance=Position(2, 5)
        )
        pol, snap = self._night_town(tm)
        pol._deepest_level = 1
        self.assertTrue(pol._descent_is_blocked(snap))
        self.assertIsNone(pol._descent_step(snap))

    def test_shop_approach_uses_town_map_store_at_night(self):
        tm = TownMap(
            name="T",
            width=7,
            height=5,
            walkable=self._corridor(),
            stores={STORE_GENERAL: Position(2, 5)},
        )
        pol, snap = self._night_town(tm)
        step = pol._town_map_goal_step(snap, tm.store_position(STORE_GENERAL))
        self.assertEqual(step, Position(2, 2))

    def test_parse_records_dungeon_entrance(self):
        import tempfile

        text = "\n".join(
            [
                "N:test",
                "D:#####",
                "D:#1.>#",  # store '1' at (1,1), floor, entrance '>' at (1,3)
                "D:#####",
            ]
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(text)
            path = Path(fh.name)
        try:
            tm = parse_town_map(path)
        finally:
            path.unlink()
        self.assertEqual(tm.entrance, Position(1, 3))
        self.assertIn(Position(1, 3), tm.walkable)  # '>' is walkable too
        self.assertEqual(tm.stores[STORE_GENERAL], Position(1, 1))

class TownTravelerCombatPriorityTest(unittest.TestCase):
    GOAL = Position(10, 30)

    @staticmethod
    def _snapshot(*, monster_pos=Position(10, 13), include_monster=True, width=40, height=20):
        grids = {
            Position(10, x): grid(10, x, monster=include_monster and x == monster_pos.x)
            for x in range(10, 31)
        }
        if monster_pos.y != 10 or monster_pos.x not in range(10, 31):
            grids[monster_pos] = grid(
                monster_pos.y, monster_pos.x, monster=include_monster
            )
        monsters = (
            [hostile(1, monster_pos.y, monster_pos.x, distance=3)]
            if include_monster
            else []
        )
        return Snapshot(
            player(10, 10),
            grids,
            monsters,
            floor_key=(0, 0, 0),
            width=width,
            height=height,
            town_flag=True,
            equipment=[item("light", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
        )

    def _approach(self, policy, snapshot):
        policy._shopping_approach_goal = self.GOAL
        policy._shopping_approach_store_type = STORE_GENERAL
        policy._build_grid_index(snapshot)
        return policy._shopping_approach_key(
            snapshot, Position(10, 11), "shop:travel"
        )

    def test_visible_hostile_preempts_town_travel(self):
        policy = HengbotPolicy()

        key = self._approach(policy, self._snapshot())

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")
        self.assertNotEqual(key, "\x1b`n!.")

    def test_adjacent_friendly_is_attacked_with_alter_and_inline_confirmation(self):
        policy = HengbotPolicy()
        snapshot = replace(
            self._snapshot(monster_pos=Position(10, 11)),
            visible_monsters=[
                MonsterState(
                    1, Position(10, 11), hp=10, max_hp=10, distance=1,
                    friendly=True, pet=False,
                )
            ],
        )

        key = self._approach(policy, snapshot)

        self.assertEqual(key, "+6y")
        self.assertEqual(policy.last_reason, "town:kill-mob-friendly")
        self.assertNotEqual(key, "6")

    def test_visible_friendly_is_approached_despite_multiple_hostiles(self):
        policy = HengbotPolicy()
        snapshot = self._snapshot(monster_pos=Position(10, 13))
        snapshot = replace(
            snapshot,
            visible_monsters=[
                hostile(1, 10, 13, distance=3),
                hostile(2, 10, 14, distance=4),
                MonsterState(
                    3, Position(11, 13), hp=10, max_hp=10, distance=3,
                    friendly=True, pet=False,
                ),
            ],
            grids={
                **snapshot.grids,
                Position(10, 14): grid(10, 14, monster=True),
                Position(11, 13): grid(11, 13, monster=True),
            },
        )

        self.assertEqual(self._approach(policy, snapshot), "6")
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")

    def test_visible_friendly_is_engaged_without_range_or_strength_gate(self):
        for monster_pos, distance, max_hp, speed in (
            (Position(10, 13), 3, 10, 110),
            (Position(10, 11), 1, 101, 121),
        ):
            with self.subTest(monster_pos=monster_pos):
                policy = HengbotPolicy()
                snapshot = replace(
                    self._snapshot(monster_pos=monster_pos),
                    visible_monsters=[
                        MonsterState(
                            1, monster_pos, hp=max_hp, max_hp=max_hp,
                            distance=distance, friendly=True, pet=False,
                            speed=speed,
                        )
                    ],
                )

                key = self._approach(policy, snapshot)
                if distance == 1:
                    self.assertEqual(key, "+6y")
                    self.assertEqual(policy.last_reason, "town:kill-mob-friendly")
                else:
                    self.assertEqual(key, "6")
                    self.assertEqual(policy.last_reason, "town:kill-mob-approach")

    def test_pet_is_not_engaged_and_town_travel_proceeds(self):
        policy = HengbotPolicy()
        snapshot = replace(
            self._snapshot(monster_pos=Position(10, 13)),
            visible_monsters=[
                MonsterState(
                    1, Position(10, 13), hp=10, max_hp=10, distance=3,
                    friendly=True, pet=True,
                )
            ],
        )

        self.assertEqual(self._approach(policy, snapshot), "\x1b`n!.")
        self.assertEqual(policy.last_reason, "shop:travel")

    def test_unreachable_hostile_falls_through_to_town_travel(self):
        policy = HengbotPolicy()
        snapshot = self._snapshot()
        snapshot = replace(
            snapshot,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 13): grid(10, 13, monster=True),
                self.GOAL: grid(self.GOAL.y, self.GOAL.x),
            },
        )

        self.assertEqual(self._approach(policy, snapshot), "\x1b`n!.")
        self.assertEqual(policy.last_reason, "shop:travel")

    def test_adjacent_hostile_remains_owned_by_melee(self):
        policy = HengbotPolicy()
        snapshot = replace(
            self._snapshot(monster_pos=Position(10, 11)),
            visible_monsters=[hostile(1, 10, 11, distance=1)],
        )

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_border_hostile_does_not_pull_hunt_onto_border(self):
        policy = HengbotPolicy()
        monster_pos = Position(0, 3)
        grids = {
            Position(y, 3): grid(y, 3, monster=y == 0)
            for y in range(5)
        }
        snapshot = Snapshot(
            player(2, 3),
            grids,
            [hostile(1, 0, 3, distance=2)],
            floor_key=(0, 0, 0),
            width=7,
            height=5,
            town_flag=True,
        )
        policy._build_grid_index(snapshot)

        key = policy._town_clear_traveler_key(snapshot, self.GOAL)

        self.assertEqual(key, "8")
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")
        self.assertFalse(policy._on_town_border(snapshot, Position(1, 3)))

    def test_hunt_interlude_preserves_travel_progress_and_then_resumes(self):
        policy = HengbotPolicy()
        clear = self._snapshot(include_monster=False)
        self.assertEqual(self._approach(policy, clear), "\x1b`n!.")
        travel_state = policy._town_travel_state

        self.assertEqual(self._approach(policy, self._snapshot()), "6")
        self.assertEqual(policy._town_travel_state, travel_state)

        resumed = replace(clear, player=player(10, 12))
        self.assertEqual(self._approach(policy, resumed), "\x1b`n!.")
        self.assertEqual(policy.last_reason, "shop:travel")

    def test_hidden_town_hunt_target_does_not_resume_travel(self):
        policy = HengbotPolicy()
        visible = self._snapshot(monster_pos=Position(10, 13))
        self.assertEqual(self._approach(policy, visible), "6")

        hidden = replace(
            visible,
            player=player(10, 11),
            visible_monsters=[],
            grids={
                position: replace(cell, monster_index=0)
                for position, cell in visible.grids.items()
            },
        )
        self.assertEqual(self._approach(policy, hidden), "6")
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")

class WarningGridAvoidanceTest(unittest.TestCase):
    """The 2026-08-03 06:23 Orc cave 19F capture: loot at (25,93) two cells
    north of (27,93), the step grid (26,93) raising the TR_WARNING prompt
    「本当にこのまま進むか？[y/n]」, and the bot re-posting '8' forever."""

    FLOOR = (3, 19, 0)
    PROMPT_JA = "本当にこのまま進むか？[y/n]"
    PROMPT_EN = "Really want to go ahead? [y/n]"

    def corridor(self, *, position=Position(27, 93), messages=(), inventory=()):
        grids = {
            Position(28, 93): grid(28, 93),
            Position(27, 93): grid(27, 93),
            Position(26, 93): grid(26, 93),
            Position(25, 93): grid(25, 93, objects=1, unsafe=True),
        }
        return Snapshot(
            player(position.y, position.x, hp=606, max_hp=606, level=31),
            grids,
            [],
            floor_key=self.FLOOR,
            inventory=list(inventory),
            messages=tuple(messages),
        )

    def movement_supplies(self):
        # The user scoped the exhausted-supplies ledger to movement
        # consumables only (「移動に関するルールなのでテレポート／ショート・
        # テレポート／帰還の巻物に限定する」).
        return {
            "teleport-scroll": item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            "phase-scroll": item("a", TVAL_SCROLL, SV_SCROLL_PHASE_DOOR),
            "recall-scroll": item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
        }

    def non_movement_potions(self):
        return {
            "cure-critical": item("a", TVAL_POTION, SV_POTION_CURE_CRITICAL),
            "healing": item("a", TVAL_POTION, SV_POTION_HEALING),
        }

    def refused_policy(self, inventory):
        """Drive the capture through choose_key up to the answered prompt."""
        policy = HengbotPolicy()
        first = policy.choose_key(self.corridor(inventory=inventory))
        self.assertEqual(first, "8")
        self.assertEqual(policy.last_reason, "seek-loot")
        policy.choose_key(
            self.corridor(
                messages=("T:12345 - ボロ布が鋭く震えた！", self.PROMPT_JA),
                inventory=inventory,
            )
        )
        return policy

    def test_warning_prompt_is_answered_never_a_movement_key(self):
        # Revert-proof pin of the incident: at the prompt-bearing snapshot the
        # unfixed policy re-posts the movement key '8'; the fix answers 'n'.
        supply = [item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT)]
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(self.corridor(inventory=supply)), "8")
        key = policy.choose_key(
            self.corridor(
                messages=("T:12345 - ボロ布が鋭く震えた！", self.PROMPT_JA),
                inventory=supply,
            )
        )
        self.assertNotIn(key, set("12346789"))
        self.assertEqual(key, "n")
        self.assertEqual(policy.last_reason, "warning:refuse")
        self.assertIn(Position(26, 93), policy._warning_refused_cells)
        self.assertIn(Position(26, 93), policy._engagement_avoid_cells)

    def test_refused_grid_is_not_retargeted_or_re_entered(self):
        supply = [item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT)]
        policy = self.refused_policy(supply)

        key = policy.choose_key(self.corridor(inventory=supply))

        # The only route to the loot runs through the refused grid, so the
        # loot is unreachable by walking and must not be selected again.
        self.assertIsNone(policy._loot_target)
        self.assertNotEqual(policy.last_reason, "seek-loot")
        self.assertNotEqual(key, "8")

    def test_prompt_recognized_with_decorations_in_both_languages(self):
        cases = {
            "ja-plain": self.PROMPT_JA,
            "ja-turn-prefix": f"T:9214 - {self.PROMPT_JA}",
            "ja-repeat-suffix": f"{self.PROMPT_JA} <x2>",
            "en-plain": self.PROMPT_EN,
            "en-both-decorations": f"T:9214 - {self.PROMPT_EN} <x3>",
        }
        supply = [item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT)]
        for label, message in cases.items():
            with self.subTest(label):
                policy = HengbotPolicy()
                policy.choose_key(self.corridor(inventory=supply))
                key = policy.choose_key(
                    self.corridor(messages=(message,), inventory=supply)
                )
                self.assertEqual(key, "n")
                self.assertIn(Position(26, 93), policy._warning_refused_cells)

    def test_forced_walk_only_when_supplies_entirely_exhausted(self):
        # Entirely exhausted ledger: the refusal stands once ('n'), then the
        # forced walk re-enters the grid with its deliberate 'y' attached.
        policy = self.refused_policy([])
        self.assertEqual(policy.choose_key(self.corridor(inventory=[])), "8y")
        self.assertEqual(policy.last_reason, "seek-loot")

        # Any single remaining MOVEMENT supply forbids the forced walk: no
        # 'y' is composed and the refused grid stays avoided.
        for label, supply in self.movement_supplies().items():
            with self.subTest(label):
                policy = self.refused_policy([supply])
                key = policy.choose_key(self.corridor(inventory=[supply]))
                self.assertNotIn("y", key)
                self.assertNotEqual(key, "8")
                self.assertIn(
                    Position(26, 93), policy._engagement_avoid_cells
                )

        # This is a movement rule (user ruling): healing/status potions are
        # not part of the ledger, so remaining potions do NOT block the
        # forced walk.
        for label, potion in self.non_movement_potions().items():
            with self.subTest(f"non-blocking-{label}"):
                policy = self.refused_policy([potion])
                key = policy.choose_key(self.corridor(inventory=[potion]))
                self.assertEqual(key, "8y")
                self.assertEqual(policy.last_reason, "seek-loot")

    def test_unaware_copy_is_not_a_supply(self):
        # An unidentified Teleport scroll cannot be deliberately read; the
        # ledger reports exhausted and the forced walk proceeds.
        unaware = [item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT, aware=False)]
        policy = self.refused_policy(unaware)
        self.assertEqual(policy.choose_key(self.corridor(inventory=unaware)), "8y")

    def test_walk_through_prompt_report_is_not_a_refusal(self):
        # After the forced walk crosses, the next snapshot still carries the
        # prompt message (input_check records it before the attached 'y' is
        # consumed).  Standing ON the entered grid proves the crossing: no
        # 'n', no re-latch, ordinary progress toward the loot resumes.
        policy = self.refused_policy([])
        self.assertEqual(policy.choose_key(self.corridor(inventory=[])), "8y")
        key = policy.choose_key(
            self.corridor(
                position=Position(26, 93),
                messages=(self.PROMPT_JA,),
                inventory=[],
            )
        )
        self.assertEqual(key, "8")
        self.assertEqual(policy.last_reason, "seek-loot")

    def test_unattributable_prompt_still_answered_without_a_record(self):
        # A fresh process (restart over a pending prompt) sees the prompt
        # message without having issued the walk: answer 'n' deliberately,
        # record nothing — the retried movement re-raises the prompt and the
        # next pass attributes it.
        policy = HengbotPolicy()
        key = policy.choose_key(self.corridor(messages=(self.PROMPT_JA,)))
        self.assertEqual(key, "n")
        self.assertEqual(policy.last_reason, "warning:refuse")
        self.assertFalse(policy._warning_refused_cells)

    def test_floor_change_clears_warning_refusals(self):
        policy = self.refused_policy([])
        other_floor = self.corridor(inventory=[])
        other_floor = replace(other_floor, floor_key=(3, 20, 0))
        policy.choose_key(other_floor)
        self.assertFalse(policy._warning_refused_cells)

    def test_latched_cell_yields_a_different_objective_across_decisions(self):
        # Two consecutive post-refusal decisions on the same static floor,
        # driven through the device-recovery selector (_mana_food_loot_key →
        # _nearest_position_step), which sits ABOVE the navigation-livelock
        # rung: with an avoid-unaware BFS the latched step is re-picked and
        # warning:blocked-step repeats forever, starving the livelock.  The
        # avoid-aware BFS abandons the unreachable device and the bot
        # pursues a different objective (exploration) BOTH times.
        supply = [item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT)]

        def device_corridor(*, messages=()):
            grids = {
                Position(28, 93): grid(28, 93),
                Position(27, 93): grid(27, 93),
                Position(26, 93): grid(26, 93),
                Position(25, 93): grid(
                    25, 93, objects=1, object_tvals=(TVAL_WAND,)
                ),
            }
            return Snapshot(
                player(
                    27, 93, hp=606, max_hp=606, level=31,
                    food_type=FOOD_TYPE_MANA,
                ),
                grids,
                [],
                floor_key=self.FLOOR,
                inventory=list(supply),
                messages=tuple(messages),
            )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(device_corridor()), "8")
        self.assertEqual(policy.last_reason, "mana-food:seek-device")
        self.assertEqual(
            policy.choose_key(device_corridor(messages=(self.PROMPT_JA,))),
            "n",
        )
        self.assertIn(Position(26, 93), policy._warning_refused_cells)

        for _ in range(2):
            key = policy.choose_key(device_corridor())
            self.assertNotEqual(policy.last_reason, "warning:blocked-step")
            self.assertNotEqual(key, "5")
            self.assertNotIn(key, {"8", "8y"})

    def test_static_wiggle_exits_to_pickup_when_neighbor_is_latched(self):
        # The stationary loot wiggle re-picks the min-visit neighbour every
        # decision.  In a dead-end whose only neighbour is warning-latched,
        # an avoid-unaware pick would repeat _step_toward's WAIT forever
        # (the rung sits above the navigation livelock, starving it).  The
        # avoid-aware pick leaves no admissible neighbour, so the pickup is
        # the exit — pinned across two consecutive decisions.
        supply = [item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT)]

        def deadend(*, messages=()):
            grids = {
                Position(27, 93): grid(27, 93, objects=2),
                Position(26, 93): grid(26, 93),
            }
            return Snapshot(
                player(27, 93, hp=606, max_hp=606, level=31),
                grids,
                [],
                floor_key=self.FLOOR,
                inventory=list(supply),
                messages=tuple(messages),
            )

        policy = HengbotPolicy()
        # The wiggle steps toward the only neighbour; the warning refuses it.
        self.assertEqual(policy.choose_key(deadend()), "8")
        self.assertEqual(policy.last_reason, "trigger-autodestroy")
        self.assertEqual(policy.choose_key(deadend()), "8")
        self.assertEqual(
            policy.choose_key(deadend(messages=(self.PROMPT_JA,))), "n"
        )
        self.assertIn(Position(26, 93), policy._warning_refused_cells)

        for _ in range(2):
            key = policy.choose_key(deadend())
            self.assertNotEqual(policy.last_reason, "warning:blocked-step")
            self.assertNotEqual(key, "5")

    def test_exhaustion_never_erases_engagement_owned_avoidance(self):
        # A coordinate can be owned by BOTH the warning latch and the
        # engagement/status-threat avoidance.  The forced-walk withdrawal may
        # only remove the warning owner's contribution: while the engagement
        # owner still claims the cell, exhausted supplies must not re-open it.
        supply = [item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT)]
        policy = self.refused_policy(supply)
        policy._claim_engagement_avoid_cells((Position(26, 93),))

        key = policy.choose_key(self.corridor(inventory=[]))

        self.assertNotIn(key, {"8", "8y"})
        self.assertIn(Position(26, 93), policy._engagement_avoid_cells)

        # Control: without the engagement claim the same exhausted flow
        # performs the sanctioned forced walk.
        control = self.refused_policy(supply)
        self.assertEqual(control.choose_key(self.corridor(inventory=[])), "8y")


    def test_concatenation_scanner_flags_all_bypass_shapes(self):
        # The scanner must flag every known bypass shape against synthetic
        # source — direct, nested at any depth, and the laundered forms —
        # while accepting the two legitimate patterns the production tree
        # uses (tail= ownership, and a bare comparison of a bound result).
        flagged = {
            "direct": "def f(self):\n"
            "    return self._step_toward(s, p) + 'y'\n",
            "nested-call-argument": "def f(self):\n"
            "    return g(self._step_toward(s, p) + 'y')\n",
            "deeply-nested": "def f(self):\n"
            "    return ('a' + (self._step_toward(s, p) + 'y'))\n",
            "laundered-name": "def f(self):\n"
            "    walk = self._step_toward(s, p)\n"
            "    return walk + 'y'\n",
            "augmented-assignment": "def f(self):\n"
            "    walk = self._step_toward(s, p)\n"
            "    walk += 'y'\n"
            "    return walk\n",
            "walrus": "def f(self):\n"
            "    return (w := self._step_toward(s, p)) and w + 'y'\n",
        }
        clean = {
            "tail-ownership": "def f(self):\n"
            "    return self._step_toward(s, p, tail='y')\n",
            "bound-comparison": "def f(self):\n"
            "    walk = self._step_toward(s, p)\n"
            "    return walk if walk != '5' else None\n",
        }
        for label, code in flagged.items():
            with self.subTest(label):
                self.assertTrue(
                    step_toward_concatenation_offenders(ast.parse(code))
                )
        for label, code in clean.items():
            with self.subTest(label):
                self.assertEqual(
                    step_toward_concatenation_offenders(ast.parse(code)), []
                )
