"""explore-lit-floor-sweep-1102: the n1-a life-464 dark cave floor sweep.

n1-a life-464 (warrior Lv41, build bot-ec1f68398) at オークの洞窟 23階 (the
dungeon's maxDepth, recalled there by town:unsafe-recall-fallback) stopped
2026-11-02 19:18:34 with ``stall:floor-dwell:explore``.  On the recorded
boards (light radius 3, no hostile) every decision is ``explore`` and almost
every goal is the next cell of a row-by-row sweep: floor already seen inside
the player's own light, never stepped on, not a frontier.  The floor before
(the same level) took 18:39-19:16 and 6,024 stepped cells.

Root: _plan_explore_path_pass owed a visit to every unvisited remembered floor
cell, also to floor the owner decision 2026-10-23 (#101) 「探索済みとする」
counts as explored (seen inside the own light, ``_marked_t``).  Now such a cell
is not owed a visit (and a committed visit goal seen on the way is complete);
the unknown ground beyond it is reached as a frontier.

Fixture: tests/fixtures/explore-lit-floor-sweep-20261102.json.gz
(tests/extract_explore_lit_floor_sweep_1102_fixture.py).  Every decision is the
public ``choose_key``; its key goes through the production executor port
(test_me_nokey_1031_recorded.PostedKey).  The replay is open-loop: the next
recorded board follows the recorded move, so the memory holds only the
capture's last 53 boards (DECLARED: no earlier floor memory is seeded).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
from pathlib import Path

from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests import test_me_nokey_1031_recorded as nokey
from test_esp_threat_rest_recorded import EDIT
from test_floor_dwell_seen_floor_recorded import _Replay


FIXTURE = Path(__file__).with_name("fixtures") / "explore-lit-floor-sweep-20261102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)


def _explored_unowed(policy, board, cell):
    """Seen inside the own light, never stepped on and not a frontier."""
    return (
        (cell.y, cell.x) in policy._marked_t
        and policy._visit_counts[cell] == 0
        and not policy._is_remembered_frontier(board, cell)
    )


class ExploreLitFloorSweepRecordedTest(nokey.PostedKey):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.decisions = {row["turn"]: row for row in CASE["decisions"]}

    def test_recorded_boards_swept_the_lit_floor_cell_by_cell(self):
        self.assertEqual(len(CASE["boards"]), 53)
        rows = CASE["decisions"]
        self.assertEqual(len(rows), 52)
        self.assertEqual({(row["reason"], row["owner"]) for row in rows},
                         {("explore", "explore")})
        adjacent = 0
        for line in CASE["boards"]:
            raw = json.loads(line)
            row = self.decisions.get(raw["turn"])
            if row is None:
                continue
            here = Position(raw["player"]["y"], raw["player"]["x"])
            if here.distance_to(Position(*row["goal"])) == 1:
                adjacent += 1
        self.assertEqual(adjacent, 43)

    def test_explore_goals_skip_floor_seen_in_the_own_light(self):
        replay = _Replay(self, self.monrace)
        policy = replay.policy
        recorded_explored = 0
        for line in CASE["boards"]:
            board = replay.board(line)
            key = str(policy.choose_key(board))
            self.assertEqual(policy.last_reason, "explore", board.turn)
            self.post(policy, json.loads(line), key)
            policy.confirm_key_posted(key)
            identity = policy._explore_goal_identity
            self.assertIsNotNone(identity, board.turn)
            # The replayed policy never heads for explored floor ...
            self.assertFalse(
                _explored_unowed(policy, board, identity.position),
                (board.turn, identity),
            )
            row = self.decisions.get(board.turn)
            if row is not None and _explored_unowed(
                policy, board, Position(*row["goal"])
            ):
                recorded_explored += 1
        # ... where the recorded run's goals were explored floor.
        self.assertEqual(recorded_explored, 42)


if __name__ == "__main__":
    import unittest
    unittest.main()
