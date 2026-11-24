"""The 100F battle's 周辺感知 with no stand shown is cast once per area, not on every cell (n1-c
life-221, Angband 100F, 2026-11-24 11:02:37-55, then the halt 11:04:40
stationary:exhausted:angband-finale:hold).

Owner (verbatim): 「99F 100Fはサーチ禁止。必要なら感知すること。」 and 「長期戦になる99F 100Fにおいて
無駄な行動は許されない」.  After the 11:02:30 restart the Serpent of Chaos was shown by telepathy in
the permanent rock east of the player (no stand on any of its rays, no_stand "rays=0"); the close-in
walk from (59,53) to (42,48) cast the map (me-power:sealed-pocket:map-area) on every cell it
reached, 46 maps alternating with the steps (_resurvey_key keyed by the one cell it was last cast
on).

Fixture finale-resurvey-n1c-221-1124: every player_turn board of the halt capture's snapshot ring
from the restart's first board (turn 6266122) to the halt (6268575), 1046 boards
(tests/extract_finale_resurvey_1124_fixture.py), replayed open-loop (tests/support/finale_416:
DECLARED RECONSTRUCTED device lists and expedition mark; DECLARED: the expedition's Restore Mana
count held at 0 and the Stone to Mud uses per wall cleared on every board, as in
tests/test_finale_hold_loop_1124_recorded.py).  DECLARED RECONSTRUCTED: the battle the restart's
checkpoint restored (the decision record of 11:02:32: phase battle, last seen (26,52), the stand
(35,52) on the Serpent's column).
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale, angband_finale_battle, sealed_pocket
from hengbot.model import game_distance, Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-resurvey-n1c-221-1124.jsonl.gz"
WALK = (6266232, 6266646)  # 11:02:37 (59,53) to 11:02:55 (42,48): the recorded map on every cell
MAP = "map-area"


class FinaleResurveyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        seen = []

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0
            sealed_pocket._memory(policy, board).uses.clear()
            if not seen:
                held = angband_finale_battle.battle(policy, board)
                held.phase = angband_finale_battle.BATTLE
                held.last_seen = (26, 52)
                held.stand = angband_finale_battle.Stand((35, 52), (26, 52), (1, 0), 9)
            seen.append(board.turn)

        cls.rows = finale_416.drive(finale_416.boards(FIXTURE), monrace, prepare=prepare)
        cls.walk = [row for row in cls.rows if WALK[0] <= row[0] <= WALK[1]]

    def test_the_map_is_not_cast_on_every_cell_of_the_walk(self):
        # The map after the *Destruction* at the second teleport's landing is the owner's
        # 「破壊を使用した後は周辺感知で地形把握する」, not this one.
        maps = [row for row in self.walk if MAP in (row[3] or "")
                and "after-destruction" not in row[3]]
        # The recorded run: 46 maps on these boards, one per cell of the walks (revert: 30+).
        self.assertLessEqual(len(maps), 3, maps)

    def test_no_two_maps_within_the_spacing(self):
        maps = [row[1] for row in self.rows if MAP in (row[3] or "")
                and "after-destruction" not in (row[3] or "")]
        close = [(a, b) for n, a in enumerate(maps) for b in maps[n + 1:]
                 if game_distance(Position(*a), Position(*b))
                 < angband_finale_battle.RESURVEY_SPACING]
        self.assertEqual(close, [], maps)

    def test_the_walk_still_closes_in(self):
        # The steps of the close-in walk are kept (the replay is open-loop: the recorded cells).
        steps = [row for row in self.walk if row[3] == angband_finale_battle.APPROACH_REASON]
        self.assertTrue(steps, self.walk)


if __name__ == "__main__":
    unittest.main()
