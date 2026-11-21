"""n1-b life-411 2026-11-21 13:58 (Angband 99F): the stand's last wall opened the line on Oberon.

Recorded: three boards of the 99F battle (tests/fixtures/n1b-411-finale-initiative-1121, the
incident capture 20261121-135909-loop-detected, bot main b9efeeca0).  The stand was (8,76) on
Oberon's row, Oberon at (8,60), 16 grids west.  Ten melts (turn 11355723 on) opened the row to
one wall, (8,61); the stand then held ten boards (the old rule: the last wall waits while the
target is on the ray) and at turn 11355767 melted it anyway.  The melt took the turn; the next
board shows the player touched and drained (「触られた。」「不器用になった気がしたが…」) and the
battle left by Teleportation without a shot.

Owner 2026-11-21 (verbatim, LOCKED): 「岩石溶解の消費量は問題ではなく、溶かした時に先手を取られて何も
出来ず離脱している場面が問題である。」 and the directive's 「可能なら相手の移動後に射線が通るようにして、先手を
取ること」.  The rule: a wall whose melting would leave a line of fire from the stand to the
target where it stands (the player's projection path with that wall open, any angle, within the
spells' 18 grids) is never melted: it is kept while the target's own move may open a line (then
the hasted player, 45 energy a game turn against Oberon's 40 at +35 -- core/speed-table.cpp --
fires first), and past LAST_WALL_HOLD the stand is given up for that target cell.  Pinned on the
recorded boards: the first melt (no line) and the first hold are as before; the melt that opened
the line is not made.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import angband_finale_battle as battle
from hengbot.model import InventoryItem, Position, SV_WAND_STONE_TO_MUD, TVAL_WAND, parse_snapshot
from hengbot.policy import HengbotPolicy
from support.q25_house import RACES

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-finale-initiative-1121" / "boards.json.xz"
STAND, OBERON = (8, 76), (8, 60)
LAST_WALL = Position(8, 61)


def boards():
    # DECLARED CONSTRUCTED: a charged Stone to Mud wand in the pack (the recorded melts were the
    # absorbed power's, which a fresh policy does not hold); the melt is the same decision.
    wand = InventoryItem(slot="w", name="岩石溶解の魔法棒", count=1, tval=TVAL_WAND,
                         sval=SV_WAND_STONE_TO_MUD, aware=True, known=True, fully_known=True,
                         charges=10, pval=10)
    recorded = json.loads(lzma.decompress(FIXTURE.read_bytes()))
    return [replace(board, inventory=[*board.inventory, wand])
            for board in (parse_snapshot(raw, RACES) for raw in recorded)]


class N1b411FinaleInitiativeRecordedTest(unittest.TestCase):
    def setUp(self):
        self.first_melt, self.first_hold, self.opening_melt = boards()

    def decide(self, board, held_boards):
        policy = HengbotPolicy()
        policy._monrace_knowledge = RACES
        held = battle.battle(policy, board)
        held.phase = battle.BATTLE
        # DECLARED CONSTRUCTED: the stand the recorded battle stood on, with its boards held.
        held.stand = battle.Stand(STAND, OBERON, (0, 1), 16, held=held_boards)
        target = battle.target_monster(board)
        key = battle._stand_key(policy, board, held, target)
        return key, policy.last_reason, held

    def test_the_recorded_geometry(self):
        for board in (self.first_melt, self.first_hold, self.opening_melt):
            self.assertEqual((board.player.position.y, board.player.position.x), STAND)
            target = battle.target_monster(board)
            self.assertEqual((target.position.y, target.position.x), OBERON)
        here = Position(*STAND)
        self.assertTrue(battle._opens_line(HengbotPolicy(), self.opening_melt, here, LAST_WALL,
                                           Position(*OBERON)))

    def test_a_melt_that_opens_no_line_goes_on(self):
        key, reason, held = self.decide(self.first_melt, 0)
        self.assertEqual(reason, battle.MELT_REASON)
        self.assertTrue(key)

    def test_the_last_wall_waits_for_the_target(self):
        key, reason, held = self.decide(self.first_hold, 0)
        self.assertEqual(reason, battle.HOLD_REASON)

    def test_the_melt_that_opens_the_line_on_the_target_is_never_made(self):
        key, reason, held = self.decide(self.opening_melt, battle.LAST_WALL_HOLD)
        self.assertNotEqual(reason, battle.MELT_REASON)
        self.assertIn((STAND, OBERON), held.refused)
        self.assertNotEqual(held.stand and held.stand.cell, STAND)


if __name__ == "__main__":
    unittest.main()
