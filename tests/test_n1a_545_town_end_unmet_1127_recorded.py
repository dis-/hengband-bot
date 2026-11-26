"""Work worth finishing but not needed does not stop the town (n1-a life-545, MAINTAINABILITY.md 2).

Recorded (tests/extract_n1a_545_town_end_unmet_1127_fixture.py, ``n1a-545-town-end-unmet-1127``):
the town-arrival checkpoint of 2026-11-27 04:39:14 (Amberite Rogue CL24, an anti-magic shield worn).
Row 12 took a Home candidate for identification, rows 13-15 cast 鑑定 and the shield refused each
(「反魔法バリアが魔法を邪魔した！」), row 16 deposited the candidate back as weight overload, the visit
bought four Identify scrolls, and row 40 stopped under town:blocked:unmet:home_candidate_resolved:
the candidate was doable (identification_wait kept the wait as "an owner's defect") but Home's
passes were used up, so no owner walked there.  The identification leaves are OPTIONAL
(departure_leaf_classes): the town end departs and the candidate waits for a later visit.  Rows
before the one decided are replayed through the public ``choose_key`` and post the recorded key.

DECLARED CONSTRUCTED: ``test_without_the_optional_class_the_recorded_stop_returns`` empties the
OPTIONAL class to show the stop the fix removes.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import departure_leaf_classes
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-town-end-unmet-1127"
STOP_ROW = 40
STOP_REASON = "town:blocked:unmet:home_candidate_resolved"
WAIT_LEAVES = ["home_candidate_resolved", "identification_need_clear",
               "departure_identification_need_clear"]


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class TownEndUnmet545RecordedTest(unittest.TestCase):
    def replay(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, journal, steps = load(FIXTURE, Path(scratch.name))
        self.assertEqual(journal[STOP_ROW]["reason"], STOP_REASON)
        for recorded, supply in steps[:STOP_ROW]:
            key, reason = decide(policy, supply())
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), recorded["row"])
            post(policy, recorded["key"])
        return policy, steps[STOP_ROW][1]()

    def test_the_town_end_departs_and_records_the_waived_leaves(self):
        policy, board = self.replay()
        self.assertTrue(policy._home_candidate_waiting)
        self.assertEqual(policy._identification_need, "normal")
        key, reason = decide(policy, board)
        self.assertEqual((key, reason), ("rka", "town:repetition-depart:recall"))
        self.assertEqual(policy._visit_departure_committed, "top-up-adequate")
        self.assertEqual(policy.departure_block_state(board)["town_end_waived"], WAIT_LEAVES)
        # The candidate waits for a later visit (identification_wait.release).
        self.assertFalse(policy._home_candidate_waiting)

    def test_without_the_optional_class_the_recorded_stop_returns(self):
        policy, board = self.replay()
        with mock.patch.dict(departure_leaf_classes.OPTIONAL, clear=True):
            key, reason = decide(policy, board)
        self.assertEqual((key, reason), ("5", STOP_REASON))


if __name__ == "__main__":
    unittest.main()
