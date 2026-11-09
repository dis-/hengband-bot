"""The viewing bots' town stops of 2026-11-09 after 08:00 (town-stops-1109b).

Recorded: the town-arrival checkpoints of the incident captures and their
journals (tests/extract_town_stops_1109b_fixtures.py).  Every decision goes
through the public ``choose_key`` on the restored arrival policy; each key is
acknowledged as posted the way the CLI does (``confirm_key_posted`` and the
staged prompt chain), as tests/replay_town_arrival.py replays a visit
(``RecordedVisit`` of tests/test_stops_1109_town_recorded.py).

DECLARED for every replay: a row whose recorded decision the replay does not
reproduce is fed with the recorded key posted (the recorded boards follow);
the pins name the rows they assert.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from unittest import mock

from hengbot import equipment_optimizer
from hengbot.model import STORE_HOME
from tests.test_stops_1109_town_recorded import RecordedVisit

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1109b"


class Visit(RecordedVisit):
    fixtures = FIXTURES


class JunkSweepTakeAtEntranceTest(Visit):
    """n1-a life-497 2026-11-09 08:46 town:blocked:owner-retired-burst.

    The Home junk sweep chose the shelf's 切れ味のダガー for sale (relief mode
    sale, its Home errand filed) and left Home for the entrance's atomic take
    (row 16, home:junk-sweep-withdraw).  On the outside board the town-item
    processing took the relief's pending Home item for a failed
    identification withdrawal and deferred it, and the rebuilt errand plan
    put the Magic shop first (row 17, shop:approach '&'); in that store the
    sweep left again for Home, and Home -> Magic -> Home -> Alchemist ...
    went on until the owner retirements (rows 16-31 of the record).

    Fix: the relief's filed take keeps Home first in the plan, as every
    queued Home take does (``_next_required_store_type``), and is not an
    identification withdrawal to the town-item processing.

    DECLARED WALL: the record predates C (a611ad3296, owner 2026-11-09
    「Q34 の武器は未鑑定で握らない」); with it the unidentified Q34 weapons wait
    for identification and row 6 takes one of them out of Home instead of the
    recorded take, so the visit never reaches the sweep.  C's tval set is
    emptied for the whole replay; the relief, the plan and the
    identification processing under test are untouched.
    """

    fixture = "i497"

    def setUp(self):
        super().setUp()
        wall = mock.patch.object(equipment_optimizer, "Q34_WIELD_IDENTIFY_FIRST_TVALS", frozenset())
        wall.start()
        self.addCleanup(wall.stop)

    def test_recorded_rows_replay_to_the_sweep_take(self):
        self.assertEqual([self.journal[row]["reason"] for row in (15, 16, 17)], [
            "shop:travel", "home:junk-sweep-withdraw", "shop:approach"])
        self.assertEqual(self.journal[17]["key"], "\x1b`n&.")
        self.assertEqual(self.replay_to(17), [])
        relief = self.policy._home_full_relief
        self.assertTrue(relief["sweep"])
        self.assertEqual(relief["mode"], "sale")
        self.assertTrue(self.policy._home_full_relief_take_filed())

    def test_the_sweep_take_runs_at_the_home_entrance(self):
        self.replay_to(17)
        _board, key, reason = self.decide(17)
        self.assertEqual(reason, "home-errand:atomic-withdraw:full-home-sale")
        self.assertTrue(key.startswith("5"), key)
        self.assertEqual(self.policy._shopping_approach_store_type, STORE_HOME)

    def test_the_sweep_take_is_no_failed_identification_withdrawal(self):
        self.replay_to(17)
        dagger = self.policy._home_full_relief["sale"][0]
        self.assertEqual(self.policy._home_pending_item, dagger)
        self.decide(17)
        self.assertNotIn(dagger, self.policy._deferred_home_items)


if __name__ == "__main__":
    unittest.main()
