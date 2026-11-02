"""The 2026-11-02 23:18 viewing-bot stops of n1-a life-466 (hourly-2300-1102).

Each class pins one root on its recorded board; facts the capture keeps
outside the board are marked DECLARED RECONSTRUCTED.
Fixture: tests/extract_hourly_2300_1102_fixtures.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from test_hourly_0700_1102_recorded import RecordedTownPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "hourly-2300-1102.json.gz"


def _cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class VanishedIdentificationCandidateTest(RecordedTownPolicy):
    """n1-a life-466 23:18:46 town:blocked:departure-unsatisfiable.

    At 5F (decision 5107) the warrior picked up an unknown robe; back in town
    (5129) the town-item owner made it the identification candidate and
    requested a normal Identify source.  Descending again (5137) the game
    destroyed the robe after its {壊れている} pseudo-feeling.  The request
    stayed latched with no item behind it: the Identify scroll bought at 6512
    had nothing to read on, and departure failed home_candidate_resolved and
    identification_need_clear for good, each latch's release waiting for the
    other.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["identify"]

    def test_vanished_candidate_releases_the_identify_request(self):
        case = self.case
        policy = self.primed(case["stop"], case["home"]["knowledge"]["items"], case["skill"])
        board = self.board(policy, case["stop"])
        robe = ("ローブ [2]", 36, 2)
        self.assertFalse(any(policy._item_signature(item) == robe
                             for item in (*board.inventory, *board.equipment,
                                          *policy._home_knowledge_items)))
        # DECLARED RECONSTRUCTED: the latches the life's decisions record
        # from 5129 to the stop (identification_need normal,
        # home_candidate_waiting true) with the robe as candidate.
        policy._identification_need = "normal"
        policy._identification_candidate = robe
        policy._home_candidate_waiting = True

        key = policy.choose_key(board)
        # Recorded: '5' town:blocked:departure-unsatisfiable.  Departure is
        # ready: the pre-recall character dump runs.
        self.assertEqual((key, policy.last_reason), ("Cf\ry\x1b\x1b", "town:character-dump"))
        self.assertIsNone(policy._identification_need)
        self.assertFalse(policy._home_candidate_waiting)
        self.assertEqual(policy._departure_block_state(board)["failed"], [])


if __name__ == "__main__":
    unittest.main()
