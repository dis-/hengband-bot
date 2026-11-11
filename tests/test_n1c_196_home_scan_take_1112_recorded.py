"""n1-c life-196 2026-11-12 00:44 town:blocked:equipment-home-unavailable.

Recorded: the town-arrival checkpoint of the incident capture and its journal
(tests/extract_n1c_196_home_scan_take_1112_fixture.py).  Every decision goes
through the public ``choose_key`` on the restored arrival policy; each key is
acknowledged as posted the way the CLI does (``RecordedVisit``).

The Magic-Eater (Lv24) spent two unsatisfied Home passes on an equipment
transaction whose deposit went missing (rows 7-18).  At the recall read the
spare *Identify* (me_powerful_activation._home_take_key, owner 2026-11-06)
filed the catalogue take of a ハルバード from Home and walked there (row 46);
the Home knowledge had been invalidated by the deposits, so the open page was
adopted as a scan (row 47, ``home:scan-complete-from-open-page``).  That page
was charged as Home's third unsatisfied pass: Home was blocked with the take
still filed, ``home_candidate_resolved`` stayed unmet and the visit waited
under ``town:blocked:equipment-home-unavailable`` (row 48 on) until the owner
retirement burst.

Fix: a scan page whose adopted catalogue hands a bound take to the outside
composer is that hand-off (``home:leave-for-pending-withdraw`` on a current
catalogue), not a failed stop pass; row 48 composes the take.

DECLARED: row 43 (a one-shot buy the replay's arbiter retires) is fed with
the recorded key, as ``RecordedVisit.decide`` does for any row it does not
reproduce; every other row 0-47 decides as recorded.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path

from hengbot.model import STORE_HOME
from tests.test_stops_1109_town_recorded import RecordedVisit

FIXTURES = Path(__file__).with_name("fixtures") / "home-scan-take-1112"
SCAN_ROW, STOP_ROW = 47, 48
DECLARED_ROWS = [43]


class HomeScanTakeVisit(RecordedVisit):
    fixtures = FIXTURES
    fixture = "h196"

    def test_recorded_rows(self):
        self.assertEqual(
            [self.journal[row]["reason"] for row in (46, SCAN_ROW, STOP_ROW)],
            ["shop:travel", "home:scan-complete-from-open-page",
             "town:blocked:equipment-home-unavailable"])

    def test_rows_before_the_stop_decide_as_recorded(self):
        self.assertEqual(self.replay_to(STOP_ROW), DECLARED_ROWS)

    def test_scan_page_hands_the_take_off_without_blocking_home(self):
        self.replay_to(SCAN_ROW)
        ledger = self.policy._town_visit_ledger
        self.assertEqual(ledger.unsatisfied_passes[STORE_HOME], 2)
        request = self.policy._home_errand.request
        self.assertEqual(request.purpose, "identification-catalog")
        board, key, reason = self.decide(SCAN_ROW)
        self.assertEqual((key, reason), ("\x1b", "home:scan-complete-from-open-page"))
        self.assertIn(request.signature,
                      {self.policy._item_signature(item) for item in board.store.items})
        # Before the fix: 3 passes, Home blocked under the visit bound.
        self.assertEqual(ledger.unsatisfied_passes[STORE_HOME], 2)
        self.assertNotIn(STORE_HOME, ledger.blocked_stores)

    def test_stop_row_composes_the_take(self):
        self.replay_to(STOP_ROW)
        _board, key, reason = self.decide(STOP_ROW)
        # Before the fix: ('9', 'town:blocked:equipment-home-unavailable').
        self.assertEqual(reason, "home-errand:atomic-withdraw:identification-catalog")
        self.assertTrue(key.startswith("5p"), key)


if __name__ == "__main__":
    unittest.main()
