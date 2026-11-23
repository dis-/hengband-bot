"""The walk to the last-seen cell never steps back onto a cell it left (n1-b life-416, 2026-11-24).

Owner 2026-11-13 (verbatim) 「交互に逆へ歩くループは根から防ぐ」.  n1-b life-416 on Angband 100F
(the Serpent of Chaos, last seen at (10,92)), 2026-11-24 04:34:47-59, seq 4979-4987 of the 04:23
run, owner-halt loop-detected: at (10,27) the frontier walk (``_approach_key``'s route to the
nearest frontier nearer the cell, (13,55), 34 edges) stepped '1' to (11,26); there, under that
board's walk vetoes, no route was drawn and the line (``_line_key``, a step only nearer) stepped
'9' back to (10,27), eight times over.

Fixture finale-100f-pingpong-n1b-416-1124: every player_turn board of that 100F floor, turns
4775263-4778564 (1507 boards; a row's ``_same`` fields equal the previous row's).  The whole floor
is replayed: the frontier at (13,55) is reachable only in the map the floor's earlier boards built.
tests/support/finale_416.py: DECLARED RECONSTRUCTED device lists and expedition mark.
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

LEFT = 4778547    # the recorded board at (10,27) that stepped '1' to (11,26)
END = 4778564


class FinaleApproachNoReversalRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        rows = finale_416.drive(
            finale_416.boards("finale-100f-pingpong-n1b-416-1124.jsonl.gz"), monrace)
        cls.rows = [row for row in rows if LEFT - 10 <= row[0] <= END]

    def test_the_walk_does_not_step_back_to_the_cell_it_came_from(self):
        # (11,26): the recorded run came here from (10,27) on every second board.
        back = [row for row in self.rows if row[0] > LEFT and row[1] == (11, 26)
                and row[3].startswith("angband-finale:approach") and row[2] == "9"]
        self.assertEqual(back, [], self.rows)

    def test_no_livelock_and_the_cell_is_kept(self):
        self.assertEqual([row for row in self.rows if row[3].startswith("livelock")], [],
                         self.rows)
        self.assertTrue(all(row[5] == (10, 92) for row in self.rows if row[0] >= LEFT),
                        self.rows)


if __name__ == "__main__":
    unittest.main()
