"""q2-residual-dark-placement-1102: the n1-b life-295 Q2 residual-sweep stall.

n1-b life-295 (warrior Lv22, build bot-9afd9203e) on 鉄獄15階, fixed quest 2,
stopped 2026-11-02 18:10:28 with
``stall:floor-dwell:quest-strategy:q#-residual-#-sweep``.  From turn 641840 to
the stop (14165 boards) the player walked the same 12-step loop
(1,1)-(1,5)-(3,7)-(1,5)-(1,1) under ``quest-strategy:q2-residual-86-sweep``:
race 86 has placements (1,1), (3,1) and (3,7), and (1,1) and (3,7) are dark
(light radius 2, six cells apart).

Root: the sweep marked an observation goal visited only for the placements
still unconfirmed on that board.  Standing on a placement always confirms it
(the player's own grid holds no monster), so arriving at (3,7) never recorded
the visit under placement (3,7); walking away made (3,7) unconfirmed (dark)
again with its own cell an unvisited distance-0 goal, and the same at (1,1).
Now the visit is recorded for every placement of the race.

Fixture: tests/fixtures/q2-residual-dark-placement-20261102.json.gz
(tests/extract_q2_residual_dark_placement_1102_fixture.py).  Every decision is
the public ``choose_key``; the replayed recorded boards' keys go through the
production executor port (test_me_nokey_1031_recorded.PostedKey).
DECLARED RECONSTRUCTION: the capture holds no Q2 phase history, so the
completed ordered placement phases and the four earlier residual races are
seeded as in test_q2_residual_recorded.  No target, visited goal or route is
seeded.
DECLARED COUNTERFACTUAL: after the recorded boards, the player position (and
turn) follows the emitted moves on the last recorded board; every other board
fact is unchanged.  This proves the sweep is finite, not a live completion.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import Q2_RESIDUAL_SWEEP_RACES
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests import test_me_nokey_1031_recorded as nokey


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "q2-residual-dark-placement-20261102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
SWEEP = "quest-strategy:q2-residual-86-sweep"
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def new_policy():
    quests = load_quest_knowledge(Path("C:/hengband/lib/edit/quests"))
    profiles = load_quest_strategies(ROOT / "strategy/quests")
    policy = HengbotPolicy(quest_knowledge=quests, quest_strategies=profiles)
    first = CASE["boards"][0]
    policy.consume_skill_knowledge(copy.deepcopy(CASE["skill"]))
    policy.prime(policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(first))))
    # DECLARED RECONSTRUCTION (module docstring).
    policy._q2_cleared_races.update(profiles[2].priority_targets)
    policy._q2_breach_complete = True
    policy._q2_blue_recovery_complete = True
    policy._q2_surveyed_placements.update(
        Position(*position) for position, _ in quests[2].battlefield.monster_placements
    )
    policy._q2_residual_surveyed_races.update(
        race for race in Q2_RESIDUAL_SWEEP_RACES if race != 86
    )
    return policy


def decide(policy, snapshot):
    return str(policy.choose_key(policy.with_known_skill_exp(snapshot)))


class Q2ResidualDarkPlacementRecordedTest(nokey.PostedKey):
    def test_recorded_boards_walked_the_dark_placement_loop(self):
        rows = CASE["decisions"]
        positions = [(raw["player"]["y"], raw["player"]["x"]) for raw in CASE["boards"]]
        self.assertEqual(positions[2], (3, 7))
        self.assertEqual(positions[8], (1, 1))
        self.assertEqual(positions[-1], (3, 7))
        self.assertEqual({row["reason"] for row in rows}, {SWEEP})
        # The recorded run turned back on each dark placement cell.
        self.assertEqual([row["key"] for row in rows[2:3] + rows[8:9]], ["7", "6"])

    def test_sweep_records_the_dark_placement_visits_and_finishes(self):
        policy = new_policy()
        for raw in CASE["boards"]:
            key = decide(policy, parse_snapshot(copy.deepcopy(raw)))
            self.assertEqual(policy.last_reason, SWEEP, raw["turn"])
            self.post(policy, raw, key)
            policy.confirm_key_posted(key)
        floor = parse_snapshot(copy.deepcopy(CASE["boards"][-1])).floor_key
        for placement in (Position(1, 1), Position(3, 7)):
            # Both dark placement cells were stood on: their own goal is visited.
            self.assertIn((floor, -86, placement, placement), policy._q2_phase_visited_goals)

        # DECLARED COUNTERFACTUAL (module docstring): follow the moves.
        snapshot = parse_snapshot(copy.deepcopy(CASE["boards"][-1]))
        key = decide(policy, snapshot)
        steps = 0
        while policy.last_reason == SWEEP:
            self.assertLess(steps, 600, "the residual-86 sweep did not finish")
            dy, dx = MOVES[key]
            position = Position(snapshot.player.position.y + dy, snapshot.player.position.x + dx)
            cell = snapshot.grid_at(position) or policy._remembered_grids.get(position)
            self.assertTrue(cell is not None and cell.enterable, position)
            snapshot = replace(snapshot, player=replace(snapshot.player, position=position),
                               turn=snapshot.turn + 10)
            key = decide(policy, snapshot)
            steps += 1
        self.assertIn(86, policy._q2_residual_surveyed_races)
        self.assertEqual(policy.last_reason, "quest-strategy:q2-final-patrol")


if __name__ == "__main__":
    import unittest
    unittest.main()
