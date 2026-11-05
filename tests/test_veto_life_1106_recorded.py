"""A retreat's veto remembers the monster it was set for and is lifted when that monster is gone.

Owner 2026-11-06 「脅威が見えなくなったら消す」: died, changed shape, or not seen for a while (the
hunt's 1,000 game turns, me_powers.HUNT_REDETECT_GAME_TURNS).  A veto set for no monster stays.
retreat_veto_life.

Recorded: n1-b life-317, Angband 50F, RANDOM quest 40 (tests/test_quest_loop_dwell_1106_recorded,
the fixture quest-loop-dwell-1106).  Five threat:avoid-engagement retreats from the half-giant
(index 76, race 1301) left the column (3..7, 93); it was last shown by a detection at 2345271,
and the stop's last board (2429114) shows it nowhere: 84,000 game turns later.  On that board the
column is lifted and the search loop walks on with no Teleportation.

DECLARED CONSTRUCTED: the stop's board moved to a game turn the window names, the half-giant shown
on it (``shown``) or shown with another race, its kill or shape-change line with it gone from the
board after the one that showed it, and the column claimed once more with no monster.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_quest_loop_dwell_1106_recorded import (
    COLUMN, HALF_GIANT, VETOES_DONE_TURN, WalledOffBoards, shown,
)

from hengbot import quest_target_search, retreat_enclosure, retreat_veto_life

HALF_GIANT_KEY = (HALF_GIANT["index"], HALF_GIANT["race_id"])
LAST_SHOWN_TURN = 2345271


def message(line):
    def edit(raw):
        raw["messages"] = [*raw.get("messages", []), line]
    return edit


def as_race(race):
    def edit(raw):
        raw["detected_monsters"] = [*raw.get("detected_monsters", []), dict(HALF_GIANT, race_id=race)]
    return edit


class VetoLife(WalledOffBoards):
    def after_the_retreats(self):
        replay, *_ = self.replay()
        return replay

    def at_turn(self, replay, turn, edit=None):
        """The stop's last board moved to game turn ``turn`` (DECLARED)."""
        return self.at_the_stop(replay, later=turn - self.stop_raw()["turn"], edit=edit)

    def column_stands(self, replay):
        return COLUMN <= replay.policy._engagement_owned_avoid_cells

    def test_the_column_is_set_for_the_half_giant(self):
        replay, *_ = self.replay(lambda board, _reason: board.turn >= VETOES_DONE_TURN)
        life = getattr(replay.policy, retreat_veto_life.MEMORY)
        self.assertEqual({cell: life.owners[cell] for cell in COLUMN},
                         {cell: {HALF_GIANT_KEY} for cell in COLUMN})

    def test_on_the_recorded_stop_the_unseen_half_giants_column_is_lifted(self):
        replay = self.after_the_retreats()
        self.assertEqual(getattr(replay.policy, retreat_veto_life.MEMORY)
                         .threats[HALF_GIANT_KEY].last_seen, LAST_SHOWN_TURN)
        board, _key, reason = self.at_the_stop(replay)
        self.assertFalse(COLUMN & replay.policy._engagement_owned_avoid_cells)
        self.assertFalse(COLUMN & replay.policy._engagement_avoid_cells)
        self.assertFalse(retreat_enclosure.holds_ground(replay.policy, board))
        self.assertEqual(reason, quest_target_search.LOOP_REASON)

    def test_the_column_stands_through_the_window_and_is_lifted_at_its_end(self):
        replay = self.after_the_retreats()
        _board, _key, reason = self.at_turn(
            replay, LAST_SHOWN_TURN + retreat_veto_life.UNSEEN_GAME_TURNS - 1)
        self.assertTrue(self.column_stands(replay))
        self.assertEqual(reason, retreat_enclosure.TELEPORT_REASON)
        self.at_turn(replay, LAST_SHOWN_TURN + retreat_veto_life.UNSEEN_GAME_TURNS)
        self.assertFalse(COLUMN & replay.policy._engagement_owned_avoid_cells)

    def test_shown_with_another_race_the_column_is_lifted(self):
        replay = self.after_the_retreats()
        self.at_turn(replay, LAST_SHOWN_TURN + 10, as_race(HALF_GIANT["race_id"] + 1))
        self.assertFalse(COLUMN & replay.policy._engagement_owned_avoid_cells)

    def lifted_by_a_line(self, line):
        replay = self.after_the_retreats()
        self.at_turn(replay, LAST_SHOWN_TURN + 10, shown)
        self.assertTrue(self.column_stands(replay))
        self.at_turn(replay, LAST_SHOWN_TURN + 20, message(line))
        return replay

    def test_its_kill_line_lifts_the_column(self):
        replay = self.lifted_by_a_line("ハーフジャイアントを倒した。")
        self.assertFalse(COLUMN & replay.policy._engagement_owned_avoid_cells)

    def test_its_shape_change_line_lifts_the_column(self):
        replay = self.lifted_by_a_line("ハーフジャイアントが変身した！")
        self.assertFalse(COLUMN & replay.policy._engagement_owned_avoid_cells)

    def test_another_monsters_kill_line_does_not(self):
        replay = self.lifted_by_a_line("ブルー・ホラーを倒した。")
        self.assertTrue(self.column_stands(replay))

    def test_its_kill_line_out_of_view_does_not(self):
        """Not shown on the board before, the line may name another of its race."""
        replay = self.after_the_retreats()
        self.at_turn(replay, LAST_SHOWN_TURN + 20, message("ハーフジャイアントを倒した。"))
        self.assertTrue(self.column_stands(replay))

    def test_a_column_also_claimed_for_no_monster_stays(self):
        replay = self.after_the_retreats()
        replay.policy._claim_engagement_avoid_cells(COLUMN)
        _board, _key, reason = self.at_the_stop(replay)
        self.assertTrue(self.column_stands(replay))
        self.assertEqual(reason, retreat_enclosure.TELEPORT_REASON)


if __name__ == "__main__":
    unittest.main()
