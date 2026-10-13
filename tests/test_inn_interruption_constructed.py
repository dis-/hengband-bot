"""DECLARED CONSTRUCTED R12/R11/R9 boards; no state rows were recorded.

The frozen decision rows establish coordinates/reasons/owner order only.
These boards use the real Outpost and Telmora maps of the game directory. Combat
effects and missing earlier route minima are explicitly constructed, not replay.
"""
import tests  # noqa: F401
import base64
import copy
import json
import pickle
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot import cli
from hengbot.claim_register import reach
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import Position
from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_types import CrossTownShoppingExpedition
from test_surface_map_walks import _board, _town_maps

FIXTURES = Path(__file__).parent / "fixtures"
Q2 = "fixedquest:q2-teleport"
SHOP = "town:cross-town-shopping:travel-1"


def policy_for(town):
    # The game's own town maps, read from the game directory like the other
    # surface-walk tests (game data is not copied into this repository).
    maps = _town_maps()
    policy = HengbotPolicy(town_map=maps[town], town_maps=maps)
    policy._cross_town_shopping = CrossTownShoppingExpedition(
        0, ("healing",), {"healing": 2000}, 0, 2000, (1, 2),
        target_town_id=1,
    )
    return policy


def emit(policy, town, at, reason, key=None):
    board = _board(town, at, turn=1000 + policy._decision_sequence)
    policy.prime(board)
    if key is None:
        destination = 0 if town == 1 else 1
        key = policy._town_teleport_route(board, destination).key
    def proposal(_board, *_args):
        policy.last_reason = reason
        if reason in {Q2, SHOP}:
            route = policy._town_teleport_building_route(
                _board, policy._town_teleport_building_positions(_board))
            if route is not None:
                policy._declare_reach(route.target,
                                      family=policy._town_turn_arbiter.owner_for_reason(reason))
        return key
    # One producer boundary isolates accounting from unrelated CL45 needs.
    # The map router, preview, held/final accounting and driver observer run.
    with patch.object(policy, "_fixed_quest_key", side_effect=proposal), \
            patch.object(policy, "_departure_supplier_counterfactual", return_value=None):
        selected = policy.choose_key(board)
    cli._observe_owner_retired_progress(policy, board, selected)
    return selected, board, policy._town_turn_arbiter.telemetry


class InnInterruptionTest(unittest.TestCase):
    def test_prior_own_edge_settles_budget_before_combat_and_identifies_its_work(self):
        for town, reason, at, moved in [(1, Q2, (23, 51), (24, 52)),
                                       (0, SHOP, (33, 111), (32, 112))]:
            with self.subTest(reason=reason):
                policy = policy_for(town)
                owner = policy._town_turn_arbiter.owner_for_reason(reason)
                for _ in range(3):
                    emit(policy, town, at, reason)
                self.assertEqual(policy._town_turn_arbiter._no_progress_by_owner[owner], 2)
                policy._owner_retired_no_progress_count = 2
                with patch("hengbot.town_work.current_record", return_value={"work_id": "combat-test"}):
                    emit(policy, town, moved, "town:kill-mob-approach", "6")
                self.assertEqual(policy._town_turn_arbiter._no_progress_by_owner[owner], 0)
                self.assertEqual(policy._owner_retired_no_progress_count, 0)
                settlement = policy._owner_retired_progress["last_settlement"]
                self.assertEqual(settlement["operation_identity"], "teleport:0" if town else "teleport:1")
                self.assertEqual(settlement["minimum_before"] - settlement["minimum_after"], 1)

    def test_stationary_route_action_cannot_supply_a_legal_own_edge(self):
        policy = policy_for(1)
        emit(policy, 1, (23, 50), Q2)
        policy._decision_sequence += 1
        policy._town_inn_route_receipt(_board(1, (23, 50)), Q2, "5", consume=True)
        policy._decision_sequence += 1
        receipt = policy._town_inn_route_receipt(_board(1, (23, 51)), Q2, "3", consume=True)
        self.assertFalse(receipt["productive"])
        self.assertIsNone(receipt["settled_owner"])

    def test_unrelated_receipt_cannot_reset_legacy_owner_budget(self):
        arbiter = HengbotPolicy()._town_turn_arbiter
        for _ in range(2):
            arbiter.observe(in_town=True, reason="melee", progress_vector=("same",))
        arbiter.observe(in_town=True, reason="melee", progress_vector=("same",),
                        route_receipt={"settled_owner": "misc"})
        self.assertEqual(arbiter._no_progress_by_owner["misc"], 2)

    def test_unrelated_owner_does_not_require_an_inn_map(self):
        policy = HengbotPolicy()
        board = _board(0, (23, 50))
        # A limited map like the existing non-target-entrance regression:
        # departure needs its entrance; it has admitted no INN transport.
        policy._town_map = SimpleNamespace(entrance=Position(23, 50))
        receipt = policy._town_inn_route_receipt(board, "depart", ">", consume=True)
        self.assertIsNone(receipt["owner"])
        self.assertFalse(receipt["productive"])

    def test_legacy_path_reproduces_the_base_recurrence_retirement(self):
        for town, reason, points in [(1, Q2, [(23, 47), (22, 48), (23, 49),
                                             (23, 50), (23, 51)]),
                                     (0, SHOP, [(34, 110), (33, 111)])]:
            with self.subTest(reason=reason):
                policy = policy_for(town)
                arbiter = policy._town_turn_arbiter
                for at in points:
                    board = _board(town, at)
                    policy.prime(board)
                    vector = policy._town_arbiter_progress_vector(board, reason)
                    arbiter.observe(in_town=True, reason=reason, progress_vector=vector)
                arbiter.observe(in_town=True, reason="melee", progress_vector=("combat",))
                board = _board(town, (21, 65) if town else (34, 110))
                policy.prime(board)
                vector = policy._town_arbiter_progress_vector(board, reason)
                self.assertTrue(arbiter.preview_may_select(reason, vector))
                telemetry = arbiter.observe(in_town=True, reason=reason, progress_vector=vector)
                self.assertTrue(telemetry["retired"])
                diagnostic = arbiter._retirement_diagnostic
                self.assertEqual(diagnostic["recurrence_count"], 2)
                self.assertEqual(diagnostic["recurrence_limit"], 2)
                self.assertEqual(diagnostic["trigger_category"], "recurrence")
                self.assertEqual(diagnostic["own_unsuccessful_count"], 1)
                self.assertEqual(diagnostic["last_pair_before"]["owner"], "misc")

    def test_recorded_decision_boundaries_remain_historical_facts(self):
        pins = json.loads((FIXTURES / "d3b-decision-pins.json").read_text(encoding="utf-8"))
        for name, sequence, reason in [("R12", 35059, Q2), ("R11", 35000, SHOP),
                                       ("R9", 6737, SHOP)]:
            row = next(row for row in pins[name] if row["decision_sequence"] == sequence)
            self.assertEqual(row["reason"], reason)
            self.assertTrue(row["arbiter"]["retired"])
        before = next(row for row in pins["R12"] if row["decision_sequence"] == 35042)
        resumed = next(row for row in pins["R12"] if row["decision_sequence"] == 35059)
        self.assertEqual(before["position"], {"y": 23, "x": 51})
        self.assertEqual(resumed["position"], {"y": 21, "x": 65})
        self.assertEqual(pins["R12"][-2]["reason"], "melee")

    def test_r12_and_shopping_resume_to_the_inn_with_all_three_seams(self):
        for town, reason, old, resumed in [(1, Q2, (23, 51), (21, 65)),
                                          (0, SHOP, (33, 111), (22, 110)),
                                          (0, SHOP, (33, 111), (34, 110))]:
            with self.subTest(reason=reason, resumed=resumed):
                policy = policy_for(town)
                # Earlier rank at the resumption cell, then route-owned walk
                # to the recorded last-own position: repeats the real vector.
                if town == 1:
                    for own_at in [(23, 47), (22, 48), (23, 49), (23, 50), old]:
                        emit(policy, town, own_at, reason)
                else:
                    own_at = resumed
                    for _ in range(1 if resumed == (34, 110) else 7):
                        _, own_board, _ = emit(policy, town, own_at, reason)
                        route = policy._town_teleport_building_route(
                            own_board, policy._town_teleport_building_positions(own_board))
                        own_at = (route.first_step.y, route.first_step.x)
                    old = own_at
                    emit(policy, town, old, reason)
                emit(policy, town, old, "town:kill-mob-approach", "6")
                emit(policy, town, resumed, "melee", "5")
                policy._owner_retired_no_progress_count = 2
                key, _, telemetry = emit(policy, town, resumed, reason)
                receipt = policy._town_inn_accounting["receipt"]
                self.assertTrue(receipt["rebaseline"])
                self.assertFalse(telemetry["progress"])
                self.assertFalse(telemetry["retired"])
                self.assertEqual(policy._owner_retired_no_progress_count, 2)
                self.assertEqual(policy._town_turn_arbiter._no_progress_by_owner[
                    policy._town_turn_arbiter.owner_for_reason(reason)], 1)
                for _ in range(50):
                    board = _board(town, resumed)
                    policy.prime(board)
                    route = policy._town_teleport_building_route(
                        board, policy._town_teleport_building_positions(board))
                    resumed = (route.first_step.y, route.first_step.x)
                    if route.remaining_edges == 1:
                        self.assertIn("m", str(key))
                        break
                    key, _, telemetry = emit(policy, town, resumed, reason)
                    self.assertTrue(telemetry["progress"])
                    self.assertFalse(telemetry["retired"])
                    self.assertEqual(policy._owner_retired_no_progress_count, 0)
                else:
                    self.fail("INN command not reached")

    def test_preview_is_read_only_and_duplicate_resumption_cannot_rebaseline(self):
        policy = policy_for(1)
        for at in [(23, 47), (22, 48), (23, 49), (23, 50), (23, 51)]:
            emit(policy, 1, at, Q2)
        emit(policy, 1, (23, 51), "town:kill-mob-approach", "6")
        emit(policy, 1, (21, 65), "melee", "5")
        board = _board(1, (21, 65))
        policy._decision_sequence += 1
        before = copy.deepcopy(policy._town_inn_accounting)
        receipt = policy._town_inn_route_receipt(board, Q2, "1")
        self.assertTrue(receipt["rebaseline"])
        self.assertEqual(policy._town_inn_accounting, before)
        policy._town_inn_route_receipt(board, Q2, "1", consume=True)
        policy._decision_sequence += 1
        duplicate = policy._town_inn_route_receipt(board, Q2, "1", consume=True)
        self.assertFalse(duplicate["rebaseline"])
        self.assertFalse(duplicate["progress"])
        self.assertEqual(duplicate["minimum_after"], 9)

    def test_second_real_interruption_survives_stale_preview_recurrence(self):
        policy = policy_for(1)
        for at in [(23, 47), (22, 48), (23, 49), (23, 50), (23, 51)]:
            emit(policy, 1, at, Q2)
        for cycle in range(2):
            emit(policy, 1, (23, 51) if cycle == 0 else (22, 64),
                 "melee" if cycle == 0 else "town:kill-mob-approach", "6")
            key, _, telemetry = emit(policy, 1, (21, 65), Q2)
            self.assertEqual(str(key), "1")
            self.assertFalse(telemetry["retired"])
            key, _, telemetry = emit(policy, 1, (22, 64), Q2)
            self.assertTrue(telemetry["progress"])
            self.assertEqual(policy._owner_retired_no_progress_count, 0)

    def test_held_route_preview_uses_the_same_qualified_receipt(self):
        policy = policy_for(1)
        for at in [(23, 47), (22, 48), (23, 49), (23, 50), (23, 51)]:
            emit(policy, 1, at, Q2)
        emit(policy, 1, (23, 51), "town:kill-mob-approach", "6")
        emit(policy, 1, (21, 65), Q2)
        emit(policy, 1, (22, 64), Q2)
        emit(policy, 1, (22, 64), "town:kill-mob-approach", "6")
        holder = policy._claim_register.declare("quest-request", reach((28, 56)),
                                                 floor=(0, 0, 0))
        # Independent held-claim seam: the real retained Reach is supplied at
        # the holder boundary; the policy gate is otherwise in its OFF mode.
        with patch.object(policy, "_town_held_decision", return_value=holder):
            key, _, telemetry = emit(policy, 1, (21, 65), Q2)
        self.assertEqual(str(key), "1")
        self.assertFalse(telemetry["retired"])
        self.assertNotIn("arbiter-retirement", {
            row["stage"] for row in policy._decision_rewrite_refused})

    def test_rebaseline_preserves_already_spent_own_budget(self):
        policy = policy_for(1)
        emit(policy, 1, (23, 51), Q2)
        emit(policy, 1, (23, 51), Q2)
        self.assertEqual(policy._town_turn_arbiter._no_progress_by_owner["quest-request"], 1)
        emit(policy, 1, (23, 51), "town:kill-mob-approach", "6")
        _, _, telemetry = emit(policy, 1, (21, 65), Q2)
        self.assertEqual(telemetry["budget_remaining_estimate"], 1)
        self.assertFalse(telemetry["progress"])
        _, _, telemetry = emit(policy, 1, (21, 65), Q2)
        self.assertTrue(telemetry["retired"])

    def test_cli_cannot_replace_the_shared_receipt_with_a_goal_only_minimum(self):
        policy = policy_for(1)
        holder = policy._claim_register.declare("quest-request", reach((28, 56)),
                                                 floor=(0, 0, 0))
        policy._claim_register.declare_execution(
            holder.claim_id, work_id="teleport:0", producer="quest-request", state="awaiting")
        # Independent driver seam: real admitted execution, with only the
        # emitted work-record lookup supplied at the CLI boundary.
        with patch("hengbot.town_work.current_record", return_value={"work_id": "teleport:0"}):
            emit(policy, 1, (23, 50), Q2)
            emit(policy, 1, (23, 51), Q2)
            policy._owner_retired_no_progress_count = 2
            # A fabricated nonadjacent own jump cannot be route evidence even
            # though BFS drops. The shared legal-edge receipt must prevail.
            _, _, telemetry = emit(policy, 1, (26, 54), Q2)
        self.assertFalse(telemetry["progress"])
        self.assertEqual(policy._owner_retired_no_progress_count, 2)

    def test_same_owner_retargeting_and_changed_topology_cannot_rebaseline(self):
        for change in ("retarget", "topology", "alias"):
            with self.subTest(change=change):
                policy = policy_for(0)
                emit(policy, 0, (33, 111), SHOP)
                emit(policy, 0, (33, 111), "town:kill-mob-approach", "6")
                reason = SHOP
                if change == "retarget":
                    policy._cross_town_shopping.target_town_id = 2
                    reason = "town:cross-town-shopping:travel-2"
                elif change == "alias":
                    reason = SHOP + "-renamed"
                board = _board(0, (34, 110))
                policy.prime(board)
                if change == "topology":
                    policy._floor_t.discard((36, 117))
                policy._decision_sequence += 1
                receipt = policy._town_inn_route_receipt(board, reason, "9", consume=True)
                self.assertFalse(receipt["rebaseline"])
                self.assertFalse(receipt["productive"])

    def test_no_closing_resumption_retires_at_existing_own_bound(self):
        for town, reason, bound in [(1, Q2, 3), (0, SHOP, 8)]:
            with self.subTest(reason=reason):
                policy = policy_for(town)
                old, displaced = ((23, 51), (21, 65)) if town else ((33, 111), (22, 110))
                emit(policy, town, old, reason)
                emit(policy, town, old, "melee", "6")
                # Combat effect observed on the first resumed board.
                for own in range(1, bound + 1):
                    key, _, telemetry = emit(policy, town, displaced, reason)
                    self.assertEqual(telemetry["retired"], own == bound)
                diagnostic = policy._town_turn_arbiter._retirement_diagnostic
                self.assertEqual(diagnostic["trigger_category"], "budget")
                self.assertEqual(diagnostic["own_unsuccessful_count"], bound)
                self.assertEqual(diagnostic["own_unsuccessful_bound"], bound)

    def test_own_bounce_and_stationary_interrupt_keep_legacy_failure_visible(self):
        for interrupt in [None, "survival:mana-absorb", "periodic:save", "melee"]:
            for town, reason, bound in [(1, Q2, 3), (0, SHOP, 8)]:
                with self.subTest(reason=reason, interrupt=interrupt):
                    policy = policy_for(town)
                    near, far = ((22, 64), (21, 65)) if town else ((33, 111), (34, 110))
                    emit(policy, town, near, reason)
                    if interrupt:
                        emit(policy, town, near, interrupt, "5")
                        emit(policy, town, near, reason)
                    owner = policy._town_turn_arbiter.owner_for_reason(reason)
                    if owner in policy._town_turn_arbiter._retired:
                        self.assertTrue(policy._town_turn_arbiter.retirement_pending)
                        continue
                    for own in range(1, bound + 1):
                        _, _, telemetry = emit(policy, town, far if own % 2 else near, reason)
                        state = policy._town_inn_accounting
                        self.assertFalse(state["receipt"]["rebaseline"])
                        self.assertFalse(telemetry["progress"])
                        if owner in policy._town_turn_arbiter._retired:
                            break
                    self.assertIn(owner, policy._town_turn_arbiter._retired)
                    self.assertLessEqual(own, bound)

    def test_fresh_and_restored_policies_have_no_interruption_memory(self):
        policy = policy_for(1)
        self.assertIsNone(policy._town_inn_accounting)
        emit(policy, 1, (23, 51), Q2)
        self.assertIsNotNone(policy._town_inn_accounting)
        encoded = checkpoint(policy)
        self.assertNotIn("_town_inn_accounting", pickle.loads(base64.b64decode(encoded)))
        with patch("hengbot.latch_onset_capture.find_monrace_definitions",
                   return_value=FIXTURES / "d3b-empty-monrace.json"):
            restored = restore_checkpoint(HengbotPolicy, encoded)
        self.assertIsNone(restored._town_inn_accounting)
        normalize_policy_state(policy, restart=True)
        self.assertIsNone(policy._town_inn_accounting)
        legacy = policy_for(1)
        legacy.__dict__.pop("_town_inn_accounting", None)
        legacy.__dict__.pop("_policy_state_version", None)
        normalize_policy_state(legacy)
        self.assertIsNone(legacy._town_inn_accounting)
        fresh = policy_for(1)
        emit(fresh, 1, (21, 65), Q2)
        self.assertFalse(fresh._town_inn_accounting["receipt"]["rebaseline"])


if __name__ == "__main__":
    unittest.main()
