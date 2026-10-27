"""#98: captured boards through choose_key and the production follow executor.

Declared replay boundary: fresh policy plus recorded Home catalogue/capacity,
optimization depth, purchase quantities, fundraising mode and Home pass facts.
The first stop's active surplus producer is evidenced by its recorded call chain;
the second stop's block and exhausted passes are recorded diagnostic facts.
Constructed controls below change only the named availability or item count.
Executor replies are constructed command-boundary replies, not live game runs.
"""
from __future__ import annotations

import tests  # noqa: F401
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from dataclasses import replace

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _parse_items,
    _send_decision_key_with_prompt_chain,
)
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import STORE_STUCK_LIMIT
from hengbot.protocol import snapshot_protocol_version
from test_esp_threat_rest_recorded import EDIT, _policy
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).parent / "fixtures/overweight-recurrence-1027.json.gz"
SHA256 = "c2ad676e1c7357ba6cab572965130ca704b5d3171ffdc827dd19bea6da8a74c0"


class OverweightRecurrenceTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        cls.captures = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, index):
        capture = self.captures[index]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        snapshot = parse_snapshot(capture["board"], self.monrace)
        policy.prime(snapshot)
        last = capture["decisions"][-1]
        policy._equipment_optimization_last_depth = last["equipment_optimization"]["optimization_depth"]
        policy._fundraising_mode = last["fundraising"]["mode"]
        knowledge = capture["knowledge"]
        policy._adopt_home_catalogue(tuple(_parse_items(
            knowledge["knowledge"]["items"], protocol=snapshot_protocol_version(knowledge))))
        home = capture["home"]["store"]
        policy._home_capacity_observation = (
            home["stock_num"], home["capacity"], policy._effective_town_id(snapshot))
        policy._town_visit_purchases = {tuple(sig) for sig, _ in capture["purchases"]}
        policy._town_visit_purchase_quantities = {
            tuple(sig): count for sig, count in capture["purchases"]}
        projection = last["equipment_optimization"]["home_route_projection"]
        policy._town_visit_ledger.unsatisfied_passes[7] = projection["home_unsatisfied_passes"]
        policy._town_visit_ledger.approach_fails[7] = projection["home_approach_fails"]
        if projection["home_blocked"]:
            policy._town_visit_ledger.blocked_stores.add(7)
        # The skill list was already known to the running bot. Avoid a fresh
        # attachment probe; no weight/retention/route producer is replaced.
        policy._skill_exp_cache = (0, 0, snapshot.player.level, policy._town_visit_epoch)
        if index == 0:
            policy._overweight_surplus_disposal = {"town": policy._effective_town_id(snapshot)}
        else:
            policy._town_blocked_reason = "overweight-home-unreachable"
        return policy, snapshot

    def post(self, policy, snapshot, key):
        """Follow execution using constructed replies at real input barriers."""
        game = executor_harness.FaithfulHookGame()
        raw = copy.deepcopy(self.captures[0 if snapshot.turn == 556321 else 1]["board"])
        game.state = raw
        game.screen = executor_harness.command_screen(snapshot.turn)
        game.states = [dict(raw, turn=snapshot.turn + 1)]
        game.screens = [executor_harness.command_screen(snapshot.turn + 1)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "overweight-98-replay", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=snapshot, posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        # Follow maps the registered General Store travel macro to Ctrl-K.
        self.assertEqual(game.accepted, ["\x0b"] if str(key) == "\x1b`n!." else [str(key)])
        self.assertFalse(game.term_fifo)

    def test_recorded_retained_stop_is_named_and_records_its_numbers(self):
        policy, snapshot = self.replay(0)
        self.assertEqual((snapshot.turn, policy._inventory_weight(snapshot),
                          policy._inventory_weight_limit(snapshot)), (556321, 1656, 1650))
        # Reproduce all explicit reservation branches from the stop record.
        expected = self.captures[0]["decisions"][-1]["retention_reservations"]
        for entry in expected:
            item = next(i for i in snapshot.inventory
                        if policy._item_signature(i) == tuple(entry["signature"]))
            self.assertEqual(policy._retention_reservation_detail(snapshot, item),
                             (entry["reservation"], entry["branch"]))
        key = policy.choose_key(snapshot)
        self.assertEqual((str(key), policy.last_reason),
                         ("9", "town:blocked:overweight-retained-only"))
        record = json.loads(policy._overweight_surplus_record_path.read_text(
            encoding="utf-8").splitlines()[-1])
        self.assertEqual((record["weight"], record["limit"], record["excess"]), (1656, 1650, 6))
        self.assertEqual({entry[0] for entry in record["retained"]}, set("abcdefghijklmno"))
        self.post(policy, snapshot, key)

    def test_recorded_exhausted_home_uses_legal_surplus(self):
        policy, snapshot = self.replay(1)
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual((relief.route, relief.weight, relief.limit, relief.home_room),
                         ("sell-or-destroy", 1899, 1750, False))
        self.assertEqual([(i.slot, count) for _, _, i, count, _ in relief.surplus],
                         [("a", 1), ("f", 1), ("l", 4)])
        key = policy.choose_key(snapshot)
        self.assertEqual((str(key), policy.last_reason), ("\x1b`n!.", "shop:travel"))
        self.assertIsNotNone(policy._overweight_surplus_disposal)
        self.post(policy, snapshot, key)

    def test_need_router_offers_surplus_when_home_passes_are_exhausted(self):
        policy, snapshot = self.replay(1)
        policy._town_blocked_reason = None  # CONSTRUCTED: before the terminal verdict.
        self.assertIn("overweight-surplus", {need.category for need in policy._town_need_candidates(snapshot)})
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "shop:travel")
        self.post(policy, snapshot, key)

    def test_reachable_home_with_observed_room_keeps_deposit_priority(self):
        policy, snapshot = self.replay(1)
        # CONSTRUCTED: same board before Home exhausted its existing bound.
        policy._town_visit_ledger.unsatisfied_passes[7] = 0
        policy._town_visit_ledger.blocked_stores.clear()
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual((relief.route, relief.home_room), ("deposit", True))
        self.assertTrue(relief.deposits)

    def test_reachable_home_with_unknown_capacity_observes_before_surplus(self):
        policy, snapshot = self.replay(1)
        # CONSTRUCTED: same pack before the Home bound, with no capacity
        # observation. Missing knowledge must not stand for a full Home.
        policy._town_visit_ledger.unsatisfied_passes[7] = 0
        policy._town_visit_ledger.blocked_stores.clear()
        policy._town_blocked_reason = None
        policy._home_capacity_observation = None
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual((relief.route, relief.home_room), ("home-relief", False))
        categories = {need.category for need in policy._town_need_candidates(snapshot)}
        self.assertIn("weight-overload", categories)
        self.assertNotIn("overweight-surplus", categories)
        key = policy.choose_key(snapshot)
        self.assertIsNone(policy._overweight_surplus_disposal)
        self.post(policy, snapshot, key)

    def test_posted_disposal_keeps_its_existing_effect_wait_bound(self):
        policy, snapshot = self.replay(1)
        # CONSTRUCTED: all buyers refused the empty staff, its destruction
        # was posted, and the unchanged board exhausted the existing wait.
        policy._town_blocked_reason = None
        policy._store_sale_refused.update((0, 1, 2, 3, 4, 5, 6, 8))
        staff = next(item for item in snapshot.inventory if item.slot == "l")
        pending = dict(identity=policy._sale_item_identity(staff), before_count=staff.count,
                       posted=True, mode="destroy", waits=STORE_STUCK_LIMIT - 1)
        policy._overweight_surplus_disposal = {
            "town": policy._effective_town_id(snapshot), "pending": pending}
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "town:blocked:overweight-home-full-no-legal-relief")
        self.assertIs(policy._overweight_surplus_disposal["pending"], pending)
        self.assertEqual(pending["waits"], STORE_STUCK_LIMIT)
        self.post(policy, snapshot, key)

    def test_observed_home_page_does_not_reopen_an_exhausted_route(self):
        policy, snapshot = self.replay(1)
        # CONSTRUCTED: show the last recorded Home page on the stop's pack.
        # The physical free slots cannot reset the already exhausted passes.
        page = parse_snapshot(self.captures[1]["home"], self.monrace).store
        snapshot = replace(snapshot, store=page)
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual((relief.route, relief.home_room), ("sell-or-destroy", False))


if __name__ == "__main__":
    unittest.main()
