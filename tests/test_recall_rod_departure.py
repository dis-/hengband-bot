"""The Rod of Recall as the town departure's read (n1-a life-508, 2026-11-11 00:40).

cmd-item/cmd-zaprod.cpp SV_ROD_RECALL calls recall_player(randint0(21) + 15),
the Word of Recall scroll's call: on the surface it asks choose_dungeon
(spell-kind/spells-world.cpp), and the rod recharges (pval 60, BaseitemDefinitions
id 354).  The supply ledger counts one rod as the read the departure adds to
the standing scroll target; the departure zaps a charged rod before a scroll.

DECLARED CONSTRUCTED: the boards are the recorded n1-c life-010 town board of
tests/test_recall_dungeon_prompt_recorded.py with its Word of Recall stack
(slot c) turned into a Rod of Recall, or a rod added beside it.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import gzip
import json
import unittest

from hengbot.input_executor import ScreenKind
from hengbot.model import SV_ROD_RECALL, TVAL_ROD, parse_snapshot
from hengbot.observed_input import compile_observed_input
from tests.support import recorded as executor_pins
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import ConservativePolicy
from tests.test_recall_dungeon_prompt_recorded import FIXTURE, chooser_screen

ZAP_PROMPT = "どのロッドを振りますか? "


def rod(board, slot="c", *, charging=False, count=1):
    """The board's Word of Recall row (slot c) as a Rod of Recall at ``slot``."""
    scroll = next(item for item in board["inventory"] if item["slot"] == "c")
    return {**copy.deepcopy(scroll), "slot": slot, "tval": TVAL_ROD, "sval": SV_ROD_RECALL,
            "name": "帰還のロッド", "count": count, "charging": charging,
            "charging_count": count if charging else 0, "weight": 15}


class RecallRodDepartureTest(executor_pins.ProductionHarness):
    """The recorded harness, on boards whose slot c holds the rod."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def policy(self):
        # As tests/test_recall_dungeon_prompt_recorded.py primes it.
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

    def setUp(self):
        super().setUp()
        self.raw = copy.deepcopy(self.case["board"])
        self.raw["inventory"] = [rod(self.case["board"]) if item["slot"] == "c" else item
                                 for item in self.raw["inventory"]]

    def board(self, policy, raw=None):
        return parse_snapshot(copy.deepcopy(raw or self.raw), policy._monrace_knowledge)

    def test_ledger_counts_one_rod_as_the_departure_read(self):
        policy, _ = self.policy()
        board = self.board(policy)
        self.assertEqual(policy._count_recall_scrolls(board), 0)
        self.assertEqual(policy._count_recall_means(board), 1)
        two = copy.deepcopy(self.raw)
        two["inventory"] = [rod(self.case["board"], count=2) if item["slot"] == "c" else item
                            for item in two["inventory"]]
        # A second rod reads nothing more at the departure.
        self.assertEqual(policy._count_recall_means(self.board(policy, two)), 1)
        both = copy.deepcopy(self.case["board"])
        both["inventory"].append(rod(self.case["board"], "x"))
        board = self.board(policy, both)
        self.assertEqual(policy._count_recall_scrolls(board), 3)
        self.assertEqual(policy._count_recall_means(board), 4)
        self.assertEqual(
            policy._supply_ledger(board, policy._planned_depth())["recall"].count, 4)

    def test_rod_is_kept_on_the_pack(self):
        policy, _ = self.policy()
        board = self.board(policy)
        carried = next(item for item in board.inventory if item.is_recall_rod)
        self.assertEqual(policy._retention_reservation_detail(board, carried),
                         (1, "supply-ledger:recall-rod"))

    def test_departure_zaps_a_charged_rod_before_a_scroll(self):
        policy, _ = self.policy()
        both = copy.deepcopy(self.case["board"])
        both["inventory"].append(rod(self.case["board"], "x"))
        board = self.board(policy, both)
        device = policy._town_recall_device(board)
        self.assertTrue(device.is_recall_rod)
        self.assertEqual(policy._town_recall_device_key(board, device, "a"), "zxa")
        both["inventory"][-1] = rod(self.case["board"], "x", charging=True)
        board = self.board(policy, both)
        device = policy._town_recall_device(board)
        self.assertTrue(device.is_recall_scroll)
        self.assertEqual(policy._recall_issue_stock(board), 3)

    def test_zap_releases_the_destination_at_the_chooser(self):
        prefix, steps = compile_observed_input(
            "zca", ScreenKind.COMMAND, self.raw, "town:recall-to-yeek-cave", [])
        self.assertEqual(prefix, "z")
        self.assertEqual([(set(step.kinds), step.keys) for step in steps],
                         [({ScreenKind.ITEM_SOURCE}, "c"),
                          ({ScreenKind.DUNGEON_CHOICE}, "a")])

    def post_rod(self, key, screens):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(self.raw)
        game.screen = executor_pins.command_screen(self.raw["turn"])
        game.screens = screens
        game.states = [copy.deepcopy(self.raw) for _ in screens]
        game.states[-1]["turn"] = self.raw["turn"] + 1
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        policy, _ = self.policy()
        sent, _line = _send_new_decision_key(
            port, "constructed-board", key, None, set(), in_store=False,
            decision={"sequence": 1, "reason": "town:recall-to-yeek-cave"},
            snapshot=self.board(policy), posting_contract=PostingContract(),
        )
        return game, port, sent

    def test_executor_answers_the_rod_destination(self):
        game, port, sent = self.post_rod("zca", [
            executor_pins.prompt_screen(ZAP_PROMPT),
            chooser_screen(),
            executor_pins.command_screen(479583),
        ])
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, ["z", "c", "a"])

    def test_unanswered_zap_cancels_the_chooser(self):
        game, port, sent = self.post_rod("zc", [
            executor_pins.prompt_screen(ZAP_PROMPT),
            chooser_screen(),
            executor_pins.command_screen(479582),
        ])
        self.assertFalse(sent)
        self.assertEqual(game.accepted, ["z", "c", "\x1b"])
        self.assertIn("reason=recall-destination-unchosen", port.last_result.stop_line)

    def test_departure_board_undoes_the_zap(self):
        policy, _ = self.policy()
        board = self.board(policy)
        charged = next(item for item in board.inventory if item.is_recall_rod)
        policy._town_recall_issue_watch = (2, board.turn, policy._recall_issue_stock(board))
        policy._town_recall_issue_rod = charged
        zapped = replace(board, player=replace(board.player, recalling=True),
                         inventory=[replace(item, charging=True) if item is charged else item
                                    for item in board.inventory])
        undone = policy._recall_departure_board(zapped)
        self.assertFalse(undone.player.recalling)
        self.assertIs(next(item for item in undone.inventory if item.is_recall_rod), charged)


if __name__ == "__main__":
    unittest.main()
