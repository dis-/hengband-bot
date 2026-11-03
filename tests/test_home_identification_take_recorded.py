"""n1-a life-472 (2026-11-03 12:05): a doable Home identification take was never done.

The fourth town:blocked:unmet:home_candidate_resolved stop of this root.
The catalogue take of the Home cloak was filed while an Identify scroll was
carried; the scroll was shelved at Home (journal row 62) and the take stayed
filed, unposted and undoable.  The binder skips while any take is filed, so
the 全耐性の防護服 [6,+8] that the *Identify* bought at row 68 could identify
was never filed, Home was already tried, and the town end stopped.

Now one rule (hengbot.home_identification) decides which Home candidate the
visit can identify for the binder, for the release of a filed take, and for
the town end's identification wait: the cloak's take gives way to the
armour's (row 126), and the town end routes Home for that filed take
instead of stopping.

Recorded: the capture's arrival checkpoint and visit journal
(tests/extract_home_identification_take_fixture.py).  All 144 decisions
before the stop replay unchanged through the public chooser; the stop board
now travels Home, posted through the production executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import home_identification, identification_wait
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore
from tests import test_input_executor as executor_pins
from town_work_corpus import replay_window


FIXTURE = Path(__file__).with_name("fixtures") / "home-identification-take-20261103"
STOP = "town:blocked:unmet:home_candidate_resolved"
ARMOUR = ("全耐性の防護服 [6,+8]", 36, 9)


class HomeIdentificationTakeRecordedTest(executor_pins.ProductionHarness):
    def test_town_end_routes_home_for_the_doable_take(self):
        with TemporaryDirectory() as raw:
            visit = Path(raw) / "town-arrival"
            visit.mkdir()
            (visit / POLICY_FILE).write_bytes(
                lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
            (visit / JOURNAL_FILE).write_bytes(gzip.compress(
                lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())))
            rows = journal(visit)
            self.assertEqual((rows[-1]["key"], rows[-1]["reason"]), ("5", STOP))
            scratch = Path(raw) / "scratch"
            scratch.mkdir()
            policy = restore(visit, scratch)
            steps = list(decisions(policy, visit, scratch))
            result = replay_window("n1-a-472", policy, iter(steps[:-1]))
            self.assertIsNone(result.first_divergence)
            self.assertEqual(result.matched_rows, 144)
            board = steps[-1][1]()
            key = policy.choose_key(board)

        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        # The filed take is the armour, and the three owners agree on it.
        self.assertEqual(policy._home_errand.request.signature, ARMOUR)
        self.assertEqual([policy._item_signature(item) for item in
                          home_identification.candidates(policy, board)], [ARMOUR])
        self.assertTrue(identification_wait.visit_can_identify(policy, board))

        raw_board = json.loads(rows[-1]["line"] or rows[-1]["inputs"][-1])
        game = executor_pins.FaithfulHookGame()
        game.state = raw_board
        game.screen = executor_pins.command_screen(raw_board["turn"])
        # DECLARED CONSTRUCTED: the next board after the travel command.
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
        # The executor posts the travel macro as the game's travel key.
        self.assertEqual(game.accepted, [""])


if __name__ == "__main__":
    unittest.main()
