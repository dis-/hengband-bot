"""Shop entrances on a dungeon floor are not entered (owner 2026-11-04 「入らない」).

n1-c life-139.  Angband 2F: the recorded board with its underground city.
Angband 5F, 22:42 (decisions 6503-6519, store 2): shop:observe-and-leave and
shop:one-shot-buy '5' alternated 8 rounds for crossbow bolts, no purchase.  Those
boards went with the truncated state log.

DECLARED CONSTRUCTED: the store page is a recorded town page (the bolts on the
shelf of row 6503) placed on the 2F board; the dead end of the last test.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import LEAVE_STORE_KEY, NEIGHBOR_OFFSETS
from tests import test_input_executor as executor_pins
from tests.test_dungeon_stops_1103_recorded import RecordedBoards


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-2f-1104" / "board-2f.json.xz"
ENTRANCES = (Position(28, 77), Position(31, 86), Position(31, 90), Position(33, 69),
             Position(35, 68), Position(36, 80), Position(36, 85), Position(38, 71))
STORE_WEAPON = 2
TVAL_BOLT = 18

def board_raw() -> dict:
    return json.loads(lzma.decompress(FIXTURE.read_bytes()))


class ShopEntrancesOnADungeonFloor(RecordedBoards):
    def post(self, policy, raw: dict, key: str) -> None:
        """Post ``key`` through the production executor, from the store page."""
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
        outside = copy.deepcopy(raw)
        outside.pop("store")
        game.states = [dict(outside, turn=raw["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract(),
        )
        self.assertTrue(sent, port.last_result.stop_line)

    def test_the_entrances_are_no_route_and_no_frontier(self):
        raw = board_raw()
        policy = self.fresh_policy(raw)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy._build_grid_index(board)
        for cell in ENTRANCES:
            grid = board.grids[cell]
            self.assertTrue(grid.is_store, cell)
            self.assertNotIn((cell.y, cell.x), policy._floor_t)
            self.assertFalse(policy._is_frontier(board, grid))

    def test_a_page_is_left_at_once_and_the_next_board_does_not_reenter(self):
        raw = board_raw()
        bolts = next(item for item in raw["inventory"] if item["tval"] == TVAL_BOLT)
        raw["store"] = {"store_type": STORE_WEAPON, "page": 0, "stock_num": 1, "page_count": 1,
                        "items": [dict(bolts, letter="q", price=3, count=82)]}
        policy = self.fresh_policy(raw)
        self.assertEqual((self.decide(policy, raw), policy.last_reason),
                         (LEAVE_STORE_KEY, "shop:store-context-exit"))
        self.assertIsNone(policy._store_visit)
        self.post(policy, raw, LEAVE_STORE_KEY)
        self.assertIsNone(policy._shop_observation)
        outside = board_raw()
        outside["turn"] = raw["turn"] + 10
        key = self.decide(policy, outside)
        self.assertFalse(policy.last_reason.startswith("shop:"), (key, policy.last_reason))

    def test_a_dead_end_whose_only_step_is_an_entrance_takes_it(self):
        raw = board_raw()
        policy = self.fresh_policy(raw)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        entrance = ENTRANCES[0]
        here = Position(entrance.y - 1, entrance.x)
        grids = dict(board.grids)
        floor_cell = next(grid for grid in grids.values() if grid.passable and not grid.is_store)
        grids[here] = replace(floor_cell, position=here)
        for dy, dx in NEIGHBOR_OFFSETS:
            cell = Position(here.y + dy, here.x + dx)
            if cell != entrance and cell in grids:
                grids[cell] = replace(grids[cell], passable=False, wall=True)
        board = replace(board, grids=grids, player=replace(board.player, position=here))
        policy._remembered_floor_t.clear()
        policy._build_grid_index(board)
        self.assertEqual(policy._least_visited_neighbor(board), entrance)
        with patch.object(policy, "_engagement_avoid_cells", {entrance}):
            self.assertIsNone(policy._least_visited_neighbor(board))
