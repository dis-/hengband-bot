"""Aimed item commands send their direction only at the observed question (owner answer (b)-5).

Owner answer 2026-11-23 「問いが出た時だけ方向を送る」.  The wand ``a``, rod ``z``, fire ``f`` and
throw ``v`` commands were posted whole with their direction or target walk (``fo8``,
``fo*t5\\x1b``, ``fo*p9666t5\\x1b``, ``aj8``): the (a)-3 recording (9d3e85670) counted them as
``composed-passthrough`` rows.  get_aim_dir (target/target-getter.cpp) asks nothing with
use_old_target and a valid target, a known non-aiming rod (zaprod-execution.cpp) asks nothing,
and no launcher or no item prints a message; the trailing keys then fell to the command loop.

The target walk's tail: at get_aim_dir's question '*' opens target_set (target-setter.cpp), and
't' sets the target and ends the mode at once (switch_target_input / switch_next_grid_command,
``done = true``), so get_aim_dir returns and the composers' ``5\\x1b`` was read by the command
loop: '5' is ',' (stay still, lib/pref/pref-key.prf ``A:,`` ``C:0:5``), a whole game turn.

Recorded (tests/fixtures/aimed-item-direction-1123.json.gz, tests/extract_aimed_item_direction_
1123_fixture.py): n1-a life-535 (2026-11-23 12:41-13:04 JST, after 57a80bc0a deployed), the game
-turn advance from each posted key to the next decision, and the composed-passthrough rows of
n1-a life-535, n1-b life-416 and n1-c life-221.  A shot by direction (``f`` + ammo + digit)
advanced a median 4 game turns, a step 6, and a shot at the target (``f`` + ammo + ``*t5\\x1b``)
10: the shot and one more player turn, the '5' stay.

The fix (observed_input.aim_steps): the command and the item letter go together (a rod's letter
at its observed chooser); the direction, or the walk up to 't', only at the observed direction
question, and '5' / ESC only while target_set still waits (its key guide on row 0).

DECLARED CONSTRUCTED: the question screens (get_aim_dir's prompt, target_set's key guide, the
rod chooser) at the source's literals, with their input_context, on the recorded test board of
tests/test_classA_observed_input (as test_magic_eater_o3 builds them); no capture holds them.
"""
from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import statistics
import time
import unittest
from pathlib import Path

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.observed_input import AIMED_ITEM_COMMANDS, compile_observed_input, composed_passthrough
from tests.support import recorded as executor_harness
from tests.support.recorded import FaithfulHookGame, command_screen, prompt_screen
from tests.test_classA_observed_input import board

FIXTURE = Path(__file__).with_name("fixtures") / "aimed-item-direction-1123.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

# target/target-getter.cpp get_aim_dir (no target yet / a target kept).
AIM_PROMPT = "方向 ('*'でターゲット選択, ESCで中断)? "
AIM_PROMPT_TARGET = "方向 ('5'でターゲットへ, '*'でターゲット再選択, ESCで中断)? "
# target/target-setter.cpp build_key_guide (a monster under the cursor).
TARGET_GUIDE = "q止 t決 p自 o現 +次 -前"
ZAP_PROMPT = "(持ち物:a-z, ESCで中断) どのロッドを振りますか? "   # cmd-zaprod.cpp


def _median(kind):
    counts = CASE["turn_advance"][kind]
    return statistics.median(int(advance) for advance, count in counts.items() for _ in range(count))


def aim_question(text=AIM_PROMPT, *, has_target=False):
    screen = prompt_screen(text)
    screen["cursor"]["visible"] = True
    screen["input_context"] = {"kind": "direction", "prompt": text, "can_choose_target": True,
                               "has_target": has_target, "at_feet": False}
    return screen


def target_guide():
    screen = prompt_screen(f"[{TARGET_GUIDE}] オーク (無傷)")
    screen["cursor"]["visible"] = True
    screen["input_context"] = {"kind": "target", "prompt": TARGET_GUIDE}
    return screen


def rod_chooser():
    screen = prompt_screen(ZAP_PROMPT)
    screen["cursor"]["visible"] = True
    screen["input_context"] = {"kind": "item", "prompt": ZAP_PROMPT}
    return screen


class TheRecordingTest(unittest.TestCase):

    def test_a_shot_at_the_target_took_one_more_player_turn(self):
        """The '5' after the set target was a stay: a target shot advanced the game by a shot
        by direction and a step (the medians of n1-a life-535's consecutive decisions)."""
        direction, step, target = (_median("fire-direction"), _median("step"),
                                   _median("fire-target"))
        self.assertEqual((direction, step, target), (4, 6, 10))
        self.assertEqual(target, direction + step)
        self.assertGreaterEqual(_median("fire-offset"), direction + step)

    def test_the_recorded_passthroughs_cover_every_aimed_shape(self):
        shapes = {(row["command"], row["suffix"]) for row in CASE["passthrough"]}
        self.assertLessEqual({("f", "direction"), ("f", "target-cursor"), ("a", "direction")},
                             shapes)
        self.assertIn(("T", "direction"), shapes)          # the tunnel stays (always asks)


class TheCompositionTest(unittest.TestCase):

    def test_every_recorded_aimed_key_holds_its_suffix_for_the_question(self):
        raw = board()
        for row in CASE["passthrough"]:
            key = row["key"]
            if key[0] not in AIMED_ITEM_COMMANDS:
                continue
            with self.subTest(owner=row["owner"], key=key):
                prefix, steps = compile_observed_input(key, ScreenKind.COMMAND, raw, row["owner"], [])
                self.assertEqual(prefix, key[:2])
                self.assertTrue(all(step.optional for step in steps))
                self.assertEqual(steps[0].kinds, frozenset({ScreenKind.DIRECTION}))
                if key.endswith("t5\x1b"):
                    self.assertEqual([step.keys for step in steps], [key[2:-2], "5", "\x1b"])
                    self.assertEqual({step.kinds for step in steps[1:]},
                                     {frozenset({ScreenKind.LOOK})})
                else:
                    self.assertEqual([step.keys for step in steps], [key[2:]])
                self.assertIsNone(composed_passthrough(key, prefix))

    def test_a_rod_answers_its_chooser_then_the_question(self):
        prefix, steps = compile_observed_input("zb4", ScreenKind.COMMAND, board(), "ranged", [])
        self.assertEqual(prefix, "z")
        self.assertEqual([(step.kinds, step.keys, step.optional) for step in steps], [
            (frozenset({ScreenKind.ITEM_SOURCE}), "b", False),
            (frozenset({ScreenKind.DIRECTION}), "4", True)])

    def test_control_other_recorded_shapes_keep_their_form(self):
        raw = board()
        for row in CASE["passthrough"]:
            if row["key"][0] in AIMED_ITEM_COMMANDS:
                continue
            with self.subTest(key=row["key"]):
                # do_cmd_tunnel always asks (get_rep_dir); the eat chooser is unclassified.
                self.assertEqual(compile_observed_input(row["key"], ScreenKind.COMMAND, raw,
                                                        row["owner"], []), (row["key"], []))


class TheAimedPostingTest(executor_harness.ProductionHarness):

    def post(self, key, owner, screens, *, tunnel_macros_ready=True):
        raw = board()
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)   # DECLARED CONSTRUCTED
        game.screens = [*screens, command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=tunnel_macros_ready,
                                  request_budget=2)
        self.assertEqual(port(key, decision={"sequence": 1, "reason": owner}), SendResult.SENT,
                         port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(executor.ready_screen.kind, ScreenKind.COMMAND)
        self.assertFalse(game.term_fifo)
        self.assertFalse(game.screens, "every scheduled question was answered")
        return game.accepted

    def test_the_question_screens_are_classified(self):
        self.assertEqual(classify_screen(aim_question(), None).kind, ScreenKind.DIRECTION)
        self.assertEqual(classify_screen(aim_question(AIM_PROMPT_TARGET, has_target=True),
                                         None).kind, ScreenKind.DIRECTION)
        self.assertEqual(classify_screen(target_guide(), None).kind, ScreenKind.LOOK)
        self.assertEqual(classify_screen(rod_chooser(), None).kind, ScreenKind.ITEM_SOURCE)

    def test_a_direction_is_sent_at_the_question(self):
        for key, owner in (("fo8", "ranged:fire"), ("aj8", "anaguma:dig"),
                           ("aq4", "ranged:aim-wand"), ("vb6", "q1:throw-torch")):
            with self.subTest(key=key):
                self.assertEqual(self.post(key, owner, [aim_question()]), [key[:2], key[2]])

    def test_no_question_drops_the_direction(self):
        """use_old_target with a valid target (or no launcher): no question, and no direction
        left to become a step."""
        for key, owner in (("fo8", "ranged:fire"), ("aj8", "anaguma:dig"),
                           ("vb6", "q1:throw-torch")):
            with self.subTest(key=key):
                self.assertEqual(self.post(key, owner, []), [key[:2]])

    def test_a_set_target_leaves_no_stay(self):
        """'t' ends target_set and get_aim_dir at once: '5' and ESC fall away (the recorded
        extra player turn)."""
        for key, owner in (("fo*t5\x1b", "ranged:fire-target"),
                           ("fo*p9666t5\x1b", "ranged:fire-offset")):
            with self.subTest(key=key):
                self.assertEqual(self.post(key, owner, [aim_question()]), ["fo", key[2:-2]])

    def test_a_refused_t_is_retried_with_five(self):
        """can_target_monster_at_cursor false: target_set still waits, '5' tries again."""
        self.assertEqual(self.post("fo*t5\x1b", "ranged:fire-target",
                                   [aim_question(), target_guide()]), ["fo", "*t", "5"])

    def test_no_question_drops_the_target_walk(self):
        self.assertEqual(self.post("fo*t5\x1b", "ranged:fire-target", []), ["fo"])

    def test_a_rod_direction_only_when_it_aims(self):
        self.assertEqual(self.post("zb4", "ranged:rod", [rod_chooser(), aim_question()]),
                         ["z", "b", "4"])
        # A known non-aiming rod (zaprod-execution.cpp: no get_aim_dir).
        self.assertEqual(self.post("zb4", "ranged:rod", [rod_chooser()]), ["z", "b"])

    def test_control_the_tunnel_is_sent_whole(self):
        # (Without the tunnel macros, which would send its own one-key macro.)
        self.assertEqual(self.post("T4", "breakout:seek-frontier", [], tunnel_macros_ready=False),
                         ["T4"])


if __name__ == "__main__":
    unittest.main()
