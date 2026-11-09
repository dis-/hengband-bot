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
from tests.support import recorded as executor_pins
from tests import test_dungeon_stops_1103_recorded as _test_dungeon_stops_1103_recorded


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-2f-1104" / "board-2f.json.xz"
SHAFT = Position(27, 56)
READ_PROMPT = "どの巻物を読みますか? "


def board_raw() -> dict:
    return json.loads(lzma.decompress(FIXTURE.read_bytes()))


class PostedBoards(_test_dungeon_stops_1103_recorded.RecordedBoards):
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


class StuckLadderAtAKnownStair(PostedBoards):
    """Angband 5F, 22:34: the walk passed '<' [14,51] at decision 2963 and '<'
    [24,80] at 3002, and at 60 steps the stuck bound read a Recall.  22:38: 60
    steps into the walk to the one '<' [12,166] it read another.  Those boards
    were lost with the state log, so the shape is on the 2F board.

    DECLARED CONSTRUCTED: two ordinary up stairs, the exhausted floor (no explore
    step, searched walls, no visible loot; the recorded rows were on that ladder).
    """

    def board_and_policy(self, raw):
        policy = self.fresh_policy(raw)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        here = board.player.position
        far = next(position for position, grid in board.grids.items()
                   if grid.passable and not grid.has_up_stairs and not grid.has_down_stairs
                   and abs(position.y - here.y) + abs(position.x - here.x) > 12
                   and not grid.is_store)
        grids = {position: replace(grid, object_count=0, object_tvals=(),
                                   has_down_stairs=False, has_up_stairs=False)
                 for position, grid in board.grids.items()}
        grids[here] = replace(grids[here], has_up_stairs=True, in_view=True)
        grids[far] = replace(grids[far], has_up_stairs=True, in_view=True)
        board = replace(board, grids=grids, found_items=())
        policy._remembered_downstairs.clear()
        policy._remembered_upstairs.clear()
        policy.prime(board)
        policy._build_grid_index(board)
        policy._visit_counts = Counter({Position(y, x): 1 for y, x in policy._remembered_floor_t})
        policy._probed_frontiers.update(Position(y, x) for y, x in policy._remembered_floor_t)
        policy._blocked_unknown.update(
            (y + dy, x + dx) for y, x in policy._remembered_floor_t
            for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        policy._search_counts[(here.y, here.x)] = SEARCH_LIMIT
        return board, policy

    def test_the_stair_underfoot_is_taken_and_the_walk_is_not_a_dead_end(self):
        raw = board_raw()
        board, policy = self.board_and_policy(raw)
        # Held across a walk: 59 of the bound, then one more walking step.
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT - 1
        policy.last_reason = "stuck:seek-stairs"
        with (
            patch.object(policy, "_skill_exp_request_key", return_value=None),
            patch.object(policy, "_undersearched_walls", return_value=[]),
            patch.object(policy, "_explore_step", return_value=None),
        ):
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (UP_STAIRS_KEY, "stuck:ascend"))
        self.post_key(policy, raw, key)
