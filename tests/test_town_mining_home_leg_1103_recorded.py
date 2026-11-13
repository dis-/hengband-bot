"""Recorded town boards of two 2026-11-03 town stops (build 96a499308).

Sources: tests/fixtures/town-uncomposable-n1b-302-1103.json.gz and
town-uncomposable-n1a-469-1103.json.gz
(tests/extract_town_uncomposable_1103_fixtures.py).

n1-b life-302 (Lv30, 09:48, 13,903 gold): a mining fundraising set (mode
"mine", below the 15,000 target) came back to town with 9 of 10 Cure
Critical Wounds, 6 of 20 identify-staff charges and no Treasure Detection.
The set filed only its kit (Home, which stored the detection).  The Home leg
was owned by a withdraw request for 守りの毛皮のクローク the visit had already
deferred; the Home pass composed nothing
(shop:observed-operation-uncomposable) and the town end stopped on
town:blocked:survival:cure_critical_ready.

n1-a life-469 (09:02): the atomic withdraw took all nine スピードの薬; the
pending withdrawal of one stayed, the current Home page had none, every Home
leg was refused reservation-unavailable and the visit stopped under
town:blocked:unmet:home_candidate_resolved.

Owner 2026-11-03 「道具の後に足りない分を買う」: in a mining set the kit
comes first (11-02 「採掘の要求品が優先」), then the remaining gold buys the
departure-survival shortfall.  Every decision is the public ``choose_key``;
the keys go through the production executor port.

DECLARED CONSTRUCTED: each policy is fresh from the fixture's first board
(the live processes started long before the rings), with
``_fundraising_mode = "mine"`` (the recorded rows' fundraising mode).
* shortfall case: one carried 財宝感知の巻物 (the Home stock's row) so the
  kit is secured;
* deferred-request case: the recorded policy-state's Home visit request
  (legacy-withdrawal of the cloak) filed and the cloak deferred, as
  ``_deferred_home_items`` recorded;
* carried-take case: the recorded policy-state's ``_home_pending_item``
  (スピードの薬, quantity 1) and the 772014 Home knowledge row without the
  potions taken at 772871 (the 773691 page).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from tests.support import item_use_route_wall
from pathlib import Path

from hengbot.home_visit import HomeVisitKind, HomeVisitRequest
from hengbot.model import parse_snapshot
from hengbot.policy_constants import STORE_ALCHEMIST, STORE_HOME, STORE_MAGIC, STORE_TEMPLE
from tests import test_n1c_deaths_1101_recorded as d57


FIXTURES = Path(__file__).with_name("fixtures")


def _load(name):
    with gzip.open(FIXTURES / f"town-uncomposable-{name}-1103.json.gz", "rt",
                   encoding="utf-8") as stream:
        return json.load(stream)


CASE_302, CASE_469 = _load("n1b-302"), _load("n1a-469")
CLOAK = ("守りの毛皮のクローク [3,+15]", 35, 3)
SPEED = ("スピードの薬", 75, 29)


def mining_policy(case):
    policy = d57.loops.new_policy(case, case["skill"], monraces=case["monraces"])
    policy._fundraising_mode = "mine"
    return policy


def with_detection(case):
    case = copy.deepcopy(case)
    scroll = next(item for item in case["home"]["knowledge"]["items"]
                  if item["name"].startswith("財宝感知の巻物"))
    for raw in case["boards"]:
        raw["inventory"].append(dict(copy.deepcopy(scroll), count=1, slot="z"))
    return case


class TownMiningHomeLegRecordedTest(d57.PostedDeathKey):
    def setUp(self):
        super().setUp()
        item_use_route_wall.hold(self)  # wall, declared: tests/support/item_use_route_wall.py

    def test_recorded_rows(self):
        recorded = d57.recorded(CASE_302)
        self.assertEqual(recorded[1376553][0],
                         "town:entrance-step-off:shop:observed-operation-uncomposable")
        self.assertEqual(recorded[1376559][0], "town:blocked:survival:cure_critical_ready")
        self.assertEqual(d57.recorded(CASE_469)[773711][0],
                         "town:blocked:unmet:home_candidate_resolved")

    def test_mining_set_buys_the_survival_shortfall_after_the_kit(self):
        case = with_detection(CASE_302)
        policy = mining_policy(case)
        boards = [copy.deepcopy(raw) for raw in case["boards"][:2]]
        policy.confirm_key_posted(d57.loops.decide(policy, boards[0]))
        key = d57.loops.decide(policy, boards[1])
        self.assertTrue(policy._fundraising_kit_secured(
            parse_snapshot(copy.deepcopy(boards[1]), policy._monrace_knowledge)))
        plan = policy._town_errand_plan
        categories = {category for values in plan.need_categories.values()
                      for category in values}
        self.assertTrue({"cure-critical", "identify-staff"} <= categories, plan.need_categories)
        self.assertTrue({STORE_TEMPLE, STORE_ALCHEMIST, STORE_MAGIC} & set(plan.stops), plan.stops)
        self.assertEqual(policy.last_reason, "shop:travel")
        self.assertNotEqual(plan.stops[plan.index], STORE_HOME)
        self.post(policy, boards[1], key)

    def test_deferred_withdraw_request_does_not_own_the_home_leg(self):
        case = dict(CASE_302, boards=CASE_302["boards"][3:])
        policy = mining_policy(case)
        self.assertEqual(policy._home_visit.file(HomeVisitRequest(
            HomeVisitKind.WITHDRAW, "legacy-withdrawal",
            item_identity=CLOAK, address=CLOAK)), "filed")
        policy._defer_home_item(CLOAK, "constructed")
        raw = copy.deepcopy(case["boards"][0])
        key = d57.loops.decide(policy, raw)
        request = policy._home_visit.request
        self.assertFalse(request is not None and request.item_identity == CLOAK)
        self.post(policy, raw, key)

    def test_carried_take_retires_the_pending_withdrawal(self):
        case = copy.deepcopy(CASE_469)
        case["home"]["knowledge"]["items"] = [
            item for item in case["home"]["knowledge"]["items"]
            if not item["name"].startswith("スピードの薬")]
        case["boards"] = case["boards"][1:]
        policy = mining_policy(case)
        policy._home_pending_item, policy._home_pending_quantity = SPEED, 1
        raw = copy.deepcopy(case["boards"][0])
        key = d57.loops.decide(policy, raw)
        self.assertIsNone(policy._home_pending_item)
        self.assertFalse(policy.last_reason.startswith("town:blocked"), policy.last_reason)
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
