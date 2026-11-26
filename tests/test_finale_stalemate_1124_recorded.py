"""The 100F battle leaves for the exit side of the target's permanent-rock enclosure when neither
moves (n1-c life-221, Angband 100F, 2026-11-24 11:02:55-11:04:40, the halt
stationary:exhausted:angband-finale:hold).

Owner 2026-11-24, the question 「100Fでサーペントが永久岩に囲まれた行き止まりにいて、テレパシーで距離3に
見えているのに、どのマスからも射線が通らず、お互いに動かない時はどうしますか？」, the chosen answer
(verbatim): 「離れて出口側へ回って待つ — 標的から離れ、永久岩の囲みから出てくる道の先の、射線が取れる所へ
回って待つ。相手が動いて出てきた所で先手を取る。」.  At (42,48) the Serpent of Chaos (KILL_WALL) was shown
by telepathy at (44,50), 3 away, inside a vault's permanent rock: every ray from it ends in permanent
rock (no_stand "rays=0 ... reach=520"); the battle held about 800 boards until the bound.  The
vault's way out is its south corridor: the target's way (over every cell but permanent rock) first
reaches the player's ground at (58,55).

Fixture finale-resurvey-n1c-221-1124 (tests/extract_finale_resurvey_1124_fixture.py): the halt
capture's player_turn boards from the 11:02:30 restart to the halt, replayed open-loop
(tests/support/finale_416, with the DECLARED RECONSTRUCTED state of
tests/test_finale_resurvey_1124_recorded.py).  Then, DECLARED CONSTRUCTED, the halt's last board is
replayed closed-loop: the player moved one cell per step key the policy sends (the Serpent on
(44,50) as recorded, which is what it did on every recorded board).
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, angband_finale_battle, finale_prep, sealed_pocket
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_DELTAS, WAIT_KEY
from tests.support import finale_416
from tests.support.recorded import EDIT, _policy

FIXTURE = "finale-resurvey-n1c-221-1124.jsonl.gz"
HALT_CELL = (42, 48)
SERPENT = (44, 50)
FIRST_HOLD = 6266644  # 11:02:55, the first hold at (42,48)
EXIT = (58, 55)
CLOSED_LOOP_BOARDS = 40


class FinaleStalemateRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        raw_boards = finale_416.boards(FIXTURE)
        directory = TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), monrace)
        first = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw_boards[0]), monrace))
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        held = finale_prep.phase(policy)
        held.lifted, held.step = True, finale_prep.DONE
        decided, owner, seen = [], None, []

        def decide(raw):
            nonlocal owner
            raw = copy.deepcopy(raw)
            if owner:
                raw["_completed_operation_owner"] = owner
            if raw["player"].get("food_state") == "normal":
                # DECLARED CONSTRUCTED: full, the boards after the battle's eat ahead of a food
                # wand's charge (angband_finale_battle ``_bank_food_key``, 2026-11-26).
                raw["player"]["food_state"] = "full"
            board = policy.with_known_skill_exp(parse_snapshot(raw, monrace))
            policy._me_device_lists = finale_416.device_lists(board.turn)
            angband_finale.memory(policy).restore_mana_used = 0
            sealed_pocket._memory(policy, board).uses.clear()
            if not seen:
                battle = angband_finale_battle.battle(policy, board)
                battle.phase = angband_finale_battle.BATTLE
                battle.last_seen = (26, 52)
                battle.stand = angband_finale_battle.Stand((35, 52), (26, 52), (1, 0), 9)
            seen.append(board.turn)
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            owner = policy.last_reason if key else None
            if key:
                policy.confirm_key_posted(key)
            return (board.turn, (board.player.position.y, board.player.position.x), key,
                    policy.last_reason)

        for raw in raw_boards:
            decided.append(decide(raw))
        cls.recorded = decided
        cls.plan = getattr(getattr(policy, angband_finale_battle.MEMORY), "outflank", None)
        # Closed loop from the halt's board: each step key moves the player one cell.
        last = copy.deepcopy(raw_boards[-1])
        walk = []
        for n in range(CLOSED_LOOP_BOARDS):
            last["turn"] += 2
            row = decide(last)
            walk.append(row)
            delta = DIRECTION_DELTAS.get(row[2])
            if delta is not None and row[3] == angband_finale_battle.OUTFLANK_REASON:
                last["player"]["y"] += delta[0]
                last["player"]["x"] += delta[1]
        cls.walk = walk

    def test_the_halt_cell_is_left_toward_the_exit_side(self):
        held = [row for row in self.recorded if row[0] >= FIRST_HOLD and row[1] == HALT_CELL]
        holds = [row for row in held if row[3] == angband_finale_battle.HOLD_REASON]
        # The recorded run: about 800 holds on (42,48) (revert: 808 in this replay, then the stop).
        self.assertLessEqual(len(holds), angband_finale_battle.STALEMATE_BOARDS, holds[-3:])
        walks = [row for row in held if row[3] == angband_finale_battle.OUTFLANK_REASON]
        self.assertTrue(walks, held[-5:])
        self.assertEqual(walks[0][2], "1", walks[0])  # south-west, around the vault's west wall

    def test_the_plan_waits_beyond_the_exit_with_a_line_onto_it(self):
        self.assertIsNotNone(self.plan)
        wait, exit_cell, aim = self.plan[:3]
        self.assertFalse(self.plan[3])  # walked, no Stone to Mud
        self.assertEqual(aim, SERPENT)
        self.assertEqual(exit_cell, EXIT)
        distance = game_distance(Position(*wait), Position(*exit_cell))
        self.assertGreaterEqual(distance, angband_finale_battle.STAND_MIN_DISTANCE)
        self.assertLessEqual(game_distance(Position(*wait), Position(*SERPENT)),
                             angband_finale_battle.TELEPATHY_RANGE)

    def test_the_walk_reaches_the_wait_cell_and_waits_there(self):
        wait = self.plan[0] if self.plan else None
        cells = [row[1] for row in self.walk]
        self.assertIn(wait, cells, self.walk)
        arrived = cells.index(wait)
        steps = self.walk[:arrived]
        self.assertTrue(all(row[3] == angband_finale_battle.OUTFLANK_REASON for row in steps),
                        steps)
        # Never within the teleport's distance 2 of the Serpent, and no cell entered twice.
        self.assertTrue(all(game_distance(Position(*cell), Position(*SERPENT))
                            > angband_finale_battle.TELEPORT_WITHIN for cell in cells), cells)
        self.assertEqual(len(set(cells[:arrived + 1])), arrived + 1, cells)
        waits = self.walk[arrived:]
        self.assertTrue(all(row[2] == WAIT_KEY and row[3] == angband_finale_battle.HOLD_REASON
                            for row in waits), waits)


if __name__ == "__main__":
    unittest.main()
