"""The Black Market tour's first leg is not undone on arrival (n1-c life-216, 2026-11-17 17:28).

Owner 2026-11-17: 「資金10万以上のときはすべての町の闇市を確認するルーティーン」 every
return by Word of Recall, Zul excluded (bm_tour).  Live (n1-c life-216, Magic-Eater,
about 2.65M gold, tests/extract_bm_tour_loop_1117_fixture.py): at the Outpost's recall
read the tour took the inn to Telmora (rows 169-170); on the arrival (row 171) the
fixed-quest return (``_fixed_quest_key``: in Telmora with no fixed quest to travel for,
back to the Outpost by inn; recorded as ``fixedquest:q2-teleport``) answered first and
took the character back; the Outpost's read point sent it to Telmora again, 1,000 gold a
round, until loop-detected at 17:28.

Now a town the circuit or the tour came to is theirs until they end
(``_cross_town_trip_holds_town``), and a tour leg to a town it already reached and was
taken away from closes the tour (``left-before-seen-N``) instead of paying again.

The rows are replayed through the public chooser and the live CLI's owner-retirement
entrance (--owner-retired-log-only), each posting its recorded key.

DECLARED CONSTRUCTED: the board of row 174 (back at the Outpost after the return live
took) decided after the fixed arrival's decision (not posted), for the bound.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import bm_tour
from hengbot.cli import _handle_owner_retirement
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "bm-tour-loop-1117" / "n1c-216-1715"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
LEG_ROWS = (169, 170)
ARRIVAL_ROW = 171
BACK_ROW = 174
TELMORA = 1


def post(policy, board, key, visit_before):
    """Post ``key`` as the live CLI does; returns what was posted."""
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    return key


class BlackMarketTourLoop1117RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Rows 0-170 posted as recorded; the policy before the arrival in Telmora."""
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURE, Path(scratch.name))
        cls.mismatches = []
        for row, supply in steps[:ARRIVAL_ROW]:
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            entry = recorded[row["row"]]
            if (key, policy.last_reason) != (entry["key"], entry["reason"]):
                cls.mismatches.append((row["row"], key, policy.last_reason))
            post(policy, board, entry["key"], before)
        cls.before_arrival = policy
        cls.recorded = recorded
        cls.steps = steps

    def policy(self):
        return copy.deepcopy(self.before_arrival)

    def test_the_tour_leg_replays_as_recorded(self):
        self.assertEqual(self.mismatches, [])
        for row in LEG_ROWS:
            self.assertEqual(self.recorded[row]["reason"], f"{bm_tour.TRAVEL_REASON}-{TELMORA}")
        self.assertEqual(self.recorded[ARRIVAL_ROW]["reason"], "fixedquest:q2-teleport")
        tour = bm_tour.record(self.before_arrival)
        self.assertEqual((tour.armed, tour.seen, tour.target), (True, [0], TELMORA))

    def test_the_arrival_in_telmora_is_not_sent_back(self):
        policy = self.policy()
        board = self.steps[ARRIVAL_ROW][1]()
        self.assertEqual(policy._effective_town_id(board), TELMORA)
        policy.choose_key(board)
        # Live: ("7", "fixedquest:q2-teleport"), the walk to the inn back to the Outpost.
        self.assertFalse(policy.last_reason.startswith("fixedquest:"), policy.last_reason)
        tour = bm_tour.record(policy)
        self.assertEqual((tour.arrived, tour.target, tour.closed), ([TELMORA], None, None))
        self.assertTrue(policy._cross_town_trip_holds_town(board))

    def test_a_tour_taken_back_does_not_pay_the_leg_again(self):
        policy = self.policy()
        # The arrival is decided (not posted: its walk to a Telmora shop never starts).
        policy.choose_key(self.steps[ARRIVAL_ROW][1]())
        back = self.steps[BACK_ROW][1]()
        self.assertEqual(policy._effective_town_id(back), 0)
        # Live: ("3mb", "town:cross-town-bm-tour:travel-1"), the next fare to Telmora.
        self.assertEqual(self.recorded[BACK_ROW]["reason"], f"{bm_tour.TRAVEL_REASON}-{TELMORA}")
        policy.choose_key(back)
        self.assertFalse(policy.last_reason.startswith(bm_tour.TRAVEL_REASON), policy.last_reason)
        tour = bm_tour.record(policy)
        self.assertEqual(tour.closed, f"left-before-seen-{TELMORA}")
        self.assertFalse(policy._cross_town_trip_holds_town(back))


if __name__ == "__main__":
    unittest.main()
