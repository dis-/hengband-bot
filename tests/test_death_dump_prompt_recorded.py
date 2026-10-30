"""D32: recorded deaths that stopped at the death chain's screen-dump question.

Seven viewing characters died on 2026-10-30 (n1-c lives 8, 9, 11, 16; n1-a
lives 424, 433; n1-b life 268) and every stop was filed as ``stuck-prompt``
(owners melee, emergency:cornered-attack, explore, ranged:fire-target,
emergency:seek-upstairs): after ``death_save()`` the game asks
``input_check_strict("Dump the screen? ")`` at row zero
(player/player-damage.cpp:456, core/asking-player.cpp prt(buf, 0, 0)) before
"You die.", and the executor classified that row as an unowned confirm.

Boards, decisions, stop screens and stop lines are recorded
(tests/fixtures/death-dump-prompt-20261030.json.gz, see
tests/extract_death_dump_prompt.py).  Each case decides on its last recorded
board through the public chooser and posts the key through the production
executor; the game's reply is the recorded stop screen.  The engine moving
from the decided board to the death screen in one reply is CONSTRUCTED (the
recorded process saw intermediate boards on some lives).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path

from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen

FIXTURE = Path(__file__).parent / "fixtures" / "death-dump-prompt-20261030.json.gz"
JAPANESE_PROMPT = "画面を保存しますか？[y/n]"


class DeathDumpPromptRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.races = {}
        for key, facts in cls.data["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            cls.races[int(key)] = MonraceKnowledge(**facts)

    def test_recorded_stops_were_dead_characters_at_the_dump_question(self):
        self.assertEqual(len(self.data["cases"]), 7)
        for life, case in self.data["cases"].items():
            with self.subTest(life=life):
                self.assertLessEqual(case["dead_hp"], 0)
                self.assertEqual(case["screen"]["lines"][0].rstrip(), JAPANESE_PROMPT)
                self.assertIn(f'ctx_prompt="{JAPANESE_PROMPT}" reason=unowned confirm',
                              case["stop_line"])
                self.assertIn(f"owner={case['decision']['reason']} ", case["stop_line"])

    def test_recorded_dump_question_is_the_player_death(self):
        for life, case in self.data["cases"].items():
            with self.subTest(life=life):
                raw = copy.deepcopy(case["board"])
                policy = HengbotPolicy(monrace_knowledge=dict(self.races))
                policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
                key = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
                self.assertIsInstance(key, str)
                self.assertTrue(key)

                game = FaithfulHookGame()
                game.state = copy.deepcopy(raw)
                game.screen = command_screen(raw["turn"])
                game.screens = [copy.deepcopy(case["screen"])]
                _, _, executor = self.make(game)
                self.assertEqual(
                    executor.observe_boundary(deadline=9999999999).outcome, "ready")
                port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                          request_budget=2)
                sent = port(key, decision={"reason": policy.last_reason,
                                           "sequence": policy._decision_sequence})
                self.assertIs(sent, SendResult.PLAYER_DEATH, port.last_result.reason)
                self.assertEqual(port.last_result.outcome, "player-death")
                self.assertEqual(port.last_result.reason,
                                 f"<player-death> feature={JAPANESE_PROMPT}")

    def test_english_dump_question_and_unrelated_confirms(self):
        # The English build prints the same input_check_strict row.
        self.assertEqual(classify_screen(prompt_screen("Dump the screen? [y/n]")).kind,
                         ScreenKind.DEATH)
        # The question is only the death chain's when it is the whole row.
        for row in ("Really attack? [y/n]", "画面を保存しますか？[y/n] x"):
            with self.subTest(row=row):
                self.assertIsNot(classify_screen(prompt_screen(row)).kind, ScreenKind.DEATH)
