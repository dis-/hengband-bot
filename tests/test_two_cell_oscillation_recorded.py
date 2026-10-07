"""Recorded pins: three two-cell alternations on Castle 20F (2026-10-02).

User report 2026-10-02: 「気になったのは4の件と、敵の眼の前で攻撃もせずに
うろうろしていたこと。」 -- "4の件" is the bot walking back and forth
between two cells.  Three recorded instances, one pin each:

(a) 13:03:46-48 (decisions 3580-3589): after eight searches at (31,15) the
    oscillation breakout's last rung, ``_least_visited_neighbor``, posted
    '8'/'2' between the corridor's dead end (30,15) and (31,15) until
    ``livelock:recall-escape``.  Its score ranked visit counts above "not
    straight back", and a dead-end square is always the least visited one;
    ``previous`` was ``_recent[-2]``, which after the searches was the
    current square itself.  Fix: "never straight back" (the last square
    stood on that is not this one) ranks above visits.
    SUBSTRATE WALL: no board of this window was retained (capture rings of
    13:12 start at turn 3644500; the live state log was truncated by the
    15:0x relaunch), so the pin rebuilds the walk bookkeeping from the
    recorded decision rows (position per decision, entry visits, 's'
    searches) and a corridor board whose floor is exactly the squares the
    player stood on in those rows; every other neighbour is wall (the
    recorded ``breakout:*`` reasons mean no reachable frontier remained).
(b) 13:12 (capture autorecover-20261002-131232-loop-detected): with the
    breeder latch armed, ``_breeder_breakthrough_escape_key`` owned every
    decision and walked frontier squares while non-breeding hostiles (腐った
    死体, later ブルー・ホラー) stood adjacent, never attacking them.  Fix: the
    latch is about the breeders; a non-breeding hostile adjacent to a
    non-afraid player yields the decision to the ordinary combat ladder
    (whose survival rules may still flee).
    Replay: a fresh policy fed boards 5610-5619 (warm-up, keys not asserted:
    the live process had earlier floor memory) is given the two latches the
    live log shows were armed -- ``_breeder_breakthrough_floor`` (live
    reasons ``breeder-breakthrough:*`` from 5620) and
    ``_emergency_return_active`` (live ``emergency:cure-critical`` 13:06:08,
    decision 4051, same process and floor, which is why the breakthrough's
    recall branch was skipped) -- DECLARED WALL.  It then reproduces every
    live (key, reason) of 5620-5646; 5647 is the first board with a
    non-breeder adjacent and the first divergence (R4): nothing later is
    asserted.
(c) 15:14-15:16 (capture autorecover-20261002-151537-loop-detected, a process
    that attached at 15:14:3x): ``summoner:retreat`` '3' from (23,115), where
    閾に棲む者 is in view at distance 18, then ``seek-loot`` '7' straight back
    from (24,116), where it is out of view.  Fix: the retreat persists the
    abandoned square as an engagement-avoid cell, the same navigation veto
    the flee / threat:reposition retreats already use.  The fresh process is
    replayed from its attach board (its own ``skill_exp`` row first); 1-2
    reproduce live; 3 is the first divergence (R4).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position, Snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import NEIGHBOR_OFFSETS, SEARCH_LIMIT

from policy_fixtures import grid, player
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "two-cell-oscillation-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "two-cell-oscillation-20261002.boundaries.json"
# Same character and day: the 11:51 process's skill_exp row (first line of the
# castle fixture) and calibration file, both committed with earlier pins.
CASTLE_FIXTURE = FIXTURES / "castle-top-floor-exit-20261002.jsonl.gz"
CALIBRATION = FIXTURES / "wild-ambush-20261002.character-calibration.json"
SHA256 = {
    FIXTURE: "d3ff57adf6a9956877613ffe8e646d1d272f1d5ff71438c6d9f3c74f2cef5e34",
    BOUNDARIES: "2a942188414fc1d5d75f314e1a3d8d0b82700a04b3a46d6b0d4b7f6fc213032f",
    CASTLE_FIXTURE: "a6469df8e139299e623602f9f389e4bbfe7458ffca5f1f7b7edf32c3637b6873",
    CALIBRATION: "a71a507ffe45da1e8ca3c32a59886b3be1c88c6f68b4c6f5d691ab51e0fb6ce5",
}
CASTLE_20F = (12, 20, 0)

A_BREAKOUT = 3580  # first least-visited step after the searches at (31,15)
A_LAST = 3589
DEAD_END = Position(30, 15)
CORRIDOR = Position(31, 15)

B_WARMUP_END = 5619
B_LATCH = 5620
B_COMMITTED_FRONTIER_DIVERGENCE = 5644
B_DIVERGENCE = 5647

C_RETREAT = 2
C_DIVERGENCE = 3
C_RETREAT_CELL = Position(23, 115)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _load():
    for path, digest in SHA256.items():
        assert _sha(path) == digest, path
    boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    fields = boundaries["recorded_fields"]

    def table(name):
        return {row[0]: dict(zip(fields, row)) for row in boundaries[name]}

    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream]
    lines = {
        role: [record["line"] for record in records if record["role"] == role]
        for role in ("b", "c")
    }
    return boundaries, table, lines


def _key(value) -> str:
    return str(value)


class LeastVisitedDeadEndRecordedTest(unittest.TestCase):
    """(a) the breakout's least-visited step must not bounce into the dead end."""

    @classmethod
    def setUpClass(cls):
        _boundaries, table, _lines = _load()
        cls.recorded = table("a_recorded")

    def _board(self, position: Position) -> Snapshot:
        floors = {
            Position(*row["position"]) for row in self.recorded.values()
        }
        grids = {cell: grid(cell.y, cell.x) for cell in floors}
        for cell in floors:
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(cell.y + dy, cell.x + dx)
                if neighbor not in grids:
                    grids[neighbor] = grid(neighbor.y, neighbor.x, passable=False)
        return Snapshot(
            player(position.y, position.x), grids, [],
            floor_key=CASTLE_20F, width=198, height=66,
        )

    def _policy_before(self, sequence: int) -> HengbotPolicy:
        """The walk bookkeeping of the recorded rows before ``sequence``.

        Mirrors ``_observe``: a visit on entering a square, one ``_recent``
        entry per decision, and the recorded searches per square.
        """
        policy = HengbotPolicy()
        policy._floor_key = CASTLE_20F
        last = None
        for number in range(min(self.recorded), sequence):
            row = self.recorded[number]
            here = Position(*row["position"])
            if here != last:
                policy._visit_counts[here] += 1
                last = here
            policy._recent.append(here)
            if row["key"] == "s":
                policy._search_counts[(here.y, here.x)] += 1
        policy._last_position = last
        return policy

    def test_recorded_rows_are_the_alternation(self):
        window = [
            (tuple(self.recorded[number]["position"]),
             self.recorded[number]["key"], self.recorded[number]["reason"])
            for number in range(A_BREAKOUT, A_LAST + 1)
        ]
        self.assertEqual(
            window,
            [((31, 15), "8", "breakout:least-visited"),
             ((30, 15), "2", "breakout:least-visited")] * 5,
        )
        self.assertEqual(
            [self.recorded[number]["key"] for number in range(A_BREAKOUT - 8, A_BREAKOUT)],
            ["s"] * SEARCH_LIMIT,
        )
        self.assertEqual(self.recorded[A_LAST + 1]["reason"], "livelock:recall-escape")
        self.assertEqual(
            {self.recorded[n]["visible_hostiles"] for n in range(A_BREAKOUT, A_LAST + 1)},
            {0},
        )

    def test_breakout_walks_on_instead_of_into_the_dead_end(self):
        policy = self._policy_before(A_BREAKOUT)
        board = self._board(CORRIDOR)
        # The dead end is the least visited neighbour on the recorded walk.
        self.assertLess(
            policy._visit_counts[DEAD_END], policy._visit_counts[Position(32, 15)]
        )
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "breakout:least-visited")
        self.assertNotEqual(key, self.recorded[A_BREAKOUT]["key"])
        self.assertEqual(key, "2")  # on to (32,15), away from the dead end

    def test_a_dead_end_still_steps_out(self):
        policy = self._policy_before(A_BREAKOUT + 1)
        # Recorded board of 3581: the player stands in the dead end; its only
        # walkable neighbour is the square it came from.
        policy._recent.append(DEAD_END)
        policy._last_position = DEAD_END
        policy._visit_counts[DEAD_END] += 1
        board = self._board(DEAD_END)
        policy._build_grid_index(board)
        self.assertEqual(policy._least_visited_neighbor(board), CORRIDOR)


class BreederBreakthroughAdjacentHostileRecordedTest(unittest.TestCase):
    """(b) a non-breeding adjacent hostile is fought, not walked past."""

    @classmethod
    def setUpClass(cls):
        boundaries, table, lines = _load()
        cls.recorded = table("b_recorded")
        cls.ends = {int(k): v for k, v in boundaries["b_board_end"].items()}
        cls.lines = lines["b"]
        with gzip.open(CASTLE_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.knowledge = json.loads(stream.readline())
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        self.policy._crossarea_fundraising_enforced = True  # live argv
        self.policy.consume_skill_knowledge(self.knowledge)  # declared wall
        self._fed = -1

    def _board(self, sequence):
        end = self.ends[sequence]
        rows = self.lines[self._fed + 1: end + 1]
        self._fed = end
        _decoded, snapshots = _consume_response_sequence(
            rows, self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        return snapshots[-1]

    def _replay_through(self, last):
        rows = {}
        board = None
        for sequence in range(min(self.ends), last + 1):
            board = self._board(sequence)
            if sequence == B_LATCH:
                # DECLARED WALL: both latches the live log shows armed.
                self.policy._breeder_breakthrough_floor = board.floor_key
                self.policy._emergency_return_active = True
            key = self.policy.choose_key(board)
            rows[sequence] = (_key(key), self.policy.last_reason)
            self.policy.confirm_key_posted(key)
        return rows, board

    def _live(self, sequence):
        return (self.recorded[sequence]["key"], self.recorded[sequence]["reason"])

    def test_recorded_window_is_the_incident(self):
        loop = [self._live(n) for n in range(5643, 5651)]
        self.assertEqual(
            loop,
            [("6", "breeder-breakthrough:seek-frontier"),
             ("4", "breeder-breakthrough:seek-frontier")] * 4,
        )
        self.assertTrue(all(
            self.recorded[n]["reason"].startswith("breeder-breakthrough:")
            for n in range(B_LATCH, 5699) if n not in {5654, 5658}
        ))
        self.assertEqual(
            [tuple(self.recorded[n]["position"]) for n in range(5693, 5699)],
            [(35, 70), (35, 71), (35, 72), (35, 71), (35, 72), (35, 71)],
        )

    def test_replay_reproduces_live_until_a_non_breeder_is_adjacent(self):
        rows, _board = self._replay_through(B_DIVERGENCE - 1)
        self.assertEqual(
            {n: rows[n] for n in range(B_LATCH, B_COMMITTED_FRONTIER_DIVERGENCE)},
            {n: self._live(n) for n in range(B_LATCH, B_COMMITTED_FRONTIER_DIVERGENCE)},
        )
        # Since 8adae98b, the breakthrough commits to the frontier at (35,69).
        # At board 5644 the replay is at (35,68), so it continues east ('6').
        # Live instead steps west ('4'), then alternates east at 5645 and west
        # at 5646: the exact backtracking the committed-frontier change prevents.
        self.assertEqual(
            rows[B_COMMITTED_FRONTIER_DIVERGENCE],
            ("6", "breeder-breakthrough:seek-frontier"),
        )
        self.assertEqual(
            self._live(B_COMMITTED_FRONTIER_DIVERGENCE),
            ("4", "breeder-breakthrough:seek-frontier"),
        )

    def test_adjacent_non_breeder_is_fought_before_the_frontier_walk(self):
        rows, board = self._replay_through(B_DIVERGENCE)
        adjacent = [
            monster for monster in board.visible_monsters
            if monster.position.distance_to(board.player.position) <= 1
        ]
        self.assertTrue(adjacent)
        self.assertFalse(any(monster.can_multiply for monster in adjacent))
        self.assertFalse(board.player.afraid)
        self.assertEqual(
            self._live(B_DIVERGENCE), ("6", "breeder-breakthrough:seek-frontier")
        )
        key, reason = rows[B_DIVERGENCE]
        self.assertEqual(reason, "melee")
        target = adjacent[0].position
        self.assertEqual(
            key, self.policy._direction_key(board.player.position, target)
        )


class SummonerRetreatVetoRecordedTest(unittest.TestCase):
    """(c) seek-loot must not walk straight back into the abandoned square."""

    @classmethod
    def setUpClass(cls):
        boundaries, table, lines = _load()
        cls.recorded = table("c_recorded")
        cls.ends = {int(k): v for k, v in boundaries["c_board_end"].items()}
        cls.lines = list(lines["c"])
        cls.knowledge = json.loads(cls.lines[boundaries["c_knowledge_row"]])
        cls.lines[boundaries["c_knowledge_row"]] = None
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        self.policy._crossarea_fundraising_enforced = True  # live argv
        # The process read its own ~f reply (state row 1) before decision 1.
        self.policy.consume_skill_knowledge(self.knowledge)
        self._fed = -1

    def _board(self, sequence):
        end = self.ends[sequence]
        rows = [row for row in self.lines[self._fed + 1: end + 1] if row is not None]
        self._fed = end
        _decoded, snapshots = _consume_response_sequence(
            rows, self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        return snapshots[-1]

    def _replay_through(self, last):
        rows = {}
        board = None
        for sequence in range(1, last + 1):
            board = self._board(sequence)
            key = self.policy.choose_key(board)
            rows[sequence] = (_key(key), self.policy.last_reason)
            self.policy.confirm_key_posted(key)
        return rows, board

    def _live(self, sequence):
        return (self.recorded[sequence]["key"], self.recorded[sequence]["reason"])

    def test_recorded_rows_are_the_alternation(self):
        self.assertEqual(
            [self._live(n) for n in range(1, 23)],
            [("7", "seek-loot"), ("3", "summoner:retreat")] * 11,
        )
        self.assertEqual(
            {tuple(self.recorded[n]["position"]) for n in range(1, 23)},
            {(24, 116), (23, 115)},
        )

    def test_replay_reproduces_the_retreat(self):
        rows, board = self._replay_through(C_RETREAT)
        self.assertEqual(rows, {n: self._live(n) for n in range(1, C_RETREAT + 1)})
        self.assertEqual(board.player.position, C_RETREAT_CELL)
        self.assertTrue(any(
            monster.can_summon and monster.distance == 18
            for monster in board.visible_monsters
        ))

    def test_seek_loot_does_not_walk_back_into_the_abandoned_square(self):
        rows, board = self._replay_through(C_DIVERGENCE)
        self.assertIn(C_RETREAT_CELL, self.policy._engagement_avoid_cells)
        self.assertFalse(any(m.can_summon for m in board.visible_monsters))
        self.assertEqual(self._live(C_DIVERGENCE), ("7", "seek-loot"))
        key, _reason = rows[C_DIVERGENCE]
        self.assertNotEqual(
            key, self.policy._step_toward(board, C_RETREAT_CELL)
        )


if __name__ == "__main__":
    unittest.main()
