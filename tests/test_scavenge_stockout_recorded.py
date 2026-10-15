"""Captured stock-out transition and constructed scavenge run-clock controls."""
import tests  # noqa: F401 -- isolate all runtime writes
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from hengbot.model import (
    DUNGEON_YEEK_CAVE,
    STORE_ALCHEMIST,
    STORE_HOME,
    SV_LITE_LANTERN,
    SV_POTION_CURE_CRITICAL,
    SV_SCROLL_DETECT_TREASURE,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_SCROLL,
    Position,
    parse_snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_constants import UP_STAIRS_KEY, WAIT_KEY
from policy_fixtures import grid, item, store_item

FIXTURE = Path(__file__).parent / "fixtures/scavenge-stockout-20261015.jsonl.gz"
SHA256 = "9d8960c80b3e3013e4f5fbb6b729ed3fc4f5f0cff57d230943f40fb71c5391fa"
RECORDED_STOP = (348228, "9", "town:blocked:departure-unsatisfiable")


class ScavengeStockoutRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        cls.rows = [
            json.loads(line)
            for line in gzip.open(FIXTURE, "rt", encoding="utf-8")
        ]
        cls.home, cls.alchemist, cls.terminal = map(parse_snapshot, cls.rows)

    def policy_with_stockout(self, board=None, *, mode=None):
        board = board or self.terminal
        policy = HengbotPolicy()
        if mode is not None:
            policy._fundraising_mode = mode
        policy.prime(board)
        # The captured Home page was empty for detection; these completion flags
        # represent its completed knowledge scan in the running session.
        policy._home_knowledge_current = True
        policy._home_knowledge_invalidated = False
        policy._home_knowledge_items = []
        policy._equipment_catalog.home_scan_complete = True
        policy._town_supplier_stock[STORE_ALCHEMIST] = self.alchemist.store
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
            policy._effective_town_id(board), self.alchemist.turn
        )
        return policy

    def test_captured_stockout_takes_scavenge_transition(self):
        # On 4e68bc66 this terminal board's recorded decision was the stop
        # below; the constructed, restored context now routes it to scavenge.
        self.assertEqual(self.terminal.turn, RECORDED_STOP[0])
        self.assertEqual(self.terminal.player.gold, 2_760)
        home_items = self.home.store.items
        detection_items = [
            item for item in self.alchemist.store.items
            if item.is_treasure_detection_scroll
        ]
        self.assertFalse(any(item.is_treasure_detection_scroll for item in home_items))
        self.assertEqual(detection_items, [])
        policy = self.policy_with_stockout()
        policy._town_cycle_pending = True
        key = policy._town_special_key(self.terminal)
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:cycle-break")
        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.assertTrue(policy._detectionless_scavenge_allowed(self.terminal))

    def test_carried_or_home_detection_vetoes_stockout_exception(self):
        carried = replace(
            self.terminal,
            inventory=(*self.terminal.inventory,
                       item("z", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)),
        )
        policy = self.policy_with_stockout(carried)
        self.assertFalse(policy._detectionless_scavenge_allowed(carried))
        self.assertIsNone(policy._settle_fundraising_detection(carried))
        self.assertEqual(policy._fundraising_mode, "mine")

        policy = self.policy_with_stockout()
        policy._home_knowledge_items = [
            item("z", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)
        ]
        self.assertFalse(policy._detectionless_scavenge_allowed(self.terminal))
        self.assertEqual(
            policy._settle_fundraising_detection(self.terminal), STORE_HOME
        )
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_unobserved_alchemist_does_not_prove_stockout(self):
        policy = HengbotPolicy()
        policy.prime(self.terminal)
        policy._home_knowledge_current = True
        policy._home_knowledge_invalidated = False
        policy._equipment_catalog.home_scan_complete = True
        self.assertFalse(policy._detectionless_scavenge_allowed(self.terminal))
        self.assertEqual(
            policy._settle_fundraising_detection(self.terminal), STORE_ALCHEMIST
        )
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_restored_checkpoint_defaults_run_clock(self):
        policy = HengbotPolicy()
        self.assertIsNone(policy._scavenge_run_start_turn)
        policy.__dict__.pop("_scavenge_run_start_turn", None)
        policy._policy_state_version = 5
        normalize_policy_state(policy)
        self.assertIsNone(policy._scavenge_run_start_turn)

    def test_existing_too_expensive_case_still_scavenges(self):
        policy = self.policy_with_stockout()
        expensive = replace(
            self.alchemist.store,
            items=[store_item("a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
                              price=self.terminal.player.gold + 1)],
        )
        policy._town_supplier_stock[STORE_ALCHEMIST] = expensive
        self.assertTrue(policy._detectionless_scavenge_allowed(self.terminal))
        self.assertIsNone(policy._settle_fundraising_detection(self.terminal))
        self.assertEqual(policy._fundraising_mode, "scavenge")

    def test_scavenge_run_returns_at_10000_and_new_run_resets_clock(self):
        start_turn = self.terminal.turn
        position = Position(10, 10)
        grids = {
            position: grid(10, 10, upstairs=True),
            Position(10, 11): grid(10, 11),
        }
        floor = replace(
            self.terminal,
            player=replace(
                self.terminal.player, position=position, food_state="normal",
            ),
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            town_flag=False,
            turn=start_turn,
            grids=grids,
            store=None,
            inventory=(*self.terminal.inventory,
                       item("f", TVAL_FOOD, 1)),
        )
        policy = self.policy_with_stockout(floor, mode="scavenge")
        self.assertEqual(policy._scavenge_run_start_turn, start_turn)

        # Constructed next-frontier continuation keeps the existing scavenge
        # work active at 9,999 elapsed turns.
        with patch.object(policy, "_explore_step", return_value=Position(10, 11)):
            before_limit = replace(floor, turn=start_turn + 9_999)
            policy._fundraising_key(before_limit, [])
        self.assertFalse(policy._returning_to_town)
        self.assertEqual(policy._scavenge_run_start_turn, start_turn)
        self.assertEqual(policy.last_reason, "fundraise:scavenge")

        at_limit = replace(floor, turn=start_turn + 10_000)
        key = policy._fundraising_key(at_limit, [])
        self.assertEqual(key, UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, "fundraise:ascend")
        self.assertTrue(policy._returning_to_town)

        # A town re-settlement starts a fresh clock; the next floor's first
        # board records its own game-turn origin.
        policy._returning_to_town = False
        self.assertIsNone(policy._settle_fundraising_detection(self.terminal))
        self.assertIsNone(policy._scavenge_run_start_turn)
        next_run = replace(floor, turn=start_turn + 20_000)
        policy._fundraising_key(next_run, [])
        self.assertEqual(policy._scavenge_run_start_turn, next_run.turn)

    def test_scavenge_departure_keeps_survival_gates_without_cure_potions(self):
        ready = replace(
            self.terminal,
            player=replace(
                self.terminal.player,
                hp=self.terminal.player.max_hp,
                mp=self.terminal.player.max_mp,
                food_state="normal",
                confused=False,
                blind=False,
                poisoned=False,
                cut=False,
            ),
            inventory=(
                *(obj for obj in self.terminal.inventory
                  if not (obj.tval == TVAL_POTION
                          and obj.sval == SV_POTION_CURE_CRITICAL)),
                item("f", TVAL_FOOD, 1),
            ),
            equipment=(*self.terminal.equipment,
                       item("light", TVAL_LITE, SV_LITE_LANTERN,
                            is_equipment=True, fuel=5_000)),
            store=None,
        )
        self.assertFalse(any(
            obj.tval == TVAL_POTION
            and obj.sval == SV_POTION_CURE_CRITICAL
            for obj in ready.inventory
        ))
        policy = self.policy_with_stockout(ready)
        policy._fundraising_mode = "scavenge"
        self.assertTrue(policy._fundraising_departure_ready(ready))
        for label, damaged in (
            ("hp", replace(ready, player=replace(ready.player, hp=ready.player.hp - 1))),
            ("mp", replace(ready, player=replace(ready.player, mp=ready.player.mp - 1))),
            ("status", replace(ready, player=replace(ready.player, confused=True))),
            ("light", replace(ready, equipment=(), inventory=tuple(
                obj for obj in ready.inventory if not obj.is_light
            ))),
            ("food", replace(ready, player=replace(ready.player, food_state="hungry"),
                              inventory=tuple(obj for obj in ready.inventory
                                              if not obj.is_food))),
        ):
            with self.subTest(gate=label):
                self.assertFalse(policy._fundraising_departure_ready(damaged))
