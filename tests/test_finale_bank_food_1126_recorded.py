"""The 100F battle of a Zombie eats its food wands' charges ahead, below full, so that UN_POWER
blows draining the pack's wands do not starve the fight out (n1-c life-222, Angband 100F,
2026-11-26 10:00-10:04).

Owner 2026-11-26 (verbatim): 「また勝利直前で帰った。何を学習したのか」.

The recorded run: the expedition carried the three food wands of finale_prep's food step
(謎の魔法棒 {@E1} 24, {@E2} 24, {@E3} 23 charges: 71 charges, +5000 food each, cmd-eat.cpp
exe_eat_charge_of_magic_device).  One charge was eaten (hungry at turn 12320551, eaten at
12320554); then UN_POWER blows (「ザックからエネルギーが吸い取られた！」) drained the stacks one by
one: {@E2} by 竜殺しの始祖『ミラーク』 at 12320596, {@E1} by ワープ・デーモン at 12324020, {@E3} at
12324520.  Hungry again at 12325001 (5000 food in 4447 game turns) with every wand at 0
charges, the battle recalled (``starving_out``, recall_why ["starving-out"]) with the Serpent of
Chaos last shown almost dead (turn 12324911; badly wounded at 12325016 after the recall was read).

Fixture finale-bank-food-n1c-222-1126 (tests/extract_finale_bank_food_1126_fixture.py): the
floor's player_turn boards from the arrival to turn 12320600 and from 12324500 to 12325010,
replayed open-loop (tests/support/finale_416: DECLARED RECONSTRUCTED device lists and expedition
mark; DECLARED: the expedition's Restore Mana count held at 0).
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale, angband_finale_battle as fb
from hengbot.model import Position, game_distance
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-bank-food-n1c-222-1126.jsonl.gz"
WINDOW = 12324500
FIRST_HUNGER = 12320551
FIRST_DRAIN = 12320596
LAST_DRAIN = 12324520
STARVED = 12325001
TVAL_WAND = 65
SV_WAND_WONDER = 24


def _charged_food_slots(board) -> set:
    return {item["slot"] for item in board["inventory"]
            if item["tval"] == TVAL_WAND and item["sval"] == SV_WAND_WONDER
            and item.get("known") and item.get("charges", 0) > 0}


def _nearest_hostile(board):
    here = Position(board["player"]["y"], board["player"]["x"])
    return min((game_distance(here, Position(monster["y"], monster["x"]))
                for monster in board.get("visible_monsters", ())
                if not monster.get("pet") and not monster.get("friendly")), default=None)


class FinaleBankFoodRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        boards = finale_416.boards(FIXTURE)

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0

        split = next(index for index, board in enumerate(boards) if board["turn"] >= WINDOW)
        cls.rows = (finale_416.drive(boards[:split], monrace, prepare=prepare, eat_ahead=True)
                    + finale_416.drive(boards[split:], monrace, prepare=prepare, eat_ahead=True))
        cls.boards = boards
        assert len(cls.rows) == len(boards)

    def _ahead(self):
        return [(board, row) for board, row in zip(self.boards, self.rows)
                if row[3] == fb.BANK_FOOD_REASON]

    def test_the_food_is_eaten_ahead_before_the_first_drain(self):
        turns = [row[0] for _board, row in self._ahead()]
        # Recorded: no eat below full; the first meal at the hunger of 12320551, and the drain
        # of 12320596 (revert: no eat ahead at all).
        self.assertTrue(turns)
        self.assertLess(turns[0], FIRST_HUNGER)
        self.assertLess(turns[0], FIRST_DRAIN)

    def test_the_eat_ahead_takes_a_charged_food_wand_below_full_with_no_hostile_near(self):
        for board, row in self._ahead():
            self.assertEqual(board["player"]["food_state"], "normal", row)
            self.assertEqual(row[2][0], "E", row)
            self.assertIn(row[2][1], _charged_food_slots(board), row)
            nearest = _nearest_hostile(board)
            self.assertTrue(nearest is None or nearest > 4, (row, nearest))

    def test_no_eat_ahead_once_every_food_wand_is_drained(self):
        for board, row in zip(self.boards, self.rows):
            if row[0] > LAST_DRAIN:
                self.assertNotEqual(row[3], fb.BANK_FOOD_REASON, row)

    def test_the_recall_with_nothing_to_eat_is_kept(self):
        # Recorded: hungry with every food wand at 0 charges, the recall (starving-out): kept,
        # the eat ahead is what keeps the food from being drained (revert: unchanged).
        row = next(row for row in self.rows if row[0] == STARVED)
        self.assertEqual(row[3], fb.RECALL_REASON, row)


if __name__ == "__main__":
    unittest.main()
