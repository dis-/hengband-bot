"""Recorded pin: the survival / kill ratio first changes the tour at index 2.

User decisions 2026-10-02: 「生存÷撃破の比で比べる」 and 「足切りも比に置き換える」
(the dangerous-field "survival >= 95% of the maximum" floor became the 1% band
on the ratio).  On the 2026-09-22 tour capture
(tests/fixtures/unaffordable-claim-tour-20260922.jsonl.gz) no loadout
survives 30 turns.  The worn ★更正せるセオデン王のビークド・アックス set survives 11.24 turns
at ratio 1.552 (DPS 85.9); the 殺戮の野太刀 (9d4) set survives 10.59 turns
(94.2%, below the old floor) at ratio 1.828 (DPS 107.3).  The ratio picks the
野太刀 set, so board 2 becomes the Home equipment trip instead of the live
shop travel.  The key differs from live, so the pin stops there (R4).
Before the ratio (main 03907edf) production already diverged at this board,
with 'tb' equipment-transaction:takeoff toward a セオデン set;
the replays stay on the recorded gear only through the wall below.

Ownership replays of this capture keep the recorded gear through
tests/recorded_loadout.py (old survival, old margin and the old floor).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import tempfile
import unittest
from pathlib import Path

from hengbot.cli import _consume_response_sequence

import test_unaffordable_claim_tour_recorded as tour

FIRST_CHANGED = 2
NODACHI = "殺戮の野太刀 (9d4) (+4,+6)"
THEODEN = "★更正せるセオデン王のビークド・アックス"


def _main_hand(loadout) -> str:
    return loadout.item_at("main_hand").item.name


class MarginRatioTourDivergenceRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tour.UnaffordableClaimTourRecordedTest.setUpClass()
        replay = tour.UnaffordableClaimTourRecordedTest
        cls.live = [tuple(row[:2]) for row in replay.boundaries["recorded"]]
        cls.rows = []
        with tempfile.TemporaryDirectory(prefix="ratio-tour-") as raw:
            directory = Path(raw)
            policy, monrace = tour._live_like_policy(directory)
            cursor = 0
            for index in range(FIRST_CHANGED + 1):
                count = replay.boundaries["input_rows"][index]
                segment = replay.lines[cursor:cursor + count]
                cursor += count
                _decoded, snapshots = _consume_response_sequence(
                    segment, policy, lambda _key: True, monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                snapshot = snapshots[-1]
                policy._experience_drain_known = tour._drain_unknown
                key = policy.choose_key(snapshot)
                key = policy.validate_read_key(snapshot, key)
                cls.rows.append((str(key), policy.last_reason))
                if index == FIRST_CHANGED:
                    cls.preparation = policy._equipment_optimization_preparation
                tour._recorded_process_capture(policy, snapshot)
                policy.confirm_key_posted(key)

    def test_decisions_before_the_divergence_match_live(self):
        for index in range(FIRST_CHANGED):
            self.assertEqual(self.rows[index], self.live[index], index)

    def test_first_divergence_is_the_home_trip_for_the_nodachi(self):
        self.assertEqual(self.live[FIRST_CHANGED], ("\x1b`n%.", "shop:travel"))
        self.assertEqual(self.rows[FIRST_CHANGED],
                         ("\x1b`n(.", "equipment-transaction:travel-home"))
        preparation = self.preparation
        self.assertEqual(preparation.blockers, ())
        best = preparation.result.best
        self.assertEqual(_main_hand(best.loadout), NODACHI)
        self.assertAlmostEqual(best.metrics.survival_turns, 10.594, places=3)
        self.assertAlmostEqual(best.metrics.combat_margin, 1.828, places=3)
        self.assertAlmostEqual(best.metrics.expected_dps, 107.3, places=1)
        # The ★更正せるセオデン王のビークド・アックス set the floor kept (the
        # pre-ratio production target at this board, reached by 'tb'
        # takeoff) is still evaluated, and loses on the ratio.
        theoden = [entry for entry in preparation.result.top_candidates
                   if _main_hand(entry.loadout).startswith(THEODEN)]
        self.assertTrue(theoden)
        self.assertAlmostEqual(theoden[0].metrics.survival_turns, 11.243, places=3)
        self.assertAlmostEqual(theoden[0].metrics.combat_margin, 1.552, places=3)
        self.assertAlmostEqual(theoden[0].metrics.expected_dps, 85.9, places=1)
        self.assertLess(best.metrics.survival_turns,
                        theoden[0].metrics.survival_turns * 0.95)


if __name__ == "__main__":
    unittest.main()
