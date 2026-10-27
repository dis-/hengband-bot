"""Projected recorded ego-torch selection preserves its required lantern."""
import tests  # noqa: F401
import gzip
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import parse_snapshot, _parse_items
from hengbot.policy import HengbotPolicy
from hengbot.equipment_optimizer import (
    OwnedEquipmentCatalog, current_loadout, EvaluatedLoadout, LoadoutMetrics, OptimizationResult,
)
from hengbot.equipment_transaction_planner import EquipmentTransactionPlan
from hengbot.warrior_optimization import WarriorOptimizationPreparation
from hengbot.input_executor import Operation
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).parent / "fixtures/top-stops-departure.json.gz"


class TopStopsLightTest(executor_harness.ProductionHarness):
    def scene(self):
        case = json.loads(gzip.decompress(FIXTURE.read_bytes()))[2]
        board = parse_snapshot(case["state"])
        page = next(row for row in reversed(case["knowledge"]) if row["knowledge"]["category"] == "home")
        lantern = next(i for i in _parse_items(page["knowledge"]["items"], protocol=3) if i.is_lantern)
        lantern = replace(lantern, slot="k", count=1)
        # DECLARED CONSTRUCTED: the selected torch is worn as in the terminal
        # record, and one of the observed Home lanterns has just been taken.
        # Freeze only the recorded optimizer's torch selection; calibration
        # constants and a faithful pre-deposit checkpoint were not preserved.
        board = replace(board, inventory=(*board.inventory, lantern))
        policy = HengbotPolicy()
        policy.prime(board)
        policy.consume_home_knowledge(())
        for row in case["knowledge"]:
            if row["knowledge"]["category"] == "skill_exp":
                policy.consume_skill_knowledge(row)
        policy._equipment_optimization_last_depth = 19
        policy._target_dungeon_id = 2
        catalog = OwnedEquipmentCatalog()
        catalog.refresh_carried(board.inventory, board.equipment)
        loadout = current_loadout(catalog.items)
        selected = EvaluatedLoadout(loadout, LoadoutMetrics(0, 0, 0))
        result = OptimizationResult(selected, (), (), frozenset(), 0, 0, 0, 0, False, frozenset())
        prep = WarriorOptimizationPreparation(loadout, result, EquipmentTransactionPlan((), (), 0), ())
        policy._equipment_optimization_preparation = prep
        return policy, board, lantern, prep

    def test_public_route_keeps_selected_torch_and_carried_departure_lantern(self):
        policy, board, lantern, prep = self.scene()
        self.assertTrue(next(i for i in board.equipment if i.slot == "light").is_torch)
        self.assertEqual(policy._retention_reservation(board, lantern), 1)
        self.assertIsNone(policy._light_to_wield(board))
        with patch.object(policy, "_prepare_equipment_optimization", return_value=prep):
            key = policy.choose_key(board)
        self.assertNotIn(policy.last_reason, {"wield-light", "town:blocked:departure-unsatisfiable"})
        self.assertTrue(policy._light_ready(board))
        self.assertEqual(policy._retention_reservation(board, lantern), 1)
        self.assertNotIn(lantern, [i for i in board.inventory if policy._retention_surplus(board, i) > 0])
        # Source-derived command response; this is transport coverage, not a
        # captured post-change live game result.
        game = FaithfulHookGame()
        game.state = {"turn": board.turn, "grid_map": {"runs": []}}
        game.screen = command_screen(board.turn)
        game.screens = [command_screen(board.turn + 1)]
        game, _client, executor = self.make(game)
        executor.observe_boundary(deadline=9999999999)
        result = executor.submit(Operation(1, policy.last_reason, str(key), executor.ready_board), deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, [str(key)])

    def test_legacy_upgrade_remains_without_selected_torch_evidence(self):
        policy, board, lantern, _prep = self.scene()
        policy._equipment_optimization_preparation = None
        self.assertEqual(policy._light_to_wield(board), lantern)
