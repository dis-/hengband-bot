"""Issue #101: the depth-capped 30F floor whose exploration never ended.

Owner answers 2026-10-23:
 (1) floor the player has seen inside its own light counts as explored after
     the light moves on and the game stops drawing it;
 (2) remains (tval 10) are told apart by the game's auto-pickup, so the bot's
     own floor filter does not target a remains pile.

Fixtures (rows copied as-is from the Linux soak c4-a/life-014 captures):
- floor-dwell-20261022-0047-state.jsonl.gz: all 113 state rows of
  20261022-004727-stall-floor-dwell-explore (Angband 30F, protocol 3, light
  radius 1, turns 4331403..4332676); -decisions: the 112 decision rows of the
  same turns (recorded explore goals).
- floor-dwell-20261022-0129-remains.jsonl.gz: state rows 85 and 86 of
  20261022-012932-stall-floor-dwell-explore: recorded decisions 'seek-loot' '6'
  toward a single ゾンビ・イークの死体 at (12,111), then 'pickup' 'g' on it.

DECLARED CONSTRUCTED: the controls of the remains pile rewrite the pile's
tvals on the recorded rows (a mixed pile, a skeleton-fragment pile).  The
replay is open-loop: each recorded board is observed and decided, the next
recorded board follows whatever the replayed policy chose.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import NEIGHBOR_OFFSETS
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
STATE = FIXTURES / "floor-dwell-20261022-0047-state.jsonl.gz"
STATE_SHA256 = "5c24d1d7db1d2b5f4f0a72e8efe25f1caee263ce1ab49f5617d1827c9e8ff326"
DECISIONS = FIXTURES / "floor-dwell-20261022-0047-decisions.jsonl.gz"
DECISIONS_SHA256 = "d92f0f3834fb2d3f8c349615a1554fcca10ddb1dfa88f8b883cca89277455cf5"
REMAINS = FIXTURES / "floor-dwell-20261022-0129-remains.jsonl.gz"
REMAINS_SHA256 = "ec03db4ee115e0d1b1c5e4ed3d1604fbe8efcf173b78863bf90c33508d09ac87"
CORPSE = Position(12, 111)


def _lines(path: Path, digest: str) -> list[str]:
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest
    return gzip.decompress(data).decode("utf-8").splitlines()


class _Replay:
    def __init__(self, test: unittest.TestCase, monrace):
        self.temporary = TemporaryDirectory()
        test.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.monrace = monrace
        self.policy = _policy(self.directory, monrace)
        self.policy._crossarea_fundraising_enforced = True

    def board(self, line: str):
        _decoded, snapshots = _consume_response_sequence(
            [line], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        board = snapshots[-1]
        # DECLARED CONSTRUCTED: the ~f skill-exp cache.
        self.policy._skill_exp_cache = (
            0, 0, board.player.level, self.policy._town_visit_epoch
        )
        return board

    def decide(self, line: str):
        board = self.board(line)
        key = self.policy.choose_key(board)
        return board, key, self.policy.last_reason


class SeenFloorExploredRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.states = _lines(STATE, STATE_SHA256)
        assert len(cls.states) == 113
        cls.decisions = {}
        for line in _lines(DECISIONS, DECISIONS_SHA256):
            row = json.loads(line)
            cls.decisions.setdefault(row["turn"], row)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _replay_floor(self):
        replay = _Replay(self, self.monrace)
        policy = replay.policy
        rows = []
        board = None
        for line in self.states:
            board, _key, reason = replay.decide(line)
            recorded = self.decisions.get(board.turn) or {}
            claim = recorded.get("claim") or {}
            cell = (claim.get("goal") or {}).get("cell")
            recorded_goal = (
                Position(cell[0], cell[1])
                if claim.get("owner") == "explore" and cell is not None else None
            )
            identity = policy._explore_goal_identity
            rows.append({
                "reason": reason,
                "goal": identity.position if identity is not None else None,
                "recorded_goal": recorded_goal,
                "recorded_goal_frontier": (
                    policy._is_remembered_frontier(board, recorded_goal)
                    if recorded_goal is not None else None
                ),
                "recorded_goal_visits": (
                    policy._visit_counts[recorded_goal]
                    if recorded_goal is not None else None
                ),
            })
        return policy, board, rows

    def test_recorded_rewalk_targets_are_not_chosen(self):
        _policy_, _board, rows = self._replay_floor()
        recorded = [row for row in rows if row["recorded_goal"] is not None]
        self.assertEqual(len(recorded), 112)
        # Recorded goals already walked on, with every neighbour seen: the
        # re-walk targets of the recorded window (all 112 were frontiers).
        rewalk = [
            row for row in recorded
            if not row["recorded_goal_frontier"] and row["recorded_goal_visits"]
        ]
        self.assertEqual(len(rewalk), 9)
        self.assertEqual(
            [row for row in rewalk if row["goal"] == row["recorded_goal"]], []
        )
        self.assertEqual({row["reason"] for row in rows}, {"explore"})

    def test_seen_floor_leaves_only_unseen_frontier(self):
        policy, board, _rows = self._replay_floor()
        frontier = [
            Position(y, x) for (y, x) in policy._floor_t
            if policy._is_remembered_frontier(board, Position(y, x))
        ]
        # 142 remembered floor cells, every one a frontier before the change.
        self.assertEqual(len(policy._floor_t), 142)
        self.assertEqual(len(frontier), 17)
        # Control: what is left is unseen ground -- each remaining frontier
        # borders a cell no recorded board ever showed.
        for position in frontier:
            self.assertTrue(any(
                (position.y + dy, position.x + dx)
                not in policy._remembered_known_t
                and board.in_bounds(Position(position.y + dy, position.x + dx))
                for dy, dx in NEIGHBOR_OFFSETS
            ), position)

    def test_seen_only_outside_own_light_stays_unexplored(self):
        # Control: a cell shown only away from the player's light (not seen
        # inside it) is known but not explored.
        policy, board, _rows = self._replay_floor()
        outside = policy._remembered_known_t - policy._remembered_marked_t
        self.assertTrue(outside)
        self.assertTrue(outside.isdisjoint(policy._marked_t))


class RemainsPileRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = _lines(REMAINS, REMAINS_SHA256)
        assert len(cls.rows) == 2
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _rows_with_pile(self, tvals):
        rows = []
        for line in self.rows:
            data = json.loads(line)
            grid_map = data["grid_map"]
            if tvals is not None:
                for cell in grid_map["cells"]:
                    if (cell["y"], cell["x"]) == (CORPSE.y, CORPSE.x):
                        cell["o"] = len(tvals)
                        cell["t"] = list(tvals)
                for index, found in enumerate(grid_map["found_items"]):
                    if found[:2] == [CORPSE.y, CORPSE.x]:
                        grid_map["found_items"][index] = [
                            CORPSE.y, CORPSE.x, len(tvals), *tvals]
                for index, names in enumerate(grid_map["found_item_names"]):
                    if names[:2] == [CORPSE.y, CORPSE.x]:
                        grid_map["found_item_names"][index] = [
                            CORPSE.y, CORPSE.x, *(["item"] * len(tvals))]
            rows.append(json.dumps(data, ensure_ascii=False))
        return rows

    def _decide_both(self, tvals=None):
        self.replay = _Replay(self, self.monrace)
        return [self.replay.decide(line) for line in self._rows_with_pile(tvals)]

    def test_single_remains_pile_is_not_targeted(self):
        (approach, _key0, reason0), (_board, _key1, reason1) = self._decide_both()
        self.assertEqual(approach.grid_at(CORPSE).object_tvals, (10,))
        # Recorded: 'seek-loot' '6' then 'pickup' 'g' on the corpse.
        self.assertNotIn(reason0, {"seek-loot", "pickup"})
        self.assertNotIn(reason1, {"seek-loot", "pickup", "trigger-autodestroy"})
        self.assertNotIn(CORPSE, self.replay.policy._known_loot)

    def test_mixed_pile_is_still_picked_up(self):
        decided = self._decide_both((10, 23))
        self.assertEqual(
            [(key, reason) for _board, key, reason in decided],
            [("6", "seek-loot"), ("gaa", "pickup")],
        )

    def test_skeleton_fragment_pile_unchanged(self):
        decided = self._decide_both((1, 3))
        self.assertNotIn(decided[0][2], {"seek-loot", "pickup"})
        self.assertNotIn(decided[1][2], {"seek-loot", "pickup"})


if __name__ == "__main__":
    unittest.main()
