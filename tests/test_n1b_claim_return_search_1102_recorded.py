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
exempts).

walkout-dig-1102 (owner 2026-11-02 「1Fから歩いて出るときは概ね採掘中なので、
困ったら壁を掘れば上り階段に辿り着くと思うのだが壁を調べ続ける理由は？」 ->
「掘って進む」): the warrior carried a Shovel and a Pick, so instead of the
search it wields the digger and tunnels toward the nearest unexplored area
(no up staircase is remembered; walkout_dig).  Only without a digging tool
does the return search the walls as before.
Fixture: tests/extract_n1b_claim_return_search_1102_fixture.py.
DECLARED RECONSTRUCTED: the escape owner (return:seek-secret-wall) is the
capture's policy-state.json value; the wall search counts are not in it
(fresh counts).
DECLARED CONSTRUCTED: the boards after the take-off and after the wield
(test_barehand_mining_recorded's ``taken_off`` / ``wielded``), and the
no-digger board (the recorded board without its two diggers).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import choose_past_junk_key

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _cell_loop_guard_applies, _send_new_decision_key,
    _transport_key,
)
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SEARCH_KEY, STUCK_ESCAPE_LIMIT, TUNNEL_KEY, WALK_OUT_MAX_DEPTH
from tests import test_input_executor as executor_pins
from tests.test_barehand_mining_recorded import ITEM_PROMPTS, taken_off, wielded
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-claim-return-search-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
CLAIM_QUEST = 14
TVAL_DIGGING = 20  # TV_DIGGING (object/tval-types.h)
SHOVEL = "シャベル"
# hengbot.policy_constants.RETURN_DIG_FRONTIER_REASON, spelled out so the
# revert check runs every test instead of an import error.
DIG_FRONTIER = "return:dig-to-frontier"


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

    def decide(self, policy, raw):
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        return board, choose_past_junk_key(policy, board)

    def post(self, policy, board, raw, key):
        """Send ``key`` through the production executor; the turn passes."""
        prompts = ([executor_pins.prompt_screen(ITEM_PROMPTS[key[0]])]
                   if key[0] in ITEM_PROMPTS else [])
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = prompts + [executor_pins.command_screen(raw["turn"] + 10)]
        # DECLARED CONSTRUCTED: the command spent one player turn.
        game.states = ([copy.deepcopy(raw) for _ in prompts]
                       + [dict(copy.deepcopy(raw), turn=raw["turn"] + 10)])
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
        self.assertEqual("".join(game.accepted), _transport_key(key, True))
        self.assertEqual(port.last_result.outcome, "completed")
        policy.confirm_key_posted(key)

    def test_digger_tunnels_toward_the_unexplored_instead_of_searching(self):
        for raw in CASE["boards"]:
            with self.subTest(raw["turn"]):
                self.assertEqual(
                    sum(item["tval"] == TVAL_DIGGING for item in raw["inventory"]), 2)
                policy = self.policy()
                board, key = self.decide(policy, raw)
                # The take-off of the sword is the digger swap's first post
                # (the claim relabels it; the dig keeps its own label).
                self.assertEqual((key, policy.last_reason), ("ta", "fixedquest:claim:return"))
                self.assertEqual(policy._breakout_dig_floor, board.floor_key)
                self.post(policy, board, raw, key)
                bare = taken_off(raw, "main_hand")
                board, key = self.decide(policy, bare)
                shovel = next(item["slot"] for item in bare["inventory"]
                              if item["name"].startswith(SHOVEL))
                self.assertEqual(key, "w" + shovel)
                self.post(policy, board, bare, key)
                digging = wielded(bare, SHOVEL, "main_hand")
                board, key = self.decide(policy, digging)
                self.assertEqual(policy.last_reason, DIG_FRONTIER)
                self.assertTrue(key.startswith(TUNNEL_KEY), key)
                self.assertNotEqual(key, SEARCH_KEY)
                self.assertFalse(_cell_loop_guard_applies(
                    board, policy.last_reason, board.player.position))
                self.post(policy, board, digging, key)

    def test_without_a_digger_the_return_searches_the_walls(self):
        policy = self.policy()
        for raw in CASE["boards"]:
            with self.subTest(raw["turn"]):
                raw = copy.deepcopy(raw)
                raw["inventory"] = [item for item in raw["inventory"]
                                    if item["tval"] != TVAL_DIGGING]
                board, key = self.decide(policy, raw)
                self.assertEqual((key, policy.last_reason),
                                 (SEARCH_KEY, "return:search-upstairs"))
                self.assertFalse(_cell_loop_guard_applies(
                    board, policy.last_reason, board.player.position))
                self.post(policy, board, raw, key)

    def test_the_search_bound_reads_the_carried_recall(self):
        """n1-c life-139: the wall search never reached the bound, as its labels
        restarted the count.  DECLARED CONSTRUCTED: the 58 earlier searches, and no
        junk scroll 'h' (destroyed first since the fixture was recorded)."""
        policy = self.policy()
        first, second = (copy.deepcopy(raw) for raw in CASE["boards"][:2])
        for raw in (first, second):
            raw["inventory"] = [item for item in raw["inventory"]
                                if item["tval"] != TVAL_DIGGING and item["slot"] != "h"]
        board, key = self.decide(policy, first)
        self.assertEqual((key, policy.last_reason), (SEARCH_KEY, "return:search-upstairs"))
        self.post(policy, board, first, key)
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        board, key = self.decide(policy, second)
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot, policy.last_reason)


if __name__ == "__main__":
    import unittest
    unittest.main()
