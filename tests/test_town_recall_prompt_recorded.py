"""D26: the recorded n1-a life-443 town recall stop (2026-10-30 21:39).

After the tavern rumors and the character dump, decision 2660 read Word of
Recall (``town:recall-to-yeek-cave``, ``rda``: scroll d, Yeek cave = chooser
letter a, the only entered dungeon).  spells-world.cpp recall_player showed
choose_dungeon 「どのダンジョンに帰還しますか:」 with its row printed by
prt(row, 2, 14), so the side panel 「兵士」 stays in cells 0-13 of the row.
The executor's listed-destination check required the row to start with
blanks, refused the owned letter, cancelled the chooser with Escape
(recall_player returns false, the scroll is kept) and stopped as
recall-destination-unchosen; three stops retired the character.

Pinned through the production reader and executor port: the recorded board
composes the recorded key, and the chooser as the game draws it (the
recorded side-panel cells, then the formatted row) is answered with ``a``.
Fixture: tests/extract_town_recall_prompt_fixture.py.
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
from hengbot.policy import ConservativePolicy
from tests import test_input_executor as executor_pins


FIXTURE = Path(__file__).with_name("fixtures") / "town-recall-prompt-20261030.json.gz"
READ_PROMPT = "どの巻物を読みますか? "
CHOOSER = "どのダンジョンに帰還しますか:"
# dungeon-service.cpp RECALL: "      {:c}) {:c}{:<12} : 最大 {} 階".
YEEK_ROW = "      a)  イークの洞窟   : 最大 1 階"


class TownRecallPromptRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def chooser_screen(self):
        # choose_dungeon: prt(prompt, 0, 0); prt(row, 2, 14) over the
        # recorded side panel (its cells 0-13 of row 2).
        screen = executor_pins.prompt_screen(CHOOSER)
        for row, cells in self.case["side_panel"].items():
            screen["lines"][int(row)] = cells
        screen["lines"][2] += YEEK_ROW
        return screen

    def recorded_read(self):
        policy = ConservativePolicy()
        snapshot = parse_snapshot(copy.deepcopy(self.case["board"]), policy._monrace_knowledge)
        policy.prime(snapshot)
        # The capture's policy state holds _town_recall_issue_watch
        # [2, 176520, 10]: the departure read for Yeek cave (dungeon 2).
        policy._pending_recall_dungeon_id = 2
        recall = next(item for item in snapshot.inventory if item.is_recall_scroll)
        return snapshot, policy._read_key(snapshot, recall)

    def post(self, key, screens, *, recalled):
        raw = self.case["board"]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = screens
        game.states = [copy.deepcopy(raw) for _ in screens]
        # DECLARED CONSTRUCTED: the game's reply to the answered chooser
        # (recall_player: "回りの大気が張りつめてきた...", word_recall set).
        game.states[-1]["turn"] = raw["turn"] + 1
        game.states[-1]["player"]["recalling"] = recalled
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        snapshot = parse_snapshot(copy.deepcopy(raw), ConservativePolicy()._monrace_knowledge)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": self.case["decision"]["decision_sequence"],
                      "reason": self.case["decision"]["reason"]},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        return game, port, sent

    def test_recorded_board_composes_the_recorded_read(self):
        decision = self.case["decision"]
        self.assertEqual(
            (decision["decision_sequence"], decision["turn"], decision["reason"],
             decision["key"]),
            (2660, 176520, "town:recall-to-yeek-cave", "rda"))
        snapshot, key = self.recorded_read()
        self.assertTrue(snapshot.in_town)
        self.assertFalse(snapshot.player.recalling)
        self.assertEqual(list(snapshot.entered_dungeon_ids), [2])
        self.assertEqual(key, decision["key"])
        self.assertIs(classify_screen(self.chooser_screen()).kind, ScreenKind.DUNGEON_CHOICE)

    def test_chooser_under_the_side_panel_is_answered(self):
        _snapshot, key = self.recorded_read()
        game, port, sent = self.post(key, [
            executor_pins.prompt_screen(READ_PROMPT),
            self.chooser_screen(),
            executor_pins.command_screen(self.case["board"]["turn"] + 1),
        ], recalled=True)
        # Recorded: r, d, Escape and stuck-prompt recall-destination-unchosen.
        self.assertEqual(game.accepted, ["r", "d", "a"])
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(port.last_result.outcome, "completed")

    def test_unlisted_letter_under_the_side_panel_is_still_cancelled(self):
        game, port, sent = self.post("rdb", [
            executor_pins.prompt_screen(READ_PROMPT),
            self.chooser_screen(),
            executor_pins.command_screen(self.case["board"]["turn"]),
        ], recalled=False)
        self.assertFalse(sent)
        self.assertEqual(game.accepted, ["r", "d", "\x1b"])
        self.assertIn("reason=recall-destination-unchosen", port.last_result.stop_line)


if __name__ == "__main__":
    unittest.main()
