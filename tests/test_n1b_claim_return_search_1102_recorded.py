"""n1-b life-293 (2026-11-02 13:06, Yeek cave 1F): the quest-claim return.

Walking back to town to claim the completed quest 14 (1F is within
WALK_OUT_MAX_DEPTH, so the carried Word of Recall is kept), the return owner searched the walls for a hidden up staircase
('s' up to SEARCH_LIMIT times per wall cell, bounded by
_wall_search_counts).  The fixed-quest claim relabelled every return key
fixedquest:claim:return except return:wait-recall, so the wall search lost
its return:search-upstairs label, which the CLI cell guard exempts: the
guard stopped the walk at 13:06:35 and 13:06:59 and the character retired.

Now the claim keeps the return's bounded stationary labels
(policy_constants.RETURN_STATIONARY_REASONS, the same set the cell guard
exempts) and the search is posted through the production executor.
Fixture: tests/extract_n1b_claim_return_search_1102_fixture.py.
DECLARED RECONSTRUCTED: the escape owner (return:seek-secret-wall) is the
capture's policy-state.json value; the wall search counts are not in it
(fresh counts).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _cell_loop_guard_applies, _send_new_decision_key,
)
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SEARCH_KEY, WALK_OUT_MAX_DEPTH
from tests import test_input_executor as executor_pins
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-claim-return-search-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
CLAIM_QUEST = 14


class ClaimReturnWallSearchTest(executor_pins.ProductionHarness):

    def policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        policy = _policy(Path(directory.name), monrace)
        first = CASE["boards"][0]
        policy.prime(parse_snapshot(copy.deepcopy(first), monrace))
        terrain = CASE["terrain"]
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
        for name, value in CASE["modes"].items():
            setattr(policy, name, value)
        escape = CASE["escape_state"]
        policy._escape_state.floor = tuple(escape["floor"])
        policy._escape_state.enter(escape["owner"], escape["rung"])
        policy.consume_skill_knowledge(
            {**CASE["skill"], "player": {"level": first["player"]["level"]}})
        return policy

    def test_recorded_rows_searched_under_the_claim_label(self):
        self.assertEqual([(row["reason"], row["key"]) for row in CASE["decisions"]],
                         [("fixedquest:claim:return", "s")] * 2)
        board = parse_snapshot(copy.deepcopy(CASE["boards"][0]), {})
        self.assertEqual(board.floor_key, (2, 1, 0))
        self.assertEqual(CASE["terrain"]["upstairs"], [])
        # A Word of Recall is carried: at depth <= WALK_OUT_MAX_DEPTH the
        # return walks out and keeps the scroll for its stuck backstop.
        self.assertTrue(any(item.is_recall_scroll for item in board.inventory))
        self.assertLessEqual(board.dungeon_level, WALK_OUT_MAX_DEPTH)
        quest = next(q for q in CASE["boards"][0]["progress"]["quests"] if q["id"] == CLAIM_QUEST)
        self.assertEqual(quest["cur_num"], quest["max_num"])
        self.assertTrue(CASE["modes"]["_returning_to_town"])

    def test_wall_search_keeps_the_guard_exempt_return_label(self):
        policy = self.policy()
        for raw in CASE["boards"]:
            with self.subTest(raw["turn"]):
                board = policy.with_known_skill_exp(
                    parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
                key = policy.choose_key(board)
                self.assertEqual((key, policy.last_reason),
                                 (SEARCH_KEY, "return:search-upstairs"))
                self.assertFalse(_cell_loop_guard_applies(
                    board, policy.last_reason, board.player.position))
                game = executor_pins.FaithfulHookGame()
                game.state = copy.deepcopy(raw)
                game.screen = executor_pins.command_screen(raw["turn"])
                game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
                # DECLARED CONSTRUCTED: the search spent one player turn.
                game.states = [dict(copy.deepcopy(raw), turn=raw["turn"] + 10)]
                _game, _client, executor = self.make(game)
                self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
                port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
                sent, _line = _send_new_decision_key(
                    port, "recorded-board", key, None, set(), in_store=False,
                    decision={"sequence": policy._decision_sequence,
                              "reason": policy.last_reason},
                    snapshot=board, posting_contract=PostingContract(),
                )
                self.assertTrue(sent, port.last_result.stop_line)
                self.assertEqual(game.accepted, [SEARCH_KEY])
                self.assertEqual(port.last_result.outcome, "completed")


if __name__ == "__main__":
    import unittest
    unittest.main()
