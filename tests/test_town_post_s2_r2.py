"""Owner decision 2026-10-25: recorded town boards through choose_key.

No checkpoint was captured. DECLARED runtime walls: an empty, current Home
catalogue, exhausted optional launcher enchants, known heavy worn curses, and
the failed supplier observations. The skill census response is absent. B also
skips the unrelated departure dispatcher to attach at its captured oscillating
exploration decision; it does not replace routing, S2 or the progress seam.
Post-command screens/effects below are SOURCE-DERIVED protocol controls from
market/bounty.cpp, not claimed recorded game responses.
"""
import tests  # noqa: F401

import copy
import gzip
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import (
    STORE_HOME, STORE_GENERAL,
    SV_SCROLL_ENCHANT_WEAPON_TO_HIT, SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
    parse_snapshot,
)
from hengbot.policy_types import TownErrandPlan
from hengbot.town_terminal import TerminalRef
from hengbot import town_terminal
from hengbot.home_visit import HomeVisitKind, HomeVisitRequest
from hengbot.policy_constants import DIRECTION_KEYS
from tests.test_esp_threat_rest_recorded import _policy, EDIT
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.test_input_executor import ProductionHarness, FaithfulHookGame, command_screen, prompt_screen

FIXTURES = Path(__file__).parent / "fixtures"


def rows(name, kind="state"):
    with gzip.open(FIXTURES / f"town-post-s2-1025-{name}-{kind}.jsonl.gz",
                   "rt", encoding="utf-8") as stream:
        return list(map(json.loads, stream))


def building():
    screen = command_screen()
    screen["lines"][2] = "  Hunter Office"
    screen["lines"][19] = " c) Hand over wanted remains"
    screen["lines"][23] = " ESC) Exit building"
    return screen


class PostS2OwnerDecisionTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def attached(self, name, index=0):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        raw = rows(name)[index]
        board = parse_snapshot(raw, self.monrace)
        policy.prime(board)
        policy.consume_home_knowledge(())
        policy._in_store_ops_enabled = True
        policy._crossarea_fundraising_enforced = True
        policy._launcher_enchant_attempted.update((
            SV_SCROLL_ENCHANT_WEAPON_TO_HIT, SV_SCROLL_ENCHANT_WEAPON_TO_DAM))
        policy._heavy_cursed_items.update(
            policy._item_signature(i) for i in board.equipment if i.is_cursed)
        return policy, board, raw

    def decide(self, policy, board):
        # Sole missing protocol response wall; no route/admission/selector mock.
        with patch.object(policy, "_skill_exp_request_key", return_value=None):
            return policy.choose_key(board)

    def cashout(self):
        policy, board, raw = self.attached("a1404", 6)
        shelf = parse_snapshot(rows("a1404")[8], self.monrace)
        policy._town_supplier_stock[shelf.store.store_type] = shelf.store
        policy._shopping_approach_store_type = shelf.store.store_type
        policy._shopping_approach_goal = shelf.player.position
        # Warm the missing process-local selections on the recorded board.
        # No input is posted. Then seed the captured repeated post-selection
        # fingerprint, which includes those selections as well as game facts.
        self.assertEqual(self.decide(policy, board), "7cy\x1b")
        policy._town_progress_history().append(policy._town_progress_fingerprint(board))
        return policy, board, raw

    def drive_cashout(self, raw, policy, key, question):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        after = copy.deepcopy(raw)
        after["turn"] += 1
        after["inventory"] = [i for i in after["inventory"] if not i.get("is_bounty")]
        game.screens = [building(), prompt_screen(question), building(),
                        command_screen(after["turn"])]
        game.states = [raw, raw, after, after]
        _, client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(
            deadline=time.monotonic() + 2).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False,
                                  request_budget=0.2, policy=policy)
        _send_new_decision_key(
            port, json.dumps(raw), key, None, set(), in_store=False,
            snapshot=parse_snapshot(raw, self.monrace),
            decision={"sequence": policy._decision_sequence,
                      "reason": policy.last_reason, "key": key})
        return game, port.last_result

    def test_a1_admitted_handover_reaches_its_question_and_answer(self):
        policy, board, raw = self.cashout()
        key = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), ("7cy\x1b", "bounty:cashout"))
        game, result = self.drive_cashout(
            raw, policy, key, "Hand wanted remains over? [y/n]")
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["7", "c", "y", "\x1b"])
        self.assertFalse(any(i.get("is_bounty") for i in result.board["inventory"]))

    def test_a1_foreign_question_never_borrows_the_handover_yes(self):
        policy, board, raw = self.cashout()
        key = self.decide(policy, board)
        game, result = self.drive_cashout(
            raw, policy, key, "Abandon this quest? [y/n]")
        self.assertEqual(game.accepted, ["7", "c"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_b_detector_visit_closes_empty_home_and_continues_information_work(self):
        policy, board, _ = self.attached("b")
        policy._town_store_attempted.update({i: board.turn for i in range(8)})
        # Reconstruct the captured fully explored oscillation without replacing
        # the detector itself. The saved board has no complete process history.
        policy._recent.extend([board.player.position] * policy._recent.maxlen)
        policy._town_progress_history().append(policy._town_progress_fingerprint(board))
        with patch.object(policy, "_town_special_key", return_value=None):
            key = self.decide(policy, board)
        closed = policy._town_visit_ledger.closed_terminals
        self.assertIn(TerminalRef("home-recovery", ("home-recovery",)), closed,
                      (key, policy.last_reason, policy._town_errand_plan))
        self.assertNotIn("owner-retired-burst", policy.last_reason)
        self.assertNotEqual(policy._shopping_approach_store_type, STORE_HOME)
        self.assertIsNone(policy._store_visit)
        self.assertTrue(key)
        self.assertIsNone(policy._home_visit.request)
        self.assertFalse(policy._home_visit.active)

    def test_a2_refusal_settles_only_the_same_missing_batch(self):
        policy, board, _ = self.attached("a1426")
        # Recorded held identities, explicitly reconstructed from diagnosis 10.
        missing = ("財宝感知の巻物", 70, 26)
        digger = ("穴掘りのオークのつるはし (1d3) (+8,+6) (+3) {+掘|酸}", 20, 5)
        second = ("穴掘りの戦闘用つるはし (1d8) (+6,+9) (+5) {+掘|酸}", 20, 7)
        unrelated = ("later-other-work", 70, 1)
        policy._home_pending_item = missing
        policy._home_pending_batch = [digger, second]
        policy._home_pending_quantities = {missing: 1, digger: 1, second: 1, unrelated: 2}
        policy._home_pending_quantity = 1
        policy._home_withdrawal_queued = True
        policy._town_store_attempted.update({i: board.turn for i in range(8)})
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = 1
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME], {STORE_HOME: ("stored-detection", "stored-digger")})
        # DECLARED transport state: the existing failed-native-travel latch.
        # This pin follows the fallback walk; it does not invent responses for
        # the absent native point-selector/continue-travel process state.
        policy._town_travel_fallback = policy._town_walk_in_entrance(board)
        key = self.decide(policy, board)
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual(policy._home_pending_batch, [])
        self.assertFalse(policy._home_withdrawal_queued)
        self.assertTrue({missing, digger, second} <= policy._deferred_home_items)
        self.assertEqual(policy._home_pending_quantities, {unrelated: 2})
        terminal = TerminalRef("home-withdraw", (missing, (digger, second)))
        self.assertIn(terminal, policy._town_visit_ledger.closed_terminals)
        self.assertNotIn("owner-retired-burst", policy.last_reason)
        self.assertNotEqual(policy.last_reason, "fundraise:departure-blocked")
        self.assertIn(key, DIRECTION_KEYS.values())
        # Real departure checks still apply after settling unavailable work.
        self.assertFalse(all(policy._town_departure_conjuncts(board).values()))

    def test_detector_route_key_cannot_bypass_its_borrowed_withdrawal(self):
        policy, board, _ = self.attached("a1426")
        target = ("財宝感知の巻物", 70, 26)
        policy._shopping_approach_store_type = STORE_HOME
        policy._home_visit.file(HomeVisitRequest(
            HomeVisitKind.WITHDRAW, "legacy-withdrawal", target, address=target))
        policy._home_pending_item = target
        policy._build_grid_index(board)
        policy._begin_map_predicate_cache(board)
        key = policy._shopping_approach_key(
            board, board.player.position, "town-progress-invariant:approach")
        self.assertIsNone(key)
        self.assertIsNone(policy._home_pending_item)
        self.assertIn(target, policy._deferred_home_items)

    def test_detector_borrows_concrete_home_terminals_and_unknown_store_information(self):
        policy, board, _ = self.attached("b")
        target = policy._item_signature(board.inventory[0])
        for kind, terminal_id in (
                (HomeVisitKind.DEPOSIT, "home-deposit"),
                (HomeVisitKind.EQUIPMENT_MUTATION, "no-refusal"),
                (HomeVisitKind.SCAN, "no-refusal")):
            policy._home_visit.request = HomeVisitRequest(
                kind, "test-requester", target)
            ref = town_terminal.visit_intended_terminal(policy, board, STORE_HOME)
            self.assertEqual(ref.terminal_id, terminal_id)
        ref = town_terminal.visit_intended_terminal(policy, board, STORE_GENERAL)
        self.assertTrue(town_terminal.terminal_admission(policy, board, ref).admitted)
        policy._decision_sequence += 1
        policy._town_store_attempted[STORE_GENERAL] = board.turn
        self.assertFalse(town_terminal.terminal_admission(policy, board, ref).admitted)
        self.assertFalse(town_terminal.may_take_board(
            policy, "_shopping_approach_key", "detectors", board, ref))
        self.assertIn(ref, policy._town_visit_ledger.closed_terminals)

    def test_a2_dispatcher_uses_the_refused_fundraising_terminal(self):
        policy, board, _ = self.attached("a1426")
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs = 1
        policy._build_grid_index(board)
        policy._begin_map_predicate_cache(board)
        with patch.object(policy, "_fundraising_departure_ready", return_value=False), \
                patch.object(policy, "_town_restock_wait_key", return_value=None):
            key = policy._town_special_key(board)
        self.assertIsNone(key)
        terminal = TerminalRef("fundraising", ("mine",))
        self.assertIn(terminal, policy._town_visit_ledger.closed_terminals)
        self.assertNotEqual(policy.last_reason, "fundraise:departure-blocked")


if __name__ == "__main__":
    import unittest
    unittest.main()
