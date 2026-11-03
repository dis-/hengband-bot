"""The n1-c stops of 2026-11-04 on the viewing bots (stops-1104-0750).

Recorded: tests/extract_n1c_stops_1104_fixtures.py.  Town stops replay from
their arrival checkpoints through the public chooser; the dungeon stops decide
on their recorded boards.  Facts the capture keeps outside the board are marked
DECLARED CONSTRUCTED.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore
from test_hourly_0700_1102_recorded import RecordedTownPolicy
from tests import test_input_executor as executor_pins
from town_work_corpus import replay_window


FIXTURES = Path(__file__).with_name("fixtures") / "n1c-stops-1104"


def _boards():
    with gzip.open(FIXTURES / "boards.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


class TownStops(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, stop):
        visit = self.scratch / stop / "town-arrival"
        visit.mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURES / stop / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((FIXTURES / stop / "journal.jsonl.xz").read_bytes())))
        runtime = self.scratch / stop / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        Path(policy._home_disposal.history_path).unlink(missing_ok=True)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

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
            posting_contract=PostingContract(),
        )
        self.assertTrue(sent)

    def test_a_town_fight_is_not_the_opening_routes_standstill(self):
        """life-127 07:31:30: six shots and a rest on one cell killing a mercenary,
        then no-progress:quest on the walk to Q1's entrance."""
        policy, recorded, steps = self.load("opening-fight")
        result = replay_window("opening-fight", policy, iter(steps[:-1]))
        self.assertIsNone(result.first_divergence)
        board = steps[-1][1]()
        key = policy.choose_key(board)
        # Recorded: ('', 'quest:blocked:opening-route').
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None))
        self.assertEqual((key, policy.last_reason), ("9", "quest:enter:approach"))
        self.assert_posts(policy, recorded[-1], board, key)

    def test_the_staff_sequence_waits_for_a_pending_inscription(self):
        """life-127 07:36:26: the Magic Shop page leaves for the worn light's
        random-teleport inscription; the sequence stepped off and back in
        (7, 3, ESC) until no-progress:buy.

        The checkpoint replays only with the recorded keys acknowledged, the
        calibration file being the live process's.  DECLARED CONSTRUCTED: the
        optimizer's selection of the worn light (the live blocker
        pending-random-teleport-suppression).
        """
        policy, recorded, steps = self.load("staff-inscription")
        for entry, supply in steps[:13]:
            policy.choose_key(supply())
            if entry["key"]:
                policy.confirm_key_posted(entry["key"])
        light = next(owned.id for owned in policy._equipment_catalog.items
                     if owned.origin == "equipped" and owned.equipped_slot == "light")
        policy._equipment_preparation_selected_ids = lambda _preparation: frozenset({light})
        key = policy.choose_key(steps[13][1]())
        self.assertEqual((key, policy.last_reason), ("\x1b", "shop:observe-and-leave"))
        policy.confirm_key_posted(key)
        key = policy.choose_key(steps[14][1]())
        # Recorded: ('7', 'shop:approach').
        self.assertEqual((key, policy.last_reason), ("wja", "town:restore-combat-weapon"))
        policy.confirm_key_posted(key)
        board = steps[15][1]()
        key = policy.choose_key(board)
        # Recorded: ('3', 'shop:approach').
        self.assertEqual((key, policy.last_reason),
                         ("{/g.\r", "equipment:suppress-equipped-random-teleport"))
        self.assert_posts(policy, recorded[15], board, key)


class DungeonStops(RecordedTownPolicy):
    @classmethod
    def setUpClass(cls):
        cls.case = _boards()

    def test_a_kept_away_monster_is_not_walked_back_to_past_another_hostile(self):
        """life-125 07:18:17: the walk to shoot reached (3,65), a sleeping ゾンビ・イーク
        came into view and the board went to seek-loot, whose step out of view
        started the walk again."""
        case = self.case["loop"]
        boards = case["boards"]
        # DECLARED CONSTRUCTED: an empty Home list.
        policy = self.primed(boards[0], [], case["skill"])
        for raw, expected in zip(boards, (("7", "seek-loot"),
                                          ("3", "immobile-threat:approach-to-shoot"),
                                          ("7", "seek-loot"))):
            key = policy.choose_key(self.board(policy, raw))
            self.assertEqual((key, policy.last_reason), expected)
            policy.confirm_key_posted(key)
        key = policy.choose_key(self.board(policy, boards[3]))
        # Recorded: ('3', 'immobile-threat:approach-to-shoot').
        self.assertNotEqual(policy.last_reason, "immobile-threat:approach-to-shoot")
        self.assertNotEqual(key, "3")


if __name__ == "__main__":
    unittest.main()
