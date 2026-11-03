"""The loop-detected stops of the 2026-11-04 morning (build 2d4b7645d / b044fd30f).

Every board is decided through the public choose_key on the recorded boards;
a key is posted through the production executor.  Nothing but the marked seeds
is constructed.  Fixtures: tests/extract_loops_1104_fixtures.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from tests import test_input_executor as executor_pins
from tests.test_dungeon_stops_1103_recorded import RecordedBoards


FIXTURES = Path(__file__).with_name("fixtures") / "loops-1104"
EMPTY_AIR = "何もない空中を攻撃した。"


def fixture(name: str) -> dict:
    return json.loads(lzma.decompress((FIXTURES / name).read_bytes()))


class ItemCommandBoards(RecordedBoards):
    def post_item_command(self, policy, raw: dict, key: str, prompt: str) -> None:
        """Post ``key`` (command, item letter) through the production executor."""
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(prompt),
                        executor_pins.command_screen(raw["turn"] + 1)]
        game.states = [copy.deepcopy(raw), copy.deepcopy(raw)]
        game.states[-1]["turn"] = raw["turn"] + 1
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract(),
        )
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, [key[0], key[1:]])


class BlindStrikeAtAnEmptyCell(ItemCommandBoards):
    """n1-b life-307, 2026-11-04 02:14, Yeek cave 13F (D13).

    Bitten blind by a ヴラスタ, it fought through at the cell north of it, the
    cell of the last sighted board.  That monster died; 「何もない空中を攻撃
    した。」 came back on most of the 40 strikes while unseen attackers took HP
    355 -> 231, and the loop guard stopped the bot.
    """

    def test_empty_air_retires_the_remembered_cell(self):
        case = fixture("blind-air.json.xz")
        policy = self.fresh_policy(case["boards"][0])
        for raw in case["boards"]:
            key = self.decide(policy, raw)
            air = any(EMPTY_AIR in message for message in raw["messages"])
            if raw["turn"] < self.FIRST_AIR_TURN:
                continue
            if raw["turn"] == self.FIRST_AIR_TURN:
                # Nothing remembered and no blow on this board: the cure.
                self.assertTrue(air)
                self.assertEqual((key, policy.last_reason), ("qb", "item:cure-critical"))
                self.post_item_command(policy, raw, key, "どの薬を飲みますか? ")
            elif raw["turn"] == self.AIR_AND_BLOW_TURN:
                # An unseen blow on an empty-air board: the random free
                # neighbour of owner 2026-10-03, not the retired cell.
                self.assertTrue(air)
                self.assertEqual((key, policy.last_reason), ("+1", "blind:fight-through"))
                return
        self.fail("the recorded boards ended early")

    FIRST_AIR_TURN = 376184
    AIR_AND_BLOW_TURN = 376286


class RetreatVetoesEncloseTheMazePlayer(ItemCommandBoards):
    """n1-a life-476 02:51 (Labyrinth 15F, D15), n1-b life-307 03:18 (18F, D18).

    The floor's retreat vetoes (threat:avoid-engagement, summoner:retreat) held
    every way out of a corridor pocket after the threats had died.  An unconquered
    forgetting maze refuses the idle fallback's Recall, so it waited with '5' at
    one cell until the loop guard stopped the bot.
    """

    def assert_recall_leaves(self, name: str):
        case = fixture(name)
        policy = self.fresh_policy(case["boards"][0], case["terrain"])
        # SEEDS: the stop's floor-long vetoes and written-off frontiers.
        policy._claim_engagement_avoid_cells(Position(*cell) for cell in case["avoid"])
        policy._probed_frontiers.update(Position(*cell) for cell in case["probed"])
        raw = case["boards"][-1]
        # The removed breakout wander (0d46d60d2) never had this step either:
        # the least-visited neighbour refuses the same vetoes.
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertIsNone(policy._least_visited_neighbor(snapshot))
        key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, "stuck:recall-escape")
        self.assertEqual(key[0], "r")
        self.post_item_command(policy, raw, key, "どの巻物を読みますか? ")

    def test_d15(self):
        self.assert_recall_leaves("enclosed-d15.json.xz")

    def test_d18(self):
        self.assert_recall_leaves("enclosed-d18.json.xz")


if __name__ == "__main__":
    unittest.main()
