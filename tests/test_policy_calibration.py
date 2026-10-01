import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import ast
import base64
import gzip
import hashlib
import inspect
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import hengbot.equipment_mutation as equipment_mutation_module
import hengbot.policy as policy_module
import hengbot.policy_calibration as policy_calibration_module
from hengbot.cli import POLICY_FINAL_STOP_REASONS
from hengbot.cli import _dispatch_response_lines
from hengbot.equipment_optimizer import (
    OwnedEquipment,
    equipment_identity,
    equipment_move_identity,
)
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import (
    GridState,
    PLAYER_CLASS_WARRIOR,
    Position,
    STORE_ALCHEMIST,
    STORE_HOME,
    STORE_TEMPLE,
    SV_LITE_FEANOR,
    SV_LITE_LANTERN,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_RESTORE_CON,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_REMOVE_CURSE,
    SV_STAFF_IDENTIFY,
    Snapshot,
    StoreState,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_RING,
    TVAL_SCROLL,
    TVAL_STAFF,
    TVAL_SWORD,
    parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, STORE_STUCK_LIMIT, WAIT_KEY
try:
    from policy_fixtures import grid, hostile, item, player, store_item
except ModuleNotFoundError:
    from tests.policy_fixtures import grid, hostile, item, player, store_item


class EquippedCalibrationRegressionTest(unittest.TestCase):
    HOME = Position(10, 12)

    def _grids(self):
        grids = {
            Position(10, x): grid(10, x) for x in range(9, 14)
        }
        grids[self.HOME] = GridState(
            position=self.HOME, known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_HOME,
        )
        return grids


    def _snapshot(self, *, inventory=(), equipment=(), monsters=(),
                  store=None, hp=200, max_hp=200):
        base = player(
            10, 10, class_id=PLAYER_CLASS_WARRIOR, level=12,
            hp=hp, max_hp=max_hp,
        )
        base = replace(
            base,
            race_id=3, personality_id=1, ac=10,
            stat_cur=(18, 10, 10, 17, 16, 9),
            stat_use=(20, 10, 10, 18, 17, 9),
        )
        return Snapshot(
            base,
            self._grids(),
            list(monsters),
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            equipment=list(equipment),
            store=store,
        )


    def _scan_complete_policy(self):
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page([])
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        return policy


    def test_unactionable_home_identification_routes_when_home_unblocked(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        target = store_item("a", TVAL_SWORD, 1, name="Home blade")
        policy._identification_need = "normal"
        policy._identification_candidate = policy._item_signature(target)
        policy._equipment_catalog._home = {
            "target": OwnedEquipment("target", target, "home")
        }
        with patch.object(
            policy, "_identification_need_actionable", return_value=False
        ):
            store_type = policy._next_required_store_type(snapshot)

        self.assertEqual(store_type, STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)


    def test_blocked_unactionable_home_identification_retires_once(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        target = store_item("a", TVAL_SWORD, 1, name="Home blade")
        policy._identification_need = "normal"
        policy._identification_candidate = policy._item_signature(target)
        policy._equipment_catalog._home = {
            "target": OwnedEquipment("target", target, "home")
        }
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            policy._town_store_visit_limit(STORE_HOME)
        )
        with patch.object(
            policy, "_identification_need_actionable", return_value=False
        ), patch.object(
            policy, "_town_terminal_transitions"
        ) as retire:
            store_type = policy._next_required_store_type(snapshot)

        retire.assert_called_once_with(snapshot)
        self.assertNotEqual(store_type, STORE_HOME)


    def test_entry_telemetry_does_not_change_public_decision(self):
        def fixture():
            policy = self._scan_complete_policy()
            snapshot = self._snapshot()
            return policy, snapshot

        control, snapshot = fixture()
        observed, observed_snapshot = fixture()

        control_key = control.choose_key(snapshot)
        observed.calibration_entry_state(observed_snapshot)
        observed.equipment_transaction_entry_state(observed_snapshot)
        observed_key = observed.choose_key(observed_snapshot)

        self.assertEqual(observed_key, control_key)
        self.assertEqual(observed.last_reason, control.last_reason)


    def test_departure_unsatisfiable_is_an_immediate_cli_final_stop(self):
        self.assertIn(
            "town:blocked:departure-unsatisfiable", POLICY_FINAL_STOP_REASONS
        )

