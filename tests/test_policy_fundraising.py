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

class IdleItemDepositTest(unittest.TestCase):
    """An identified non-consumable item carried unused through UNUSED_DIVE_LIMIT
    whole dives becomes a Home-deposit candidate; using it (its carried count drops)
    resets that, and consumables / devices / survival kit are never idle-stashed."""

    JUNK_TVAL = 2  # empty bottle: aware, non-consumable, non-equipment dead weight

    def _dungeon(self, inv):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=list(inv),
        )

    def _town(self, inv):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inv),
        )

    def _dive(self, pol, start_inv, end_inv=None):
        # town -> dungeon(begin) -> dungeon(step) -> town(end). A lower count in
        # end_inv than start_inv reads as the item being used (consumed) this dive.
        end_inv = start_inv if end_inv is None else end_inv
        pol._track_idle_items(self._dungeon(start_inv), (0, 0, 0))  # dive begins
        pol._track_idle_items(self._dungeon(end_inv), (DUNGEON_YEEK_CAVE, 1, 0))  # step
        pol._track_idle_items(self._town(end_inv), (DUNGEON_YEEK_CAVE, 1, 0))  # dive ends

    def test_unused_item_becomes_a_deposit_candidate_after_the_limit(self):
        pol = HengbotPolicy()
        junk = item("k", self.JUNK_TVAL, 0, name="empty bottle")
        for _ in range(UNUSED_DIVE_LIMIT - 1):
            self._dive(pol, [junk])
        self.assertFalse(pol._home_deposit_candidate(junk))  # not idle long enough yet
        self._dive(pol, [junk])  # reaches UNUSED_DIVE_LIMIT
        self.assertTrue(pol._home_deposit_candidate(junk))

    def test_using_the_item_resets_the_idle_count(self):
        pol = HengbotPolicy()
        junk2 = item("k", self.JUNK_TVAL, 0, count=2, name="empty bottle")
        junk1 = item("k", self.JUNK_TVAL, 0, count=1, name="empty bottle")
        self._dive(pol, [junk2])  # idle 1
        self._dive(pol, [junk2])  # idle 2
        self._dive(pol, [junk2], end_inv=[junk1])  # consumed one -> used -> reset
        self.assertEqual(pol._item_idle_dives.get(("empty bottle", self.JUNK_TVAL, 0)), 0)
        self.assertFalse(pol._home_deposit_candidate(junk2))

    def test_survival_kit_and_charged_devices_stay_but_low_use_is_stashed(self):
        # Narrowed protection: the survival kit and a CHARGED device stay; low-use
        # identified consumables (a resist / cure-light potion, an enchant / light
        # scroll) go once idle — the items the user flagged that were wrongly kept.
        pol = HengbotPolicy()
        protected = [
            item("c", TVAL_STAFF, 5, charges=9, name="Identify"),  # charged device
            item("d", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, name="Recall"),  # survival
        ]
        low_use = [
            item("a", TVAL_POTION, 34, name="Cure Light"),  # non-essential potion
            item("b", TVAL_SCROLL, 24, name="Light"),       # non-essential scroll
        ]
        for _ in range(UNUSED_DIVE_LIMIT + 1):
            self._dive(pol, protected + low_use)
        for it in protected:
            self.assertFalse(pol._home_deposit_candidate(it), it.name)
        for it in low_use:
            self.assertTrue(pol._home_deposit_candidate(it), it.name)

    def test_a_depleted_wand_is_stashed_immediately(self):
        # 0-charge wand = pure junk (no utility, no MANA charge-food) -> deposit at
        # once, without waiting out the idle counter.
        dead_wand = item("k", TVAL_WAND, 0, charges=0, name="Magic Missile (0)")
        self.assertTrue(HengbotPolicy()._home_deposit_candidate(dead_wand))

    def test_surplus_digging_tools_are_stashed_keeping_two(self):
        # Fundraising needs ONE digger; the rest are dead weight (the 5-slot haul the
        # user saw). Keep the best, stash the others.
        pol = HengbotPolicy()
        diggers = [
            item("a", TVAL_DIGGING, 1, name="Shovel"),
            item("b", TVAL_DIGGING, 4, name="Pick"),
            item("c", TVAL_DIGGING, 7, name="Mattock"),  # highest sval -> the keeper
        ]
        snap = self._town(diggers)
        surplus = [it for it in diggers if pol._is_surplus_digging_tool(snap, it)]
        self.assertEqual({it.slot for it in surplus}, {"a"})
        self.assertFalse(pol._is_surplus_digging_tool(snap, diggers[1]))
        self.assertFalse(pol._is_surplus_digging_tool(snap, diggers[2]))

    def test_deposit_sweep_keeps_two_carried_diggers(self):
        diggers = [
            item("a", TVAL_DIGGING, 1, name="Shovel"),
            item("b", TVAL_DIGGING, 4, name="Pick"),
        ]
        snap = self._town(diggers)

        for mode in (None, "dive"):
            pol = HengbotPolicy()
            pol._fundraising_mode = mode
            self.assertEqual(pol._digging_tool_count(snap), 2)
            self.assertIsNone(pol._find_home_deposit(snap))

    def test_surplus_diggers_keep_dwarven_shovel_over_plain_pick(self):
        pol = HengbotPolicy()
        dwarven_shovel = item(
            "a", TVAL_DIGGING, 3, name="Dwarven Shovel", pval=3
        )
        plain_pick = item("b", TVAL_DIGGING, 4, name="Pick", pval=1)
        snap = self._town([dwarven_shovel, plain_pick])

        self.assertFalse(pol._is_surplus_digging_tool(snap, dwarven_shovel))
        self.assertFalse(pol._is_surplus_digging_tool(snap, plain_pick))

    def test_surplus_diggers_prefer_ego_when_digging_power_is_equal(self):
        pol = HengbotPolicy()
        ego_shovel = item(
            "a", TVAL_DIGGING, 1, name="Shovel of Digging", pval=3, is_ego=True
        )
        dwarven_shovel = item(
            "b", TVAL_DIGGING, 3, name="Dwarven Shovel", pval=3
        )
        snap = self._town([ego_shovel, dwarven_shovel])

        self.assertFalse(pol._is_surplus_digging_tool(snap, ego_shovel))
        self.assertFalse(pol._is_surplus_digging_tool(snap, dwarven_shovel))

    def test_gate1_sale_retains_the_standing_two_digger_kit(self):
        pol = HengbotPolicy()
        diggers = [
            item("a", TVAL_DIGGING, 3, name="best shovel", pval=3),
            item("b", TVAL_DIGGING, 1, name="second shovel", pval=1),
        ]
        snap = replace(
            self._town(diggers), store=StoreState(STORE_GENERAL, [])
        )

        self.assertEqual(
            pol._batch_sell_key(snap, [diggers[0]]), LEAVE_STORE_KEY
        )
        self.assertEqual(pol.last_reason, "shop:retain-standing-digging-tool")
        self.assertIsNone(pol._batch_sell_pending)

    def test_gate1_five_diggers_compose_sales_for_only_the_three_worst(self):
        diggers = [
            item(chr(ord("a") + rank), TVAL_DIGGING, rank + 1,
                 name=f"digger-{rank}", pval=rank)
            for rank in range(5)
        ]
        snap = replace(
            self._town(diggers), store=StoreState(STORE_GENERAL, [])
        )
        pol = HengbotPolicy()

        self.assertEqual(
            {candidate.slot for candidate in diggers
             if not pol._sale_retains_digging_tool(snap, candidate)},
            {"a", "b", "c"},
        )
        for index in range(3):
            remaining = [replace(diggers[index], inscription="@0"), *diggers[index + 1:]]
            view = replace(snap, inventory=remaining)
            sale_pol = HengbotPolicy()
            key = sale_pol._batch_sell_key(view, [remaining[0]])
            self.assertIn(SELL_KEY, key)
            self.assertEqual(sale_pol.last_reason, "shop:one-shot-sale-compose")
        self.assertTrue(pol._sale_retains_digging_tool(snap, diggers[3]))
        self.assertTrue(pol._sale_retains_digging_tool(snap, diggers[4]))

    def test_five_equal_diggers_are_surplus_for_deposit_but_retained_from_sale(self):
        diggers = [
            item(chr(ord("a") + index), TVAL_DIGGING, 1,
                 name=f"equal-shovel-{index}", pval=1)
            for index in range(5)
        ]
        snap = self._town(diggers)
        policy = HengbotPolicy()

        self.assertEqual(
            {candidate.slot for candidate in diggers
             if policy._is_surplus_digging_tool(snap, candidate)},
            {"c", "d", "e"},
        )
        self.assertTrue(all(
            policy._sale_retains_digging_tool(snap, candidate)
            for candidate in diggers
        ))

class MiningReachableTreasureClosureTest(unittest.TestCase):
    def _policy(self, target):
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._known_treasure = {target}
        policy._mining_detection_centers = [Position(3, 3)]
        return policy

    def test_digs_through_non_gold_tunnel_to_reach_gold(self):
        target = Position(3, 5)
        grids = {
            Position(y, x): grid(y, x, passable=False)
            for y in range(7)
            for x in range(7)
        }
        grids.update(
            {
                Position(3, 3): grid(3, 3),
                Position(3, 4): grid(
                    3, 4, passable=False, can_dig=False, tunnel=True
                ),
                target: grid(
                    3, 5, passable=False, gold=True, can_dig=False, tunnel=True
                ),
            }
        )
        snap = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=7,
            height=7,
        )
        policy = self._policy(target)

        self.assertEqual(policy._mining_closure_key(snap), TUNNEL_KEY + "6")
        self.assertEqual(policy.last_reason, "fundraise:dig-to-treasure")
        self.assertNotIn(target, policy._mining_dropped_veins)

    def test_live_unmarked_southwest_vein_is_bumped_before_tunnelling(self):
        target = Position(20, 103)
        snap = Snapshot(
            player(19, 104, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(19, 104): grid(19, 104),
                target: grid(
                    20,
                    103,
                    passable=False,
                    gold=True,
                    tunnel=True,
                    permanent=False,
                    terrain_id=56,
                    marked=False,
                ),
            },
            [],
            floor_key=(2, 1, 0),
        )
        policy = self._policy(target)
        policy._mining_detection_centers = [Position(19, 104)]

        self.assertEqual(policy._mining_closure_key(snap), "1")
        self.assertEqual(policy.last_reason, "fundraise:dig-mark-bump")

    def test_marked_southwest_vein_still_uses_tunnel_command(self):
        target = Position(20, 103)
        snap = Snapshot(
            player(19, 104, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(19, 104): grid(19, 104),
                target: grid(
                    20,
                    103,
                    passable=False,
                    gold=True,
                    tunnel=True,
                    permanent=False,
                    terrain_id=56,
                    marked=True,
                ),
            },
            [],
            floor_key=(2, 1, 0),
        )
        policy = self._policy(target)
        policy._mining_detection_centers = [Position(19, 104)]

        self.assertEqual(policy._mining_closure_key(snap), TUNNEL_KEY + "1")
        self.assertEqual(policy.last_reason, "fundraise:dig-to-treasure")

    def test_persistently_unmarked_vein_is_dropped_after_bounded_bumps(self):
        target = Position(20, 103)
        snap = Snapshot(
            player(19, 104, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(19, 104): grid(19, 104),
                target: grid(
                    20,
                    103,
                    passable=False,
                    gold=True,
                    tunnel=True,
                    terrain_id=56,
                    marked=False,
                ),
            },
            [],
            floor_key=(2, 1, 0),
        )
        policy = self._policy(target)
        policy._mining_detection_centers = [Position(19, 104)]
        with patch.object(policy, "_finish_mining_floor", return_value="FINISH"):
            for _ in range(DIGGER_WIELD_LIMIT - 1):
                self.assertEqual(policy._mining_closure_key(snap), "1")
            self.assertEqual(policy._mining_closure_key(snap), "FINISH")

        self.assertIn(target, policy._mining_dropped_veins)

    def test_shared_unmarkable_wall_is_bumped_only_once_across_two_veins(self):
        wall = Position(3, 4)
        targets = {Position(2, 5), Position(4, 5)}
        grids = {
            Position(y, x): grid(y, x, passable=False, permanent=True)
            for y in range(7)
            for x in range(7)
        }
        grids.update(
            {
                Position(3, 3): grid(3, 3),
                wall: grid(
                    3,
                    4,
                    passable=False,
                    tunnel=True,
                    marked=False,
                    terrain_id=56,
                ),
                Position(3, 5): grid(3, 5),
                Position(2, 5): grid(
                    2, 5, passable=False, gold=True, tunnel=True
                ),
                Position(4, 5): grid(
                    4, 5, passable=False, gold=True, tunnel=True
                ),
            }
        )
        snap = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(2, 1, 0),
            width=7,
            height=7,
        )
        policy = self._policy(next(iter(targets)))
        policy._known_treasure = targets
        decisions = []
        with patch.object(policy, "_finish_mining_floor", return_value="FINISH"):
            for _ in range(12):
                key = policy._mining_closure_key(snap)
                decisions.append(key)
                if key == "FINISH":
                    break

        bumps = [key for key in decisions if key == "6"]
        self.assertLessEqual(len(bumps), DIGGER_WIELD_LIMIT)
        self.assertIn(wall, policy._mining_unmarkable_grids)
        self.assertEqual(decisions[-1], "FINISH")
        self.assertLess(len(decisions), 12)

    def test_closure_routes_around_excluded_diggable_wall(self):
        target = Position(1, 1)
        excluded = Position(2, 2)
        snap = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(3, 3): grid(3, 3),
                excluded: grid(2, 2, passable=False, tunnel=True),
                Position(2, 3): grid(2, 3),
                Position(1, 3): grid(1, 3),
                Position(1, 2): grid(1, 2),
                target: grid(
                    1, 1, passable=False, gold=True, tunnel=True
                ),
            },
            [],
            floor_key=(2, 1, 0),
            width=7,
            height=7,
        )
        policy = self._policy(target)
        policy._mining_unmarkable_grids.add(excluded)

        self.assertEqual(policy._mining_closure_key(snap), "8")
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")

    def test_tunnel_refuses_excluded_grid_without_rearming_bumps(self):
        excluded = Position(3, 4)
        snap = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(3, 3): grid(3, 3),
                excluded: grid(
                    3, 4, passable=False, tunnel=True, marked=False
                ),
            },
            [],
            floor_key=(2, 1, 0),
        )
        policy = self._policy(excluded)
        policy._mining_unmarkable_grids.add(excluded)

        self.assertIsNone(policy._mining_tunnel_key(snap, excluded))
        self.assertNotIn(excluded, policy._mining_mark_bumps)

    def test_floor_change_clears_unmarkable_grid_exclusions(self):
        excluded = Position(3, 4)
        first = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            {Position(3, 3): grid(3, 3)},
            [],
            floor_key=(2, 1, 0),
        )
        second = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            {Position(3, 3): grid(3, 3)},
            [],
            floor_key=(2, 2, 0),
        )
        policy = HengbotPolicy()
        policy._observe(first)
        policy._mining_unmarkable_grids.add(excluded)

        policy._observe(second)

        self.assertNotIn(excluded, policy._mining_unmarkable_grids)

    def test_drops_gold_enclosed_by_permanent_rock(self):
        target = Position(3, 3)
        grids = {
            Position(y, x): grid(
                y,
                x,
                passable=(y, x) == (1, 1),
                gold=Position(y, x) == target,
                tunnel=Position(y, x) == target,
                permanent=max(abs(y - 3), abs(x - 3)) == 1,
            )
            for y in range(7)
            for x in range(7)
        }
        snap = Snapshot(
            player(1, 1, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=7,
            height=7,
        )
        policy = self._policy(target)
        with patch.object(policy, "_finish_mining_floor", return_value="FINISH"):
            self.assertEqual(policy._mining_closure_key(snap), "FINISH")

        self.assertIn(target, policy._mining_dropped_veins)
        self.assertEqual(policy._mining_veins_dropped, 1)

    def test_finishes_after_fixed_targets_are_collected_or_dropped(self):
        reachable = Position(2, 3)
        blocked = Position(5, 5)
        grids = {
            Position(y, x): grid(
                y,
                x,
                passable=(y, x) in {(2, 2)},
                gold=Position(y, x) in {reachable, blocked},
                tunnel=Position(y, x) in {reachable, blocked},
                permanent=max(abs(y - 5), abs(x - 5)) == 1,
            )
            for y in range(8)
            for x in range(8)
        }
        first = Snapshot(
            player(2, 2, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=8,
            height=8,
        )
        policy = self._policy(reachable)
        policy._known_treasure.add(blocked)
        key = policy._mining_closure_key(first)
        self.assertEqual(key, TUNNEL_KEY + "6")
        self.assertNotEqual(key, WAIT_KEY)

        policy._known_treasure.discard(reachable)
        cleared = dict(grids)
        cleared[reachable] = grid(2, 3)
        second = Snapshot(
            player(2, 3, class_id=PLAYER_CLASS_WARRIOR),
            cleared,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            width=8,
            height=8,
        )
        with patch.object(policy, "_finish_mining_floor", return_value="FINISH"):
            self.assertEqual(policy._mining_closure_key(second), "FINISH")
        self.assertIn(blocked, policy._mining_dropped_veins)

    def test_actively_digging_target_survives_past_leash(self):
        # A reachable vein reached by tunnelling a hard tile must NOT be dropped
        # at the per-target leash: active digging is forward progress. Only the
        # global MINING_SWEEP_HARD_LIMIT backstop bounds a tile that never breaks
        # through.
        target = Position(3, 4)
        snap = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(3, 3): grid(3, 3),
                target: grid(3, 4, passable=False, gold=True, tunnel=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = self._policy(target)
        with patch.object(policy, "_finish_mining_floor", return_value="FINISH"):
            for _ in range(MINING_STALL_LIMIT + 5):
                result = policy._mining_closure_key(snap)
                self.assertEqual(result, TUNNEL_KEY + "6")
        self.assertNotIn(target, policy._mining_dropped_veins)

    def test_navigation_stall_still_drops_target_at_leash(self):
        # A target the bot can only WALK toward while making no progress (fixed
        # position) still burns the per-target leash and is dropped; the digging
        # exemption must not disable the navigation stall guard.
        target = Position(3, 5)
        snap = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(3, 3): grid(3, 3),
                Position(3, 4): grid(3, 4),
                target: grid(3, 5, passable=False, gold=True, tunnel=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = self._policy(target)
        policy._mining_closure_key(snap)
        self.assertEqual(policy.last_reason, "fundraise:seek-treasure")
        with patch.object(policy, "_finish_mining_floor", return_value="FINISH"):
            for _ in range(MINING_STALL_LIMIT):
                result = policy._mining_closure_key(snap)
                if result == "FINISH":
                    break
        self.assertEqual(result, "FINISH")
        self.assertIn(target, policy._mining_dropped_veins)

    def test_floor_decision_cap_finishes_with_visible_reason(self):
        target = Position(3, 4)
        snap = Snapshot(
            player(3, 3, class_id=PLAYER_CLASS_WARRIOR),
            {
                Position(3, 3): grid(3, 3),
                target: grid(3, 4, passable=False, gold=True, tunnel=True),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
        )
        policy = self._policy(target)
        policy._mining_sweep_steps = MINING_SWEEP_HARD_LIMIT
        with patch.object(policy, "_finish_mining_floor", return_value="FINISH"):
            self.assertEqual(policy._mining_closure_key(snap), "FINISH")
        self.assertEqual(policy.last_reason, "fundraise:mining-hard-limit")

class FundraisingStuckEscapeTest(unittest.TestCase):
    """A mining pocket sealed by walls (no reachable up-stairs, nothing to explore,
    no walkable neighbour) must ESCAPE rather than WAIT forever — the exact hang that
    tripped the loop guard on Yeek Cave L1 and stopped the bot."""

    def _walled_in(self, inventory, *, can_dig=False, upstairs_at=None):
        grids = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                pos = Position(10 + dy, 10 + dx)
                center = dy == 0 and dx == 0
                grids[pos] = grid(
                    10 + dy, 10 + dx, passable=center, can_dig=can_dig and not center
                )
        if upstairs_at is not None:
            grids[upstairs_at] = grid(
                upstairs_at.y, upstairs_at.x, passable=False, upstairs=True, can_dig=True
            )
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=list(inventory),
        )

    def test_digs_out_of_a_sealed_pocket_toward_the_upstairs(self):
        # A mining pocket walled off from the up-stairs: the miner DIGS out toward the
        # known up-stairs rather than spending a scarce Teleport scroll to relocate.
        snap = self._walled_in(
            [item("t", TVAL_SCROLL, 9, count=3)],  # teleport, must stay untouched
            can_dig=True,
            upstairs_at=Position(10, 12),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        self.assertEqual(pol._leave_fundraising_floor(snap), TUNNEL_KEY + "6")  # dig east
        self.assertEqual(pol.last_reason, "fundraise:tunnel-out")

    def test_digs_out_when_sealed_without_spending_recall(self):
        # Same pocket, only a Word of Recall on hand: still dig out — Recall is a
        # survival/return resource, not an unstick tool.
        snap = self._walled_in(
            [item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
            can_dig=True,
            upstairs_at=Position(10, 12),
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        self.assertEqual(pol._leave_fundraising_floor(snap), TUNNEL_KEY + "6")
        self.assertEqual(pol.last_reason, "fundraise:tunnel-out")

    def test_waits_only_when_truly_boxed_in_by_permanent_rock(self):
        # No diggable wall, no reachable stairs, no remembered floor: nothing safe to
        # do but WAIT. Crucially it still does NOT read a Teleport/Recall scroll.
        snap = self._walled_in([item("t", TVAL_SCROLL, 9, count=3)])  # non-diggable walls
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        self.assertEqual(pol._leave_fundraising_floor(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "fundraise:upstairs-not-found")

    def test_oscillating_route_drops_the_vein_without_teleporting(self):
        # Bouncing between two tiles seeking a walled-off vein must neither read
        # a scarce Teleport scroll NOR start digging blank rock at it: the vein
        # is dropped (it is not distance-1) and the run moves on — the coverage
        # design trades the expensive vein for reliably finishing the cheap ones.
        from collections import deque

        grids = {
            Position(12, 126): grid(12, 126),  # player tile (passable)
            Position(13, 126): grid(13, 126),  # oscillation partner
            Position(12, 127): grid(12, 127, passable=False, can_dig=True),  # rock toward vein
            Position(12, 129): grid(12, 129, passable=False, gold=True, can_dig=True),  # vein
        }
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3)],  # teleport, must stay untouched
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),  # a digging tool (TV_DIGGING)
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key  # already detected: skip re-read
        pol._known_treasure = {Position(12, 129)}
        pol._treasure_target = Position(12, 129)
        pol._recent = deque(
            [Position(12, 126), Position(13, 126)] * 5, maxlen=STUCK_WINDOW
        )
        key = pol._fundraising_key(snap, [])
        self.assertNotEqual(key, "rt")  # the teleport scroll stays in the kit
        self.assertNotEqual(pol.last_reason, "fundraise:tunnel-to-treasure")
        self.assertIn(Position(12, 129), pol._mining_dropped_veins)
        self.assertEqual(pol._mining_veins_dropped, 1)

    def test_gives_up_when_oscillating_with_nothing_diggable(self):
        # Oscillating with NO vein tunnellable toward and none reachable on foot: leave
        # (climb out) rather than dig or read a Teleport scroll. It must NOT walk
        # (seek-treasure) while bouncing, nor spend any scroll.
        from collections import deque

        grids = {Position(12, 126): grid(12, 126), Position(13, 126): grid(13, 126)}
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3)],  # teleport, must stay untouched
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._known_treasure = {Position(9, 126)}  # vein exists but no diggable neighbour
        pol._recent = deque(
            [Position(12, 126), Position(13, 126)] * 5, maxlen=STUCK_WINDOW
        )
        key = pol._fundraising_key(snap, [])
        self.assertFalse(key.startswith(READ_KEY))  # no teleport / no scroll
        self.assertNotIn(
            pol.last_reason,
            {
                "fundraise:teleport-unstick",
                "fundraise:tunnel-to-treasure",  # nothing diggable
                "fundraise:seek-treasure",  # must not walk while bouncing
            },
        )

    def test_spent_leash_finishes_the_floor_without_tunneling(self):
        # The safety leash still bounds a degenerate run, and even then the exit
        # never falls back to digging blank rock toward a far vein.
        from collections import deque
        from hengbot.policy import MINING_STALL_LIMIT

        grids = {
            Position(12, 126): grid(12, 126),
            Position(13, 126): grid(13, 126),
            Position(12, 127): grid(12, 127, passable=False, can_dig=True),  # rock toward vein
            Position(12, 129): grid(12, 129, passable=False, gold=True, can_dig=True),  # vein
        }
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3)],
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._known_treasure = {Position(12, 129)}
        pol._recent = deque(
            [Position(12, 126), Position(13, 126)] * 5, maxlen=STUCK_WINDOW
        )
        pol._mining_stall_turns = MINING_STALL_LIMIT
        key = pol._fundraising_key(snap, [])
        self.assertNotEqual(key, TUNNEL_KEY + "6")
        self.assertNotEqual(pol.last_reason, "fundraise:tunnel-to-treasure")
        # And the exit never re-reads a detection scroll either.
        key = pol._fundraising_key(snap, [])
        self.assertFalse(key.startswith(READ_KEY))
        self.assertNotEqual(pol.last_reason, "fundraise:tunnel-to-treasure")

    def obsolete_spent_leash_still_digs_one_adjacent_gold_vein(self):
        from hengbot.policy import MINING_STALL_LIMIT

        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(
                    10, 11, passable=False, gold=True, can_dig=True
                ),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            equipment=[
                item(
                    "g", TVAL_LITE, SV_LITE_LANTERN,
                    fuel=5000, is_equipment=True,
                ),
                item("d", 20, 1, is_equipment=True),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._mining_sweep_done = True
        pol._mining_stall_turns = MINING_STALL_LIMIT

        self.assertEqual(pol._fundraising_key(snap, []), TUNNEL_KEY + "6")
        self.assertEqual(pol.last_reason, "fundraise:mine-treasure")
        self.assertEqual(pol._mining_stall_turns, 0)

    def test_leash_expiry_leaves_toward_upstairs_without_reading_a_scroll(self):
        # With the leash already spent and no gold in reach, the miner heads out (digging
        # toward the up-stairs here) rather than re-reading a detection scroll or teleporting.
        from hengbot.policy import MINING_STALL_LIMIT

        grids = {
            Position(10, 10): grid(10, 10),  # player
            Position(10, 11): grid(10, 11, passable=False, can_dig=True),  # rock toward stairs
            Position(10, 12): grid(10, 12, passable=False, upstairs=True, can_dig=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("t", TVAL_SCROLL, 9, count=3),  # teleport, must stay untouched
                item("s", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=3),  # detection, unused
            ],
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key  # already detected this floor
        pol._mining_stall_turns = MINING_STALL_LIMIT  # leash spent
        key = pol._fundraising_key(snap, [])
        self.assertEqual(key, TUNNEL_KEY + "6")  # digging OUT toward the up-stairs
        self.assertEqual(pol.last_reason, "fundraise:tunnel-out")
        self.assertFalse(key.startswith(READ_KEY))  # neither detect-treasure nor teleport

    def obsolete_walled_vein_is_left_instead_of_tunneled_at(self):
        # Coverage design: a vein with no walkable approach is the EXPENSIVE
        # kind — blank-rock digging burned the leash and stranded the rest of
        # the floor. It is left behind (never tunnelled at, never a reason to
        # read a scroll); the cheap veins elsewhere get the time instead.
        grids = {
            Position(12, 126): grid(12, 126),  # player (its only known tile is walled in)
            Position(12, 127): grid(12, 127, passable=False, can_dig=True),  # rock toward vein
            Position(12, 129): grid(12, 129, passable=False, gold=True, can_dig=True),  # vein
        }
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            grids,
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3)],  # teleport, must stay untouched
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("d", 20, 1, is_equipment=True),  # digger equipped
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._known_treasure = {Position(12, 129)}
        # NOT oscillating (empty history) and no walkable approach to the vein.
        self.assertFalse(pol._is_oscillating())
        key = pol._fundraising_key(snap, [])
        self.assertNotEqual(key, TUNNEL_KEY + "6")
        self.assertNotEqual(pol.last_reason, "fundraise:tunnel-to-treasure")
        self.assertEqual(pol._mining_stall_turns, MINING_STALL_LIMIT)

    def test_mining_removes_both_combat_hands_before_wielding_a_digger(self):
        # do_cmd_wield's both-hands-full branch opens "Equip which hand?"
        # (cmd-equipment.cpp:189-201).  Mining must never answer that selector by
        # replacing just one hand: that creates the forbidden combat+digger mix.
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {Position(12, 126): grid(12, 126), Position(13, 126): grid(13, 126)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3), item("j", 20, 4)],  # teleport + digger
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("main_hand", 23, 1, is_equipment=True, name="Broad Sword"),
                item("sub_hand", 34, 2, is_equipment=True, name="Small metal shield"),  # TV_SHIELD
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
        self.assertEqual(pol._fundraising_key(snap, []), "ta")
        self.assertEqual(pol.last_reason, "fundraise:wield-digging-tool")
        self.assertEqual(pol._normal_weapon_name, "Broad Sword")  # remembered to re-wield

    def test_mining_removes_single_combat_weapon_instead_of_declining_dual_wield(self):
        # Only the main hand occupied: do_cmd_wield asks "Dual wielding? [y/n]"
        # (cmd-equipment.cpp:181-188).  A blind `n` caused the live modal leak;
        # remove the combat weapon first, then wield on the observed empty board.
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {Position(12, 126): grid(12, 126), Position(13, 126): grid(13, 126)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3), item("j", 20, 4)],  # teleport + digger
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("main_hand", 23, 1, is_equipment=True, name="Broad Sword"),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
        self.assertEqual(pol._fundraising_key(snap, []), "ta")
        self.assertEqual(pol.last_reason, "fundraise:wield-digging-tool")

    def test_gives_up_mining_when_the_weapon_will_not_swap_for_the_digger(self):
        # A truly stuck / cursed main weapon that never yields to the digging-tool wield
        # (even after answering the which-hand prompt) must not re-issue "wield" forever
        # (the loop that stopped the bot) — after DIGGER_WIELD_LIMIT attempts, abandon.
        from hengbot.policy import DIGGER_WIELD_LIMIT

        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {Position(12, 126): grid(12, 126), Position(13, 126): grid(13, 126)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("t", TVAL_SCROLL, 9, count=3), item("j", 20, 4)],  # teleport + digger
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item("main_hand", 23, 1, is_equipment=True, name="Cursed Hammer"),
                item("sub_hand", 34, 2, is_equipment=True, name="Small metal shield"),  # TV_SHIELD
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
        posted = pol._fundraising_key(snap, [])
        self.assertEqual(posted, "ta")
        self.assertTrue(pol.confirm_key_posted(posted))
        keys = [
            pol._fundraising_key(snap, [])
            for _ in range(DIGGER_WIELD_LIMIT - 1)
        ]
        self.assertEqual(keys[:-1], [None] * (DIGGER_WIELD_LIMIT - 2))
        self.assertIsNotNone(keys[-1])
        self.assertEqual(pol.last_reason, "fundraise:abandon-unwieldable-digger")
        self.assertIsNone(pol._fundraising_mode)

    def test_lagged_successful_two_digger_assembly_never_hits_unwieldable_exit(self):
        sword = item("main_hand", 23, 1, is_equipment=True, name="Sword")
        shield = item("sub_hand", 34, 2, is_equipment=True, name="Shield")
        shovel = item("j", TVAL_DIGGING, 4, name="Shovel")
        pick = item("k", TVAL_DIGGING, 4, name="Pick")
        base = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000),
            {Position(12, 126): grid(12, 126)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[shovel, pick], equipment=[sword, shield],
        )
        pol = HengbotPolicy()

        stages = (
            (base, "ta"),
            (replace(base, inventory=[replace(sword, slot="a"), shovel, pick],
                     equipment=[shield]), "tb"),
            (replace(base, inventory=[replace(sword, slot="a"),
                                     replace(shield, slot="b"), shovel, pick],
                     equipment=[]), "wj"),
            (replace(base, inventory=[replace(sword, slot="a"),
                                     replace(shield, slot="b"), pick],
                     equipment=[replace(shovel, slot="main_hand")]), "wky"),
        )
        for snapshot, expected in stages:
            key = pol._wield_digging_tool_key(snapshot, "fundraise:wield-digging-tool")
            self.assertEqual(key, expected)
            self.assertTrue(pol.confirm_key_posted(key))
            self.assertIsNone(
                pol._wield_digging_tool_key(
                    snapshot, "fundraise:wield-digging-tool"
                )
            )
            self.assertLess(pol._digger_wield_attempts, DIGGER_WIELD_LIMIT)

        completed = replace(
            base, inventory=[replace(sword, slot="a"), replace(shield, slot="b")],
            equipment=[replace(shovel, slot="main_hand"),
                       replace(pick, slot="sub_hand")],
        )
        self.assertIsNone(
            pol._wield_digging_tool_key(completed, "fundraise:wield-digging-tool")
        )
        self.assertLess(pol._digger_wield_attempts, DIGGER_WIELD_LIMIT)

    def test_refused_flip_continues_mining_with_current_loadout(self):
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {
                Position(12, 126): grid(12, 126),
                Position(13, 126): grid(13, 126),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item("t", TVAL_SCROLL, 9, count=3),
                item("j", TVAL_DIGGING, 4, name="Shovel"),
            ],
            equipment=[
                item(
                    "g", TVAL_LITE, SV_LITE_LANTERN,
                    fuel=5000, is_equipment=True,
                ),
                item(
                    "main_hand", TVAL_SWORD, 1,
                    name="Sword", is_equipment=True,
                ),
                item(
                    "sub_hand", 34, 2,
                    name="Shield", is_equipment=True,
                ),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
        pol._equipment_mutation.last_posted_goal = "combat-loadout"
        pol._equipment_mutation.last_posted_core = progress_core(snap)

        key = pol._fundraising_key(snap, [])
        self.assertIsNone(key, (key, pol.last_reason))
        self.assertEqual(pol.last_reason, "goal-already-superseded")
        self.assertEqual(pol._fundraising_mode, "mine")

    def test_mining_wields_two_carried_diggers_in_both_hands(self):
        pol = HengbotPolicy()
        first = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000),
            {Position(12, 126): grid(12, 126)},
            [],
            inventory=[
                item("j", TVAL_DIGGING, 1, name="Shovel"),
                item("k", TVAL_DIGGING, 4, name="Pick"),
            ],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True, name="Sword"),
                item("sub_hand", 34, 2, is_equipment=True, name="Shield"),
            ],
        )
        self.assertEqual(pol._wield_digging_tool_key(first, "mine:wield"), "ta")
        second = Snapshot(
            first.player,
            first.grids,
            [],
            inventory=list(first.inventory),
            equipment=[item("sub_hand", 34, 2, is_equipment=True, name="Shield")],
        )
        self.assertEqual(pol._wield_digging_tool_key(second, "mine:wield"), "tb")
        empty = replace(second, equipment=[])
        self.assertEqual(pol._wield_digging_tool_key(empty, "mine:wield"), "wj")
        one_digger = replace(
            empty,
            inventory=[item("k", TVAL_DIGGING, 4, name="Pick")],
            equipment=[
                item("main_hand", TVAL_DIGGING, 1, is_equipment=True, name="Shovel")
            ],
        )
        self.assertEqual(pol._wield_digging_tool_key(one_digger, "mine:wield"), "wky")
        self.assertEqual(pol._normal_sub_hand_name, "Shield")

    def test_dual_diggers_stay_wielded_and_the_next_detection_read_lands(self):
        scroll = item("s", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=2)
        shovel = item(
            "main_hand", TVAL_DIGGING, 1, is_equipment=True, name="Shovel"
        )
        pick = item(
            "sub_hand", TVAL_DIGGING, 4, is_equipment=True, name="Pick"
        )
        snap = Snapshot(
            player(
                12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100
            ),
            {Position(12, 126): grid(12, 126)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[scroll, item("f", TVAL_FOOD, 35, count=2)],
            equipment=[
                shovel,
                pick,
                item(
                    "light",
                    TVAL_LITE,
                    SV_LITE_LANTERN,
                    fuel=5000,
                    is_equipment=True,
                ),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT

        self.assertEqual(pol._fundraising_key(snap, []), "rs", pol.last_reason)
        self.assertEqual(pol.last_reason, "fundraise:detect-treasure")

        detected = replace(
            snap,
            inventory=[replace(scroll, count=1), item("f", TVAL_FOOD, 35, count=2)],
            grids={
                Position(12, 126): grid(12, 126),
                Position(12, 127): grid(
                    12, 127, passable=False, gold=True, can_dig=True
                ),
            },
        )
        pol._known_treasure = {Position(12, 127)}
        keys = [pol._fundraising_key(detected, []) for _ in range(2)]
        self.assertEqual(keys, [TUNNEL_KEY + "6", TUNNEL_KEY + "6"])
        self.assertTrue(
            all(
                sum(item.is_digging_tool for item in board.equipment) == 2
                and not any(
                    item.is_melee_weapon and not item.is_digging_tool
                    for item in board.equipment
                )
                for board in (snap, detected)
            )
        )

    def test_one_digger_is_ready_and_only_targets_main_hand(self):
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000),
            {Position(12, 126): grid(12, 126)},
            [],
            inventory=[item("j", TVAL_DIGGING, 1, name="Shovel")],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True, name="Sword"),
                item("sub_hand", 34, 2, is_equipment=True, name="Shield"),
            ],
        )
        pol = HengbotPolicy()
        with patch.object(pol, "_fundraising_food_ready", return_value=True), \
             patch.object(pol, "_mining_detection_scroll_target", return_value=0):
            self.assertTrue(pol._fundraising_supplies_ready(snap))
        self.assertEqual(pol._wield_digging_tool_key(snap, "mine:wield"), "ta")

    def test_mining_end_restores_both_combat_hands(self):
        pol = HengbotPolicy()
        pol._normal_weapon_name = "Sword"
        pol._normal_sub_hand_name = "Shield"
        first = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("w", 23, 1, is_equipment=True, name="Sword"),
                item("s", 34, 2, is_equipment=True, name="Shield"),
            ],
            equipment=[
                item("main_hand", TVAL_DIGGING, 1, is_equipment=True),
                item("sub_hand", TVAL_DIGGING, 4, is_equipment=True),
            ],
        )
        self.assertEqual(
            pol._restore_mining_combat_hand_key(first, "restore"), "wwa"
        )
        second = Snapshot(
            first.player,
            first.grids,
            [],
            inventory=[item("s", 34, 2, is_equipment=True, name="Shield")],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True, name="Sword"),
                item("sub_hand", TVAL_DIGGING, 4, is_equipment=True),
            ],
        )
        self.assertEqual(
            pol._restore_mining_combat_hand_key(second, "restore"), "wsb"
        )

    def test_mining_restores_optimizer_single_hand_not_displaced_dual_wield(self):
        pol = HengbotPolicy()
        sword = item("s", TVAL_SWORD, 1, name="Long Sword", is_equipment=True)
        optimal = Loadout(
            (("main_hand", OwnedEquipment("optimal-sword", sword, "pack")),),
            "one_handed",
        )
        pol._equipment_optimization_preparation = SimpleNamespace(
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=optimal))
        )
        observed = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[sword, item("j", TVAL_DIGGING, 1, name="Shovel")],
            equipment=[
                item("main_hand", 21, 1, is_equipment=True, name="Flail"),
                item("sub_hand", 22, 1, is_equipment=True, name="Naginata"),
            ],
        )
        self.assertEqual(pol._wield_digging_tool_key(observed, "mine:wield"), "ta")

        both_diggers = replace(
            observed,
            inventory=[
                sword,
                item("f", 21, 1, name="Flail", is_equipment=True),
                item("n", 22, 1, name="Naginata", is_equipment=True),
            ],
            equipment=[
                item("main_hand", TVAL_DIGGING, 1, is_equipment=True, name="Shovel"),
                item("sub_hand", TVAL_DIGGING, 4, is_equipment=True, name="Pick"),
            ],
        )
        self.assertEqual(
            pol._restore_mining_combat_hand_key(both_diggers, "restore"), "wsa"
        )
        main_restored = replace(
            both_diggers,
            inventory=[item("n", 22, 1, name="Naginata", is_equipment=True)],
            equipment=[
                replace(sword, slot="main_hand", is_equipment=True),
                item("sub_hand", TVAL_DIGGING, 4, is_equipment=True, name="Pick"),
            ],
        )
        self.assertEqual(
            pol._restore_mining_combat_hand_key(main_restored, "restore"), "tb"
        )

    def test_mining_restores_optimizer_dual_wield(self):
        pol = HengbotPolicy()
        sword = item("s", TVAL_SWORD, 1, name="Sword", is_equipment=True)
        dagger = item("d", TVAL_SWORD, 2, name="Dagger", is_equipment=True)
        optimal = Loadout(
            (
                ("main_hand", OwnedEquipment("sword", sword, "pack")),
                ("sub_hand", OwnedEquipment("dagger", dagger, "pack")),
            ),
            "dual_wield",
        )
        pol._equipment_optimization_preparation = SimpleNamespace(
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: focused optimizer unit supplies a collaborator result whose downstream handling is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=optimal))
        )
        observed = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[item("j", TVAL_DIGGING, 1, name="Shovel")],
            equipment=[
                replace(sword, slot="main_hand", is_equipment=True),
                replace(dagger, slot="sub_hand", is_equipment=True),
            ],
        )
        pol._wield_digging_tool_key(observed, "mine:wield")
        digging = replace(
            observed,
            inventory=[sword, dagger],
            equipment=[
                item("main_hand", TVAL_DIGGING, 1, is_equipment=True),
                item("sub_hand", TVAL_DIGGING, 4, is_equipment=True),
            ],
        )
        self.assertEqual(pol._restore_mining_combat_hand_key(digging, "restore"), "wsa")
        self.assertEqual(
            pol._restore_mining_combat_hand_key(
                replace(
                    digging,
                    inventory=[dagger],
                    equipment=[
                        replace(sword, slot="main_hand", is_equipment=True),
                        item("sub_hand", TVAL_DIGGING, 4, is_equipment=True),
                    ],
                ),
                "restore",
            ),
            "wdb",
        )

    def test_second_opposite_town_loadout_swap_needs_non_equipment_progress(self):
        pol = HengbotPolicy()
        yeek = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[item("j", TVAL_DIGGING, 1, name="Shovel")],
            equipment=[item(
                "main_hand", TVAL_SWORD, 1, name="Sword", is_equipment=True
            )],
        )
        posted = pol._wield_digging_tool_key(
                yeek, "fundraise:wield-digging-tool"
            )
        self.assertEqual(posted, "ta")
        self.assertTrue(pol.confirm_key_posted(posted))
        town_digging = replace(
            yeek,
            floor_key=(0, 0, 0),
            inventory=[item("s", TVAL_SWORD, 1, name="Sword", is_equipment=True)],
            equipment=[item(
                "main_hand", TVAL_DIGGING, 1, name="Shovel", is_equipment=True
            )],
        )
        self.assertIsNone(pol._restore_mining_combat_hand_key(
            town_digging, "town:restore-combat-weapon"
        ))
        self.assertEqual(pol.last_reason, "goal-already-superseded")
        progressed = replace(town_digging, player=replace(
            town_digging.player, gold=town_digging.player.gold + 1
        ))
        self.assertEqual(pol._restore_mining_combat_hand_key(
            progressed, "town:restore-combat-weapon"
        ), "wsn")

    def test_loadout_swap_is_not_recorded_when_restore_posts_nothing(self):
        pol = HengbotPolicy()
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            equipment=[item(
                "main_hand", TVAL_SWORD, 1, name="Sword", is_equipment=True
            )],
        )
        self.assertIsNone(pol._restore_mining_combat_hand_key(
            town, "town:restore-combat-weapon"
        ))
        self.assertIsNone(pol._equipment_mutation.last_posted_goal)

    def test_mining_restore_without_optimizer_falls_back_to_observed_weapon(self):
        pol = HengbotPolicy()
        observed = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[item("j", TVAL_DIGGING, 1, name="Shovel")],
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True, name="Sword")],
        )
        pol._wield_digging_tool_key(observed, "mine:wield")
        digging = replace(
            observed,
            inventory=[item("s", TVAL_SWORD, 1, name="Sword", is_equipment=True)],
            equipment=[item("main_hand", TVAL_DIGGING, 1, is_equipment=True)],
        )
        self.assertEqual(pol._restore_mining_combat_hand_key(digging, "restore"), "wsn")

    def test_combat_restore_abandons_when_target_identity_never_appears(self):
        from hengbot.policy import DIGGER_WIELD_LIMIT

        pol = HengbotPolicy()
        pol._normal_sub_hand_name = "Shield"
        stuck = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[
                item("s", 34, 2, is_equipment=True, name="Shield"),
            ],
            equipment=[
                item("main_hand", 23, 1, is_equipment=True, name="Sword"),
                item(
                    "sub_hand",
                    TVAL_DIGGING,
                    4,
                    is_equipment=True,
                    name="Pick",
                ),
            ],
        )
        keys = [
            pol._restore_mining_combat_hand_key(stuck, "restore")
            for _ in range(DIGGER_WIELD_LIMIT)
        ]
        self.assertEqual(keys[:-1], ["wsb"] * (DIGGER_WIELD_LIMIT - 1))
        self.assertIsNone(keys[-1])
        self.assertEqual(
            pol.last_reason, "restore:abandon-unconfirmed-equip"
        )

    def test_cursed_locked_combat_weapon_abandons_instead_of_mixed_loadout(self):
        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000, gold=100),
            {
                Position(12, 126): grid(12, 126),
                Position(12, 127): grid(
                    12, 127, passable=False, gold=True, can_dig=True
                ),
            },
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=[
                item(
                    "s",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=3,
                ),
                item("j", TVAL_DIGGING, SV_DIGGING_SHOVEL),
            ],
            equipment=[
                item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True),
                item(
                    "main_hand",
                    21,
                    5,
                    is_equipment=True,
                    is_cursed=True,
                    inscription="HEAVY_CURSE",
                    name="Cursed Mace",
                ),
            ],
        )
        pol = HengbotPolicy()
        pol._fundraising_mode = "mine"
        pol._mining_scroll_used_floor = snap.floor_key
        pol._known_treasure = {Position(12, 127)}

        self.assertIsNone(
            pol._wield_digging_tool_key(snap, "fundraise:wield-digging-tool")
        )
        self.assertEqual(pol._normal_weapon_name, "Cursed Mace")

    def test_heavy_cursed_main_offhand_digger_wield_is_bounded(self):
        from hengbot.policy import DIGGER_WIELD_LIMIT

        snap = Snapshot(
            player(12, 126, class_id=PLAYER_CLASS_WARRIOR, food=12000),
            {Position(12, 126): grid(12, 126)},
            [],
            inventory=[item("j", TVAL_DIGGING, SV_DIGGING_SHOVEL)],
            equipment=[
                item(
                    "main_hand",
                    21,
                    5,
                    is_equipment=True,
                    is_cursed=True,
                    inscription="HEAVY_CURSE",
                    name="Cursed Mace",
                ),
            ],
        )
        pol = HengbotPolicy()

        keys = [
            pol._wield_digging_tool_key(snap, "mine:wield")
            for _ in range(DIGGER_WIELD_LIMIT)
        ]
        self.assertEqual(keys, [None] * DIGGER_WIELD_LIMIT)
        self.assertEqual(pol._digger_wield_attempts, 0)
