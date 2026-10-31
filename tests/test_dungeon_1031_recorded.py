"""#47 (2026-10-31): recorded dungeon deaths and loops of family fix-dungeon-1031.

Fixture: tests/fixtures/dungeon-1031.json.gz (tests/extract_dungeon_1031_fixture.py).
Every decision goes through the public choose_key and every posted key
through the production executor port.

- death-return (n1-a life-446, 鉄獄48階): the second emergency escape latched
  the town return (emergency-repeat), but the immobile-summoner avoidance kept
  exploring and looting; 14 teleports later the last scroll was gone and the
  character died.  A latched return now owns the decision (return:recall).
- death-blind (same death): blinded by a dragon, the empty hostile list read as
  an unseen attacker; unseen-recall walked into an adjacent monster five times
  while Cure Critical Wounds sat behind it.  Blindness is now cured first.
- q22-sweep (n1-a life-447, オークのキャンプ): each step swapped the visible
  target (the sleeping captain at [14,6] / a black orc) and the sweep walked
  between [11,13] and [11,14].  The chosen target is now kept.
- angband-1f (n1-c life-055, 鉄獄1階): the up stairs leave for the wilderness,
  so they are rightly no targets, but the return read Recall only below
  WALK_OUT_MAX_DEPTH and searched walls instead.
- wilderness (n1-c life-059): the '<' on 鉄獄2階 [5,62] was an up shaft (two
  floors) and left for the wilderness; there the refused global map
  (「敵がすぐ近くにいるときは広域マップに入れない！」) was retried forever.
  Owner 2026-10-31 「帰還を読む。ただし、そもそも荒野にいることがおかしい。」

DECLARED CONSTRUCTED / RECONSTRUCTED: the captures hold no ~f reply, so the
skill knowledge is supplied before each decision.  The life-055 and life-059
replays start mid-return, so ``_returning_to_town`` is set as the recorded
return:* reasons show.  The Q22 opening phase, post-wave light and initial
hold are set complete (the recorded rows are in the sweep phase).  Executor
replies are the next recorded board, or the same board one turn later.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests import test_input_executor as executor_pins
from tests.test_town_decision_speed_caches import EDIT, build_policy

FIXTURE = Path(__file__).with_name("fixtures") / "dungeon-1031.json.gz"
READ_PROMPT = "どの巻物を読みますか? "
QUAFF_PROMPT = "どの薬を飲みますか? "
CHOOSER = "どのダンジョンに帰還しますか:"


def skill(policy, raw):
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })


def decide(policy, raw):
    skill(policy, raw)
    return str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))


def chooser_screen(rows):
    screen = executor_pins.prompt_screen(CHOOSER)
    for index, row in enumerate(rows):
        screen["lines"][2 + index] = " " * 14 + "      " + row
    return screen


class RecordedHarness(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def boards(self, name):
        return [copy.deepcopy(board) for board in self.cases[name]["boards"]]

    def post(self, policy, raw, key, screens, following):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [*screens, executor_pins.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        return game.accepted

    @staticmethod
    def later(raw, turns=10):
        return dict(copy.deepcopy(raw), turn=raw["turn"] + turns, messages=[])


class DeathReturnRecordedTest(RecordedHarness):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, name, stop_turn):
        boards = self.boards(name)
        policy = HengbotPolicy(monrace_knowledge=dict(self.monraces))
        policy.prime(parse_snapshot(boards[0], policy._monrace_knowledge))
        for raw in boards:
            if raw["turn"] == stop_turn:
                return policy, raw
            decide(policy, raw)
        self.fail(stop_turn)

    def test_recorded_rows(self):
        rows = {row["turn"]: row for row in self.cases["death-return"]["decisions"]}
        self.assertEqual((rows[1712410]["reason"], rows[1712410]["key"]),
                         ("emergency:teleport", "rc"))
        self.assertEqual((rows[1712415]["reason"], rows[1712415]["key"]),
                         ("explore:avoid-immobile-summoner", "9"))
        rows = {row["turn"]: row for row in self.cases["death-blind"]["decisions"]}
        self.assertEqual((rows[1713414]["reason"], rows[1713414]["key"]),
                         ("unseen-recall:move", "4"))
        blind = self.boards("death-blind")[-1]
        self.assertTrue(blind["player"]["status"]["blind"])

    def test_latched_town_return_outranks_the_summoner_avoidance(self):
        policy, raw = self.replay("death-return", 1712415)
        # The emergency escape of 1712410 latched the return; observing this
        # board counts it as the second of the dive (emergency-repeat).
        self.assertTrue(policy._returning_to_town)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertTrue(any(policy._summoner_never_approaches(board, monster)
                            for monster in policy._perceived_hostiles(board))
                        or policy._immobile_summoner_memory[1])
        key = decide(policy, raw)
        self.assertEqual(policy._last_return_trigger, "emergency-repeat")
        self.assertEqual(policy.last_reason, "return:recall")
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot)
        following = self.later(raw)
        self.assertEqual(self.post(policy, raw, key, [executor_pins.prompt_screen(READ_PROMPT)],
                                   following), ["r", recall.slot])

    def test_blindness_is_cured_before_the_unseen_recall_walk(self):
        policy, raw = self.replay("death-blind", 1713414)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertTrue(board.player.blind)
        self.assertTrue(board.player.recalling)
        key = decide(policy, raw)
        cure = policy._find_status_cure_potion(board)
        self.assertEqual(policy.last_reason, "item:cure-critical")
        self.assertEqual(key, "q" + cure.slot)
        following = self.later(raw)
        self.assertEqual(self.post(policy, raw, key, [executor_pins.prompt_screen(QUAFF_PROMPT)],
                                   following), ["q", cure.slot])


if __name__ == "__main__":
    unittest.main()
