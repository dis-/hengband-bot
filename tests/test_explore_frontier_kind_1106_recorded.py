"""explore-osc-1106: the n1-b life-323 corridor walk back and forth (Orc cave 23F).

n1-b life-323 (Magic-Eater Lv34, HP 504/504, build bot-038a35897) on Orc cave
23F (not a quest floor), 2026-11-06 07:20-07:22: ``explore`` stepped
(22,92)/(23,92) and (21,94)/(22,94) back and forth, eight searches, a
breakout, then back (cells (22,92) and (23,92) 42 times each).

Root: _explore_step labelled the planner's goal a VISIT goal whenever it was
never stepped on, but the planner had reached it as a frontier: since #101
(owner 2026-10-23 「探索済みとする」) floor seen inside the own light is not owed a
visit.  A VISIT goal on such a cell is complete on the next board, so every
step planned afresh and the visit penalty of the cell just left flipped the
nearest goal.  Now one predicate, ``_explore_visit_owed``, answers "is this
cell owed a visit" for the planner, the goal's kind and the goal's completion.

Fixture: tests/fixtures/explore-frontier-kind-20261106.json.gz
(tests/extract_explore_frontier_kind_1106_fixture.py): the recorded boards of
turns 2861370-2861436 and their decision rows.  Every decision is the public
``choose_key``; its key goes through the production executor port.  The replay
is open-loop: the next recorded board follows the recorded move, and the
policy remembers only these boards (DECLARED: no earlier floor memory).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import ast
import gzip
import json
from pathlib import Path

from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ExplorationGoalKind
from tests import test_me_nokey_1031_recorded as nokey
from tests.support.recorded import EDIT
from test_floor_dwell_seen_floor_recorded import _Replay


FIXTURE = Path(__file__).with_name("fixtures") / "explore-frontier-kind-20261106.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8", errors="surrogateescape") as _stream:
    CASE = json.load(_stream)
ALTERNATION = (2861413, 2861416, 2861422, 2861426, 2861432, 2861436)
SOURCE = Path(__file__).resolve().parents[1] / "src" / "hengbot"


class ExploreFrontierKindRecordedTest(nokey.PostedKey):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.decisions = {row["turn"]: row for row in CASE["decisions"]}

    def test_recorded_rows_alternate_between_two_cells(self):
        self.assertEqual(len(CASE["boards"]), 15)
        rows = [self.decisions[turn] for turn in ALTERNATION]
        self.assertEqual([(row["position"], row["key"]) for row in rows],
                         [([22, 92], "2"), ([23, 92], "8")] * 3)
        self.assertEqual({row["reason"] for row in rows}, {"explore"})

    def test_the_explore_goal_holds_across_the_alternation(self):
        replay = _Replay(self, self.monrace)
        policy = replay.policy
        goals, keys = [], []
        for line in CASE["boards"]:
            board = replay.board(line)
            key = str(policy.choose_key(board))
            policy.confirm_key_posted(key)
            if board.turn not in ALTERNATION:
                continue
            self.assertEqual(policy.last_reason, "explore", board.turn)
            self.post(policy, json.loads(line), key)
            identity = policy._explore_goal_identity
            self.assertIsNotNone(identity, board.turn)
            # The planner reached it as a frontier: seen in the own light,
            # never stepped on, not owed a visit.
            self.assertEqual(identity.kind, ExplorationGoalKind.FRONTIER, board.turn)
            self.assertIn((identity.position.y, identity.position.x), policy._marked_t)
            self.assertFalse(policy._explore_visit_owed(identity.position))
            goals.append(identity.position)
            keys.append(key)
        # One goal and one direction on both cells: no new plan per step.
        self.assertEqual(set(goals), {Position(19, 94)})
        self.assertEqual(set(keys), {"8"})

    def test_every_visit_goal_label_asks_the_one_predicate(self):
        """A function that names ExplorationGoalKind.VISIT decides with
        _explore_visit_owed (the goal's kind and its completion)."""
        offenders = []
        for path in sorted(SOURCE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                names = {
                    sub.attr for sub in ast.walk(node) if isinstance(sub, ast.Attribute)
                }
                if "VISIT" in names and "_explore_visit_owed" not in names:
                    offenders.append(f"{path.name}:{node.name}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    import unittest
    unittest.main()
