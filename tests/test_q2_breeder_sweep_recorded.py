"""Recorded pins for the 2026-10-19 Quest 2 (Sewer) stops (#78).

Linux soak c4-a life-014, floor (0, 15, 2), main 35b1cf2d.

A. 08:38:24 loop-detected: the Q2 ranged core fired at a corpse-mass
   (race 202, MULTIPLY) group from (7,27)/(8,26).  The visible count fell
   15 -> 5 over the 40-decision window while the decisions were labelled
   ``quest-strategy:q2-fire``.  The driver exempts the same core's
   ``quest-strategy:ranged-fire`` label from the cell loop guard, but not the
   Q2 label, so the productive fight was stopped as a confined loop.

B. 08:39:36 loop-detected: after the restart, ``quest:blocked:
   q2-residual-202-sweep`` waited 35 times at (9,46).  No routable,
   unvisited observation goal remained for the three race-202 placements,
   which were never in view; WAIT changes neither the visited set nor the
   static routes, so the state could only repeat.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation for bare module runs
import gzip
import hashlib
import json
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.cli import (
    LOOP_WINDOW,
    QUEST_COMBAT_REASON_PREFIXES,
    _cell_loop_guard_applies,
    _is_looping,
)
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import RANGED_MAX_DISTANCE
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.quest_strategies import load_quest_strategies


ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
FIXTURES = ROOT / "tests/fixtures"
FIRE_FIXTURE = FIXTURES / "q2-corpse-fire-loop-20261019.jsonl.gz"
BLOCKED_FIXTURE = FIXTURES / "q2-residual-202-blocked-20261019.jsonl.gz"
SHA256 = {
    FIRE_FIXTURE: "0d2c34128d3e4c683ddb24286e9dd7831eb22c5cce5efa03f5d853c82efcf3b9",
    BLOCKED_FIXTURE: "07c75361fde2a29b0df8ce959a5adb6095ca58bee469cff97da46dce95e79106",
}
CORPSE_MASS = 202
BLOCKED_REASON = "quest:blocked:q2-residual-202-sweep"


def _rows(path: Path) -> list[dict]:
    raw = gzip.decompress(path.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == SHA256[path], path
    return [json.loads(line) for line in raw.decode("utf-8").splitlines()]


def _guard_stop_sequence(rows: list[dict]) -> int | None:
    """Feed recorded decisions through the driver's cell loop guard."""
    recent = deque(maxlen=LOOP_WINDOW)
    previous = None
    for row in rows:
        position = Position(row["position"]["y"], row["position"]["x"])
        floor = row["floor"]
        snapshot = SimpleNamespace(
            in_town=False,
            floor_key=(floor["dungeon_id"], floor["level"], floor["quest_id"]),
            player=SimpleNamespace(position=position),
        )
        if _cell_loop_guard_applies(snapshot, row["reason"], previous):
            recent.append((snapshot.floor_key, position.y, position.x))
            if _is_looping(recent):
                return row["decision_sequence"]
        else:
            recent.clear()
        previous = position
    return None


class Q2CorpseMassFireRecordedTest(unittest.TestCase):
    def test_recorded_fire_window_is_a_progressing_fight(self):
        rows = _rows(FIRE_FIXTURE)
        self.assertEqual(len(rows), LOOP_WINDOW)
        self.assertEqual(
            (rows[0]["decision_sequence"], rows[-1]["decision_sequence"]),
            (5120, 5159),
        )
        self.assertEqual(
            sum(row["reason"] == "quest-strategy:q2-fire" for row in rows), 30
        )
        fights = [row for row in rows if row["visible_hostiles"]]
        self.assertEqual(
            (fights[0]["visible_hostiles"], fights[-1]["visible_hostiles"]),
            (15, 5),
        )
        kills = sum(
            "死体の塊を倒した" in message
            for row in rows
            for message in row["messages"]
        )
        self.assertEqual(kills, 15)
        self.assertEqual(
            {(row["position"]["y"], row["position"]["x"]) for row in rows},
            {(3, 23), (4, 24), (5, 25), (6, 26), (7, 27), (8, 26)},
        )

    def test_q2_fire_holds_are_quest_combat_not_a_cell_loop(self):
        rows = _rows(FIRE_FIXTURE)
        self.assertIsNone(_guard_stop_sequence(rows))
        self.assertIn("quest-strategy:q2-fire", QUEST_COMBAT_REASON_PREFIXES)
        # Removing the Q2 label recreates the exact live stop.
        with patch(
            "hengbot.cli.QUEST_COMBAT_REASON_PREFIXES",
            tuple(
                prefix for prefix in QUEST_COMBAT_REASON_PREFIXES
                if prefix != "quest-strategy:q2-fire"
            ),
        ):
            self.assertEqual(_guard_stop_sequence(rows), 5159)

    def test_q2_route_steps_still_feed_the_cell_guard(self):
        # Control: only stationary combat is exempt; moving decisions such as
        # the recorded breeder recommit still count toward the guard.
        rows = _rows(FIRE_FIXTURE)
        recommit = rows[1]
        self.assertEqual(
            recommit["reason"], "quest-strategy:q2-breeder-recommit"
        )
        snapshot = SimpleNamespace(
            in_town=False,
            floor_key=(0, 15, 2),
            player=SimpleNamespace(position=Position(4, 24)),
        )
        self.assertTrue(
            _cell_loop_guard_applies(
                snapshot, recommit["reason"], Position(3, 23)
            )
        )
        stationary_recommit = _cell_loop_guard_applies(
            snapshot, recommit["reason"], Position(4, 24)
        )
        self.assertTrue(stationary_recommit)


class Q2ResidualBlockedRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quest = load_quest_knowledge(EDIT / "quests")[2]
        cls.monraces = load_monrace_knowledge(
            EDIT / "MonraceDefinitions.jsonc"
        )
        cls.profile = load_quest_strategies(ROOT / "strategy/quests")[2]
        cls.rows = _rows(BLOCKED_FIXTURE)
        cls.placements = [
            Position(*position)
            for position, race_id in cls.quest.battlefield.monster_placements
            if race_id == CORPSE_MASS
        ]

    def _setup(self, *, leave_unvisited: Position | None = None):
        policy = HengbotPolicy(
            quest_knowledge={2: self.quest},
            quest_strategies={2: self.profile},
            monrace_knowledge=self.monraces,
        )
        # DECLARED CONSTRUCTED: the capture holds only the process tail
        # (decisions 625..845).  Restore the approved earlier Q2 gates, as in
        # the #61 pin, with race 202 as the active residual sweep.
        policy._q2_cleared_races.update(self.profile.priority_targets)
        policy._q2_surveyed_placements.update(
            Position(*position)
            for position, _ in self.quest.battlefield.monster_placements
        )
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        snapshot = parse_snapshot(self.rows[0]["board"], self.monraces)
        navigator = QuestFloorNavigator(2, self.quest.battlefield)
        navigator.allow_diagonal = True
        navigator.opened.update(
            position
            for position, grid in snapshot.grids.items()
            if grid.enterable
            and self.quest.battlefield.terrain.get((position.y, position.x))
            == "wall"
        )
        # DECLARED CONSTRUCTED: the recorded blocked reason is emitted only
        # when no unvisited observation goal is routable.  The visits that
        # produced that state precede the capture, so mark every race-202
        # observation goal visited (optionally keeping one as a control).
        for placement in self.placements:
            for goal in navigator.observation_goals(
                placement, RANGED_MAX_DISTANCE
            ):
                if goal != leave_unvisited:
                    policy._q2_phase_visited_goals.add(
                        (snapshot.floor_key, -CORPSE_MASS, placement, goal)
                    )
        return policy, navigator, snapshot

    def test_recorded_rows_wait_at_one_cell(self):
        self.assertEqual(len(self.rows), 35)
        self.assertEqual(
            {(row["key"], row["reason"]) for row in self.rows},
            {("5", BLOCKED_REASON)},
        )
        self.assertEqual(
            {(row["position"]["y"], row["position"]["x"]) for row in self.rows},
            {(9, 46)},
        )
        snapshot = parse_snapshot(self.rows[0]["board"], self.monraces)
        self.assertEqual(snapshot.player.position, Position(9, 46))
        self.assertEqual(
            self.placements,
            [Position(7, 35), Position(7, 36), Position(8, 36)],
        )
        for placement in self.placements:
            grid = snapshot.grid_at(placement)
            self.assertTrue(grid.known)
            self.assertFalse(grid.has_monster)
            self.assertFalse(grid.in_view)

    def test_exhausted_residual_sweep_moves_to_the_next_race(self):
        policy, navigator, snapshot = self._setup()

        key = policy._q2_phase_key(snapshot, self.profile, navigator)

        self.assertIn(CORPSE_MASS, policy._q2_residual_surveyed_races)
        self.assertNotEqual(policy.last_reason, BLOCKED_REASON)
        self.assertEqual(
            (key, policy.last_reason),
            ("1", "quest-strategy:q2-residual-213-sweep"),
        )

    def test_routable_unvisited_goal_keeps_the_202_sweep(self):
        # Control: while one observation goal is still unvisited and
        # routable, the race-202 sweep keeps routing toward it.
        policy, navigator, snapshot = self._setup(
            leave_unvisited=Position(7, 35)
        )

        key = policy._q2_phase_key(snapshot, self.profile, navigator)

        self.assertNotIn(CORPSE_MASS, policy._q2_residual_surveyed_races)
        self.assertEqual(
            policy.last_reason, "quest-strategy:q2-residual-202-sweep"
        )
        self.assertIn(key, set("12346789"))


if __name__ == "__main__":
    unittest.main()
