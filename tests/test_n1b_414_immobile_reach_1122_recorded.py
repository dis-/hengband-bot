"""n1-b life-414, Orc cave 22F, 2026-11-22 06:51-07:26: the floor-dwell stop of a floor still being explored.

The bot process started at 06:51:33 on the game's reload of the floor.  Its absorbed Detect Evil
(turn 1104257) showed 21 死体の塊 (race 202: NEVER_MOVE, MULTIPLY, TOUCH:LOSE_CON) at
(47-50,181-193); immobile_threat_memory kept them for the floor visit (a stat-draining touch is
kept away from, owner 2026-11-01 21h) and they were never in view again.  Every board after,
immobile_ranged_kill ``key`` asked each of them for a safe ranged kill, and no cell the walks
reached could shoot any: each ask searched the whole cave (four passes, and the shooting test
over every grid) and found nothing.  A decision took 2.0-2.7 s (40-60 ms before the reload, and
on the 07:26 restart that never saw them), so 35 minutes held 985 decisions; the explore was
making its way (known 11,724 -> 12,225, frontiers 3,579 -> 2,658) when the floor-dwell watcher
(30 minutes of wall time on one floor) stopped the bot.  The restarted process explored the rest
in four minutes and recalled.

Recorded (tests/extract_n1b_414_immobile_reach_1122_fixture.py): the detection's board and a
later explore board of the run, decided by a fresh policy as the restarted bot decided them.

Pinned: the board's goal-walk reach is searched once for every remembered monster
(immobile_ranged_kill ``_board_reach``); a monster with no shooting cell in it gets no route
search of its own, and the answer is the full search's (no plan, the same key).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import hengbot.policy  # noqa: F401 -- loads the modules in their cycle-safe order
from hengbot import goal_route, immobile_ranged_kill, immobile_threat_memory
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-414-immobile-reach-1122" / "boards.json.xz"
UNDEAD_MASS = 202


class N1b414ImmobileReachRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boards = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.policy = _policy(Path(directory.name), self.monrace)
        detection, self.later = self.boards
        self.policy.prime(self._snapshot(detection))
        self.policy.consume_skill_knowledge({
            "player": {"level": detection["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]}})
        self.policy.choose_key(self._snapshot(detection))
        self.searches = []
        original = goal_route.nearest_goal_path

        def counted(policy, snapshot, predicate, entrance_cells):
            if goal_route.goal_kind(predicate).endswith("plan.<locals>.shooting"):
                self.searches.append(snapshot.turn)
            return original(policy, snapshot, predicate, entrance_cells)
        goal_route.nearest_goal_path = counted
        self.addCleanup(setattr, goal_route, "nearest_goal_path", original)

    def _snapshot(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge)

    def test_remembered_masses_cost_no_route_search_each(self):
        key = self.policy.choose_key(self._snapshot(self.later))
        masses = [monster for monster in immobile_threat_memory.remembered(self.policy)
                  if monster.race_id == UNDEAD_MASS]
        self.assertEqual(len(masses), 21)
        self.assertNotEqual(self.policy.last_reason, immobile_ranged_kill.APPROACH_REASON)
        self.assertIsNotNone(key)
        # Main searched the cave for each of the 21 on every board.
        self.assertEqual(self.searches, [])

    def test_the_answer_is_the_full_searchs(self):
        snapshot = self._snapshot(self.later)
        self.policy.choose_key(snapshot)
        masses = [monster for monster in immobile_threat_memory.remembered(self.policy)
                  if monster.race_id == UNDEAD_MASS]
        reach = immobile_ranged_kill._board_reach(self.policy, snapshot)
        for monster in masses:
            with self.subTest(monster=monster.position):
                self.assertTrue(immobile_ranged_kill.kept_away(self.policy, snapshot, monster))
                self.assertIsNone(immobile_ranged_kill.plan(self.policy, snapshot, monster))
                self.assertIsNone(immobile_ranged_kill.plan(
                    self.policy, snapshot, monster, reach=reach))
        # The full search ran once per monster above (no reach given), the shared reach never.
        self.assertEqual(len(self.searches), len(masses))


if __name__ == "__main__":
    unittest.main()
