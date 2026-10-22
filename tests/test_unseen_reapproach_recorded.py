"""Recorded pins: walking back into a continuing unseen attack (Angband 30F, 2026-10-20).

User 2026-10-06 「後ずさりは今のまま・拾いを諦める」 and 2026-10-19 (one
question, one predicate): while an unseen attack continues, nothing in the
direction retreated from is approached again -- by exploration or by loot --
and a restarted bot still knows the attack.

Source: Linux soak c4-a life-014, captures 20261020-040109-loop-detected,
-040122-no-key-exhausted and -040134-no-key-exhausted.  The fixture holds the
state row of each decision from the floor arrival (9604, recall landing at
(22, 64)) to the loop stop (9714), then the first board of the restarted
process ("1:1"); ``.recorded.json`` holds the live (tag, turn, key, reason,
position, hp, messages).  Declared: the knowledge row is the restarted
process's (turn 2564990, same character); the calibration file is the shared
recorded one of ``test_esp_threat_rest_recorded`` (no calibration was
captured; nothing here reads it on a dungeon floor).

Replay on e8ae2b19, fresh process warmed on 9604's board: every key of
9605-9714 equals live except 9629 (probe vs seek-loot, a pre-floor history
difference); from 9630 to the loop stop it is the live sequence, including
the explore '4' steps back onto the hit cells.  After the fix the first
divergence is 9647 (explore leaves the attack's area); later boards are the
live ones the fixed bot would not have seen, so they are declared boards.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import os
from types import SimpleNamespace
from unittest import mock

from hengbot.cli import (
    _build_argument_parser,
    _configure_policy_output_paths,
    _consume_response_sequence,
)
from hengbot.model import Position
from hengbot.policy_identification import UNSEEN_LOOT_QUIET_TURNS
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.runtime_paths import RUNTIME_DIR_ENV, isolate_restored_runtime_paths

from recorded_floor_knowledge import pre_seen_floor_replay
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "unseen-reapproach-dl30-20261020.jsonl.gz"
RECORDED = FIXTURES / "unseen-reapproach-dl30-20261020.recorded.json"
SHA256 = {
    FIXTURE: "af8f1a26790a60ee579c0140a6b1adca51bfda014abb3dbaa51b241ecc4c7c1f",
    RECORDED: "eb07809b7239635c87be42b0110e6e59863e2b5dd82fcb8adaaafa3e8ba9cfdb",
}
FLOOR = (1, 30, 0)
ARRIVAL = 9604
LOOP_STOP = 9714
FIRST_FIX_DIVERGENCE = 9647
LAST_LOOP_EXPLORE = 9712  # explore '4' from (22, 62) onto the hit cell (22, 61)
RESTART_BOARD = "1:1"  # restarted process: seek-loot '4' toward (23, 61)
ITEM_IN_ATTACK = Position(23, 61)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class UnseenReapproachRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        cls.knowledge = json.loads(records[0]["line"])
        cls.boards = {record["sequence"]: record["line"] for record in records[1:]}
        rows = json.loads(RECORDED.read_text(encoding="utf-8"))["recorded"]
        cls.recorded = {row[0]: row for row in rows}
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _process(self, directory: Path):
        """A bot process as the CLI starts it, decision log in ``directory``."""
        policy = _policy(directory, self.monrace)
        policy.consume_skill_knowledge(self.knowledge)
        # As the CLI points it: beside the decision log.
        _configure_policy_output_paths(policy, _build_argument_parser().parse_args([
            "--state-file", str(directory / "state.jsonl"),
            "--decision-log", str(directory / "bot-decisions.jsonl"),
        ]))
        return policy

    def _decide(self, policy, directory: Path, tag: str):
        _decoded, snapshots = _consume_response_sequence(
            [self.boards[tag]], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        board = snapshots[-1]
        key = policy.choose_key(board)
        if key is not None:
            policy.confirm_key_posted(key)
        return key, policy.last_reason, board

    def _replay_floor(self, policy, directory: Path, last: int):
        rows = {}
        for sequence in range(ARRIVAL, last + 1):
            tag = f"0:{sequence}"
            rows[sequence] = self._decide(policy, directory, tag)
        return rows

    def _live(self, tag):
        row = self.recorded[tag]
        return row[2], row[3]

    def test_recorded_rows_are_the_incident(self):
        loop = [self._live(f"0:{n}") for n in range(9710, 9713)]
        self.assertEqual(loop, [("4", "explore")] * 3)
        self.assertEqual(self.recorded["0:9713"][4], [22, 61])
        self.assertTrue(any(m.startswith("何か") for m in self.recorded["0:9713"][6]))
        self.assertEqual(self._live(RESTART_BOARD), ("4", "seek-loot"))
        self.assertEqual(self._live("1:7"), (None, "warning:blocked-step"))

    @pre_seen_floor_replay  # declared wall: board recorded 2026-10-20, before the 2026-10-23 seen-floor rule (tests/recorded_floor_knowledge.py)
    def test_explore_does_not_walk_back_into_the_attack(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            policy = self._process(directory)
            rows = self._replay_floor(policy, directory, LOOP_STOP)
        for sequence in range(9630, FIRST_FIX_DIVERGENCE):
            with self.subTest(sequence=sequence):
                self.assertEqual(rows[sequence][:2], self._live(f"0:{sequence}"))
        # Live (and e8ae2b19): explore '4' toward the frontier (24, 59)
        # behind the hit cells of 9645 (22, 62), retreat heading east.
        self.assertEqual(self._live(f"0:{FIRST_FIX_DIVERGENCE}"), ("4", "explore"))
        self.assertEqual(rows[FIRST_FIX_DIVERGENCE][:2], ("8", "explore"))
        # Declared board (the fixed bot was elsewhere): the last explore
        # before the loop stop no longer steps onto the hit cell (22, 61).
        self.assertEqual(self._live(f"0:{LAST_LOOP_EXPLORE}"), ("4", "explore"))
        self.assertEqual(rows[LAST_LOOP_EXPLORE][:2], ("6", "explore"))
        # The retreat itself is unchanged on the hit boards.
        for sequence in (9645, 9646, 9713, 9714):
            with self.subTest(retreat=sequence):
                self.assertEqual(rows[sequence][:2], self._live(f"0:{sequence}"))

    def test_restarted_process_still_knows_the_attack(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = self._process(directory)
            self._replay_floor(first, directory, LOOP_STOP)
            record = json.loads(
                (directory / "unseen-attack.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                (record["floor"], record["turn"], record["position"], record["direction"]),
                (list(FLOOR), self.recorded["0:9713"][1], [22, 61], [0, 1]),
            )
            restarted = self._process(directory)
            key, reason, _board = self._decide(restarted, directory, RESTART_BOARD)
        # Live (and e8ae2b19): seek-loot '4' back to (23, 61), the fire bolt,
        # the retreat onto a warning-refused cell and no key, three times.
        self.assertEqual((key, reason), ("9", "explore"))
        self.assertNotEqual(restarted._loot_target, ITEM_IN_ATTACK)

    def test_retreat_does_not_step_onto_a_warning_refused_cell(self):
        # The restarted process as live ran it (no record): seek-loot onto
        # (23, 61), fire bolt, retreat '9' then '6' toward (22, 63), whose
        # weapon warning prompt is on board 1:7.
        refused = Position(22, 63)
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            policy = self._process(directory)
            for tag in ("1:1", "1:2", "1:3", "1:4", "1:5", "1:6"):
                with self.subTest(tag=tag):
                    self.assertEqual(self._decide(policy, directory, tag)[:2],
                                     self._live(tag))
            key, reason, board = self._decide(policy, directory, "1:7")
            # Live (and e8ae2b19): (None, 'warning:blocked-step') -> no key.
            self.assertEqual(self._live("1:7"), (None, "warning:blocked-step"))
            self.assertEqual((key, reason), ("4", "explore"))
            self.assertIn(refused, policy._warning_refused_cells)
            # Control: the same board with the cell not refused keeps the
            # retreat's own step.
            policy._warning_refused_cells.discard(refused)
            policy._unseen_retreat_floor = FLOOR
            policy._unseen_retreat_direction = (0, 1)
            self.assertEqual(policy._unseen_reverse_choke_step(board), refused)

    def test_control_no_attack_record_still_loots_the_item(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            restarted = self._process(directory)
            key, reason, _board = self._decide(restarted, directory, RESTART_BOARD)
        self.assertEqual((key, reason), self._live(RESTART_BOARD))
        self.assertEqual(restarted._loot_target, ITEM_IN_ATTACK)

    def test_control_attack_past_the_quiet_window_still_loots_the_item(self):
        turn = self.recorded[RESTART_BOARD][1]
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "unseen-attack.json").write_text(json.dumps({
                "floor": list(FLOOR),
                "turn": turn - UNSEEN_LOOT_QUIET_TURNS,
                "position": [22, 61],
                "direction": [0, 1],
            }) + "\n", encoding="utf-8")
            restarted = self._process(directory)
            key, reason, _board = self._decide(restarted, directory, RESTART_BOARD)
        self.assertEqual((key, reason), self._live(RESTART_BOARD))
        self.assertEqual(restarted._loot_target, ITEM_IN_ATTACK)


class UnseenAttackAreaConsumersTest(unittest.TestCase):
    """Declared boards: every walker consults the same area predicate.

    The last unseen hit of this floor landed on HIT and the retreat heads
    east (0, 1), so the area is x <= HIT.x while the hit is inside the quiet
    window.  Walls are declared through ``_walkable_neighbors``.
    """

    HIT = Position(10, 8)
    TURN = 5000

    def _policy(self):
        policy = HengbotPolicy()
        policy._unseen_last_hit_floor = FLOOR
        policy._unseen_last_hit_turn = self.TURN
        policy._unseen_last_hit_position = self.HIT
        policy._unseen_loot_direction = (0, 1)
        return policy

    def _board(self, position):
        return SimpleNamespace(
            player=SimpleNamespace(position=position), floor_key=FLOOR,
            turn=self.TURN + 1, grids={}, in_town=False,
            in_bounds=lambda _position: True,
        )

    def test_loot_target_in_the_area_is_not_resumed(self):
        # Standing behind the hit cell (the half-plane deferral measured from
        # the player keeps the item); the predicate drops the committed target.
        policy = self._policy()
        policy._known_loot = {self.HIT}
        policy._loot_target = self.HIT
        policy._position_target_step = lambda snapshot, target: target
        self.assertIsNone(policy._loot_step(self._board(Position(10, 7))))

    def test_loot_route_does_not_cross_the_area(self):
        policy = self._policy()
        target = Position(11, 10)
        policy._known_loot = {target}
        graph = {Position(10, 9): [Position(10, 8)], Position(10, 8): [target]}
        policy._walkable_neighbors = lambda snapshot, pos, **_: graph.get(pos, [])
        self.assertIsNone(policy._loot_step(self._board(Position(10, 9))))
        # Control: the same board without the hit walks the route.
        policy._unseen_last_hit_position = None
        self.assertEqual(policy._loot_step(self._board(Position(10, 9))), Position(10, 8))

    def test_explore_planner_does_not_enter_the_area(self):
        policy = self._policy()
        policy._floor_t = {(10, 8)}
        policy._walkable_neighbors = lambda snapshot, pos, **_: (
            [Position(10, 8)] if pos == Position(10, 9) else []
        )
        board = self._board(Position(10, 9))
        self.assertEqual(policy._plan_explore_path_pass(board, allow_damaging=False), [])
        policy._unseen_last_hit_turn = self.TURN - UNSEEN_LOOT_QUIET_TURNS
        self.assertEqual(
            policy._plan_explore_path_pass(board, allow_damaging=False), [Position(10, 8)]
        )

    def _frontier_policy(self, frontiers, graph=None):
        policy = self._policy()
        policy._remembered_floor_t = {(p.y, p.x) for p in frontiers}
        policy._is_remembered_frontier = lambda snapshot, position: True
        policy._equipped_digging_tool = lambda snapshot: None
        if graph is None:
            policy._walkable_neighbors = lambda snapshot, pos, **_: [
                Position(pos.y + dy, pos.x + dx)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx
            ]
        else:
            policy._walkable_neighbors = lambda snapshot, pos, **_: graph.get(pos, [])
        return policy

    def test_global_frontier_prefers_a_frontier_outside_the_area(self):
        inside, outside = Position(10, 5), Position(10, 12)
        policy = self._frontier_policy({inside, outside})
        path = policy._global_frontier_path(self._board(Position(10, 10)))
        self.assertEqual((len(path), path[-1]), (2, outside))

    def test_global_frontier_route_does_not_cross_the_area(self):
        goal = Position(12, 12)
        graph = {Position(10, 12): [Position(11, 11)], Position(11, 11): [goal]}
        policy = self._frontier_policy({goal}, graph)
        policy._unseen_last_hit_position = Position(11, 11)
        self.assertEqual(policy._global_frontier_path(self._board(Position(10, 12))), [])

    def test_retreat_choke_search_skips_a_warning_refused_cell(self):
        # Declared corridor east of the hit: two chokes ahead, the nearer one
        # refused by the weapon warning.  The retreat aims at the other.
        policy = self._policy()
        policy._unseen_retreat_floor = FLOOR
        policy._unseen_retreat_direction = (0, 1)
        start, ahead = Position(10, 10), Position(10, 11)
        refused, other = Position(10, 12), Position(11, 12)
        graph = {start: [ahead], ahead: [refused, other]}
        policy._walkable_neighbors = lambda snapshot, pos, **_: graph.get(pos, [])
        policy._open_neighbor_count = lambda snapshot, pos: (
            1 if pos in (refused, other) else 8
        )
        board = self._board(start)
        self.assertEqual(policy._unseen_reverse_choke_step(board), ahead)
        self.assertEqual(policy._unseen_retreat_target, refused)
        policy._warning_refused_cells.add(refused)
        self.assertEqual(policy._unseen_reverse_choke_step(board), ahead)
        self.assertEqual(policy._unseen_retreat_target, other)

    def test_restored_checkpoint_moves_the_record_with_the_runtime_dir(self):
        policy = SimpleNamespace(_unseen_attack_path=Path("jsonlog") / "unseen-attack.json")
        with TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {RUNTIME_DIR_ENV: tmp}):
            isolate_restored_runtime_paths(policy)
            self.assertEqual(policy._unseen_attack_path, Path(tmp) / "unseen-attack.json")


if __name__ == "__main__":
    unittest.main()
