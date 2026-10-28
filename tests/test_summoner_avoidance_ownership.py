"""Summoner veto withdrawal must preserve the other navigation owners."""

import tests  # noqa: F401
import unittest
from unittest.mock import patch

from hengbot.model import Position, Snapshot
from hengbot.policy import HengbotPolicy
from tests import policy_fixtures as fixtures


class SummonerAvoidanceOwnershipTest(unittest.TestCase):
    def test_release_preserves_overlapping_owners_with_or_without_supplies(self):
        board = Snapshot(fixtures.player(10, 10), {}, [])
        warning, engagement, paralyzer, summoner, unrelated = (
            Position(10, x) for x in range(11, 16)
        )
        for exhausted in (False, True):
            with self.subTest(exhausted=exhausted):
                policy = HengbotPolicy()
                policy._warning_refused_cells = {warning}
                policy._engagement_owned_avoid_cells = {engagement}
                policy._paralyzer_avoid_cells = {paralyzer}
                policy._engagement_avoid_cells = {
                    warning, engagement, paralyzer, summoner, unrelated,
                }
                with patch.object(policy, "_warning_supplies_exhausted", return_value=exhausted):
                    policy._refresh_warning_avoidance(
                        board, released_cells={warning, engagement, paralyzer, summoner},
                    )
                    self.assertEqual(policy._engagement_avoid_cells,
                                     {warning, engagement, paralyzer, unrelated})
                    self.assertEqual(policy._warning_refused_cells, {warning})
                    # Supply policy belongs to the ordinary refresh, not to
                    # the summoner relinquishing its own overlapping veto.
                    policy._refresh_warning_avoidance(board)
                    self.assertEqual(warning in policy._engagement_avoid_cells, not exhausted)

    def test_release_with_no_warning_latch_still_withdraws_summoner_veto(self):
        policy = HengbotPolicy()
        cell = Position(10, 11)
        policy._engagement_avoid_cells = {cell}
        board = Snapshot(fixtures.player(10, 10), {}, [])
        policy._refresh_warning_avoidance(board, released_cells={cell})
        self.assertEqual(policy._engagement_avoid_cells, set())


if __name__ == "__main__":
    unittest.main()
