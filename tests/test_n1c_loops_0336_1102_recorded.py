"""n1c-loops-0336-1102: the two n1-c loop stops of 2026-11-02 (build bot-df4001950).

life-100 (Magic-Eater, Lv27, オークの洞窟16階, 03:35-03:36, three loop-detected
stops): the only way from (42,92) to the dropped bolts at (42,70)/(42,72) is
the one-wide corridor of row 42, where a モングバット (race 235) hovered at
(42,72)-(42,77).  The grid index leaves every visible monster's cell out of
the walkable floor, so while the bat was in view the loot route had no path:
the floor-loot claim was released (``loot-retarget``) and exploration (after
the restarts, the descent route) stepped '9' out of the corridor to (41,93).
Out of view, the cell was floor again and ``seek-loot`` stepped '1' straight
back, 40 times.  The loot route now passes the cells of the visible hostiles
that do not block loot, so it is the same in and out of view.

life-101 (a new Lv1 character, the Outpost, 03:36-03:38): the General store
had no plain torch for the Q34 carry (20; an ego 灼熱の松明 at 4491 gold
only), so the opening route waited for the restock.  Its wait posted the stay
key '5' — one player turn a decision, ~93 identical decisions per 1,000-turn
wait — and the viewer's stall check stopped it
(``stall-town-wait-restock-general``); the restarts then ended in
``livelock:exhausted``.  The opening wait now posts the shared restock wait's
rest (``RESTOCK_WAIT_MACRO``).

Fixtures: tests/fixtures/n1c-loot-corridor-20261102.json.gz,
n1c-opening-restock-wait-20261102.json.gz
(tests/extract_n1c_loops_0336_1102_fixtures.py).  Every decision is the public
``choose_key`` and every posted key goes through the production executor port.
DECLARED RECONSTRUCTED: the life-100 staff sequence record is the capture's
``_me_staff_sequence``.
DECLARED CONSTRUCTED: the life-101 replies to the posted keys (a walk moves
the player one cell, a walk onto an entrance shows the recorded page,
cmd-move.cpp asks the rest count, a 300-turn rest passes 3,000 game turns).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
import time
import unittest
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import RESTOCK_WAIT_MACRO
from tests import test_d57_nav_depth_1101_recorded as nav
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_town_stops_recorded as stops
import tests.support.recorded as executor_harness


FIXTURES = Path(__file__).with_name("fixtures")


def _load(name):
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as stream:
        return json.load(stream)


LOOT_CASE = _load("n1c-loot-corridor-20261102.json.gz")
RESTOCK_CASE = _load("n1c-opening-restock-wait-20261102.json.gz")
LOOT_CELL, CORRIDOR_EXIT = Position(42, 72), Position(41, 93)
REST_PROMPT = "休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): &"


class LootCorridorRecordedTest(nav.RecordedDrive):
    """life-100: the loot route does not depend on the bat being in view."""

    def test_recorded_rows_alternate_on_the_bat_being_in_view(self):
        rows = {row["turn"]: (row["reason"], row["key"]) for row in LOOT_CASE["decisions"]}
        boards = {raw["turn"]: raw for raw in LOOT_CASE["boards"]}
        self.assertEqual(rows[1469295], ("explore", "9"))
        self.assertEqual(rows[1469310], ("explore", "9"))
        self.assertEqual(rows[1469305], ("seek-loot", "1"))
        self.assertEqual([m["race_id"] for m in boards[1469295]["visible_monsters"]], [235])
        self.assertEqual(boards[1469305]["visible_monsters"], [])

    def test_loot_walk_heads_down_the_corridor_while_the_bat_is_in_view(self):
        # The capture keys absorbed staffs ``staff:<sval>``; the drive's power
        # screen lists them by sval (as test_n1c_5f_loop_1102_recorded).
        record = LOOT_CASE["sequence"]
        case = dict(LOOT_CASE, sequence=dict(record, absorbed={
            key.split(":")[1]: count for key, count in record["absorbed"].items()}))
        boards = copy.deepcopy(LOOT_CASE["boards"])
        policy = nav.new_policy(case, boards)
        rows = self.drive_boards(case, boards, policy)
        # The recorded boards do not follow the drive's walk; the position
        # stuck escape (``breakout``) answering that is not part of the scene.
        in_view = [(raw, key, reason) for raw, key, reason in rows
                   if nav.step_of(raw, key) is not None and raw["visible_monsters"]
                   and reason != "breakout"]
        self.assertGreaterEqual(len(in_view), 3)
        for raw, key, reason in in_view:
            step = nav.step_of(raw, key)
            self.assertEqual(reason, "seek-loot", (raw["turn"], key, reason))
            self.assertLess(step.x, raw["player"]["x"], (raw["turn"], key, reason))
            self.assertNotEqual(step, CORRIDOR_EXIT, (raw["turn"], key, reason))
        self.assertEqual(policy._loot_target, LOOT_CELL)


class OpeningRestockWaitRecordedTest(executor_harness.ProductionHarness):
    """life-101: the opening's restock wait rests instead of posting one stay a turn."""

    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    boundary = stops.MagicEaterTownStopsRecordedTest.boundary
    shop_reply = stops.MagicEaterTownStopsRecordedTest.reply
    shop_post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        # A new character: no checkpoint, no fundraising target.
        cls.cases = {"life-101": dict(RESTOCK_CASE, state={}, supply_stockout_gold_target=None)}

    def reply(self, policy, raw, key, case):
        if key.startswith("R"):
            following = dict(copy.deepcopy(raw), messages=[])
            following["turn"] += 3000  # DECLARED CONSTRUCTED: R300 at normal speed
            return following
        return self.shop_reply(policy, raw, key, case)

    def post(self, policy, raw, key, following):
        if not key.startswith("R"):
            return self.shop_post(policy, raw, key, following)
        game = executor_harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = executor_harness.command_screen(raw["turn"])
        game.screens = [executor_harness.prompt_screen(REST_PROMPT),
                        executor_harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw), copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "n1c-opening-restock-wait", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, (getattr(port.last_result, "reason", None), game.accepted))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, ["R", key[1:]])

    def test_recorded_wait_posted_one_stay_per_decision(self):
        rows = RESTOCK_CASE["decisions"]
        waits = [row for row in rows if row["reason"] == "town:wait-restock:general"]
        self.assertEqual({row["key"] for row in waits}, {"5"})
        self.assertGreaterEqual(len(waits), 8)
        torches = [row for row in rows[-1]["procurement_requirements"]
                   if row["item"] == "Quest throwing torches"]
        self.assertEqual(torches, [{"item": "Quest throwing torches", "current": 5,
                                    "target": 20, "missing": 15}])
        shelf = RESTOCK_CASE["pages"]["0"]["items"]
        self.assertEqual([item["is_ego"] for item in shelf
                          if item["tval"] == 39 and item["sval"] == 0], [True])

    def test_opening_restock_wait_rests_through_the_production_executor(self):
        case = self.cases["life-101"]
        policy, raw = self.boundary("life-101")
        self.pages = copy.deepcopy(case["pages"])
        self.case_cells = case["store_cells"]
        self.bought, reasons = [], []
        for _ in range(40):
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            reasons.append(policy.last_reason)
            if policy.last_reason.startswith("town:wait-restock:"):
                break
            following = self.reply(policy, raw, key, case)
            self.post(policy, raw, key, following)
            raw = following
        else:
            self.fail(reasons[-12:])
        self.assertIn("shop:observe-and-leave", reasons)
        self.assertEqual((policy.last_reason, key), ("town:wait-restock:general", RESTOCK_WAIT_MACRO))
        self.assertEqual(self.bought, [])
        self.post(policy, raw, key, self.reply(policy, raw, key, case))


if __name__ == "__main__":
    unittest.main()
