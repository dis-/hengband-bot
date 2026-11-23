"""The Black Markets' Restore Mana circuit whatever Angband's recall depth (n1-b life-416).

Owner rules: 2026-11-23 「闇市を回って買い足す — 4つの町の闇市を巡回して買い足し、目標に届くまで99Fへは
行かない。闇市に無ければ巡回をくり返す。」 (finale_bm_tour, finale_hold ``black_market_due``);
2026-11-19 「準備ができるまで95Fで探索」 for any other shortage.

Recorded (tests/extract_finale_bm_entry_1124_fixture.py, ``n1b-416-finale-bm-entry-1124``): the
town-arrival checkpoint of 2026-11-24 02:42:34 (turn 4601311).  Oberon was killed at 02:20 and a
Scroll of Reset Recall set Angband's recall depth to 95 at 02:21:00, so the 96F+ refusal
(angband_cap ``deep_recall_refused``) that ``finale_hold.applies`` reads no longer held: from row
16 the ordinary departure ran (the character dump, the ordinary Black Market tour's legs) and row
82 read the Word of Recall to Angband 95F with 76 of the 84 Restore Mana owned and every other
supply owned.  Rows before the one decided are replayed through the public ``choose_key`` and post
the recorded key.

DECLARED CONSTRUCTED: ``test_another_short_row_keeps_the_95f_exploration`` reads the Healing row
short beside the Restore Mana for the whole replay (``finale_hold.short_rows``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_cap, finale_bm_tour, finale_hold
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-finale-bm-entry-1124"
FIRST_DEPARTURE_ROW = 16
RECALL_ROW = 82
RECALL_KEY = "rga"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class FinaleBlackMarketEntry1124RecordedTest(unittest.TestCase):
    def replay(self, rows):
        """(policy, the board of row ``rows``) after the rows before it, as recorded."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, journal, steps = load(FIXTURE, Path(scratch.name))
        self.assertEqual(steps[rows][0]["key"], journal[rows]["key"])
        for recorded, supply in steps[:rows]:
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(supply())
            post(policy, recorded["key"])
        return policy, steps[rows][0], steps[rows][1]()

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def assert_reset_depth(self, policy, board):
        # The Reset Recall's 95F: the 96F+ refusal and its town hold do not apply.
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 95)
        self.assertFalse(angband_cap.deep_recall_refused(board, DUNGEON_ANGBAND, policy))
        self.assertFalse(finale_hold.applies(policy, board))

    def test_the_first_departure_starts_the_circuit(self):
        policy, recorded, board = self.replay(FIRST_DEPARTURE_ROW)
        self.assertEqual(recorded["reason"], "town:character-dump")
        self.assert_reset_depth(policy, board)

        key, reason = self.decide(policy, board)

        self.assertEqual(finale_hold.short_rows(policy), ["restore_mana"])
        tour = finale_bm_tour.record(policy)
        self.assertIsNotNone(tour)
        self.assertIsNone(tour.closed)
        # This town's Black Market first (the store router's approach).
        self.assertEqual(reason, finale_bm_tour.APPROACH_REASON)
        self.assertTrue(key)

    def test_restore_mana_short_does_not_recall_to_95f(self):
        policy, recorded, board = self.replay(RECALL_ROW)
        self.assertEqual((recorded["key"], recorded["reason"]),
                         (RECALL_KEY, "town:recall-to-angband"))
        self.assert_reset_depth(policy, board)
        self.assertGreater(finale_bm_tour.shortage(policy, board), 0)

        key, reason = self.decide(policy, board)

        # Recorded: ('rga', 'town:recall-to-angband'), Angband 95F with 76 of the 84.
        self.assertNotEqual(key, RECALL_KEY)
        self.assertFalse(reason.startswith("town:recall-to-"))
        self.assertTrue(finale_hold.black_market_due(policy, board))
        tour = finale_bm_tour.record(policy)
        self.assertIsNone(tour.closed)
        # Every town's Black Market was seen in this lap: the night at the inn, then the next lap.
        self.assertTrue(tour.night.due)
        self.assertTrue(reason.startswith("depart:inn-refill:finale-bm:"), reason)

    def test_another_short_row_keeps_the_95f_exploration(self):
        # DECLARED CONSTRUCTED (module docstring): the Healing short as well.
        with mock.patch.object(finale_hold, "short_rows",
                               return_value=["restore_mana", "healing"]):
            policy, _recorded, board = self.replay(RECALL_ROW)
            self.assertFalse(finale_hold.black_market_due(policy, board))
            key, reason = self.decide(policy, board)
        self.assertEqual((key, reason), (RECALL_KEY, "town:recall-to-angband"))
        self.assertIsNone(finale_bm_tour.record(policy))


if __name__ == "__main__":
    unittest.main()
