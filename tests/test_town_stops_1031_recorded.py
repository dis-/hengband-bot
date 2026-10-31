"""Issue #47, 2026-10-31: recorded town-family stops of the viewing bots.

Every case starts from a fresh production policy with the source-derived town
map (``test_opening_route_r2_recorded``) and feeds the recorded boards of
``fixtures/town-stops-1031.json.gz`` (see ``extract_town_stops_1031_fixture``)
through the public chooser in their recorded order.  Replies to newly posted
keys are declared constructed; keys are posted through the production
executor.
"""
import tests  # noqa: F401

import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

from hengbot.cli import TOWN_BLOCKED_STOP_LIMIT, _advance_town_blocked_iteration
from hengbot.model import _parse_items, parse_snapshot
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_opening_route_r2_recorded as round2
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "town-stops-1031.json.gz"


class TownStops1031RecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        round2.OpeningRouteR2RecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def row(self, case, wanted):
        return next(row for index, row in self.cases[case]["rows"] if index == wanted)

    def replay(self, case, last, *, skip=(), in_store=False, prepare=None):
        """Feed the recorded rows through the public chooser up to ``last``."""
        policy, _ = round2.OpeningRouteR2RecordedTest().case("1")
        policy._in_store_ops_enabled = in_store
        primed, decisions = False, {}
        for index, row in self.cases[case]["rows"]:
            if index in skip:
                continue
            if row.get("type") == "knowledge":
                knowledge = row["knowledge"]
                if knowledge["category"] == "skill_exp":
                    policy.consume_skill_knowledge(row)
                elif knowledge["category"] == "home":
                    policy.consume_home_knowledge(_parse_items(knowledge["items"], protocol=3))
                continue
            board = parse_snapshot(row, policy._monrace_knowledge)
            if not primed:
                policy.prime(board)
                primed = True
                if prepare is not None:
                    prepare(policy)
            if in_store:
                policy.observe_store_screen(board.store is not None)
            decisions[index] = (policy.choose_key(board), policy.last_reason)
            if index == last:
                return policy, row, decisions
        raise AssertionError(f"row {last} not in {case}")

    def test_town1_first_absorb_after_home_is_not_an_oscillation(self):
        # n1-b life-276 08:44: the hungry zombie left Home (two Home pages with
        # the same position-free progress state) and every absorb was rewritten
        # into a walk toward the Alchemist until the detectors retired.
        policy, raw, decisions = self.replay("town1", 115)
        self.assertEqual(decisions[112], ("~9\x1b", "home:request-knowledge-scan"))
        self.assertEqual(decisions[114], ("\x1b", "home:leave-for-pending-withdraw"))
        self.assertEqual(parse_snapshot(raw, policy._monrace_knowledge).player.food_state,
                         "hungry")
        self.assertEqual(decisions[115], ("Ef", "survival:mana-absorb"))
        # DECLARED CONSTRUCTED: the engine's reply to the absorb.
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        self.post(policy, raw, "Ef", following)

    def fuse(self, rows):
        """Drive the production town-block fuse over recorded decision rows."""

        class Recorded:
            # The recorded run stopped with no durable town change, so every
            # row carries the same progress state (DECLARED CONSTRUCTED).
            def _town_progress_fingerprint(self, _snapshot):
                return ("recorded-town-state",)

        policy, snapshot = Recorded(), SimpleNamespace(in_town=True)
        streak, durable, peak = 0, None, 0
        for row in rows:
            policy.last_reason = row["reason"]
            policy.decision_claim = {
                "claim_id": row["claim_id"], "distance": row["distance"],
                "goal": {"kind": row["goal_kind"]},
            }
            streak, durable = _advance_town_blocked_iteration(
                policy, snapshot, streak, durable, key=row["key"])
            peak = max(peak, streak)
        return streak, peak

    def test_loops4_5_walk_and_fight_after_one_block_do_not_trip_the_fuse(self):
        # n1-c life-057 08:34 / 08:45: one town:blocked line, then a walk to the
        # down staircase (08:34) or a fight with a fleeing town monster (08:45)
        # reached TOWN_BLOCKED_STOP_LIMIT and stopped the bot as loop-detected.
        for name in ("walk", "fight"):
            with self.subTest(name):
                rows = self.cases["fuse"][name]
                self.assertTrue(rows[0]["reason"].startswith("town:blocked:"))
                self.assertEqual(len(rows), TOWN_BLOCKED_STOP_LIMIT)
                _, peak = self.fuse(rows)
                self.assertLess(peak, TOWN_BLOCKED_STOP_LIMIT // 2)

    def test_repeated_blocks_between_the_recorded_walk_steps_still_trip_the_fuse(self):
        rows = self.cases["fuse"]["walk"]
        repeated = [rows[0]] * TOWN_BLOCKED_STOP_LIMIT
        self.assertEqual(self.fuse(repeated)[0], TOWN_BLOCKED_STOP_LIMIT)
        # A walk that never closes on its goal still counts every step.
        stalled = [rows[0]] + [dict(row, distance=rows[1]["distance"])
                               for row in rows[1:] if row["goal_kind"] == "Reach"]
        stalled += [stalled[-1]] * (TOWN_BLOCKED_STOP_LIMIT - len(stalled))
        self.assertEqual(self.fuse(stalled)[0], TOWN_BLOCKED_STOP_LIMIT)

    def test_town2_home_first_leave_on_a_later_page_ends_the_entry(self):
        # n1-b life-276 08:49: after an inscribe and a sale on the Alchemist
        # page, the continuation selected a departure-blocking buy, _shop sent
        # it Home first (ESC, shop:home-first-before-purchase), and the entry
        # called that mismatch shop-required-operation-uncomposable and stopped.
        home = self.row("town1", 113)
        alchemist = parse_snapshot(self.row("town1", 108), None).store

        def prepare(policy):
            # DECLARED RECONSTRUCTED: the process had read Home (turn 1092865)
            # and the Alchemist's shelf (turn 1092564) earlier in this life; the
            # capture of the stop starts in the dungeon, so both come from the
            # same life's previous capture (fixture case town1).
            policy.consume_home_knowledge(_parse_items(home["knowledge"]["items"], protocol=3))
            policy._town_supplier_stock[4] = alchemist

        policy, raw, decisions = self.replay(
            "town2", 131, skip={128}, in_store=True, prepare=prepare)
        self.assertEqual(decisions[129], ("{h@0\r", "shop:in-store-inscribe"))
        self.assertEqual(decisions[130], ("d0y", "shop:in-store-sell"))
        self.assertEqual(policy.in_store_decision_telemetry()["fallback"]["shop_reason"],
                         "shop:home-first-before-purchase")
        self.assertEqual(decisions[131], ("\x1b", "shop:in-store-done"))
        self.assertNotIn("required-page-continuation", policy._shop_selector_diagnostics)
        # DECLARED CONSTRUCTED: the engine's reply to the leave is the recorded
        # Alchemist entrance board with the post-sale pack and gold.
        outside = copy.deepcopy(self.row("town2", 128))
        outside.update(turn=raw["turn"] + 1, messages=[],
                       inventory=copy.deepcopy(raw["inventory"]))
        outside["player"]["gold"] = raw["player"]["gold"]
        self.post(policy, raw, "\x1b", outside)
        policy.choose_key(parse_snapshot(outside, policy._monrace_knowledge))
        self.assertFalse((policy.last_reason or "").startswith("town:blocked:"),
                         policy.last_reason)
