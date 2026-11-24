"""The 100F outflank opens its way with Stone to Mud when no wait cell is in walking reach (n1-c
life-221, Angband 100F, 2026-11-24 13:02:10-26, after a restart, the halt
stationary:exhausted:angband-finale:hold).

Owner 2026-11-24, the question about the exit beside the player and no wait cell within the 10
reachable cells, the chosen answer (verbatim): 「岩石溶解で道を開けて待つマスへ行く — 届く10マスの周りの
溶かせる壁を溶かして、出口から距離3以上で射線が通るマスへの道を作る。」.  After the restart the map memory
held only the ten floor cells the board showed around (42,48) (the map, map_area, remembers walls,
not floors), the outflank's exit read (43,47) beside the player and no wait cell was found
(no_stand "... reach=10 outflank=no-cell exit=(43,47)"); the battle held to the bound.  The way out
of the vault around the Serpent of Chaos (44,50) is its south corridor onto row 59.

Fixture finale-stalemate-melt-n1c-221-1124 (tests/extract_finale_stalemate_melt_1124_fixture.py):
the halt capture's player_turn boards from the restart's first board to the halt, 129 boards,
replayed open-loop (tests/support/finale_416: DECLARED RECONSTRUCTED device lists and expedition
mark; DECLARED: the expedition's Restore Mana count held at 0 and the Stone to Mud uses per wall
cleared on every board).  DECLARED RECONSTRUCTED: the battle the restart's checkpoint restored
(phase battle, last seen (44,50), the Serpent's cell on every board).  Then, DECLARED CONSTRUCTED,
the halt's last board closed-loop: a step key moves the player one cell, a Stone to Mud key makes
the wall it is aimed at (the next cell in its direction) floor; the Serpent stays on (44,50).
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import unittest

from hengbot import angband_finale, angband_finale_battle, sealed_pocket
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_DELTAS, WAIT_KEY
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-stalemate-melt-n1c-221-1124.jsonl.gz"
HALT_CELL = (42, 48)
SERPENT = (44, 50)
CLOSED_LOOP_BOARDS = 60
FLOOR_PALETTE = [1, 1, 416, 1]  # the board's own palette entry of a lit-less floor (feat 1)


class FinaleStalemateMeltRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        raw_boards = finale_416.boards(FIXTURE)
        held_policy = []

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0
            sealed_pocket._memory(policy, board).uses.clear()
            if not held_policy:
                battle = angband_finale_battle.battle(policy, board)
                battle.phase = angband_finale_battle.BATTLE
                battle.last_seen = SERPENT
            held_policy[:] = [policy]

        cls.recorded = finale_416.drive(raw_boards, monrace, prepare=prepare)
        policy = held_policy[0]
        cls.plan = getattr(getattr(policy, angband_finale_battle.MEMORY), "outflank", None)
        # The closed loop, on the drive's policy (its directory is gone: no file is written by
        # these decisions' owners).
        raw = copy.deepcopy(raw_boards[-1])
        palette = raw["grid_map"]["palette"]
        floor = palette.index(FLOOR_PALETTE)
        walk = []
        for _ in range(CLOSED_LOOP_BOARDS):
            raw["turn"] += 2
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), monrace))
            policy._me_device_lists = finale_416.device_lists(board.turn)
            angband_finale.memory(policy).restore_mana_used = 0
            sealed_pocket._memory(policy, board).uses.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            reason = policy.last_reason
            here = (board.player.position.y, board.player.position.x)
            walk.append((board.turn, here, key, reason))
            if key:
                policy.confirm_key_posted(key)
            if reason == angband_finale_battle.OUTFLANK_REASON and key in DIRECTION_DELTAS:
                raw["player"]["y"] += DIRECTION_DELTAS[key][0]
                raw["player"]["x"] += DIRECTION_DELTAS[key][1]
            elif (reason or "").startswith(angband_finale_battle.MELT_REASON):
                delta = DIRECTION_DELTAS[key[-1]]
                raw["grid_map"]["runs"].append([here[0] + delta[0], here[1] + delta[1], 1, floor])
        cls.walk = walk

    def test_a_plan_is_drawn_with_stone_to_mud(self):
        holds = [row for row in self.recorded if row[1] == HALT_CELL
                 and row[3] == angband_finale_battle.HOLD_REASON]
        # The recorded run: 120 holds on (42,48), then the stop (revert: 126 in this replay).
        self.assertLessEqual(len(holds), angband_finale_battle.STALEMATE_BOARDS, holds[-3:])
        self.assertIsNotNone(self.plan)
        wait, exit_cell, aim, melt = self.plan
        self.assertEqual(aim, SERPENT)
        self.assertTrue(melt)
        # The exit is out of the vault (its south corridor onto row 59), not beside the player.
        self.assertGreaterEqual(exit_cell[0], 59, self.plan)
        self.assertGreaterEqual(game_distance(Position(*wait), Position(*exit_cell)),
                                angband_finale_battle.STAND_MIN_DISTANCE)
        self.assertLessEqual(game_distance(Position(*wait), Position(*SERPENT)),
                             angband_finale_battle.TELEPATHY_RANGE)
        walks = [row for row in self.recorded if row[3] == angband_finale_battle.OUTFLANK_REASON]
        self.assertTrue(walks)

    def test_the_way_reaches_the_wait_cell_and_waits_there(self):
        wait = self.plan[0] if self.plan else None
        cells = [row[1] for row in self.walk]
        self.assertIn(wait, cells, self.walk)
        arrived = cells.index(wait)
        # A map on the way (sealed_pocket): the constructed board shows no floor where the player
        # stepped into the cells it did not show; the game would.
        moves = {row[3] for row in self.walk[:arrived] if "map-area" not in row[3]}
        self.assertLessEqual(moves, {angband_finale_battle.OUTFLANK_REASON,
                                     angband_finale_battle.MELT_REASON + ":absorbed-power"},
                             self.walk[:arrived])
        self.assertTrue(all(game_distance(Position(*cell), Position(*SERPENT))
                            > angband_finale_battle.TELEPORT_WITHIN for cell in cells), cells)
        waits = self.walk[arrived:]
        self.assertTrue(all(row[2] == WAIT_KEY and row[3] == angband_finale_battle.HOLD_REASON
                            for row in waits), waits)


if __name__ == "__main__":
    unittest.main()
