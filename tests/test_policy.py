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


class HistoryIsolationProbeTest(unittest.TestCase):
    def test_policy_history_writer_uses_fixture_default(self):
        HengbotPolicy()._home_disposal.note_dungeon_recall()


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


class ReadLetterBindingTest(unittest.TestCase):
    def snapshot(self, inventory):
        return Snapshot(
            player=player(5, 5), grids={}, visible_monsters=[], inventory=inventory
        )

    def test_detection_scroll_stale_letter_never_reads_monster_confusion(self):
        policy = HengbotPolicy()
        detection = item(
            "h", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
            name="Scroll of Detect Treasure",
        )
        composed = policy._read_key(self.snapshot([detection]), detection)
        panic = item("h", TVAL_SCROLL, 36, name="Scroll of Monster Confusion")
        moved_detection = replace(detection, slot="i")

        posted = policy.validate_read_key(
            self.snapshot([panic, moved_detection]), composed
        )

        self.assertEqual(posted, READ_KEY + "i")
        self.assertNotEqual(posted, READ_KEY + "h")
        self.assertEqual(policy.read_telemetry["resolved"]["sval"], SV_SCROLL_DETECT_TREASURE)
        self.assertEqual(policy.read_telemetry["composed"]["letter"], "h")

    def test_each_read_family_uses_identity_binding_and_preserves_suffix(self):
        families = (
            ("escape", SV_SCROLL_TELEPORT, ""),
            ("recall", SV_SCROLL_WORD_OF_RECALL, "a"),
            ("identify", SV_SCROLL_IDENTIFY, "b"),
            ("detect-treasure", SV_SCROLL_DETECT_TREASURE, ""),
            ("light", SV_SCROLL_LIGHT, ""),
            ("remove-curse", SV_SCROLL_REMOVE_CURSE, ""),
            ("enchant", SV_SCROLL_ENCHANT_WEAPON_TO_HIT, "/a"),
        )
        for family, sval, suffix in families:
            with self.subTest(family=family):
                policy = HengbotPolicy()
                intended = item("h", TVAL_SCROLL, sval, name=family)
                composed = policy._read_key(
                    self.snapshot([intended]), intended, suffix
                )
                panic = item("h", TVAL_SCROLL, 36, name="panic")
                moved = replace(intended, slot="j")
                self.assertEqual(
                    policy.validate_read_key(self.snapshot([panic, moved]), composed),
                    READ_KEY + "j" + suffix,
                )

    def test_matching_letter_posts_unchanged_and_records_identity(self):
        policy = HengbotPolicy()
        scroll = item("h", TVAL_SCROLL, SV_SCROLL_LIGHT, name="Light")
        snapshot = self.snapshot([scroll])

        key = policy._read_key(snapshot, scroll, "\x1b")

        self.assertEqual(key, READ_KEY + "h\x1b")
        self.assertEqual(
            policy.read_telemetry,
            {
                "key": key,
                "letter": "h",
                "resolved": {"tval": TVAL_SCROLL, "sval": SV_SCROLL_LIGHT, "name": "Light"},
                "intended": {"tval": TVAL_SCROLL, "sval": SV_SCROLL_LIGHT, "name": "Light"},
                "composed": {
                    "letter": "h",
                    "resolved": {"tval": TVAL_SCROLL, "sval": SV_SCROLL_LIGHT, "name": "Light"},
                },
            },
        )

    def test_no_composer_uppercases_a_pack_label_selector(self):
        root = Path(__file__).parents[1] / "src" / "hengbot"
        uppercase_calls = [
            (path.name, node.lineno)
            for path in sorted(root.glob("*.py"))
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if _is_forbidden_uppercase_call(path, node)
        ]

        self.assertEqual(uppercase_calls, [])

    def test_uppercase_selector_guard_detects_letter_and_composed_pack_label(self):
        def uppercase_calls(source):
            return [
                node.lineno
                for node in ast.walk(ast.parse(source))
                if _is_forbidden_uppercase_call(Path("planted_policy.py"), node)
            ]

        for expression in ("letter.upper()", "pack_label.upper() + suffix"):
            with self.subTest(expression=expression):
                planted = f"def planted(letter, pack_label, suffix):\n    return {expression}\n"
                self.assertEqual(uppercase_calls(planted), [2])

    def test_recall_destination_answer_comes_from_this_characters_entered_order(self):
        policy = HengbotPolicy()
        recall = item("d", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, name="Recall")
        snapshot = replace(
            self.snapshot([recall]),
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE, DUNGEON_ANGBAND),
        )

        destination = policy._recall_selection_key(snapshot, DUNGEON_ANGBAND)

        self.assertEqual(destination, "b")
        self.assertEqual(policy._read_key(snapshot, recall, destination), "rdb")






















# Item tvals used by the tests (see model.TVAL_*).
STAFF = 55
WAND = 65
POTION = 75
SCROLL = 70
FOOD = 80
FOOD_TYPE_MANA = 4










class RestTest(unittest.TestCase):
    def _open_room(self):
        return {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }

    def test_rests_to_recover_when_hurt_and_safe(self):
        snap = Snapshot(player(10, 10, hp=40, max_hp=100), self._open_room(), [])
        self.assertEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

    def test_stationary_rest_repeats_without_owner_expectation_exemption(self):
        snap = Snapshot(player(10, 10, hp=40, max_hp=100), self._open_room(), [])
        policy = HengbotPolicy()

        self.assertEqual(
            [policy.choose_key(snap), policy.choose_key(snap)],
            [REST_MACRO, REST_MACRO],
        )
        self.assertEqual(policy._owner_expectations._pending, {})

    def test_does_not_rest_while_bleeding(self):
        # A dungeon floor: these exercise the DUNGEON rest rules, not the town
        # recover-at-the-store behaviour (in_town is a distinct code path).
        snap = Snapshot(
            player(10, 10, hp=40, max_hp=100, poisoned=True),
            self._open_room(),
            [],
            floor_key=(1, 5, 0),
        )
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)

    def test_does_not_rest_when_healthy(self):
        snap = Snapshot(
            player(10, 10, hp=95, max_hp=100),
            self._open_room(),
            [],
            floor_key=(1, 5, 0),
        )
        self.assertNotEqual(HengbotPolicy().choose_key(snap), REST_MACRO)



class BountyCashoutTest(unittest.TestCase):
    def test_enters_hunter_office_and_redeems_bounty(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=13),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("a", 10, 1, name="wanted corpse", is_bounty=True)],
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "6cy\x1b")
        self.assertEqual(policy.last_reason, "bounty:cashout")

    def test_confirms_each_bounty_stack_in_one_office_visit(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, building_type=13),
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[
                item("a", 10, 0, name="wanted skeleton", is_bounty=True),
                item("b", 10, 1, name="wanted corpse", is_bounty=True),
            ],
        )

        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "6cyy\x1b")
        self.assertEqual(policy.last_reason, "bounty:cashout")

    def test_standing_on_office_hops_off_to_reenter(self):
        # After a cash-out the bot is left standing ON the office tile. A path to
        # its own tile is empty, so the office used to read as "not found" and a
        # sticky town block stranded it forever. It must instead hop to a
        # neighbour so the next approach can walk back on and redeem the rest.
        grids = {
            Position(10, 10): grid(10, 10, building_type=13),  # bot is on the office
            Position(10, 11): grid(10, 11),  # a walkable tile to step off onto
        }
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            inventory=[item("a", 10, 1, name="wanted", is_bounty=True)],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "bounty:step-off")
        self.assertIsNone(policy._town_blocked_reason)

    def test_unreachable_office_never_latches_a_town_block(self):
        # No office in view and no static map: cashing out is simply skipped this
        # turn (return None), never a sticky block that would outlive the bounty.
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[item("a", 10, 1, name="wanted", is_bounty=True)],
        )
        policy = HengbotPolicy()
        policy._observe(snap)
        self.assertIsNone(policy._bounty_cashout_key(snap))
        self.assertIsNone(policy._town_blocked_reason)

    def test_seeks_visible_loot_before_walking_to_a_store(self):
        grids = {
            Position(9, 10): grid(9, 10, objects=1),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): GridState(
                position=Position(10, 12), known=True, passable=True, wall=False,
                has_monster=False, has_down_stairs=False, has_up_stairs=False,
                unsafe=False, store_number=STORE_GENERAL,
            ),
        }
        snap = Snapshot(
            player(10, 10, gold=1000), grids, [], floor_key=(0, 0, 0)
        )
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "8")
        self.assertEqual(policy.last_reason, "seek-loot")

    def test_seeks_loot_on_trap_undetected_grid(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11, objects=1, unsafe=True),
        }
        snap = Snapshot(player(10, 10), grids, [])
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snap), "6")
        self.assertEqual(policy.last_reason, "seek-loot")

    def test_commits_to_loot_when_a_nearer_item_flickers_into_view(self):
        floor_key = (1, 3, 0)
        policy = HengbotPolicy()
        first = Snapshot(
            player(10, 10),
            {
                Position(10, x): grid(10, x, objects=1 if x == 15 else 0)
                for x in range(9, 16)
            },
            [],
            floor_key=floor_key,
        )
        self.assertEqual(policy.choose_key(first), "6")
        self.assertEqual(policy._loot_target, Position(10, 15))

        second = Snapshot(
            player(10, 11),
            {
                Position(10, 9): grid(10, 9, objects=1),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=floor_key,
        )

        self.assertEqual(policy.choose_key(second), "6")
        self.assertEqual(policy._loot_target, Position(10, 15))
        self.assertEqual(policy.last_reason, "seek-loot")

    def test_forgets_loot_after_autodestroy_removes_it(self):
        floor_key = (1, 3, 0)
        policy = HengbotPolicy()
        first = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, objects=1),
            },
            [],
            floor_key=floor_key,
        )
        self.assertEqual(policy.choose_key(first), "6")

        second = Snapshot(
            player(10, 11),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
            },
            [],
            floor_key=floor_key,
        )
        policy.choose_key(second)

        self.assertNotIn(Position(10, 11), policy._known_loot)
        self.assertIsNone(policy._loot_target)
        self.assertNotEqual(policy.last_reason, "seek-loot")












class DiggingToolRecognitionTest(unittest.TestCase):
    def test_recognizes_every_digging_sval_not_just_shovel_and_pick(self):
        # tval TV_DIGGING covers SV_SHOVEL..SV_MATTOCK (1..7); all dig, the sval
        # only sets power. Upgraded diggers must not read as "no digger".
        for sval in range(1, 8):  # shovel, gnomish/dwarven shovel, pick, ..., mattock
            self.assertTrue(
                item("a", TVAL_DIGGING, sval).is_digging_tool,
                f"digging sval {sval} not recognized",
            )
            self.assertTrue(
                store_item("a", TVAL_DIGGING, sval).is_digging_tool,
                f"store digging sval {sval} not recognized",
            )
        # A non-digging item is still rejected.
        self.assertFalse(item("a", TVAL_FOOD, 35).is_digging_tool)




























































class StuckEscapeTest(unittest.TestCase):
    """A dungeon floor whose stairs are walled off must not trap the bot: after
    enough consecutive last-resort wanders it Word-of-Recalls out. The streak is
    counted in _observe and reset by any other action or by reaching town."""

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

    def test_streak_counts_the_whole_stuck_family(self):
        # Not just stuck:wander — searching for secret ways and breaking out of a
        # visited pocket count too, so a floor that mixes them still escapes.
        pol = HengbotPolicy()
        d = self._dungeon()
        for reason in ("stuck:wander", "search", "seek-secret-wall", "breakout:least-visited"):
            pol.last_reason = reason
            pol._observe(d)
        self.assertEqual(pol._stuck_escape_streak, 4)

    def test_streak_held_through_upkeep_between_searches(self):
        # Relighting / resting between searches must not reset the streak, or a
        # walled-off floor never accumulates enough to escape.
        pol = HengbotPolicy()
        d = self._dungeon()
        pol.last_reason = "search"; pol._observe(d)
        pol.last_reason = "refill-light"; pol._observe(d)
        pol.last_reason = "search"; pol._observe(d)
        self.assertEqual(pol._stuck_escape_streak, 2)

    def test_streak_resets_on_a_productive_action(self):
        pol = HengbotPolicy()
        pol._stuck_escape_streak = 7
        pol.last_reason = "explore"
        pol._observe(self._dungeon())
        self.assertEqual(pol._stuck_escape_streak, 0)

    def test_streak_resets_in_town(self):
        pol = HengbotPolicy()
        pol._stuck_escape_streak = 7
        pol.last_reason = "stuck:wander"
        pol._observe(self._town())
        self.assertEqual(pol._stuck_escape_streak, 0)

    def test_fundraise_digs_toward_upstairs_instead_of_teleporting(self):
        # Bouncing toward walled-off up-stairs while leaving a fundraising floor no
        # longer burns a Teleport scroll — the miner digs toward the stairs instead.
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=5)
        grids = {
            Position(10, 10): grid(10, 10),  # player
            Position(10, 11): grid(10, 11, passable=False, can_dig=True),  # rock toward stairs
            Position(10, 12): grid(10, 12, passable=False, upstairs=True, can_dig=True),
        }
        snap = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            [],
            inventory=[teleport],
            floor_key=(2, 1, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        self.assertEqual(pol._leave_fundraising_floor(snap), TUNNEL_KEY + "6")
        self.assertEqual(pol.last_reason, "fundraise:tunnel-out")

    def test_stuck_digs_through_known_vein_to_downstairs_before_recall(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        digger = item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)
        sword = item("main_hand", 23, 1, name="Broad Sword", is_equipment=True)
        snap = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, passable=False, can_dig=True),
                Position(10, 12): grid(10, 12, downstairs=True),
            },
            [],
            inventory=[recall, digger],
            equipment=[sword],
            equipment_observed=True,
            floor_key=(2, 8, 0),
        )
        snap = replace(
            snap,
            grids={position: replace(cell, lit=False) for position, cell in snap.grids.items()},
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        self.assertEqual(pol.choose_key(snap), "ta")
        self.assertEqual(pol.last_reason, "breakout:wield-digging-tool")

        unarmed = replace(
            snap,
            inventory=[recall, digger, replace(sword, slot="a")],
            equipment=[],
        )
        self.assertEqual(pol.choose_key(unarmed), "wd")
        self.assertEqual(pol.last_reason, "breakout:wield-digging-tool")

        digging = replace(
            unarmed,
            inventory=[recall, replace(sword, slot="a")],
            equipment=[replace(digger, slot="main_hand")],
        )
        self.assertEqual(pol.choose_key(digging), TUNNEL_KEY + "6")
        self.assertEqual(pol.last_reason, "breakout:dig-to-stairs")

        opened = replace(
            digging,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, downstairs=True),
            },
        )
        self.assertEqual(pol.choose_key(opened), "wan")
        self.assertEqual(pol.last_reason, "breakout:restore-combat-weapon")

    def test_breakout_restore_pending_survives_refused_wield(self):
        sword = item("s", 23, 1, name="Broad Sword", is_equipment=True)
        digger = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            inventory=[sword], equipment=[digger], floor_key=(2, 8, 0),
        )
        pol = HengbotPolicy()
        pol._breakout_dig_floor = snap.floor_key
        with patch.object(pol, "_wield_weapon_key", return_value=None):
            self.assertIsNone(pol._breakout_restore_weapon_key(snap))
        self.assertEqual(pol._breakout_dig_floor, snap.floor_key)

        generated = pol._breakout_restore_weapon_key(snap)
        self.assertIsNotNone(generated)
        pol.refuse_key_posting("breakout:restore-combat-weapon", generated)
        self.assertEqual(pol._breakout_dig_floor, snap.floor_key)
        retry = pol._breakout_restore_weapon_key(snap)
        self.assertEqual(retry, generated)
        self.assertTrue(pol.confirm_key_posted(retry))
        self.assertIsNone(pol._breakout_dig_floor)

    def test_breakout_wield_reports_survive_real_choose_key_fallthrough(self):
        sword = item("s", 23, 1, name="Broad Sword", is_equipment=True)
        digger = item(
            "main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True
        )
        snap = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            inventory=[sword], equipment=[digger], floor_key=(2, 8, 0),
        )
        pol = HengbotPolicy()
        pol._breakout_dig_floor = snap.floor_key
        first = pol.choose_key(snap)
        self.assertTrue(first.startswith("w"))
        self.assertTrue(pol.confirm_key_posted(first))
        # A lagged breakout board still carries the observed digger. Recreate
        # the restore obligation so choose_key drives the wield-side executor
        # report through its ordinary exploration fall-through.
        pol._breakout_dig_floor = snap.floor_key

        reports = []
        for _ in range(30):
            key = pol.choose_key(snap)
            report = pol.consume_pending_mutation_report()
            if report is not None:
                reports.append(report)
            if key.startswith("w"):
                self.assertTrue(pol.confirm_key_posted(key))
                pol._breakout_dig_floor = snap.floor_key
        self.assertGreaterEqual(
            reports.count("posting-contract:equipment-mutation-released"), 3
        )

    def test_stuck_recall_escape_without_digging_tool(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, passable=False, can_dig=True),
                Position(10, 12): grid(10, 12, downstairs=True),
            },
            [],
            inventory=[recall],
            floor_key=(2, 8, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        self.assertEqual(pol.choose_key(snap), READ_KEY + "r")
        self.assertEqual(pol.last_reason, "stuck:recall-escape")

    def test_stuck_teleport_escape_without_recall_or_known_downstairs(self):
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[teleport],
            floor_key=(2, 3, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        self.assertEqual(pol.choose_key(snap), READ_KEY + "t")
        self.assertEqual(pol.last_reason, "stuck:teleport-escape")

    def test_stuck_recall_escape_is_preferred_over_teleport(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[teleport, recall],
            floor_key=(2, 3, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        self.assertEqual(pol.choose_key(snap), READ_KEY + "r")
        self.assertEqual(pol.last_reason, "stuck:recall-escape")

    def test_stuck_escape_does_not_burn_phase_door(self):
        phase = item("p", TVAL_SCROLL, SV_SCROLL_PHASE_DOOR)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[phase],
            floor_key=(2, 3, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        key = pol.choose_key(snap)

        self.assertNotEqual(key, READ_KEY + "p")
        self.assertNotEqual(pol.last_reason, "stuck:teleport-escape")

    def test_stuck_teleport_escape_is_locked_on_quest_floor(self):
        teleport = item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT)
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=[teleport],
            floor_key=(2, 3, 40),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        key = pol.choose_key(snap)

        self.assertNotEqual(key, READ_KEY + "t")
        self.assertNotEqual(pol.last_reason, "stuck:teleport-escape")

    def test_stuck_uses_walkable_downstairs_route_without_tunnelling(self):
        digger = item("d", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)
        snap = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, downstairs=True),
            },
            [],
            inventory=[digger],
            floor_key=(2, 8, 0),
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        self.assertEqual(pol.choose_key(snap), "6")
        self.assertIn(pol.last_reason, {"seek-downstairs", "approach-descent"})
        self.assertFalse(pol.last_reason.startswith("breakout:dig"))

    def test_forgetting_maze_does_not_recall_on_stuck_streak(self):
        maze = DungeonInfo(
            4, "Labyrinth", 10, 18, 1,
            flags=frozenset({"MAZE", "FORGET"}),
            guardian_id=1034,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(4, 10, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        pol = HengbotPolicy(dungeon_knowledge={4: maze})
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        key = pol.choose_key(snap)

        self.assertNotEqual(key, "rr")
        self.assertNotEqual(pol.last_reason, "stuck:recall-escape")

    def test_conquered_forgetting_maze_recalls_on_stuck_streak(self):
        maze = DungeonInfo(
            4, "Labyrinth", 10, 18, 1,
            flags=frozenset({"MAZE", "FORGET"}),
            guardian_id=1034,
        )
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(4, 18, 0),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
            conquered_dungeon_ids=(4,),
        )
        pol = HengbotPolicy(dungeon_knowledge={4: maze})
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        self.assertEqual(pol.choose_key(snap), "rr")
        self.assertEqual(pol.last_reason, "stuck:recall-escape")

    def test_visible_maze_upstairs_is_retried_after_stale_route_expiry(self):
        maze = DungeonInfo(
            4, "Labyrinth", 10, 18, 1,
            flags=frozenset({"MAZE", "FORGET"}),
        )
        stair = grid(10, 11, upstairs=True, in_view=True)
        pol = HengbotPolicy(dungeon_knowledge={4: maze})
        pol._nav_ledger.expire("ascend", stair.position)

        self.assertTrue(pol._is_upstairs_target(stair))
        pol._stair_rejection_strikes[("<", stair.position)] = 2
        self.assertFalse(pol._is_upstairs_target(stair))

    def test_active_random_quest_does_not_recall_on_stuck_streak(self):
        snap = Snapshot(
            player(10, 10),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 6, 40),
            inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)],
        )
        pol = HengbotPolicy()
        pol._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        pol.last_reason = "search"

        key = pol.choose_key(snap)

        self.assertNotEqual(key, "rr")
        self.assertNotEqual(pol.last_reason, "stuck:recall-escape")

    def test_forgetting_maze_routes_to_a_remembered_downstairs(self):
        maze = DungeonInfo(
            4, "Labyrinth", 10, 18, 1,
            flags=frozenset({"MAZE", "FORGET"}),
        )
        visible = Snapshot(
            player(10, 10),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11, downstairs=True),
            },
            [],
            floor_key=(4, 10, 0),
        )
        forgotten = replace(
            visible,
            grids={
                Position(10, 10): grid(10, 10),
                Position(10, 11): grid(10, 11),
            },
        )
        pol = HengbotPolicy(dungeon_knowledge={4: maze})
        pol._build_grid_index(visible)
        pol._build_grid_index(forgotten)

        self.assertEqual(pol._descent_step(forgotten), Position(10, 11))
        self.assertEqual(pol.last_reason, "seek-downstairs")

    def test_forgetting_maze_moves_instead_of_searching_each_corridor_tile(self):
        maze = DungeonInfo(
            4, "Labyrinth", 10, 18, 1,
            flags=frozenset({"MAZE", "FORGET"}),
        )
        center = Position(10, 10)
        east = Position(10, 11)
        grids = {center: grid(10, 10), east: grid(10, 11)}
        for dy, dx in (
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1), (0, 1),
            (1, -1), (1, 0), (1, 1),
        ):
            pos = Position(10 + dy, 10 + dx)
            if pos not in grids:
                grids[pos] = grid(pos.y, pos.x, passable=False)
        snap = Snapshot(
            player(10, 10),
            grids,
            [],
            floor_key=(4, 18, 0),
        )
        pol = HengbotPolicy(dungeon_knowledge={4: maze})
        pol._recent.extend([center] * STUCK_WINDOW)
        pol._should_start_town_return = lambda _snapshot: False
        pol._return_to_town_key = lambda _snapshot, _hostiles: None

        self.assertEqual(pol.choose_key(snap), "6")
        self.assertNotEqual(pol.last_reason, "search")
        self.assertEqual(pol._search_counts[center.y, center.x], 0)














class ResistanceDepthGateTest(unittest.TestCase):
    """The depth-requirement table (AGENTS.md) gates descent and steers equipment:
    never descend into a band whose mandatory resistances the character lacks, and
    prefer jewelry that closes a required-resistance gap."""

    def _at(self, depth, abilities, inventory=(), equipment=(), speed=110):
        return Snapshot(
            player(
                10, 10, class_id=PLAYER_CLASS_WARRIOR,
                abilities=frozenset(abilities), speed=speed,
            ),
            {Position(10, 10): grid(10, 10, downstairs=True)},
            [],
            floor_key=(DUNGEON_ANGBAND, depth, 0),
            inventory=list(inventory),
            equipment=list(equipment),
        )

    def test_blocks_descent_without_the_required_resistance(self):
        snap = self._at(24, set())  # 24F -> 25F needs free action + confusion + fire
        self.assertFalse(
            HengbotPolicy()._is_descent_target(snap, snap.grids[Position(10, 10)])
        )

    def test_stair_refusal_explores_across_consecutive_decisions(self):
        snap = self._at(
            30, {"resist_pois", "resist_cold", "resist_elec", "resist_acid"}
        )
        grids = {
            Position(y, x): grid(
                y, x, lit=True, downstairs=(y == 10 and x == 10)
            )
            for y in range(7, 14)
            for x in range(7, 14)
        }
        snap = replace(
            snap,
            player=replace(snap.player, class_id=-1),
            grids=grids,
        )
        policy = HengbotPolicy()
        directions = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }
        position = snap.player.position
        visited = {position}
        keys = []

        for decision in range(6):
            current = replace(
                snap,
                turn=snap.turn + decision,
                player=replace(snap.player, position=position),
            )
            key = policy.choose_key(current)
            keys.append(key)
            self.assertIn(key, directions, (decision, key, policy.last_reason))
            dy, dx = directions[key]
            position = Position(position.y + dy, position.x + dx)
            visited.add(position)

        self.assertEqual(keys, ["7", "3", "8", "2", "9", "1"])
        self.assertNotIn(WAIT_KEY, keys)
        self.assertNotIn(policy_module.DOWN_STAIRS_KEY, keys)
        self.assertGreaterEqual(len(visited), 4)

    def test_allows_descent_once_the_requirement_is_met(self):
        snap = self._at(24, {"free_action", "resist_conf", "resist_fire"})
        self.assertTrue(
            HengbotPolicy()._is_descent_target(snap, snap.grids[Position(10, 10)])
        )

    def test_20f_requires_free_action_and_fire_but_not_confusion(self):
        policy = HengbotPolicy()
        self.assertEqual(
            policy._missing_required_abilities(
                self._at(19, {"free_action", "resist_fire"}), 20
            ),
            frozenset(),
        )
        self.assertEqual(
            policy._missing_required_abilities(self._at(19, {"resist_fire"}), 20),
            frozenset({"free_action"}),
        )
        self.assertEqual(
            policy._missing_required_abilities(
                self._at(20, {"free_action", "resist_fire"}), 21
            ),
            frozenset({"resist_conf"}),
        )

    def test_shallow_floors_need_no_resistance(self):
        snap = self._at(5, set())
        self.assertTrue(
            HengbotPolicy()._is_descent_target(snap, snap.grids[Position(10, 10)])
        )

    def test_reports_the_missing_abilities_for_a_band(self):
        snap = self._at(30, {"resist_pois"})  # 26-30F needs pois+cold+elec+acid
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(snap, 30),
            frozenset({"resist_cold", "resist_elec", "resist_acid"}),
        )

    def test_50f_also_requires_a_destruction_method(self):
        # AGENTS.md: from 50F a usable *Destruction* method is mandatory on top
        # of the resistance table; it is not a player.abilities flag.
        abilities = {"resist_chaos", "resist_neth", "telepathy"}
        snap = self._at(49, abilities)  # 49F -> 50F
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(snap, 50),
            frozenset({"destruction"}),
        )
        self.assertFalse(
            HengbotPolicy()._is_descent_target(snap, snap.grids[Position(10, 10)])
        )

    def test_destruction_scroll_or_charged_staff_satisfies_the_50f_gate(self):
        abilities = {"resist_chaos", "resist_neth", "telepathy"}
        scroll = self._at(
            49, abilities,
            inventory=[item("s", TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION)],
        )
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(scroll, 50), frozenset()
        )
        self.assertTrue(
            HengbotPolicy()._is_descent_target(scroll, scroll.grids[Position(10, 10)])
        )
        charged = self._at(
            49, abilities,
            inventory=[item("u", TVAL_STAFF, SV_STAFF_DESTRUCTION, charges=2)],
        )
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(charged, 50), frozenset()
        )
        empty_staff = self._at(
            49, abilities,
            inventory=[item("u", TVAL_STAFF, SV_STAFF_DESTRUCTION, charges=0)],
        )
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(empty_staff, 50),
            frozenset({"destruction"}),
        )

    def test_81f_also_requires_speed_plus_25(self):
        abilities = {"resist_chaos", "resist_neth", "telepathy"}
        kit = [item("s", TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION)]
        slow = self._at(80, abilities, inventory=kit)  # base speed 110
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(slow, 81),
            frozenset({"speed+25"}),
        )
        fast = self._at(80, abilities, inventory=kit, speed=135)
        self.assertEqual(
            HengbotPolicy()._missing_required_abilities(fast, 81), frozenset()
        )




























































class SecondHomeScanAndAccidentalEntryTest(unittest.TestCase):
    def test_posted_movement_into_store_suppresses_next_surface_key(self):
        from absorbing_state_catalog import (
            _movement_opens_store_before_surface_observation,
        )

        policy, world = _movement_opens_store_before_surface_observation()
        posted = []
        movement = policy.choose_key(world.snapshot(1))
        sent, posted_line = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            "movement-opens-store", movement, None, set(), in_store=False,
        )
        self.assertTrue(sent)
        policy.confirm_key_posted(movement)
        world.apply(movement)
        next_key = policy.choose_key(world.snapshot(2))
        sent, _ = _send_new_decision_key(
            lambda value, **_kwargs: posted.append(value) or True,
            "first-open-store-page", next_key, posted_line, {movement},
            in_store=True,
        )

        self.assertEqual(
            posted, ["6"],
            f"a surface key landed in the open store: {posted!r}",
        )
        self.assertFalse(sent)
        self.assertEqual(policy.last_reason, "store:entry-await-observation")









def step_toward_concatenation_offenders(tree: ast.Module) -> list[tuple[str, int]]:
    """Find every composition of a ``_step_toward`` result outside the owner.

    Flags a ``_step_toward`` call anywhere inside a BinOp at any nesting
    depth, and the laundered forms: the call's result bound to a name
    (assignment, annotated assignment, walrus, augmented assignment) that is
    later used in a BinOp or augmented assignment within the same function.
    """

    def is_step_toward(node):
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_step_toward"
        )

    def contains_call(expr):
        return any(is_step_toward(sub) for sub in ast.walk(expr))

    offenders = []
    for function in (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        tainted = set()
        for node in ast.walk(function):
            if not isinstance(
                node, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.AugAssign)
            ):
                continue
            if node.value is None or not contains_call(node.value):
                continue
            if isinstance(node, ast.Assign):
                tainted.update(
                    target.id
                    for target in node.targets
                    if isinstance(target, ast.Name)
                )
            elif isinstance(node.target, ast.Name):
                tainted.add(node.target.id)

        def references_taint(expr):
            return any(
                isinstance(sub, ast.Name) and sub.id in tainted
                for sub in ast.walk(expr)
            )

        for node in ast.walk(function):
            if isinstance(node, ast.BinOp) and (
                contains_call(node) or references_taint(node)
            ):
                offenders.append((function.name, node.lineno))
            elif isinstance(node, ast.AugAssign) and (
                contains_call(node.value)
                or (
                    isinstance(node.target, ast.Name)
                    and node.target.id in tainted
                )
            ):
                offenders.append((function.name, node.lineno))
    return offenders













class OwnerExpectationContractTest(unittest.TestCase):
    def test_restore_upgrades_six_field_owner_progress_core(self):
        snapshot = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0),
        )
        policy = HengbotPolicy()
        current = policy._owner_progress_core(snapshot)
        legacy = SimpleNamespace(
            floor=current.floor,
            position=current.position,
            gold=current.gold,
            experience=current.experience,
            inventory=current.inventory,
            equipment=current.equipment,
        )
        policy._owner_expectations._pending["owner"] = policy_module.OwnerExpectation(
            legacy, frozenset({"position"})
        )
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertFalse(restored._owner_expectations.may_select(
            "owner", restored._owner_progress_core(snapshot)
        ))
        moved = replace(
            snapshot, player=replace(snapshot.player, position=Position(10, 11))
        )
        self.assertTrue(restored._owner_expectations.may_select(
            "owner", restored._owner_progress_core(moved)
        ))

    def test_unknown_expected_change_is_rejected_at_post_time(self):
        snapshot = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0),
        )
        policy = HengbotPolicy()
        with self.assertRaisesRegex(ValueError, "unknown owner expectation"):
            policy._owner_expectations.post(
                "owner", policy._owner_progress_core(snapshot), "inventroy"
            )

    def test_failed_home_withdrawal_rearms_after_decision_expiry(self):
        snapshot = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(0, 0, 0), turn=100,
        )
        policy = HengbotPolicy()
        registry = policy_module.OwnerExpectationRegistry()
        registry.post("home-errand", policy._owner_progress_core(snapshot), "inventory")
        policy._decision_sequence = 9
        self.assertFalse(registry.may_select(
            "home-errand", policy._owner_progress_core(replace(snapshot, turn=1099))
        ))
        policy._decision_sequence = 10
        self.assertTrue(registry.may_select(
            "home-errand", policy._owner_progress_core(replace(snapshot, turn=1100))
        ))
    def test_posted_owner_cannot_be_selected_twice_on_unchanged_progress_core(self):
        snapshot = Snapshot(
            player(10, 10, gold=123),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
        )
        policy = HengbotPolicy()
        progress_core = policy._owner_progress_core(snapshot)
        registry = policy_module.OwnerExpectationRegistry()

        self.assertTrue(registry.may_select("owner", progress_core))
        registry.post("owner", progress_core, "position")
        self.assertFalse(registry.may_select("owner", progress_core))
        inside_store = replace(
            snapshot,
            store=StoreState(STORE_HOME, []),
        )
        self.assertFalse(
            registry.may_select("owner", policy._owner_progress_core(inside_store))
        )
        self.assertFalse(registry.may_select("owner", progress_core))
        moved = policy._owner_progress_core(
            replace(
                snapshot,
                player=replace(snapshot.player, position=Position(10, 11)),
            )
        )
        self.assertTrue(registry.may_select("owner", moved))

    def test_pin_vacuity_undeclared_position_does_not_release_recall_read(self):
        snapshot = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            floor_key=(DUNGEON_YEEK_CAVE, 10, 0),
        )
        policy = HengbotPolicy()
        registry = policy_module.OwnerExpectationRegistry()
        registry.post(
            "return:recall", policy._owner_progress_core(snapshot),
            "inventory", "recalling", "floor",
        )
        moved = replace(
            snapshot, player=replace(snapshot.player, position=Position(10, 11))
        )
        self.assertFalse(registry.may_select(
            "return:recall", policy._owner_progress_core(moved)
        ))
        recalling = replace(moved, player=replace(moved.player, recalling=True))
        self.assertTrue(registry.may_select(
            "return:recall", policy._owner_progress_core(recalling)
        ))






if __name__ == "__main__":
    unittest.main()
