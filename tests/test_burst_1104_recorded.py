"""The owner-retired-burst stops of the 2026-11-04 night (bot-6120e77fd).

Recorded: each capture's arrival checkpoint and visit journal
(tests/extract_burst_1104_fixture.py).  The rows before the fixed decision replay
unchanged through the public chooser; the fixed decision is posted through the
production executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import lzma
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest import mock

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.policy_equipment import prepare_warrior_optimization
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore
from tests import test_input_executor as executor_pins
from town_work_corpus import replay_window


FIXTURES = Path(__file__).with_name("fixtures") / "burst-1104"
BLOCKED_ON_TIMEOUT = "town:blocked:equipment-optimization-timeout"


def no_search_budget(*args, **kwargs):
    """DECLARED: the budget is zero, so the recorded timeout does not hang on the
    speed of this machine (live: 25 s, 31,661 and 41,614 of 83,968 loadouts)."""
    return prepare_warrior_optimization(*args, **{**kwargs, "timeout_seconds": 0})


class Burst1104RecordedTest(executor_pins.ProductionHarness):
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
        Path(policy._home_disposal.history_path).unlink(missing_ok=True)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def replay(self, name, policy, steps):
        """Replay ``steps`` unchanged."""
        result = replay_window(name, policy, iter(steps))
        self.assertIsNone(result.first_divergence)
        self.assertEqual(result.matched_rows, len(steps))

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

    def test_search_timeout_leaves_no_target_and_the_visit_departs(self):
        """n1-a life-480 21:09, owner-retired-burst after 27 rows of the blocked wait.

        failed: equipment_departure_ready only.  The exact search of a 43-item
        catalog ran out of budget; it names no target, as a missing calibration does.
        """
        with mock.patch("hengbot.policy_equipment.prepare_warrior_optimization",
                        no_search_budget):
            policy, recorded, steps = self.load("optimizer-timeout")
            self.replay("before-the-dump", policy, steps[:5])
            # DECLARED CONSTRUCTED: the game writes the sheet row 4 asked for.
            dump = Path(policy._character_dump_path)
            dump.write_bytes((FIXTURES / "optimizer-timeout" / "character-dump.txt").read_bytes())
            os.utime(dump, ns=(time.time_ns(), time.time_ns()))
            self.replay("the-search", policy, steps[5:6])
            self.assertEqual(recorded[6]["reason"], BLOCKED_ON_TIMEOUT)
            board = steps[6][1]()
            key = policy.choose_key(board)
            self.assertEqual(policy._equipment_optimization_preparation.blockers,
                             ("optimization-timeout",))
            self.assertEqual((key, policy.last_reason),
                             ("2", "town:entrance-step-off:town:await-recall-confirmation"))
            policy.confirm_key_posted(key)
            self.assert_posts(policy, recorded[6], board, key)
            board = steps[7][1]()
            self.assertEqual((policy.choose_key(board), policy.last_reason),
                             ("rfa", "town:recall-to-angband"))

    def test_walk_to_a_town_monster_is_not_charged_as_a_defect(self):
        """n1-c life-133 21:12, owner-retired-burst after `town-progress-invariant:
        defect:town:kill-mob-approach`: the seam relabelled the survival walk to a
        monster, so the detectors' budget of 3 retired three times in nine steps."""
        policy, recorded, steps = self.load("hunt-at-seam")
        self.replay("before-the-walk", policy, steps[:118])
        for row in range(118, 125):
            self.assertIn("town-progress-invariant:defect:", recorded[row]["reason"])
            board = steps[row][1]()
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason),
                             (recorded[row]["key"], "town:kill-mob-approach"), row)
            self.assertEqual(policy._town_turn_arbiter.telemetry["producer_owner"],
                             "survival", row)
            self.assertFalse(policy._town_turn_arbiter.pending_retirement_owners, row)
            policy.confirm_key_posted(key)
        self.assert_posts(policy, recorded[124], board, key)


if __name__ == "__main__":
    unittest.main()
