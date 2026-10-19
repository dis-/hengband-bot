"""Every movement key into a cell answers one question through one predicate:
``_step_toward`` (issue #83, predicate audit question 8).

#75 routed the no-wait flee step through ``_step_toward``.  Two producers
still posted a bare ``_direction_key`` into cells that may be rubble (the
game refuses a plain step into rubble with "岩石が行く手をはばんでいる。"):

* ``_forbid_wait_while_damaged`` -> ``no-wait:least-visited``;
* ``_low_hp_no_kit_hit_key`` (an unseen ranged attacker) -> ``no-wait:flee``
  to an uncovered neighbour, toward the attacker, or along the cover route.

Boards: the recorded #75 board (tests/fixtures/flee-into-rubble-20261019,
row 0: turn 3407514, player (12,38), rubble north at (11,38)).

DECLARED CONSTRUCTED (all boards): the ~f skill-exp cache and the tried
quest speed potion (as in test_flee_into_rubble_recorded); an observed hit
(``_took_damage``) and the WAIT the rewrite receives; and per test:
* least-visited: both 蛇人間 removed (the competing flee owner), the three
  floor neighbours south already visited once;
* unseen, uncovered neighbour: no monster in view, the message of an
  unseen caster;
* unseen, cover route: as above, with the three squares north of the rubble
  (10,37..39) turned into floor, so the rubble itself is exposed and the
  nearest cover lies behind it;
* unseen, toward the attacker: the rubble north becomes wall, the floor
  square south (13,38) becomes the recorded rubble, and one 蛇人間 stands
  at (16,38) and names the spell; no square is out of its line of fire
  nearer than the attacker.
Controls replace the rubble by the floor square the player stands on.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "flee-into-rubble-20261019.jsonl.gz"
SHA256 = "8e7da7da8d97524032d1e38f3b0ec1231f8289f448fd3a77b7a43fa84a0a5301"
HERE = Position(12, 38)
NORTH = Position(11, 38)
SOUTH = Position(13, 38)
UNSEEN_CAST = "何かが魔力の矢の呪文を唱えた。"


class StepKeyUnifyRubbleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.line = gzip.decompress(data).decode("utf-8").splitlines()[0]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)
        self.policy._fixed_quest_speed_attempted = True

    def _board(self):
        _decoded, snapshots = _consume_response_sequence(
            [self.line], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        board = snapshots[-1]
        self.policy._skill_exp_cache = (
            0, 0, board.player.level, self.policy._town_visit_epoch
        )
        self.assertEqual(board.turn, 3407514)
        self.assertEqual(board.player.position, HERE)
        self.assertTrue(board.grid_at(NORTH).is_rubble)
        self.assertFalse(board.grid_at(NORTH).passable)
        return board

    @staticmethod
    def _with_grids(board, **cells):
        grids = dict(board.grids)
        for position, source in cells.values():
            grids[position] = replace(board.grids[source], position=position)
        return replace(board, grids=grids)

    # ------------------------------------------------ no-wait:least-visited
    def _least_visited(self, board):
        board = replace(board, visible_monsters=[])
        policy = self.policy
        policy._build_grid_index(board)
        for x in (37, 38, 39):
            policy._visit_counts[Position(13, x)] += 1
        policy._took_damage = True
        policy.last_reason = "summoner:hold-choke"
        return (
            policy._forbid_wait_while_damaged(board, "5"),
            policy.last_reason,
        )

    def test_least_visited_step_tunnels_the_rubble(self):
        self.assertEqual(
            self._least_visited(self._board()), ("T8", "no-wait:least-visited")
        )

    def test_control_least_visited_open_floor_is_unchanged(self):
        board = self._with_grids(self._board(), north=(NORTH, HERE))
        self.assertEqual(
            self._least_visited(board), ("8", "no-wait:least-visited")
        )

    # ------------------------------------------ unseen attack: no-wait:flee
    def _unseen(self, board, hostiles=()):
        if not hostiles:
            board = replace(board, visible_monsters=[], messages=[UNSEEN_CAST])
        policy = self.policy
        policy._build_grid_index(board)
        policy._took_damage = True
        return (
            policy._low_hp_no_kit_hit_key(board, list(hostiles)),
            policy.last_reason,
        )

    def test_unseen_uncovered_neighbour_tunnels_the_rubble(self):
        self.assertEqual(self._unseen(self._board()), ("T8", "no-wait:flee"))

    def test_control_unseen_uncovered_open_floor_is_unchanged(self):
        board = self._with_grids(self._board(), north=(NORTH, HERE))
        self.assertEqual(self._unseen(board), ("8", "no-wait:flee"))

    def _cover_board(self, board):
        return self._with_grids(
            board,
            a=(Position(10, 37), HERE),
            b=(Position(10, 38), HERE),
            c=(Position(10, 39), HERE),
        )

    def test_unseen_cover_route_tunnels_the_rubble(self):
        board = self._cover_board(self._board())
        policy = self.policy
        policy._build_grid_index(board)
        # The rubble itself is exposed: the cover lies behind it.
        self.assertGreater(policy._open_neighbor_count(board, NORTH), 2)
        self.assertEqual(self._unseen(board), ("T8", "no-wait:flee"))

    def test_control_unseen_cover_route_open_floor_is_unchanged(self):
        board = self._cover_board(self._board())
        board = self._with_grids(board, north=(NORTH, HERE))
        self.assertEqual(self._unseen(board), ("8", "no-wait:flee"))

    def _attacker_board(self, board, south_from):
        recorded = board
        board = self._with_grids(
            board, north=(NORTH, Position(11, 37)), south=(SOUTH, south_from)
        )
        shooter = replace(recorded.visible_monsters[0], position=Position(16, 38))
        return (
            replace(
                board,
                visible_monsters=[shooter],
                messages=[shooter.name + "が魔力の矢の呪文を唱えた。"],
            ),
            shooter,
        )

    def test_unseen_step_toward_the_attacker_tunnels_the_rubble(self):
        board, shooter = self._attacker_board(self._board(), NORTH)
        self.assertTrue(board.grid_at(SOUTH).is_rubble)
        self.assertEqual(
            self._unseen(board, [shooter]), ("T2", "no-wait:flee")
        )

    def test_control_unseen_step_toward_the_attacker_open_floor(self):
        board, shooter = self._attacker_board(self._board(), HERE)
        self.assertEqual(
            self._unseen(board, [shooter]), ("2", "no-wait:flee")
        )


if __name__ == "__main__":
    unittest.main()
