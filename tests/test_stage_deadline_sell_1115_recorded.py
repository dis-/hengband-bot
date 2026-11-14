"""A stage that keeps completing its work does not spend its deadline (2026-11-15).

Recorded: n1-b life-397 (2026-11-15 00:48:40, Magic-Eater Lv47) stopped at
town:blocked:stage-deadline:sell in the middle of a run of sales: inscribe and sell, one item
after another, each sale raising the gold (rows 186-202).  The town-arrival checkpoint,
journal rows and sidecar files (tests/extract_stage_deadline_sell_1115_fixture.py) replay
through the public choose_key with the recorded keys posted.  On the stop row (203) the sell
stage, whose count restarted at each observed sale (town_visit_plan.note_observed_progress),
takes its next action instead: it leaves the store, the sales done (shop:in-store-done), and
the production executor port posts that key on the recorded store board.

DECLARED: rows 169-185 are posted with their recorded keys.  They follow the periodic
character dump of row 164 (and the dumps of rows 170, 176 and 178), whose dump file the
game wrote on the viewing server and no capture keeps; without it the replayed calibration
stays required after each stat-restore potion, the shop-buy owner's progress vector repeats
and the arbiter retires it (town:blocked:owner-retired on row 169), on main as on this
change.  The live bot bought and quaffed there.  Rows 0-168 and 186-202 replay as recorded.
DECLARED CONSTRUCTED: the game's screens around the posted Escape (a store screen, then the
map) and the board after it (the stop board, its turn advanced, outside the store).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import town_visit_plan
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load
from tests.support import recorded as executor_pins

FIXTURES = Path(__file__).with_name("fixtures") / "stage-deadline-sell-1115"
STOP = "town:blocked:stage-deadline:sell"
STOP_ROW = 203
DUMP_GAP = range(169, 186)
SALE_RUN = range(186, 203)


def store_page_screen(store):
    """DECLARED CONSTRUCTED: the store page with the recorded stock and the menu rows
    (the recorded page's 52 rows need a taller terminal than the harness's)."""
    screen = executor_pins.store_screen()
    menu = screen["lines"][20:22]
    screen["lines"] = screen["lines"][:6] + [""] * 56
    screen["height"] = len(screen["lines"])
    for index, item in enumerate(store["items"]):
        screen["lines"][6 + index] = f"{item['letter']}) {item['name']}"
    screen["lines"][58:60] = menu
    screen["cursor"] = {"visible": True, "y": 58, "x": 0}
    return screen


class StageDeadlineSell1115RecordedTest(executor_pins.ProductionHarness):
    def test_n1b_397_sale_run_goes_on(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURES / "n1b397", Path(scratch.name))
        self.assertEqual(len(steps), STOP_ROW + 1)
        self.assertEqual(steps[STOP_ROW][0]["reason"], STOP)
        sell_counts = []
        for index, (row, supply) in enumerate(steps):
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            decided = (key, policy.last_reason)
            sell_counts.append(policy._town_visit.stage_decisions.get("sell", 0))
            if index == STOP_ROW:
                break
            if index in DUMP_GAP:
                key = row["key"]
            else:
                self.assertEqual(decided, (row["key"], row["reason"]), index)
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        self.assertEqual(decided, ("\x1b", "shop:in-store-done"))
        self.assertFalse(policy.last_reason.startswith(town_visit_plan.STAGE_DEADLINE_STOP_PREFIX))
        # The visit's sell operations pass the deadline; the count since the
        # last observed sale stays far below it.
        traced = sum(segment[3] for segment in policy._town_visit.plan_segments
                     if segment[0] == "sell")
        self.assertGreaterEqual(traced, town_visit_plan.STAGE_DEADLINES["sell"])
        self.assertLessEqual(max(sell_counts[index] for index in SALE_RUN), 2)
        self.assertLess(max(sell_counts), town_visit_plan.STAGE_DEADLINES["sell"])
        self.assert_posts(policy, recorded[STOP_ROW], board, key)

    def assert_posts(self, policy, row, board, key):
        """The production executor posts ``key`` on the recorded store board."""
        raw = json.loads(row["line"] if row["line"] is not None else row["inputs"][-1])
        self.assertIsNotNone(raw.get("store"))
        game = executor_pins.FaithfulHookGame()
        game.state, game.jsonl = copy.deepcopy(raw), [copy.deepcopy(raw)]
        game.screen = store_page_screen(raw["store"])
        outside = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, store=None)
        game.screens, game.states = [executor_pins.command_screen(outside["turn"])], [outside]
        _game, _client, executor = self.make(game)
        result = executor.observe_boundary(deadline=9999999999)
        self.assertEqual(result.outcome, "ready", result)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-store-board", key, None, set(), in_store=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, [key])


if __name__ == "__main__":
    unittest.main()
