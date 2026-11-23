"""The 99F/100F Restore Mana short alone: the four towns' Black Markets lap after lap (n1-b life-416).

Owner 2026-11-23 (verbatim): 「闇市を回って買い足す — 4つの町の闇市を巡回して買い足し、目標に届くまで
99Fへは行かない。闇市に無ければ巡回をくり返す。」, with 2026-11-20 「一周する毎に宿屋で一泊する」
(finale_bm_tour, finale_hold ``town_key``).

Recorded (tests/extract_finale_town_1123_fixture.py, ``n1b-416-finale-town-1123``): the
town-arrival checkpoint of 21:13:45 (turn 4308361) in the Outpost.  Rows 0-18 are decided through
the public ``choose_key``; the board of row 19 owned 79 of the 84 Restore Mana and every other
supply, and its Black Market had been seen on this return (bm_tour).  Before the circuit the town
stopped there (``town:blocked:finale-not-in-town:restore_mana``).

DECLARED CONSTRUCTED: the later legs are not in the record.  ``test_next_town_enters_its_market``
reads the board as Telmora's (``_effective_town_id`` 1, the leg's target); the lap's end marks the
four towns seen; the night's end moves the stay's posted turn before the board's; the funds case
lowers the gold to 500.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import finale_bm_tour, finale_hold
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

TOWN = Path(__file__).with_name("fixtures") / "n1b-416-finale-town-1123"
FALLBACK_ROW = 19
TRAVEL = "town:cross-town-bm-tour:travel-"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class FinaleBlackMarketTour1123RecordedTest(unittest.TestCase):
    def replay(self):
        """(policy, the row-19 board) after rows 0-18 replayed as recorded."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(TOWN, Path(scratch.name))
        for recorded, supply in steps[:FALLBACK_ROW]:
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(supply())
            post(policy, recorded["key"])
        return policy, steps[FALLBACK_ROW][1]()

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def started(self):
        policy, board = self.replay()
        key, reason = self.decide(policy, board)
        return policy, board, key, reason

    def test_restore_mana_short_starts_the_circuit(self):
        policy, _board, key, reason = self.started()
        # Recorded before the circuit: town:blocked:finale-not-in-town:restore_mana.
        self.assertEqual(reason, f"{TRAVEL}1")
        self.assertTrue(key)
        facts = finale_bm_tour.facts(policy)
        self.assertEqual((facts["lap"], facts["seen"], facts["target"], facts["short_at_lap"]),
                         (1, [0], 1, 5))
        self.assertIsNone(facts["closed"])
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon), (DUNGEON_ANGBAND, None))

    def test_next_town_enters_its_market(self):
        policy, board, _key, _reason = self.started()
        # DECLARED CONSTRUCTED (module docstring): the board read as the leg's target, Telmora.
        with mock.patch.object(type(policy), "_effective_town_id", return_value=1):
            key = finale_hold.town_key(policy, board)
        self.assertTrue(key)
        self.assertTrue(policy.last_reason.startswith("shop:travel"), policy.last_reason)
        self.assertEqual(finale_bm_tour.facts(policy)["seen"], [0])

    def test_lap_done_takes_the_night_then_the_next_lap(self):
        policy, board, _key, _reason = self.started()
        tour = finale_bm_tour.record(policy)
        # DECLARED CONSTRUCTED (module docstring): the four towns seen.
        tour.seen, tour.target = [0, 1, 2, 3], None
        key = finale_hold.town_key(policy, board)
        self.assertTrue(key)
        self.assertEqual(policy.last_reason, "depart:inn-refill:finale-bm:approach")
        self.assertTrue(tour.night.due)
        # DECLARED CONSTRUCTED (module docstring): the stay went out on an earlier turn.
        tour.night.stay.posted_turn = board.turn - 1
        key = finale_hold.town_key(policy, board)
        self.assertTrue(key)
        facts = finale_bm_tour.facts(policy)
        self.assertEqual((facts["lap"], facts["nights"], facts["night_due"]), (2, 1, False))
        self.assertEqual(facts["laps"], [{"lap": 1, "seen": [0, 1, 2, 3], "bought": 0}])
        # The next lap begins with this town's Black Market again.
        self.assertTrue(policy.last_reason.startswith("shop:travel"), policy.last_reason)

    def test_funds_short_raises_the_gold(self):
        policy, board = self.replay()
        # DECLARED CONSTRUCTED (module docstring): 500 gold.
        poor = replace(board, player=replace(board.player, gold=500))
        key, reason = self.decide(policy, poor)
        # Owner 2026-11-18 「必要なものは買う」: no stop; the gold is raised (finale_bm_tour
        # ``_funds_key``; tests/test_finale_bm_funds_1124_recorded.py).
        self.assertFalse(reason.startswith("town:blocked:"), reason)
        self.assertIsNone(finale_bm_tour.facts(policy)["closed"])
        self.assertEqual(policy._fundraising_mode, "prepare")


if __name__ == "__main__":
    unittest.main()
