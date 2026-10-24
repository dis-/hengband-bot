"""ROOT-FIX S2-c rest: rung #1's opening condition lives in its intended_terminal.

``_fixed_quest_prepare_return_required`` (and the quest-request retirement)
no longer guard the ``_fixed_quest_key#1`` call site; the rung's declared
terminal returns NOT_APPLICABLE when it does not apply, and the entry skips
the producer for that answer on and off town (distinct from None, "no
terminal, not judged", which runs the producer).

Boards: the CONSTRUCTED goldburn seam (row 3512, Telmora; see
test_goldburn_shopping_constructed), and the same row with the town flag
cleared (DECLARED CONSTRUCTED off-town board).  The predicate's answer and
the target choice are DECLARED CONSTRUCTED patches.  The recorded town-3
prepare-return walk (fixtures/quest-prepare-return-town3-walk-stage2) runs
the real predicate through ``choose_key`` and only counts who asks it.
"""

import tests  # noqa: F401

import gzip
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot import town_terminal
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import NOT_APPLICABLE, TerminalRef
from test_goldburn_shopping_constructed import board
from test_quest_travel_progress import QuestTravelFixtureMixin


def _entry(policy, snap, rung):
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    calls = []
    key = policy._town_producer_entry(rung, lambda: calls.append("ran") or "7")
    return key, calls


class RungOneApplicabilityTest(unittest.TestCase):
    def run_rung_one(self, *, required, snap=None, retired=False):
        policy = HengbotPolicy()
        if retired:
            policy._town_turn_arbiter._retired["quest-request"] = "constructed"
        snap = board() if snap is None else snap
        with patch.object(HengbotPolicy, "_fixed_quest_prepare_return_required",
                          return_value=required) as predicate, \
                patch.object(HengbotPolicy, "_fixed_quest_target", return_value=None):
            terminal = town_terminal.rung_terminal(policy, "_fixed_quest_key#1", snap)
            return terminal, _entry(policy, snap, "_fixed_quest_key#1"), predicate.call_count

    def test_not_required_the_entry_skips_the_producer(self):
        terminal, (key, calls), _count = self.run_rung_one(required=False)
        self.assertEqual(terminal, NOT_APPLICABLE)
        self.assertEqual((key, calls), (None, []))

    def test_control_required_the_producer_runs(self):
        terminal, (key, calls), _count = self.run_rung_one(required=True)
        self.assertEqual(terminal, TerminalRef("quest-prepare-return", (1,)))
        self.assertEqual((key, calls), ("7", ["ran"]))

    def test_retired_quest_request_does_not_ask_the_predicate(self):
        terminal, (key, calls), count = self.run_rung_one(required=True, retired=True)
        self.assertEqual(terminal, NOT_APPLICABLE)
        self.assertEqual((key, calls, count), (None, [], 0))

    def test_off_town_the_rung_does_not_apply(self):
        off_town = replace(board(), town_flag=False)
        self.assertFalse(off_town.in_town)
        policy = HengbotPolicy()
        # The real predicate answers off town (no patch).
        self.assertEqual(town_terminal.rung_terminal(policy, "_fixed_quest_key#1", off_town),
                         NOT_APPLICABLE)
        self.assertEqual(_entry(policy, off_town, "_fixed_quest_key#1"), (None, []))

    def test_control_off_town_an_undeclared_terminal_passes_through(self):
        off_town = replace(board(), town_flag=False)
        policy = HengbotPolicy()
        self.assertIsNone(town_terminal.rung_terminal(policy, "_fixed_quest_key#2", off_town))
        self.assertEqual(_entry(policy, off_town, "_fixed_quest_key#2"), ("7", ["ran"]))

    def test_no_parallel_predicate_is_left(self):
        self.assertEqual(town_terminal.PARALLEL_PREDICATES_S1, frozenset())


class RungOneAskedOnlyByItsTerminalTest(QuestTravelFixtureMixin, unittest.TestCase):
    """Recorded town-3 prepare-return walk (test_quest_prepare_return_stage2):
    the ladder asks the predicate only through rung #1's terminal, never
    beside the call site, and the walk is unchanged."""

    def test_predicate_is_asked_inside_the_terminal(self):
        path = (Path(__file__).resolve().parent / "fixtures"
                / "quest-prepare-return-town3-walk-stage2.jsonl.gz")
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        policy = self._policy()
        real = HengbotPolicy._fixed_quest_prepare_return_required
        callers = []

        def spy(self_, snapshot):
            callers.append(sys._getframe(1).f_code.co_name)
            return real(self_, snapshot)

        keys = []
        with patch.object(HengbotPolicy, "_fixed_quest_prepare_return_required", spy):
            for index, raw in enumerate(rows):
                snapshot = parse_snapshot(raw, self.monrace)
                if index == 0:
                    policy.prime(snapshot)
                key = policy.choose_key(snapshot)
                policy.confirm_key_posted(key)
                if raw["turn"] >= 2856703:
                    keys.append((str(key), key.reason))
        self.assertEqual(keys, [(step, "fixedquest:prepare-return")
                                for step in ("7", "8", "9", "9", "9")])
        self.assertIn("fixed_quest_return_intended_terminal", callers)
        self.assertNotIn("_decide", callers)


if __name__ == "__main__":
    unittest.main()
