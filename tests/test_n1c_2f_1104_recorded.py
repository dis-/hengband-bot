"""n1-c life-139, 2026-11-04 (build aa7b42b89): the walking return on Angband 2F.

Owner: 「n1-cがangband 2Fで様子がおかしい」.  A return latched on 4F by
combat:avoid-unprofitable-unique walked up with Recall in the pack, because
depth <= WALK_OUT_MAX_DEPTH spares the scroll.  Angband's top leads to the
wilderness, so that walk cannot reach town.  2F's one known '<' [27,56] was a
shaft to the wilderness, rightly refused; it stood on it at decision 9537 and
searched on, 8 's' per cell for over 8 minutes.

Fixture: tests/extract_n1c_2f_1104_fixture.py (the last board on the floor).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key, _transport_key
from hengbot.model import Position, parse_snapshot
from hengbot.policy import SEARCH_LIMIT
from hengbot.policy_constants import STUCK_ESCAPE_LIMIT, UP_STAIRS_KEY, WALK_OUT_MAX_DEPTH
from hengbot.wilderness_exit import SHAFT_TERRAIN_IDS
from tests import test_input_executor as executor_pins
from tests.test_dungeon_stops_1103_recorded import RecordedBoards


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-2f-1104" / "board-2f.json.xz"
SHAFT = Position(27, 56)
READ_PROMPT = "どの巻物を読みますか? "


def board_raw() -> dict:
    return json.loads(lzma.decompress(FIXTURE.read_bytes()))


class PostedBoards(RecordedBoards):
    def post_key(self, policy, raw: dict, key: str, prompts=()) -> None:
        """Post ``key`` through the production executor."""
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(prompt) for prompt in prompts] + [
            executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [copy.deepcopy(raw) for _ in prompts] + [
            dict(copy.deepcopy(raw), turn=raw["turn"] + 10)]
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
        self.assertEqual("".join(game.accepted), _transport_key(key, True))


class WalkingReturnOnAngband2F(PostedBoards):
    def test_the_recall_is_read_where_the_walk_cannot_reach_town(self):
        raw = board_raw()
        policy = self.fresh_policy(raw)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(board.floor_key, (1, 2, 0))
        self.assertLessEqual(board.dungeon_level, WALK_OUT_MAX_DEPTH)
        self.assertIn(board.grids[SHAFT].terrain_id, SHAFT_TERRAIN_IDS)
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        # SEED: the latched return of the decision log (objective "Return to town").
        policy._returning_to_town = True

        key = self.decide(policy, raw)

        self.assertEqual((key, policy.last_reason), ("r" + recall.slot, "return:recall"))
        self.post_key(policy, raw, key, prompts=[READ_PROMPT])
