"""Walks are not counted against a town stage's deadline (owner 2026-11-14 「歩きは数えない」).

Recorded: n1-a life-522 (2026-11-14 08:34:53, Lv36) and n1-b life-396 (11:02:17, Lv8)
stopped at town:blocked:stage-deadline:equipment.  Their town-arrival checkpoints, journal
rows and sidecar files (tests/extract_stage_deadline_walk_1114_fixture.py) replay through
the public choose_key with the recorded keys posted.  Every row before the stop decides as
recorded; on the stop row the equipment stage, whose count had been filled by walks toward
Home (equipment-transaction:approach-home, travel-home) and toward a town monster
(town:kill-mob-approach), takes its real next action instead.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import town_visit_plan
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures") / "stage-deadline-walk-1114"
STOP = "town:blocked:stage-deadline:equipment"


class StageDeadlineWalk1114RecordedTest(unittest.TestCase):
    def replay(self, name):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURES / name, Path(scratch.name))
        decided = []
        for index, (row, supply) in enumerate(steps):
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(supply())
            decided.append((key, policy.last_reason))
            if index == len(steps) - 1:
                break
            self.assertEqual(decided[-1], (row["key"], row["reason"]), len(decided) - 1)
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        self.assertEqual(steps[-1][0]["reason"], STOP)
        walks = sum(town_visit_plan.is_walking(row["key"], row["reason"]) for row, _ in steps)
        # The stage trace keeps every equipment decision (the old deadline's
        # count, walks included); the deadline counts the operations only,
        # since the stage last completed an observed unit of its work
        # (2026-11-15, town_visit_plan.note_observed_progress; the visits'
        # operations without that restart were 5 and 8).
        traced = sum(segment[3] for segment in policy._town_visit.plan_segments
                     if segment[0] == "equipment")
        operations = policy._town_visit.stage_decisions.get("equipment", 0)
        return policy, decided[-1], walks, traced, operations

    def test_n1a_522_walks_to_home_and_enters(self):
        _policy, last, walks, traced, operations = self.replay("n1a522")
        self.assertGreaterEqual(walks, 32)
        self.assertEqual(last, ("5", "equipment-transaction:travel-home:await-entry"))
        self.assertGreaterEqual(traced, 42)
        self.assertEqual(operations, 3)

    def test_n1b_396_equips_instead_of_stopping(self):
        _policy, last, _walks, traced, operations = self.replay("n1b396")
        self.assertEqual(last, ("win", "equipment-transaction:equip"))
        self.assertGreaterEqual(traced, 42)
        self.assertEqual(operations, 1)


if __name__ == "__main__":
    unittest.main()
