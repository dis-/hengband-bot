"""The town stops of the 2026-11-03 night on the viewing bots (bot-91357d2d0).

Recorded: each capture's arrival checkpoint and visit journal
(tests/extract_town_stops_1103_fixture.py).  The rows before the fixed decision
replay unchanged through the public chooser; the fixed decision is posted
through the production executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import identification_wait, town_terminal
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import STORE_ALCHEMIST, STORE_HOME
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore
from tests import test_input_executor as executor_pins
from town_work_corpus import replay_window


FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1103"
TRAVEL_HOME = "\x1b`n(."
TRAVEL_ALCHEMIST = "\x1b`n%."


class TownStops1103RecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, stop):
        """The stop's arrival policy, its journal rows and its board suppliers."""
        visit = self.scratch / stop / "town-arrival"
        visit.mkdir(parents=True)
        fixture = FIXTURES / stop
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        runtime = self.scratch / stop / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        # The stops share the isolated runtime directory; each has its own history.
        Path(policy._home_disposal.history_path).unlink(missing_ok=True)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def replay(self, stop, rows):
        """Replay the first ``rows`` rows unchanged; the policy and next steps."""
        policy, recorded, steps = self.load(stop)
        result = replay_window(stop, policy, iter(steps[:rows]))
        self.assertIsNone(result.first_divergence)
        self.assertEqual(result.matched_rows, rows)
        return policy, recorded, steps

    def assert_posts(self, policy, row, board, key):
        """The production executor posts ``key`` on the recorded board."""
        raw_board = json.loads(row["line"] or row["inputs"][-1])
        game = executor_pins.FaithfulHookGame()
        game.state = raw_board
        game.screen = executor_pins.command_screen(raw_board["turn"])
        # DECLARED CONSTRUCTED: the next board after the command.
        game.screens = [executor_pins.command_screen(raw_board["turn"] + 10)]
        game.states = [dict(raw_board, turn=raw_board["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)

    def test_purchase_that_yields_to_slot_recovery_keeps_its_supplier(self):
        """n1-b 21:59, town:blocked:survival:recall_departure_ready.

        failed: recall_departure_ready, teleport_ready, identify_staff_ready;
        fundraising-no-detection with 62 Treasure Detection on the Alchemist's
        shelf.  The kit purchase yielded to the slot recovery (row 40) and the
        outside composition latched the Alchemist as "shop-observed-complete",
        so after the deposit nothing returned to it.
        """
        policy, recorded, steps = self.replay("kit-purchase-yield", 44)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)
        board = steps[44][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (TRAVEL_ALCHEMIST, "shop:travel"))
        self.assertEqual(policy._town_errand_plan.need_categories,
                         {STORE_ALCHEMIST: ("fundraising-detection",)})
        self.assert_posts(policy, recorded[44], board, key)

    def test_recall_stockout_does_not_walk_back_to_the_supplier_it_has_tried(self):
        """n1-b 21:33: the 16 Temple visits before that stop.

        The Temple sold its 2 recall scrolls last visit and the Alchemist's
        page proves it has none, so the need registry skips both; the recall
        branch read only the attempted latch and walked into the Temple until
        the cycle break closed every store.  Now the arrival's first board
        takes the restock wait.
        """
        policy, _recorded, steps = self.load("temple-loop")
        key = policy.choose_key(steps[0][1]())
        self.assertEqual((key, policy.last_reason), ("R300\r", "town:wait-restock:temple"))

    def test_identification_wait_does_not_count_a_staff_below_its_rate(self):
        """n1-b 21:33, town:blocked:unmet:home_candidate_resolved.

        failed: recall_departure_ready, home_candidate_resolved,
        identification_need_clear, departure_identification_need_clear; two
        Identify staffs at a 71% device skill (the rule is 80%) refused by
        identify-carried as no-identification-source, while the town end's
        wait counted them as a source.  Both answers now come from one rule.
        """
        policy, _recorded, steps = self.load("temple-loop")
        board = steps[0][1]()
        policy.choose_key(board)
        self.assertLess(policy._identify_staff_success_rate(board), 0.8)
        self.assertEqual(policy._identification_candidate, ("ムチ (1d6)", 21, 2))
        self.assertFalse(town_terminal.gather_identify_carried(policy, board).source_held)
        self.assertFalse(identification_wait.visit_can_identify(policy, board))

    def test_town_end_routes_home_for_the_kit_of_an_open_mining_set(self):
        """n1-b 22:11, town:blocked:survival:cure_critical_ready.

        failed: cure_critical_ready (8 of 10); the shovel and the Treasure
        Detection are on the Home shelf, and Home was latched by the pass that
        took the identification candidate.  An open mining set makes the
        town end stop, so its kit is routed first.
        """
        policy, recorded, steps = self.replay("kit-at-home", 39)
        board = steps[39][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (TRAVEL_HOME, "shop:travel"))
        self.assertEqual(policy._town_errand_plan.need_categories,
                         {STORE_HOME: ("fundraising-kit",)})
        self.assert_posts(policy, recorded[39], board, key)

    def test_recall_countdown_is_not_charged_as_a_defect(self):
        """n1-a 21:36, owner-retired-burst after `town-progress-invariant:defect:
        town:wait-recall=>town:wait-recall`: the read scroll reopened the recall
        shortage and the seam ran its counterfactual on the accepted recall."""
        policy, recorded, steps = self.replay("recall-countdown", 29)
        for row in range(29, len(steps)):
            board = steps[row][1]()
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), ("5", "town:wait-recall"), row)
            policy.confirm_key_posted(key)
        self.assert_posts(policy, recorded[-1], board, key)

    def test_pack_pass_does_not_walk_back_past_a_pending_inscription(self):
        """n1-a 21:30, owner-retired-burst after the Magic Shop page left for
        the inscription and the pack pass stepped off and back in to sell (x4).

        The checkpoint replays only with the recorded keys acknowledged: rows 0
        and 5 depend on the periodic dump's timer and the optimizer calibration
        it refreshes.  DECLARED CONSTRUCTED: the optimizer's selection of the
        carried boots (the live blocker pending-random-teleport-suppression).
        """
        policy, _recorded, steps = self.load("inscription-first")
        for entry, supply in steps[:8]:
            policy.choose_key(supply())
            if entry["key"]:
                policy.confirm_key_posted(entry["key"])
        boots = next(owned.id for owned in policy._equipment_catalog.items
                     if owned.origin == "pack" and "ドラゴン・ブーツ" in owned.item.name)
        policy._equipment_preparation_selected_ids = lambda _preparation: frozenset({boots})
        key = policy.choose_key(steps[8][1]())
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "town-progress-invariant:continue-observed-shop"))
        policy.confirm_key_posted(key)
        board = steps[9][1]()
        key = policy.choose_key(board)
        # Recorded: ("7", "equipment:leave-store-to-suppress-random-teleport").
        self.assertEqual(policy.last_reason, "identify:full")
        self.assertTrue(key.startswith("r"), key)


if __name__ == "__main__":
    unittest.main()
