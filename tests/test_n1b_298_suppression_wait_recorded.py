"""n1-b life-298 2026-11-02 23:46 town:blocked:departure-unsatisfiable.

The optimizer had selected the Home helm 光の陣笠 [4,+8] {Q34} (known, not
fully known, so it might carry random teleport) into the warrior's loadout,
which held departure under pending-random-teleport-suppression until it was
withdrawn and inscribed.  Its Home withdrawal was lost at decision 2731
(home:leave-for-pending-withdraw) and the helm was deferred for the visit
from decision 2732 on, so no producer could act on it; the relax for an
unactionable suppression ("random-teleport-suppression-unactionable-current-
loadout") still required the worn loadout to be confirmed for the optimizer
inputs, and the inputs that selected the helm had no confirmation.  Every
decision until 2773 failed equipment_departure_ready and the visit stopped.

Owner 2026-11-03 (answer): 「鑑定待ちでも止めない」 / 「鑑定できない訪問では
取り出さない」 -- with that the only blocker, the visit departs on the worn
loadout.  Pinned through the public forced visit departure (the town end's
and the CLI's entry) on the recorded stop board; its key goes through the
production executor.
Fixture: tests/extract_n1b_298_suppression_wait_fixture.py.
DECLARED CONSTRUCTED: the captures keep no C-screen calibration, so the
optimizer preparation is constructed: the worn loadout with the helm on its empty
head slot, the one blocker the recorded rows show.  DECLARED RECONSTRUCTED: the
helm's visit deferral (the rows' deferred_home_item_signatures).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from hengbot.equipment_optimizer import SLOT_HEAD, Loadout, current_loadout
from hengbot.warrior_optimization import WarriorOptimizationPreparation
from tests import test_me_nokey_1031_recorded as _test_me_nokey_1031_recorded
import test_hourly_0700_1102_recorded as _test_hourly_0700_1102_recorded


FIXTURE = Path(__file__).with_name("fixtures") / "suppression-wait-n1b-298-1102.json.gz"
HELM = ("光の陣笠 [4,+8] {Q34}", 32, 4)
BLOCKER = "pending-random-teleport-suppression"


def _case():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class SuppressionWaitDepartsTest(_test_hourly_0700_1102_recorded.RecordedTownPolicy, _test_me_nokey_1031_recorded.PostedKey):
    @classmethod
    def setUpClass(cls):
        cls.case = _case()

    def policy(self):
        raw = self.case["board"]
        policy = self.primed(raw, self.case["home"]["knowledge"]["items"], self.case["skill"])
        board = self.board(policy, raw)
        catalog = policy._equipment_catalog.items
        (helm,) = [owned for owned in catalog
                   if owned.origin == "home" and policy._item_signature(owned.item) == HELM]
        worn = current_loadout(catalog)
        # The head slot is empty on the board; the helm fills it.
        selected = Loadout(tuple(sorted((*worn.slots, (SLOT_HEAD, helm)),
                                        key=lambda entry: entry[0])), worn.hand_mode)
        preparation = WarriorOptimizationPreparation(
            current=worn,
            result=SimpleNamespace(best=SimpleNamespace(loadout=selected),
                                   incomplete_item_ids=frozenset()),
            transaction=None, blockers=(BLOCKER,))
        policy._prepare_equipment_optimization = lambda snapshot: preparation
        policy._defer_home_item(HELM, "unobserved-home-withdrawal")
        return policy, board, raw

    def test_recorded_rows(self):
        rows = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual(rows[2731]["reason"], "home:leave-for-pending-withdraw")
        self.assertIn(list(HELM), rows[2732]["deferred"])
        stop = rows[2773]
        self.assertEqual((stop["reason"], stop["key"]), ("town:blocked:departure-unsatisfiable", "7"))
        self.assertEqual((stop["blockers"], stop["failed"]), ([BLOCKER], ["equipment_departure_ready"]))
        self.assertFalse(any("陣笠" in item["name"] for item in self.case["board"]["equipment"]))

    def test_unwithdrawable_home_suppression_departs_on_the_worn_loadout(self):
        policy, board, raw = self.policy()
        self.assertTrue(policy._equipment_departure_ready(board, commit=False))
        key = policy.force_visit_departure(board, "no-owner-answered")
        # Recorded: '7' town:blocked:departure-unsatisfiable (a stop).  The
        # forced departure commits and walks to the entrance (no recall
        # destination for this depth): the committed-departure walk.
        self.assertEqual(policy._visit_departure_committed, "no-owner-answered")
        self.assertEqual((key, policy.last_reason), ("7", "town:blocked:repetition"))
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
