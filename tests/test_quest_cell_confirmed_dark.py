"""Pin (#84 question 9): one answer to "is fixed-quest cell P confirmed empty?".

On 4e34499f the Q2 placement survey accepted any known cell at distance <= 1
(``in_view or distance <= 1``) while the Q2 residual sweep accepted only an
``in_view`` cell.  On a dark corridor (own grid unlit) a placement one step
away that the game does not report in view is not seen: the game's
``player_can_see_bold`` needs torch light, perma-light or noctovision, never
adjacency.  The survey marked it checked; the residual did not.  After the fix
every quest site asks ``_quest_cell_confirmed_empty`` (the player's own grid,
else ``_player_can_see_empty_cell``), so both answer "not confirmed".
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import unittest
from pathlib import Path

from policy_fixtures import grid, item, player
from test_policy import REAL_QUEST_DEFINITIONS
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_WAND, Position, Snapshot
from hengbot.policy import HengbotPolicy
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.policy_constants import Q2_RESIDUAL_SWEEP_RACES, Q2_POST_BLUE_SEQUENCE
from hengbot.quest_knowledge import QuestBattlefield, QuestInfo, load_quest_knowledge
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.quest_strategies import load_quest_strategies

FLOOR = (0, 1, 2)


class QuestCellConfirmedDarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if REAL_QUEST_DEFINITIONS is None:
            raise unittest.SkipTest("real Hengband quest definitions are unavailable")
        cls.q2 = load_quest_knowledge(REAL_QUEST_DEFINITIONS)[2]
        cls.profile = load_quest_strategies(
            Path(__file__).parent.parent / "strategy" / "quests"
        )[2]

    def _setup(self):
        policy = HengbotPolicy(
            quest_strategies={2: self.profile}, quest_knowledge={2: self.q2}
        )
        navigator = QuestFloorNavigator(2, self.q2.battlefield)
        navigator.reset_for_floor(FLOOR)
        race_id = self.profile.priority_targets[0]
        placement = next(
            Position(*raw)
            for raw, placed in self.q2.battlefield.monster_placements
            if placed == race_id and navigator._static_walkable(Position(*raw))
        )
        stand = next(
            Position(placement.y + dy, placement.x + dx)
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0))
            if navigator._static_walkable(
                Position(placement.y + dy, placement.x + dx)
            )
        )
        return policy, navigator, race_id, placement, stand

    def _board(self, stand, placement, *, lit):
        return Snapshot(
            player(stand.y, stand.x, hp=300, max_hp=300),
            {stand: grid(stand.y, stand.x), placement: grid(placement.y, placement.x)},
            [],
            floor_key=FLOOR,
            inventory=[item("w", TVAL_WAND, SV_WAND_STONE_TO_MUD, charges=3)],
            can_see_own_grid=lit,
            light_radius=1 if lit else 0,
        )

    def _residual_unconfirmed(self, policy, board, placement, race_id):
        """The residual sweep's own test of one placement (post-fix helper)."""
        grid_state = board.grid_at(placement)
        return not (
            grid_state is not None
            and grid_state.known
            and not grid_state.has_monster
            and policy._quest_cell_confirmed_empty(board, placement, race_id=race_id)
        )

    def test_dark_adjacent_placement_is_not_surveyed(self):
        policy, navigator, race_id, placement, stand = self._setup()
        board = self._board(stand, placement, lit=False)
        self.assertEqual(stand.distance_to(placement), 1)
        self.assertFalse(board.grid_at(placement).in_view)
        policy._q2_phase_key(board, self.profile, navigator)
        surveyed = placement in policy._q2_surveyed_placements
        # 4e34499f: surveyed is True here while the residual (in_view only)
        # leaves the same placement unconfirmed.
        self.assertFalse(surveyed)
        self.assertTrue(
            self._residual_unconfirmed(policy, board, placement, race_id)
        )

    def test_lit_adjacent_placement_is_surveyed(self):
        policy, navigator, race_id, placement, stand = self._setup()
        board = self._board(stand, placement, lit=True)
        policy._q2_phase_key(board, self.profile, navigator)
        self.assertIn(placement, policy._q2_surveyed_placements)
        self.assertFalse(
            self._residual_unconfirmed(policy, board, placement, race_id)
        )

    def test_own_grid_in_the_dark_is_surveyed(self):
        policy, navigator, race_id, placement, _stand = self._setup()
        board = self._board(placement, placement, lit=False)
        policy._q2_phase_key(board, self.profile, navigator)
        self.assertIn(placement, policy._q2_surveyed_placements)
        self.assertFalse(
            self._residual_unconfirmed(policy, board, placement, race_id)
        )


LINE_FLOOR = (0, 15, 2)


class Q2LateSitesTest(unittest.TestCase):
    """Breeder, residual and final patrol on a one-row Q2 battlefield."""

    @classmethod
    def setUpClass(cls):
        cls.profile = load_quest_strategies(
            Path(__file__).parent.parent / "strategy" / "quests"
        )[2]

    def _setup(self, *, residual_done):
        battlefield = QuestBattlefield(
            terrain={(1, x): "floor" for x in range(1, 21)},
            monster_placements=(((1, 18), 202),),
        )
        policy = HengbotPolicy(
            quest_strategies={2: self.profile},
            quest_knowledge={2: QuestInfo(2, "The Sewer", 6, 15, 0, battlefield=battlefield)},
        )
        policy._q2_cleared_races.update(self.profile.priority_targets)
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        policy._q2_surveyed_placements.update(
            placement
            for _, _, placements in Q2_POST_BLUE_SEQUENCE
            for placement in placements
        )
        policy._q2_surveyed_placements.add(Position(1, 18))
        policy._q2_residual_surveyed_races.update(
            race for race in Q2_RESIDUAL_SWEEP_RACES
            if residual_done or race != 202
        )
        navigator = QuestFloorNavigator(2, battlefield)
        navigator.reset_for_floor(LINE_FLOOR)
        return policy, navigator

    def _board(self, at, *, lit, light_radius=1):
        return Snapshot(
            player(1, at, hp=300, max_hp=300),
            {Position(1, x): grid(1, x) for x in range(1, 21)},
            [],
            floor_key=LINE_FLOOR,
            can_see_own_grid=lit,
            light_radius=light_radius if lit else 0,
        )

    def test_breeder_last_seen_adjacent_in_the_dark_is_recommitted(self):
        policy, navigator = self._setup(residual_done=True)
        policy._q2_breeder_last_seen = Position(1, 18)
        policy._q2_breeder_last_seen_floor = LINE_FLOOR
        policy._q2_phase_key(self._board(17, lit=False), self.profile, navigator)
        # 4e34499f: distance 1 cleared the unseen cell.
        self.assertEqual(policy._q2_breeder_last_seen, Position(1, 18))
        self.assertEqual(policy.last_reason, "quest-strategy:q2-breeder-recommit")

    def test_breeder_last_seen_adjacent_in_light_is_cleared(self):
        policy, navigator = self._setup(residual_done=True)
        policy._q2_breeder_last_seen = Position(1, 18)
        policy._q2_breeder_last_seen_floor = LINE_FLOOR
        policy._q2_phase_key(self._board(17, lit=True), self.profile, navigator)
        self.assertIsNone(policy._q2_breeder_last_seen)

    def test_residual_placement_lit_without_view_flag_is_confirmed(self):
        policy, navigator = self._setup(residual_done=False)
        # Own grid lit, placement two cells away inside light radius 2 with
        # line of sight, no view flag on the wire (the 10-02 capture shape).
        policy._q2_phase_key(
            self._board(16, lit=True, light_radius=2), self.profile, navigator
        )
        self.assertEqual(policy.last_reason, "quest-strategy:q2-residual-202-clear")

    def test_residual_placement_dark_and_unseen_stays_unconfirmed(self):
        policy, navigator = self._setup(residual_done=False)
        policy._q2_phase_key(self._board(17, lit=False), self.profile, navigator)
        self.assertNotIn(202, policy._q2_residual_surveyed_races)

    def test_final_patrol_records_lit_cells_without_view_flag(self):
        policy, navigator = self._setup(residual_done=True)
        policy._q2_phase_key(
            self._board(10, lit=True, light_radius=2), self.profile, navigator
        )
        # 4e34499f recorded only in_view cells (none on this wire).
        self.assertTrue(
            {Position(1, 8), Position(1, 9), Position(1, 11), Position(1, 12)}
            <= policy._q2_final_patrol_visited
        )
        self.assertNotIn(Position(1, 13), policy._q2_final_patrol_visited)


class Q34SourceAndSweepTest(unittest.TestCase):
    """Q34 final source and placement sweep without view flags."""

    @classmethod
    def setUpClass(cls):
        if REAL_QUEST_DEFINITIONS is None:
            raise unittest.SkipTest("real Hengband quest definitions are unavailable")
        profiles = load_quest_strategies(
            Path(__file__).parent.parent / "strategy" / "quests"
        )
        plan = dict(profiles[34].engagement_plan)
        plan.pop("opening_light", None)
        from dataclasses import replace
        cls.profile = replace(profiles[34], engagement_plan=plan)
        cls.q34 = load_quest_knowledge(REAL_QUEST_DEFINITIONS)[34]

    def _policy(self):
        stationary = MonraceKnowledge(10, 110, False, False, flags=frozenset({"NEVER_MOVE"}))
        policy = HengbotPolicy(
            quest_strategies={34: self.profile},
            quest_knowledge={34: self.q34},
            monrace_knowledge={
                107: stationary,
                243: stationary,
                174: MonraceKnowledge(10, 110, False, False),
            },
        )
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15), (107, 9, 11), (107, 11, 9),
        }
        return policy

    def _board(self, at, cells, *, lit, light_radius=2):
        return Snapshot(
            player(*at),
            {Position(*cell): grid(*cell) for cell in cells},
            [],
            floor_key=(0, 5, 34),
            can_see_own_grid=lit,
            light_radius=light_radius,
        )

    def test_final_source_two_cells_away_in_light_is_cleared(self):
        policy = self._policy()
        board = self._board(
            (3, 15), [(3, 13), (3, 14), (3, 15), (11, 2)], lit=True
        )
        policy._build_grid_index(board)
        policy._approved_quest_strategy_key(board, [], [])
        self.assertEqual(policy.last_reason, "quest-strategy:final-source-cleared")

    def test_sweep_marks_lit_cell_without_view_flag(self):
        policy = self._policy()
        policy._quest_strategy_surveyed_placements[34] = {Position(3, 13)}
        board = self._board(
            (3, 15), [(3, 13), (3, 14), (3, 15), (3, 16), (3, 17), (11, 2)], lit=True
        )
        policy._build_grid_index(board)
        policy._approved_quest_strategy_key(board, [], [])
        surveyed = policy._quest_strategy_surveyed_placements[34]
        self.assertIn(Position(3, 17), surveyed)


if __name__ == "__main__":
    unittest.main()
