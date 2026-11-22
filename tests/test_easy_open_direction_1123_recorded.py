"""easy_open takes the direction itself: the composed ``o`` + direction stepped onto the door (n1-c life-221).

cmd-action/cmd-open-close.cpp do_cmd_open, with easy_open (option-types-table.cpp: on), sets
command_dir itself when exactly one closed door (floor-info.cpp count_doors_traps
GridCountKind::CLOSED_DOOR, marked grids) or one non-empty chest (open-util.cpp count_chests), not
both, is around the player; get_rep_dir (target/target-getter.cpp) then asks no direction.  The bot
posted the composed ``o`` + direction as one key string, so the direction key was read as the next
command: a step onto the opened door, or an attack on a monster in it.  do_cmd_close (one open
door, GridCountKind::OPEN) and do_cmd_disarm (easy_disarm: one trap, the player's own grid too, or
one known trapped chest) do the same.

n1-c life-221 (Quest 25, 2026-11-23), recorded in tests/fixtures/n1c-221-q25-druj-stand-1123.json.gz
(tests/extract_n1c_221_q25_druj_stand_1123_fixture.py):

 * turn 3191468, the generic walk (``_step_toward``, reason quest25:walk): ``o3`` on [9,23] with the
   one closed door [10,24] around; the next board (3191477) has the player on [10,24].
 * turn 3191513, ``o6`` on the stand [13,27] (the one closed door [13,28]); the next board (3191524)
   has him on [13,28], beside the stairway to hell.
 * turn 3202245, ``o4`` on [11,20] (the one closed door [11,19]); the next board (3202271) has him on
   [11,19], the druj's doorway.

The fix (observed_input, every producer): the open / close / disarm command key goes alone and the
direction is released only at the observed direction question; with no question it falls away.

DECLARED CONSTRUCTED: the command boundary after the open (the board turn + 10).  DECLARED REUSED:
the direction question screen is the recorded one of tests/fixtures/q34-chest-prompt-20261026.json.gz
(「方向 ('.'足元, ESCで中断)?」, get_rep_dir(player, true), the same call do_cmd_open and
do_cmd_disarm make); the two-door control's board is the recorded 3191468 one with a second closed
door drawn at [8,23] (DECLARED CONSTRUCTED).
"""
from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import Position, parse_snapshot
from hengbot.observed_input import compile_observed_input
from hengbot.policy_constants import EASY_DIRECTION_COMMANDS
import tests.support.recorded as executor_harness
from tests.support import q25_house as q25
from tests.support import recorded
from tests.support.recorded import FaithfulHookGame, command_screen

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1c-221-q25-druj-stand-1123.json.gz", "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
with gzip.open(FIXTURES / "q34-chest-prompt-20261026.json.gz", "rt", encoding="utf-8") as _stream:
    DIRECTION_SCREEN = json.load(_stream)["captures"][0]["screen"]

# (turn of the open, key, reason, the player's cell, the door, the next board's turn)
OPENS = (
    (3191468, "o3", "quest25:walk", (9, 23), (10, 24), 3191477),
    (3191513, "o6", "quest25:open-door", (13, 27), (13, 28), 3191524),
    (3202245, "o4", "quest25:walk-to-sight", (11, 20), (11, 19), 3202271),
)
WALK_OPEN = OPENS[0]


def board(turn):
    return copy.deepcopy(next(raw for raw in CASE["boards"] if raw["turn"] == turn))


def snapshot(raw):
    return parse_snapshot(copy.deepcopy(raw), q25.RACES)


def closed_doors_around(raw):
    snap = snapshot(raw)
    here = snap.player.position
    return {(here.y + dy, here.x + dx)
            for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)
            if (grid := snap.grid_at(Position(here.y + dy, here.x + dx))) is not None
            and grid.known and grid.is_closed_door}


def with_second_door(raw, cell):
    """DECLARED CONSTRUCTED: a second closed door drawn on ``cell`` (the board's own door row)."""
    raw = copy.deepcopy(raw)
    door = WALK_OPEN[4]
    runs = raw["grid_map"]["runs"]
    door_palette = next(run[3] for run in runs if run[0] == door[0] and run[1] <= door[1] < run[1] + run[2])
    pieces = []
    for run in runs:
        y, x, length, palette = run[:4]
        if y == cell[0] and x <= cell[1] < x + length:
            if cell[1] > x:
                pieces.append([y, x, cell[1] - x, palette, *run[4:]])
            pieces.append([y, cell[1], 1, door_palette, *run[4:]])
            if x + length > cell[1] + 1:
                pieces.append([y, cell[1] + 1, x + length - cell[1] - 1, palette, *run[4:]])
        else:
            pieces.append(run)
    raw["grid_map"]["runs"] = pieces
    return raw


class TheRecordingTest(unittest.TestCase):

    def test_each_open_with_one_door_around_stepped_onto_the_door(self):
        for turn, key, reason, here, door, following in OPENS:
            with self.subTest(key=key):
                [row] = [row for row in CASE["decisions"] if row["turn"] == turn and row["key"] == key]
                self.assertEqual((row["reason"], (row["y"], row["x"])), (reason, here))
                self.assertEqual(closed_doors_around(board(turn)), {door})
                after = board(following)["player"]
                self.assertEqual((after["y"], after["x"]), door)

    def test_the_walk_keys_the_open_with_its_direction(self):
        """The generic walk's door step (``_step_toward``) keeps ``o`` + direction: the intent
        the lock and jam counts read; only the posting drops the direction."""
        turn, key, _reason, _here, door, _following = WALK_OPEN
        raw = board(turn)
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        self.assertEqual(policy._step_toward(snapshot(raw), Position(*door)), key)


class TheCompositionTest(unittest.TestCase):

    def test_every_producer_sends_the_command_alone(self):
        raw = board(WALK_OPEN[0])
        for owner in ("quest25:walk", "nav:explore", "chest:open", "trap:disarm", "quest25:close-door"):
            for command in EASY_DIRECTION_COMMANDS:
                with self.subTest(owner=owner, command=command):
                    prefix, steps = compile_observed_input(
                        command + "3", ScreenKind.COMMAND, raw, owner, [])
                    self.assertEqual(prefix, command)
                    self.assertEqual([(step.kinds, step.keys, step.optional) for step in steps][:1],
                                     [(frozenset({ScreenKind.DIRECTION}), "3", True)])

    def test_control_the_commands_that_always_ask_keep_their_form(self):
        raw = board(WALK_OPEN[0])
        # cmd-tunnel.cpp do_cmd_tunnel: get_rep_dir with no command_dir set, always asked.
        self.assertEqual(compile_observed_input("T3", ScreenKind.COMMAND, raw, "nav:dig", []), ("T3", []))
        # A plain step is not an open.
        self.assertEqual(compile_observed_input("3", ScreenKind.COMMAND, raw, "quest25:walk", []), ("3", []))


class TheOpenPostingTest(executor_harness.ProductionHarness):

    def post(self, raw, key, owner, *, prompted):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        following = copy.deepcopy(raw)
        following["turn"] += 10        # DECLARED CONSTRUCTED: the boundary after the open
        prompt_state = copy.deepcopy(raw)
        prompt_state["input_context"] = copy.deepcopy(DIRECTION_SCREEN["input_context"])
        game.screens = ([copy.deepcopy(DIRECTION_SCREEN)] if prompted else []) + [command_screen(following["turn"])]
        game.states = ([prompt_state] if prompted else []) + [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = recorded._policy(Path(directory.name), q25.RACES)
        policy.last_reason = owner
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "easy-open-direction", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": owner},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(executor.ready_screen.kind, ScreenKind.COMMAND)
        self.assertFalse(game.term_fifo)
        self.assertFalse(game.screens, "every scheduled question was answered")
        return game

    def test_the_question_screen_is_a_direction_question(self):
        self.assertEqual(classify_screen(DIRECTION_SCREEN, None).kind, ScreenKind.DIRECTION)

    def test_one_door_around_posts_the_open_alone(self):
        """The recorded opens: no direction question comes, and no direction key is left to
        become the next command (the step onto the door)."""
        for turn, key, reason, _here, _door, _following in OPENS:
            with self.subTest(key=key):
                game = self.post(board(turn), key, reason, prompted=False)
                self.assertEqual(game.accepted, [key[0]])

    def test_control_two_doors_around_answer_the_question(self):
        turn, key, reason, _here, door, _following = WALK_OPEN
        raw = with_second_door(board(turn), (8, 23))
        self.assertEqual(closed_doors_around(raw), {door, (8, 23)})
        game = self.post(raw, key, reason, prompted=True)
        self.assertEqual(game.accepted, [key[0], key[1]])


if __name__ == "__main__":
    unittest.main()
