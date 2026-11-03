"""The town stops of the 2026-11-04 morning on the viewing bots, one per root.

Recorded: each capture's arrival checkpoint, calibration and visit journal
(tests/extract_town_stops_1104_fixtures.py).  The rows before the fixed decision
replay unchanged through the public chooser unless a test declares otherwise;
the fixed decision is posted through the production executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from dataclasses import replace
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, STORE_ALCHEMIST
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests import test_input_executor as executor_pins
from town_work_corpus import replay_window


FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1104"
TRAVEL_MAGIC = "\x1b`n&."
TRAVEL_HOME = "\x1b`n(."


class TownStops1104RecordedTest(executor_pins.ProductionHarness):
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
        adopt_calibration(policy, fixture / "calibration.json", runtime)
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

    def test_failed_home_take_releases_the_visit_for_the_next_store(self):
        """n1-a life-475 01:53, town:blocked:survival:identify_staff_ready.

        failed: identify_staff_ready; the Magic Shop's 12-charge staff at $808
        with 93194 gold.  The three Teleport Away wands merged into the carried
        one, the take read as failed, and the visit stayed in flight
        (operation-released-effect-not-observed): acquire_result "refused".
        """
        policy, recorded, steps = self.replay("merged-take", 15)
        self.assertEqual(recorded[15]["reason"], "town:entrance-step-off:town:end-step-off")
        board = steps[15][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (TRAVEL_MAGIC, "shop:travel"))
        self.assert_posts(policy, recorded[15], board, key)

    def test_home_requests_of_carried_items_end_with_the_home_list(self):
        """n1-a life-476 02:51, town:blocked:survival:identify_staff_ready.

        failed: identify_staff_ready; town plan Home, Magic Shop, Weapon Smiths,
        Black Market.  The withdrawals of the diggers the last visit took stayed
        queued, and each board's Home stop was their refused terminal
        (reservation-unavailable).

        DECLARED: the arrival checkpoint holds the character dump request the
        recorded first row did not answer; the dump is off for that row.
        """
        policy, recorded, steps = self.load("stale-requests")
        with mock.patch.object(HengbotPolicy, "_periodic_character_dump_key",
                               lambda _self, _snapshot, key: key):
            result = replay_window("stale-requests", policy, iter(steps[:1]))
            self.assertIsNone(result.first_divergence)
            board = steps[1][1]()
            key = policy.choose_key(board)
        self.assertEqual(recorded[1]["reason"], "town:blocked:survival:identify_staff_ready")
        self.assertEqual((key, policy.last_reason), (TRAVEL_HOME, "shop:travel"))
        self.assert_posts(policy, recorded[1], board, key)

    def test_entry_leaves_a_blocker_the_open_mining_order_does_not_buy(self):
        """n1-a life-476 02:30, town:blocked:shop-required-operation-uncomposable.

        The tagged ring's sale lost its item to an equipment plan, and the
        preflight still required the Identify staff the open mining set's
        ordinary order does not buy (cause selection-emission-mismatch).
        """
        policy, recorded, steps = self.replay("reserved-ring", 8)
        self.assertEqual(recorded[8]["reason"], "town:blocked:shop-required-operation-uncomposable")
        key = policy.choose_key(steps[8][1]())
        self.assertEqual((key, policy.last_reason), ("\x1b", "shop:in-store-done"))
        self.assertIsNone(policy._town_blocked_reason)

    def test_no_owner_left_reaches_the_town_end_and_its_release(self):
        """n1-a life-476 04:36, departure-unsatisfiable.

        failed: home_candidate_resolved, identification_need_clear,
        departure_identification_need_clear; the fallback of _town_special_key
        stopped before the town end could release a wait this visit cannot
        finish (no candidate, no source for one).
        """
        policy, recorded, steps = self.replay("identification-wait", 19)
        self.assertEqual(recorded[19]["reason"], "town:blocked:departure-unsatisfiable")
        board = steps[19][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("7", "town:entrance-step-off:town:end-step-off"))
        self.assertEqual(policy._visit_departure_recorded, set())
        self.assert_posts(policy, recorded[19], board, key)

    def test_mining_kit_rebuys_the_detection_a_churn_latch_names(self):
        """n1-b life-306 00:32, owner-retired-burst (depth-gate then fundraising).

        DECLARED CONSTRUCTED: on the recorded Alchemist page the latch and the
        open mining set are written, as the visit reached them later: the sold
        Treasure Detection latched (4, 70, 26) before the mining set opened.
        The later recorded rows no longer replay since the stale Home requests
        end (test_home_requests_of_carried_items_end_with_the_home_list).
        """
        policy, _recorded, steps = self.load("kit-latch")
        board = steps[27][1]()
        policy._town_visit_ledger.purchase_churn_class_exclusions.add((STORE_ALCHEMIST, 70, 26))
        policy._town_visit_sale_signatures.add((70, 26))
        policy._fundraising_mode = "prepare"
        with policy._in_store_pure_scope():
            item = policy._next_purchase(board)
        self.assertIsNotNone(item)
        self.assertTrue(item.is_treasure_detection_scroll)


if __name__ == "__main__":
    unittest.main()
