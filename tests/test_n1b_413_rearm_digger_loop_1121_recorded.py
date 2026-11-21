"""n1-b life-413 2026-11-21 19:02 (Angband 12F): the digger swap's strip undone on every next board.

Recorded: two boards of the stall (tests/fixtures/n1b-413-rearm-digger-loop-1121, the incident
capture 20261121-190207-stall-floor-dwell-melee-rearm-empty-hand, bot main db36f1744).  The last
194 decisions alternate stuck:walled-off-wield-digger 'ta' (the swap strips the Long Sword before
it wields the Dwarven pick, _wield_digging_tool_key: do_cmd_wield's prompts depend on the occupied
hands) and melee:rearm-empty-hand 'wq' (the sword wielded back), 97 each, nothing in view.  On the
board after each strip the breakout's restore rung (_breakout_restore_weapon_key, ladder_opening,
asked first) read "no digger worn" as the swap over and cleared the dig floor; with it cleared
mining_loadout.swap_abandoned held (no mining run, no return latched) and the re-arm
(mining_loadout.rollback_key, ladder_pre_combat) wielded the sword back before the digger came.

Pinned: the strip opens one owned transaction (mining_loadout.swap_in_progress), ended only by the
game's state -- the digger worn, the floor left -- or by the swap's own abort (an awake hostile in
view: the swap wields the weapon back itself); no count of moves.  Driven through the two producers
in the ladder's order on the recorded boards: after the strip the restore rung keeps the dig floor
and the pre-combat rung answers the digger's wield, however many boards pass; with an awake
hostile the swap aborts and re-arms; no decision makes the opposite weapon-slot action of the one
before it while the swap holds the hand.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import mining_loadout
from hengbot.model import MonsterState, Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from support.q25_house import RACES

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-rearm-digger-loop-1121" / "boards.json.xz"
WIELD_REASON = "stuck:walled-off-wield-digger"
STRIP, REARM = "ta", "wq"   # the recorded keys: the sword off (main hand 'a'), the sword back (pack 'q')


def boards():
    return [parse_snapshot(raw, RACES) for raw in json.loads(lzma.decompress(FIXTURE.read_bytes()))]


class N1b413RearmDiggerLoopRecordedTest(unittest.TestCase):
    def setUp(self):
        self.armed, self.stripped = boards()
        self.policy = HengbotPolicy()
        self.policy._monrace_knowledge = RACES
        self.policy._decision_sequence = 100

    def strip(self):
        """Decision 1 on the armed board: the walled-off dig's swap strips the sword ('ta') and
        marks its floor (walkout_dig.dig_step_key)."""
        policy = self.policy
        key = policy._wield_digging_tool_key(self.armed, WIELD_REASON)
        policy._breakout_dig_floor = self.armed.floor_key
        return key

    def ladder(self, board):
        """The two producers that act on the hand, in the ladder's order (ladder_opening's restore
        rung, then ladder_pre_combat's re-arm): the first key wins, as in ``_decide``."""
        policy = self.policy
        policy._decision_sequence += 1
        for rung in (policy._breakout_restore_weapon_key, policy._mining_loadout_rollback_key):
            key = rung(board)
            if key is not None:
                return key, policy.last_reason
        return None, None

    def test_the_recorded_boards(self):
        self.assertTrue(mining_loadout.worn_in_slot(self.armed, "main_hand").name.startswith("ロング・ソード"))
        self.assertIsNone(mining_loadout.worn_in_slot(self.stripped, "main_hand"))
        for board in (self.armed, self.stripped):
            self.assertTrue(any(item.is_digging_tool for item in board.inventory))
            self.assertFalse(board.visible_monsters)

    def test_the_swap_wields_the_digger_however_many_boards_pass(self):
        self.assertEqual(self.strip(), STRIP)
        for _ in range(10):
            key, reason = self.ladder(self.stripped)
            self.assertNotEqual(key, REARM)
            self.assertEqual(reason, WIELD_REASON)
            self.assertTrue(key.startswith("w"), key)
            self.assertEqual(self.policy._breakout_dig_floor, self.stripped.floor_key)

    def test_an_awake_hostile_aborts_the_swap_by_its_own_rearm(self):
        self.assertEqual(self.strip(), STRIP)
        board = self.stripped
        # DECLARED CONSTRUCTED: an awake hostile in view three cells from the player on the
        # stripped board (the abort's reason; the recorded board shows none).
        here = board.player.position
        cell = Position(here.y, here.x + 3)
        awake = MonsterState(index=900, position=cell, hp=30, max_hp=30, distance=3,
                             friendly=False, pet=False, name="orc", race_id=118, level=11)
        board = replace(board, visible_monsters=[awake])
        key, reason = self.ladder(board)
        self.assertEqual((key, reason), (REARM, mining_loadout.REARM_REASON))
        self.assertFalse(mining_loadout.swap_in_progress(self.policy, board))

    def test_no_opposite_weapon_slot_actions_in_a_row(self):
        """The invariant over the recorded pair: the decision after the strip is never the
        weapon's re-arm while nothing aborts the swap; the swap's digger wield comes instead."""
        decisions = [self.strip()]
        decisions.append(self.ladder(self.stripped)[0])
        for before, after in zip(decisions, decisions[1:]):
            self.assertFalse(before == STRIP and after == REARM, decisions)


if __name__ == "__main__":
    unittest.main()
