"""n1-b life-411 2026-11-19: Angband is explored no deeper than 95F (angband_cap).

The Lv50 Magic-Eater held Angband as the guardian bounce valve's alternate with its recall depth 99
(Oberon's floor, the TAKEN kill quest 99F) and recalled to 99F and back to town dive after dive.
Owner 2026-11-19 (verbatim): 「99F 100Fの戦い方をまだ作っていない。n1-bは次回潜行時に95Fまで登り
階段で戻ること。以降、準備ができるまで鉄獄95Fで探索すること。」

Recorded: the town-arrival checkpoint of 00:54:41 (tests/extract_n1b_411_angband_cap_1119_fixture.py),
its 81 journal rows replayed (row 29 the Word of Recall read to Angband, town:recall-to-angband),
and the next dive's arrival board (Angband 99F, turn 7814111).  Rows 21, 22, 26 and 27 (the
in-store purchase and two Magic-Eater list refreshes) replay differently on the build before this
change too; the replay posts the recorded keys there (``KNOWN_DIVERGENT``).

DECLARED CONSTRUCTED:
* ``floor_board``: the recorded 99F arrival board at the depth asked, its monsters removed, the 9x9
  cells around the player opened and in view, an up staircase ``stair`` cells east of the player (or
  none) and a down staircase 3 cells west;
* each following board of a floor advances the game turn by 10 and carries the decided reason as
  the completed operation (the Magic-Eater arrival powers settle, me_powers.observe);
* the executor's raw boards: the recorded 99F board with its floor and saved Angband depth changed;
* before the floor's decisions, the town's equipment work the replay left half done is dropped (a
  stopped Home errand and the equipment transaction): the recorded keys predate the 99F/100F
  loadout order (angband_finale, owner 2026-11-20), whose swap the replay never finishes.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import angband_cap, dive_floor, explored_floor, hunt_target
from hengbot.input_executor import Operation
from hengbot.model import DUNGEON_ANGBAND, GridState, Position, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.recorded import ProductionHarness, command_screen, prompt_screen
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-angband-cap-1119"
KNOWN_DIVERGENT = frozenset({21, 22, 26, 27})
RESET_PROMPT = "ここは最深到達階より浅い階です。この階に戻って来ますか？ [y/n]"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class N1b411AngbandCapRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.arrival, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.policy = copy.deepcopy(cls.arrival)
        cls.decided = []
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            cls.decided.append(decide(cls.policy, board))
            post(cls.policy, recorded["key"])
        cls.town = board
        cls.raw = json.loads(lzma.decompress((FIXTURE / "angband-99f-board.json.xz").read_bytes()))

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.arrival._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def floor_board(self, policy, level, stair):
        """DECLARED CONSTRUCTED (the module docstring)."""
        raw = copy.deepcopy(self.raw)
        raw["floor"] = {**raw["floor"], "level": level}
        raw["detected_monsters"], raw["visible_monsters"] = [], []
        board = parse_snapshot(raw, policy._monrace_knowledge)
        here = board.player.position
        grids = dict(board.grids)
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                cell = Position(here.y + dy, here.x + dx)
                base = grids.get(cell) or GridState(cell, True, True, False, False, False, False, False)
                grids[cell] = replace(
                    base, known=True, passable=True, wall=False, has_up_stairs=False,
                    has_down_stairs=False, can_dig=False, tunnel=False, permanent=False,
                    is_closed_door=False, is_door=False, trap=False, marked=True, in_view=True,
                    lit=True)
        if stair is not None:
            up = Position(here.y, here.x + stair)
            grids[up] = replace(grids[up], has_up_stairs=True)
        down = Position(here.y, here.x - 3)
        grids[down] = replace(grids[down], has_down_stairs=True)
        return replace(board, grids=grids)

    def play(self, level, stair, decisions=7):
        """The decisions on the floor, the arrival powers settled (the module docstring)."""
        policy = copy.deepcopy(self.policy)
        # The town's equipment work the replay left half done: dropped (the module docstring).
        policy._home_errand.release_stopped()
        policy._set_equipment_transaction_session(None)
        board = self.floor_board(policy, level, stair)
        decided = []
        for _ in range(decisions):
            key, reason = decide(policy, board)
            decided.append((key, reason))
            post(policy, key)
            board = replace(board, turn=board.turn + 10, completed_operation_owner=reason)
        return policy, board, decided

    def test_a_the_recorded_town_visit_recalls_to_angband_99(self):
        for row, (recorded, decided) in enumerate(zip(self.journal, self.decided)):
            if row not in KNOWN_DIVERGENT:
                self.assertEqual(decided, (recorded["key"], recorded["reason"]), row)
        self.assertEqual(self.decided[29], ("rfa", "town:recall-to-angband"))
        board, policy = self.town, self.policy
        self.assertTrue(board.in_town)
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 99)
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon,
                          policy._alternate_dungeon_reason),
                         (DUNGEON_ANGBAND, DUNGEON_ANGBAND, "guardian_bounce_valve"))
        # The landing lies past the cap: the arrival climbs, no stair below 95 is a target.
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND), 95)
        self.assertTrue(angband_cap.climbing_floor((DUNGEON_ANGBAND, 99, 0)))
        self.assertFalse(angband_cap.climbing_floor((DUNGEON_ANGBAND, 95, 0)))
        self.assertTrue(angband_cap.capped_at(DUNGEON_ANGBAND, 96))
        self.assertFalse(angband_cap.capped_at(DUNGEON_ANGBAND, 95))
        self.assertFalse(angband_cap.capped_at(dive_floor.DUNGEON_CASTLE, 96))
        self.assertFalse(angband_cap.capped(board, 96))  # a town board has no stair below

    def test_b_the_99f_arrival_climbs_toward_the_up_stairs(self):
        policy, board, decided = self.play(99, 3)
        self.assertTrue(dive_floor.climbing(policy, board))
        self.assertTrue(dive_floor.capped(policy, board, 100))
        self.assertIsNone(hunt_target.target_race(policy, board))  # Oberon is not hunted
        self.assertFalse(policy._quest_floor_exit_locked(board))
        self.assertFalse(explored_floor.dead_end(policy, board))
        reasons = [reason for _key, reason in decided]
        self.assertIn("angband-cap-95:seek-upstairs", reasons)
        key = decided[reasons.index("angband-cap-95:seek-upstairs")][0]
        self.assertIn(key, {"3", "6", "9"})  # a step east, toward the up staircase
        self.assertFalse(any(reason in {"seek-downstairs", "descend"} for reason in reasons))

        _policy, _board, decided = self.play(99, 0)
        self.assertIn(("<", "angband-cap-95:ascend"), decided)

    def test_c_at_95f_no_stair_down(self):
        policy, board, decided = self.play(95, 3)
        self.assertFalse(dive_floor.climbing(policy, board))
        self.assertTrue(dive_floor.capped(policy, board, 96))
        self.assertFalse(policy._is_descent_target(board, board.grid_at(Position(
            board.player.position.y, board.player.position.x - 3))))
        reasons = [reason for _key, reason in decided]
        self.assertFalse(any(reason in {"seek-downstairs", "descend"}
                             or reason.startswith(("angband-cap-95:", "castle-climb:"))
                             for reason in reasons), reasons)
        self.assertEqual(reasons[-1], "explore")
        # Above the cap the down stairs are taken as ever.
        policy = copy.deepcopy(self.policy)
        board = self.floor_board(policy, 94, None)
        self.assertFalse(dive_floor.capped(policy, board, 95))
        # On the cap's floor an underfoot escape takes no stair down either.
        policy = copy.deepcopy(self.policy)
        board = self.floor_board(policy, 95, None)
        here = board.player.position
        grids = dict(board.grids)
        grids[here] = replace(grids[here], has_down_stairs=True)
        board = replace(board, grids=grids)
        policy._took_damage = True
        self.assertIsNone(policy._down_stairs_underfoot_key(board, "test:underfoot"))


class AngbandCapRecallDepthAnswerTest(ProductionHarness):
    """recall_player's reset question (src/spell-kind/spells-world.cpp:442-449) is answered y on
    the cap's floor and below it while the saved depth is past the cap, n everywhere else."""

    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(lzma.decompress((FIXTURE / "angband-99f-board.json.xz").read_bytes()))

    def board(self, dungeon_id, level, saved):
        raw = copy.deepcopy(self.raw)
        raw["floor"] = {**raw["floor"], "dungeon_id": dungeon_id, "level": level}
        raw["progress"] = {**raw["progress"], "dungeon_recall_depths": {
            **raw["progress"]["dungeon_recall_depths"], str(dungeon_id): saved}}
        return raw

    def answer(self, observation):
        game, _client, executor = self.make()
        game.screens = [prompt_screen(RESET_PROMPT), command_screen(3)]
        executor.observe_boundary(deadline=9999999999)
        result = executor.submit(
            Operation(4556, "return:recall", "rf", observation), deadline=9999999999)
        self.assertEqual(result.outcome, "completed", result.reason)
        return game.accepted

    def test_the_answer(self):
        self.assertEqual(self.raw["progress"]["dungeon_recall_depths"]["1"], 99)
        cases = (
            ((DUNGEON_ANGBAND, 95, 99), "y"),  # the cap's floor: the next dive lands on 95
            ((DUNGEON_ANGBAND, 97, 99), "y"),  # read on the climb: lands nearer the cap
            ((DUNGEON_ANGBAND, 94, 99), "n"),  # above the cap: the deepest floor is kept
            ((dive_floor.DUNGEON_CASTLE, 95, 99), "n"),  # no cap there
        )
        for (dungeon_id, level, saved), expected in cases:
            with self.subTest(dungeon_id=dungeon_id, level=level):
                observation = self.board(dungeon_id, level, saved)
                self.assertEqual(angband_cap.reset_recall_depth(observation), expected == "y")
                self.assertEqual(self.answer(observation), ["rf", expected])


if __name__ == "__main__":
    unittest.main()
