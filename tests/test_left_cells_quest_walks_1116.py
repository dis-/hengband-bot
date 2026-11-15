"""The fixed-quest walks read the cells an owner left (owner 2026-11-15, maintainability review Q2).

Owner 「記録は読ませる・危ない範囲は今のまま」: the quest navigator's walks (the loot sweep, the gold
pickup, the exit, the Q2 phase routes and every ``route_to_static_goals``) and the Q18 exit plan's
walks (quest_find_exit) keep off the left-cell registry (left_cells ``refused``) while a way off
it leads on; the areas round a monster (``_walk_veto``) they still do not read.

The recorded case: n1-a life 523 (2026-11-15 05:37, Q18) tests/test_n1a_523_q18_loop_1115_recorded,
its closed loop with the outwaited-squid fix taken out (``_outwaited`` always False, as live):
'1' exit-to-choke onto (2,18) and '9' exit-walk back.  The ping-pong guard recorded the cell the
winner left, but the exit walk did not read the registry, so the pair went on and was escalated
again and again until the loop detector stopped the bot.  Reading it, the exit walk takes the
way round instead and the pair is not escalated.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from types import SimpleNamespace
from unittest import mock

from hengbot import pingpong_guard, quest_find_exit
from hengbot.model import Position
from hengbot.quest_knowledge import QuestBattlefield
from hengbot.quest_navigator import QuestFloorNavigator
from tests import test_n1a_523_q18_loop_1115_recorded as q18

WALK, TO_CHOKE = "quest-strategy:exit-walk", "quest-strategy:exit-to-choke"
ESCALATE = "pingpong-escalate:"


def _q18_walk(*, reads_left_cells: bool, decisions: int = q18.BOUND + 60):
    case = q18.N1a523Q18OutwaitedSquidTest("test_the_recorded_boards")
    before = (mock.patch.object(quest_find_exit, "left_cells",
                                SimpleNamespace(refused=lambda policy, snapshot: frozenset()))
              if not reads_left_cells else mock.patch.dict({}))
    with mock.patch.object(quest_find_exit, "_outwaited", lambda navigator, monster: False), before:
        return case.walk(decisions)


class Q18ExitWalkReadsLeftCellsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.after = _q18_walk(reads_left_cells=True)
        cls.before = _q18_walk(reads_left_cells=False)

    def test_control_without_the_registry_the_pair_is_escalated_to_the_loop_stop(self):
        rows, tripped, events, _policy, _raw = self.before
        self.assertEqual(rows[q18.BOUND:q18.BOUND + 4],
                         [(q18.CHOKE, "1", TO_CHOKE), (q18.BEHIND, "9", WALK)] * 2)
        self.assertGreaterEqual(sum(1 for _index, event in events if event.startswith(ESCALATE)), 3)
        self.assertIsNotNone(tripped)

    def test_the_exit_walk_keeps_off_the_cell_the_guard_recorded(self):
        rows, tripped, events, _policy, _raw = self.after
        first = next(index for index, event in events if event.startswith("pingpong:"))
        # The guard reads the pair once (as before) ...
        self.assertEqual(events[0], (first, f"pingpong:{TO_CHOKE}/{WALK}"))
        # ... and on that board the choke walk steps '1' onto (2,18) again (it won: its walk
        # keeps its move), from where the exit walk no longer steps back onto the choke (1,19)
        # the guard recorded: it takes the way round by (1,17).
        self.assertEqual(rows[first], (q18.CHOKE, "1", TO_CHOKE))
        self.assertEqual(rows[first + 1], (q18.BEHIND, "7", WALK), rows[first - 2:first + 6])
        # Not inside the guard's window (its record's lifetime).
        window = rows[first:first + pingpong_guard.GUARD_BOARDS]
        self.assertNotIn((q18.BEHIND, "9", WALK), window, window[:10])
        self.assertFalse([event for _index, event in events if event.startswith(ESCALATE)], events)
        self.assertIsNone(tripped)


class NavigatorWalkPathTest(unittest.TestCase):
    """The navigator's walk off the bound left cells, else as before."""

    @staticmethod
    def navigator(cells):
        terrain = {cell: "floor" for cell in cells}
        navigator = QuestFloorNavigator(99, QuestBattlefield(terrain=terrain))
        navigator.reset_for_floor((0, 1, 99))
        return navigator

    def test_round_the_left_cell_when_a_way_leads_on(self):
        # Two rows: (0,0)..(0,2) and (1,0)..(1,2); (0,1) left.
        navigator = self.navigator({(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)})
        start, goal = Position(0, 0), Position(0, 2)
        self.assertEqual(navigator.walk_path(start, {goal})[1], Position(0, 1))  # nothing bound
        navigator.left_bound = ((0, 1, 99), start, frozenset({Position(0, 1)}))
        path = navigator.walk_path(start, {goal})
        self.assertNotIn(Position(0, 1), path)
        self.assertEqual(path[-1], goal)
        # Bound on another cell (a stale board): not read.
        navigator.left_bound = ((0, 1, 99), Position(1, 0), frozenset({Position(0, 1)}))
        self.assertEqual(navigator.walk_path(start, {goal})[1], Position(0, 1))

    def test_the_record_never_shuts_the_walk_in(self):
        navigator = self.navigator({(0, 0), (0, 1), (0, 2)})
        start, goal = Position(0, 0), Position(0, 2)
        navigator.left_bound = ((0, 1, 99), start, frozenset({Position(0, 1)}))
        self.assertEqual(navigator.walk_path(start, {goal}),
                         [Position(0, 0), Position(0, 1), Position(0, 2)])
        self.assertEqual(navigator.route_to_static_goals(start, {goal}), Position(0, 1))


if __name__ == "__main__":
    unittest.main()
