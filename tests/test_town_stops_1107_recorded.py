"""Town stops of 2026-11-07 decided again from recorded mid-visit checkpoints.

Recorded substrate: tests/fixtures/town-stops-1107/ (written by
tests/extract_town_stops_1107_fixtures.py, which names the incident captures
and how the checkpoints were taken; ``replay.json`` lists the journal rows
the deployed code decided differently before the checkpoint).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import STORE_HOME
import town_stops_1107_fixture as fx


class TownStops1107RecordedTest(unittest.TestCase):

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def test_town_end_routes_home_for_a_filed_take_home_was_not_marked_tried_for(self):
        """n1-a life 492 09:42:14 town:blocked:unmet:home_candidate_resolved.

        The checkpoint is taken before the stop's board (journal row 55; the
        deployed code decided rows 0-54 as recorded).  The catalogue take of
        闇の陣笠 was filed, four *Identify* scrolls were carried and the
        visit's attempted set was {6: ...}: Home's latch from its pass had
        expired.  filed_take_route_key routed only a Home marked tried, so the
        town end stopped; the restarted process took the helmet on its first
        Home entry (decision 4, home-errand:atomic-withdraw:
        identification-catalog).
        """
        self.assertEqual(fx.replay_facts("home-take-route")["diverged"], [])
        policy = fx.restore("home-take-route", self.scratch)
        entry = fx.journal("home-take-route")[0]
        self.assertEqual(entry["reason"], "town:blocked:unmet:home_candidate_resolved")
        board = fx.board(policy, entry, self.scratch)
        request = policy._home_errand.request
        self.assertTrue(policy._home_errand.active)
        self.assertEqual(request.purpose, "identification-catalog")
        key = policy.choose_key(board)
        # The Home latch of this visit's pass (turn 5583538) expired on this
        # board's observation (turn 5583960), as the live log shows.
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)


if __name__ == "__main__":
    unittest.main()
