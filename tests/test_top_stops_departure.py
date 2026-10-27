"""Captured CCW stockouts: public walk-in dispatch and follow execution."""
import tests  # noqa: F401
import copy
import gzip
import json
from dataclasses import replace
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import stockout_mining_intended_terminal, rung_terminal, terminal_admission
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).parent / "fixtures/top-stops-departure.json.gz"


class TopStopsDepartureTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(gzip.decompress(FIXTURE.read_bytes()))

    def scene(self, case):
        board = parse_snapshot(case["state"])
        policy = HengbotPolicy()
        policy.prime(board)
        # DECLARED CONSTRUCTED: isolate supply remedy after Home work is done;
        # no claim/checkpoint or calibration constants survive these captures.
        # Inventory, gear, map and CCW counts are the verbatim terminal board.
        policy.consume_home_knowledge(())
        for row in case["knowledge"]:
            if row["knowledge"]["category"] == "skill_exp":
                policy.consume_skill_knowledge(row)
        policy._equipment_optimization_last_depth = case["decision"]["equipment_optimization"]["optimization_depth"]
        policy._target_dungeon_id = 2
        stores = case["decision"]["departure_block"]["town_ledger"]["store_visits"]
        policy._town_store_attempted.update({int(store): board.turn for store in stores})
        policy._town_restock_suppressed = True
        return policy, board

    def send(self, board, key, reason):
        game = FaithfulHookGame()
        # DECLARED CONSTRUCTED: source-derived command response to the chosen
        # step-off/wait. This proves transport, not an observed live fix.
        raw = {"turn": board.turn, "grid_map": {"runs": []}}
        game.state = raw
        game.screen = command_screen(board.turn)
        game.screens = [command_screen(board.turn + 1)]
        game.states = [{"turn": board.turn + 1, "grid_map": {"runs": []}}]
        game, _client, executor = self.make(game)
        executor.observe_boundary(deadline=9999999999)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _posted = _send_new_decision_key(
            port, "top-stops-B", key, None, set(), in_store=False,
            decision={"sequence": 1, "reason": reason}, snapshot=board,
            posting_contract=PostingContract())
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, [str(key)])

    def test_public_walk_in_stockout_starts_preparation_even_without_detection(self):
        for case in self.cases[:2]:
            with self.subTest(source=case["source"]):
                policy, board = self.scene(case)
                self.assertFalse(policy._cure_critical_ready(board))
                self.assertIn({"item": "Cure Critical Wounds potions",
                               "current": 4 if "life-359" in case["source"] else 7,
                               "target": 10, "missing": 6 if "life-359" in case["source"] else 3,
                               "blocked_reason": "no-actionable-supplier"},
                              policy.procurement_requirements(board))
                if "life-359" in case["source"]:
                    self.assertIsNone(policy._town_recall_destination(board)[0])
                key = policy.choose_key(board)
                self.assertIn("fundraise:supply-stockout-mining", policy.last_reason)
                self.assertEqual(policy._fundraising_mode, "prepare")
                self.assertEqual(policy._planned_mining_runs, 1)
                # Preparation must have a declared admissible terminal, rather
                # than bypassing admission as an unregistered producer.
                terminal = rung_terminal(policy, "supply-stockout-prepare", board)
                self.assertIsNotNone(terminal)
                self.assertTrue(terminal_admission(policy, board, terminal).admitted)
                self.assertEqual(policy._fundraising_gold_target(), board.player.gold + 5000)
                self.send(board, key, policy.last_reason)
                if "life-193" in case["source"]:
                    self.assertEqual(policy._count_treasure_detection_scrolls(board), 0)
                    self.assertIn("fundraising-no-detection", policy._decision_terminal_admissions[0]["codes"])

    def test_optional_identification_latches_do_not_veto_the_mining_plan(self):
        policy, board = self.scene(self.cases[0])
        # The incident's ordinary dive gate also failed these stale optional
        # identification leaves. No physical transfer or session was active.
        policy._home_candidate_waiting = True
        policy._identification_need = "normal"
        failed = policy._departure_block_state(board)["failed"]
        self.assertIn("home_candidate_resolved", failed)
        self.assertIn("identification_need_clear", failed)
        self.assertIsNotNone(stockout_mining_intended_terminal(policy, board))
        key = policy.choose_key(board)
        self.assertIn("fundraise:supply-stockout-mining", policy.last_reason)
        self.send(board, key, policy.last_reason)

    def test_three_round_limit_and_hard_incomplete_transfer_remain_visible(self):
        policy, board = self.scene(self.cases[0])
        policy._supply_stockout_cycles = 3
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:blocked:departure-unsatisfiable")
        self.assertIsNone(policy._fundraising_mode)
        policy, board = self.scene(self.cases[0])
        hurt = replace(board, player=replace(board.player, hp=board.player.hp - 1))
        self.assertIsNone(stockout_mining_intended_terminal(policy, hurt))
        policy._home_pending_item = ("pending", 23, 1)
        self.assertIsNone(stockout_mining_intended_terminal(policy, board))
