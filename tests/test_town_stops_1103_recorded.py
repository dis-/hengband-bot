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


if __name__ == "__main__":
    unittest.main()
