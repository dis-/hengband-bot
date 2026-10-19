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
from hengbot.quest_knowledge import load_quest_knowledge
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


if __name__ == "__main__":
    unittest.main()
