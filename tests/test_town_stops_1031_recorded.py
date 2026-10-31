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

    def replay(self, case, last):
        """Feed the recorded rows through the public chooser up to ``last``."""
        policy, _ = round2.OpeningRouteR2RecordedTest().case("1")
        primed, decisions = False, {}
        for index, row in self.cases[case]["rows"]:
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
