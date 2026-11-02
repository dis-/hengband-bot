"""n1-c life-103 07:02:47 loop-detected: a summoner hold point under fire.

Owner decision (2026-11-02): 「撃たれる場所は待つポイントとして不適当なので
撃たれない場所で待つ。無理ならテレポート。」

Recorded: at (2,30) on 18F a Crypt Creep (race 124, S_UNDEAD / CAUSE_1)
stood twenty cells west down a straight corridor.  The summoner choke hold
chose WAIT there, the survival gate rewrote it into ``no-wait:flee`` '6', and
from (2,31) (beyond sight) explore walked back '4'; decisions 6096-6131
alternated until the loop detector stopped the bot.

Every cell of that corridor row is in the creep's line of fire and the one
side opening (3,32) is not a choke, so no other hold point exists: the hold
reads Teleportation, and the abandoned point stays vetoed for the floor visit
so exploration from (2,31) no longer walks back into it.
Fixture: tests/extract_summoner_hold_los_1102_fixture.py.  Only the game's
reply to the newly posted read is constructed (DECLARED CONSTRUCTED).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.summoner_wait import HOLD_TELEPORT_REASON
from tests import test_input_executor as executor_pins
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "summoner-hold-los-1102.json.gz"
READ_PROMPT = "どの巻物を読みますか? "


class SummonerHoldUnderFireTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def test_shot_hold_point_teleports_and_is_not_walked_back_into(self):
        recorded = [(d["decision_sequence"], d["reason"], d["key"]) for d in self.case["decisions"]]
        self.assertEqual(recorded, [(6095, "explore", "4"), (6096, "no-wait:flee", "6"),
                                    (6097, "explore", "4")])
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        policy = _policy(Path(directory.name), monrace)
        boards = [parse_snapshot(copy.deepcopy(raw), monrace) for raw in self.case["boards"]]
        policy.prime(boards[0])
        if self.case["skill"] is not None:
            policy.consume_skill_knowledge(
                {**self.case["skill"], "player": {"level": boards[0].player.level}})
        keys = []
        for board in boards:
            board = policy.with_known_skill_exp(board)
            keys.append((board.player.position, policy.choose_key(board), policy.last_reason))
            if len(keys) == 2:
                shot = board
        self.assertEqual(keys[0][1:], ("4", "explore"))
        hold_point, key, reason = keys[1]
        self.assertEqual(hold_point, Position(2, 30))
        self.assertEqual((key, reason), ("rf", HOLD_TELEPORT_REASON))
        self.assertTrue(next(i for i in shot.inventory if i.slot == "f").is_teleport_scroll)
        self.assertIn(hold_point, policy._engagement_avoid_cells)
        # From (2,31) exploration no longer steps back into the vetoed point.
        self.assertEqual(keys[2][0], Position(2, 31))
        self.assertNotEqual(keys[2][1], "4")

        raw = self.case["boards"][1]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(READ_PROMPT),
                        executor_pins.command_screen(raw["turn"] + 1)]
        game.states = [copy.deepcopy(raw) for _ in game.screens]
        # DECLARED CONSTRUCTED: the teleport moved the player off the corridor.
        game.states[-1]["turn"] = raw["turn"] + 1
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": 6096, "reason": reason},
            snapshot=shot, posting_contract=PostingContract(),
        )
        self.assertEqual(game.accepted, ["r", "f"])
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(port.last_result.outcome, "completed")


if __name__ == "__main__":
    import unittest
    unittest.main()
