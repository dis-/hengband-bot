"""D22: the recorded n1-c life-010 town emergency recall (2026-10-30 08:28).

Decision 6186 read Word of Recall in town as ``emergency:recall`` (``rc``)
at HP 14/129 beside 鳩『ポッポ』.  On the surface spells-world.cpp
recall_player asks 「どのダンジョンに帰還しますか:」 (choose_dungeon); the
operation carried no answer and stopped unowned three times.

Pinned through the public ``choose_key`` and the production executor port:
the low-HP ladder no longer reads recall off the dungeon floors (it would
land the wounded player in the dungeon, not the town); a surface recall read
answers the chooser with the listed destination letter only at the observed
prompt; a read without an owned destination cancels the chooser and stops
under a name.  Fixture: tests/extract_recall_dungeon_prompt_fixture.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.observed_input import compile_observed_input
from hengbot.policy import ConservativePolicy
from tests import test_input_executor as executor_pins


FIXTURE = Path(__file__).with_name("fixtures") / "recall-dungeon-prompt-20261030.json.gz"
READ_PROMPT = "どの巻物を読みますか? "
CHOOSER = "どのダンジョンに帰還しますか:"


def chooser_screen(prompt=CHOOSER, rows=("a) イークの洞窟   : 最大 1 階",)):
    # choose_dungeon: prt(prompt, 0, 0); prt(rows[i], 2 + i, 14), each row
    # formatted "      {letter}) ..." (dungeon-service.cpp RECALL).
    screen = executor_pins.prompt_screen(prompt)
    for index, row in enumerate(rows):
        screen["lines"][2 + index] = " " * 14 + "      " + row
    return screen


class RecallDungeonPromptRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def policy(self):
        policy = ConservativePolicy()
        for key, facts in self.case["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            policy._monrace_knowledge[int(key)] = MonraceKnowledge(**facts)
        snapshot = parse_snapshot(copy.deepcopy(self.case["board"]), policy._monrace_knowledge)
        policy.prime(snapshot)
        policy.consume_skill_knowledge(self.case["skill_knowledge"])
        return policy, snapshot

    def post(self, key, reason, screens):
        raw = self.case["board"]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = screens
        game.states = [copy.deepcopy(raw) for _ in screens]
        game.states[-1]["turn"] = raw["turn"] + 1
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        _policy, snapshot = self.policy()
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": self.case["decision"]["decision_sequence"],
                      "reason": reason},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        return game, port, sent

    def test_capture_pins_town_emergency_recall_board(self):
        decision = self.case["decision"]
        self.assertEqual(
            (decision["decision_sequence"], decision["turn"], decision["reason"],
             decision["key"]),
            (6186, 479582, "emergency:recall", "rc"))
        _policy, snapshot = self.policy()
        self.assertTrue(snapshot.in_town)
        self.assertEqual(snapshot.dungeon_level, 0)
        self.assertEqual((snapshot.player.hp, snapshot.player.max_hp), (14, 129))
        self.assertFalse(snapshot.player.recalling)
        self.assertEqual(snapshot.entered_dungeon_ids, (2,) if isinstance(
            snapshot.entered_dungeon_ids, tuple) else [2])
        recall = next(item for item in snapshot.inventory if item.is_recall_scroll)
        self.assertEqual((recall.slot, recall.count), ("c", 3))
        self.assertEqual([monster.name for monster in snapshot.visible_monsters],
                         ["鳩『ポッポ』"])
        self.assertIs(classify_screen(chooser_screen()).kind, ScreenKind.DUNGEON_CHOICE)

    def test_low_hp_ladder_does_not_read_recall_in_town(self):
        policy, snapshot = self.policy()
        key = policy.choose_key(snapshot)
        self.assertNotEqual(policy.last_reason, "emergency:recall")
        self.assertFalse(str(key).startswith("rc"), key)

    def test_surface_recall_read_without_destination_stays_unanswered(self):
        policy, snapshot = self.policy()
        recall = next(item for item in snapshot.inventory if item.is_recall_scroll)
        # The voluntary selector walks to Yeek cave at deepest 1 (below
        # RECALL_MIN_DEPTH): no destination is established on this board.
        self.assertEqual(policy._town_recall_destination(snapshot), (None, 2))
        key = policy._read_key(snapshot, recall)
        self.assertEqual(key, "rc")
        prefix, steps = compile_observed_input(
            key, ScreenKind.COMMAND, self.case["board"], "emergency:recall", [])
        self.assertEqual((prefix, [step.keys for step in steps]), ("r", ["c"]))

    def established_read(self):
        policy, snapshot = self.policy()
        # DECLARED CONSTRUCTED: a town departure that chose Yeek cave (the
        # only entered dungeon, chooser letter a) holds its pending id.
        policy._pending_recall_dungeon_id = 2
        recall = next(item for item in snapshot.inventory if item.is_recall_scroll)
        return policy._read_key(snapshot, recall)

    def test_surface_recall_read_carries_listed_destination(self):
        # The reader every recall path composes through.
        key = self.established_read()
        self.assertEqual(key, "rca")
        prefix, steps = compile_observed_input(
            key, ScreenKind.COMMAND, self.case["board"], "emergency:recall", [])
        self.assertEqual(prefix, "r")
        self.assertEqual([(set(step.kinds), step.keys) for step in steps],
                         [({ScreenKind.ITEM_SOURCE}, "c"),
                          ({ScreenKind.DUNGEON_CHOICE}, "a")])

    def test_executor_answers_destination_at_observed_chooser(self):
        key = self.established_read()
        game, port, sent = self.post(key, "town:recall-to-yeek-cave", [
            executor_pins.prompt_screen(READ_PROMPT),
            chooser_screen(),
            executor_pins.command_screen(479583),
        ])
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, ["r", "c", "a"])

    def test_english_chooser_is_answered(self):
        game, port, sent = self.post("rca", "town:recall-to-yeek-cave", [
            executor_pins.prompt_screen("Read which scroll? "),
            chooser_screen("Which dungeon do you recall?: ",
                           ("a) Yeek cave        : Max level 1",)),
            executor_pins.command_screen(479583),
        ])
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, ["r", "c", "a"])

    def test_recorded_unanswered_read_cancels_chooser_under_named_stop(self):
        # The recorded key carried no destination: Escape, never a guess.
        game, port, sent = self.post("rc", "emergency:recall", [
            executor_pins.prompt_screen(READ_PROMPT),
            chooser_screen(),
            executor_pins.command_screen(479582),
        ])
        self.assertFalse(sent)
        self.assertEqual(game.accepted, ["r", "c", "\x1b"])
        self.assertEqual(port.last_result.outcome, "stuck-prompt")
        self.assertIn("reason=recall-destination-unchosen", port.last_result.stop_line)

    def test_unlisted_destination_is_never_answered(self):
        game, port, sent = self.post("rcb", "town:recall-to-yeek-cave", [
            executor_pins.prompt_screen(READ_PROMPT),
            chooser_screen(),
            executor_pins.command_screen(479582),
        ])
        self.assertFalse(sent)
        self.assertEqual(game.accepted, ["r", "c", "\x1b"])
        self.assertIn("reason=recall-destination-unchosen", port.last_result.stop_line)


if __name__ == "__main__":
    unittest.main()
