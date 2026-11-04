"""n1-c life-103 07:02:47 loop-detected: a summoner hold point under fire.

Owner decision (2026-11-02): 「撃たれる場所は待つポイントとして不適当なので
撃たれない場所で待つ。無理ならテレポート。」

Recorded: at (2,30) on 18F a Crypt Creep (race 124, S_UNDEAD / CAUSE_1)
stood twenty cells west down a straight corridor.  The summoner choke hold
chose WAIT there, the survival gate rewrote it into ``no-wait:flee`` '6', and
from (2,31) (beyond sight) explore walked back '4'; decisions 6096-6131
alternated until the loop detector stopped the bot.

The creep's cast distance is twenty, beyond get_max_range() = 18
(mspell-attack.cpp:320): the game cannot shoot the player there, so (2,30)
is a fit hold point and the WAIT survives the survival gate.  With the
creep moved inside its reach (DECLARED CONSTRUCTED, (2,16)) the point is
shot at: it stays vetoed for the floor visit and the hold walks east to a
choke beyond the creep's reach.  (Teleportation when no such choke exists is
pinned by tests/test_flee_into_rubble_recorded.py.)
Fixture: tests/extract_summoner_hold_los_1102_fixture.py.  Constructed parts
are marked DECLARED CONSTRUCTED.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.summoner_wait import HOLD_REPOSITION_REASON
from tests import test_input_executor as executor_pins
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "summoner-hold-los-1102.json.gz"
CRYPT_CREEP = 124


class SummonerHoldUnderFireTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def _policy_on(self, boards, adjust=lambda board: board):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        policy = _policy(Path(directory.name), monrace)
        boards = [adjust(parse_snapshot(copy.deepcopy(raw), monrace)) for raw in boards]
        policy.prime(boards[0])
        if self.case["skill"] is not None:
            policy.consume_skill_knowledge(
                {**self.case["skill"], "player": {"level": boards[0].player.level}})
        keys = []
        for board in boards:
            board = policy.with_known_skill_exp(board)
            keys.append((board.player.position, policy.choose_key(board), policy.last_reason))
        return policy, board, keys

    def test_recorded_hold_beyond_the_creeps_reach_is_kept(self):
        recorded = [(d["decision_sequence"], d["reason"], d["key"]) for d in self.case["decisions"]]
        self.assertEqual(recorded, [(6095, "explore", "4"), (6096, "no-wait:flee", "6"),
                                    (6097, "explore", "4")])
        policy, board, keys = self._policy_on(self.case["boards"][:2])
        self.assertEqual(keys[0][1:], ("3", "explore"))  # floor in the own light is not owed (37414d7d41, #101)
        self.assertEqual(keys[1], (Position(2, 30), "5", "summoner:hold-choke"))
        creep = next(m for m in board.visible_monsters if m.race_id == CRYPT_CREEP)
        self.assertEqual(policy._monster_cast_distance(creep.position, Position(2, 30)), 20)
        self.assertNotIn(Position(2, 30), policy._engagement_avoid_cells)

        raw = self.case["boards"][1]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [copy.deepcopy(raw)]
        # DECLARED CONSTRUCTED: the WAIT spent one player turn.
        game.states[-1]["turn"] = raw["turn"] + 10
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", "5", None, set(), in_store=False,
            decision={"sequence": 6096, "reason": "summoner:hold-choke"},
            snapshot=board, posting_contract=PostingContract(),
        )
        self.assertEqual(game.accepted, ["5"])
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(port.last_result.outcome, "completed")

    def test_hold_inside_reach_moves_out_of_it_and_is_vetoed(self):
        boards = self.case["boards"][:2]

        def inside_reach(board):
            # DECLARED CONSTRUCTED: the creep inside its reach on the same
            # corridor row, (2,16), cast distance 14.
            moved = Position(2, 16)
            return replace(board, visible_monsters=[
                replace(m, position=moved, distance=board.player.position.distance_to(moved))
                if m.race_id == CRYPT_CREEP else m
                for m in board.visible_monsters])

        policy, shot, keys = self._policy_on(boards, inside_reach)
        hold_point, key, reason = keys[1]
        self.assertEqual(hold_point, Position(2, 30))
        self.assertEqual((key, reason), ("6", HOLD_REPOSITION_REASON))
        self.assertIn(hold_point, policy._engagement_avoid_cells)
        destination = policy._validated_choke_route(
            shot, [m for m in shot.visible_monsters if m.race_id == CRYPT_CREEP],
            admit=lambda cell: cell not in policy._engagement_avoid_cells
            and not any(policy._fire_reaches(shot, m, cell, projectable=True)
                        for m in shot.visible_monsters))[0]
        self.assertGreater(
            policy._monster_cast_distance(Position(2, 16), destination), 18)


if __name__ == "__main__":
    import unittest
    unittest.main()
