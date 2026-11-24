"""The 100F stalemate's *Destruction* with the target in the circle (n1-c life-221, Angband 100F,
2026-11-24 13:39:23-36, after a restart, the halt stationary:exhausted:angband-finale:hold on the
outflank's wait cell).

Owner 2026-11-24, the stalemate (the target in a permanent-rock dead end, no line from anywhere,
it does not come out), the chosen answer (verbatim): 「サーペントを巻き込んで *破壊* で飛ばす —
サーペントを範囲に入れて *破壊* を使う。クエストの標的は消えず、全回復して階のどこかへ飛ばされるので、
囲みの外へ出る見込みが高い。全回復するのは、まだ被害を与えていない今なら損が無い。飛ばした後は着いた所で
全感知して探す。」.  The player walked from (42,48) to the wait cell (59,45) (13:39:27, game turn
6268924) and held there 400 game turns while the Serpent of Chaos moved from (44,50) to (45,51),
straight at the player, and stopped on the permanent rock; the hold's bound stopped the run.

Fixture finale-stalemate-destruction-n1c-221-1124
(tests/extract_finale_stalemate_destruction_1124_fixture.py): the halt capture's player_turn
boards from the restart's first board to the halt, 193 boards, replayed open-loop
(tests/support/finale_416, with the DECLARED state of tests/test_finale_resurvey_1124_recorded.py:
device lists, expedition mark, Restore Mana count, Stone to Mud uses).  DECLARED RECONSTRUCTED: the
battle the restart's checkpoint restored (phase battle, last seen (44,50), the outflank plan
[[59,45],[59,54],[44,50],True] of the decision record of 13:39:25).  DECLARED CONSTRUCTED for the
hurt case: the same boards with the Serpent's health band "lightly_wounded".
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import unittest

from hengbot import angband_finale, angband_finale_battle, destruction_use, sealed_pocket
from hengbot.model import Position, game_distance
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-stalemate-destruction-n1c-221-1124.jsonl.gz"
WAIT_CELL = (59, 45)
ARRIVAL = 6268924  # 13:39:27, the first board on the wait cell
HALT = 6269324     # 13:39:36, the recorded stop
SERPENT_RACE = 862
STALEMATE = destruction_use.REASON + angband_finale_battle.STALEMATE_SUFFIX


def _drive(monrace, boards):
    held_policy = []

    def prepare(policy, board):
        angband_finale.memory(policy).restore_mana_used = 0
        sealed_pocket._memory(policy, board).uses.clear()
        if not held_policy:
            battle = angband_finale_battle.battle(policy, board)
            battle.phase = angband_finale_battle.BATTLE
            battle.last_seen = (44, 50)
            battle.outflank = ((59, 45), (59, 54), (44, 50), True)
        held_policy[:] = [policy]

    rows = finale_416.drive(boards, monrace, prepare=prepare)
    return rows, getattr(held_policy[0], angband_finale_battle.MEMORY)


def _hurt(boards):
    hurt = copy.deepcopy(boards)
    for board in hurt:
        for kind in ("visible_monsters", "detected_monsters"):
            for monster in board.get(kind) or ():
                if monster.get("race_id") == SERPENT_RACE:
                    monster["health"] = "lightly_wounded"
    return hurt


class FinaleStalemateDestructionRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        boards = finale_416.boards(FIXTURE)
        cls.rows, cls.battle = _drive(monrace, boards)
        cls.hurt_rows, cls.hurt_battle = _drive(monrace, _hurt(boards))

    def test_the_destruction_takes_the_serpent_in_after_the_wait(self):
        casts = [row for row in self.rows if (row[3] or "").startswith(STALEMATE)]
        # The recorded run: holds on (59,45) to the stop at 13:39:36 (revert: no cast).
        self.assertTrue(casts, [row[:4] for row in self.rows[-5:]])
        turn, cell, _key, reason, _phase, _seen, target = casts[0]
        self.assertEqual(cell, WAIT_CELL)
        self.assertGreaterEqual(turn - ARRIVAL, angband_finale_battle.OUTFLANK_WAIT_GAME_TURNS)
        self.assertLess(turn, HALT)
        # 17 from the Serpent: beyond the staff's sure radius 13, within the powered one's 18.
        distance = game_distance(Position(*cell), Position(*target))
        self.assertGreater(distance, destruction_use.GUARANTEED_RADIUS)
        self.assertLessEqual(distance, angband_finale_battle.POWERED_SURE)
        self.assertTrue(reason.endswith(destruction_use.POWERED_SUFFIX), reason)

    def test_the_cast_asks_the_full_detection(self):
        self.assertTrue(self.battle.detect_due)
        self.assertIsNone(self.battle.outflank)

    def test_a_hurt_target_is_not_taken_in(self):
        casts = [row for row in self.hurt_rows if (row[3] or "").startswith(STALEMATE)]
        self.assertEqual(casts, [])
        self.assertIn("destruction=hurt", self.hurt_battle.no_stand or "")


if __name__ == "__main__":
    unittest.main()
