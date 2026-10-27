"""#47 / incident #119: sell first on the unchanged October 27 boards.

DECLARED ATTACH: the truncated capture has no Python checkpoint. Restore the
recorded exhausted Black Market plan, completed store visits, rejected sheet
reason and the Home knowledge answer. The failed artifact destruction at
10937..10939 supplies its undestroyable identity. The unrelated skill cache
prevents a new attach from spending this decision on a census. No captured
inventory, position or store field is changed in the recorded pins.

Each attach ends at its first divergent key. The executor's command-ready
answer below is a constructed protocol boundary, not a claimed live response
to the newly selected travel key. Refused outlets and worthless-object cases
are explicitly constructed controls.
"""
from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime writes
import copy
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from hengbot.cli import (_consume_response_sequence, _ExecutorInputPort,
                         _send_new_decision_key)
from hengbot.model import parse_snapshot, STORE_MAGIC
from hengbot.policy_types import TownErrandPlan
from tests import test_input_executor as executor_harness
from tests.test_esp_threat_rest_recorded import _policy

FIXTURE = Path(__file__).parent / "fixtures/rod-overflow-20261027.json.gz"
SHA256 = "0ded04b3f4f9977bff9e8153feed1adbd2f78bdde63e57d8b0b51753eee7ff6a"


class RodOverflowRecordedTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.capture = json.load(stream)

    def attached(self, index=97, *, refused=False):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        policy = _policy(directory, {})
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        _consume_response_sequence(
            [json.dumps(self.capture["boards"][38])], policy, lambda key: True, {},
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        raw = self.capture["boards"][index]
        board = parse_snapshot(raw)
        policy.prime(board)
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        policy._town_errand_plan = TownErrandPlan([6], {}, index=1)
        reason = "equipment-stat-modifiers-unknown"
        policy._calibration_unavailable_reason = reason
        policy._calibration_rejection = (None, reason)
        for store_type in (1, 2, 3, 4, 5, 6, 7):
            policy._set_town_store_attempted(store_type, board.turn, "visit-complete")
        policy._undestroyable_sigs.update(
            policy._item_signature(item) for item in board.inventory if item.is_artifact
        )
        if refused:
            # Constructed: real sale refusals at every outlet, Home unavailable
            # for this visit. This isolates the terminal overflow decision.
            policy._store_sale_refused.update(range(8))
            policy._home_deposit_abandoned = True
        return policy, board, raw

    def test_recorded_pack_routes_to_sale_after_completed_shop_visits(self):
        policy, board, raw = self.attached()
        self.assertEqual((board.turn, len(board.inventory)), (1664219, 21))
        recorded = self.capture["decisions"][-2]
        self.assertEqual((recorded["reason"], recorded["key"]),
                         ("town:destroy-overflow", "01kf"))
        self.assertEqual(recorded["town_plan"]["index"], 1)
        self.assertEqual(recorded["equipment_optimization"]["calibration"][
            "unavailable_reason"], "equipment-stat-modifiers-unknown")
        self.assertIn(STORE_MAGIC, policy._town_store_attempted)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b`n&.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_MAGIC)
        candidate = policy._find_town_organization_surplus(board)
        self.assertEqual((candidate.slot, candidate.tval), ("l", 40))
        self.assertNotIn(STORE_MAGIC, policy._town_store_attempted)

        # Follow's actual sender and executor submit the selected travel key.
        game = executor_harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_harness.command_screen(board.turn)
        after = copy.deepcopy(raw)
        after["turn"] = board.turn + 1
        game.states = [after]
        game.screens = [executor_harness.command_screen(after["turn"])]
        _, client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(
            deadline=time.monotonic() + 2).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                  request_budget=2, policy=policy)
        _send_new_decision_key(
            port, json.dumps(raw), key, None, set(), in_store=False, snapshot=board,
            decision={"sequence": policy._decision_sequence,
                      "reason": policy.last_reason, "key": key})
        self.assertEqual(port.last_result.outcome, "completed")
        # Follow expands the configured Magic-store travel macro to Ctrl-Q.
        self.assertEqual(game.accepted, ["\x11"])

    def test_current_magic_page_still_accepts_surplus_after_observation_visit(self):
        policy, board, _ = self.attached(72)
        self.assertEqual(board.store.store_type, STORE_MAGIC)
        self.assertEqual(policy._town_organization_sale_store(
            board, next(item for item in board.inventory if item.tval == 40)), STORE_MAGIC)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b", "shop:observe-and-leave"))
        policy.confirm_key_posted(key)
        # The captured next row really is the exit from this observation page.
        outside = parse_snapshot(self.capture["boards"][73])
        key = policy.choose_key(outside)
        self.assertEqual((key, policy.last_reason), ("{l@0\r", "shop:batch-inscribe"))

    def test_recorded_detection_rod_is_never_terminal_overflow_victim(self):
        policy, board, _ = self.attached(refused=True)
        rod = next(item for item in board.inventory if item.slot == "f")
        self.assertEqual((rod.tval, rod.sval), (66, 6))
        self.assertTrue(policy._has_town_economic_path(rod))
        self.assertIsNone(policy._overflow_disposal_item(board))
        self.assertEqual((policy.choose_key(board), policy.last_reason),
                         ("1", "town:blocked:overflow-no-legal-disposal"))

    def test_recorded_remove_curse_scroll_is_never_terminal_overflow_victim(self):
        policy, board, _ = self.attached(93, refused=True)
        scroll = next(item for item in board.inventory if item.slot == "f")
        self.assertEqual((scroll.tval, scroll.sval), (70, 14))
        self.assertTrue(policy._has_town_economic_path(scroll))
        self.assertIsNone(policy._overflow_disposal_item(board))
        self.assertEqual((policy.choose_key(board), policy.last_reason),
                         ("1", "town:blocked:overflow-no-legal-disposal"))

    def test_actual_sale_refusal_still_closes_outlet(self):
        policy, board, _ = self.attached()
        amulet = next(item for item in board.inventory if item.slot == "l")
        self.assertEqual(policy._town_organization_sale_store(board, amulet), STORE_MAGIC)
        policy._store_sale_refused.update(range(8))
        self.assertIsNone(policy._town_organization_sale_store(board, amulet))

    def test_constructed_worthless_bottle_remains_a_last_resort(self):
        policy, board, _ = self.attached(refused=True)
        # Constructed negative control: a broken bottle has zero sale value.
        # Leave all retained supplies and gear unchanged.
        bottle = replace(board.inventory[5], tval=2, sval=1, name="Empty Bottle",
                         is_broken=True, charges=0, pval=0,
                         damage_dice_num=0, damage_dice_sides=0)
        board = replace(board, inventory=[
            bottle if item.slot == bottle.slot else item for item in board.inventory
        ])
        self.assertFalse(policy._has_town_economic_path(bottle))
        self.assertIs(policy._overflow_disposal_item(board), bottle)
        self.assertEqual((policy.choose_key(board), policy.last_reason),
                         ("01kf", "inventory:destroy-disposable-item"))
