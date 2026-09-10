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

class FixedQuestTest(unittest.TestCase):
    QUEST_ID = 1

    def _quest(self, status: int) -> QuestState:
        return QuestState(
            id=self.QUEST_ID,
            name="Thieves Hideout",
            status=status,
            type=6,
            level=5,
            flags=6,
            fixed=True,
            has_reward=True,
            reward_baseitem_id=42,
        )

    def _town_map(self, *, reward=False) -> TownMap:
        walkable = {
            Position(y, x)
            for y in range(66)
            for x in range(198)
            if not reward or y == 27
        }
        return TownMap(
            name="Outpost",
            width=198,
            height=66,
            walkable=frozenset(walkable),
            quest_buildings={self.QUEST_ID: frozenset({Position(26, 98)})},
            quest_entrances={self.QUEST_ID: frozenset({Position(35, 177)})},
            reward_positions=frozenset({Position(27, 98)}),
        )

    def _town_snapshot(self, y, x, grids, status):
        return Snapshot(
            player(y, x, level=8, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            town_id=0,
            town_index=1,
            quests={self.QUEST_ID: self._quest(status)},
        )

    def test_requests_allowed_fixed_quest_at_quest_building(self):
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(26, 98, building_type=1, building_special=1),
        }
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True

        key = policy.choose_key(self._town_snapshot(26, 97, grids, 0))

        self.assertEqual(key, "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:request")

    def test_claim_approach_yields_after_one_postless_frozen_board_selection(self):
        grids = {
            Position(26, 96): grid(26, 96),
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(26, 98, building_type=1, building_special=1),
        }
        policy = HengbotPolicy(self._town_map())
        policy._floor_t.update({(26, 96), (26, 97), (26, 98)})
        frozen = self._town_snapshot(26, 96, grids, QUEST_STATUS_COMPLETED)

        first = policy._fixed_quest_building_key(
            frozen, self.QUEST_ID, "fixedquest:claim",
            set_reward_pending=True,
        )
        refused_retry = policy._fixed_quest_building_key(
            frozen, self.QUEST_ID, "fixedquest:claim",
            set_reward_pending=True,
        )
        advanced = replace(
            frozen,
            player=replace(frozen.player, position=Position(26, 97)),
        )
        after_progress = policy._fixed_quest_building_key(
            advanced, self.QUEST_ID, "fixedquest:claim",
            set_reward_pending=True,
        )

        self.assertEqual((first, refused_retry, after_progress), ("6", None, "6q\x1b"))

    def test_ready_unoffered_q14_does_not_shadow_offered_q34(self):
        quests = {
            14: replace(self._quest(QUEST_STATUS_UNTAKEN), id=14, level=5),
            34: replace(self._quest(QUEST_STATUS_UNTAKEN), id=34, level=5),
        }
        snapshot = replace(
            self._town_snapshot(26, 97, {
                Position(26, 98): grid(
                    26, 98, building_type=1, building_special=1
                ),
                Position(30, 40): grid(
                    30, 40, building_type=1, building_special=34
                ),
            }, QUEST_STATUS_UNTAKEN),
            quests=quests,
        )
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True

        self.assertEqual(policy._fixed_quest_target(snapshot), 34)

    def test_q14_becomes_eligible_and_routes_when_castle_offers_it(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_UNTAKEN)
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True

        self.assertEqual(policy._fixed_quest_target(snapshot), 14)
        self.assertEqual(policy._fixed_quest_key(snapshot, []), "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:request")

    def _win_quest_acceptance_fixture(self, extra_quests=()):
        knowledge = {
            1: QuestInfo(1, "Thieves Hideout", 6, 5, 6,
                         placed_monsters=((44, 1),)),
            8: QuestInfo(8, "Oberon", 1, 99, 0, dungeon=1,
                         max_num=1, monrace_id=860),
            9: QuestInfo(9, "Serpent of Chaos", 1, 100, 0, dungeon=1,
                         max_num=1, monrace_id=862),
            14: QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0,
                          num_mon=16, monrace_id=257),
        }
        quests = {
            1: self._quest(QUEST_STATUS_UNTAKEN),
            8: QuestState(8, status=QUEST_STATUS_TAKEN, fixed=True),
            9: QuestState(9, status=QUEST_STATUS_TAKEN, fixed=True),
            **dict(extra_quests),
        }
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(
                26, 98, building_type=1, building_special=1
            ),
        }
        base = self._town_snapshot(26, 97, grids, QUEST_STATUS_UNTAKEN)
        snapshot = replace(
            base,
            player=replace(
                base.player, level=8, hp=1000, max_hp=1000,
                main_hand_blows=10, main_hand_to_d=100,
            ),
            equipment=[item(
                "main_hand", TVAL_SWORD, 1, is_equipment=True,
                damage_dice_num=10, damage_dice_sides=10,
            )],
            quests=quests,
        )
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge=knowledge,
            monrace_knowledge={44: MonraceKnowledge(1, 110, False, False)},
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        return policy, snapshot

    def test_birth_taken_win_quests_do_not_block_ready_q1_acceptance(self):
        policy, snapshot = self._win_quest_acceptance_fixture()

        self.assertEqual(policy._fixed_quest_target(snapshot), 1)
        self.assertTrue(policy.fixed_quest_readiness_state()["verdict"])
        policy._fixed_quest_building_key = (
            lambda _snapshot, _quest_id, reason, **_kwargs: reason
        )
        self.assertEqual(
            policy._fixed_quest_key(snapshot, []), "fixedquest:request"
        )

    def test_real_taken_allowlist_quest_still_serializes_acceptance(self):
        q14 = QuestState(14, status=QUEST_STATUS_TAKEN, fixed=True)
        policy, snapshot = self._win_quest_acceptance_fixture({14: q14})

        self.assertEqual(policy._fixed_quest_target(snapshot), 14)
        self.assertIsNone(policy._fixed_quest_key(snapshot, []))

    def test_unsupported_taken_fixed_quest_still_blocks_acceptance(self):
        unsupported = QuestState(3, status=QUEST_STATUS_TAKEN, fixed=True)
        policy, snapshot = self._win_quest_acceptance_fixture({3: unsupported})

        self.assertIsNone(policy._fixed_quest_target(snapshot))
        self.assertIsNone(policy._fixed_quest_key(snapshot, []))

    def test_q2_is_entirely_absent_from_targeting_on_old_emitter_snapshot(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, 0),
            quests={2: QuestState(2, status=0, fixed=True)},
            visited_town_ids=None,
        )
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        self.assertIsNone(policy._fixed_quest_target(snapshot))

    def test_q2_is_absent_from_targeting_until_telmora_was_visited(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, 0),
            quests={2: QuestState(2, status=0, fixed=True)},
            visited_town_ids=(0,),
        )
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True

        self.assertIsNone(policy._fixed_quest_target(snapshot))

    def test_q2_telmora_visit_requires_exported_visited_town(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, 0),
            player=replace(self._town_snapshot(26, 97, {}, 0).player, gold=2000),
            quests={2: QuestState(2, status=0, fixed=True)},
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._town_teleport_key = lambda _snapshot, town_id: f"teleport:{town_id}"
        with patch.object(
            policy_module, "EXECUTABLE_QUEST_STRATEGY_IDS", frozenset({1, 2, 14, 34})
        ):
            self.assertEqual(
                policy._telmora_q2_travel_key(snapshot, snapshot.quests[2]),
                "teleport:1",
            )
        self.assertTrue(policy._telmora_q2_errand)

    def test_q2_travel_reads_rumors_before_unknown_telmora(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, QUEST_STATUS_UNTAKEN),
            player=replace(self._town_snapshot(26, 97, {}, 0).player, gold=5000),
            quests={2: QuestState(2, status=QUEST_STATUS_UNTAKEN, fixed=True)},
            visited_town_ids=(0,),
        )
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._fixed_quest_ready_for_travel = lambda _snapshot, _quest_id: True

        with (
            patch.object(policy, "_town_teleport_key") as travel,
            patch.object(policy, "_town_special_key", return_value="READ-RUMORS") as rumor,
        ):
            self.assertEqual(policy._fixed_quest_key(snapshot, []), "READ-RUMORS")

        travel.assert_not_called()
        rumor.assert_called_once_with(snapshot)
        self.assertEqual(policy._town_travel_rumor_pending, 1)

    def test_q2_travel_starts_only_after_telmora_unlock_is_exported(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, QUEST_STATUS_UNTAKEN),
            player=replace(self._town_snapshot(26, 97, {}, 0).player, gold=5000),
            quests={2: QuestState(2, status=QUEST_STATUS_UNTAKEN, fixed=True)},
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._fixed_quest_ready_for_travel = lambda _snapshot, _quest_id: True
        policy._town_travel_rumor_pending = 1

        with patch.object(policy, "_town_teleport_key", return_value="TO-TELMORA") as travel:
            self.assertEqual(policy._fixed_quest_key(snapshot, []), "TO-TELMORA")

        travel.assert_called_once_with(snapshot, 1)
        self.assertIsNone(policy._town_travel_rumor_pending)

    def test_unknown_fixed_quest_destination_drives_real_rumor_batch(self):
        inn = Position(26, 98)
        snapshot = replace(
            self._town_snapshot(
                26,
                97,
                {
                    Position(26, 97): grid(26, 97),
                    inn: grid(26, 98, building_type=0),
                },
                QUEST_STATUS_UNTAKEN,
            ),
            player=replace(self._town_snapshot(26, 97, {}, 0).player, gold=5000),
            visited_town_ids=(0,),
        )
        policy = HengbotPolicy(self._town_map())
        policy._town_travel_rumor_pending = 1
        policy._town_departure_ready = lambda _snapshot: False
        policy._nearest_goal_step = lambda _snapshot, _goal: inn

        key = policy._town_special_key(snapshot)

        self.assertTrue(key.startswith("6u\r"))
        self.assertTrue(key.endswith("\x1b"))
        self.assertEqual(policy.last_reason, "town:rumor-batch")

    def test_q2_acceptance_is_enabled_after_executor_lands(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, QUEST_STATUS_UNTAKEN),
            quests={2: QuestState(2, status=QUEST_STATUS_UNTAKEN, fixed=True)},
            visited_town_ids=(0, 1),
            town_id=1,
        )
        policy = HengbotPolicy(self._town_map())
        policy._fixed_quest_target = lambda _snapshot: 2
        policy._telmora_q2_travel_key = lambda _snapshot, _quest: None
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._fixed_quest_ready_for_travel = lambda _snapshot, _quest_id: True
        policy._fixed_quest_building_key = (
            lambda *_args, **_kwargs: "fixedquest:request"
        )

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "fixedquest:request")

    def _q14_town_fixture(self, status):
        quest = QuestState(
            14, status=status, type=QUEST_TYPE_KILL_LEVEL, level=5,
            dungeon_id=DUNGEON_YEEK_CAVE, fixed=True,
        )
        knowledge = {
            14: QuestInfo(
                14, "Warg Problem", QUEST_TYPE_KILL_LEVEL, 5, 2,
                dungeon=DUNGEON_YEEK_CAVE, max_num=1, monrace_id=257,
            )
        }
        town_map = TownMap(
            name="Outpost", width=198, height=66,
            walkable=frozenset(
                Position(y, x) for y in range(66) for x in range(198)
            ),
            quest_buildings={14: frozenset({Position(26, 98)})},
            quest_entrances={},
            reward_positions=frozenset({Position(27, 98)}),
        )
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(
                26, 98, building_type=1, building_special=14
            ),
        }
        snapshot = replace(
            self._town_snapshot(26, 97, grids, QUEST_STATUS_UNTAKEN),
            quests={14: quest},
        )
        policy = HengbotPolicy(town_map, quest_knowledge=knowledge)
        policy._build_grid_index(snapshot)
        return policy, snapshot

    def test_q14_untaken_requests_castle_acceptance_without_retargeting_dungeon(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_UNTAKEN)
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._target_dungeon_id = 7

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:request")
        self.assertEqual(policy._target_dungeon_id, 7)

    def test_q14_taken_targets_yeek_for_walk_in_descent(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_TAKEN)
        policy._target_dungeon_id = 7

        self.assertIsNone(policy._fixed_quest_key(snapshot, []))
        self.assertEqual(policy._target_dungeon_id, DUNGEON_YEEK_CAVE)
        self.assertTrue(policy._taken_kill_quest_requires_walk_in(
            replace(snapshot, recall_depth=8)
        ))

    def test_q14_completed_claims_at_castle_and_latches_floor_reward(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_COMPLETED)

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:claim")
        self.assertEqual(policy._fixed_quest_reward_pending, 14)

    def test_q14_rewarded_collects_latched_floor_reward_and_clears_latch(self):
        policy, snapshot = self._q14_town_fixture(QUEST_STATUS_REWARDED)
        policy._fixed_quest_reward_pending = 14
        grids = {
            Position(27, 97): grid(27, 97),
            Position(27, 98): grid(27, 98, objects=1),
        }
        snapshot = replace(snapshot, player=player(27, 97), grids=grids)

        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "fixedquest:reward-approach")

        policy._floor_key = (0, 0, 0)
        policy._last_position = Position(27, 97)
        pickup = replace(snapshot, player=player(27, 98))
        self.assertEqual(policy.choose_key(pickup), "g")
        self.assertEqual(policy.last_reason, "fixedquest:reward-pickup")

        policy._floor_key = (0, 0, 0)
        policy._last_position = Position(27, 98)
        empty = replace(
            pickup,
            grids={
                Position(27, 97): grid(27, 97),
                Position(27, 98): grid(27, 98),
            },
        )
        self.assertIsNone(policy._fixed_quest_key(empty, []))
        self.assertIsNone(policy._fixed_quest_reward_pending)
        self.assertEqual(policy.last_reason, "fixedquest:reward-complete")

    def test_q2_outbound_travel_is_enabled_after_executor_lands(self):
        snapshot = replace(
            self._town_snapshot(26, 97, {}, QUEST_STATUS_UNTAKEN),
            player=replace(self._town_snapshot(26, 97, {}, 0).player, gold=2000),
            quests={2: QuestState(2, status=QUEST_STATUS_UNTAKEN, fixed=True)},
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._town_teleport_key = lambda _snapshot, town_id: f"teleport:{town_id}"

        self.assertEqual(
            policy._telmora_q2_travel_key(snapshot, snapshot.quests[2]),
            "teleport:1",
        )
        self.assertTrue(policy._telmora_q2_errand)

    def test_telmora_stranding_recovery_stays_ungated(self):
        snapshot = replace(self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN), quests={})
        policy = HengbotPolicy(self._town_map())
        policy._town_teleport_key = (
            lambda _snapshot, town_id: "home" if town_id == 0 else None
        )

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "home")

    def test_q2_in_morivant_uses_inn_service_directly_to_telmora(self):
        snapshot = replace(
            self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN, gold=2000),
            town_id=2,
            town_index=3,
        )
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready_for_travel = lambda _snapshot, _quest_id: True
        policy._town_teleport_key = (
            lambda _snapshot, town_id: f"teleport:{town_id}"
        )

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "teleport:1")
        self.assertTrue(policy._telmora_q2_errand)

    def test_q2_missing_floor_metadata_in_telmora_routes_to_quest_building(self):
        quest_door = Position(21, 41)
        telmora = TownMap(
            name="Telmora",
            width=198,
            height=66,
            walkable=frozenset(
                {Position(21, x) for x in range(41, 55)}
                | {Position(18, 22), quest_door}
            ),
            buildings={2: Position(18, 22), 1: Position(21, 44)},
            quest_buildings={2: frozenset({quest_door, Position(21, 44)})},
        )
        outpost = replace(
            self._town_map(), buildings={2: Position(25, 71)}
        )
        snapshot = replace(
            self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN, gold=2000),
            player=replace(
                self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN).player,
                position=Position(21, 54),
                gold=2000,
            ),
            town_id=-1,
            town_index=0,
            width=0,
            height=0,
            grids={
                Position(18, 22): grid(18, 22, building_type=2),
                quest_door: grid(21, 41, building_type=1, building_special=2),
                **{
                    Position(21, x): grid(21, x)
                    for x in range(42, 55)
                },
                Position(65, 197): grid(65, 197, passable=False),
            },
        )
        policy = HengbotPolicy(town_maps={0: outpost, 1: telmora})
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._fixed_quest_ready_for_travel = lambda _snapshot, _quest_id: True
        policy._build_grid_index(snapshot)

        self.assertEqual(policy._effective_town_id(snapshot), 1)
        self.assertTrue(policy._town_map_active(snapshot))
        self.assertEqual(policy._fixed_quest_key(snapshot, []), "4")
        self.assertEqual(policy.last_reason, "fixedquest:request:approach")

    def test_morivant_inn_selects_telmora_with_letter_b(self):
        inn = Position(26, 98)
        town_map = replace(self._town_map(), buildings={4: inn})
        snapshot = replace(
            self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN, gold=2000),
            town_id=2,
            town_index=3,
            grids={
                Position(26, 97): grid(26, 97),
                inn: grid(26, 98, building_type=4),
            },
        )
        policy = HengbotPolicy(town_maps={2: town_map})
        policy._build_grid_index(snapshot)

        self.assertEqual(policy._town_teleport_key(snapshot, 1), "6mb")

    def test_town_teleport_departure_requires_home_fare_reserve(self):
        inn = Position(26, 98)
        town_map = replace(self._town_map(), buildings={0: inn})
        base = replace(
            self._town_snapshot(26, 97, {inn: grid(26, 98, building_type=0)}, 0),
            town_id=0,
        )
        policy = HengbotPolicy(town_map)
        policy._build_grid_index(base)

        refused = replace(base, player=replace(base.player, gold=999))
        self.assertIsNone(policy._town_teleport_key(refused, 2))
        self.assertEqual(
            policy.town_teleport_refusal,
            {
                "current_town_id": 0,
                "destination_town_id": 2,
                "gold": 999,
                "required_gold": 2 * TOWN_TELEPORT_COST,
            },
        )
        allowed = replace(base, player=replace(base.player, gold=1000))
        self.assertEqual(policy._town_teleport_key(allowed, 2), "6mc")

    def test_town_teleport_return_only_requires_the_fare(self):
        inn = Position(26, 98)
        town_map = replace(self._town_map(), buildings={4: inn})
        base = replace(
            self._telmora_q2_snapshot(QUEST_STATUS_REWARDED),
            grids={Position(26, 97): grid(26, 97), inn: grid(26, 98, building_type=4)},
        )
        policy = HengbotPolicy(town_maps={1: town_map})
        policy._build_grid_index(base)

        refused = replace(base, player=replace(base.player, gold=499))
        self.assertIsNone(policy._town_teleport_key(refused, 0))
        allowed = replace(base, player=replace(base.player, gold=500))
        self.assertEqual(policy._town_teleport_key(allowed, 0), "6ma")

    def test_other_executable_building_quest_acceptance_stays_unchanged(self):
        for quest_id in (1, 34):
            with self.subTest(quest_id=quest_id):
                snapshot = replace(
                    self._town_snapshot(26, 97, {}, QUEST_STATUS_UNTAKEN),
                    quests={
                        quest_id: QuestState(
                            quest_id, status=QUEST_STATUS_UNTAKEN, fixed=True
                        )
                    },
                )
                policy = HengbotPolicy(self._town_map())
                policy._fixed_quest_target = lambda _snapshot, value=quest_id: value
                policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
                policy._fixed_quest_building_key = (
                    lambda *_args, **_kwargs: "fixedquest:request"
                )

                self.assertEqual(policy._fixed_quest_key(snapshot, []), "fixedquest:request")

    def test_enabling_q2_executor_restores_acceptance(self):
        snapshot = replace(
            self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN),
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._fixed_quest_ready_for_travel = lambda _snapshot, _quest_id: True
        policy._fixed_quest_is_offered = lambda _snapshot, _quest_id: True
        policy._fixed_quest_building_key = (
            lambda *_args, **_kwargs: "fixedquest:request"
        )

        with patch.object(
            policy_module, "EXECUTABLE_QUEST_STRATEGY_IDS", frozenset({1, 2, 14, 34})
        ):
            self.assertEqual(policy._fixed_quest_key(snapshot, []), "fixedquest:request")

    def _telmora_q2_snapshot(self, status, *, gold=500):
        return replace(
            self._town_snapshot(26, 97, {}, 0),
            player=replace(self._town_snapshot(26, 97, {}, 0).player, gold=gold),
            town_id=1,
            quests={2: QuestState(2, status=status, fixed=True)},
            visited_town_ids=(0, 1),
        )

    def test_q2_return_trip_uses_errand_latch_after_claim(self):
        snapshot = self._telmora_q2_snapshot(QUEST_STATUS_REWARDED)
        policy = HengbotPolicy(self._town_map())
        policy._telmora_q2_errand = True
        policy.approved_quest_strategy = lambda _quest_id: None
        policy._town_teleport_key = lambda _snapshot, town_id: "a" if town_id == 0 else None

        self.assertEqual(policy._telmora_q2_travel_key(snapshot, snapshot.quests[2]), "a")

    def test_q2_approval_revocation_in_telmora_returns_home(self):
        snapshot = self._telmora_q2_snapshot(QUEST_STATUS_TAKEN)
        policy = HengbotPolicy(self._town_map())
        policy._telmora_q2_errand = True
        policy.approved_quest_strategy = lambda _quest_id: None
        policy._town_teleport_key = lambda _snapshot, town_id: "a" if town_id == 0 else None

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "a")

    def test_q2_failure_in_telmora_returns_home(self):
        snapshot = self._telmora_q2_snapshot(5)
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: object()
        policy._town_teleport_key = lambda _snapshot, town_id: "a" if town_id == 0 else None

        self.assertEqual(policy._fixed_quest_key(snapshot, []), "a")

    def test_q2_acceptance_in_telmora_requires_approval(self):
        snapshot = self._telmora_q2_snapshot(QUEST_STATUS_UNTAKEN)
        policy = HengbotPolicy(self._town_map())
        policy.approved_quest_strategy = lambda _quest_id: None
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        policy._fixed_quest_building_key = lambda *_args, **_kwargs: "accept"

        self.assertIsNone(policy._fixed_quest_key(snapshot, []))

    def test_q2_return_trip_requires_teleport_fare(self):
        snapshot = self._telmora_q2_snapshot(QUEST_STATUS_REWARDED, gold=499)
        policy = HengbotPolicy(self._town_map())
        policy._telmora_q2_errand = True
        policy.approved_quest_strategy = lambda _quest_id: object()
        self.assertIsNone(policy._telmora_q2_travel_key(snapshot, snapshot.quests[2]))
        self.assertEqual(policy.last_reason, "town:teleport-refused-fare")

    def test_q2_outpost_inn_selects_telmora_with_letter_b(self):
        inn = Position(26, 98)
        town_map = self._town_map()
        town_map = replace(town_map, buildings={0: inn})
        snapshot = replace(
            self._town_snapshot(
                26, 97, {Position(26, 97): grid(26, 97, building_type=-1)}, 0
            ),
            visited_town_ids=(0, 1),
        )
        policy = HengbotPolicy(town_map)
        policy._build_grid_index(snapshot)
        self.assertEqual(policy._town_teleport_key(snapshot, 1), "6mb")

    def test_readiness_does_not_use_player_level(self):
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 1),))
        harmless = MonraceKnowledge(1, 110, False, False)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge={18: info}, monrace_knowledge={44: harmless}
        )
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(
                26, 97, level=1,
                hp=100, max_hp=100, main_hand_blows=4, main_hand_to_d=10,
            ),
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=2, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        self.assertTrue(policy._fixed_quest_ready(snapshot, 18))

    def test_fixed_quest_kill_time_counts_both_dual_wielded_weapons(self):
        info = QuestInfo(
            18, "Water Cave", 4, 35, 6, placed_monsters=((44, 1),)
        )
        target = MonraceKnowledge(
            300, 110, False, False, max_melee_damage=0
        )
        policy = HengbotPolicy(
            self._town_map(),
            quest_knowledge={18: info},
            monrace_knowledge={44: target},
        )
        snapshot = replace(
            self._town_snapshot(
                26, 97, {Position(26, 97): grid(26, 97)}, 0
            ),
            player=replace(
                player(
                    26,
                    97,
                    level=38,
                    hp=500,
                    max_hp=500,
                    main_hand_blows=2,
                    main_hand_to_h=100,
                    main_hand_to_d=10,
                ),
                sub_hand_blows=2,
                sub_hand_to_h=100,
                sub_hand_to_d=10,
            ),
            equipment=[
                item(
                    "main_hand",
                    TVAL_SWORD,
                    1,
                    is_equipment=True,
                    damage_dice_num=1,
                    damage_dice_sides=1,
                ),
                item(
                    "sub_hand",
                    TVAL_SWORD,
                    1,
                    is_equipment=True,
                    damage_dice_num=1,
                    damage_dice_sides=1,
                ),
            ],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True

        main_only = replace(
            snapshot,
            equipment=[snapshot.equipment[0]],
            player=replace(snapshot.player, sub_hand_blows=0),
        )
        self.assertFalse(policy._fixed_quest_ready(main_only, 18))
        self.assertEqual(
            policy.fixed_quest_readiness_state()["reason"],
            "toughest-kill-time",
        )

        self.assertTrue(policy._fixed_quest_ready(snapshot, 18))
        readiness = policy.fixed_quest_readiness_state()
        self.assertGreater(readiness["sub_hand_melee_output"], 0)
        self.assertEqual(
            readiness["melee_output"],
            readiness["main_hand_melee_output"]
            + readiness["sub_hand_melee_output"],
        )

    def test_fixed_quest_roster_threat_rejects_despite_level_floor(self):
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 3),))
        threat = MonraceKnowledge(100, 110, False, False, max_melee_damage=50)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge={18: info}, monrace_knowledge={44: threat}
        )
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(26, 97, level=38, hp=200, max_hp=200,
                          main_hand_blows=4, main_hand_to_d=20),
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=3, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True

        self.assertFalse(policy._fixed_quest_ready(snapshot, 18))
        self.assertEqual(policy.fixed_quest_readiness_state()["reason"], "three-turn-threat")

    def test_fixed_quest_consumables_flip_borderline_readiness(self):
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 1),))
        threat = MonraceKnowledge(100, 120, False, False, max_melee_damage=30)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge={18: info}, monrace_knowledge={44: threat}
        )
        base = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(26, 97, level=38, hp=200, max_hp=200,
                          main_hand_blows=4, main_hand_to_d=20),
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=3, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        self.assertFalse(policy._fixed_quest_ready(base, 18))

        stocked = replace(base, inventory=[
            item("s", TVAL_POTION, SV_POTION_SPEED),
            item("h", TVAL_POTION, SV_POTION_HEALING),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=2),
        ])
        self.assertTrue(policy._fixed_quest_ready(stocked, 18))
        state = policy.fixed_quest_readiness_state()
        self.assertEqual(state["hp_healing_budget"], 500)
        self.assertTrue(state["hasted"])
        self.assertTrue(state["verdict"])

    def _rand25_readiness(self, knowledge, factor, *, engagement_extra=None):
        """Run the fixed-quest readiness gate against an 8-monster roster of
        ``knowledge`` under an approved profile whose engagement plan declares
        ``random_move_damage_factor``.  Returns the readiness telemetry."""
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 8),))
        policy = HengbotPolicy(
            self._town_map(),
            quest_knowledge={18: info},
            monrace_knowledge={44: knowledge},
        )
        engagement = {"random_move_damage_factor": factor}
        if engagement_extra:
            engagement.update(engagement_extra)
        profile = StrategyProfile(
            quest_id=18,
            name={"ja": "", "en": ""},
            approved=True,
            approved_note="",
            engagement_plan=engagement,
            priority_targets=(),
            consumable_plan={},
            abort_conditions={"hp_ratio": 0.30, "allowed": True},
            required_force={"min_hp": 1, "min_expected_dps": 0, "reference_ac": 20},
            generated_by="test",
            generated_at="test",
        )
        policy.approved_quest_strategy = lambda _quest_id, _p=profile: _p
        policy._combat_weapon_ready = lambda _snapshot: True
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(26, 97, level=38, hp=200, max_hp=200,
                          main_hand_blows=4, main_hand_to_d=20),
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=3, damage_dice_sides=6)],
        )
        policy._fixed_quest_ready(snapshot, 18)
        return policy.fixed_quest_readiness_state()

    def test_random_move_damage_factor_halves_rand25_threat(self):
        rand25 = MonraceKnowledge(
            100, 110, False, False, level=14,
            max_melee_damage=50, flags=frozenset({"RAND_25"}),
        )
        full = self._rand25_readiness(rand25, 1.0)
        half = self._rand25_readiness(rand25, 0.5)
        self.assertEqual(full["random_move_damage_factor"], 1.0)
        self.assertEqual(half["random_move_damage_factor"], 0.5)
        # The RAND_25 monster's modeled melee is halved, so its three-turn
        # adjacent threat must drop.  Reverting the halving makes these equal.
        self.assertLess(half["worst_adjacent"], full["worst_adjacent"])

    def test_random_move_damage_factor_ignores_non_rand25_monster(self):
        plain = MonraceKnowledge(
            100, 110, False, False, level=14, max_melee_damage=50,
        )
        full = self._rand25_readiness(plain, 1.0)
        half = self._rand25_readiness(plain, 0.5)
        # Without the RAND_25 flag the factor must not touch the threat, so a
        # blanket (flag-agnostic) halving would fail this equality.
        self.assertEqual(half["worst_adjacent"], full["worst_adjacent"])

    def test_max_simultaneous_melee_caps_modeled_adjacency(self):
        rand25 = MonraceKnowledge(
            100, 110, False, False, level=14,
            max_melee_damage=50, flags=frozenset({"RAND_25"}),
        )
        uncapped = self._rand25_readiness(rand25, 1.0)
        capped = self._rand25_readiness(
            rand25, 1.0, engagement_extra={"max_simultaneous_melee": 4}
        )
        self.assertEqual(uncapped["simultaneous_melee"], 8)
        self.assertEqual(capped["simultaneous_melee"], 4)
        self.assertLess(capped["worst_adjacent"], uncapped["worst_adjacent"])

    def test_quest14_profile_encodes_approved_tier2_engagement(self):
        # The 2026-07-22 user-approved Tier2 intent (max 4 simultaneous melee,
        # RAND_25 damage counted at half) must live in the loaded profile, not
        # only in the prose note.  Dropping either field regresses acceptance.
        profiles = load_quest_strategies(
            Path(__file__).resolve().parents[1] / "strategy" / "quests"
        )
        q14 = profiles.get(14)
        self.assertIsNotNone(q14)
        self.assertEqual(q14.engagement_plan.get("max_simultaneous_melee"), 4)
        self.assertEqual(q14.engagement_plan.get("random_move_damage_factor"), 0.5)

    def _full_pack_quest_sweep_setup(self):
        policy = HengbotPolicy(self._town_map())
        snapshot = Snapshot(
            player(5, 5), {Position(5, 5): grid(5, 5)}, [],
            floor_key=(0, 15, 22),
            inventory=[item(f"i{n}", TVAL_POTION, 5) for n in range(30)],
        )
        # Non-light loot on the floor, so the light-defer shortcut does not apply.
        floor_grid = grid(4, 5, objects=1, object_tvals=(TVAL_SWORD,))
        # Nothing carried is disposable yet (all-unidentified pack).
        policy._full_pack_destroy_key = lambda _snapshot: None
        return policy, snapshot, floor_grid

    def test_quest_sweep_identifies_unknown_before_abandoning_full_pack_loot(self):
        policy, snapshot, floor_grid = self._full_pack_quest_sweep_setup()
        # An identify source/target is available: identify in place instead of
        # deferring the loot. (The standalone pack-pressure identify never runs
        # mid-quest, so the quest sweep must invoke it itself.)
        policy._pack_pressure_identify_key = lambda _snapshot: "uab"
        self.assertEqual(
            policy._quest_sweep_pack_space_key(snapshot, floor_grid), "uab"
        )
        self.assertEqual(policy.last_reason, "quest:sweep:identify")

    def test_quest_sweep_defers_full_pack_loot_only_when_identify_unavailable(self):
        policy, snapshot, floor_grid = self._full_pack_quest_sweep_setup()
        # No usable identify source/target: only now defer the loot.
        policy._pack_pressure_identify_key = lambda _snapshot: None
        self.assertEqual(
            policy._quest_sweep_pack_space_key(snapshot, floor_grid), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "quest:sweep:defer-full-pack-loot")

    def _identify_carry_policy(self, engagement_plan):
        policy = HengbotPolicy(self._town_map())
        policy._planned_depth = lambda: 1  # shallow: the depth gate alone waives it
        policy._total_identify_staff_charges = lambda _snapshot: 0
        policy._carry_procurement_strategy = lambda _snapshot: SimpleNamespace(
            engagement_plan=engagement_plan
        )
        snapshot = self._town_snapshot(
            26, 97, {Position(26, 97): grid(26, 97)}, 0
        )
        return policy, snapshot

    def test_loot_quest_requires_identify_staff_even_when_shallow(self):
        policy, snapshot = self._identify_carry_policy({"carry_identify_staff": True})
        # A carry-opting quest needs the staff regardless of the shallow depth.
        self.assertFalse(policy._identify_staff_ready(snapshot))

    def test_non_carry_quest_leaves_shallow_identify_staff_optional(self):
        policy, snapshot = self._identify_carry_policy({})
        # No opt-in: the depth gate still waives the staff for a shallow trip.
        self.assertTrue(policy._identify_staff_ready(snapshot))

    def test_only_q22_and_q31_opt_into_identify_staff_carry(self):
        profiles = load_quest_strategies(
            Path(__file__).resolve().parents[1] / "strategy" / "quests"
        )
        self.assertTrue(profiles[22].engagement_plan.get("carry_identify_staff"))
        self.assertTrue(profiles[31].engagement_plan.get("carry_identify_staff"))
        for qid in (1, 2, 14, 34):
            self.assertFalse(
                profiles[qid].engagement_plan.get("carry_identify_staff"), qid
            )

    def test_fixed_quest_healing_budget_is_limited_to_three_quaffs(self):
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 1),))
        harmless = MonraceKnowledge(1, 110, False, False)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge={18: info}, monrace_knowledge={44: harmless}
        )
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(26, 97, level=38, hp=200, max_hp=200,
                          main_hand_blows=4, main_hand_to_d=20),
            inventory=[item("h", TVAL_POTION, SV_POTION_HEALING, count=99)],
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=3, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True

        self.assertTrue(policy._fixed_quest_ready(snapshot, 18))
        self.assertEqual(policy.fixed_quest_readiness_state()["hp_healing_budget"], 1100)

    def test_fixed_quest_budget_excludes_outpaced_cure_critical(self):
        info = QuestInfo(18, "Water Cave", 4, 35, 6, placed_monsters=((44, 1),))
        threat = MonraceKnowledge(
            1, 110, False, False, max_melee_damage=100
        )
        policy = HengbotPolicy(
            self._town_map(),
            quest_knowledge={18: info},
            monrace_knowledge={44: threat},
        )
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(
                26, 97, level=38, hp=200, max_hp=200,
                main_hand_blows=4, main_hand_to_d=20,
            ),
            inventory=[
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=99)
            ],
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1, is_equipment=True,
                    damage_dice_num=3, damage_dice_sides=6,
                )
            ],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True

        self.assertFalse(policy._fixed_quest_ready(snapshot, 18))
        self.assertEqual(
            policy.fixed_quest_readiness_state()["hp_healing_budget"], 200
        )

    def test_kill_number_readiness_uses_q_line_roster(self):
        info = QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0, num_mon=16, monrace_id=257)
        warg = MonraceKnowledge(14, 120, False, False, max_melee_damage=1)
        policy = HengbotPolicy(self._town_map(), quest_knowledge={14: info}, monrace_knowledge={257: warg})
        snapshot = replace(
            self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
            player=player(26, 97, level=8, hp=5000, max_hp=5000, main_hand_blows=4, main_hand_to_d=30),
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True, damage_dice_num=3, damage_dice_sides=6)],
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        self.assertTrue(policy._fixed_quest_ready(snapshot, 14))
        self.assertEqual(policy.fixed_quest_readiness_state()["roster_size"], 16)

    def test_active_kill_floor_locks_healthy_exit_but_allows_teleport(self):
        info = QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0, num_mon=16, monrace_id=257)
        quest = QuestState(id=14, status=1, type=5, level=5, dungeon_id=0, r_idx=257, cur_num=3, max_num=16, num_mon=16, fixed=True)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 5, 14), quests={14: quest},
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT), item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        self.assertTrue(policy._quest_floor_exit_locked(snap))
        self.assertTrue(policy._floor_navigation_exit_locked(snap))
        self.assertIsNone(policy._escape_by_stairs(snap))
        self.assertEqual(policy._escape_scroll(snap).slot, "t")
        self.assertIsNone(policy._return_to_town_key(snap, []))

        complete = replace(snap, quests={14: replace(quest, cur_num=16)})
        self.assertFalse(policy._quest_floor_exit_locked(complete))

    def test_new_single_target_shape_without_target_or_progress_keeps_exit_lock(self):
        info = QuestInfo(
            28, "Royal Crypt", QUEST_TYPE_KILL_LEVEL, 70, QUEST_FLAG_ONCE,
            dungeon=2, max_num=1, monrace_id=999,
        )
        data = {
            "player": {"y": 10, "x": 10, "hp": 100, "max_hp": 100},
            "floor": {"dungeon_id": 2, "level": 70, "quest_id": 28},
            "progress": {"quests": [{
                "id": 28, "name": "Royal Crypt", "status": QUEST_STATUS_TAKEN,
                "type": QUEST_TYPE_KILL_LEVEL, "level": 70, "fixed": True,
            }]},
        }
        snapshot = parse_snapshot(data, {})
        policy = HengbotPolicy(quest_knowledge={28: info})

        self.assertEqual(policy._active_kill_quest_id(snapshot), 28)
        self.assertTrue(policy._quest_floor_exit_locked(snapshot))
        self.assertFalse(policy._kill_quest_descent_allowed(snapshot))

    def test_new_quest_row_shapes_join_static_facts_and_handle_progress(self):
        cases = (
            (
                "kill-number-current",
                {"id": 14, "name": "Wargs", "status": 1, "type": 5,
                 "level": 5, "fixed": True, "cur_num": 3, "max_num": 16},
                QuestInfo(14, "Wargs", 5, 5, 0, dungeon=3, num_mon=16,
                          monrace_id=257),
                257, 3, True, True,
            ),
            (
                "kill-level-current-multiple",
                {"id": 20, "name": "Pack", "status": 1, "type": 1,
                 "level": 20, "fixed": True, "r_idx": 300,
                 "cur_num": 2, "max_num": 4},
                QuestInfo(20, "Pack", 1, 20, 0, dungeon=3, max_num=4,
                          monrace_id=300),
                300, 2, True, False,
            ),
            (
                "kill-level-current-single",
                {"id": 28, "name": "Single", "status": 1, "type": 1,
                 "level": 28, "fixed": True, "r_idx": 999},
                QuestInfo(28, "Single", 1, 28, QUEST_FLAG_ONCE, dungeon=3,
                          max_num=1, monrace_id=999),
                999, None, True, False,
            ),
            (
                "random-current",
                {"id": 49, "name": "Random", "status": 1, "type": 7,
                 "level": 30, "fixed": False, "r_idx": 777},
                QuestInfo(49, "Random", 7, 30, 0, dungeon=3, max_num=1),
                777, None, True, True,
            ),
            (
                "taken-find-artifact-with-reward",
                {"id": 31, "name": "Artifact", "status": 1, "type": 3,
                 "level": 31, "fixed": True, "reward_artifact_id": 12,
                 "reward_baseitem_id": 42},
                QuestInfo(31, "Artifact", 3, 31, 0, dungeon=3),
                None, None, False, True,
            ),
            (
                "finished-random",
                {"id": 50, "name": "Finished", "status": 4, "type": 7,
                 "level": 32, "fixed": False, "r_idx": 778,
                 "complev": 33, "comptime": 1234},
                QuestInfo(50, "Finished", 7, 32, 0, dungeon=3, max_num=1),
                778, None, False, True,
            ),
            (
                "failed-random",
                {"id": 51, "name": "Failed", "status": 3, "type": 7,
                 "level": 33, "fixed": False, "r_idx": 779,
                 "complev": 34, "comptime": 2345},
                QuestInfo(51, "Failed", 7, 33, 0, dungeon=3, max_num=1),
                779, None, False, True,
            ),
        )
        for (
            name, row, info, expected_race, expected_progress,
            expected_active, expected_descent,
        ) in cases:
            with self.subTest(name=name):
                data = {
                    "player": {"y": 10, "x": 10, "hp": 100, "max_hp": 100},
                    "floor": {
                        "dungeon_id": 3, "level": info.level, "quest_id": 0,
                    },
                    "progress": {"quests": [row]},
                }
                snapshot = parse_snapshot(data, {})
                quest = snapshot.quests[info.id]
                policy = HengbotPolicy(quest_knowledge={info.id: info})
                monster = hostile(
                    1, 10, 11, hp=10, max_hp=10,
                    race_id=expected_race or 12345,
                )

                self.assertIsNone(quest.dungeon_id)
                self.assertEqual(quest.cur_num, expected_progress)
                self.assertEqual(
                    policy._quest_target_race_id(quest), expected_race,
                )
                self.assertEqual(
                    policy._active_kill_quest_id(snapshot) == info.id,
                    expected_active,
                )
                self.assertEqual(
                    policy._consumable_fight_target(snapshot, monster),
                    expected_race is not None and expected_active,
                )
                self.assertEqual(
                    policy._kill_quest_descent_allowed(snapshot),
                    expected_descent,
                )

    def test_dying_kill_quest_with_no_teleport_may_take_stairs(self):
        info = QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0, num_mon=16, monrace_id=257)
        quest = QuestState(id=14, status=1, type=5, level=5, dungeon_id=0, r_idx=257, cur_num=3, max_num=16, num_mon=16, fixed=True)
        snap = Snapshot(
            player(10, 10, hp=10, max_hp=100),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 5, 14), quests={14: quest},
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        self.assertFalse(policy._quest_floor_exit_locked(snap))
        self.assertEqual(policy._escape_by_stairs(snap), "<")

    def test_non_once_kill_quest_releases_after_stuck_budget(self):
        info = QuestInfo(14, "Warg Problem", 5, 5, 2, dungeon=0, num_mon=16, monrace_id=257)
        quest = QuestState(id=14, status=1, type=5, level=5, dungeon_id=0, cur_num=15, max_num=16, num_mon=16, fixed=True)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 5, 14), quests={14: quest},
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        self.assertFalse(policy._quest_floor_exit_locked(snap))
        self.assertEqual(policy._escape_by_stairs(snap), "<")

    def test_once_kill_level_only_releases_when_dying_without_teleport(self):
        info = QuestInfo(28, "Royal Crypt", 1, 70, QUEST_FLAG_ONCE, dungeon=0, max_num=1, monrace_id=999)
        quest = QuestState(id=28, status=1, type=1, level=70, dungeon_id=0, cur_num=0, max_num=1, fixed=True)
        healthy = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 70, 28), quests={28: quest},
        )
        policy = HengbotPolicy(quest_knowledge={28: info})
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        self.assertTrue(policy._quest_floor_exit_locked(healthy))
        dying = replace(healthy, player=player(10, 10, hp=10, max_hp=100))
        self.assertTrue(policy._kill_quest_exit_would_fail(dying))
        self.assertFalse(policy._quest_floor_exit_locked(dying))
        self.assertEqual(policy._escape_by_stairs(dying), "<")

    def test_kill_level_completion_uses_max_num_not_nonzero_num_mon(self):
        info = QuestInfo(28, "Royal Crypt", 1, 70, QUEST_FLAG_ONCE, dungeon=0, num_mon=99, max_num=1, monrace_id=999)
        quest = QuestState(id=28, status=1, type=1, cur_num=1, max_num=1, num_mon=99)
        snap = Snapshot(player(10, 10), {}, [], floor_key=(0, 70, 28), quests={28: quest})
        self.assertIsNone(HengbotPolicy(quest_knowledge={28: info})._active_kill_quest_id(snap))

    def test_kill_number_uses_num_mon_when_max_num_is_zero(self):
        quest = QuestState(
            id=14, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_KILL_NUMBER,
            level=5, dungeon_id=0, cur_num=15, num_mon=16, max_num=0,
        )
        snap = Snapshot(
            player(10, 10), {}, [], floor_key=(0, 5, 14),
            quests={14: quest},
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._active_kill_quest_id(snap), 14)
        self.assertTrue(policy._quest_floor_exit_locked(snap))
        self.assertIsNone(policy._active_kill_quest_id(
            replace(snap, quests={14: replace(quest, cur_num=16)})
        ))

    def test_runtime_random_quest_locks_floor_exit_without_static_knowledge(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=6, dungeon_id=1, cur_num=0, max_num=1,
        )
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(1, 6, 49), quests={49: quest},
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        policy = HengbotPolicy()

        self.assertEqual(policy._active_kill_quest_id(snap), 49)
        self.assertTrue(policy._quest_floor_exit_locked(snap))
        self.assertIsNone(policy._return_to_town_key(snap, []))
        self.assertIsNone(policy._escape_by_stairs(snap))

    def test_deepest_random_quest_with_empty_escape_kit_reads_recall(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=24, dungeon_id=DUNGEON_ANGBAND, cur_num=0, max_num=1,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_ANGBAND, 24, 49),
            dungeon_recall_depths={DUNGEON_ANGBAND: 24},
            quests={49: quest},
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=7),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            ],
        )
        policy = HengbotPolicy()

        with patch.object(policy, "_missing_required_abilities", return_value=()):
            self.assertEqual(policy.choose_key(snap), READ_KEY + "r")
        self.assertEqual(policy._last_return_trigger, "escape-kit-empty")
        self.assertEqual(policy.last_reason, "return:recall")

    def test_deepest_random_quest_with_teleport_keeps_exit_locked(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=24, dungeon_id=DUNGEON_ANGBAND, cur_num=0, max_num=1,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_ANGBAND, 24, 49),
            dungeon_recall_depths={DUNGEON_ANGBAND: 24},
            quests={49: quest},
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=7),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=1),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            ],
        )
        policy = HengbotPolicy()

        self.assertTrue(policy._quest_floor_exit_locked(snap))
        with patch.object(policy, "_missing_required_abilities", return_value=()):
            self.assertNotEqual(policy.choose_key(snap), READ_KEY + "r")
        self.assertNotEqual(policy.last_reason, "return:recall")

    def test_runtime_random_quest_lock_releases_when_complete_or_off_floor(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=6, dungeon_id=1, cur_num=0, max_num=1,
        )
        snap = Snapshot(
            player(10, 10), {}, [], floor_key=(1, 6, 49),
            quests={49: quest},
        )
        policy = HengbotPolicy()

        self.assertFalse(policy._quest_floor_exit_locked(
            replace(snap, quests={49: replace(quest, cur_num=1)})
        ))
        self.assertFalse(policy._quest_floor_exit_locked(
            replace(snap, floor_key=(1, 7, 0))
        ))

    def test_runtime_random_quest_panic_release_survives(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=6, dungeon_id=1, cur_num=0, max_num=1,
        )
        snap = Snapshot(
            player(10, 10, hp=10, max_hp=100), {}, [],
            floor_key=(1, 6, 49), quests={49: quest},
        )

        self.assertFalse(HengbotPolicy()._quest_floor_exit_locked(snap))

    def test_runtime_random_quest_releases_after_stuck_budget(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=6, dungeon_id=1, cur_num=0, max_num=1,
        )
        snap = Snapshot(
            player(10, 10), {}, [], floor_key=(1, 6, 49),
            quests={49: quest},
        )
        policy = HengbotPolicy()
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT

        self.assertFalse(policy._quest_floor_exit_locked(snap))

    def test_statically_known_random_quest_releases_after_stuck_budget(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=6, dungeon_id=1, r_idx=777, cur_num=0, max_num=1,
        )
        info = QuestInfo(
            49, "Random quest", QUEST_TYPE_RANDOM, 6, 0,
            dungeon=1, max_num=1, monrace_id=777,
        )
        snap = Snapshot(
            player(10, 10), {}, [], floor_key=(1, 6, 49),
            quests={49: quest},
        )
        policy = HengbotPolicy(quest_knowledge={49: info})
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT

        self.assertTrue(policy._kill_quest_exit_would_fail(snap))
        self.assertFalse(policy._quest_floor_exit_locked(snap))

    def test_random_quest_remains_locked_below_consecutive_stuck_budget(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=6, dungeon_id=1, r_idx=777, cur_num=0, max_num=1,
        )
        snap = Snapshot(
            player(10, 10), {}, [], floor_key=(1, 6, 49),
            quests={49: quest},
        )
        policy = HengbotPolicy()
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1

        self.assertTrue(policy._quest_floor_exit_locked(snap))

    def test_locked_random_quest_melees_visible_quest_race_first(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=6, dungeon_id=1, r_idx=777, cur_num=0, max_num=1,
        )
        bystander = hostile(1, 9, 10, hp=1, max_hp=1, race_id=111)
        target = hostile(2, 10, 11, hp=10, max_hp=10, race_id=777)
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {
                Position(10, 10): grid(10, 10),
                Position(9, 10): grid(9, 10, monster=True),
                Position(10, 11): grid(10, 11, monster=True),
            },
            [bystander, target],
            floor_key=(1, 6, 49),
            quests={49: quest},
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_locked_random_quest_pursues_visible_quest_race(self):
        quest = QuestState(
            id=49, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_RANDOM,
            level=6, dungeon_id=1, r_idx=777, cur_num=0, max_num=1,
        )
        target = hostile(
            2, 10, 12, hp=10, max_hp=10, distance=2, race_id=777
        )
        snap = Snapshot(
            player(10, 10, hp=100, max_hp=100),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, monster=True),
            },
            [target],
            floor_key=(1, 6, 49),
            quests={49: quest},
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "hunt:quest-target")

    def test_descent_guard_selects_kill_quest_in_current_dungeon(self):
        other = QuestInfo(14, "Other", 5, 3, 0, dungeon=1, num_mon=16)
        current = QuestInfo(28, "Current", 1, 5, 0, dungeon=2, max_num=1)
        quests = {
            14: QuestState(id=14, status=0),
            28: QuestState(id=28, status=0),
        }
        snap = Snapshot(
            player(10, 10, class_id=-1),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [], floor_key=(2, 5, 0), quests=quests,
        )
        policy = HengbotPolicy(quest_knowledge={14: other, 28: current})
        self.assertFalse(policy._is_descent_target(snap, snap.grids[Position(10, 10)]))

    def test_real_lib_fixed_quest_rosters_25_and_28_run_through_readiness(self):
        edit = Path(r"C:\hengband\lib\edit")
        quest_path = REAL_QUEST_DEFINITIONS
        monrace_path = edit / "MonraceDefinitions.jsonc"
        if quest_path is None or not monrace_path.is_file():
            self.skipTest("real Hengband lib/edit is not available")
        quests = load_quest_knowledge(quest_path)
        monraces = load_monrace_knowledge(monrace_path)
        policy = HengbotPolicy(
            self._town_map(), quest_knowledge=quests, monrace_knowledge=monraces
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True
        for quest_id in (25, 28):
            with self.subTest(quest_id=quest_id):
                snapshot = replace(
                    self._town_snapshot(26, 97, {Position(26, 97): grid(26, 97)}, 0),
                    player=player(
                        26, 97, level=1,
                        hp=100000, max_hp=100000, main_hand_blows=10,
                        main_hand_to_d=100000,
                    ),
                    equipment=[item(
                        "main_hand", TVAL_SWORD, 1, is_equipment=True,
                        damage_dice_num=10, damage_dice_sides=10,
                    )],
                )
                self.assertTrue(policy._fixed_quest_ready(snapshot, quest_id))

    def test_fixed_quest_quaffs_speed_once_on_first_engagement(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snapshot = replace(
            self._town_snapshot(10, 10, grids, 1),
            player=player(10, 10, hp=100, max_hp=100, level=8,
                          main_hand_blows=2, main_hand_to_d=10),
            inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                            damage_dice_num=2, damage_dice_sides=6)],
            visible_monsters=[hostile(1, 10, 11, hp=10, max_melee_damage=1)],
            floor_key=(0, 0, self.QUEST_ID),
            town_flag=False,
            town_id=-1,
        )
        policy = HengbotPolicy(self._town_map())

        self.assertEqual(policy.choose_key(snapshot), "qs")
        self.assertEqual(policy.last_reason, "quest:quaff-speed")
        self.assertNotEqual(policy.choose_key(snapshot), "qs")

        not_once = QuestInfo(1, "Thieves Hideout", 6, 5, 2)
        policy = HengbotPolicy(self._town_map(), quest_knowledge={1: not_once})
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        original = self._town_snapshot(
            26, 97, {Position(26, 97): grid(26, 97, building_special=1)}, 0
        )
        self.assertEqual(policy._fixed_quest_target(original), 1)

    def test_non_once_fixed_quest_allows_recoverable_floor_exit(self):
        info = QuestInfo(1, "Repeatable Hideout", 6, 5, 2)
        quest = self._quest(1)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [], floor_key=(0, 1, 1), quests={1: quest},
        )
        policy = HengbotPolicy(quest_knowledge={1: info})
        policy._returning_to_town = True

        self.assertEqual(policy._active_fixed_quest_id(snap), 1)
        self.assertEqual(policy._return_to_town_key(snap, []), "<")
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_selects_lowest_level_eligible_untaken_quest(self):
        quest18 = replace(self._quest(0), id=18, level=35)
        quest25 = replace(self._quest(0), id=25, level=48)
        knowledge = {
            18: QuestInfo(18, "Water Cave", 4, 35, 6),
            25: QuestInfo(25, "Haunted House", 6, 48, 6),
        }
        policy = HengbotPolicy(self._town_map(), quest_knowledge=knowledge)
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        snapshot = replace(
            self._town_snapshot(
                26, 97,
                {
                    Position(26, 98): grid(26, 98, building_special=18),
                    Position(30, 40): grid(30, 40, building_special=25),
                },
                0,
            ),
            quests={25: quest25, 18: quest18},
        )

        self.assertEqual(policy._fixed_quest_target(snapshot), 18)

    def test_existing_taken_kill_quest_is_selected_before_new_acceptance(self):
        quest14 = replace(self._quest(1), id=14, level=5, flags=2)
        quest18 = replace(self._quest(0), id=18, level=35)
        knowledge = {
            14: QuestInfo(14, "Warg Problem", 1, 5, 2),
            18: QuestInfo(18, "Water Cave", 4, 35, 6),
        }
        policy = HengbotPolicy(self._town_map(), quest_knowledge=knowledge)
        policy._fixed_quest_ready = lambda _snapshot, _quest_id: True
        snapshot = replace(
            self._town_snapshot(26, 97, {}, 0),
            quests={18: quest18, 14: quest14},
        )

        self.assertEqual(policy._fixed_quest_target(snapshot), 14)

    def test_generalized_castle_quest_claim_latches_shared_reward_tile(self):
        quest_id = 18
        quest = replace(self._quest(2), id=quest_id, level=35)
        town_map = replace(
            self._town_map(),
            quest_buildings={quest_id: frozenset({Position(26, 98)})},
        )
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(
                26, 98, building_type=1, building_special=quest_id
            ),
        }
        snapshot = replace(
            self._town_snapshot(26, 97, grids, 2),
            quests={quest_id: quest},
        )
        policy = HengbotPolicy(town_map)

        self.assertEqual(policy.choose_key(snapshot), "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:claim")
        self.assertEqual(policy._fixed_quest_reward_pending, quest_id)
        self.assertEqual(
            policy._fixed_quest_reward_positions(snapshot, quest_id),
            frozenset({Position(27, 98)}),
        )

    def test_enters_taken_fixed_quest_from_visible_entrance(self):
        grids = {
            Position(35, 176): grid(35, 176),
            Position(35, 177): grid(
                35, 177, has_quest_enter=True, quest_id=self.QUEST_ID
            ),
        }
        policy = HengbotPolicy(self._town_map())

        key = policy.choose_key(self._town_snapshot(35, 176, grids, 1))

        self.assertEqual(key, "6y")
        self.assertEqual(policy.last_reason, "fixedquest:enter")

    def test_taken_q1_approach_does_not_enter_dead_end_town_loop(self):
        origin = Position(26, 109)
        entrance = Position(35, 177)
        northeast_detour = {
            Position(25, x) for x in range(110, entrance.x + 1)
        } | {
            Position(y, entrance.x) for y in range(25, entrance.y + 1)
        }
        town_map = replace(
            self._town_map(),
            walkable=frozenset(northeast_detour),
        )
        grids = {
            origin: grid(origin.y, origin.x),
            Position(27, 110): grid(27, 110),
            entrance: grid(
                entrance.y,
                entrance.x,
                has_quest_enter=True,
                quest_id=self.QUEST_ID,
            ),
        }
        policy = HengbotPolicy(town_map)
        policy._quest_equipment_entry_allowed = lambda *_args, **_kwargs: True

        position = origin
        visited = {position}
        offsets = {
            "7": (-1, -1),
            "8": (-1, 0),
            "9": (-1, 1),
            "4": (0, -1),
            "6": (0, 1),
            "1": (1, -1),
            "2": (1, 0),
            "3": (1, 1),
        }
        for _ in range(120):
            key = policy.choose_key(
                self._town_snapshot(
                    position.y, position.x, grids, QUEST_STATUS_TAKEN
                )
            )
            if position == entrance:
                self.assertEqual(key, ">y")
                break
            dy, dx = offsets[key[0]]
            position = Position(position.y + dy, position.x + dx)
            self.assertNotIn(position, visited)
            visited.add(position)
        else:
            self.fail("quest entrance was not reached")

        self.assertEqual(position, entrance)

    def test_taken_q1_approach_prefers_viable_southeast_route(self):
        origin = Position(26, 109)
        entrance = Position(35, 177)
        northeast_detour = {
            Position(25, x) for x in range(110, entrance.x + 1)
        } | {
            Position(y, entrance.x) for y in range(25, entrance.y + 1)
        }
        southeast_route = {
            Position(y, 110) for y in range(27, entrance.y + 1)
        } | {
            Position(entrance.y, x) for x in range(110, entrance.x + 1)
        }
        town_map = replace(
            self._town_map(),
            walkable=frozenset(northeast_detour | southeast_route),
        )
        grids = {
            origin: grid(origin.y, origin.x),
            entrance: grid(
                entrance.y,
                entrance.x,
                has_quest_enter=True,
                quest_id=self.QUEST_ID,
            ),
        }
        policy = HengbotPolicy(town_map)

        key = policy.choose_key(
            self._town_snapshot(origin.y, origin.x, grids, QUEST_STATUS_TAKEN)
        )

        self.assertEqual(key, "3")
        self.assertEqual(policy.last_reason, "fixedquest:approach")

    def test_claims_completed_fixed_quest_and_latches_reward(self):
        grids = {
            Position(26, 97): grid(26, 97),
            Position(26, 98): grid(26, 98, building_type=1, building_special=1),
        }
        policy = HengbotPolicy(self._town_map())

        key = policy.choose_key(self._town_snapshot(26, 97, grids, 2))

        self.assertEqual(key, "6q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:claim")
        self.assertEqual(policy._fixed_quest_reward_pending, self.QUEST_ID)

    def test_completed_fixed_quest_floor_heads_for_upstairs(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(
                10, 11, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            ),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(2)},
        )
        policy = HengbotPolicy()

        key = policy.choose_key(snap)

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "fixedquest:seek-exit")

    def test_pack_full_taken_quest_does_not_route_to_exit(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(
                10, 11, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            ),
        }
        inventory = [item(chr(ord("a") + i), 1, i) for i in range(PACK_CAPACITY)]
        snap = Snapshot(
            player(10, 10),
            grids,
            inventory,
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(1)},
        )
        policy = HengbotPolicy()

        key = policy._return_to_town_key(snap, [])

        self.assertIsNone(key)
        self.assertFalse(policy._returning_to_town)

    def test_completed_quest_leaves_from_quest_exit(self):
        grids = {
            Position(10, 10): grid(
                10, 10, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            )
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(2)},
        )
        policy = HengbotPolicy()

        key = policy.choose_key(snap)

        self.assertEqual(key, "<")
        self.assertEqual(policy.last_reason, "fixedquest:exit")

    def test_collects_pending_fixed_quest_reward_from_reward_tile(self):
        grids = {
            Position(27, 97): grid(27, 97),
            Position(27, 98): grid(27, 98, objects=1),
        }
        policy = HengbotPolicy(self._town_map(reward=True))
        policy._fixed_quest_reward_pending = self.QUEST_ID

        key = policy.choose_key(self._town_snapshot(27, 97, grids, 3))

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "fixedquest:reward-approach")

        policy._floor_key = (0, 0, 0)
        policy._last_position = Position(27, 97)
        pickup = self._town_snapshot(27, 98, grids, 3)
        key = policy.choose_key(pickup)

        self.assertEqual(key, "g")
        self.assertEqual(policy.last_reason, "fixedquest:reward-pickup")

        policy._floor_key = (0, 0, 0)
        policy._last_position = Position(27, 98)
        empty_grids = {
            Position(27, 97): grid(27, 97),
            Position(27, 98): grid(27, 98),
        }
        empty = self._town_snapshot(27, 98, empty_grids, 3)
        self.assertIsNone(policy._fixed_quest_key(empty, []))
        self.assertIsNone(policy._fixed_quest_reward_pending)
        self.assertIsNone(policy._fixed_quest_key(empty, []))

    def test_pending_fixed_quest_reward_retries_deferred_reward_tile(self):
        reward_position = Position(27, 98)
        grids = {reward_position: grid(27, 98, objects=1)}
        policy = HengbotPolicy(self._town_map(reward=True))
        policy._fixed_quest_reward_pending = self.QUEST_ID
        policy._deferred_loot.add(reward_position)

        key = policy.choose_key(self._town_snapshot(27, 98, grids, 3))

        self.assertEqual(key, "g")
        self.assertEqual(policy.last_reason, "fixedquest:reward-pickup")
        self.assertNotIn(reward_position, policy._deferred_loot)
        self.assertNotEqual(policy.last_reason, "fixedquest:reward-approach")

    def test_emergency_upstairs_reason_records_quest_failure(self):
        grids = {
            Position(10, 10): grid(
                10, 10, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            ),
            Position(10, 11): grid(10, 11),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(1)},
        )
        policy = HengbotPolicy()
        policy._emergency_escape_pending = True

        key = policy._emergency_item(snap, [])

        self.assertEqual(key, "<")
        self.assertEqual(policy.last_reason, "emergency:stairs-quest-fail")

class Q22Q31StrategyExecutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = load_quest_strategies(Path("strategy/quests"))

    def test_user_approved_strategies_are_executable(self):
        policy = HengbotPolicy(quest_strategies=self.profiles)

        self.assertIsNotNone(policy.approved_quest_strategy(22))
        self.assertIsNotNone(policy.approved_quest_strategy(31))

    def test_q22_approved_draft_routes_by_inn_to_angwil(self):
        profile = replace(self.profiles[22], approved=True)
        quest = QuestState(22, status=QUEST_STATUS_UNTAKEN, fixed=True, level=15)
        snapshot = Snapshot(
            player(
                10,
                10,
                hp=100,
                max_hp=100,
                gold=1000,
                main_hand_blows=4,
                main_hand_to_d=10,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0), town_flag=True, town_id=0,
            quests={22: quest},
            visited_town_ids=(0, 3),
            equipment=[
                item(
                    "main_hand",
                    TVAL_SWORD,
                    1,
                    is_equipment=True,
                    damage_dice_num=2,
                    damage_dice_sides=6,
                )
            ],
        )
        policy = HengbotPolicy(
            quest_strategies={22: profile},
            quest_knowledge={
                22: QuestInfo(
                    22,
                    "Orc Camp",
                    6,
                    15,
                    6,
                    placed_monsters=((44, 1),),
                )
            },
            monrace_knowledge={44: MonraceKnowledge(1, 110, False, False)},
        )

        with patch.object(
            policy, "_approved_strategy_force_ready", return_value=True
        ), patch.object(
            policy, "_combat_weapon_ready", return_value=True
        ), patch.object(
            policy, "_town_teleport_key", return_value="TO-ANGWIL"
        ) as travel:
            self.assertFalse(policy._fixed_quest_ready(snapshot, 22))
            self.assertTrue(policy._fixed_quest_ready_for_travel(snapshot, 22))
            self.assertEqual(policy._fixed_quest_key(snapshot, []), "TO-ANGWIL")

        travel.assert_called_once_with(snapshot, 3)

    def test_q22_and_q31_reward_tiles_are_dedicated(self):
        policy = HengbotPolicy()
        q22 = Snapshot(
            player(31, 98), {Position(31, 98): grid(31, 98)}, [],
            floor_key=(0, 0, 0), town_flag=True, town_id=3,
        )
        q31 = replace(q22, player=player(36, 118), town_id=0)

        self.assertEqual(
            policy._fixed_quest_reward_positions(q22, 22),
            frozenset({Position(31, 99)}),
        )
        self.assertEqual(
            policy._fixed_quest_reward_positions(q31, 31),
            frozenset({Position(36, 119)}),
        )

    def test_q22_reward_preempts_q31_travel_and_reconstructs_after_restart(self):
        reward = Position(31, 99)
        snapshot = Snapshot(
            player(31, 98, gold=5000),
            {
                Position(31, 98): grid(31, 98),
                reward: grid(31, 99, objects=1),
            },
            [], floor_key=(0, 0, 0), town_flag=True, town_id=3,
            quests={
                22: QuestState(
                    22, status=QUEST_STATUS_FINISHED, fixed=True, level=15
                ),
                2: QuestState(
                    2, status=QUEST_STATUS_FINISHED, fixed=True, level=15
                ),
                31: QuestState(
                    31, status=QUEST_STATUS_UNTAKEN, fixed=True, level=25
                ),
            },
            visited_town_ids=(0, 1, 3),
        )
        policy = HengbotPolicy(quest_strategies=self.profiles)

        with patch.object(
            policy, "_town_map_goal_step", return_value=reward
        ), patch.object(
            policy, "_town_teleport_key", return_value="WRONG-Q31-TRAVEL"
        ) as travel:
            self.assertEqual(policy._fixed_quest_key(snapshot, []), "6")

        travel.assert_not_called()
        self.assertEqual(policy._fixed_quest_reward_pending, 22)
        self.assertEqual(policy.last_reason, "fixedquest:reward-approach")

    def test_q22_starts_placement_sweep_only_after_hold_gate(self):
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 7)},
            monster_placements=(((1, 6), 118),),
            entrance=(1, 1), exit=(1, 1),
        )
        profile = replace(
            self.profiles[22],
            approved=True,
            engagement_plan={
                **self.profiles[22].engagement_plan,
                "hold_position": [1, 1],
                "initial_hold_turns": 2,
            },
        )
        policy = HengbotPolicy(
            quest_strategies={22: profile},
            quest_knowledge={
                22: QuestInfo(22, "Orc Camp", 6, 15, 6, battlefield=battlefield)
            },
            monrace_knowledge={118: MonraceKnowledge(64, 110, False, False)},
        )
        snapshot = Snapshot(
            player(1, 1), {Position(1, 1): grid(1, 1)}, [],
            floor_key=(0, 15, 22),
        )

        self.assertEqual(policy._approved_quest_strategy_key(snapshot, [], []), WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "quest-strategy:hold"
        )
        self.assertEqual(policy._approved_quest_strategy_key(snapshot, [], []), WAIT_KEY)
        self.assertEqual(policy._approved_quest_strategy_key(snapshot, [], []), "6")
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")

    def test_q22_reads_light_at_first_reveal_after_two_sweep_steps(self):
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 7)},
            monster_placements=(((1, 6), 118),),
            entrance=(1, 1), exit=(1, 1),
        )
        profile = replace(
            self.profiles[22],
            approved=True,
            engagement_plan={
                **self.profiles[22].engagement_plan,
                "hold_position": [1, 1],
                "initial_hold_turns": 1,
                "post_wave_light_steps": 2,
            },
        )
        policy = HengbotPolicy(
            quest_strategies={22: profile},
            quest_knowledge={
                22: QuestInfo(22, "Orc Camp", 6, 15, 6, battlefield=battlefield)
            },
            monrace_knowledge={118: MonraceKnowledge(64, 110, False, False)},
        )

        def at(x):
            return Snapshot(
                player(1, x),
                {Position(1, cell): grid(1, cell) for cell in range(1, 7)},
                [], floor_key=(0, 15, 22),
                inventory=[item("l", TVAL_SCROLL, SV_SCROLL_LIGHT)],
            )

        self.assertEqual(policy._approved_quest_strategy_key(at(1), [], []), WAIT_KEY)
        self.assertEqual(policy._approved_quest_strategy_key(at(1), [], []), "6")
        self.assertEqual(policy._approved_quest_strategy_key(at(2), [], []), "6")
        revealed_wave = hostile(2, 1, 5)
        self.assertEqual(
            policy._approved_quest_strategy_key(
                at(3), [revealed_wave], []
            ),
            "rl",
        )
        self.assertEqual(policy.last_reason, "quest-strategy:post-wave-light")
        self.assertEqual(policy._approved_quest_strategy_key(at(3), [], []), "6")

        # A later mobile wave must not reset the one-time opening gate.  Once
        # Light has been used, quiet turns resume the battlefield sweep directly.
        later_wave = hostile(3, 1, 5)
        policy._approved_quest_strategy_key(
            at(3), [later_wave], []
        )
        self.assertEqual(policy._approved_quest_strategy_key(at(3), [], []), "6")
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")

    def _q22_exhausted_sweep_policy(self):
        """Q22 policy primed to the moment the placement sweep is exhausted:
        opening hold complete, every placement confirmed empty, and the final
        sweep round reached — the state that used to freeze on WAIT_KEY because
        the mobile orcs had wandered off their placements."""
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 7)},
            monster_placements=(((1, 6), 118),),
            entrance=(1, 1), exit=(1, 1),
        )
        profile = replace(
            self.profiles[22],
            approved=True,
            engagement_plan={
                **self.profiles[22].engagement_plan,
                "hold_position": [1, 1],
                "max_sweep_rounds": 3,
            },
        )
        policy = HengbotPolicy(
            quest_strategies={22: profile},
            quest_knowledge={
                22: QuestInfo(22, "Orc Camp", 6, 15, 6, battlefield=battlefield)
            },
            monrace_knowledge={118: MonraceKnowledge(64, 110, False, False)},
        )
        policy._quest_strategy_initial_hold_turns[22] = 999
        policy._quest_strategy_surveyed_placements[22] = {Position(1, 6)}
        policy._quest_strategy_sweep_rounds[22] = 2
        snapshot = Snapshot(
            player(1, 1), {Position(1, 1): grid(1, 1)}, [],
            floor_key=(0, 15, 22),
        )
        policy._build_grid_index(snapshot)
        return policy, snapshot

    def test_q22_exhausted_placement_sweep_explores_for_strayed_targets(self):
        policy, snapshot = self._q22_exhausted_sweep_policy()
        # A reachable frontier exists: the exhausted sweep must MOVE to hunt the
        # strayed orcs, not freeze on WAIT_KEY.
        policy._explore_step = lambda _snapshot: Position(1, 2)
        key = policy._approved_quest_strategy_key(snapshot, [], [])
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep-explore")
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(key, self._direction_key_for(policy, snapshot, Position(1, 2)))

    def test_q22_exhausted_sweep_waits_only_when_no_frontier_remains(self):
        policy, snapshot = self._q22_exhausted_sweep_policy()
        # Fully-explored floor, no frontier: degrade to the loop-guarded wait.
        policy._explore_step = lambda _snapshot: None
        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "quest:blocked:placement-sweep-exhausted")

    @staticmethod
    def _direction_key_for(policy, snapshot, step):
        return policy._step_toward(snapshot, step)

    def test_q31_reads_light_only_after_opening_rush_settles(self):
        battlefield = QuestBattlefield(
            terrain={(18, 1): "floor", (17, 1): "floor"},
            monster_placements=(((17, 1), 343),),
            entrance=(18, 1), exit=(18, 1),
        )
        profile = replace(
            self.profiles[31],
            approved=True,
            engagement_plan={
                **self.profiles[31].engagement_plan,
                "hold_position": [18, 1],
                "initial_hold_turns": 1,
                "post_wave_light_steps": 0,
            },
        )
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            quest_knowledge={
                31: QuestInfo(
                    31, "Old Man Willow Quest", 6, 22, 6,
                    battlefield=battlefield,
                )
            },
            monrace_knowledge={343: MonraceKnowledge(200, 120, False, False)},
        )

        def at_hold(monsters):
            return Snapshot(
                player(18, 1),
                {Position(18, 1): grid(18, 1)},
                monsters,
                floor_key=(0, 22, 31),
                inventory=[item("l", TVAL_SCROLL, SV_SCROLL_LIGHT)],
            )

        rushing = hostile(1, 17, 1)
        self.assertNotEqual(
            policy._approved_quest_strategy_key(
                at_hold([rushing]), [rushing], [rushing]
            ),
            "rl",
        )
        self.assertEqual(
            policy._approved_quest_strategy_key(at_hold([]), [], []), WAIT_KEY
        )
        self.assertEqual(
            policy._approved_quest_strategy_key(at_hold([]), [], []), "rl"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:post-wave-light")

    def test_q31_opening_hold_uses_speed_instead_of_generic_teleport(self):
        profile = replace(
            self.profiles[31],
            approved=True,
            engagement_plan={
                **self.profiles[31].engagement_plan,
                "hold_position": [18, 1],
                "initial_hold_turns": 60,
                "max_simultaneous_melee": 3,
            },
        )
        policy = HengbotPolicy(quest_strategies={31: profile})
        enemies = [
            replace(hostile(1, 17, 1, distance=1), race_id=343),
            replace(hostile(2, 17, 2, distance=1), race_id=339),
            replace(hostile(3, 16, 1, distance=2), race_id=205),
        ]
        snapshot = Snapshot(
            player(18, 1, hp=400, max_hp=585),
            {
                Position(18, 1): grid(18, 1),
                Position(17, 1): grid(17, 1, monster=True),
                Position(17, 2): grid(17, 2, monster=True),
                Position(16, 1): grid(16, 1, monster=True),
            },
            enemies,
            floor_key=(0, 22, 31),
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )

        with (
            patch.object(policy, "_unique_combat_consumable", return_value=None),
            patch.object(
                policy,
                "_predicted_damage",
                side_effect=lambda *_args, **kwargs: (
                    156 if kwargs.get("expected") else 511
                ),
            ),
            patch.object(
                policy,
                "threat_prediction",
                return_value={"operational_total": 511},
            ),
        ):
            self.assertEqual(
                policy._emergency_item(snapshot, enemies),
                "qs",
            )
        self.assertEqual(policy.last_reason, "quest-strategy:quaff-speed")

    def test_q31_opening_hold_heals_before_generic_teleport(self):
        profile = replace(
            self.profiles[31],
            approved=True,
            engagement_plan={
                **self.profiles[31].engagement_plan,
                "hold_position": [18, 1],
                "initial_hold_turns": 60,
                "max_simultaneous_melee": 3,
            },
        )
        policy = HengbotPolicy(quest_strategies={31: profile})
        enemies = [
            replace(hostile(1, 17, 1, distance=1), race_id=343),
            replace(hostile(2, 17, 2, distance=1), race_id=339),
            replace(hostile(3, 16, 1, distance=2), race_id=205),
        ]
        snapshot = Snapshot(
            player(18, 1, hp=200, max_hp=585),
            {
                Position(18, 1): grid(18, 1),
                Position(17, 1): grid(17, 1, monster=True),
                Position(17, 2): grid(17, 2, monster=True),
                Position(16, 1): grid(16, 1, monster=True),
            },
            enemies,
            floor_key=(0, 22, 31),
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )

        with (
            patch.object(policy, "_unique_combat_consumable", return_value=None),
            patch.object(
                policy,
                "_predicted_damage",
                side_effect=lambda *_args, **kwargs: (
                    156 if kwargs.get("expected") else 511
                ),
            ),
            patch.object(
                policy,
                "threat_prediction",
                return_value={"operational_total": 511},
            ),
        ):
            self.assertEqual(policy._emergency_item(snapshot, enemies), "qs")
            self.assertEqual(policy.last_reason, "quest-strategy:quaff-speed")
            self.assertEqual(policy._emergency_item(snapshot, enemies), "qh")
        self.assertEqual(policy.last_reason, "quest-strategy:opening-heal")

    def test_q31_stationary_sweep_does_not_recall_at_full_hp(self):
        profile = replace(
            self.profiles[31],
            approved=True,
            engagement_plan={
                **self.profiles[31].engagement_plan,
                "max_simultaneous_melee": 3,
            },
            abort_conditions={"allowed": True, "hp_ratio": 0.25},
        )
        stationary = MonraceKnowledge(
            100, 110, False, False, flags=frozenset({"NEVER_MOVE"})
        )
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            monrace_knowledge={206: stationary, 329: stationary},
        )
        policy._fixed_quest_speed_attempted = True
        enemies = [
            replace(hostile(1, 8, 14, distance=5), race_id=329),
            replace(hostile(2, 6, 6, distance=3), race_id=329),
            replace(hostile(3, 5, 7, distance=2), race_id=206),
            replace(hostile(4, 4, 2, distance=7), race_id=329),
            replace(hostile(5, 5, 10, distance=1), race_id=329),
        ]
        snapshot = Snapshot(
            player(4, 9, hp=414, max_hp=414),
            {Position(4, 9): grid(4, 9)},
            enemies,
            floor_key=(0, 22, 31),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )

        with (
            patch.object(policy, "_unique_combat_consumable", return_value=None),
            patch.object(
                policy,
                "_predicted_damage",
                side_effect=lambda *_args, **kwargs: (
                    154 if kwargs.get("expected") else 893
                ),
            ),
        ):
            self.assertIsNone(policy._emergency_item(snapshot, enemies))

    def test_q31_stationary_sweep_can_recall_at_abort_threshold(self):
        profile = replace(
            self.profiles[31],
            approved=True,
            engagement_plan={
                **self.profiles[31].engagement_plan,
                "max_simultaneous_melee": 3,
            },
            abort_conditions={"allowed": True, "hp_ratio": 0.25},
        )
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            monrace_knowledge={
                329: MonraceKnowledge(
                    100, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                )
            },
        )
        policy._fixed_quest_speed_attempted = True
        enemy = replace(hostile(1, 5, 10, distance=1), race_id=329)
        snapshot = Snapshot(
            player(4, 9, hp=100, max_hp=414),
            {Position(4, 9): grid(4, 9)},
            [enemy],
            floor_key=(0, 22, 31),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
            quests={
                31: QuestState(
                    31, status=QUEST_STATUS_TAKEN, fixed=True
                )
            },
        )

        with (
            patch.object(policy, "_unique_combat_consumable", return_value=None),
            patch.object(policy, "_predicted_damage", return_value=893),
        ):
            self.assertEqual(policy._emergency_item(snapshot, [enemy]), "rr")
        self.assertEqual(policy.last_reason, "emergency:recall-quest-fail")

    def test_q31_defers_fixed_target_ammo_recovery_during_opening_wave(self):
        profile = replace(
            self.profiles[31],
            approved=True,
            engagement_plan={
                **self.profiles[31].engagement_plan,
                "hold_position": [18, 1],
                "initial_hold_turns": 60,
            },
        )
        policy = HengbotPolicy(quest_strategies={31: profile})
        recovery_plan = profile.engagement_plan["throwing_points"][0]
        recovery_key = (
            int(recovery_plan["race_id"]),
            int(recovery_plan["target"][0]),
            int(recovery_plan["target"][1]),
        )
        policy._quest_strategy_pending_recovery[31] = recovery_plan
        policy._quest_strategy_cleared_targets[31] = {recovery_key}
        rushing = replace(hostile(1, 17, 1, distance=1), race_id=343)
        snapshot = Snapshot(
            player(18, 1, hp=585, max_hp=585),
            {
                Position(18, 1): grid(18, 1),
                Position(17, 1): grid(17, 1, monster=True),
                Position(17, 2): grid(17, 2, objects=1),
                Position(16, 3): grid(16, 3, objects=1),
            },
            [rushing],
            floor_key=(0, 22, 31),
        )

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [rushing], [rushing]),
            "8",
        )
        self.assertEqual(policy.last_reason, "quest-strategy:melee")
        self.assertIn(31, policy._quest_strategy_pending_recovery)

    def test_q22_restart_at_light_point_latches_used_scroll_phase(self):
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 7)},
            monster_placements=(((1, 6), 118),),
            entrance=(1, 1), exit=(1, 1),
        )
        profile = replace(
            self.profiles[22],
            approved=True,
            engagement_plan={
                **self.profiles[22].engagement_plan,
                "hold_position": [1, 1],
                "initial_hold_turns": 1,
                "post_wave_light_steps": 3,
            },
        )
        policy = HengbotPolicy(
            quest_strategies={22: profile},
            quest_knowledge={
                22: QuestInfo(22, "Orc Camp", 6, 15, 6, battlefield=battlefield)
            },
            monrace_knowledge={118: MonraceKnowledge(64, 110, False, False)},
        )
        snapshot = Snapshot(
            player(1, 4),
            {Position(1, cell): grid(1, cell) for cell in range(1, 7)},
            [], floor_key=(0, 15, 22), inventory=[],
        )
        policy._quest_strategy_initial_hold_turns[22] = 1

        self.assertEqual(policy._approved_quest_strategy_key(snapshot, [], []), "6")
        self.assertIn(22, policy._quest_strategy_post_wave_light_attempted)
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")

    def test_q22_sweep_closes_on_visible_mobile_when_shot_is_blocked(self):
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 7)},
            monster_placements=(((1, 2), 118),),
            entrance=(1, 6), exit=(1, 6),
        )
        profile = replace(
            self.profiles[22],
            approved=True,
            engagement_plan={
                **self.profiles[22].engagement_plan,
                "hold_position": [1, 6],
            },
        )
        policy = HengbotPolicy(
            quest_strategies={22: profile},
            quest_knowledge={
                22: QuestInfo(22, "Orc Camp", 6, 15, 6, battlefield=battlefield)
            },
            monrace_knowledge={118: MonraceKnowledge(64, 110, False, False)},
        )
        policy._quest_strategy_post_wave_light_attempted.add(22)
        enemy = hostile(2, 1, 2)
        snapshot = Snapshot(
            player(1, 4),
            {Position(1, cell): grid(1, cell) for cell in range(1, 7)},
            [enemy], floor_key=(0, 15, 22), inventory=[],
        )

        with patch.object(policy, "_q2_ranged_core_key", return_value=None):
            self.assertEqual(
                policy._approved_quest_strategy_key(
                    snapshot, [enemy], []
                ),
                "4",
            )
        self.assertEqual(policy.last_reason, "quest-strategy:sweep-engage-mobile")

    def test_q22_restart_at_approved_hold_does_not_repeat_opening_consumables(self):
        profile = replace(self.profiles[22], approved=True)
        hold = Position(*profile.engagement_plan["opening_reposition"]["goal_points"][0])
        snapshot = Snapshot(
            player(hold.y, hold.x), {hold: grid(hold.y, hold.x)}, [],
            floor_key=(0, 15, 22),
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        policy = HengbotPolicy(quest_strategies={22: profile})

        key = policy._approved_quest_strategy_key(snapshot, [], [])

        self.assertNotIn(key, {"qs", "rt"})
        self.assertEqual(policy._quest_strategy_opening_phase[22], 3)
        self.assertEqual(policy._quest_strategy_hold_positions[22], hold)

    def test_q22_first_entry_uses_player_start_not_exit_stair(self):
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(29, 34)},
            monster_placements=(),
            player_start=(1, 33),
            entrance=(1, 29),
            exit=(1, 29),
        )
        profile = replace(self.profiles[22], approved=True)
        start = Position(*battlefield.player_start)
        snapshot = Snapshot(
            player(start.y, start.x),
            {start: grid(start.y, start.x)},
            [],
            floor_key=(0, 15, 22),
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        policy = HengbotPolicy(
            quest_strategies={22: profile},
            quest_knowledge={
                22: QuestInfo(22, "Orc Camp", 6, 15, 6, battlefield=battlefield)
            },
        )

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), "qs"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:q22-opening-speed")
        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), "rt"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:q22-opening-teleport")

    def test_q22_emergency_preserves_speed_then_teleport_opening_order(self):
        profile = replace(self.profiles[22], approved=True)
        policy = HengbotPolicy(quest_strategies={22: profile})
        enemy = replace(hostile(1, 1, 2, distance=1), race_id=215)
        snapshot = Snapshot(
            player(1, 1, hp=100, max_hp=358),
            {
                Position(1, 1): grid(1, 1),
                Position(1, 2): grid(1, 2, monster=True),
            },
            [enemy],
            floor_key=(0, 15, 22),
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )

        with patch.object(policy, "_predicted_damage", return_value=432):
            self.assertEqual(policy._emergency_item(snapshot, [enemy]), "qs")
            self.assertEqual(policy.last_reason, "quest-strategy:q22-opening-speed")
            self.assertFalse(policy._fixed_quest_speed_attempted)
            self.assertEqual(policy._emergency_item(snapshot, [enemy]), "rt")
            self.assertEqual(policy.last_reason, "quest-strategy:q22-opening-teleport")
            self.assertFalse(policy._fixed_quest_speed_attempted)

    def test_q22_reposition_heals_only_below_55_percent_with_adjacent_enemy(self):
        profile = replace(self.profiles[22], approved=True)
        policy = HengbotPolicy(quest_strategies={22: profile})
        policy._quest_strategy_opening_phase[22] = 2
        enemy = replace(hostile(1, 1, 2, distance=1), race_id=215)
        inventory = [
            item("h", TVAL_POTION, SV_POTION_HEALING),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
        ]
        below_threshold = Snapshot(
            player(1, 1, hp=54, max_hp=100),
            {
                Position(1, 1): grid(1, 1),
                Position(1, 2): grid(1, 2, monster=True),
            },
            [enemy], floor_key=(0, 15, 22), inventory=inventory,
        )

        def damage(_snapshot, _hostiles, *, turns=3, expected=False):
            return 40 if turns == 1 and expected else 10

        with patch.object(policy, "_predicted_damage", side_effect=damage):
            self.assertEqual(policy._emergency_item(below_threshold, [enemy]), "qh")
            self.assertEqual(policy.last_reason, "quest-strategy:q22-reposition-heal")

        at_threshold = replace(
            below_threshold, player=player(1, 1, hp=55, max_hp=100)
        )
        with patch.object(policy, "_predicted_damage", side_effect=damage):
            self.assertIsNone(policy._emergency_item(at_threshold, [enemy]))

        distant_enemy = replace(enemy, position=Position(1, 3), distance=2)
        distant = replace(
            below_threshold,
            grids={
                Position(1, 1): grid(1, 1),
                Position(1, 3): grid(1, 3, monster=True),
            },
            visible_monsters=[distant_enemy],
        )
        with patch.object(policy, "_predicted_damage", side_effect=damage):
            self.assertIsNone(policy._emergency_item(distant, [distant_enemy]))

    def test_q22_reposition_does_not_heal_when_effective_healing_is_too_small(self):
        profile = replace(self.profiles[22], approved=True)
        policy = HengbotPolicy(quest_strategies={22: profile})
        policy._quest_strategy_opening_phase[22] = 2
        enemy = replace(hostile(1, 1, 2, distance=1), race_id=215)
        snapshot = Snapshot(
            player(1, 1, hp=54, max_hp=100),
            {
                Position(1, 1): grid(1, 1),
                Position(1, 2): grid(1, 2, monster=True),
            },
            [enemy], floor_key=(0, 15, 22),
            inventory=[item("h", TVAL_POTION, SV_POTION_HEALING)],
        )

        def damage(_snapshot, _hostiles, *, turns=3, expected=False):
            return 47 if turns == 1 and expected else 10

        with patch.object(policy, "_predicted_damage", side_effect=damage):
            self.assertIsNone(policy._emergency_item(snapshot, [enemy]))

    def test_q22_reposition_lethality_does_not_create_an_extra_heal_rule(self):
        profile = replace(self.profiles[22], approved=True)
        policy = HengbotPolicy(quest_strategies={22: profile})
        policy._quest_strategy_opening_phase[22] = 2
        enemy = replace(hostile(1, 1, 2, distance=1), race_id=215)
        snapshot = Snapshot(
            player(1, 1, hp=90, max_hp=100),
            {
                Position(1, 1): grid(1, 1),
                Position(1, 2): grid(1, 2, monster=True),
            },
            [enemy], floor_key=(0, 15, 22),
            inventory=[
                item("h", TVAL_POTION, SV_POTION_HEALING),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )

        with patch.object(policy, "_predicted_damage", return_value=100):
            self.assertEqual(policy._emergency_item(snapshot, [enemy]), "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_q22_restart_off_entrance_routes_without_reusing_consumables(self):
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 8)},
            monster_placements=(), entrance=(1, 1), exit=(1, 1),
        )
        profile = replace(
            self.profiles[22],
            approved=True,
            engagement_plan={
                **self.profiles[22].engagement_plan,
                "opening_reposition": {
                    "speed_first": True,
                    "teleport_once": True,
                    "goal_points": [[1, 7]],
                    "avoid_non_adjacent_combat": True,
                },
            },
        )
        snapshot = Snapshot(
            player(1, 3),
            {Position(1, cell): grid(1, cell) for cell in range(1, 8)},
            [], floor_key=(0, 15, 22),
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        policy = HengbotPolicy(
            quest_strategies={22: profile},
            quest_knowledge={
                22: QuestInfo(22, "Orc Camp", 6, 15, 6, battlefield=battlefield)
            },
        )

        key = policy._approved_quest_strategy_key(snapshot, [], [])

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "quest-strategy:q22-opening-reposition")
        self.assertEqual(policy._quest_strategy_opening_phase[22], 2)

    def test_q31_profile_launcher_fires_standard_bolts(self):
        profile = replace(self.profiles[31], approved=True)
        target = replace(hostile(1, 18, 5, distance=4), race_id=206)
        snapshot = Snapshot(
            player(18, 1, hp=600, max_hp=600),
            {
                Position(18, x): grid(18, x, monster=x == 5, lit=True)
                for x in range(1, 6)
            },
            [target], floor_key=(0, 22, 31),
            inventory=[item("b", TVAL_BOLT, 0, count=99)],
            equipment=[
                item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)
            ],
        )
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            monrace_knowledge={
                206: MonraceKnowledge(
                    529, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                )
            },
        )
        policy._fixed_quest_speed_attempted = True

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [target], []), "fb6"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:ranged-fire")

    def test_q31_cursor_fire_completes_and_stops_after_no_progress(self):
        profile = replace(self.profiles[31], approved=True)
        target = replace(hostile(16, 8, 14, distance=6), race_id=329)
        snapshot = Snapshot(
            player(9, 20, hp=464, max_hp=464),
            {
                Position(9, 20): grid(9, 20, lit=True),
                Position(8, 14): grid(8, 14, monster=True, lit=True),
            },
            [target], floor_key=(0, 22, 31),
            inventory=[item("j", TVAL_BOLT, 0, count=5)],
            equipment=[
                item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)
            ],
        )
        policy = HengbotPolicy(quest_strategies={31: profile})

        attempts = [
            policy._q2_ranged_core_key(
                replace(
                    snapshot,
                    inventory=[item("j", TVAL_BOLT, 0, count=count)],
                ),
                profile,
                [target],
            )
            for count in (5, 4, 3, 2)
        ]

        self.assertEqual(attempts[:3], ["fj*p744444t5\x1b"] * 3)
        self.assertIsNone(attempts[3])

    def test_q31_cursor_fire_rejects_walkable_los_blocker(self):
        profile = replace(self.profiles[31], approved=True)
        target = replace(hostile(16, 7, 22, distance=5), race_id=329)
        snapshot = Snapshot(
            player(12, 23, hp=464, max_hp=464),
            {
                Position(12, 23): grid(12, 23, lit=True),
                Position(11, 22): grid(11, 22, lit=True),
                Position(9, 22): grid(
                    9, 22, lit=True, allows_los=False
                ),
                Position(7, 22): grid(
                    7, 22, monster=True, lit=True, in_view=True
                ),
            },
            [target], floor_key=(0, 22, 31),
            inventory=[item("i", TVAL_BOLT, 0, count=7)],
            equipment=[
                item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)
            ],
        )
        policy = HengbotPolicy(quest_strategies={31: profile})

        self.assertIsNone(
            policy._q2_ranged_core_key(snapshot, profile, [target])
        )

    def test_q31_melees_stationary_target_after_forced_adjacency(self):
        profile = replace(self.profiles[31], approved=True)
        target = replace(hostile(16, 5, 7, distance=1), race_id=206)
        snapshot = Snapshot(
            player(6, 7, hp=416, max_hp=464),
            {
                Position(6, 7): grid(6, 7, lit=True),
                Position(5, 7): grid(5, 7, monster=True, lit=True),
            },
            [target], floor_key=(0, 22, 31),
            inventory=[item("i", TVAL_BOLT, 0, count=7)],
            equipment=[
                item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)
            ],
        )
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            monrace_knowledge={
                206: MonraceKnowledge(
                    529, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                )
            },
        )

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [target], [target]),
            "8",
        )
        self.assertEqual(policy.last_reason, "quest-strategy:melee")

    def test_q31_hold_gate_precedes_stationary_target_survey(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        info = load_quest_knowledge(definitions)[31]
        profile = replace(self.profiles[31], approved=True)
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            quest_knowledge={31: info},
            monrace_knowledge={
                206: MonraceKnowledge(
                    529, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
                329: MonraceKnowledge(
                    500, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
            },
        )
        snapshot = Snapshot(
            player(18, 1), {Position(18, 1): grid(18, 1)}, [],
            floor_key=(0, 22, 31),
        )

        self.assertEqual(policy._approved_quest_strategy_key(snapshot, [], []), WAIT_KEY)
        self.assertEqual(policy.last_reason, "quest-strategy:hold")
        policy._quest_strategy_initial_hold_turns[31] = 60
        self.assertEqual(policy._approved_quest_strategy_key(snapshot, [], []), "s")
        self.assertEqual(policy.last_reason, "quest-strategy:survey-target-unconfirmed")

    def test_q31_sweeps_instead_of_cycling_at_stale_mobile_spawn(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        info = load_quest_knowledge(definitions)[31]
        profile = replace(self.profiles[31], approved=True)
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            quest_knowledge={31: info},
            monrace_knowledge={
                206: MonraceKnowledge(
                    529, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
                329: MonraceKnowledge(
                    500, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
            },
        )
        policy._fixed_quest_speed_attempted = True
        policy._quest_strategy_initial_hold_turns[31] = 60
        policy._quest_strategy_cleared_targets[31] = {
            (
                int(plan["race_id"]),
                int(plan["target"][0]),
                int(plan["target"][1]),
            )
            for plan in profile.engagement_plan["throwing_points"]
        }
        stale_spawn = Position(2, 11)
        snapshot = Snapshot(
            player(stale_spawn.y, stale_spawn.x),
            {stale_spawn: grid(stale_spawn.y, stale_spawn.x)},
            [],
            floor_key=(0, 22, 31),
        )
        policy._build_grid_index(snapshot)

        key = policy._approved_quest_strategy_key(snapshot, [], [])

        self.assertIn(key, {"1", "2", "3", "4", "6", "7", "8", "9"})
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")

    def test_q31_does_not_exhaust_sweep_after_only_initial_placements(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        info = load_quest_knowledge(definitions)[31]
        profile = replace(self.profiles[31], approved=True)
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            quest_knowledge={31: info},
            monrace_knowledge={
                206: MonraceKnowledge(
                    529, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
                329: MonraceKnowledge(
                    500, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
            },
        )
        policy._fixed_quest_speed_attempted = True
        policy._quest_strategy_initial_hold_turns[31] = 60
        policy._quest_strategy_cleared_targets[31] = {
            (
                int(plan["race_id"]),
                int(plan["target"][0]),
                int(plan["target"][1]),
            )
            for plan in profile.engagement_plan["throwing_points"]
        }
        battlefield = info.battlefield
        self.assertIsNotNone(battlefield)
        policy._quest_strategy_surveyed_placements[31] = {
            Position(*position)
            for position, _ in battlefield.monster_placements
        }
        policy._quest_strategy_sweep_rounds[31] = 2
        current = Position(14, 25)
        snapshot = Snapshot(
            player(current.y, current.x),
            {current: grid(current.y, current.x)},
            [],
            floor_key=(0, 22, 31),
        )
        policy._build_grid_index(snapshot)

        key = policy._approved_quest_strategy_key(snapshot, [], [])

        self.assertIn(key, {"1", "2", "3", "4", "6", "7", "8", "9"})
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")

    def test_q31_repeats_full_map_sweep_after_three_rounds_for_teleporting_huorns(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        info = load_quest_knowledge(definitions)[31]
        profile = replace(self.profiles[31], approved=True)
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            quest_knowledge={31: info},
            monrace_knowledge={
                206: MonraceKnowledge(
                    529, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
                329: MonraceKnowledge(
                    500, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
            },
        )
        policy._fixed_quest_speed_attempted = True
        policy._quest_strategy_initial_hold_turns[31] = 60
        policy._quest_strategy_cleared_targets[31] = {
            (
                int(plan["race_id"]),
                int(plan["target"][0]),
                int(plan["target"][1]),
            )
            for plan in profile.engagement_plan["throwing_points"]
        }
        battlefield = info.battlefield
        self.assertIsNotNone(battlefield)
        navigator = QuestFloorNavigator(31, battlefield)
        policy._quest_strategy_surveyed_placements[31] = {
            Position(y, x)
            for (y, x) in battlefield.terrain
            if navigator._static_walkable(Position(y, x))
        }
        policy._quest_strategy_sweep_rounds[31] = 3
        current = Position(14, 25)
        snapshot = Snapshot(
            player(current.y, current.x),
            {current: grid(current.y, current.x)},
            [],
            floor_key=(0, 22, 31),
        )
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep-repeat")
        self.assertEqual(policy._quest_strategy_sweep_rounds[31], 4)

    def test_q31_refills_empty_lantern_before_continuing_quiet_sweep(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        info = load_quest_knowledge(definitions)[31]
        profile = replace(self.profiles[31], approved=True)
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            quest_knowledge={31: info},
        )
        current = Position(14, 25)
        snapshot = Snapshot(
            player(current.y, current.x),
            {current: grid(current.y, current.x)},
            [],
            inventory=[
                item("a", TVAL_FLASK, SV_FLASK_OIL, name="oil", fuel=7500)
            ],
            equipment=[
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    name="lantern",
                    fuel=0,
                    is_equipment=True,
                )
            ],
            floor_key=(0, 22, 31),
        )

        self.assertEqual(policy.choose_key(snapshot), "\\Fa")
        self.assertEqual(policy.last_reason, "refill-light")

    def test_q31_restart_uses_static_route_to_retake_distant_hold(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        info = load_quest_knowledge(definitions)[31]
        profile = replace(self.profiles[31], approved=True)
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            quest_knowledge={31: info},
            monrace_knowledge={
                206: MonraceKnowledge(
                    529, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
                329: MonraceKnowledge(
                    500, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                ),
            },
        )
        restart_position = Position(1, 10)
        snapshot = Snapshot(
            player(restart_position.y, restart_position.x),
            {restart_position: grid(restart_position.y, restart_position.x)},
            [],
            floor_key=(0, 22, 31),
        )
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), "4"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:retake-hold")

class ApprovedQuestStrategyExecutionTest(unittest.TestCase):
    QUEST_ID = 1

    @classmethod
    def setUpClass(cls):
        cls.profiles = load_quest_strategies(
            Path(__file__).parent.parent / "strategy" / "quests"
        )
        q1_terrain = {
            (y, x): ("wall" if y in {4, 9} or x in {0, 14} else "floor")
            for y in range(4, 10) for x in range(15)
        }
        q1_terrain.update({(5, 4): "door", (8, 4): "door", (8, 1): "exit"})
        cls.q1_battlefield = QuestBattlefield(
            terrain=q1_terrain, player_start=(8, 1), entrance=(8, 1), exit=(8, 1),
            searchable=((5, 4), (8, 4)),
        )
        cls.q34_battlefield = QuestBattlefield(monster_placements=(
            ((3, 13), 174), ((7, 15), 243), ((9, 11), 107), ((11, 9), 107),
        ))

    def _policy(self, *, q34_opening_light=False):
        stationary = MonraceKnowledge(
            10, 110, False, False, flags=frozenset({"NEVER_MOVE"})
        )
        mobile = MonraceKnowledge(10, 110, False, False)
        profiles = self.profiles
        if not q34_opening_light:
            q34_plan = dict(self.profiles[34].engagement_plan)
            q34_plan.pop("opening_light", None)
            profiles = {
                **self.profiles,
                34: replace(self.profiles[34], engagement_plan=q34_plan),
            }
        return HengbotPolicy(
            quest_strategies=profiles,
            quest_knowledge={
                1: QuestInfo(
                    1, "Thieves Hideout", 6, 5, 6,
                    battlefield=self.q1_battlefield,
                ),
                34: QuestInfo(
                    34, "Dump Witness", 6, 5, 6,
                    battlefield=self.q34_battlefield,
                )
            },
            monrace_knowledge={107: stationary, 243: stationary, 174: mobile},
        )

    def _q34_source_policy(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        policy = self._policy()
        policy._quest_knowledge[34] = load_quest_knowledge(definitions)[34]
        return policy

    def _live_redacted_quest_fixture(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        knowledge = load_quest_knowledge(definitions)
        policy = HengbotPolicy(
            quest_strategies=self.profiles,
            quest_knowledge=knowledge,
        )
        quests = {
            quest_id: QuestState(
                id=quest_id, status=status, fixed=True,
                level=knowledge[quest_id].level,
            )
            for quest_id, status in {
                8: QUEST_STATUS_TAKEN,
                9: QUEST_STATUS_TAKEN,
                34: QUEST_STATUS_FINISHED,
                1: QUEST_STATUS_FINISHED,
                14: QUEST_STATUS_FINISHED,
                49: QUEST_STATUS_FINISHED,
                43: QUEST_STATUS_FINISHED,
            }.items()
        }
        snapshot = Snapshot(
            player(10, 10, level=30, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            visited_town_ids=frozenset({0, 1, 3}),
            quests=quests,
        )
        return policy, snapshot

    def test_redacted_live_export_synthesizes_q2_then_q22_then_q31(self):
        policy, snapshot = self._live_redacted_quest_fixture()

        self.assertEqual(policy._fixed_quest_head(snapshot).id, 2)
        snapshot = replace(snapshot, quests={
            **snapshot.quests,
            2: QuestState(2, status=QUEST_STATUS_FINISHED, fixed=True),
        })
        self.assertEqual(policy._fixed_quest_head(snapshot).id, 22)
        snapshot = replace(snapshot, quests={
            **snapshot.quests,
            22: QuestState(22, status=QUEST_STATUS_FINISHED, fixed=True),
        })
        self.assertEqual(policy._fixed_quest_head(snapshot).id, 31)

    def test_exported_terminal_states_are_never_resurrected(self):
        policy, snapshot = self._live_redacted_quest_fixture()
        terminal = {1: 4, 14: 5, 34: 6}
        snapshot = replace(snapshot, quests={
            **snapshot.quests,
            **{
                quest_id: QuestState(quest_id, status=status, fixed=True)
                for quest_id, status in terminal.items()
            },
        })

        known = policy._known_fixed_quests(snapshot)

        self.assertEqual(known[2].status, QUEST_STATUS_UNTAKEN)
        self.assertEqual(
            {quest_id: known[quest_id].status for quest_id in terminal},
            terminal,
        )

    def test_redacted_export_preserves_taken_inflight_guard(self):
        policy, snapshot = self._live_redacted_quest_fixture()
        supported = replace(snapshot, quests={
            **snapshot.quests,
            22: QuestState(22, status=QUEST_STATUS_TAKEN, fixed=True),
        })
        unsupported = replace(snapshot, quests={
            **snapshot.quests,
            99: QuestState(99, status=QUEST_STATUS_TAKEN, fixed=True),
        })

        self.assertEqual(
            policy._known_fixed_quests(snapshot)[2].status,
            QUEST_STATUS_UNTAKEN,
        )
        self.assertEqual(policy._fixed_quest_head(supported).id, 22)
        self.assertIsNone(policy._fixed_quest_head(unsupported))

    def test_redacted_conditional_quests_still_require_live_offer(self):
        policy, snapshot = self._live_redacted_quest_fixture()
        snapshot = replace(snapshot, quests={
            **snapshot.quests,
            2: QuestState(2, status=QUEST_STATUS_FINISHED, fixed=True),
            22: QuestState(22, status=QUEST_STATUS_FINISHED, fixed=True),
            31: QuestState(31, status=QUEST_STATUS_FINISHED, fixed=True),
        })

        known = policy._known_fixed_quests(snapshot)
        self.assertTrue({18, 25, 28}.issubset(known))
        self.assertIsNone(policy._fixed_quest_head(snapshot))

    def test_redacted_export_reconnects_q2_scroll_procurement(self):
        policy, snapshot = self._live_redacted_quest_fixture()

        strategy = policy._carry_procurement_strategy(snapshot)
        needs = policy._enumerate_town_needs(snapshot)

        self.assertIsNotNone(strategy)
        self.assertEqual(strategy.quest_id, 2)
        self.assertTrue(any(
            need.store_type == STORE_ALCHEMIST
            and need.category == "quest-scrolls"
            for need in needs
        ))

    def test_completed_q34_opens_floor_chest_before_sweep_pickup(self):
        policy = self._q34_source_policy()
        chest_position = Position(10, 8)
        snapshot = Snapshot(
            player(10, 9, hp=100, max_hp=100),
            {
                Position(10, 9): grid(10, 9),
                chest_position: grid(
                    10, 8, objects=1, object_tvals=(TVAL_CHEST,)
                ),
            },
            [],
            floor_key=(0, 5, 34),
            quests={
                34: QuestState(
                    id=34, status=QUEST_STATUS_COMPLETED, fixed=True, level=5
                )
            },
        )

        self.assertEqual(policy.choose_key(snapshot), "s")
        self.assertEqual(policy.last_reason, "chest:search")
        self.assertEqual(policy._chest_position, chest_position)

    def test_completed_q34_ignores_ruined_chests_for_wooden_chest(self):
        policy = self._q34_source_policy()
        wooden = Position(10, 8)
        ruined = Position(3, 15)
        snapshot = Snapshot(
            player(3, 14, hp=100, max_hp=100),
            {
                Position(3, 14): grid(3, 14),
                ruined: grid(3, 15, objects=1, object_tvals=(TVAL_CHEST,)),
                wooden: grid(10, 8, objects=1, object_tvals=(TVAL_CHEST,)),
            },
            [],
            floor_key=(0, 5, 34),
            quests={
                34: QuestState(
                    id=34, status=QUEST_STATUS_COMPLETED, fixed=True, level=5
                )
            },
        )

        with patch.object(
            policy, "_nearest_goal_step", return_value=Position(4, 14)
        ):
            self.assertEqual(policy.choose_key(snapshot), "2")

        self.assertEqual(policy.last_reason, "chest:approach")
        self.assertEqual(policy._chest_position, wooden)

    def _quest(self, status):
        return QuestState(id=1, status=status, type=6, level=5, flags=6, fixed=True)

    def _force_snapshot(self, quest_id, *, hp, torches, speed=1, healing=2,
                        abilities=frozenset()):
        inventory = [
            item("t", TVAL_LITE, SV_LITE_TORCH, count=torches, fuel=5000),
            item("s", TVAL_POTION, SV_POTION_SPEED, count=speed),
            item("h", TVAL_POTION, SV_POTION_HEALING, count=healing),
        ]
        return Snapshot(
            player(1, 1, hp=hp, max_hp=hp, abilities=abilities),
            {Position(1, 1): grid(1, 1)}, [], inventory=inventory,
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True)],
            floor_key=(0, 0, quest_id),
        )

    def test_acceptance_base_tier_revert_proofs_each_component(self):
        policy = self._policy()
        profile = policy.approved_quest_strategy(1)
        self.assertIsNotNone(profile)
        base = self._force_snapshot(1, hp=36, torches=5)
        with patch("hengbot.policy.weapon_expected_dps", return_value=28):
            self.assertTrue(policy._approved_strategy_force_ready(base, profile))
            for changed in (
                replace(base, player=replace(base.player, hp=35, max_hp=35)),
                replace(base, inventory=[*base.inventory[:1], base.inventory[2]]),
                replace(base, inventory=[base.inventory[0], base.inventory[1],
                                         replace(base.inventory[2], count=1)]),
                replace(base, inventory=[replace(base.inventory[0], count=4),
                                         *base.inventory[1:]]),
            ):
                with self.subTest(changed=changed):
                    self.assertFalse(policy._approved_strategy_force_ready(changed, profile))
        with patch("hengbot.policy.weapon_expected_dps", return_value=27.99):
            self.assertFalse(policy._approved_strategy_force_ready(base, profile))
        resisted_profile = replace(
            profile, required_force={**profile.required_force, "resists": ["fire"]}
        )
        with patch("hengbot.policy.weapon_expected_dps", return_value=28):
            self.assertFalse(policy._approved_strategy_force_ready(base, resisted_profile))
            fire_ready = replace(
                base, player=replace(base.player, abilities=frozenset({"resist_fire"}))
            )
            self.assertTrue(policy._approved_strategy_force_ready(fire_ready, resisted_profile))

    def test_no_healing_tier_waives_potions_not_torches(self):
        policy = self._policy()
        profile = policy.approved_quest_strategy(1)
        no_potions = self._force_snapshot(1, hp=88, torches=5, speed=0, healing=0)
        no_potions = replace(no_potions, inventory=no_potions.inventory[:1])
        with patch("hengbot.policy.weapon_expected_dps", return_value=28):
            self.assertTrue(policy._approved_strategy_force_ready(no_potions, profile))
            short_ammo = replace(
                no_potions, inventory=[replace(no_potions.inventory[0], count=4)]
            )
            self.assertFalse(policy._approved_strategy_force_ready(short_ammo, profile))

    def test_q14_no_healing_tier_accepts_no_supplies_only_at_four_warg_line(self):
        policy = self._policy()
        profile = policy.approved_quest_strategy(14)
        no_supplies = replace(
            self._force_snapshot(14, hp=150, torches=0, speed=0, healing=0),
            inventory=[],
        )
        with patch("hengbot.policy.weapon_expected_dps", return_value=36):
            self.assertTrue(
                policy._approved_strategy_force_ready(no_supplies, profile)
            )
            self.assertFalse(
                policy._approved_strategy_force_ready(
                    replace(
                        no_supplies,
                        player=replace(no_supplies.player, hp=149, max_hp=149),
                    ),
                    profile,
                )
            )
        with patch("hengbot.policy.weapon_expected_dps", return_value=35.99):
            self.assertFalse(
                policy._approved_strategy_force_ready(no_supplies, profile)
            )

    def test_cure_critical_does_not_satisfy_strategy_healing_potions(self):
        policy = self._policy()
        profile = policy.approved_quest_strategy(1)
        base = self._force_snapshot(1, hp=36, torches=5, healing=2)
        cure_only = replace(
            base,
            inventory=[
                base.inventory[0],
                base.inventory[1],
                replace(base.inventory[2], sval=SV_POTION_CURE_CRITICAL),
            ],
        )

        with patch("hengbot.policy.weapon_expected_dps", return_value=28):
            self.assertFalse(
                policy._approved_strategy_force_ready(cure_only, profile)
            )
        status = policy.fixed_quest_readiness_state()["strategy_force"]
        self.assertEqual(status["heal_potions"]["measured"], 0)
        self.assertIn("heal_potions", status["failed"])

    def test_q34_readiness_does_not_make_never_move_melee_targets_adjacent(self):
        policy = self._policy()
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34],
            placed_monsters=((174, 1), (243, 1), (107, 2)),
        )
        stationary = MonraceKnowledge(
            49, 110, False, False, max_melee_damage=300,
            flags=frozenset({"NEVER_MOVE"}),
        )
        policy._monrace_knowledge.update({107: stationary, 243: stationary})
        policy._monrace_knowledge[174] = MonraceKnowledge(
            8, 120, False, False, max_melee_damage=9
        )
        snapshot = self._force_snapshot(
            34, hp=627, torches=20, speed=10, healing=29
        )
        policy._combat_weapon_ready = lambda _snapshot: True
        policy._town_departure_ready = lambda _snapshot: True

        with (
            patch("hengbot.policy.weapon_expected_dps", return_value=78.0),
            patch.object(policy, "_main_hand_dps", return_value=78.0),
        ):
            self.assertTrue(policy._fixed_quest_ready(snapshot, 34))

        readiness = policy.fixed_quest_readiness_state()
        self.assertEqual(readiness["strategy_controlled_stationary"], [107, 243])
        self.assertLess(
            readiness["worst_adjacent"],
            readiness["hp_healing_budget"]
            * policy_module.FIXED_QUEST_MAX_DAMAGE_RATIO,
        )

    def test_q34_emergency_filter_leaves_distant_stationary_targets_to_strategy(self):
        policy = self._policy()
        profile = policy.approved_quest_strategy(34)
        snapshot = Snapshot(
            player(1, 18, hp=85, max_hp=85),
            {Position(1, 18): grid(1, 18)},
            [],
            floor_key=(0, 5, 34),
        )
        bee = replace(hostile(1, 3, 18, distance=2), race_id=174)
        cloaker = replace(hostile(2, 7, 15, distance=6), race_id=243)

        filtered = policy._quest_strategy_emergency_hostiles(
            snapshot, profile, [bee, cloaker]
        )

        self.assertEqual([monster.race_id for monster in filtered], [174])
        adjacent_cloaker = replace(cloaker, position=Position(1, 19), distance=1)
        filtered = policy._quest_strategy_emergency_hostiles(
            snapshot, profile, [bee, adjacent_cloaker]
        )
        self.assertEqual(
            [monster.race_id for monster in filtered], [174, 243]
        )

    def test_q31_emergency_filter_retains_distant_tele_to_stationary_target(self):
        profile = replace(self.profiles[31], approved=True)
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            monrace_knowledge={
                329: MonraceKnowledge(
                    500,
                    110,
                    False,
                    False,
                    max_melee_damage=72,
                    flags=frozenset({"NEVER_MOVE"}),
                    abilities=frozenset({"BLINK", "TELE_TO"}),
                    spell_frequency=11,
                )
            },
        )
        target = replace(hostile(1, 8, 14, distance=6), race_id=329)
        snapshot = Snapshot(
            player(9, 20, hp=464, max_hp=464),
            {
                Position(9, 20): grid(9, 20, lit=True),
                Position(8, 14): grid(8, 14, monster=True, lit=True),
            },
            [target],
            floor_key=(0, 22, 31),
        )

        filtered = policy._quest_strategy_emergency_hostiles(
            snapshot, profile, [target]
        )

        self.assertEqual(filtered, [target])

    def test_acceptance_errand_reserves_and_routes_q34_torches(self):
        policy = self._policy()
        torches = item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
        quest = QuestState(id=34, status=0, fixed=True, level=5)
        snap = Snapshot(player(10, 10, class_id=PLAYER_CLASS_WARRIOR), {Position(10, 10): grid(10, 10, building_special=34)}, [],
                        floor_key=(0, 0, 0), town_flag=True, quests={34: quest},
                        inventory=[torches], equipment=[item(
                            "main_hand", TVAL_SWORD, 1,
                            name="short sword", is_equipment=True,
                        )])
        self.assertEqual(policy._retention_reservation(snap, torches), 20)
        short = replace(snap, inventory=[replace(torches, count=19)])
        needs = policy._enumerate_town_needs(short)
        self.assertTrue(any(
            need.store_type == STORE_GENERAL and need.category == "quest-throwing-items"
            for need in needs
        ))

    def test_fresh_q34_torches_preempt_fundraising_and_home_errands(self):
        policy = self._policy()
        policy._fundraising_mode = "prepare"
        policy._town_restock_suppressed = True
        policy._town_store_attempted.update({STORE_HOME: 1, STORE_GENERAL: 1})
        policy._town_errand_plan = policy_module.TownErrandPlan([STORE_HOME])
        quest = QuestState(id=34, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5)
        snapshot = Snapshot(
            player(
                10, 10, level=1, class_id=PLAYER_CLASS_WARRIOR,
                gold=FUNDRAISING_START_GOLD - 1,
            ),
            {Position(10, 10): grid(10, 10, building_special=34)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            quests={34: quest},
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=6, fuel=5000),
                item("d", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=4),
            ],
            equipment=[
                item(
                    "main_hand", TVAL_SWORD, 1,
                    name="short sword", is_equipment=True,
                )
            ],
        )

        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertIsNone(policy._fundraising_mode)
        self.assertFalse(policy._town_restock_suppressed)
        self.assertEqual(
            policy._enumerate_town_needs(snapshot),
            [policy_module.TownNeed(
                STORE_GENERAL, "quest-throwing-items", "opening-quest"
            )],
        )

    def _measured_q34_opening(self, *, status=QUEST_STATUS_UNTAKEN):
        weapon = item(
            "main_hand", TVAL_SWORD, 1,
            name="short sword", is_equipment=True,
        )
        return Snapshot(
            player(
                10, 9, level=1, class_id=PLAYER_CLASS_WARRIOR, gold=271,
            ),
            {
                Position(10, 9): grid(10, 9),
                Position(10, 10): replace(
                    grid(10, 10), store_number=STORE_GENERAL,
                ),
                Position(9, 10): replace(
                    grid(9, 10), store_number=STORE_HOME,
                ),
                Position(11, 10): grid(11, 10, building_special=34),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            quests={
                34: QuestState(id=34, status=status, fixed=True, level=5)
            },
            equipment=[weapon],
        )

    def test_measured_q34_opening_routes_and_buys_torches_exactly(self):
        policy = self._policy()
        torch = store_item(
            "a", TVAL_LITE, SV_LITE_TORCH,
            name="torch", count=99, price=1,
        )
        opening = replace(
            self._measured_q34_opening(),
            store=StoreState(STORE_GENERAL, [torch]),
        )

        routing_policy = self._policy()
        routing_policy._equipment_catalog.home_scan_complete = True
        routing_policy._home_knowledge_current = True
        routing_policy._home_knowledge_items = []
        self.assertEqual(
            routing_policy.choose_key(replace(opening, store=None)), "6",
        )
        self.assertEqual(routing_policy.last_reason, "shop:approach")
        self.assertEqual(policy._next_required_store_type(opening), STORE_GENERAL)
        policy._home_knowledge_current = True
        policy._home_knowledge_items = []
        self.assertEqual(_public_shop_inner(self, policy, opening), "pa20\r\r")
        self.assertNotEqual(policy.last_reason, "home:atomic-deposit")
        self.assertFalse(policy.last_reason.startswith("calibration:"))
        self.assertNotEqual(policy.last_reason, "equipment-transaction:takeoff")

    def test_q34_opening_sequence_never_reaches_calibration_or_takeoff(self):
        policy = self._policy()
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._home_knowledge_items = []
        opening = self._measured_q34_opening()

        keys = [policy.choose_key(replace(opening, turn=0))]
        reasons = [policy.last_reason]
        keys.append(policy.choose_key(replace(opening, turn=1)))
        reasons.append(policy.last_reason)
        keys.append(policy.choose_key(replace(opening, turn=2)))
        reasons.append(policy.last_reason)
        keys.append(policy.choose_key(replace(opening, turn=3)))
        reasons.append(policy.last_reason)

        self.assertEqual(keys, ["6", "6", "6", "6"])
        self.assertEqual(reasons, ["shop:approach"] * 4)
        self.assertNotIn("home:atomic-deposit", reasons)
        self.assertFalse(any(reason.startswith("calibration:") for reason in reasons))
        self.assertNotIn("equipment-transaction:takeoff", reasons)

    def test_fresh_q34_opening_scans_home_before_initial_purchase(self):
        policy = self._policy()
        opening = self._measured_q34_opening()

        self.assertEqual(policy.choose_key(opening), "~9\x1b\x1b")
        self.assertEqual(policy.last_reason, "home:request-knowledge-scan")
        self.assertTrue(policy._opening_q34_active(opening))

        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._home_knowledge_items = []
        policy._home_knowledge_scan_requested = True
        self.assertEqual(policy.choose_key(replace(opening, turn=1)), "6")
        self.assertEqual(policy.last_reason, "shop:approach")

    def test_q34_wait_on_store_entrance_steps_off_instead_of_staying(self):
        policy = self._policy()
        opening = self._measured_q34_opening()
        entrance = Position(10, 10)
        opening = replace(
            opening,
            player=replace(opening.player, position=entrance),
        )
        policy._shopping_approach_store_type = STORE_GENERAL
        # Artifact decision 110 was in LEAVING, with no entry command in flight.
        self.assertIsNone(policy._store_entry_wait_owner)
        policy.last_reason = "opening-q34:wait"

        key = policy._forbid_wait_on_town_entrance(opening, WAIT_KEY)

        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "town:entrance-step-off:opening-q34:wait"
        )

    def test_genuine_store_entry_in_flight_keeps_entry_wait(self):
        policy = self._policy()
        opening = self._measured_q34_opening()
        entrance = Position(10, 10)
        opening = replace(opening, player=replace(opening.player, position=entrance))
        policy._shopping_approach_store_type = STORE_GENERAL

        self.assertEqual(
            policy._shopping_approach_key(opening, entrance, "shop:travel"),
            WAIT_KEY,
        )
        self.assertEqual(policy._store_entry_wait_owner, STORE_GENERAL)
        policy.last_reason = "opening-q34:wait"

        self.assertEqual(
            policy._forbid_wait_on_town_entrance(opening, WAIT_KEY), WAIT_KEY
        )

    def test_q34_restock_wait_publishes_supplier_reason(self):
        policy = self._policy()
        opening = self._measured_q34_opening()
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._home_knowledge_items = []
        policy._home_knowledge_scan_requested = True
        policy._town_restock_waiting_for = (STORE_GENERAL,)
        policy._town_restock_wait_until = opening.turn + STORE_RESTOCK_WAIT_TURNS

        with (
            patch.object(policy, "_town_claims_active", return_value=False),
            patch.object(policy, "_town_terminal_transitions"),
            patch.object(policy, "_town_restore_weapon_key", return_value=None),
            patch.object(policy, "_fixed_quest_key", return_value=None),
        ):
            key = policy._opening_q34_town_key(opening, [])

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:wait-restock:general")

    def test_frozen_q34_town_damage_replay_steps_away_on_each_hp_drop(self):
        self.skipTest(
            "source artifact destroyed 2026-08-17; rebuild from a future capture"
        )
        artifact = Path("evidence/evidence-death2-20260814-0300.jsonl")
        records = {
            row["decision_sequence"]: row
            for row in map(json.loads, artifact.read_text(encoding="utf-8").splitlines())
            if row.get("decision_sequence") in {675, 681, 689}
        }
        self.assertEqual(
            [(seq, records[seq]["player"]["hp"]) for seq in (675, 681, 689)],
            [(675, 9), (681, 5), (689, 2)],
        )
        policy = self._policy()
        base = self._measured_q34_opening()
        position = Position(45, 109)
        base = replace(
            base,
            turn=records[675]["turn"],
            player=replace(
                base.player, position=position, hp=9, max_hp=85, gold=1
            ),
            grids={
                position: grid(45, 109, building_special=34),
                Position(44, 108): grid(44, 108),
                Position(44, 109): grid(44, 109),
                Position(45, 108): grid(45, 108),
            },
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
            ],
        )

        keys = []
        reasons = []
        for sequence in (675, 681, 689):
            record = records[sequence]
            snapshot = replace(
                base,
                turn=record["turn"],
                player=replace(base.player, hp=record["player"]["hp"]),
            )
            keys.append(policy.choose_key(snapshot))
            reasons.append(policy.last_reason)

        self.assertEqual(keys, [WAIT_KEY, "7", "7"])
        self.assertEqual(
            reasons,
            ["opening-q34:wait", "no-wait:least-visited", "no-wait:least-visited"],
        )

    def test_q34_opening_holds_when_taken_and_releases_only_when_cleared(self):
        policy = self._policy()
        untaken = self._measured_q34_opening()
        taken = replace(
            untaken,
            quests={
                34: replace(untaken.quests[34], status=QUEST_STATUS_TAKEN)
            },
        )
        cleared = replace(
            untaken,
            quests={
                34: replace(untaken.quests[34], status=QUEST_STATUS_COMPLETED)
            },
        )

        self.assertTrue(policy._opening_q34_active(untaken))
        self.assertTrue(policy._opening_q34_active(taken))
        self.assertFalse(policy._opening_q34_active(cleared))

    def _warmed_current_q34_entrance_replay(self):
        policy = self._q34_source_policy()
        policy._character_calibration_path = Path(
            "tests/fixtures/q34-entry-character-calibration-20260814.json"
        )
        with Path(
            "tests/fixtures/q34-entry-current-tail-20260814.jsonl"
        ).open(encoding="utf-8-sig") as records:
            raw_rows = [json.loads(row) for row in records]
        boards = [
            policy._with_grid_memory(parse_snapshot(raw, policy._monrace_knowledge))
            for raw in raw_rows
        ]
        board = replace(
            boards[-1],
            quests={
                34: QuestState(
                    id=34, status=QUEST_STATUS_TAKEN, fixed=True, level=5
                )
            },
        )
        self.assertEqual(board.player.position, Position(45, 109))
        self.assertEqual((board.player.hp, board.player.max_hp), (85, 85))
        self.assertEqual(board.player.gold, 33)
        self.assertEqual(policy._count_throwing_torches(board), 20)
        return policy, board

    def test_current_q34_entrance_replay_enters_on_reviewed_readiness(self):
        policy, board = self._warmed_current_q34_entrance_replay()

        uncalibrated = self._policy()
        preparation = uncalibrated._prepare_equipment_optimization(board)
        self.assertEqual(preparation.blockers, ("calibration-required",))
        self.assertFalse(uncalibrated._equipment_departure_ready(board))
        self.assertTrue(policy._evaluate_fixed_quest_readiness(
            board, 34, require_target_town=True
        ))
        self.assertAlmostEqual(
            policy._fixed_quest_readiness["strategy_force"]["dps"]["measured"],
            28.161615655384615,
            places=1,
        )

        self.assertEqual(QuestFloorNavigator.enter_from_town(policy, board, 34), ">y")
        self.assertEqual(policy.last_reason, "quest:enter")

    def test_current_q34_entrance_replay_refuses_failed_strategy_force(self):
        policy, board = self._warmed_current_q34_entrance_replay()
        injured = replace(board, player=replace(board.player, hp=9, max_hp=9))

        self.assertIsNone(QuestFloorNavigator.enter_from_town(policy, injured, 34))
        self.assertEqual(policy._fixed_quest_readiness["reason"], "strategy-force")
        self.assertEqual(policy.last_reason, "quest:readiness:strategy-force")

    def test_q34_readiness_measures_wielded_weapon_without_calibration(self):
        policy = self._policy()
        opening = self._measured_q34_opening()
        weapon = replace(
            opening.equipment[0],
            damage_dice_num=2,
            damage_dice_sides=5,
        )
        opening = replace(
            opening,
            player=replace(
                opening.player,
                main_hand_blows=1,
                main_hand_to_h=0,
                main_hand_to_d=0,
                melee_skill=60,
            ),
            equipment=[weapon],
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=2500)],
        )

        self.assertFalse(policy._approved_strategy_force_ready(opening, self.profiles[34]))
        measured = policy.fixed_quest_readiness_state()["strategy_force"]
        self.assertGreater(measured["dps"]["measured"], 0.0)
        self.assertEqual(measured["dps"]["required"], 8.0)

    def test_q34_readiness_deficits_start_existing_fundraising_owner(self):
        policy = self._policy()
        opening = replace(
            self._measured_q34_opening(),
            player=replace(self._measured_q34_opening().player, gold=61),
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=2500)],
        )

        policy._approved_strategy_force_ready(opening, self.profiles[34])
        self.assertIsNotNone(policy._next_required_store_type(opening))
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_q34_unreachable_readiness_deficits_stop_visibly(self):
        policy = self._policy()
        opening = replace(
            self._measured_q34_opening(),
            player=replace(self._measured_q34_opening().player, gold=3000),
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=2500)],
        )
        for store_type in (STORE_TEMPLE, STORE_BLACK):
            policy._town_store_attempted[store_type] = opening.turn
            policy._town_visit_ledger.nonhome_attempted_without_effect[store_type] = (
                policy._town_observable_effect_state(opening)
            )

        with patch.object(policy, "_shopping_approach_step", return_value=None):
            key = policy._opening_q34_town_key(opening, [])

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "livelock:exhausted")
        self.assertEqual(
            policy.fixed_quest_readiness_state()["strategy_force"]["failed"],
            ["dps", "speed_potions", "heal_potions"],
        )

    def test_rich_q34_readiness_deficits_still_use_live_shop_route(self):
        policy = self._policy()
        opening = replace(
            self._measured_q34_opening(),
            player=replace(self._measured_q34_opening().player, gold=5000),
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=2500)],
        )
        goal = Position(31, 119)

        with (
            patch.object(policy, "_shopping_approach_step", return_value=goal),
            patch.object(
                policy, "_shopping_approach_key", return_value="RICH-SHOP"
            ) as approach,
        ):
            key = policy._opening_q34_town_key(opening, [])

        self.assertEqual(key, "RICH-SHOP")
        approach.assert_called_once_with(opening, goal, "shop:travel")
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertIsNone(policy._fundraising_mode)

    def test_q34_terminal_ignores_readiness_not_evaluated_this_decision(self):
        opening = replace(
            self._measured_q34_opening(),
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=2500)],
        )

        for blocker in ("adjacent", "overweight"):
            with self.subTest(blocker=blocker):
                policy = self._policy()
                policy._fixed_quest_readiness = {
                    "strategy_force": {"failed": ["stale-deficit"]}
                }
                adjacent = blocker == "adjacent"
                overweight = blocker == "overweight"
                with (
                    patch.object(
                        policy,
                        "_physical_adjacent_hostiles",
                        return_value=[hostile(1, 10, 11)] if adjacent else [],
                    ),
                    patch.object(
                        policy, "_inventory_overweight", return_value=overweight
                    ),
                ):
                    key = policy._opening_q34_town_key(opening, [])

                self.assertEqual(key, WAIT_KEY)
                self.assertEqual(policy.last_reason, "opening-q34:wait")

    def test_finished_q34_other_quest_keeps_calibration_entry_refusal(self):
        policy, board = self._warmed_current_q34_entrance_replay()
        control = replace(
            board,
            quests={
                34: QuestState(
                    id=34, status=QUEST_STATUS_FINISHED, fixed=True, level=5
                ),
                1: QuestState(
                    id=1, status=QUEST_STATUS_TAKEN, fixed=True, level=5
                ),
            },
        )

        self.assertFalse(policy._opening_q34_active(control))
        self.assertFalse(policy._quest_equipment_entry_allowed(control, 1))
        self.assertEqual(policy._town_blocked_reason, "equipment-departure-incomplete")
        self.assertEqual(policy._departure_block["failed"], [
            "recall_departure_ready",
            "food_ready",
            "teleport_ready",
            "cure_critical_ready",
            "equipment_departure_ready",
            "home_candidate_resolved",
            "home_catalog_ready",
        ])

    def test_frozen_q34_offer_is_stable_across_mapless_store_snapshot(self):
        self.skipTest(
            "source artifact destroyed 2026-08-17; rebuild from a future capture"
        )
        evidence = Path(
            "evidence/evidence-q34-contract-flicker-20260814.jsonl"
        )
        with evidence.open(encoding="utf-8") as records:
            decisions = [json.loads(record) for record in records]
        captured = [
            row for row in decisions
            if row.get("decision_sequence") in {1, 2}
        ]
        self.assertEqual(
            [
                (
                    row["decision_sequence"], row.get("store_type"),
                    row.get("timing", {}).get("nearby_grids"),
                )
                for row in captured
            ],
            [(1, None, None), (1, STORE_HOME, 0), (2, None, 10448)],
        )

        policy = self._policy()
        outside = self._measured_q34_opening()
        boards = [
            replace(
                outside,
                turn=captured[0]["turn"],
                player=replace(
                    outside.player, gold=captured[0]["player"]["gold"]
                ),
            ),
            replace(
                outside,
                turn=captured[1]["turn"],
                player=replace(
                    outside.player, gold=captured[1]["player"]["gold"]
                ),
                grids={},
                store=StoreState(STORE_HOME, []),
            ),
            replace(
                outside,
                turn=captured[2]["turn"],
                player=replace(
                    outside.player, gold=captured[2]["player"]["gold"]
                ),
            ),
        ]

        evaluated = []
        for board in boards:
            policy._with_grid_memory(board)
            evaluated.append(policy._fixed_quest_is_offered(board, 34))
        self.assertEqual(evaluated, [True, True, True])
        self.assertEqual(
            [policy._opening_q34_active(board) for board in boards],
            [True, True, True],
        )
        self.assertEqual(
            [policy._fixed_quest_head(board).id for board in boards],
            [34, 34, 34],
        )
        self.assertTrue(all(
            not any(
                "fundraising" in claim.category
                or claim.category.startswith("mining-")
                or claim.category.startswith("stored-")
                for claim in policy._enumerate_live_store_claims(board)
            )
            for board in boards
        ))

    def _frozen_armed_q34_board(self):
        evidence = Path(
            "evidence/evidence-home-armed-reenter-loop-20260814.jsonl"
        )
        with evidence.open(encoding="utf-8") as records:
            decisions = [json.loads(record) for record in records]
        self.assertEqual(len(decisions), 219)
        tail = [
            row for row in decisions
            if row.get("decision_sequence") in {215, 216, 217}
        ]
        self.assertEqual(
            [(row["decision_sequence"], row["key"]) for row in tail],
            [(215, "1"), (216, ""), (217, LEAVE_STORE_KEY)],
        )

        target = tail[0]
        board = self._measured_q34_opening()
        return replace(
            board,
            turn=target["turn"],
            player=replace(board.player, gold=target["player"]["gold"]),
            inventory=[
                item("b", TVAL_LITE, SV_LITE_TORCH, count=7, fuel=1500),
                item("c", TVAL_LITE, SV_LITE_TORCH, count=13, fuel=2500),
            ],
        )

    def test_frozen_armed_q34_board_rejects_fundraising_and_leaves_home_cycle(self):
        self.skipTest(
            "source artifact destroyed 2026-08-17; rebuild from a future capture"
        )
        snapshot = self._frozen_armed_q34_board()
        policy = self._policy()

        self.assertTrue(policy._opening_q34_active(snapshot))
        self.assertEqual(policy._opening_q34_torch_shortage(snapshot), 0)
        self.assertFalse(policy._start_fundraising(snapshot))
        claims = policy._enumerate_live_store_claims(snapshot)
        self.assertEqual(claims, [])
        self.assertEqual(policy._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertIsNone(policy._fundraising_mode)

        released = replace(
            snapshot,
            quests={
                **snapshot.quests,
                34: QuestState(
                    id=34, status=QUEST_STATUS_FINISHED, fixed=True, level=5
                ),
            },
        )
        resumed = self._policy()
        self.assertTrue(resumed._start_fundraising(released))
        resumed_claims = resumed._enumerate_live_store_claims(snapshot)
        self.assertFalse(
            any("fundraising" in claim.category or claim.category.startswith("mining-")
                or claim.category.startswith("stored-") for claim in resumed_claims),
            resumed_claims,
        )
        self.assertEqual(resumed._next_required_store_type(snapshot), STORE_GENERAL)
        self.assertIsNone(resumed._fundraising_mode)

        keys = [policy.choose_key(replace(snapshot, turn=snapshot.turn + offset))
                for offset in range(3)]
        self.assertEqual(keys, ["5", "5", "5"])
        self.assertEqual(policy.last_reason, "opening-q34:wait")
        self.assertNotIn(LEAVE_STORE_KEY, keys)
        self.assertNotIn("", keys)

    @staticmethod
    def _ninth_strike_monrace_ids(value):
        if isinstance(value, dict):
            race_id = value.get("race_id")
            if isinstance(race_id, int):
                yield race_id
            for nested in value.values():
                yield from ApprovedQuestStrategyExecutionTest._ninth_strike_monrace_ids(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from ApprovedQuestStrategyExecutionTest._ninth_strike_monrace_ids(nested)

    def _warmed_ninth_strike_replay(self):
        artifact = Path("evidence/evidence-ninth-strike-snapshots.jsonl")
        raw_rows = [
            json.loads(line)
            for line in artifact.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(raw_rows), 137)
        policy = self._policy()
        boards = []
        for raw in raw_rows:
            knowledge = {
                race_id: MonraceKnowledge(1, 110, False, False)
                for race_id in set(self._ninth_strike_monrace_ids(raw))
            }
            boards.append(policy._with_grid_memory(parse_snapshot(raw, knowledge)))
        return policy, boards

    def test_ninth_strike_archive_opening_claim_gate_and_decisions(self):
        self.skipTest(
            "source artifact destroyed 2026-08-17; rebuild from a future capture"
        )
        policy, boards = self._warmed_ninth_strike_replay()
        outside = [board for board in boards if board.store is None][-2:]

        self.assertTrue(all(policy._opening_q34_active(board) for board in outside))
        self.assertEqual(
            [policy._enumerate_live_store_claims(board) for board in outside],
            [[], []],
        )
        self.assertEqual(
            [policy._next_required_store_type(board) for board in outside],
            [STORE_GENERAL, STORE_GENERAL],
        )
        keys = [policy.choose_key(board) for board in outside]
        self.assertEqual(keys, ["5", "5"])
        self.assertEqual(policy.last_reason, "opening-q34:wait")

    def test_ninth_strike_archive_finished_q34_restores_claims_unchanged(self):
        self.skipTest(
            "source artifact destroyed 2026-08-17; rebuild from a future capture"
        )
        policy, boards = self._warmed_ninth_strike_replay()
        outside = next(board for board in reversed(boards) if board.store is None)
        finished = replace(
            outside,
            quests={
                34: QuestState(
                    id=34, status=QUEST_STATUS_FINISHED, fixed=True, level=5
                )
            },
        )

        restored = policy._enumerate_live_store_claims(finished)
        self.assertFalse(policy._opening_q34_active(finished))
        restored_categories = Counter(claim.category for claim in restored)
        expected_suppressed = Counter({
                "identification-withdrawal": 1,
                "recall": 2,
                "teleport": 1,
                "cure-critical": 2,
                "oil": 1,
                "food": 1,
                "quest-speed": 1,
                "quest-healing": 2,
                "equipment-catalog": 1,
                "black-market": 1,
        })
        self.assertEqual(
            Counter({
                category: restored_categories[category]
                for category in expected_suppressed
            }),
            expected_suppressed,
        )

    def test_ninth_strike_archive_opening_hunger_precedes_claim_gate(self):
        self.skipTest(
            "source artifact destroyed 2026-08-17; rebuild from a future capture"
        )
        policy, boards = self._warmed_ninth_strike_replay()
        outside = next(board for board in reversed(boards) if board.store is None)
        hungry = replace(
            outside,
            player=replace(outside.player, food_state="hungry"),
            inventory=[item for item in outside.inventory if item.tval != TVAL_FOOD],
        )

        self.assertTrue(policy._opening_q34_active(hungry))
        self.assertEqual(policy._enumerate_live_store_claims(hungry), [])
        self.assertEqual(policy._next_required_store_type(hungry), STORE_GENERAL)

    def test_finished_q34_capture_releases_fundraising_start_and_claims(self):
        self.skipTest(
            "source artifact destroyed 2026-08-17; rebuild from a future capture"
        )
        captured = self._frozen_armed_q34_board()
        finished = replace(
            captured,
            quests={
                **captured.quests,
                34: QuestState(
                    id=34, status=QUEST_STATUS_FINISHED, fixed=True, level=5
                ),
            },
        )
        policy = self._policy()

        self.assertFalse(policy._opening_q34_active(finished))
        self.assertTrue(policy._start_fundraising(finished))
        claims = policy._enumerate_live_store_claims(finished)
        self.assertIn("fundraising-kit", {claim.category for claim in claims})
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_q34_opening_weaponless_home_recovery_rearms_exactly(self):
        policy = self._policy()
        opening = replace(self._measured_q34_opening(), equipment=[])
        home_weapon = item(
            "a", TVAL_SWORD, 1,
            name="short sword", is_equipment=True,
        )
        home = replace(
            opening,
            store=StoreState(
                STORE_HOME,
                [
                    store_item(
                        "a", TVAL_SWORD, 1,
                        name="short sword", count=1, price=0,
                    )
                ],
            ),
        )

        self.assertEqual(policy._next_required_store_type(opening), STORE_HOME)
        self.assertEqual(policy.choose_key(home), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home-errand:filed:combat-weapon")
        self.assertIn(
            "home-errand:combat-weapon", policy._owner_expectations._pending
        )
        self.assertNotEqual(policy.last_reason, "home:store-context-exit")
        policy.consume_home_knowledge((home_weapon,))
        policy._home_page_size = 12
        policy._shopping_approach_store_type = STORE_HOME
        entrance = replace(
            opening,
            grids={
                opening.player.position: replace(
                    grid(10, 9), store_number=STORE_HOME,
                ),
                Position(11, 10): grid(11, 10, building_special=34),
            },
        )
        self.assertEqual(
            policy._atomic_home_withdraw_key(
                entrance, entrance.player.position,
            ),
            WAIT_KEY,
        )
        armed_pack = replace(entrance, inventory=[home_weapon])
        self.assertEqual(policy._opening_q34_town_key(armed_pack, []), "wa")
        self.assertNotEqual(policy.last_reason, "shop:approach")

    def test_q34_opening_releases_stale_withdraw_terminal(self):
        policy = self._policy()
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._home_knowledge_items = []
        opening = self._measured_q34_opening()
        policy._town_blocked_reason = (
            "equipment-transaction:withdraw-item-unobserved:home:stale:0"
        )

        self.assertEqual(policy.choose_key(opening), "6")
        self.assertFalse(policy.last_reason.startswith("town:blocked:"))
        self.assertIsNone(policy._town_blocked_reason)

    def test_fresh_q34_torch_shortage_blocks_fundraising_start(self):
        policy = self._policy()
        quest = QuestState(id=34, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5)
        snapshot = Snapshot(
            player(
                10, 10, level=1, class_id=PLAYER_CLASS_WARRIOR,
                gold=FUNDRAISING_START_GOLD - 1,
            ),
            {Position(10, 10): grid(10, 10, building_special=34)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            quests={34: quest},
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=19, fuel=5000)],
        )

        self.assertFalse(policy._start_fundraising(snapshot))
        self.assertIsNone(policy._fundraising_mode)

    def test_fresh_q34_stockout_waits_and_retries_only_general_store(self):
        policy = self._policy()
        quest = QuestState(
            id=34, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
        )
        snapshot = Snapshot(
            player(
                10, 10, level=1, class_id=PLAYER_CLASS_WARRIOR, gold=100
            ),
            {
                Position(10, 10): grid(10, 10),
                Position(11, 10): grid(11, 10, building_special=34),
            },
            [],
            turn=100,
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            quests={34: quest},
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=6, fuel=5000)
            ],
        )
        policy._town_store_attempted[STORE_GENERAL] = snapshot.turn
        policy._town_errand_plan = policy_module.TownErrandPlan(
            [STORE_GENERAL], index=1
        )

        self.assertIsNone(policy._next_required_store_type(snapshot))
        wait_until = policy._town_restock_wait_until
        self.assertEqual(
            policy._town_special_key(replace(snapshot, turn=snapshot.turn + 1)),
            RESTOCK_WAIT_MACRO,
        )
        self.assertTrue(policy.last_reason.startswith("town:wait-restock:"))
        self.assertEqual(
            policy._next_required_store_type(replace(snapshot, turn=wait_until)),
            STORE_GENERAL,
        )
        self.assertNotIn(STORE_GENERAL, policy._town_store_attempted)

        # A second genuine stockout starts another bounded wait rather than
        # falling through to unrelated shops or waiting forever without a
        # General Store re-check.
        retry = replace(snapshot, turn=wait_until)
        policy._town_store_attempted[STORE_GENERAL] = retry.turn
        self.assertIsNone(policy._next_required_store_type(retry))
        second_wait_until = policy._town_restock_wait_until
        self.assertEqual(
            policy._next_required_store_type(
                replace(retry, turn=second_wait_until)
            ),
            STORE_GENERAL,
        )

    def test_fresh_q34_precedes_same_level_q1_transaction_head(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(10, 10, level=1, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10),
                Position(11, 10): grid(11, 10, building_special=1),
                Position(12, 10): grid(12, 10, building_special=34),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            quests={
                1: QuestState(
                    id=1, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
                ),
                34: QuestState(
                    id=34, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
                ),
            },
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
            ],
        )

        self.assertEqual(policy._fixed_quest_head(snapshot).id, 34)

    def test_fresh_q34_acceptance_does_not_require_dungeon_departure_kit(self):
        policy = self._policy()
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34],
            placed_monsters=((174, 1), (243, 1), (107, 2)),
        )
        snapshot = self._force_snapshot(
            34, hp=85, torches=20, speed=0, healing=0
        )
        snapshot = replace(
            snapshot,
            player=replace(
                snapshot.player, level=1, class_id=PLAYER_CLASS_WARRIOR
            ),
            grids={Position(1, 1): grid(1, 1, building_special=34)},
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            quests={
                34: QuestState(
                    id=34, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
                )
            },
            inventory=snapshot.inventory[:1],
        )
        policy._combat_weapon_ready = lambda _snapshot: True

        with (
            patch.object(policy, "_town_departure_ready", return_value=False),
            patch("hengbot.policy.weapon_expected_dps", return_value=22.0),
            patch.object(policy, "_main_hand_dps", return_value=22.0),
        ):
            self.assertTrue(policy._fixed_quest_ready(snapshot, 34))

        self.assertNotEqual(
            policy.fixed_quest_readiness_state().get("reason"), "departure"
        )

    def test_approved_q2_is_not_blocked_by_incomplete_home_administration(self):
        policy = self._policy()
        policy._quest_knowledge[2] = replace(
            policy._quest_knowledge[34], id=2, placed_monsters=((174, 8),)
        )
        snapshot = self._force_snapshot(
            2, hp=400, torches=0, speed=2, healing=2,
        )
        snapshot = replace(snapshot, town_flag=True, town_id=1)
        policy._combat_weapon_ready = lambda _snapshot: True
        threat_group_sizes = []

        def predicted_threat(_snapshot, monsters, _turns):
            threat_group_sizes.append(len(monsters))
            return {"operational_total": 100 * len(monsters)}

        with (
            patch.object(policy, "_town_departure_ready", return_value=False),
            patch.object(policy, "_approved_strategy_force_ready", return_value=True),
            patch.object(policy, "threat_prediction", side_effect=predicted_threat),
            patch.object(policy, "_main_hand_dps", return_value=999.0),
        ):
            self.assertTrue(policy._fixed_quest_ready(snapshot, 2))

        self.assertEqual(max(threat_group_sizes), 1)
        self.assertEqual(
            policy.fixed_quest_readiness_state().get("reason"), "ready"
        )

    def test_procurement_uses_only_the_first_currently_offered_quest(self):
        policy = self._policy()
        quests = {
            quest_id: QuestState(
                id=quest_id, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
            )
            for quest_id in (1, 34)
        }
        snapshot = Snapshot(
            player(10, 10, level=2, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(10, 10): grid(10, 10, building_special=1),
                Position(10, 11): grid(10, 11, building_special=34),
            },
            [], floor_key=(0, 0, 0), town_flag=True, quests=quests,
        )

        strategy = policy._carry_procurement_strategy(snapshot)

        self.assertIsNotNone(strategy)
        self.assertEqual(strategy.quest_id, 1)
        self.assertEqual(strategy.required_force["throwing_items"]["lit_torch"], 5)
        self.assertEqual(strategy.required_force["speed_potions"], 1)
        self.assertEqual(strategy.required_force["heal_potions"], 2)
        torch = StoreItem(
            "a", "Torch", 99, TVAL_LITE, SV_LITE_TORCH,
            price=1, aware=True, known=True,
        )
        self.assertEqual(policy._purchase_quantity(snapshot, torch), 10)
        needs = policy._enumerate_town_needs(snapshot)
        self.assertIn(
            policy_module.TownNeed(STORE_GENERAL, "quest-throwing-items", "normal"),
            needs,
        )
        self.assertIn(
            policy_module.TownNeed(STORE_BLACK, "quest-speed", "normal"), needs
        )

    def _q2_carry_snapshot(self):
        return Snapshot(
            player(10, 10, hp=218, max_hp=218, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 2),
            inventory=[
                item(
                    "b", TVAL_BOLT, 0, count=99, to_d=3,
                    damage_dice_num=1, damage_dice_sides=5,
                ),
                item("l", TVAL_SCROLL, SV_SCROLL_LIGHT, count=6),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2),
                item("w", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=3),
                item("s", TVAL_POTION, SV_POTION_SPEED, count=2),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=2),
            ],
            equipment=[
                item("main_hand", TVAL_SWORD, 1, is_equipment=True),
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True, to_d=3,
                ),
            ],
        )

    def test_q2_readiness_requires_launcher_ammo_scrolls_and_wall_breach(self):
        policy = self._policy()
        profile = self.profiles[2]
        base = self._q2_carry_snapshot()
        with patch("hengbot.policy.weapon_expected_dps", return_value=50):
            self.assertTrue(policy._approved_strategy_force_ready(base, profile))
            digger_ready = replace(
                base,
                inventory=[*base.inventory[:3], *base.inventory[4:]],
                equipment=[
                    base.equipment[1],
                    item(
                        "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                        is_equipment=True, pval=3,
                    ),
                ],
            )
            self.assertTrue(
                policy._approved_strategy_force_ready(digger_ready, profile)
            )
            weak_digger = replace(
                digger_ready,
                equipment=[
                    digger_ready.equipment[0],
                    replace(digger_ready.equipment[1], pval=2),
                ],
            )
            self.assertFalse(
                policy._approved_strategy_force_ready(weak_digger, profile)
            )
            variants = {
                "launcher": replace(base, equipment=base.equipment[:1]),
                "throwing_items.launcher_ammo": replace(
                    base, inventory=[replace(base.inventory[0], count=98), *base.inventory[1:]]
                ),
                "required_scrolls.light": replace(
                    base, inventory=[base.inventory[0], replace(base.inventory[1], count=5), *base.inventory[2:]]
                ),
                "required_scrolls.teleport": replace(
                    base, inventory=[*base.inventory[:2], replace(base.inventory[2], count=1), *base.inventory[3:]]
                ),
                "utility_tools.wall_breach": replace(
                    base, inventory=[*base.inventory[:3], *base.inventory[4:]]
                ),
            }
            for missing, snapshot in variants.items():
                with self.subTest(missing=missing):
                    self.assertFalse(
                        policy._approved_strategy_force_ready(snapshot, profile)
                    )
                    self.assertIn(
                        missing,
                        policy.fixed_quest_readiness_state()["strategy_force"]["failed"],
                    )

    def test_q2_average_shot_damage_gate_reports_carried_ammo_measurement(self):
        policy = self._policy()
        profile = self.profiles[2]
        ready = self._q2_carry_snapshot()
        entry = replace(
            ready,
            inventory=[replace(ready.inventory[0], to_d=0), *ready.inventory[1:]],
        )
        near = replace(
            ready,
            inventory=[replace(ready.inventory[0], to_d=2), *ready.inventory[1:]],
        )

        for snapshot, measured, expected_ready in (
            (entry, 18.0, False),
            (near, 24.0, False),
            (ready, 27.0, True),
        ):
            with self.subTest(measured=measured):
                status = policy._quest_carry_status(
                    snapshot, profile.required_force
                )["launcher.average_damage"]
                self.assertEqual(status["measured"], measured)
                self.assertEqual(status["required"], 25.0)
                self.assertEqual(status["ready"], expected_ready)

        with patch("hengbot.policy.weapon_expected_dps", return_value=50):
            self.assertFalse(
                policy._approved_strategy_force_ready(near, profile)
            )
        readiness = policy.fixed_quest_readiness_state()["strategy_force"]
        self.assertIn("launcher.average_damage", readiness["failed"])
        self.assertEqual(
            readiness["carries"]["launcher.average_damage"],
            {"measured": 24.0, "required": 25.0, "ready": False},
        )

    def test_q2_unmet_average_damage_continues_into_real_shop_progression(self):
        gremlin = MonraceKnowledge(
            25,
            110,
            False,
            False,
            level=8,
            max_melee_damage=1,
            can_multiply=True,
            average_hp=15,
            armor_class=30,
        )
        policy = HengbotPolicy(
            quest_strategies=self.profiles,
            quest_knowledge={
                2: QuestInfo(
                    2,
                    "The Sewer",
                    6,
                    15,
                    QUEST_FLAG_ONCE,
                    placed_monsters=((153, 1),),
                )
            },
            monrace_knowledge={153: gremlin},
        )
        prepared = self._q2_carry_snapshot()
        near = replace(
            prepared,
            player=replace(
                prepared.player,
                level=20,
                gold=10000,
                main_hand_blows=10,
                main_hand_to_h=100,
                main_hand_to_d=20,
                melee_skill=200,
            ),
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): replace(
                    grid(10, 11), store_number=STORE_WEAPON
                ),
            },
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            visited_town_ids=(0, 1),
            inventory=[
                replace(prepared.inventory[0], to_d=2),
                *prepared.inventory[1:],
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=3),
                item("f", TVAL_FOOD, 35, count=5),
            ],
            equipment=[
                item(
                    "main_hand",
                    TVAL_SWORD,
                    1,
                    is_equipment=True,
                    damage_dice_num=10,
                    damage_dice_sides=10,
                    to_h=10,
                    to_d=10,
                ),
                prepared.equipment[1],
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    is_equipment=True,
                    fuel=5000,
                ),
            ],
            quests={
                2: QuestState(
                    2,
                    status=QUEST_STATUS_UNTAKEN,
                    fixed=True,
                    level=15,
                )
            },
        )

        key = policy.choose_key(near)
        readiness = policy.fixed_quest_readiness_state()

        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertFalse(readiness["verdict"])
        self.assertEqual(readiness["reason"], "strategy-force")
        self.assertIn(
            "launcher.average_damage",
            readiness["strategy_force"]["failed"],
        )
        self.assertEqual(
            readiness["strategy_force"]["carries"][
                "launcher.average_damage"
            ],
            {"measured": 24.0, "required": 25.0, "ready": False},
        )
        self.assertIsNone(policy._town_blocked_reason)

    def test_q2_wall_breach_checks_black_market_then_falls_back_to_general(self):
        policy = self._policy()
        profile = self.profiles[2]
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=10000),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
        )
        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            needs = policy._enumerate_town_needs(snapshot)
        self.assertIn(TownNeed(STORE_WEAPON, "quest-ranged-kit", "normal"), needs)
        self.assertIn(TownNeed(STORE_ALCHEMIST, "quest-scrolls", "normal"), needs)
        self.assertIn(TownNeed(STORE_BLACK, "quest-carry", "normal"), needs)
        self.assertNotIn(TownNeed(STORE_MAGIC, "quest-carry", "normal"), needs)
        self.assertNotIn(TownNeed(STORE_GENERAL, "quest-carry", "normal"), needs)

        policy._town_store_attempted[STORE_BLACK] = snapshot.turn
        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            fallback = policy._enumerate_town_needs(snapshot)
        self.assertNotIn(TownNeed(STORE_BLACK, "quest-carry", "normal"), fallback)
        self.assertIn(TownNeed(STORE_GENERAL, "quest-carry", "normal"), fallback)

    def test_q2_black_market_buys_stone_to_mud_when_present(self):
        policy = self._policy()
        profile = self.profiles[2]
        wand = StoreItem(
            "w", "Stone to Mud (4 charges)", 1,
            TVAL_WAND, SV_WAND_STONE_TO_MUD, price=900, charges=4,
        )
        unrelated = StoreItem(
            "x", "Magic Missile (8 charges)", 1,
            TVAL_WAND, 15, price=200, charges=8,
        )
        strong_digger = StoreItem(
            "d", "Dwarven Shovel (+3)", 1,
            TVAL_DIGGING, 3, price=500, pval=3,
        )
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=10000),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            store=StoreState(STORE_BLACK, [strong_digger, unrelated, wand]),
        )

        self.assertEqual(policy._quest_carry_purchase(snapshot, profile), wand)

    def test_black_market_stone_to_mud_is_not_q2_only(self):
        policy = self._policy()
        wand = StoreItem(
            "w", "Stone to Mud (4 charges)", 1,
            TVAL_WAND, SV_WAND_STONE_TO_MUD, price=900, charges=4,
        )
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=10000),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            store=StoreState(STORE_BLACK, [wand]),
        )

        with patch.object(policy, "_carry_procurement_strategy", return_value=None):
            self.assertEqual(policy._next_purchase_unreserved(snapshot), wand)
            carried = replace(
                snapshot,
                inventory=[item("w", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=2)],
            )
            self.assertIsNone(policy._next_purchase_unreserved(carried))

    def test_q2_digger_fallback_requires_plus_three(self):
        policy = self._policy()
        profile = self.profiles[2]
        weak = StoreItem(
            "a", "Pick (+2)", 1, TVAL_DIGGING, 4, price=50, pval=2,
        )
        strong = StoreItem(
            "b", "Dwarven Shovel (+3)", 1,
            TVAL_DIGGING, 3, price=500, pval=3,
        )
        base = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=10000),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True,
            store=StoreState(STORE_GENERAL, [weak]),
        )

        self.assertIsNone(policy._quest_carry_purchase(base, profile))
        self.assertEqual(
            policy._quest_carry_purchase(
                replace(base, store=StoreState(STORE_GENERAL, [weak, strong])),
                profile,
            ),
            strong,
        )

    @staticmethod
    def _q2_breach_navigator():
        battlefield = QuestBattlefield(
            terrain={
                (5, 47): "wall", (5, 48): "floor",
                (6, 47): "floor", (7, 47): "wall",
                (8, 47): "wall", (9, 47): "wall",
                (10, 47): "wall", (11, 47): "wall",
                (12, 47): "floor",
            },
            player_start=(5, 48), entrance=(5, 48), exit=(5, 48),
        )
        navigator = QuestFloorNavigator(2, battlefield)
        navigator.reset_for_floor((0, 1, 2))
        return navigator

    def test_q2_breach_wand_is_one_macro_and_requires_grid_confirmation(self):
        policy = self._policy()
        navigator = self._q2_breach_navigator()
        grids = {
            Position(6, 47): grid(6, 47),
            **{
                Position(y, 47): grid(y, 47, passable=False, can_dig=True)
                for y in range(7, 12)
            },
        }
        snapshot = Snapshot(
            player(6, 47), grids, [], floor_key=(0, 1, 2),
            inventory=[item("w", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=3)],
        )

        self.assertEqual(policy._q2_breach_key(snapshot, navigator), "aw2")
        self.assertFalse(policy._q2_breach_complete)
        still_closed = replace(
            snapshot,
            inventory=[item("w", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=2)],
        )
        self.assertEqual(policy._q2_breach_key(still_closed, navigator), "aw2")
        self.assertFalse(policy._q2_breach_complete)
        opened = replace(
            still_closed,
            grids={**grids, Position(7, 47): grid(7, 47)},
        )
        self.assertEqual(policy._q2_breach_key(opened, navigator), "2")
        self.assertEqual(policy.last_reason, "quest-strategy:q2-breach-approach")
        next_wall = replace(opened, player=player(7, 47))
        self.assertEqual(policy._q2_breach_key(next_wall, navigator), "aw2")
        confirmed = replace(
            next_wall,
            player=player(10, 47),
            grids={
                Position(y, 47): grid(y, 47)
                for y in range(6, 12)
            },
            inventory=[item("w", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=1)],
        )
        self.assertIsNone(policy._q2_breach_key(confirmed, navigator))
        self.assertTrue(policy._q2_breach_complete)
        self.assertIn(Position(11, 47), navigator.opened)

    def test_q2_breach_digging_rejects_plus_two_and_uses_equipped_plus_three(self):
        policy = self._policy()
        navigator = self._q2_breach_navigator()
        grids = {
            Position(6, 47): grid(6, 47),
            Position(7, 47): grid(7, 47, passable=False, can_dig=True),
        }
        weak = Snapshot(
            player(6, 47), grids, [], floor_key=(0, 1, 2),
            equipment=[
                item(
                    "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
                    is_equipment=True, pval=2,
                )
            ],
        )
        self.assertEqual(policy._q2_breach_key(weak, navigator), WAIT_KEY)
        self.assertEqual(policy.last_reason, "quest:blocked:q2-breach-tool")

        strong = replace(
            weak,
            equipment=[replace(weak.equipment[0], pval=3)],
        )
        self.assertEqual(policy._q2_breach_key(strong, navigator), "T2")
        self.assertEqual(policy.last_reason, "quest-strategy:q2-breach-dig")

    def test_q2_breach_wield_uses_its_dedicated_goal(self):
        policy = self._policy()
        navigator = self._q2_breach_navigator()
        strong = item(
            "d", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            is_equipment=True, pval=3,
        )
        snap = Snapshot(
            player(6, 47),
            {
                Position(6, 47): grid(6, 47),
                Position(7, 47): grid(7, 47, passable=False, can_dig=True),
            },
            [], floor_key=(0, 1, 2), inventory=[strong],
        )
        with patch.object(policy, "_equipment_wield", return_value="wd") as wield:
            self.assertEqual(policy._q2_breach_key(snap, navigator), "wd")
        self.assertEqual(wield.call_args.args[1], "q2-breach-loadout")

    def test_q2_breach_advances_after_opening_adjacent_wall_before_digging_again(self):
        policy = self._policy()
        navigator = self._q2_breach_navigator()
        tool = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL,
            is_equipment=True, pval=3,
        )
        grids = {
            Position(6, 47): grid(6, 47),
            Position(7, 47): grid(7, 47),
            Position(8, 47): grid(8, 47, passable=False, can_dig=True),
            Position(9, 47): grid(9, 47, passable=False, can_dig=True),
            Position(10, 47): grid(10, 47, passable=False, can_dig=True),
            Position(11, 47): grid(11, 47, passable=False, can_dig=True),
        }
        snapshot = Snapshot(
            player(6, 47), grids, [], floor_key=(0, 1, 2), equipment=[tool],
        )

        self.assertEqual(policy._q2_breach_key(snapshot, navigator), "2")
        self.assertEqual(policy.last_reason, "quest-strategy:q2-breach-approach")

        advanced = replace(snapshot, player=player(7, 47))
        self.assertEqual(policy._q2_breach_key(advanced, navigator), "T2")
        self.assertEqual(policy.last_reason, "quest-strategy:q2-breach-dig")

    def test_q2_real_map_phase_replay_clears_every_placement_via_breach(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        battlefield = q2.battlefield
        self.assertIsNotNone(battlefield)
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        profile = self.profiles[2]
        navigator = QuestFloorNavigator(2, battlefield)
        navigator.reset_for_floor((0, 1, 2))
        placements = {
            race_id: [Position(*position) for position, placed in battlefield.monster_placements
                      if placed == race_id]
            for race_id in profile.priority_targets
        }
        wand = item("w", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=3)

        def observe(placement):
            if navigator._static_walkable(placement):
                standing = placement
                placement_grid = grid(placement.y, placement.x)
            else:
                goals = navigator.ranged_vantage_goals(
                    placement, RANGED_MAX_DISTANCE
                ) or navigator.observation_goals(
                    placement, RANGED_MAX_DISTANCE
                )
                standing = min(
                    goals,
                    key=lambda position: position.distance_to(placement),
                )
                placement_grid = grid(
                    placement.y, placement.x, passable=False, in_view=True
                )
            snapshot = Snapshot(
                player(standing.y, standing.x, hp=300, max_hp=300),
                {
                    standing: grid(standing.y, standing.x),
                    placement: placement_grid,
                },
                [], floor_key=(0, 1, 2), inventory=[wand],
            )
            return policy._q2_phase_key(snapshot, profile, navigator)

        for race_id in profile.priority_targets[:2]:
            for placement in placements[race_id]:
                action = observe(placement)
        breach_ready = Snapshot(
            player(6, 47, hp=300, max_hp=300),
            {
                Position(6, 47): grid(6, 47),
                **{
                    Position(y, 47): grid(y, 47, passable=False, can_dig=True)
                    for y in range(7, 12)
                },
            },
            [], floor_key=(0, 1, 2), inventory=[wand],
        )
        action = policy._q2_phase_key(breach_ready, profile, navigator)
        self.assertEqual(action, "aw2")
        self.assertFalse(policy._q2_breach_complete)

        opened = Snapshot(
            player(6, 47, hp=300, max_hp=300),
            {
                Position(6, 47): grid(6, 47),
                Position(7, 47): grid(7, 47),
                **{
                    Position(y, 47): grid(y, 47, passable=False, can_dig=True)
                    for y in range(8, 12)
                },
            },
            [], floor_key=(0, 1, 2), inventory=[replace(wand, charges=2)],
        )
        self.assertEqual(policy._q2_phase_key(opened, profile, navigator), "2")
        next_wall = replace(
            opened,
            player=player(7, 47, hp=300, max_hp=300),
        )
        self.assertEqual(policy._q2_phase_key(next_wall, profile, navigator), "aw2")
        confirmed = replace(
            next_wall,
            player=player(10, 47, hp=300, max_hp=300),
            grids={
                Position(y, 47): grid(y, 47)
                for y in range(6, 12)
            },
            inventory=[replace(wand, charges=1)],
        )
        policy._q2_phase_key(confirmed, profile, navigator)
        self.assertTrue(policy._q2_breach_complete)

        blue_confirmed = Snapshot(
            player(13, 47, hp=300, max_hp=300),
            {
                Position(13, 47): grid(13, 47),
                Position(12, 47): grid(12, 47, in_view=True),
            },
            [], floor_key=(0, 1, 2), inventory=[replace(wand, charges=1)],
        )
        self.assertEqual(
            policy._q2_phase_key(blue_confirmed, profile, navigator), WAIT_KEY
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-blue-clear-confirmed"
        )
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            placement
            for _, _, placements in policy_module.Q2_POST_BLUE_SEQUENCE
            for placement in placements
        )

        for race_id in profile.priority_targets[3:]:
            for placement in placements[race_id]:
                observe(placement)

        self.assertEqual(policy._q2_cleared_races, set(profile.priority_targets))
        self.assertTrue(
            all(
                not navigator._static_walkable(placement)
                for race_id in (944, 1044)
                for placement in placements[race_id]
            )
        )

    def test_q2_post_blue_sequence_covers_every_deep_water_puddle(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        battlefield = load_quest_knowledge(definitions)[2].battlefield
        self.assertIsNotNone(battlefield)
        placed_puddles = {
            Position(*position)
            for position, race_id in battlefield.monster_placements
            if race_id == 944
        }
        planned_puddles = {
            placement
            for _, race_id, placements in policy_module.Q2_POST_BLUE_SEQUENCE
            if race_id == 944
            for placement in placements
        }

        self.assertEqual(planned_puddles, placed_puddles)

    def test_unready_q22_returns_from_target_town_instead_of_wandering(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(10, 10, level=17),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=3,
            quests={
                22: QuestState(
                    id=22,
                    status=QUEST_STATUS_UNTAKEN,
                    fixed=True,
                    level=18,
                )
            },
        )

        with patch.object(
            policy, "_fixed_quest_ready_for_travel", return_value=False
        ), patch.object(
            policy, "_town_teleport_key", return_value="TRAVEL"
        ) as travel:
            self.assertEqual(policy._fixed_quest_key(snapshot, []), "TRAVEL")

        travel.assert_called_once_with(snapshot, 0)
        self.assertEqual(policy.last_reason, "fixedquest:prepare-return")

    def test_unready_q22_does_not_leave_base_town(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(10, 10, level=17),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            quests={
                22: QuestState(
                    id=22,
                    status=QUEST_STATUS_UNTAKEN,
                    fixed=True,
                    level=18,
                )
            },
        )

        with patch.object(
            policy, "_fixed_quest_ready_for_travel", return_value=False
        ), patch.object(policy, "_town_teleport_key") as travel:
            self.assertIsNone(policy._fixed_quest_key(snapshot, []))

        travel.assert_not_called()

    def test_unready_q2_does_not_leave_base_town(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(10, 10, level=7),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            visited_town_ids=frozenset({0, 1}),
            quests={
                2: QuestState(
                    id=2,
                    status=QUEST_STATUS_UNTAKEN,
                    fixed=True,
                    level=15,
                )
            },
        )

        with patch.object(
            policy, "_fixed_quest_ready_for_travel", return_value=False
        ), patch.object(policy, "_town_teleport_key") as travel:
            self.assertIsNone(policy._fixed_quest_key(snapshot, []))

        travel.assert_not_called()

    def test_unready_q1_blocks_ready_q2_instead_of_skipping_ahead(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(10, 10, level=8),
            {
                Position(10, 10): grid(10, 10, building_special=1),
            },
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            visited_town_ids=frozenset({0, 1}),
            quests={
                1: QuestState(
                    id=1, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
                ),
                2: QuestState(
                    id=2, status=QUEST_STATUS_UNTAKEN, fixed=True, level=15
                ),
            },
        )
        readiness_checks = []

        def ready_for_travel(_snapshot, quest_id):
            readiness_checks.append(quest_id)
            return quest_id == 2

        with patch.object(
            policy, "_fixed_quest_ready_for_travel", side_effect=ready_for_travel
        ), patch.object(policy, "_town_teleport_key") as travel:
            self.assertIsNone(policy._fixed_quest_key(snapshot, []))

        self.assertEqual(readiness_checks, [1])
        travel.assert_not_called()

    def test_q1_owns_procurement_while_q2_is_also_untaken(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(10, 10, level=8),
            {Position(10, 10): grid(10, 10, building_special=1)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            visited_town_ids=frozenset({0, 1}),
            quests={
                1: QuestState(
                    id=1, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
                ),
                2: QuestState(
                    id=2, status=QUEST_STATUS_UNTAKEN, fixed=True, level=15
                ),
            },
        )

        strategy = policy._carry_procurement_strategy(snapshot)

        self.assertIsNotNone(strategy)
        self.assertEqual(strategy.quest_id, 1)
        self.assertEqual(
            strategy.required_force["throwing_items"]["lit_torch"], 5
        )

    def test_unready_q1_in_telmora_returns_to_outpost_for_preparation(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(10, 10, level=8, gold=1000),
            {Position(10, 10): grid(10, 10, building_special=2)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=1,
            visited_town_ids=frozenset({0, 1}),
            quests={
                1: QuestState(
                    id=1, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
                ),
                2: QuestState(
                    id=2, status=QUEST_STATUS_UNTAKEN, fixed=True, level=15
                ),
            },
        )

        with patch.object(
            policy, "_fixed_quest_ready_for_travel", return_value=False
        ), patch.object(
            policy, "_town_teleport_key", return_value="HOME"
        ) as travel:
            self.assertEqual(policy._fixed_quest_key(snapshot, []), "HOME")

        travel.assert_called_once_with(snapshot, 0)
        self.assertEqual(policy.last_reason, "fixedquest:prepare-return")

    def test_ready_q22_travels_to_quest_town(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(10, 10, level=18),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            visited_town_ids=frozenset({0, 3}),
            quests={
                1: QuestState(
                    id=1, status=QUEST_STATUS_FINISHED, fixed=True, level=5
                ),
                22: QuestState(
                    id=22,
                    status=QUEST_STATUS_UNTAKEN,
                    fixed=True,
                    level=18,
                )
            },
        )

        with patch.object(
            policy, "_fixed_quest_ready_for_travel", return_value=True
        ), patch.object(
            policy, "_town_teleport_key", return_value="TRAVEL"
        ) as travel:
            self.assertEqual(policy._fixed_quest_key(snapshot, []), "TRAVEL")

        travel.assert_called_once_with(snapshot, 3)
        self.assertEqual(policy.last_reason, "fixedquest:q22-travel")

    def test_q2_lights_route_after_opening_fight_before_gremlin_is_visible(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(4, 8)},
            monster_placements=(((1, 7), 153),),
            player_start=(1, 4),
        )
        navigator = QuestFloorNavigator(2, battlefield)
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        snapshot = Snapshot(
            player(1, 5),
            {Position(1, 5): grid(1, 5)},
            [], floor_key=(0, 15, 2),
            inventory=[item("i", TVAL_SCROLL, SV_SCROLL_LIGHT, count=6)],
        )

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "ri"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-light-after-opening"
        )

    def test_q2_normal_entry_does_not_mistake_known_later_map_for_reconnect(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(4, 8)},
            monster_placements=(((1, 7), 153),),
            player_start=(1, 4),
        )
        navigator = QuestFloorNavigator(2, battlefield)
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        later = policy_module.Q2_POST_BLUE_SEQUENCE[-1][2][0]
        snapshot = Snapshot(
            player(1, 5),
            {
                Position(1, 5): grid(1, 5),
                later: grid(later.y, later.x),
            },
            [], floor_key=(0, 15, 2),
            inventory=[item("i", TVAL_SCROLL, SV_SCROLL_LIGHT, count=6)],
        )

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "ri"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-light-after-opening"
        )
        self.assertNotIn(153, policy._q2_cleared_races)
        self.assertFalse(policy._q2_breach_complete)

    def test_q2_reconnect_can_restore_progress_from_known_later_map(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(4, 8)},
            monster_placements=(((1, 7), 153),),
            player_start=(1, 4),
        )
        navigator = QuestFloorNavigator(2, battlefield)
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        later = policy_module.Q2_POST_BLUE_SEQUENCE[-1][2][0]
        snapshot = Snapshot(
            player(1, 5),
            {
                Position(1, 5): grid(1, 5),
                later: grid(later.y, later.x),
            },
            [], floor_key=(0, 15, 2),
            inventory=[item("i", TVAL_SCROLL, SV_SCROLL_LIGHT, count=6)],
        )
        policy._q2_reconnect_recovery_floor = snapshot.floor_key

        policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertIn(153, policy._q2_cleared_races)
        self.assertTrue(policy._q2_breach_complete)

    def test_q2_real_map_routes_to_observation_cell_for_isolated_gremlin(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.add(86)
        navigator = QuestFloorNavigator(2, q2.battlefield)
        snapshot = Snapshot(
            player(1, 5),
            {Position(1, 5): grid(1, 5)},
            [], floor_key=(0, 15, 2),
        )

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "6"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:q2-phase-153")

    def test_q2_phase_reroutes_after_repeated_static_step_does_not_move(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update({86, 153, 252, 213, 270, 175, 42})
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            placement
            for _, _, placements in policy_module.Q2_POST_BLUE_SEQUENCE
            for placement in placements
        )
        navigator = QuestFloorNavigator(2, q2.battlefield)
        # The live Q2 run opened this static wall, then Hengband rejected the
        # diagonal step to (7, 24) without changing the player position.
        navigator.opened.add(Position(6, 25))
        snapshot = Snapshot(
            player(6, 25, hp=382, max_hp=382),
            {
                Position(6, 25): grid(6, 25),
                Position(7, 24): grid(7, 24),
            },
            [],
            floor_key=(0, 15, 2),
        )

        attempts = [
            policy._q2_phase_key(snapshot, self.profiles[2], navigator)
            for _ in range(4)
        ]

        self.assertEqual(attempts[:3], ["1", "1", "1"])
        self.assertNotEqual(attempts[3], "1")
        self.assertNotEqual(attempts[3], WAIT_KEY)
        self.assertEqual(policy.last_reason, "quest-strategy:q2-phase-120")
        self.assertIn(
            Position(7, 24),
            policy._q2_phase_blocked_steps[((0, 15, 2), 120)],
        )

    def test_q2_white_crocodile_route_does_not_reverse_between_opened_cells(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update(self.profiles[2].priority_targets[:-1])
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            placement
            for _, _, placements in policy_module.Q2_POST_BLUE_SEQUENCE
            for placement in placements
        )
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.opened.update(Position(16, x) for x in range(8, 26))
        first_snapshot = Snapshot(
            player(16, 8, hp=392, max_hp=392),
            {
                **{
                    Position(16, x): grid(16, x, lit=True, in_view=True)
                    for x in range(8, 26)
                },
                Position(19, 11): grid(19, 11, in_view=False),
            },
            [], floor_key=(0, 15, 2),
        )
        second_snapshot = replace(first_snapshot, player=player(16, 9, hp=392, max_hp=392))

        first = policy._q2_phase_key(
            first_snapshot, self.profiles[2], navigator
        )
        second = policy._q2_phase_key(
            second_snapshot, self.profiles[2], navigator
        )

        self.assertNotEqual((first, second), ("6", "4"))
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-phase-1044"
        )

        restarted = self._policy()
        restarted._quest_knowledge[2] = q2
        restarted._q2_cleared_races.update(
            self.profiles[2].priority_targets[:-1]
        )
        restarted._q2_breach_complete = True
        restarted._q2_blue_recovery_complete = True
        restarted._q2_surveyed_placements.update(
            placement
            for _, _, placements in policy_module.Q2_POST_BLUE_SEQUENCE
            for placement in placements
        )
        restarted_navigator = QuestFloorNavigator(2, q2.battlefield)
        restarted_navigator.opened.update(
            Position(16, x) for x in range(8, 26)
        )
        at_corridor_end = replace(first_snapshot, player=player(16, 7, hp=392, max_hp=392))

        self.assertNotEqual(
            restarted._q2_phase_key(
                at_corridor_end, self.profiles[2], restarted_navigator
            ),
            WAIT_KEY,
        )

    def test_q2_breaches_immediately_after_visible_empty_gremlin_cell(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.add(86)
        navigator = QuestFloorNavigator(2, q2.battlefield)
        gremlin = Position(7, 50)
        snapshot = Snapshot(
            player(6, 47),
            {
                Position(6, 47): grid(6, 47),
                gremlin: grid(7, 50, in_view=True),
            },
            [], floor_key=(0, 15, 2),
            inventory=[
                item("w", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=17)
            ],
        )

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertEqual(key, "aw2")
        self.assertEqual(policy.last_reason, "quest-strategy:q2-breach-wand")
        self.assertIn(153, policy._q2_cleared_races)

    def test_q2_requires_seven_cells_down_before_confirming_blue_clear(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update({86, 153})
        policy._q2_breach_complete = True
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.opened.update(Position(y, 47) for y in range(7, 12))

        at_firing_point = Snapshot(
            player(6, 47), {Position(6, 47): grid(6, 47)}, [],
            floor_key=(0, 15, 2),
        )
        self.assertEqual(
            policy._q2_phase_key(
                at_firing_point, self.profiles[2], navigator
            ),
            "2",
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-blue-confirm-approach"
        )
        self.assertNotIn(252, policy._q2_cleared_races)

        confirmation = Snapshot(
            player(13, 47),
            {Position(13, 47): grid(13, 47)},
            [], floor_key=(0, 15, 2),
        )
        self.assertEqual(
            policy._q2_phase_key(confirmation, self.profiles[2], navigator),
            WAIT_KEY,
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-blue-clear-confirmed"
        )
        self.assertIn(252, policy._q2_cleared_races)
        self.assertFalse(navigator.allow_deep_water)

        recoverable = replace(
            confirmation,
            grids={
                Position(13, 47): grid(13, 47),
                Position(12, 47): grid(
                    12, 47, objects=1, object_tvals=(TVAL_BOLT,)
                ),
            },
        )
        self.assertEqual(
            policy._q2_phase_key(recoverable, self.profiles[2], navigator),
            "8",
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-blue-recover-bolts"
        )
        on_bolts = replace(recoverable, player=player(12, 47))
        self.assertEqual(
            policy._q2_phase_key(on_bolts, self.profiles[2], navigator),
            PICKUP_KEY,
        )
        policy.confirm_key_posted(PICKUP_KEY)
        recovered = replace(
            confirmation,
            grids={Position(13, 47): grid(13, 47)},
        )
        self.assertEqual(
            policy._q2_phase_key(recovered, self.profiles[2], navigator),
            WAIT_KEY,
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-blue-recovery-complete"
        )
        self.assertTrue(policy._q2_blue_recovery_complete)

    def test_q2_blue_recovery_ignores_bolts_outside_the_recovery_region(self):
        q2 = load_quest_knowledge(REAL_QUEST_DEFINITIONS)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update({86, 153})
        policy._q2_breach_complete = True
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.opened.update(Position(y, 47) for y in range(7, 12))
        confirmation = Snapshot(
            player(13, 47), {Position(13, 47): grid(13, 47)}, [],
            floor_key=(0, 15, 2),
        )
        policy._q2_phase_key(confirmation, self.profiles[2], navigator)
        policy._q2_blue_recovery_witnessed = True
        snapshot = Snapshot(
            player(13, 47),
            {
                Position(13, 47): grid(13, 47),
                Position(14, 47): grid(14, 47, objects=1,
                                       object_tvals=(TVAL_BOLT,)),
            }, [], floor_key=(0, 15, 2),
        )

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), WAIT_KEY
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-blue-recovery-complete"
        )

    def test_q2_blue_recovery_does_not_pick_up_identified_non_bolts(self):
        q2 = load_quest_knowledge(REAL_QUEST_DEFINITIONS)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update({86, 153})
        policy._q2_breach_complete = True
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.opened.update(Position(y, 47) for y in range(7, 12))
        confirmation = Snapshot(
            player(13, 47), {Position(13, 47): grid(13, 47)}, [],
            floor_key=(0, 15, 2),
        )
        policy._q2_phase_key(confirmation, self.profiles[2], navigator)
        policy._q2_blue_recovery_witnessed = True
        snapshot = Snapshot(
            player(12, 47),
            {Position(12, 47): grid(12, 47, objects=1,
                                    object_tvals=(TVAL_LITE,))},
            [], floor_key=(0, 15, 2),
        )

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), WAIT_KEY
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-blue-recovery-complete"
        )

    def test_q2_blue_recovery_requires_identification_and_pickup_witness(self):
        q2 = load_quest_knowledge(REAL_QUEST_DEFINITIONS)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update({86, 153})
        policy._q2_breach_complete = True
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.opened.update(Position(y, 47) for y in range(7, 12))
        confirmation = Snapshot(
            player(13, 47), {Position(13, 47): grid(13, 47)}, [],
            floor_key=(0, 15, 2),
        )
        policy._q2_phase_key(confirmation, self.profiles[2], navigator)
        unknown = Snapshot(
            player(13, 47),
            {Position(12, 47): grid(12, 47, objects=1, object_tvals=())},
            [], floor_key=(0, 15, 2),
        )

        self.assertEqual(
            policy._q2_phase_key(unknown, self.profiles[2], navigator), WAIT_KEY
        )
        self.assertEqual(
            policy.last_reason,
            "quest:blocked:q2-blue-recovery-unidentified-pile",
        )
        empty = replace(
            unknown, grids={Position(13, 47): grid(13, 47)}
        )
        self.assertEqual(
            policy._q2_phase_key(empty, self.profiles[2], navigator), WAIT_KEY
        )
        self.assertEqual(
            policy.last_reason, "quest:blocked:q2-blue-recovery-unwitnessed"
        )

    def test_q2_observation_route_does_not_reverse_at_worm_corner(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update({86, 153, 252})
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.opened.update(
            [Position(y, 47) for y in range(5, 12)]
            + [
                Position(8, 57), Position(7, 57), Position(7, 56),
                Position(6, 56), Position(6, 55), Position(5, 54),
            ]
        )

        lower = Snapshot(
            player(8, 57), {Position(8, 57): grid(8, 57)}, [],
            floor_key=(0, 15, 2),
        )
        upper = Snapshot(
            player(7, 57), {Position(7, 57): grid(7, 57)}, [],
            floor_key=(0, 15, 2),
        )

        first = policy._q2_phase_key(lower, self.profiles[2], navigator)
        second = policy._q2_phase_key(upper, self.profiles[2], navigator)

        self.assertNotEqual((first, second), ("8", "2"))
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-post-blue-down-puddle"
        )

    def test_q2_stale_empty_puddle_cell_does_not_skip_downward_phase(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update({86, 153, 252})
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.opened.update(Position(y, 47) for y in range(5, 12))
        puddle = Position(18, 46)
        snapshot = Snapshot(
            player(13, 47),
            {
                Position(13, 47): grid(13, 47),
                puddle: grid(18, 46, in_view=False),
            },
            [], floor_key=(0, 15, 2),
        )

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertIn(key, {"1", "2", "3", "4", "6", "7", "8", "9"})
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-post-blue-down-puddle"
        )
        self.assertNotIn(puddle, policy._q2_surveyed_placements)

    def test_q2_restart_at_nether_worm_keeps_later_puddle_pending(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        navigator = QuestFloorNavigator(2, q2.battlefield)
        final_checkpoint = Position(11, 60)
        snapshot = Snapshot(
            player(1, 7),
            {
                Position(1, 7): grid(1, 7),
                final_checkpoint: grid(11, 60, in_view=False),
            },
            [],
            floor_key=(0, 15, 2),
        )
        policy._q2_reconnect_recovery_floor = snapshot.floor_key

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertIn(key, {"1", "2", "3", "4", "6", "7", "8", "9"})
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-post-blue-nether-worm"
        )
        self.assertTrue(policy._q2_blue_recovery_complete)
        self.assertTrue({175, 885} <= policy._q2_cleared_races)
        self.assertNotIn(944, policy._q2_cleared_races)
        self.assertNotIn(213, policy._q2_cleared_races)

    def test_q2_phase_routing_owns_distant_visible_hostile(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 15)},
            monster_placements=(((1, 14), 175),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        spider = replace(hostile(1, 1, 14, distance=13), race_id=175)
        snapshot = Snapshot(
            player(1, 1),
            {
                Position(1, 1): grid(1, 1),
                Position(1, 14): grid(1, 14, monster=True),
            },
            [spider], floor_key=(0, 15, 2),
        )

        with patch.object(policy, "_q2_phase_key", return_value="ROUTE"):
            self.assertEqual(
                policy._approved_quest_strategy_key(snapshot, [spider], []),
                "ROUTE",
            )
        self.assertNotEqual(policy.last_reason, "quest-strategy:retake-hold")

    def test_q2_restart_moves_to_reconfirm_opening_rat_placements(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        navigator = QuestFloorNavigator(2, q2.battlefield)
        snapshot = Snapshot(
            player(1, 5),
            {Position(1, 5): grid(1, 5)},
            [], floor_key=(0, 15, 2),
        )

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertIn(key, {"4", "6", "1", "2", "3", "7", "8", "9"})
        self.assertEqual(policy.last_reason, "quest-strategy:q2-phase-86")

    def test_q2_rat_reconfirmation_uses_stable_closer_goal(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_surveyed_placements.add(Position(1, 1))
        navigator = QuestFloorNavigator(2, q2.battlefield)
        snapshot = Snapshot(
            player(1, 2),
            {Position(1, 2): grid(1, 2)},
            [], floor_key=(0, 15, 2),
        )

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "2"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:q2-phase-86")

    def test_q2_outpost_errand_activates_real_carry_procurement(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=10000),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True, town_id=0,
            visited_town_ids=(0, 1),
            quests={2: QuestState(id=2, status=QUEST_STATUS_UNTAKEN, fixed=True)},
        )

        strategy = policy._carry_procurement_strategy(snapshot)

        self.assertIsNotNone(strategy)
        self.assertEqual(strategy.quest_id, 2)
        self.assertEqual(
            strategy.required_force["throwing_items"]["launcher_ammo"], 99
        )

    def test_q2_carry_procurement_buys_ammo_target_and_reserves_exact_shortages(self):
        policy = self._policy()
        profile = self.profiles[2]
        base = replace(
            self._q2_carry_snapshot(),
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[],
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True)],
        )
        crossbow = StoreItem(
            "a", "Light Crossbow", 1, TVAL_BOW, SV_BOW_LIGHT_XBOW,
            price=200, to_d=6,
        )
        bolts = StoreItem("b", "Bolts", 99, TVAL_BOLT, 0, price=2)
        weapon_store = replace(base, store=StoreState(STORE_WEAPON, [crossbow, bolts]))
        self.assertEqual(policy._quest_carry_purchase(weapon_store, profile), crossbow)
        armed = replace(
            weapon_store,
            equipment=[
                *base.equipment,
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True, to_d=6,
                ),
            ],
        )
        self.assertEqual(policy._quest_carry_purchase(armed, profile), bolts)
        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            self.assertEqual(
                policy._purchase_quantity(armed, bolts), AMMO_CARRY_TARGET
            )

        light = StoreItem("l", "Light", 20, TVAL_SCROLL, SV_SCROLL_LIGHT, price=20)
        scroll_store = replace(base, store=StoreState(STORE_ALCHEMIST, [light]))
        self.assertEqual(policy._quest_carry_purchase(scroll_store, profile), light)
        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            self.assertEqual(policy._purchase_quantity(scroll_store, light), 6)

        carried_bolts = item("b", TVAL_BOLT, 0, count=99)
        carried_light = item("l", TVAL_SCROLL, SV_SCROLL_LIGHT, count=6)
        carried_wand = item("w", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=2)
        retained = replace(
            base,
            inventory=[carried_bolts, carried_light, carried_wand],
            equipment=[
                *base.equipment,
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True, to_d=6,
                ),
            ],
        )
        with patch.object(policy, "_carry_procurement_strategy", return_value=profile):
            self.assertEqual(policy._retention_reservation(retained, carried_bolts), 99)
            self.assertEqual(policy._retention_reservation(retained, carried_light), 6)
            self.assertEqual(policy._retention_reservation(retained, carried_wand), 1)

    def test_q22_accepts_any_launcher_meeting_damage_and_matching_ammo(self):
        policy = self._policy()
        profile = self.profiles[22]
        strong_sling = item(
            "bow", TVAL_BOW, SV_BOW_SLING,
            name="Strong Sling", is_equipment=True, to_h=10, to_d=19,
        )
        shots = item("s", TVAL_SHOT, 0, count=99)
        sling_snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=10000),
            {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), town_flag=True, town_id=0,
            inventory=[shots], equipment=[strong_sling],
        )
        sling_status = policy._quest_carry_status(
            sling_snapshot, profile.required_force
        )
        self.assertTrue(sling_status["launcher"]["ready"])
        self.assertEqual(
            sling_status["launcher.average_damage"]["measured"], 42.0
        )
        self.assertTrue(
            sling_status["throwing_items.launcher_ammo"]["ready"]
        )

        weak_sling = replace(strong_sling, to_d=0)
        weak_status = policy._quest_carry_status(
            replace(sling_snapshot, equipment=[weak_sling]),
            profile.required_force,
        )
        self.assertFalse(weak_status["launcher"]["ready"])
        self.assertFalse(weak_status["launcher.average_damage"]["ready"])

        crossbow = item(
            "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
            name="Light Crossbow", is_equipment=True, to_h=3, to_d=3,
        )
        bolts = item("b", TVAL_BOLT, 0, count=99)
        crossbow_status = policy._quest_carry_status(
            replace(sling_snapshot, inventory=[bolts], equipment=[crossbow]),
            profile.required_force,
        )
        self.assertTrue(crossbow_status["launcher"]["ready"])
        self.assertEqual(
            crossbow_status["launcher.average_damage"]["measured"], 18.0
        )
        self.assertTrue(
            crossbow_status["throwing_items.launcher_ammo"]["ready"]
        )

    def test_q2_prefers_superior_home_crossbow_over_store_plain_crossbow(self):
        policy = self._policy()
        profile = self.profiles[2]
        base = replace(
            self._q2_carry_snapshot(),
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[],
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True)],
        )
        superior = StoreItem(
            "a", "Superior Light Crossbow", 1,
            TVAL_BOW, SV_BOW_LIGHT_XBOW,
            price=0, is_equipment=True, is_ego=True, to_h=5, to_d=6,
        )
        plain = StoreItem(
            "a", "Light Crossbow", 1,
            TVAL_BOW, SV_BOW_LIGHT_XBOW,
            price=200, is_equipment=True,
        )
        bolts = StoreItem("b", "Bolts", 99, TVAL_BOLT, 0, price=2)
        policy._equipment_catalog.observe_home_page([superior])

        home = replace(base, store=StoreState(STORE_HOME, [superior]))
        with patch.object(
            policy, "_carry_procurement_strategy", return_value=profile
        ):
            self.assertEqual(policy._home_quest_launcher_key(home), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:queue-quest-launcher-withdraw")

        weapon_store = replace(
            base, store=StoreState(STORE_WEAPON, [plain, bolts])
        )
        self.assertIsNone(policy._quest_carry_purchase(weapon_store, profile))

    def test_q2_lights_dark_shooting_area_before_firing_fixed_undead(self):
        policy = self._policy()
        # Real Q2 placement: corpse mass 202 occupies [7,35]/[7,36].
        target = replace(hostile(1, 7, 35, distance=4), race_id=202)
        grids = {
            Position(7, x): grid(
                7, x, monster=x == 35, lit=False
            )
            for x in range(31, 36)
        }
        bolts = item("b", TVAL_BOLT, 0, count=45)
        light = item("l", TVAL_SCROLL, SV_SCROLL_LIGHT, count=6)
        snapshot = Snapshot(
            player(7, 31, hp=300, max_hp=300), grids, [target],
            floor_key=(0, 1, 2), inventory=[bolts, light],
            equipment=[item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)],
        )
        policy._fixed_quest_speed_attempted = True

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [target], []), "rl"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:q2-light-area")

        # A failed/no-op light read is still bounded: do not consume all six.
        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [target], []), "fb6"
        )

        lit_grids = dict(grids)
        lit_grids[target.position] = replace(grids[target.position], lit=True)
        illuminated = replace(snapshot, grids=lit_grids, inventory=[bolts])
        self.assertEqual(
            policy._approved_quest_strategy_key(illuminated, [target], []), "fb6"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:q2-fire")

    def test_q2_approaches_visible_residual_multiplier_after_placement_clear(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 16)},
            monster_placements=(((1, 14), 202),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        target = replace(hostile(1, 1, 14, distance=13), race_id=202)
        snapshot = Snapshot(
            player(1, 1),
            {
                Position(1, x): grid(1, x, monster=x == 14)
                for x in range(1, 16)
            },
            [target],
            floor_key=(0, 15, 2),
            inventory=[item("b", TVAL_BOLT, 0, count=10)],
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        navigator = QuestFloorNavigator(2, battlefield)

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "6"
        )
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-approach-residual-multiplier",
        )

    def test_q2_holds_ranged_distance_from_visible_residual_multiplier(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 12)},
            monster_placements=(((1, 10), 153),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        target = replace(hostile(1, 1, 10, distance=2), race_id=153)
        bolts = item("b", TVAL_BOLT, 0, count=10)
        snapshot = Snapshot(
            player(1, 8),
            {
                Position(1, x): grid(1, x, monster=x == 10)
                for x in range(1, 12)
            },
            [target],
            floor_key=(0, 15, 2),
            inventory=[bolts],
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        navigator = QuestFloorNavigator(2, battlefield)

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), WAIT_KEY
        )
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-hold-residual-multiplier-vantage",
        )

    def test_q2_closes_on_mobile_residual_multiplier_after_ammo_exhaustion(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 16)},
            monster_placements=(((1, 14), 153),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        targets = [
            replace(hostile(index, 1, x, distance=x - 1), race_id=153)
            for index, x in enumerate((13, 14), start=1)
        ]
        snapshot = Snapshot(
            player(1, 1),
            {
                Position(1, x): grid(1, x, monster=x in {13, 14})
                for x in range(1, 16)
            },
            targets,
            floor_key=(0, 15, 2),
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        navigator = QuestFloorNavigator(2, battlefield)

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "6"
        )
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-close-residual-multiplier-no-ammo",
        )

    def test_q2_bump_attacks_adjacent_corpse_mass_without_ammo(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 5)},
            monster_placements=(((1, 3), 202),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        target = replace(hostile(1, 1, 3, distance=1), race_id=202)
        snapshot = Snapshot(
            player(1, 2),
            {
                Position(1, x): grid(1, x, monster=x == 3)
                for x in range(1, 5)
            },
            [target],
            floor_key=(0, 15, 2),
        )
        navigator = QuestFloorNavigator(2, battlefield)

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "6"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-melee-corpse-attack"
        )
        self.assertNotEqual(policy.last_reason, "quest:blocked:q2-residual-multiplier-melee")

    def test_q2_approaches_nonadjacent_corpse_mass_without_ammo(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 7)},
            monster_placements=(((1, 6), 202),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        target = replace(hostile(1, 1, 6, distance=5), race_id=202)
        snapshot = Snapshot(
            player(1, 1),
            {
                Position(1, x): grid(1, x, monster=x == 6)
                for x in range(1, 7)
            },
            [target],
            floor_key=(0, 15, 2),
        )
        navigator = QuestFloorNavigator(2, battlefield)

        decision = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertEqual(decision, "6")
        self.assertNotEqual(decision, WAIT_KEY)
        next_position = Position(1, 2)
        self.assertLess(
            next_position.distance_to(target.position),
            snapshot.player.position.distance_to(target.position),
        )
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-close-residual-multiplier-no-ammo",
        )

    def test_q2_closes_on_corpse_masses_before_recovering_dry_ammo(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 16)},
            monster_placements=(
                ((1, 2), 918),
                ((1, 13), 202),
                ((1, 14), 202),
                ((1, 15), 202),
            ),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        targets = [
            replace(hostile(index, 1, x, distance=x - 1), race_id=202)
            for index, x in enumerate((13, 14, 15), start=1)
        ]
        snapshot = Snapshot(
            player(1, 1),
            {
                Position(1, x): grid(
                    1, x,
                    monster=x in {13, 14, 15},
                    objects=1 if x == 3 else 0,
                    object_tvals=(TVAL_BOLT,) if x == 3 else (),
                )
                for x in range(1, 16)
            },
            targets,
            floor_key=(0, 15, 2),
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        navigator = QuestFloorNavigator(2, battlefield)

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "6"
        )
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-close-residual-multiplier-no-ammo",
        )

    def test_q2_recommits_to_recent_corpse_mass_before_phase_918(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 21)},
            monster_placements=(((1, 2), 918), ((1, 18), 202)),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_breeder_last_seen = Position(1, 18)
        policy._q2_breeder_last_seen_floor = (0, 15, 2)
        phase_918_index = self.profiles[2].priority_targets.index(918)
        policy._q2_cleared_races.update(
            self.profiles[2].priority_targets[:phase_918_index]
        )
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            placement
            for _, _, placements in policy_module.Q2_POST_BLUE_SEQUENCE
            for placement in placements
        )
        hidden = Snapshot(
            player(1, 10),
            {
                Position(1, x): grid(1, x, in_view=8 <= x <= 14)
                for x in range(1, 21)
            },
            [],
            floor_key=(0, 15, 2),
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        navigator = QuestFloorNavigator(2, battlefield)

        key = policy._q2_phase_key(hidden, self.profiles[2], navigator)
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-breeder-recommit",
        )
        self.assertEqual(key, "6")

    def test_q2_phase_918_runs_when_no_breeder_was_seen(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 21)},
            monster_placements=(((1, 2), 918), ((1, 18), 202)),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        phase_918_index = self.profiles[2].priority_targets.index(918)
        policy._q2_cleared_races.update(
            self.profiles[2].priority_targets[:phase_918_index]
        )
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            placement
            for _, _, placements in policy_module.Q2_POST_BLUE_SEQUENCE
            for placement in placements
        )
        snapshot = Snapshot(
            player(1, 10),
            {
                Position(1, x): grid(1, x, in_view=8 <= x <= 12)
                for x in range(1, 21)
            },
            [],
            floor_key=(0, 15, 2),
        )
        navigator = QuestFloorNavigator(2, battlefield)

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "4"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:q2-phase-918")

    def test_q2_ammo_recovery_persists_when_corpse_masses_leave_view(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 16)},
            monster_placements=(((1, 14), 202),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_ammo_recovery_floor = (0, 15, 2)
        snapshot = Snapshot(
            player(1, 1),
            {
                Position(1, x): grid(
                    1, x,
                    objects=1 if x == 3 else 0,
                    object_tvals=(TVAL_BOLT,) if x == 3 else (),
                )
                for x in range(1, 16)
            },
            [],
            floor_key=(0, 15, 2),
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        navigator = QuestFloorNavigator(2, battlefield)

        self.assertEqual(
            policy._q2_phase_key(snapshot, self.profiles[2], navigator), "6"
        )
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-recover-dry-ammo-candidate",
        )

    def _q2_live_firing_tail(self, knowledge):
        policy = self._policy()
        policy._monrace_knowledge[202] = knowledge
        battlefield = QuestBattlefield(
            terrain={
                (y, x): "floor"
                for y in range(5, 11)
                for x in range(24, 38)
            },
            monster_placements=(((7, 35), 202), ((7, 36), 202)),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_ammo_recovery_floor = (0, 15, 2)
        current = Position(8, 28)
        targets = [
            replace(
                hostile(index, y, x, distance=current.distance_to(Position(y, x))),
                race_id=202,
                can_multiply=True,
            )
            for index, (y, x) in enumerate(((8, 34), (7, 35), (7, 36)), start=10)
        ]
        snapshot = Snapshot(
            player(current.y, current.x, hp=575, max_hp=575),
            {
                Position(y, x): grid(
                    y,
                    x,
                    monster=(y, x) in {(8, 34), (7, 35), (7, 36)},
                    objects=1 if (y, x) == (6, 26) else 0,
                    object_tvals=(TVAL_BOLT,) if (y, x) == (6, 26) else (),
                )
                for y in range(5, 11)
                for x in range(24, 38)
            },
            targets,
            floor_key=(0, 15, 2),
            inventory=[item("q", TVAL_BOLT, 0, count=12)],
            equipment=[
                item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)
            ],
        )
        return policy, snapshot, QuestFloorNavigator(2, battlefield)

    def test_q2_real_tail_keeps_firing_during_dry_ammo_recovery(self):
        knowledge = MonraceKnowledge(
            10,
            110,
            False,
            False,
            max_ranged_damage=0,
            can_multiply=True,
            flags=frozenset({"NEVER_MOVE"}),
        )
        policy, snapshot, navigator = self._q2_live_firing_tail(knowledge)

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertEqual(key, "fq6")
        self.assertEqual(policy.last_reason, "quest-strategy:q2-fire")
        self.assertFalse(key in {"7", "9"})
        self.assertIsNotNone(policy._q2_ammo_recovery_floor)
        self.assertTrue(
            policy._visible_engagement_is_immobile_ranged_less(
                snapshot.visible_monsters
            )
        )

    def test_q2_mobile_hostile_does_not_defer_dry_ammo_recovery(self):
        knowledge = MonraceKnowledge(10, 110, False, False)
        policy, snapshot, navigator = self._q2_live_firing_tail(knowledge)

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertIn(key, {"7", "9"})
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-recover-dry-ammo-candidate"
        )

    def test_q2_ranged_hostile_does_not_defer_dry_ammo_recovery(self):
        knowledge = MonraceKnowledge(
            10,
            110,
            False,
            False,
            max_ranged_damage=1,
            flags=frozenset({"NEVER_MOVE"}),
        )
        policy, snapshot, navigator = self._q2_live_firing_tail(knowledge)

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertIn(key, {"7", "9"})
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-recover-dry-ammo-candidate"
        )

    def test_q2_emergency_still_precedes_stationary_engagement(self):
        knowledge = MonraceKnowledge(
            10,
            110,
            False,
            False,
            flags=frozenset({"NEVER_MOVE"}),
        )
        policy, snapshot, _ = self._q2_live_firing_tail(knowledge)
        emergency_snapshot = replace(
            snapshot, player=replace(snapshot.player, hp=10)
        )

        def emergency(_snapshot, _hostiles):
            policy.last_reason = "emergency:teleport"
            return "rt"

        with (
            patch.object(policy, "_emergency_item", side_effect=emergency),
            patch.object(policy, "_q2_phase_key") as phase,
        ):
            key = policy.choose_key(emergency_snapshot)

        self.assertEqual((key, policy.last_reason), ("rt", "emergency:teleport"))
        phase.assert_not_called()

    def test_q2_abandons_oscillating_dry_ammo_route_and_engages_cluster(self):
        policy = self._policy()
        cluster = (
            (6, 29), (6, 30), (6, 31),
            (7, 29), (7, 30), (7, 31),
            (8, 29), (8, 30), (8, 31),
            (9, 29), (9, 30), (9, 31),
        )
        battlefield = QuestBattlefield(
            terrain={
                (y, x): "floor"
                for y in range(5, 11)
                for x in range(24, 36)
            },
            monster_placements=tuple((position, 202) for position in cluster),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_ammo_recovery_floor = (0, 15, 2)
        current = Position(7, 27)
        bounce = Position(6, 26)
        policy._recent.extend(
            [bounce, current] * (STUCK_WINDOW // 2)
        )
        targets = [
            replace(
                hostile(index, y, x, distance=current.distance_to(Position(y, x))),
                race_id=202,
            )
            for index, (y, x) in enumerate(cluster, start=1)
        ]
        snapshot = Snapshot(
            player(current.y, current.x),
            {
                Position(y, x): grid(
                    y,
                    x,
                    monster=(y, x) in cluster,
                    objects=1 if (y, x) == (7, 34) else 0,
                    object_tvals=(TVAL_BOLT,) if (y, x) == (7, 34) else (),
                )
                for y in range(5, 11)
                for x in range(24, 36)
            },
            targets,
            floor_key=(0, 15, 2),
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        navigator = QuestFloorNavigator(2, battlefield)

        def live_route(_start, goals, *, blocked=None):
            if Position(7, 34) in goals:
                return bounce
            return Position(7, 28)

        with patch.object(
            navigator, "route_to_static_goals", side_effect=live_route
        ):
            key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertEqual(key, "6")
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-close-residual-multiplier-no-ammo",
        )
        self.assertIsNone(policy._q2_ammo_recovery_floor)

    def test_q2_residual_multiplier_route_never_steps_into_breeder_buffer(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 12)},
            monster_placements=(((1, 6), 153),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        target = replace(hostile(1, 1, 6, distance=3), race_id=153)
        snapshot = Snapshot(
            player(1, 3),
            {
                Position(1, x): grid(1, x, monster=x == 6)
                for x in range(1, 12)
            },
            [target],
            floor_key=(0, 15, 2),
            inventory=[item("b", TVAL_BOLT, 0, count=10)],
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        navigator = QuestFloorNavigator(2, battlefield)

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertNotEqual(key, "6")
        self.assertNotEqual(policy.last_reason, "quest-strategy:q2-approach-residual-multiplier")

    def test_q2_does_not_rest_between_engagements_while_hostile_is_visible(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 12)},
            monster_placements=(((1, 10), 1044),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_cleared_races.update(policy_module.Q2_BREEDER_RACES)
        target = replace(
            hostile(1, 1, 10, distance=9, max_ranged_damage=24),
            race_id=1044,
        )
        snapshot = Snapshot(
            player(1, 1, hp=80, max_hp=100),
            {
                Position(1, x): grid(1, x, monster=x == 10)
                for x in range(1, 12)
            },
            [target],
            floor_key=(0, 15, 2),
        )
        navigator = QuestFloorNavigator(2, battlefield)

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertNotEqual(key, REST_MACRO)
        self.assertNotEqual(
            policy.last_reason, "quest-strategy:q2-rest-between-engagements"
        )

    def test_q2_rechecks_corpse_mass_area_instead_of_generic_final_target(self):
        policy = self._policy()
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 12)},
            monster_placements=(((1, 10), 202),),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.add(Position(1, 10))
        policy._q2_surveyed_placements.update(
            placement
            for _, _, placements in policy_module.Q2_POST_BLUE_SEQUENCE
            for placement in placements
        )
        snapshot = Snapshot(
            player(1, 1),
            {
                Position(1, x): grid(1, x, in_view=x <= 3)
                for x in range(1, 12)
            },
            [],
            floor_key=(0, 15, 2),
        )
        navigator = QuestFloorNavigator(2, battlefield)

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-residual-202-sweep"
        )
        self.assertEqual(key, "6")

    def test_q2_residual_multiplier_route_does_not_reverse_between_vantages(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.allow_diagonal = True
        target = replace(hostile(1, 8, 28, distance=7), race_id=202)
        lower = Snapshot(
            player(2, 21),
            {
                Position(2, 21): grid(2, 21),
                target.position: grid(8, 28, monster=True),
            },
            [target],
            floor_key=(0, 15, 2),
            inventory=[item("b", TVAL_BOLT, 0, count=10)],
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        upper = replace(lower, player=player(3, 22))

        first = policy._q2_phase_key(lower, self.profiles[2], navigator)
        second = policy._q2_phase_key(upper, self.profiles[2], navigator)

        self.assertNotEqual((first, second), ("3", "7"))
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-approach-residual-multiplier",
        )

    def test_q2_residual_corpse_sweep_keeps_one_route_target(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            Position(*placement)
            for placement, _ in q2.battlefield.monster_placements
        )
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.opened.update(Position(16, x) for x in range(8, 40))
        grids = {
            Position(16, x): grid(16, x, lit=True, in_view=True)
            for x in range(8, 40)
        }
        first_snapshot = Snapshot(
            player(16, 25), grids, [], floor_key=(0, 15, 2)
        )
        second_snapshot = replace(first_snapshot, player=player(16, 26))

        first = policy._q2_phase_key(
            first_snapshot, self.profiles[2], navigator
        )
        second = policy._q2_phase_key(
            second_snapshot, self.profiles[2], navigator
        )

        self.assertNotEqual((first, second), ("6", "4"))
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-residual-202-sweep"
        )

    def test_q2_starts_full_map_patrol_instead_of_holding_at_entrance(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        q2 = load_quest_knowledge(definitions)[2]
        battlefield = q2.battlefield
        self.assertIsNotNone(battlefield)
        policy = self._policy()
        policy._quest_knowledge[2] = q2
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            Position(*position) for position, _ in battlefield.monster_placements
        )
        policy._q2_residual_surveyed_races.update(
            policy_module.Q2_RESIDUAL_SWEEP_RACES
        )
        navigator = QuestFloorNavigator(2, battlefield)
        navigator.reset_for_floor((0, 15, 2))
        navigator.opened.add(policy_module.Q2_BREACH_POSITION)
        snapshot = Snapshot(
            player(1, 7, hp=392, max_hp=392),
            {Position(1, 7): grid(1, 7)},
            [],
            floor_key=(0, 15, 2),
        )

        key = policy._q2_phase_key(snapshot, self.profiles[2], navigator)

        self.assertNotEqual(key, WAIT_KEY, policy.last_reason)
        self.assertEqual(policy.last_reason, "quest-strategy:q2-final-patrol")
        self.assertIsNotNone(policy._q2_final_patrol_target)

    def test_q2_full_map_patrol_covers_corridor_before_restarting_round(self):
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 7)},
            player_start=(1, 1),
            entrance=(1, 1),
            exit=(1, 1),
        )
        policy = self._policy()
        policy._quest_knowledge[2] = SimpleNamespace(battlefield=battlefield)
        policy._q2_cleared_races.update(self.profiles[2].priority_targets)
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            placement
            for _, _, placements in policy_module.Q2_POST_BLUE_SEQUENCE
            for placement in placements
        )
        policy._q2_residual_surveyed_races.update(
            policy_module.Q2_RESIDUAL_SWEEP_RACES
        )
        navigator = QuestFloorNavigator(2, battlefield)
        navigator.reset_for_floor((0, 15, 2))

        for x in range(1, 6):
            snapshot = Snapshot(
                player(1, x),
                {Position(1, x): grid(1, x)},
                [],
                floor_key=(0, 15, 2),
            )
            self.assertEqual(
                policy._q2_phase_key(snapshot, self.profiles[2], navigator),
                "6",
            )
            self.assertEqual(policy.last_reason, "quest-strategy:q2-final-patrol")

        at_end = Snapshot(
            player(1, 6),
            {Position(1, 6): grid(1, 6)},
            [],
            floor_key=(0, 15, 2),
        )
        self.assertEqual(
            policy._q2_phase_key(at_end, self.profiles[2], navigator), WAIT_KEY
        )
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:q2-final-patrol-round-complete",
        )
        self.assertEqual(
            policy._q2_phase_key(at_end, self.profiles[2], navigator), "4"
        )

    def test_q2_fires_profile_bolts_at_fixed_water_target(self):
        policy = self._policy()
        # Real Q2 placement: deep-water target 944 occupies [12,64].
        target = replace(hostile(1, 12, 64, distance=4), race_id=944)
        grids = {
            Position(12, x): grid(
                12, x, monster=x == 64, lit=True
            )
            for x in range(60, 65)
        }
        snapshot = Snapshot(
            player(12, 60), grids, [target], floor_key=(0, 1, 2),
            inventory=[item("b", TVAL_BOLT, 0, count=45)],
            equipment=[item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)],
        )
        policy._fixed_quest_speed_attempted = True

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [target], []), "fb6"
        )
        no_crossbow = replace(
            snapshot,
            equipment=[item("bow", TVAL_BOW, SV_BOW_SHORT, is_equipment=True)],
        )
        self.assertIsNone(
            policy._q2_ranged_core_key(no_crossbow, self.profiles[2], [target])
        )

    def test_q2_start_room_cursor_fires_at_nonaligned_shallow_puddle(self):
        policy = self._policy()
        left = replace(hostile(2, 2, 2, distance=2), race_id=885)
        right = replace(hostile(3, 2, 6, distance=2), race_id=885)
        snapshot = Snapshot(
            player(1, 4),
            {
                Position(1, 4): grid(1, 4),
                Position(2, 2): grid(2, 2, monster=True, lit=True),
                Position(2, 6): grid(2, 6, monster=True, lit=True),
            },
            [left, right], floor_key=(0, 15, 2),
            inventory=[item("q", TVAL_BOLT, 0, count=42)],
            equipment=[
                item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)
            ],
        )

        key = policy._approved_quest_strategy_key(snapshot, [left, right], [])

        self.assertEqual(key, "fq*p14t5\x1b")
        self.assertEqual(policy.last_reason, "quest-strategy:q2-fire")

    def test_q2_deep_puddle_uses_explicit_cursor_instead_of_stalling_target_mode(self):
        policy = self._policy()
        target = replace(hostile(16, 12, 64, distance=6), race_id=944)
        snapshot = Snapshot(
            player(18, 63),
            {
                Position(18, 63): grid(18, 63, lit=True, in_view=True),
                Position(12, 64): grid(
                    12, 64, monster=True, lit=False, in_view=True
                ),
            },
            [target], floor_key=(0, 15, 2), width=132, height=44,
            inventory=[item("n", TVAL_BOLT, 0, count=80)],
            equipment=[
                item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)
            ],
        )

        key = policy._approved_quest_strategy_key(snapshot, [target], [])

        self.assertTrue(key.startswith("fn*p"), key)
        self.assertTrue(key.endswith("t5\x1b"), key)
        self.assertNotIn("*t", key)
        self.assertEqual(policy.last_reason, "quest-strategy:q2-fire")

    def test_q2_does_not_treat_floor_loot_as_missing_torch_supply(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(3, 25),
            {
                Position(3, 25): grid(3, 25),
                Position(3, 26): grid(3, 26, objects=1),
            },
            [], floor_key=(0, 15, 2),
        )
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), WAIT_KEY
        )
        self.assertNotEqual(policy.last_reason, "quest-strategy:recover-torch")

    def test_q2_quaffs_speed_at_wererat_and_white_crocodile_engagements(self):
        policy = self._policy()
        speed = item("s", TVAL_POTION, SV_POTION_SPEED, count=2)
        wererat = replace(hostile(1, 16, 25, distance=1), race_id=270)
        base = Snapshot(
            player(16, 24),
            {
                Position(16, 24): grid(16, 24),
                Position(16, 25): grid(16, 25, monster=True),
            },
            [wererat], floor_key=(0, 1, 2), inventory=[speed],
        )

        self.assertEqual(
            policy._approved_quest_strategy_key(base, [wererat], [wererat]), "qs"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:q2-quaff-speed")
        self.assertNotEqual(
            policy._approved_quest_strategy_key(base, [wererat], [wererat]), "qs"
        )

        crocodile = replace(hostile(2, 19, 11, distance=1), race_id=1044)
        croc_snapshot = replace(
            base,
            player=player(19, 10),
            grids={
                Position(19, 10): grid(19, 10),
                Position(19, 11): grid(19, 11, monster=True),
            },
            visible_monsters=[crocodile],
        )
        self.assertEqual(
            policy._approved_quest_strategy_key(
                croc_snapshot, [crocodile], [crocodile]
            ),
            "qs",
        )

    def test_q2_wererat_lock_overrides_earlier_profile_targets(self):
        policy = self._policy()
        policy._fixed_quest_speed_attempted = True
        giant_rat = replace(hostile(1, 10, 14, distance=4), race_id=86)
        wererat = replace(hostile(2, 14, 10, distance=4), race_id=270)
        gremlin = replace(
            hostile(3, 6, 10, distance=4, can_multiply=True), race_id=153
        )
        grids = {
            **{Position(10, x): grid(10, x, monster=x == 14, lit=True)
               for x in range(10, 15)},
            **{Position(y, 10): grid(y, 10, monster=y == 14, lit=True)
               for y in range(11, 15)},
            **{Position(y, 10): grid(y, 10, monster=y == 6, lit=True)
               for y in range(6, 10)},
        }
        snapshot = Snapshot(
            player(10, 10), grids, [giant_rat, wererat, gremlin],
            floor_key=(0, 1, 2),
            inventory=[item("b", TVAL_BOLT, 0, count=45)],
            equipment=[item("bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, is_equipment=True)],
        )

        self.assertEqual(
            policy._approved_quest_strategy_key(
                snapshot, [giant_rat, wererat, gremlin], []
            ),
            "fb2",
        )

    def test_q2_gremlin_preempts_nonbreeder_work_through_public_policy(self):
        giant_rat = replace(hostile(1, 10, 11, distance=1), race_id=86)
        gremlin = replace(
            hostile(2, 6, 10, distance=4, can_multiply=True), race_id=153
        )
        grids = {
            Position(10, 10): grid(10, 10, lit=True),
            Position(10, 11): grid(10, 11, monster=True, lit=True),
            **{
                Position(y, 10): grid(
                    y, 10, monster=y == 6, lit=True
                )
                for y in range(6, 10)
            },
        }
        battlefield = QuestBattlefield(
            terrain={(position.y, position.x): "floor" for position in grids},
            player_start=(10, 10),
            entrance=(10, 10),
            exit=(10, 10),
        )
        policy = HengbotPolicy(
            quest_strategies=self.profiles,
            quest_knowledge={
                2: QuestInfo(
                    2, "The Sewer", 6, 15, QUEST_FLAG_ONCE,
                    battlefield=battlefield,
                )
            },
        )
        snapshot = Snapshot(
            player(10, 10, hp=300, max_hp=300),
            grids,
            [giant_rat, gremlin],
            floor_key=(0, 15, 2),
            inventory=[item("b", TVAL_BOLT, 0, count=99)],
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
            quests={
                2: QuestState(
                    2, status=QUEST_STATUS_TAKEN, fixed=True, level=15
                )
            },
        )

        self.assertEqual(policy.choose_key(snapshot), "fb8")
        self.assertEqual(policy.last_reason, "quest-strategy:q2-fire")

    def test_q2_wererat_lock_hunts_out_of_range_before_next_phase(self):
        policy = self._policy()
        policy._fixed_quest_speed_attempted = True
        battlefield = QuestBattlefield(
            terrain={(17, x): "floor" for x in range(27, 46)},
            monster_placements=(((17, 27), 270), ((17, 40), 42)),
            player_start=(17, 45),
        )
        policy._quest_knowledge[2] = QuestInfo(
            2, "The Sewer", 6, 15, 0, battlefield=battlefield
        )
        wererat = replace(
            hostile(19, 17, 27, distance=18, can_summon=True),
            race_id=270,
        )
        snapshot = Snapshot(
            player(17, 45, hp=330, max_hp=330),
            {
                Position(17, x): grid(
                    17, x, monster=x == 27, lit=True, in_view=True
                )
                for x in range(27, 46)
            },
            [wererat], floor_key=(0, 15, 2),
            inventory=[item("b", TVAL_BOLT, 0, count=45)],
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [wererat], []), "4"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-hunt-priority-270"
        )

    def test_q2_lone_wererat_commitment_preempts_summoner_escape(self):
        policy = self._policy()
        wererat = replace(
            hostile(19, 10, 15, distance=5, can_summon=True),
            race_id=270,
        )
        grids = {
            Position(y, x): grid(
                y, x, monster=(y, x) == (10, 15), lit=True, in_view=True
            )
            for y in range(7, 16)
            for x in range(7, 17)
        }
        snapshot = Snapshot(
            player(10, 10, hp=330, max_hp=330),
            grids,
            [wererat], floor_key=(0, 15, 2),
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
        )

        with (
            patch.object(policy, "_open_neighbor_count", return_value=8),
            patch.object(policy, "_summoner_cover_in_one_step", return_value=False),
        ):
            self.assertIsNone(policy._emergency_item(snapshot, [wererat]))

            summoned = [
                replace(hostile(20, 10, 11), race_id=156),
                replace(hostile(21, 11, 10), race_id=156),
            ]
            swarm_snapshot = replace(
                snapshot,
                visible_monsters=[wererat, *summoned],
            )
            self.assertEqual(
                policy._emergency_item(
                    swarm_snapshot, [wererat, *summoned]
                ),
                "rt",
            )
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def _q2_adjacent_swarm(
        self,
        *,
        can_multiply=False,
        max_melee_damage=0,
        carry_ammo=False,
    ):
        positions = ((9, 10), (10, 11), (11, 10))
        adjacent = [
            hostile(
                index,
                y,
                x,
                distance=1,
                race_id=153 if can_multiply else 86,
                can_multiply=can_multiply,
                max_melee_damage=max_melee_damage,
            )
            for index, (y, x) in enumerate(positions, 1)
        ]
        terrain = {
            (y, x): "floor"
            for y in range(8, 13)
            for x in range(8, 13)
        }
        policy = HengbotPolicy(
            quest_strategies=self.profiles,
            quest_knowledge={
                2: QuestInfo(
                    2,
                    "The Sewer",
                    6,
                    15,
                    0,
                    battlefield=QuestBattlefield(
                        terrain=terrain,
                        player_start=(10, 10),
                        entrance=(10, 10),
                        exit=(10, 10),
                    ),
                )
            },
        )
        inventory = [item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)]
        if carry_ammo:
            inventory.append(item("b", TVAL_BOLT, 0, count=20))
        snapshot = Snapshot(
            player(10, 10, hp=300, max_hp=300),
            {
                Position(y, x): grid(
                    y,
                    x,
                    monster=(y, x) in positions,
                )
                for y, x in terrain
            },
            adjacent,
            floor_key=(0, 15, 2),
            inventory=inventory,
            equipment=[
                item(
                    "bow",
                    TVAL_BOW,
                    SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        return policy, snapshot

    def test_q2_survivable_surround_stays_and_fights(self):
        policy, snapshot = self._q2_adjacent_swarm(
            can_multiply=True,
            max_melee_damage=8,
            carry_ammo=True,
        )

        self.assertEqual(policy.choose_key(snapshot), "8")
        self.assertEqual(policy.last_reason, "quest-strategy:melee")

    def test_q2_no_ammo_commits_to_dangerous_adjacent_breeders(self):
        policy, snapshot = self._q2_adjacent_swarm(
            can_multiply=True,
            max_melee_damage=20,
        )
        prediction = policy.threat_prediction(
            snapshot, snapshot.visible_monsters, turns=3
        )

        self.assertEqual(prediction["operational_total"], 240)
        self.assertEqual(prediction["expected_total"], 240)
        self.assertEqual(policy.choose_key(snapshot), "8")
        self.assertEqual(policy.last_reason, "quest-strategy:melee")

    def test_q2_material_nonbreeder_swarm_keeps_teleport_reset(self):
        policy, snapshot = self._q2_adjacent_swarm(max_melee_damage=20)

        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "quest-strategy:q2-teleport-reset")

    def test_q2_lethal_adjacent_swarm_still_uses_emergency_teleport(self):
        policy, snapshot = self._q2_adjacent_swarm(max_melee_damage=30)
        prediction = policy.threat_prediction(
            snapshot, snapshot.visible_monsters, turns=3
        )

        self.assertEqual(prediction["operational_total"], 360)
        self.assertGreaterEqual(
            prediction["operational_total"], snapshot.player.hp
        )
        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_q2_melee_commits_to_adjacent_corpse_cluster_without_ammo(self):
        policy = self._policy()
        adjacent = [
            replace(
                hostile(index, y, x, distance=1),
                race_id=202,
                can_multiply=True,
            )
            for index, (y, x) in enumerate(((1, 2), (2, 3), (3, 3)), 1)
        ]
        snapshot = Snapshot(
            player(2, 2, hp=300, max_hp=300),
            {
                Position(y, x): grid(
                    y, x, monster=Position(y, x) in {
                        monster.position for monster in adjacent
                    }
                )
                for y in range(1, 5)
                for x in range(1, 5)
            },
            adjacent,
            floor_key=(0, 15, 2),
            inventory=[item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=2)],
            equipment=[
                item(
                    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW,
                    is_equipment=True,
                )
            ],
        )
        policy._build_grid_index(snapshot)

        self.assertIsNone(
            policy._q2_encounter_key(
                snapshot, self.profiles[2], adjacent, adjacent
            )
        )
        self.assertNotEqual(
            policy.last_reason, "quest-strategy:q2-disengage-corpse-no-ammo"
        )
        self.assertNotEqual(policy.last_reason, "quest-strategy:q2-teleport-reset")

    def test_completed_mining_rearms_normal_maintenance_restock(self):
        policy = self._policy()
        policy._deepest_level = 5
        policy._fundraising_mode = "mine"
        policy._mining_runs_completed = 1
        policy._planned_mining_runs = 1
        policy._town_restock_suppressed = True
        policy._town_errand_plan = policy_module.TownErrandPlan([STORE_HOME])
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=14000),
            {Position(10, 10): grid(10, 10, building_special=1)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            quests={1: self._quest(QUEST_STATUS_UNTAKEN)},
            inventory=[
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=4),
                item("f", TVAL_FOOD, 35, count=5),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=4),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
            ],
            equipment=[
                item("L", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, known=True),
                item("main_hand", TVAL_SWORD, 1, is_equipment=True),
            ],
        )

        with patch.object(policy, "_effective_mining_run_target", return_value=1):
            self.assertIsNone(policy._town_special_key(snapshot))

        self.assertIsNone(policy._fundraising_mode)
        self.assertFalse(policy._town_restock_suppressed)
        self.assertIsNone(policy._town_errand_plan)
        requirements = {
            entry["item"]: entry for entry in policy.procurement_requirements(snapshot)
        }
        self.assertEqual(requirements["Word of Recall scrolls"]["missing"], 2)
        self.assertEqual(requirements["Flasks of oil"]["missing"], 1)
        needs = policy._enumerate_town_needs(snapshot)
        self.assertIn(policy_module.TownNeed(STORE_GENERAL, "oil", "normal"), needs)
        self.assertIn(
            policy_module.TownNeed(STORE_BLACK, "quest-speed", "normal"), needs
        )
        self.assertIsNotNone(policy._next_required_store_type(snapshot))

    def test_force_ready_q34_retention_does_not_recurse_through_departure(self):
        policy = self._policy()
        snap = self._force_snapshot(34, hp=605, torches=20, speed=1, healing=10)
        snap = replace(
            snap,
            floor_key=(0, 0, 0),
            town_flag=True,
            quests={
                1: QuestState(
                    id=1, status=QUEST_STATUS_FINISHED, fixed=True, level=5
                ),
                34: QuestState(id=34, status=0, fixed=True, level=5),
            },
        )
        torches = snap.inventory[0]

        # Model the live readiness tail directly: fixed-quest readiness reaches
        # departure readiness, which asks Home retention about the same pack.
        with patch.object(
            policy,
            "_fixed_quest_ready",
            side_effect=lambda current, _quest_id: policy._find_home_deposit(current) is None,
        ):
            self.assertEqual(policy._retention_reservation(snap, torches), 20)
            self.assertIsNone(policy._find_home_deposit(snap))

    def test_q34_carry_purchase_stops_at_existing_gold_reserve(self):
        policy = self._policy()
        torch = StoreItem(
            letter="a", name="Torch", count=20, tval=TVAL_LITE,
            sval=SV_LITE_TORCH, price=10, aware=True, known=True,
        )
        quest = QuestState(id=34, status=0, fixed=True, level=5)
        base = Snapshot(
            player(10, 10, level=2, class_id=PLAYER_CLASS_WARRIOR, gold=1000),
            {Position(10, 10): grid(10, 10, building_special=34)}, [], floor_key=(0, 0, 0),
            town_flag=True, quests={
                1: QuestState(
                    id=1, status=QUEST_STATUS_FINISHED, fixed=True, level=5
                ),
                34: quest,
            },
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=12, fuel=5000)],
            store=StoreState(STORE_GENERAL, [torch]),
        )
        reserve = policy._fundraising_kit_reserve(base)
        blocked = replace(
            base, player=replace(base.player, gold=reserve + torch.price - 1)
        )

        self.assertIsNone(policy._next_purchase(blocked))
        affordable = replace(
            base, player=replace(base.player, gold=reserve + torch.price * 8)
        )
        self.assertEqual(policy._next_purchase(affordable), torch)

    def test_fresh_q34_torches_spend_the_fundraising_reserve(self):
        policy = self._policy()
        torch = StoreItem(
            letter="a", name="Torch", count=99, tval=TVAL_LITE,
            sval=SV_LITE_TORCH, price=5, aware=True, known=True,
        )
        snapshot = Snapshot(
            player(
                10, 10, level=1, class_id=PLAYER_CLASS_WARRIOR, gold=100
            ),
            {Position(10, 10): grid(10, 10, building_special=34)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            town_id=0,
            quests={
                34: QuestState(
                    id=34, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5
                )
            },
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=2, fuel=5000)
            ],
            store=StoreState(STORE_GENERAL, [torch]),
        )

        self.assertEqual(policy._fundraising_kit_reserve(snapshot), 100)
        self.assertEqual(policy._next_purchase(snapshot), torch)
        self.assertEqual(policy._purchase_quantity(snapshot, torch), 18)

    def test_q34_rejects_unapproved_throw_positions_and_keeps_bee_last(self):
        policy = self._policy()
        grids = {Position(10, x): grid(10, x) for x in range(15, 21)}
        grids[Position(11, 2)] = grid(11, 2)
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
        cloaker = replace(hostile(1, 10, 18, distance=2), race_id=243)
        sword = replace(hostile(2, 10, 16, distance=4), race_id=107)
        sword2 = replace(hostile(4, 10, 17, distance=3), race_id=107)
        bee = replace(hostile(3, 3, 13, distance=14), race_id=174)
        snap = Snapshot(player(10, 20, hp=100, max_hp=100), grids,
                        [bee, sword, sword2, cloaker], inventory=[torch],
                        floor_key=(0, 1, 34))
        policy._fixed_quest_speed_attempted = True
        self.assertEqual(
            policy._approved_quest_strategy_key(
                snap, snap.visible_monsters, []
            ),
            WAIT_KEY,
        )
        self.assertEqual(
            policy.last_reason, "quest:blocked:throw-outside-approved-point"
        )
        # Once the cloaker is gone, the death sword owns the volley; the bee is last.
        self.assertEqual(policy._approved_quest_strategy_key(
            replace(snap, visible_monsters=[bee, sword, sword2]), [bee, sword, sword2], []
        ), WAIT_KEY)
        self.assertEqual(policy._approved_quest_strategy_key(
            replace(snap, visible_monsters=[bee, sword2]), [bee, sword2], []
        ), WAIT_KEY)

        # The real final target is at [3,13], behind the [4,14] door. There is
        # no ray from the lantern cell [10,20], so the final phase must traverse
        # the doorway instead of relying on a fake visible bee.
        approach_grids = {
            **{Position(y, 20): grid(y, 20) for y in range(1, 11)},
            **{Position(5, x): grid(5, x) for x in range(14, 21)},
            Position(11, 2): grid(11, 2),
            Position(4, 14): grid(4, 14, closed_door=True),
            Position(3, 13): grid(3, 13),
            Position(3, 14): grid(3, 14),
        }
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15),
            (107, 9, 11),
            (107, 11, 9),
        }
        final_hidden = replace(snap, grids=approach_grids, visible_monsters=[])
        policy._build_grid_index(final_hidden)
        self.assertFalse(policy._has_line_of_fire(
            final_hidden, Position(10, 20), Position(3, 13)
        ))
        self.assertEqual(
            policy._approved_quest_strategy_key(final_hidden, [], []), "8"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:approach-final-door")

    def test_q34_killer_bee_is_meleed_without_throwing(self):
        policy = self._policy()
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15),
            (107, 9, 11),
            (107, 11, 9),
        }
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, count=10, fuel=5000)
        bee = replace(hostile(3, 3, 13, distance=1), race_id=174)
        snapshot = Snapshot(
            player(3, 14, hp=100, max_hp=100),
            {
                Position(3, 13): grid(3, 13, monster=True, in_view=True),
                Position(3, 14): grid(3, 14, in_view=True),
                Position(11, 2): grid(11, 2),
            },
            [bee],
            inventory=[torch],
            floor_key=(0, 5, 34),
        )
        policy._fixed_quest_speed_attempted = True
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [bee], [bee]), "4"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:melee")

    def test_q34_never_move_blocker_is_thrown_at_and_never_meleed(self):
        policy = self._policy()
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)
        blocker = replace(hostile(1, 9, 20, distance=1), race_id=243)
        grids = {
            Position(10, 19): grid(10, 19), Position(10, 20): grid(10, 20),
            Position(9, 20): grid(9, 20, monster=True),
            Position(11, 2): grid(11, 2),
        }
        snap = Snapshot(
            player(10, 19), grids, [blocker], inventory=[torch], floor_key=(0, 1, 34)
        )
        policy._fixed_quest_speed_attempted = True
        policy._build_grid_index(snap)

        self.assertEqual(
            policy._approved_quest_strategy_key(snap, [blocker], [blocker]),
            WAIT_KEY,
        )
        self.assertEqual(
            policy.last_reason, "quest:blocked:throw-outside-approved-point"
        )

    def test_q34_approaches_and_uses_explicit_cloaker_throw_point(self):
        policy = self._policy()
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
        cloaker = replace(hostile(1, 7, 15, distance=3), race_id=243)
        grids = {
            Position(7, x): grid(7, x, monster=(x == 15))
            for x in range(12, 16)
        }
        approach = Snapshot(
            player(7, 12), grids, [cloaker], inventory=[torch],
            floor_key=(0, 5, 34),
        )
        policy._fixed_quest_speed_attempted = True
        policy._build_grid_index(approach)

        self.assertEqual(
            policy._approved_quest_strategy_key(approach, [cloaker], []), "6"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:approach-throw-point")

        firing = replace(approach, player=player(7, 13))
        self.assertEqual(
            policy._approved_quest_strategy_key(firing, [cloaker], []), "vt6"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:throw-torch")

    def test_q34_recovers_each_target_volley_before_next_target(self):
        policy = self._policy()
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, count=19, fuel=5000)
        cloaker = replace(hostile(1, 7, 15, distance=2), race_id=243)
        grids = {
            Position(7, 13): grid(7, 13),
            Position(7, 14): grid(7, 14),
            Position(7, 15): grid(7, 15, monster=True),
            Position(9, 11): grid(9, 11, monster=True),
        }
        volley = Snapshot(
            player(7, 13), grids, [cloaker], inventory=[torch],
            floor_key=(0, 5, 34),
        )
        policy._fixed_quest_speed_attempted = True
        policy._build_grid_index(volley)
        self.assertEqual(
            policy._approved_quest_strategy_key(volley, [cloaker], []), "vt6"
        )

        sword = replace(hostile(2, 9, 11, distance=4), race_id=107)
        dropped = replace(
            volley,
            grids={
                **grids,
                Position(7, 15): replace(
                    grid(7, 15, objects=1, in_view=True),
                    object_tvals=(TVAL_LITE,),
                ),
            },
            visible_monsters=[sword],
        )
        policy._build_grid_index(dropped)
        self.assertEqual(
            policy._approved_quest_strategy_key(dropped, [sword], []), "6"
        )
        self.assertEqual(
            policy.last_reason,
            "quest-strategy:recover-defeated-target-torches",
        )

        on_torch = replace(dropped, player=player(7, 15))
        self.assertEqual(
            policy._approved_quest_strategy_key(on_torch, [sword], []),
            PICKUP_KEY,
        )

        stacked = replace(
            on_torch,
            grids={
                **on_torch.grids,
                Position(7, 15): replace(
                    grid(7, 15, objects=2, in_view=True),
                    object_tvals=(TVAL_LITE, TVAL_LITE),
                ),
            },
        )
        self.assertEqual(
            policy._approved_quest_strategy_key(stacked, [sword], []),
            PICKUP_KEY + "aa",
        )

    def test_q34_restart_surveys_explicit_throw_points(self):
        policy = self._policy()
        route_cells = (
            {(y, 20) for y in range(1, 11)}
            | {(1, x) for x in range(1, 21)}
            | {(y, 1) for y in range(1, 12)}
            | {(11, 2), (11, 3)}
            | {(y, 3) for y in range(7, 12)}
            | {(7, x) for x in range(3, 14)}
        )
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34],
            battlefield=QuestBattlefield(
                terrain={position: "floor" for position in route_cells},
                monster_placements=(
                    ((3, 13), 174), ((7, 15), 243),
                    ((9, 11), 107), ((11, 9), 107),
                ),
            ),
        )
        grids = {
            Position(11, 2): grid(11, 2),
            Position(11, 3): grid(11, 3),
        }
        bee = replace(hostile(9, 3, 13, distance=14), race_id=174)
        later_sword = replace(hostile(10, 9, 11, distance=9), race_id=107)
        hold = Snapshot(
            player(11, 2), grids, [bee, later_sword],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=18, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(hold)

        self.assertEqual(
            policy._approved_quest_strategy_key(
                hold, [bee, later_sword], []
            ),
            "6",
        )
        self.assertEqual(policy.last_reason, "quest-strategy:survey-throw-point")

        at_cloaker_point = replace(
            hold,
            player=player(7, 13),
            grids={
                Position(7, 13): grid(7, 13),
                Position(7, 15): grid(7, 15, in_view=True),
            },
        )
        self.assertEqual(
            policy._approved_quest_strategy_key(
                at_cloaker_point, [bee, later_sword], []
            ),
            WAIT_KEY,
        )
        self.assertEqual(
            policy.last_reason, "quest:blocked:fixed-target-not-visible"
        )

    def test_q34_does_not_clear_or_recover_an_unlit_fixed_target(self):
        policy = self._policy()
        at_sword_point = Snapshot(
            player(11, 11),
            {
                Position(11, 11): grid(11, 11, in_view=True),
                # A torch lights radius 1; this remembered distance-2 target
                # cell is known but not currently observable.
                Position(9, 11): grid(9, 11, in_view=False),
            },
            [],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=18, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        policy._build_grid_index(at_sword_point)

        self.assertEqual(
            policy._approved_quest_strategy_key(at_sword_point, [], []), WAIT_KEY
        )
        self.assertEqual(
            policy.last_reason, "quest:blocked:fixed-target-not-visible"
        )
        self.assertNotIn((107, 9, 11), policy._quest_strategy_cleared_targets[34])
        self.assertNotIn(34, policy._quest_strategy_pending_recovery)

    def test_q34_fov_loss_after_visibility_does_not_unlock_recovery(self):
        policy = self._policy()
        target_key = (107, 9, 11)
        policy._quest_strategy_visible_targets[34] = {target_key}
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        dark = Snapshot(
            player(11, 11),
            {
                Position(11, 11): grid(11, 11, in_view=True),
                Position(9, 11): grid(9, 11, in_view=False),
            },
            [],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=18, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(dark)

        self.assertEqual(
            policy._approved_quest_strategy_key(dark, [], []), WAIT_KEY
        )
        self.assertNotIn(target_key, policy._quest_strategy_cleared_targets[34])
        self.assertNotIn(34, policy._quest_strategy_pending_recovery)

    def test_q34_los_flicker_off_throw_point_cannot_fake_sword_death(self):
        policy = self._q34_source_policy()
        target_key = (107, 9, 11)
        policy._quest_strategy_visible_targets[34] = {target_key}
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        flickered = Snapshot(
            player(11, 13),
            {
                Position(11, 13): grid(11, 13, in_view=True),
                Position(11, 12): grid(11, 12),
                Position(10, 11): grid(10, 11, objects=1),
                Position(9, 11): grid(9, 11, in_view=True),
            },
            [],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=16, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._fixed_quest_speed_attempted = True
        policy._build_grid_index(flickered)

        key = policy._approved_quest_strategy_key(flickered, [], [])

        self.assertEqual(key, "4")
        self.assertEqual(policy.last_reason, "quest-strategy:survey-throw-point")
        self.assertEqual(
            policy._quest_strategy_cleared_targets[34], {(243, 7, 15)}
        )
        self.assertNotIn(34, policy._quest_strategy_pending_recovery)
        self.assertGreater(Position(11, 12).distance_to(Position(9, 11)), 1)

    def test_q34_unconfirmed_recovery_cannot_enter_death_sword_adjacent_cell(self):
        policy = self._policy()
        sword_plan = policy.approved_quest_strategy(34).engagement_plan[
            "throwing_points"
        ][1]
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        policy._quest_strategy_pending_recovery[34] = sword_plan
        death_position = Position(9, 11)
        snapshot = Snapshot(
            player(11, 13),
            {
                Position(11, 13): grid(11, 13, in_view=True),
                Position(10, 12): grid(10, 12),
                Position(10, 11): grid(10, 11, objects=1),
                death_position: grid(9, 11, in_view=False),
            },
            [],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=18, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snapshot)

        key = policy._approved_quest_strategy_key(snapshot, [], [])

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "quest:blocked:unconfirmed-target-recovery"
        )
        self.assertEqual(Position(10, 12).distance_to(death_position), 1)

    def test_q34_same_recovery_substrate_cannot_rearm_survey(self):
        policy = self._policy()
        plan = policy.approved_quest_strategy(34).engagement_plan["throwing_points"][0]
        target_key = (243, 7, 15)
        policy._quest_strategy_recovery_pickup_posted = (
            34, Position(7, 14), (1, (TVAL_LITE,))
        )
        policy._quest_strategy_visible_targets[34] = {target_key}
        policy._quest_strategy_cleared_targets[34] = {target_key}
        policy._quest_strategy_pending_recovery[34] = plan
        snapshot = Snapshot(
            player(7, 13),
            {
                Position(7, 13): grid(7, 13),
                Position(7, 14): replace(
                    grid(7, 14, objects=1), object_tvals=(TVAL_LITE,)
                ),
                Position(7, 15): grid(7, 15, in_view=True),
            },
            [],
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=19, fuel=5000)],
            equipment=[
                item("light", TVAL_LITE, SV_LITE_LANTERN, is_equipment=True)
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snapshot)

        key = policy._approved_quest_strategy_key(snapshot, [], [])

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(
            policy.last_reason, "quest:blocked:q34-recovery-no-progress"
        )
        self.assertNotIn(34, policy._quest_strategy_pending_recovery)
        self.assertIn(
            (7, 14, (1, (TVAL_LITE,))),
            policy._quest_strategy_recovery_claims[34],
        )

    def test_q34_chest_is_not_recovery_substrate_or_durable_lane_blocker(self):
        policy = self._policy()
        plans = policy.approved_quest_strategy(34).engagement_plan["throwing_points"]
        policy._quest_strategy_pending_recovery[34] = plans[2]
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15), (107, 9, 11), (107, 11, 9)}
        snapshot = Snapshot(
            player(11, 9),
            {
                Position(11, 9): grid(11, 9, in_view=True),
                Position(10, 9): replace(
                    grid(10, 9, objects=1, in_view=True),
                    object_tvals=(TVAL_CHEST,),
                ),
            },
            [],
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, count=15, fuel=5000)],
            equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, is_equipment=True)],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snapshot)

        key = policy._approved_quest_strategy_key(snapshot, [], [])

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "quest-strategy:recovery-complete")
        self.assertNotIn(34, policy._quest_strategy_pending_recovery)

    def test_q34_restart_target_halo_preserves_source_and_escape_route(self):
        policy = self._policy()
        profile = policy.approved_quest_strategy(34)
        snapshot = Snapshot(
            player(11, 9),
            {
                Position(11, 9): grid(11, 9),
                Position(10, 9): replace(
                    grid(10, 9, objects=1), object_tvals=(TVAL_CHEST,)
                ),
                Position(9, 9): grid(9, 9),
            },
            [],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snapshot)

        step = policy._quest_strategy_route_step(snapshot, profile, Position(9, 9))

        self.assertEqual(step, Position(10, 9))

    def test_quest_recovery_claims_are_cleared_on_floor_change(self):
        policy = self._policy()
        first = Snapshot(player(1, 1), {Position(1, 1): grid(1, 1)}, [],
                         floor_key=(0, 5, 34))
        second = replace(first, floor_key=(0, 6, 0))
        policy.choose_key(first)
        policy._quest_strategy_recovery_claims[34] = {
            (7, 14, (1, (TVAL_LITE,)))
        }

        policy.choose_key(second)

        self.assertEqual(policy._quest_strategy_recovery_claims, {})

    def test_quest_recovery_observation_state_is_cleared_on_floor_change(self):
        policy = self._policy()
        first = Snapshot(player(1, 1), {Position(1, 1): grid(1, 1)}, [],
                         floor_key=(0, 5, 34))
        policy.choose_key(first)
        policy._quest_strategy_recovery_pickup_prepared = (
            34, Position(1, 1), (1, (TVAL_LITE,))
        )
        policy._quest_strategy_recovery_pickup_prepared_key = PICKUP_KEY
        policy._quest_strategy_recovery_pickup_posted = (
            34, Position(1, 1), (1, (TVAL_LITE,))
        )

        policy.choose_key(replace(first, floor_key=(0, 6, 0)))

        self.assertIsNone(policy._quest_strategy_recovery_pickup_prepared)
        self.assertIsNone(policy._quest_strategy_recovery_pickup_prepared_key)
        self.assertIsNone(policy._quest_strategy_recovery_pickup_posted)

    def test_q2_recovery_observation_state_is_cleared_on_floor_change(self):
        policy = self._policy()
        first = Snapshot(player(1, 1), {Position(1, 1): grid(1, 1)}, [],
                         floor_key=(0, 5, 2))
        policy.choose_key(first)
        policy._q2_blue_recovery_pickup_prepared = (Position(1, 1), (1, ()))
        policy._q2_blue_recovery_pickup_posted = (Position(1, 1), (1, ()))
        policy._q2_blue_recovery_witnessed = True

        policy.choose_key(replace(first, floor_key=(0, 6, 0)))

        self.assertIsNone(policy._q2_blue_recovery_pickup_prepared)
        self.assertIsNone(policy._q2_blue_recovery_pickup_posted)
        self.assertFalse(policy._q2_blue_recovery_witnessed)

    def test_planned_throw_unreachable_reason_is_explicitly_q34_gated(self):
        policy = self._policy()
        target = replace(hostile(1, 7, 15, distance=2), race_id=243)
        snapshot = Snapshot(
            player(7, 12),
            {Position(7, 12): grid(7, 12), Position(7, 15): grid(7, 15, monster=True)},
            [target], inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
            floor_key=(0, 5, 34),
        )
        policy._fixed_quest_speed_attempted = True
        policy._build_grid_index(snapshot)

        with patch.object(policy, "_quest_strategy_route_step", return_value=None):
            self.assertEqual(
                policy._approved_quest_strategy_key(snapshot, [target], []), WAIT_KEY
            )
        self.assertTrue(policy.last_reason.startswith("quest:blocked:q34-"))

    def test_q31_planned_throw_unreachable_reason_is_not_labeled_q34(self):
        policy = self._policy()
        plan = policy.approved_quest_strategy(31).engagement_plan["throwing_points"][0]
        target = replace(
            hostile(1, *plan["target"], distance=2), race_id=plan["race_id"]
        )
        snapshot = Snapshot(
            player(18, 2),
            {
                Position(18, 2): grid(18, 2),
                Position(*plan["target"]): grid(*plan["target"], monster=True),
            }, [target],
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
            floor_key=(0, 5, 31),
        )
        policy._quest_strategy_initial_hold_turns[31] = 60
        policy._build_grid_index(snapshot)

        with patch.object(policy, "_quest_strategy_route_step", return_value=None):
            self.assertEqual(
                policy._approved_quest_strategy_key(snapshot, [target], []), WAIT_KEY
            )
        self.assertEqual(
            policy.last_reason, "quest-strategy:throw-point-unreachable"
        )

    def test_q31_survey_unreachable_reason_is_not_labeled_q34(self):
        policy = self._policy()
        snapshot = Snapshot(
            player(18, 2), {Position(18, 2): grid(18, 2)}, [],
            inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)],
            floor_key=(0, 5, 31),
        )
        policy._quest_strategy_initial_hold_turns[31] = 60
        policy._build_grid_index(snapshot)

        with patch.object(policy, "_quest_strategy_route_step", return_value=None):
            self.assertEqual(
                policy._approved_quest_strategy_key(snapshot, [], []), WAIT_KEY
            )
        self.assertEqual(
            policy.last_reason, "quest-strategy:throw-point-unreachable"
        )

    def test_q34_pickup_confirmation_is_bound_to_exact_prepared_key(self):
        policy = self._policy()
        prepared = (34, Position(7, 14), (2, (TVAL_LITE, TVAL_LITE)))
        policy._quest_strategy_recovery_pickup_prepared = prepared
        policy._quest_strategy_recovery_pickup_prepared_key = PICKUP_KEY + "aa"

        policy.confirm_key_posted(PICKUP_KEY)
        self.assertEqual(policy._quest_strategy_recovery_pickup_prepared, prepared)
        self.assertIsNone(policy._quest_strategy_recovery_pickup_posted)

        policy.confirm_key_posted(PICKUP_KEY + "aa")
        self.assertIsNone(policy._quest_strategy_recovery_pickup_prepared)
        self.assertEqual(policy._quest_strategy_recovery_pickup_posted, prepared)

    def test_q34_recovery_claim_releases_when_pile_changes(self):
        policy = self._policy()
        plan = policy.approved_quest_strategy(34).engagement_plan["throwing_points"][0]
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        policy._quest_strategy_pending_recovery[34] = plan
        policy._quest_strategy_recovery_claims[34] = {
            (7, 14, (1, (TVAL_LITE,)))
        }
        changed = Snapshot(
            player(7, 14),
            {Position(7, 14): replace(grid(7, 14, objects=2),
                                      object_tvals=(TVAL_LITE, TVAL_LITE))},
            [], floor_key=(0, 5, 34),
        )
        policy._build_grid_index(changed)

        self.assertEqual(
            policy._approved_quest_strategy_key(changed, [], []), PICKUP_KEY + "aa"
        )
        self.assertNotIn(
            (7, 14, (1, (TVAL_LITE,))),
            policy._quest_strategy_recovery_claims[34],
        )

    def test_q34_pickup_arms_observation_with_the_composed_multi_key(self):
        policy = self._policy()
        plan = policy.approved_quest_strategy(34).engagement_plan["throwing_points"][0]
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        policy._quest_strategy_pending_recovery[34] = plan
        snapshot = Snapshot(
            player(7, 14),
            {Position(7, 14): replace(grid(7, 14, objects=2),
                                      object_tvals=(TVAL_LITE, TVAL_LITE))},
            [], floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), PICKUP_KEY + "aa"
        )
        self.assertEqual(
            policy._quest_strategy_recovery_pickup_prepared,
            (34, Position(7, 14), (2, (TVAL_LITE, TVAL_LITE))),
        )
        self.assertEqual(
            policy._quest_strategy_recovery_pickup_prepared_key, PICKUP_KEY + "aa"
        )

    def test_q34_legacy_recovery_signature_does_not_suppress_real_pickup(self):
        policy = self._policy()
        plan = policy.approved_quest_strategy(34).engagement_plan["throwing_points"][0]
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        policy._quest_strategy_pending_recovery[34] = plan
        snapshot = Snapshot(
            player(7, 14),
            {Position(7, 14): replace(grid(7, 14, objects=1),
                                      object_tvals=(TVAL_LITE,))},
            [], floor_key=(0, 5, 34),
        )
        legacy_signature = (
            243, (7, 15), (((7, 14), 1, (TVAL_LITE,)),)
        )
        policy._quest_strategy_recovery_claims[34] = {legacy_signature}
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), PICKUP_KEY
        )

    def test_q34_first_sword_uses_static_safe_route_without_diagonal_shortcut(self):
        policy = self._q34_source_policy()
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        sword = replace(hostile(2, 9, 11, distance=4), race_id=107)
        snapshot = Snapshot(
            player(11, 13),
            {
                Position(11, 13): grid(11, 13),
                Position(11, 12): grid(11, 12),
                Position(10, 12): grid(10, 12),
                Position(9, 11): grid(9, 11, monster=True, in_view=True),
            },
            [sword],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=18, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snapshot)

        key = policy._approved_quest_strategy_key(snapshot, [sword], [])

        self.assertEqual(key, "4")
        self.assertEqual(policy.last_reason, "quest-strategy:approach-throw-point")
        self.assertEqual(Position(11, 12).distance_to(Position(9, 11)), 2)
        self.assertEqual(Position(10, 12).distance_to(Position(9, 11)), 1)

    def test_q34_visible_target_off_stand_routes_to_exact_throw_point(self):
        policy = self._q34_source_policy()
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        sword = replace(hostile(2, 9, 11, distance=3), race_id=107)
        off_path = Snapshot(
            player(10, 13),
            {
                Position(10, 13): grid(10, 13),
                Position(11, 13): grid(11, 13),
                Position(9, 11): grid(9, 11, monster=True, in_view=True),
            },
            [sword],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=18, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(off_path)

        key = policy._approved_quest_strategy_key(off_path, [sword], [])

        self.assertEqual(key, "2")
        self.assertFalse(key.startswith("v"))
        self.assertEqual(policy.last_reason, "quest-strategy:approach-throw-point")

    def test_q34_static_route_rejoins_from_safe_left_room_cell(self):
        policy = self._q34_source_policy()
        snapshot = Snapshot(
            player(10, 4),
            {
                Position(10, 3): grid(10, 3),
                Position(10, 4): grid(10, 4),
                Position(11, 2): grid(11, 2),
            },
            [],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._fixed_quest_speed_attempted = True
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), "8"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:survey-throw-point")

    def test_q34_second_death_sword_routes_around_the_x10_wall(self):
        policy = self._q34_source_policy()
        snapshot = Snapshot(
            player(9, 11),
            {
                Position(9, 10): grid(9, 10, passable=False),
                Position(9, 11): grid(9, 11, in_view=True),
                Position(10, 11): grid(10, 11, in_view=True),
                Position(9, 12): grid(9, 12, closed_door=True),
                Position(11, 2): grid(11, 2),
            },
            [],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=10, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._fixed_quest_speed_attempted = True
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), "o6"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:survey-throw-point")
        self.assertEqual(
            policy._quest_strategy_cleared_targets[34],
            {(243, 7, 15), (107, 9, 11)},
        )

    def test_q34_source_map_routes_every_throw_phase_without_unsafe_step(self):
        definitions = REAL_QUEST_DEFINITIONS
        if definitions is None:
            self.skipTest("real Hengband quest definitions are unavailable")
        info = load_quest_knowledge(definitions)[34]
        self.assertIsNotNone(info.battlefield)
        policy = self._policy()
        policy._quest_knowledge[34] = info
        profile = policy._quest_strategies[34]
        plans = profile.engagement_plan["throwing_points"]
        avoid = {
            Position(*raw)
            for raw in profile.engagement_plan["avoid_door_positions"]
        }

        phases = (
            (Position(11, 2), Position(*plans[0]["stand"]), set()),
            (
                Position(7, 18),
                Position(*plans[1]["stand"]),
                {(243, 7, 15)},
            ),
            (
                Position(9, 11),
                Position(*plans[2]["stand"]),
                {(243, 7, 15), (107, 9, 11)},
            ),
        )
        routes = []
        for start, goal, cleared in phases:
            policy._quest_strategy_cleared_targets[34] = set(cleared)
            route = [start]
            while route[-1] != goal:
                current = route[-1]
                snapshot = Snapshot(
                    player(current.y, current.x),
                    {current: grid(current.y, current.x)},
                    [],
                    floor_key=(0, 5, 34),
                )
                step = policy._quest_strategy_route_step(
                    snapshot, profile, goal
                )
                self.assertIsNotNone(
                    step, f"Q34 route blocked from {current} to {goal}"
                )
                self.assertEqual(
                    abs(step.y - current.y) + abs(step.x - current.x), 1
                )
                self.assertNotIn(step, avoid)
                self.assertIn(
                    info.battlefield.terrain[(step.y, step.x)],
                    {
                        "floor", "exit", "door", "passage", "rubble",
                        "shallow_water", "tree",
                    },
                )
                for plan in plans:
                    target = Position(*plan["target"])
                    target_key = (
                        int(plan["race_id"]), target.y, target.x
                    )
                    if target_key not in cleared:
                        self.assertGreater(step.distance_to(target), 1)
                self.assertNotIn(step, route, "Q34 route contains a cycle")
                route.append(step)
                self.assertLess(len(route), 100, "Q34 route exceeded bound")
            routes.append(route)

        self.assertTrue(
            {Position(9, 12), Position(8, 7), Position(9, 8)}
            <= set(routes[2])
        )
        self.assertFalse(
            {Position(9, 10), Position(10, 10), Position(11, 10)}
            & set(routes[2])
        )

    def test_q34_final_phase_uses_throw_points_without_fixed_placement_data(self):
        policy = self._policy()
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34],
            battlefield=QuestBattlefield(
                terrain={},
                monster_placements=(((3, 13), 174),),
            ),
        )
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15),
            (107, 9, 11),
            (107, 11, 9),
        }
        grids = {
            **{Position(y, 20): grid(y, 20) for y in range(1, 11)},
            **{Position(5, x): grid(5, x) for x in range(14, 21)},
            Position(11, 2): grid(11, 2),
            Position(4, 14): grid(4, 14, closed_door=True),
            Position(3, 13): grid(3, 13),
            Position(3, 14): grid(3, 14),
        }
        snap = Snapshot(player(10, 20), grids, [], floor_key=(0, 5, 34))
        policy._build_grid_index(snap)

        self.assertEqual(
            policy._approved_quest_strategy_key(snap, [], []), "8"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:approach-final-door")

    def test_q34_final_phase_uses_static_map_beyond_visible_grids(self):
        policy = self._policy()
        route_cells = (
            {(y, 9) for y in range(7, 10)}
            | {(y, 10) for y in range(3, 8)}
            | {(3, x) for x in range(10, 14)}
        )
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34],
            battlefield=QuestBattlefield(
                terrain={position: "floor" for position in route_cells},
                monster_placements=(
                    ((3, 13), 174),
                    ((7, 15), 243),
                    ((9, 11), 107),
                    ((11, 9), 107),
                ),
            ),
        )
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15),
            (107, 9, 11),
            (107, 11, 9),
        }
        snap = Snapshot(
            player(9, 9),
            {Position(9, 9): grid(9, 9)},
            [],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snap)

        self.assertEqual(
            policy._approved_quest_strategy_key(snap, [], []), "8"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:approach-final-target")

    def test_q34_final_door_uses_only_its_southern_approach(self):
        policy = self._policy()
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15),
            (107, 9, 11),
            (107, 11, 9),
        }
        north = Snapshot(
            player(5, 15),
            {
                Position(4, 14): grid(4, 14, closed_door=True),
                Position(4, 15): grid(4, 15, closed_door=True),
                Position(5, 14): grid(5, 14),
                Position(5, 15): grid(5, 15),
                Position(11, 2): grid(11, 2),
            },
            [],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(north)

        self.assertEqual(
            policy._approved_quest_strategy_key(north, [], []), "4"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:approach-final-door")

        at_approach = replace(north, player=player(5, 14))
        self.assertEqual(
            policy._approved_quest_strategy_key(at_approach, [], []), "o8"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:open-final-door")

    def test_q34_enters_the_open_accessible_door_before_outer_routes(self):
        policy = self._policy()
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34],
            battlefield=QuestBattlefield(
                terrain={
                    (5, 14): "floor",
                    (4, 14): "door",
                    (3, 14): "floor",
                    (3, 13): "floor",
                },
                monster_placements=(
                    ((3, 13), 174),
                    ((7, 15), 243),
                    ((9, 11), 107),
                    ((11, 9), 107),
                ),
            ),
        )
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15),
            (107, 9, 11),
            (107, 11, 9),
        }
        snap = Snapshot(
            player(5, 14),
            {
                Position(3, 13): grid(3, 13),
                Position(3, 14): grid(3, 14),
                Position(4, 14): grid(4, 14),
                Position(5, 13): grid(5, 13),
                Position(5, 14): grid(5, 14),
                Position(11, 2): grid(11, 2),
            },
            [],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snap)

        self.assertEqual(
            policy._approved_quest_strategy_key(snap, [], []), "8"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:approach-final-target")

    def test_q34_empty_bee_source_transitions_to_full_battlefield_sweep(self):
        policy = self._q34_source_policy()
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15),
            (107, 9, 11),
            (107, 11, 9),
        }
        at_empty_source = Snapshot(
            player(3, 13),
            {
                Position(3, 13): grid(3, 13, in_view=True),
                Position(3, 14): grid(3, 14, in_view=True),
                Position(11, 2): grid(11, 2, in_view=True),
            },
            [],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(at_empty_source)

        self.assertEqual(
            policy._approved_quest_strategy_key(at_empty_source, [], []), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "quest-strategy:final-source-cleared")
        self.assertIn(
            Position(3, 13), policy._quest_strategy_surveyed_placements[34]
        )

        beside_empty_source = replace(
            at_empty_source,
            player=player(3, 14),
        )
        policy._build_grid_index(beside_empty_source)
        key = policy._approved_quest_strategy_key(beside_empty_source, [], [])

        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")
        self.assertIn(key, {"2", "4", "6", "8"})

    def test_q34_exit_reuses_accessible_door_and_avoids_jammed_glass(self):
        policy = self._policy()
        safe_path = (
            {(3, x) for x in range(14, 19)}
            | {(4, 14), (5, 14), (5, 15), (5, 16), (5, 17), (5, 18),
               (5, 19), (5, 20)}
            | {(y, 20) for y in range(1, 6)}
        )
        jammed_shortcut = {(2, 18), (1, 18), (1, 19), (1, 20)}
        battlefield = QuestBattlefield(
            terrain={
                position: (
                    "door" if position in {(4, 14), (2, 18)} else "floor"
                )
                for position in safe_path | jammed_shortcut
            },
            entrance=(1, 20),
            exit=(1, 20),
        )
        navigator = QuestFloorNavigator(34, battlefield)
        snap = Snapshot(
            player(3, 18),
            {
                Position(2, 18): grid(2, 18, closed_door=True),
                Position(3, 18): grid(3, 18),
                Position(4, 14): grid(4, 14),
            },
            [],
            floor_key=(0, 5, 34),
        )

        self.assertEqual(navigator._exit(policy, snap), "4")
        self.assertEqual(policy.last_reason, "quest:exit:route")

    def test_q34_fallback_route_avoids_every_adjacent_sword_cell(self):
        policy = self._policy()
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34], battlefield=None
        )
        grids = {
            Position(9, 13): grid(9, 13),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13),
            Position(11, 11): grid(11, 11),
            Position(11, 12): grid(11, 12),
            Position(11, 13): grid(11, 13),
        }
        snap = Snapshot(player(9, 13), grids, [], floor_key=(0, 5, 34))
        policy._build_grid_index(snap)

        step = policy._quest_strategy_route_step(
            snap, policy._quest_strategies[34], Position(11, 11)
        )

        self.assertEqual(step, Position(10, 13))
        self.assertGreater(step.distance_to(Position(9, 11)), 1)

    def test_q34_can_leave_a_defeated_sword_recovery_lane(self):
        policy = self._policy()
        policy._quest_strategy_cleared_targets[34] = {(107, 9, 11)}
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34], battlefield=None
        )
        grids = {
            Position(9, 11): grid(9, 11),
            Position(10, 11): grid(10, 11),
            Position(11, 12): grid(11, 12),
            Position(11, 13): grid(11, 13),
        }
        snap = Snapshot(player(9, 11), grids, [], floor_key=(0, 5, 34))
        policy._build_grid_index(snap)

        step = policy._quest_strategy_route_step(
            snap, policy._quest_strategies[34], Position(11, 13)
        )

        self.assertEqual(step, Position(10, 11))

    def test_q34_opens_lower_left_door_before_combat(self):
        policy = self._policy()
        grids = {
            **{Position(1, x): grid(1, x) for x in range(1, 21)},
            **{Position(y, 1): grid(y, 1) for y in range(2, 12)},
            Position(11, 2): grid(11, 2, closed_door=True),
        }
        monster = replace(hostile(1, 7, 15), race_id=243)
        start = Snapshot(
            player(1, 20), grids, [monster],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(start)

        self.assertEqual(
            policy._approved_quest_strategy_key(start, [monster], []), "4"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:approach-opening-door"
        )

        unobserved = replace(start, grids={
            **{Position(1, x): grid(1, x) for x in range(1, 21)},
            **{Position(y, 1): grid(y, 1) for y in range(2, 12)},
        })
        self.assertEqual(
            policy._approved_quest_strategy_key(unobserved, [monster], []), "4"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:approach-opening-door"
        )

        left_edge = replace(start, player=player(2, 1))
        self.assertEqual(
            policy._approved_quest_strategy_key(left_edge, [monster], []), "2"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:approach-opening-door"
        )

        approach = replace(start, player=player(11, 1))
        self.assertEqual(
            policy._approved_quest_strategy_key(approach, [monster], []), "o6"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:open-opening-door")

    def test_q34_picks_up_and_equips_opening_lantern_before_continuing(self):
        policy = self._policy(q34_opening_light=True)
        grids = {
            Position(10, 20): grid(10, 20),
            Position(10, 19): grid(10, 19),
        }
        on_lantern = Snapshot(
            player(10, 20), grids, [],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        on_lantern = replace(
            on_lantern,
            grids={Position(10, 20): grid(
                10, 20, objects=1, object_tvals=(TVAL_LITE,), in_view=True
            )},
        )
        policy._build_grid_index(on_lantern)

        self.assertEqual(
            policy._approved_quest_strategy_key(on_lantern, [], []), PICKUP_KEY
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:pickup-opening-lantern"
        )

        carried = replace(
            on_lantern,
            grids={Position(10, 20): grid(10, 20, in_view=True)},
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000),
                item("l", TVAL_LITE, SV_LITE_LANTERN, aware=False, fuel=0),
            ],
        )
        self.assertEqual(
            policy._approved_quest_strategy_key(carried, [], []), "wl"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:equip-opening-lantern"
        )

        outer_route = (
            {Position(y, 20): grid(y, 20) for y in range(1, 11)}
            | {Position(1, x): grid(1, x) for x in range(1, 21)}
            | {Position(y, 1): grid(y, 1) for y in range(1, 12)}
            | {Position(11, 2): grid(11, 2, closed_door=True)}
        )
        equipped = replace(
            carried,
            grids=outer_route,
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
            ],
            equipment=[
                item(
                    "light", TVAL_LITE, SV_LITE_LANTERN,
                    aware=False, fuel=0, is_equipment=True,
                )
            ],
        )
        policy._build_grid_index(equipped)
        self.assertEqual(
            policy._approved_quest_strategy_key(equipped, [], []), "8"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:approach-opening-door"
        )

    def test_q34_routes_down_outer_corridor_to_opening_lantern(self):
        policy = self._policy(q34_opening_light=True)
        route = {
            Position(y, 20): grid(y, 20, in_view=(y <= 2))
            for y in range(1, 11)
        }
        start = Snapshot(
            player(1, 20), route, [],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(start)

        self.assertEqual(
            policy._approved_quest_strategy_key(start, [], []), "2"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:approach-opening-lantern"
        )

    def test_q34_routes_back_from_lantern_on_static_battlefield(self):
        policy = self._policy(q34_opening_light=True)
        terrain = {
            **{(y, 20): "floor" for y in range(1, 11)},
            **{(1, x): "floor" for x in range(1, 21)},
            **{(y, 1): "floor" for y in range(1, 12)},
            (11, 2): "door",
        }
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34],
            battlefield=QuestBattlefield(terrain=terrain),
        )
        snapshot = Snapshot(
            player(10, 20),
            {
                Position(10, 20): grid(10, 20),
                Position(9, 20): grid(9, 20),
            },
            [],
            equipment=[
                item(
                    "light", TVAL_LITE, SV_LITE_LANTERN,
                    aware=False, fuel=0, is_equipment=True,
                )
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snapshot)

        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), "8"
        )
        self.assertEqual(
            policy.last_reason, "quest-strategy:approach-opening-door"
        )

    def test_q34_recovery_never_routes_through_glass_doors(self):
        policy = self._policy()
        grids = {
            Position(5, 8): grid(5, 8),
            Position(4, 9): grid(4, 9, closed_door=True),
            Position(3, 10): grid(3, 10, objects=1),
        }
        snap = Snapshot(
            player(5, 8), grids, [],
            inventory=[
                item("t", TVAL_LITE, SV_LITE_TORCH, count=19, fuel=5000)
            ],
            floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snap)

        self.assertEqual(policy._approved_quest_strategy_key(snap, [], []), "5")
        self.assertEqual(
            policy.last_reason, "quest:blocked:q34-throw-point-unreachable"
        )

    def test_never_move_races_come_from_monrace_flags_not_quest_ids(self):
        profile = replace(self.profiles[1], priority_targets=(900, 901))
        stationary = MonraceKnowledge(
            10, 110, False, False, flags=frozenset({"NEVER_MOVE"})
        )
        mobile = MonraceKnowledge(10, 110, False, False)
        policy = HengbotPolicy(monrace_knowledge={900: stationary, 901: mobile})

        self.assertEqual(policy._quest_never_move_races(profile), {900})

    def test_q34_final_approach_keeps_starvation_gate_reachable(self):
        policy = self._policy()
        fixed = [
            replace(hostile(1, 7, 15), race_id=243),
            replace(hostile(2, 9, 11), race_id=107),
            replace(hostile(3, 11, 9), race_id=107),
        ]
        base = Snapshot(
            player(10, 20),
            {
                Position(10, 20): grid(10, 20),
                Position(11, 2): grid(11, 2),
            },
            fixed,
            floor_key=(0, 1, 34),
        )
        policy._fixed_quest_speed_attempted = True
        policy._approved_quest_strategy_key(base, fixed, [])
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15),
            (107, 9, 11),
            (107, 11, 9),
        }
        hungry = replace(
            base, player=player(10, 20, food=1500), visible_monsters=[],
            inventory=[item("f", TVAL_FOOD, FOOD)],
        )

        self.assertEqual(policy._approved_quest_strategy_key(hungry, [], []), "Ef")
        self.assertEqual(policy.last_reason, "survival:eat")

    def test_q34_generic_supply_recovery_ignores_a_chest(self):
        policy = self._policy()
        policy._fixed_quest_speed_attempted = True
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15), (107, 9, 11), (107, 11, 9)
        }
        snapshot = Snapshot(
            player(10, 20),
            {
                Position(10, 20): replace(
                    grid(10, 20, objects=1), object_tvals=(TVAL_CHEST,)
                ),
                Position(11, 2): grid(11, 2),
            }, [], floor_key=(0, 5, 34),
        )
        policy._build_grid_index(snapshot)

        key = policy._approved_quest_strategy_key(snapshot, [], [])

        self.assertNotEqual(key, PICKUP_KEY)
        self.assertNotEqual(policy.last_reason, "quest-strategy:recover-torch")

    def test_approved_quest_uses_profile_heal_threshold(self):
        policy = self._policy()
        threat = replace(hostile(1, 10, 21, distance=1), race_id=174)
        snap = Snapshot(
            player(10, 20, hp=54, max_hp=100),
            {Position(10, 20): grid(10, 20), Position(10, 21): grid(10, 21, monster=True)},
            [threat], inventory=[item("h", TVAL_POTION, SV_POTION_HEALING)],
            floor_key=(0, 1, 34),
        )
        policy._fixed_quest_speed_attempted = True

        self.assertEqual(policy.choose_key(snap), "qh")
        self.assertEqual(policy.last_reason, "item:heal")

    def test_q1_retakes_hold_and_throws_at_distance_two(self):
        policy = self._policy()
        grids = {Position(8, x): grid(8, x) for x in range(1, 6)}
        displaced = Snapshot(player(8, 2), grids, [], floor_key=(0, 1, 1))
        policy._build_grid_index(displaced)
        self.assertEqual(policy._approved_quest_strategy_key(displaced, [], []), "6")
        thief = replace(hostile(1, 8, 5, distance=2), race_id=150)
        at_hold = replace(displaced, player=player(8, 3), visible_monsters=[thief],
                          inventory=[item("t", TVAL_LITE, SV_LITE_TORCH, fuel=5000)])
        policy._fixed_quest_speed_attempted = True
        self.assertEqual(policy._approved_quest_strategy_key(at_hold, [thief], []), "vt6")

    def test_q1_recovers_thrown_torch_before_retaking_hold(self):
        policy = self._policy()
        grids = {
            Position(8, 3): grid(8, 3),
            Position(8, 4): grid(8, 4),
            Position(8, 5): replace(
                grid(8, 5, objects=1), object_tvals=(TVAL_LITE,)
            ),
        }
        displaced = Snapshot(player(8, 4), grids, [], floor_key=(0, 5, 1))
        policy._build_grid_index(displaced)

        self.assertEqual(
            policy._approved_quest_strategy_key(displaced, [], []), "6"
        )
        self.assertEqual(policy.last_reason, "quest-strategy:recover-torch")

    def test_q1_does_not_treat_a_chest_as_a_recoverable_torch(self):
        policy = self._policy()
        grids = {
            Position(8, 3): grid(8, 3),
            Position(8, 4): grid(8, 4),
            Position(8, 5): replace(
                grid(8, 5, objects=1), object_tvals=(TVAL_CHEST,)
            ),
        }
        displaced = Snapshot(player(8, 4), grids, [], floor_key=(0, 5, 1))
        policy._build_grid_index(displaced)

        key = policy._approved_quest_strategy_key(displaced, [], [])

        self.assertNotEqual(key, "6")
        self.assertNotEqual(policy.last_reason, "quest-strategy:recover-torch")

    def test_q1_holds_position_between_visible_waves(self):
        policy = self._policy()
        at_hold = Snapshot(
            player(8, 3), {Position(8, 3): grid(8, 3)}, [], floor_key=(0, 5, 1)
        )
        policy._build_grid_index(at_hold)

        self.assertEqual(policy._approved_quest_strategy_key(at_hold, [], []), "5")
        self.assertEqual(policy.last_reason, "quest-strategy:hold")

    def test_completed_q1_leaves_hold_for_quest_exit(self):
        policy = self._policy()
        grids = {
            Position(8, 3): grid(8, 3),
            Position(8, 4): grid(8, 4, upstairs=True, has_quest_exit=True, quest_id=1),
        }
        completed = Snapshot(
            player(8, 3), grids, [], floor_key=(0, 5, 1),
            quests={1: QuestState(id=1, status=QUEST_STATUS_COMPLETED, fixed=True)},
        )

        self.assertEqual(policy.choose_key(completed), "4")
        self.assertEqual(policy.last_reason, "quest:exit:route")

    def test_conditional_speed_uses_live_three_turn_projection(self):
        policy = self._policy()
        monster = replace(hostile(1, 8, 5), race_id=150)
        snap = Snapshot(player(8, 3, hp=100, max_hp=100),
                        {Position(8, x): grid(8, x) for x in range(3, 6)}, [monster],
                        inventory=[item("s", TVAL_POTION, SV_POTION_SPEED)],
                        floor_key=(0, 1, 1))
        with patch.object(policy, "threat_prediction", return_value={"operational_total": 49}):
            self.assertNotEqual(policy._approved_quest_strategy_key(snap, [monster], []), "qs")
        with patch.object(policy, "threat_prediction", return_value={"operational_total": 50}):
            self.assertEqual(policy._approved_quest_strategy_key(snap, [monster], []), "qs")

    def test_abort_allowed_leaves_at_threshold_but_once_profiles_do_not(self):
        upstairs = {Position(10, 10): grid(10, 10, upstairs=True)}
        q14 = Snapshot(player(10, 10, hp=30, max_hp=100), upstairs, [],
                       floor_key=(0, 5, 14))
        policy = self._policy()
        self.assertEqual(policy._approved_quest_strategy_key(q14, [], []), "<")
        self.assertEqual(policy.last_reason, "quest-strategy:abort")
        for quest_id in (1, 34):
            with self.subTest(quest_id=quest_id):
                snap = replace(q14, floor_key=(0, 1, quest_id))
                self.assertNotEqual(
                    self._policy()._approved_quest_strategy_key(snap, [], []), "<"
                )

    def test_flee_upstairs_reason_records_quest_failure(self):
        grids = {
            Position(10, 10): grid(
                10, 10, upstairs=True, has_quest_exit=True, quest_id=self.QUEST_ID
            ),
            Position(10, 11): grid(10, 11, monster=True),
        }
        snap = Snapshot(
            player(10, 10, hp=20, max_hp=150),
            grids,
            [hostile(1, 10, 11, hp=100)],
            floor_key=(0, 1, self.QUEST_ID),
            quests={self.QUEST_ID: self._quest(1)},
        )
        policy = HengbotPolicy()

        key = policy.choose_key(snap)

        self.assertEqual(key, "<")
        self.assertEqual(policy.last_reason, "flee:stairs-quest-fail")

class DungeonConquestTest(unittest.TestCase):
    """Priority goal: clear an unconquered dungeon whose bottom is within the
    resistance limit for the final guardian's gear, and collect that drop before
    recalling out."""

    def _dk(self):
        return {
            1: DungeonInfo(1, "Angband", 1, 127, 30),
            2: DungeonInfo(2, "Galgals", 1, 13, 1),
            3: DungeonInfo(3, "Orc Cave", 10, 22, 5),
            4: DungeonInfo(4, "Labyrinth", 10, 18, 1),
            7: DungeonInfo(7, "Forest", 15, 32, 5),
            14: DungeonInfo(14, "Mountain", 25, 45, 20),
        }

    def _policy(self):
        return HengbotPolicy(dungeon_knowledge=self._dk())

    def _snap(self, abilities, *, conquered=(), clvl=26):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=clvl,
                   abilities=frozenset(abilities)),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            entered_dungeon_ids=(1, 2, 3, 4, 7, 14),
            conquered_dungeon_ids=conquered,
            angband_recall_unlocked=True,
        )

    ALL_2530 = frozenset(
        {"free_action", "resist_conf", "resist_fire", "resist_pois", "resist_cold",
         "resist_elec", "resist_acid"}
    )

    @staticmethod
    def _minotaur_knowledge():
        return MonraceKnowledge(
            max_hp=330,
            average_hp=330,
            speed=125,
            can_summon=False,
            friendly=False,
            level=18,
            max_melee_damage=126,
            flags=frozenset({"UNIQUE"}),
            blows=(
                MonsterBlow("BUTT", "HURT", 6, 6),
                MonsterBlow("BUTT", "HURT", 6, 6),
                MonsterBlow("BUTT", "HURT", 3, 6),
                MonsterBlow("BUTT", "HURT", 3, 6),
            ),
        )

    def _minotaur_snapshot(self, healing_count):
        snapshot = self._snap(self.ALL_2530, conquered=(3,), clvl=23)
        return replace(
            snapshot,
            player=replace(
                snapshot.player,
                hp=400,
                max_hp=400,
                speed=110,
                ac=43,
                melee_skill=140,
                main_hand_blows=5,
                main_hand_to_h=21,
                main_hand_to_d=8,
            ),
            inventory=[
                item("s", TVAL_POTION, SV_POTION_SPEED),
                item("h", TVAL_POTION, SV_POTION_HEALING, count=healing_count),
            ],
            equipment=[
                item(
                    "main_hand",
                    23,
                    20,
                    is_equipment=True,
                    damage_dice_num=3,
                    damage_dice_sides=4,
                )
            ],
        )

    def _guardian_policy(self):
        knowledge = self._dk()
        knowledge[4] = replace(knowledge[4], guardian_id=1034)
        return HengbotPolicy(
            dungeon_knowledge=knowledge,
            monrace_knowledge={1034: self._minotaur_knowledge()},
        )

    def _yeek_guardian_policy(self):
        knowledge = self._dk()
        knowledge[2] = replace(knowledge[2], guardian_id=237)
        guardian = replace(
            self._minotaur_knowledge(),
            max_hp=180,
            average_hp=180,
            speed=120,
            can_summon=True,
            max_melee_damage=26,
            blows=(MonsterBlow("HIT", "HURT", 2, 6),),
        )
        policy = HengbotPolicy(
            dungeon_knowledge=knowledge,
            monrace_knowledge={237: guardian},
        )
        set_completed_equipment_optimization(policy)
        return policy

    def _launchable_yeek_snapshot(self, *, recall_count=10):
        snapshot = replace(
            self._minotaur_snapshot(1),
            player=replace(self._minotaur_snapshot(1).player, gold=130),
            entered_dungeon_ids=(1, 2),
            angband_recall_unlocked=True,
        )
        return replace(
            snapshot,
            inventory=[
                *snapshot.inventory,
                item(
                    "r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
                    count=recall_count,
                ),
                item("f", TVAL_FOOD, FOOD_MIN_SVAL, count=10),
                item("o", TVAL_FLASK, SV_FLASK_OIL, count=10),
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=20),
                item(
                    "c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10
                ),
                item(
                    "i", TVAL_STAFF, SV_STAFF_IDENTIFY,
                    charges=20,
                ),
            ],
            equipment=[
                *snapshot.equipment,
                item(
                    "light", TVAL_LITE, SV_LITE_LANTERN,
                    fuel=5000, is_equipment=True,
                ),
            ],
        )

    def test_resistance_limit_without_free_action_stops_below_20(self):
        self.assertEqual(self._policy()._resistance_depth_limit(self._snap({"resist_fire"})), 19)

    def test_resistance_limit_covers_the_bands_the_char_can_pass(self):
        # Free action + confusion + fire cover 20-25F, but nothing covers
        # 26-30F, so the limit is 25.
        pol = self._policy()
        self.assertEqual(
            pol._resistance_depth_limit(
                self._snap({"free_action", "resist_conf", "resist_fire"})
            ),
            25,
        )

    def test_targets_deepest_conquerable_unconquered_dungeon(self):
        # limit 30 -> Orc Cave (maxDepth 22) is the deepest clearable; Forest(32) /
        # Mountain(45) exceed the resistance limit.
        self.assertEqual(self._policy()._conquest_target(self._snap(self.ALL_2530)), 3)

    def test_steps_to_the_next_after_the_deepest_is_conquered(self):
        pol = self._policy()
        self.assertEqual(pol._conquest_target(self._snap(self.ALL_2530, conquered=(3,))), 4)

    def test_does_not_target_labyrinth_without_a_viable_guardian_kit(self):
        policy = self._guardian_policy()

        self.assertIsNone(policy._conquest_target(self._minotaur_snapshot(1)))
        self.assertEqual(policy._conquest_target(self._minotaur_snapshot(5)), 4)

    def test_targets_beatable_yeek_guardian_even_after_angband_is_unlocked(self):
        policy = self._yeek_guardian_policy()
        snapshot = replace(
            self._minotaur_snapshot(1),
            entered_dungeon_ids=(1, 2),
            angband_recall_unlocked=True,
        )

        self.assertTrue(policy._guardian_fight_viable(snapshot, policy._dungeon_knowledge[2]))
        self.assertEqual(policy._conquest_target(snapshot), 2)

        policy._observe(snapshot)
        self.assertEqual(policy._target_dungeon_id, 2)

    def test_launchable_beatable_guardian_cancels_fundraising_latch(self):
        policy = self._yeek_guardian_policy()
        policy._fundraising_mode = "scavenge"
        snapshot = replace(
            self._minotaur_snapshot(1),
            entered_dungeon_ids=(1, 2),
            angband_recall_unlocked=True,
        )
        policy._town_departure_ready = lambda _snapshot: True
        policy._combat_weapon_ready = lambda _snapshot: True

        policy._observe(snapshot)

        self.assertEqual(policy._target_dungeon_id, 2)
        self.assertIsNone(policy._fundraising_mode)

    def test_blocked_poor_conquest_observe_decide_alternation_is_stable(self):
        policy = self._yeek_guardian_policy()
        snapshot = self._launchable_yeek_snapshot(recall_count=0)
        policy._fundraising_supplies_ready = lambda _snapshot: False
        policy._observe(snapshot)
        self.assertEqual(policy._conquest_target(snapshot), 2)
        self.assertFalse(policy._conquest_departure_ready(snapshot))
        policy._identification_need = "full"
        policy._start_fundraising(snapshot)
        policy._town_store_attempted[STORE_HOME] = 77

        reasons = []
        for offset in range(8):
            fresh = replace(snapshot, turn=snapshot.turn + offset)
            policy.choose_key(fresh)
            reasons.append(policy.last_reason)
            self.assertEqual(policy._fundraising_mode, "prepare")

        self.assertEqual(policy._town_store_attempted[STORE_HOME], 77)
        self.assertNotIn("home:need-full-identify", reasons)

    def test_blocked_conquest_clears_fundraising_once_when_departure_becomes_ready(self):
        policy = self._yeek_guardian_policy()
        blocked = self._launchable_yeek_snapshot(recall_count=0)
        ready = self._launchable_yeek_snapshot()

        policy._observe(blocked)
        policy._start_fundraising(blocked)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertIsNone(policy._fundraising_cleared_for_conquest)

        policy._observe(ready)
        self.assertIsNone(policy._fundraising_mode)
        self.assertEqual(policy._fundraising_cleared_for_conquest, 2)

        policy._start_fundraising(ready)
        policy._observe(replace(ready, turn=ready.turn + 1))
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._fundraising_cleared_for_conquest, 2)

    def test_beatable_guardian_defers_unavailable_full_identification(self):
        policy = self._yeek_guardian_policy()
        candidate = item(
            "c",
            45,
            1,
            known=True,
            fully_known=False,
            is_equipment=True,
            is_ego=True,
        )
        snapshot = replace(
            self._minotaur_snapshot(1),
            player=replace(self._minotaur_snapshot(1).player, gold=625),
            inventory=[*self._minotaur_snapshot(1).inventory, candidate],
        )
        signature = policy._item_signature(candidate)

        policy._observe(snapshot)
        policy._identification_need = "full"
        policy._identification_candidate = signature
        policy._town_store_attempted[STORE_ALCHEMIST] = 0
        policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(
            store_type=STORE_ALCHEMIST, items=[]
        )
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
            policy._effective_town_id(snapshot), snapshot.turn
        )

        # Exercise the terminal identification branch directly: the top-level
        # router's new poverty source otherwise activates fundraising before
        # this already-in-flight defer can be serviced.
        next_store = policy._town_terminal_transitions(snapshot)

        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)
        self.assertIsNone(policy._identification_need)
        self.assertIn(signature, policy._deferred_home_items)
        self.assertNotEqual(next_store, STORE_ALCHEMIST)

    def test_multiplier_guardian_is_not_selected_for_conquest(self):
        policy = self._yeek_guardian_policy()
        policy._monrace_knowledge[237] = replace(
            policy._monrace_knowledge[237], can_multiply=True
        )
        snapshot = replace(
            self._minotaur_snapshot(5),
            entered_dungeon_ids=(1, 2),
        )

        self.assertIsNone(policy._conquest_target(snapshot))

    def test_beatable_summoning_guardian_teleports_to_reposition_without_returning(self):
        policy = self._yeek_guardian_policy()
        guardian = replace(
            hostile(
                1,
                10,
                13,
                hp=180,
                max_hp=180,
                distance=3,
                can_summon=True,
            ),
            race_id=237,
        )
        grids = {
            Position(y, x): grid(y, x, monster=(y, x) == (10, 13))
            for y in range(8, 13)
            for x in range(8, 15)
        }
        snapshot = replace(
            self._minotaur_snapshot(1),
            floor_key=(2, 13, 0),
            town_flag=False,
            grids=grids,
            visible_monsters=[guardian],
            entered_dungeon_ids=(1, 2),
            inventory=[
                *self._minotaur_snapshot(1).inventory,
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT),
            ],
        )
        policy._target_dungeon_id = 2

        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "guardian:teleport-to-cover")
        self.assertEqual(policy._last_return_trigger, "guardian-reposition")
        self.assertFalse(policy._returning_to_town)

    def test_returns_from_penultimate_floor_when_guardian_kit_is_insufficient(self):
        policy = self._guardian_policy()
        snapshot = replace(
            self._minotaur_snapshot(1),
            floor_key=(4, 17, 0),
            town_flag=False,
            grids={Position(10, 10): grid(10, 10, downstairs=True)},
        )
        downstairs = snapshot.grid_at(snapshot.player.position)

        self.assertTrue(policy._guardian_descent_blocked(snapshot))
        self.assertTrue(policy._should_start_town_return(snapshot))
        self.assertEqual(policy._last_return_trigger, "guardian-kit-insufficient")
        self.assertFalse(policy._is_descent_target(snapshot, downstairs))

    def test_conquered_dungeon_does_not_recheck_dead_guardian_kit(self):
        policy = self._guardian_policy()
        snapshot = replace(
            self._minotaur_snapshot(1),
            floor_key=(4, 18, 0),
            town_flag=False,
            conquered_dungeon_ids=(4,),
        )

        self.assertFalse(policy._guardian_descent_blocked(snapshot))

    def test_no_target_when_all_reachable_dungeons_are_conquered(self):
        pol = self._policy()
        self.assertIsNone(pol._conquest_target(self._snap(self.ALL_2530, conquered=(3, 4))))

    def test_conquest_target_does_not_use_player_level(self):
        pol = self._policy()
        snapshot = self._snap(self.ALL_2530, conquered=(), clvl=1)

        with patch.object(pol, "_guardian_fight_viable", return_value=True):
            self.assertEqual(pol._conquest_target(snapshot), 3)

    def test_chameleon_cave_is_never_a_conquest_target_or_commitment(self):
        knowledge = self._dk()
        knowledge[DUNGEON_CHAMELEON_CAVE] = DungeonInfo(
            DUNGEON_CHAMELEON_CAVE,
            "Chameleon cave",
            30,
            45,
            30,
            guardian_id=9999,
        )
        policy = HengbotPolicy(dungeon_knowledge=knowledge)
        policy._conquest_committed = DUNGEON_CHAMELEON_CAVE
        snapshot = replace(
            self._snap(self.ALL_2530, conquered=(3, 4, 7, 14), clvl=50),
            entered_dungeon_ids=(1, DUNGEON_CHAMELEON_CAVE),
        )

        self.assertIsNone(policy._conquest_target(snapshot))
        self.assertIsNone(policy._conquest_committed)

    def test_observe_latches_the_loot_phase_on_a_fresh_conquest(self):
        pol = self._policy()
        before = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(4, 18, 0),
            entered_dungeon_ids=(1, 2, 4),
            conquered_dungeon_ids=(),
            angband_recall_unlocked=True,
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(4, 18, 0),  # standing in the Labyrinth, just conquered
            entered_dungeon_ids=(1, 2, 4),
            conquered_dungeon_ids=(4,),
            angband_recall_unlocked=True,
        )
        pol._observe(before)
        pol._observe(snap)
        self.assertEqual(pol._victory_loot_dungeon, 4)

    def test_resume_on_conquered_yeek_floor_does_not_rearm_victory_return(self):
        pol = self._policy()
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            entered_dungeon_ids=(1, DUNGEON_YEEK_CAVE),
            conquered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )

        pol._observe(snap)

        self.assertFalse(pol._yeek_victory_loot)
        self.assertTrue(pol._yeek_conquest_processed)

    def test_conquest_loot_sweeps_the_floor_before_returning(self):
        pol = self._policy()
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10, objects=1)},  # guardian drop underfoot
            [],
            floor_key=(4, 18, 0),
            inventory=[],
        )
        pol._victory_loot_dungeon = 4
        pol._position_changed = True
        self.assertEqual(pol._conquest_loot_key(snap), "g")
        self.assertEqual(pol.last_reason, "conquest:pickup")

    def test_yeek_victory_full_pack_discards_junk_before_more_loot(self):
        pol = self._policy()
        junk = item("a", TVAL_FOOD, 1, aware=False, known=False, name="mushroom")
        essentials = [
            item(
                chr(ord("b") + index),
                TVAL_SCROLL,
                SV_SCROLL_TELEPORT,
                name="Teleport",
            )
            for index in range(PACK_CAPACITY - 1)
        ]
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10, objects=1)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 13, 0),
            inventory=[junk, *essentials],
        )
        pol._yeek_victory_loot = True

        self.assertEqual(pol._victory_loot_key(snap), "01ka")
        self.assertEqual(pol.last_reason, "inventory:destroy-disposable-item")

    def test_conquest_loot_returns_once_the_floor_is_clean(self):
        pol = self._policy()
        recall = item(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, name="Word of Recall"
        )
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, level=26),
            {Position(10, 10): grid(10, 10)},  # nothing left to grab
            [],
            floor_key=(4, 18, 0),
            inventory=[recall],
        )
        pol._victory_loot_dungeon = 4
        self.assertEqual(pol._conquest_loot_key(snap), "ra")
        self.assertIsNone(pol._victory_loot_dungeon)
        self.assertTrue(pol._returning_to_town)
        self.assertEqual(pol._last_return_trigger, "conquest-complete")
        self.assertEqual(pol.last_reason, "return:recall")

    def test_latch_survives_a_speed_potion_disappearing_from_the_pack(self):
        # _guardian_fight_viable's fallback branch treats the Labyrinth Minotaur
        # fight as viable only while a Speed potion is held (see the
        # SV_POTION_SPEED check in _guardian_fight_viable): at healing=5 the base
        # (unboosted) projection fails and only the +speed retry succeeds
        # (empirically: viable with the potion in the pack, not viable without
        # it, healing held fixed). Without a latch, drinking or stashing that
        # potion would revert the conquest target on the very next observe, and
        # re-buying it would flip it back -- the recall destination churning on
        # nothing but consumable possession.
        policy = self._guardian_policy()
        with_speed = self._minotaur_snapshot(5)
        self.assertEqual(policy._conquest_target(with_speed), 4)

        without_speed = replace(
            with_speed,
            inventory=[it for it in with_speed.inventory if it.slot != "s"],
        )
        self.assertEqual(policy._conquest_target(without_speed), 4)

    def test_unlatches_once_the_dungeon_is_conquered(self):
        policy = self._guardian_policy()
        with_speed = self._minotaur_snapshot(5)
        self.assertEqual(policy._conquest_target(with_speed), 4)

        conquered = replace(with_speed, conquered_dungeon_ids=(3, 4))
        self.assertIsNone(policy._conquest_target(conquered))
        self.assertIsNone(policy._conquest_committed)

    def test_unlatches_when_the_resistance_limit_drops_below_its_max_depth(self):
        policy = self._policy()
        # Labyrinth (4) is already done, so Orc Cave (3, max_depth 22) is the
        # only dungeon within the resistance limit (30) and becomes committed.
        committed_snap = self._snap(self.ALL_2530, conquered=(4,))
        self.assertEqual(policy._conquest_target(committed_snap), 3)

        # Losing conf/fire resistance drops the limit to 19: Orc Cave's
        # max_depth (22) now exceeds it -- a hard unviability, not a consumable
        # change -- and Labyrinth is already conquered, so nothing is left to
        # fall back to.
        regressed = self._snap(set(), conquered=(4,))
        self.assertIsNone(policy._conquest_target(regressed))
        self.assertIsNone(policy._conquest_committed)

class WarningGridComposedWalkTest(unittest.TestCase):
    """The composed-walk callers (walk + follow-up tail) against the warning
    gate, pinned on the fixed-quest entrance shape: the caller's tail ('y')
    is exactly a key input_check accepts, so ungated it silently confirms a
    first-encounter TR_WARNING prompt (codex review BLOCKER 1)."""

    QUEST_ID = 1
    PROMPT = "本当にこのまま進むか？[y/n]"
    ENTRANCE = Position(35, 177)

    def _town_map(self) -> TownMap:
        walkable = frozenset(
            Position(y, x) for y in range(66) for x in range(198)
        )
        return TownMap(
            name="Outpost",
            width=198,
            height=66,
            walkable=walkable,
            quest_buildings={self.QUEST_ID: frozenset({Position(26, 98)})},
            quest_entrances={self.QUEST_ID: frozenset({self.ENTRANCE})},
            reward_positions=frozenset({Position(27, 98)}),
        )

    def _snapshot(self, y, x, *, messages=(), inventory=()):
        quest = QuestState(
            id=self.QUEST_ID,
            name="Thieves Hideout",
            status=1,
            type=6,
            level=5,
            flags=6,
            fixed=True,
            has_reward=True,
            reward_baseitem_id=42,
        )
        grids = {
            Position(35, 176): grid(35, 176),
            self.ENTRANCE: grid(
                self.ENTRANCE.y,
                self.ENTRANCE.x,
                has_quest_enter=True,
                quest_id=self.QUEST_ID,
            ),
        }
        return Snapshot(
            player(y, x, level=8, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            town_id=0,
            town_index=1,
            quests={self.QUEST_ID: quest},
            inventory=list(inventory),
            messages=tuple(messages),
        )

    def test_latched_entrance_walk_is_blocked_while_supplies_remain(self):
        # After a refusal, the composed quest-entry walk (direction + 'y')
        # must not be issued while a movement scroll remains: the gate rules
        # on the COMPLETE key, so the caller's tail cannot confirm the
        # re-raised prompt.
        supply = [item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT)]
        policy = HengbotPolicy(self._town_map())
        self.assertEqual(
            policy.choose_key(self._snapshot(35, 176, inventory=supply)), "6y"
        )
        self.assertEqual(policy.last_reason, "fixedquest:enter")

        refusal = policy.choose_key(
            self._snapshot(35, 176, messages=(self.PROMPT,), inventory=supply)
        )
        self.assertEqual(refusal, "n")
        self.assertIn(self.ENTRANCE, policy._warning_refused_cells)

        key = policy.choose_key(self._snapshot(35, 176, inventory=supply))
        self.assertNotIn("y", key)
        self.assertNotEqual(key[:1], "6")
        self.assertEqual(policy.last_reason, "warning:blocked-step")

    def test_fixed_quest_entry_obeys_incomplete_optimizer_gate(self):
        policy = HengbotPolicy(self._town_map())
        policy._prepare_equipment_optimization = lambda _snapshot: SimpleNamespace(
            ready=False,
            result=None,
            transaction=None,
            blockers=("home-scan-incomplete",),
        )
        snapshot = self._snapshot(
            35, 177,
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=3)],
        )

        self.assertIsNone(policy._fixed_quest_enter_key(snapshot, self.QUEST_ID))
        self.assertIn("equipment_departure_ready", policy._departure_block["failed"])

    def test_fixed_quest_entry_needs_no_recall_when_equipment_is_ready(self):
        policy = HengbotPolicy(self._town_map())
        set_completed_equipment_optimization(policy)
        snapshot = self._snapshot(35, 177, inventory=[])

        self.assertEqual(
            policy._fixed_quest_enter_key(snapshot, self.QUEST_ID), ">y"
        )

    def test_tail_answered_crossing_is_latched_not_silent(self):
        # First encounter: the entrance is unlatched, so the composed walk
        # goes out with its tail and the warning prompt (if it fires) is
        # answered by that tail.  The next snapshot shows the player ON the
        # target with the prompt message: the crossing was NOT sanctioned by
        # the exhausted-supplies rule, so the grid must be latched — at most
        # one such crossing per floor, never silent.
        supply = [item("a", TVAL_SCROLL, SV_SCROLL_TELEPORT)]
        policy = HengbotPolicy(self._town_map())
        self.assertEqual(
            policy.choose_key(self._snapshot(35, 176, inventory=supply)), "6y"
        )

        policy.choose_key(
            self._snapshot(
                self.ENTRANCE.y,
                self.ENTRANCE.x,
                messages=(self.PROMPT,),
                inventory=supply,
            )
        )

        self.assertIn(self.ENTRANCE, policy._warning_refused_cells)
        self.assertNotEqual(policy.last_reason, "warning:refuse")
