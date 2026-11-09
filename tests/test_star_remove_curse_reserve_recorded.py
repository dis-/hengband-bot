"""The *Remove Curse* reserve is a named requirement over the table (star-remove-curse-reserve-1102).

Owner 2026-11-02 21h: 「戦士では1枚取り置く。魔道具術師で解呪の杖を取り込み済なら
買わない。」 -- the one-scroll Home reserve (2026-07, e5e35b331) is bought
although the consumable table has no 「購入する」 on *解呪*
(consumable_policy.RESERVES); an absorbed Remove Curse staff still waives it
(me_capability REPLACES, Powerful Activation casts it).

Recorded input ``star-remove-curse-reserve-20261102.json.gz``
(tests/extract_star_remove_curse_reserve_1102_fixture.py):
  warrior  n1-a life-440 (gold 15688) on the Temple entrance, then the Temple
           page whose ware o is *解呪*の巻物; the recorded bot (before the
           table) bought it (``po\\r``) and shelved it at Home.  Its Home page
           450 turns later (before that deposit) holds no *Remove Curse*.
  me       n1-c life-092 (the Magic-Eater) on the Temple entrance, then the
           Temple page whose ware p is *解呪*の巻物.

DECLARED CONSTRUCTED (named again where built): the Home catalogue of the
warrior's recorded Home page (the capture has no Home list before the visit);
the engine's replies to newly posted keys (tests/test_me_town_stops_recorded
.reply); the Magic-Eater's gold at the reserve's surplus target and its
absorbed Remove Curse staff.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from unittest import mock

from hengbot import consumable_policy, me_staff_sequence
from hengbot.model import (
    SV_SCROLL_STAR_REMOVE_CURSE, SV_STAFF_REMOVE_CURSE, TVAL_SCROLL, _parse_items, parse_snapshot,
)
from hengbot.policy_constants import FUNDRAISING_GOLD_TARGET
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_town_stops_recorded as town_stops
import tests.support.recorded as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "star-remove-curse-reserve-20261102.json.gz"
STAR = "*解呪*の巻物"


class StarRemoveCurseReserveRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post
    reply = town_stops.MagicEaterTownStopsRecordedTest.reply

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def boundary(self, name):
        """The policy on the recorded Temple page (the store visit's first board)."""
        case = self.cases[name]
        policy, raw = lv7.Lv7TownStopRecordedTest().boundary(dict(
            monraces={}, snapshot=case["boards"]["temple"], knowledge=[],
            state={"modes_and_latches": {}}))
        if "home" in case["boards"]:
            # DECLARED CONSTRUCTED: the Home catalogue is the recorded Home page.
            policy.consume_home_knowledge(
                _parse_items(case["boards"]["home"]["store"]["items"], protocol=3))
        # DECLARED CONSTRUCTED: the skill knowledge of this visit was read
        # (as tests/test_consumable_policy_recorded).
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], policy._town_visit_epoch)
        temple = case["boards"]["temple"]["store"]
        self.pages = {str(temple["store_type"]): copy.deepcopy(temple)}
        self.case_cells = case["store_cells"]
        return policy, copy.deepcopy(raw)

    def drive(self, policy, raw, *, limit):
        """choose_key and the production executor until a ware is bought."""
        case = {"store_cells": self.case_cells}
        self.bought, reasons = [], []
        for _ in range(limit):
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            reasons.append((key, policy.last_reason))
            self.assertFalse(policy.last_reason.startswith(town_stops.STOPS), reasons[-8:])
            following = self.reply(policy, raw, key, case)
            self.post(policy, raw, key, following)
            raw = following
            if self.bought:
                break
        return reasons

    def test_recorded_shelves(self):
        for name, letter, class_id in (("warrior", "o", 0), ("me", "p", 16)):
            with self.subTest(name):
                board = self.cases[name]["boards"]["temple"]
                ware = next(it for it in board["store"]["items"] if it["letter"] == letter)
                self.assertEqual((ware["tval"], ware["sval"], ware["name"]),
                                 (TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, STAR))
                self.assertNotIn((TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE),
                                 {(it["tval"], it["sval"]) for it in board["inventory"]})
                self.assertEqual(board["player"]["class_id"], class_id)
        home = self.cases["warrior"]["boards"]["home"]["store"]
        self.assertEqual(home["stock_num"], len(home["items"]))
        self.assertFalse(consumable_policy.discretionary_buy(
            (TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE)))

    def test_warrior_buys_the_one_scroll_reserve(self):
        policy, raw = self.boundary("warrior")
        self.assertEqual(policy._home_star_remove_curse_count, 0)
        self.assertGreaterEqual(raw["player"]["gold"], FUNDRAISING_GOLD_TARGET)
        reasons = self.drive(policy, raw, limit=8)
        self.assertEqual(self.bought, [(STAR, 1)], reasons)
        self.assertEqual(reasons[-1], ("po\r\x1b", "shop:one-shot-buy"))
        # A Home reserve, not carried: the 2026-07 deposit contract.
        self.assertTrue(policy._star_remove_curse_reserve_deposit_pending)

    def test_magic_eater_buys_it_only_until_the_staff_is_absorbed(self):
        for absorbed in (False, True):
            with self.subTest(absorbed=absorbed):
                policy, raw = self.boundary("me")
                # DECLARED CONSTRUCTED: the reserve's other conditions (surplus
                # gold, none at Home, recall scrolls in hand), and for the
                # second case the absorbed Remove Curse staff.
                raw["player"]["gold"] = FUNDRAISING_GOLD_TARGET
                policy._home_star_remove_curse_count = 0
                if absorbed:
                    me_staff_sequence.state(policy).absorbed[
                        f"staff:{SV_STAFF_REMOVE_CURSE}"] = 1
                board = parse_snapshot(raw, policy._monrace_knowledge)
                with mock.patch.object(policy, "_recall_departure_shortage", return_value=False):
                    self.assertEqual(policy._star_remove_curse_reserve_purchase_needed(board),
                                     not absorbed)
                    ware = policy._affordable_star_remove_curse(board)
                self.assertEqual(ware is not None and ware.letter, not absorbed and "p")


if __name__ == "__main__":
    import unittest
    unittest.main()
