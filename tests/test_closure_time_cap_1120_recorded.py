"""The single-slot closure stops at its whole-search time cap (2026-11-20).

n1-c life-214's search needed nine closure passes and 41.7 s (each pass under
its own 25 s budget); the town decision watchdog is 90 s.  The closure now
gives each pass what is left of CLOSURE_TIME_CAP_SECONDS (30 s) and, when a
pass runs out, returns the last completed pass's result marked
``search_capped`` (n1-c 214: capped at 30.1 s after seven passes, the same
set as the uncapped 42.0 s search).

Recorded: n1-b life-411's town-arrival checkpoint and journal rows 0-1
(tests/extract_n1b_411_loadout_search_1120_fixture.py) with the cap lowered
so that the third pass runs out.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

from hengbot import warrior_optimization
from hengbot.equipment_optimizer import Loadout, OptimizationResult
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-loadout-search-1120"


def result(best, *, timed_out=False):
    return OptimizationResult(
        best=best, alternatives=(), pareto_frontier=(), dominated_item_ids=frozenset(),
        combinations_considered=0, combinations_evaluated=0, invalid_combinations=0,
        elapsed_seconds=0.0, timed_out=timed_out, incomplete_item_ids=frozenset())


def owned(name):
    return SimpleNamespace(id=name, flags=frozenset())


class ClosureTimeCapTest(unittest.TestCase):
    def test_a_pass_that_runs_out_returns_the_previous_pass_capped(self):
        worn = Loadout((("light", owned("a")),), "empty")
        moved = Loadout((("light", owned("b")),), "empty")
        passes = iter([result(SimpleNamespace(loadout=moved)), result(None, timed_out=True)])
        capped = warrior_optimization.optimize_single_slot_closure(
            worn, lambda seed: (seed, moved), lambda candidates: next(passes))
        self.assertTrue(capped.search_capped)
        self.assertFalse(capped.timed_out)
        self.assertIs(capped.best.loadout, moved)

    def test_a_first_pass_that_runs_out_fails_closed(self):
        worn = Loadout((("light", owned("a")),), "empty")
        out = warrior_optimization.optimize_single_slot_closure(
            worn, lambda seed: (seed,), lambda candidates: result(None, timed_out=True))
        self.assertTrue(out.timed_out)
        self.assertFalse(out.search_capped)


class N1b411ClosureTimeCapRecordedTest(unittest.TestCase):
    def test_the_capped_search_keeps_its_last_pass_and_reports_it(self):
        with TemporaryDirectory() as raw:
            policy, _recorded, steps = load(FIXTURE, Path(raw))
            report = Path(raw) / "loadout-report.jsonl"
            policy._loadout_report_path = report
            real = warrior_optimization.optimize_single_slot_closure
            passes = []

            def counting(current, neighbours, optimize):
                def counted(candidates):
                    passes.append(len(candidates))
                    if len(passes) == 3:
                        # The third pass finds the cap spent.
                        with mock.patch.object(warrior_optimization, "monotonic",
                                               lambda: float("inf")):
                            return optimize(candidates)
                    return optimize(candidates)
                return real(current, neighbours, counted)

            with mock.patch.object(warrior_optimization, "optimize_single_slot_closure", counting):
                board = steps[0][1]()
                key = policy.choose_key(board)
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
                policy.choose_key(steps[1][1]())
            preparation = policy._equipment_optimization_preparation
            self.assertEqual(len(passes), 3)
            self.assertTrue(preparation.result.search_capped)
            self.assertIsNotNone(preparation.result.best)
            self.assertNotIn("optimization-timeout", preparation.blockers)
            records = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(records[-1]["search_capped"])


if __name__ == "__main__":
    unittest.main()
