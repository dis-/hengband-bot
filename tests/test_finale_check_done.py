"""finale_prep ``check_done``: the check step's done-check on its own search's result, whatever the
search's duration (n1-c life-222 2026-11-26 07:46:59, tests/test_finale_check_1126_recorded.py).

The step ends on the search that chose a set (``ammo``, or a named stop when the set misses a
condition), stops as ``check:no-set`` when a search over the whole owned gear chose none, and
waits when the optimizer refused the search (a blocker): never holds the swap after a finished
search.  The policy here holds only what ``check_done`` reads; the set's conditions
(``set_missing``) are the recorded test's.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from types import SimpleNamespace
from unittest import mock

from hengbot import finale_prep


def _policy(step, feasibility):
    policy = SimpleNamespace(
        _decision_sequence=18,
        _home_errand=SimpleNamespace(request=None),
        _angband_finale_feasibility=feasibility,
    )
    held = finale_prep.Phase()
    held.step, held.since = step, 17
    setattr(policy, finale_prep.STATE, held)
    return policy, held


def _search(best, blockers=()):
    return SimpleNamespace(result=SimpleNamespace(best=best), blockers=blockers)


CHOSEN = SimpleNamespace(loadout=object(), metrics=object())


class CheckDoneTest(unittest.TestCase):
    def test_a_set_meeting_every_condition_ends_the_step(self):
        policy, held = _policy(finale_prep.CHECK, _search(CHOSEN))
        with mock.patch.object(finale_prep, "set_missing", return_value=[]):
            finale_prep.check_done(policy, snapshot=None)
        self.assertEqual(held.step, finale_prep.AMMO)
        self.assertFalse(finale_prep.holds_swap(policy))

    def test_a_set_missing_a_condition_stops_the_phase_by_name(self):
        policy, held = _policy(finale_prep.CHECK, _search(CHOSEN))
        with mock.patch.object(finale_prep, "set_missing", return_value=["resist_shard"]):
            finale_prep.check_done(policy, snapshot=None)
        self.assertEqual((held.step, held.stopped), (finale_prep.STOPPED, "check:resist_shard"))
        self.assertFalse(finale_prep.holds_swap(policy))

    def test_a_finished_search_with_no_set_stops_instead_of_holding_the_swap(self):
        policy, held = _policy(finale_prep.CHECK, _search(None))
        finale_prep.check_done(policy, snapshot=None)
        self.assertEqual((held.step, held.stopped), (finale_prep.STOPPED, "check:no-set"))
        self.assertFalse(finale_prep.holds_swap(policy))

    def test_a_refused_or_absent_search_waits(self):
        for feasibility in (None, _search(None, ("home-scan-incomplete",)),
                            SimpleNamespace(result=None, blockers=("calibration-required",))):
            policy, held = _policy(finale_prep.CHECK, feasibility)
            finale_prep.check_done(policy, snapshot=None)
            self.assertEqual(held.step, finale_prep.CHECK, feasibility)

    def test_other_steps_are_left_alone(self):
        for step in (finale_prep.IDLE, finale_prep.HOME, finale_prep.LOADOUT, finale_prep.SWAP):
            policy, held = _policy(step, _search(CHOSEN))
            with mock.patch.object(finale_prep, "set_missing", return_value=[]):
                finale_prep.check_done(policy, snapshot=None)
            self.assertEqual(held.step, step)


if __name__ == "__main__":
    unittest.main()
