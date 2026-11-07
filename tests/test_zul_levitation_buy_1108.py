"""The Zul trip buys its Ring of Levitation on the shelf it walks to (n1-c life-164).

Owner 2026-11-07 「無ければ指輪を買う」.  Live 2026-11-08 03:50 (n1-c life-164, Lv41,
222,209 gold): ``town:zul:levitation-shop`` walked onto the Magic shop entrance
(38,106), the page listed 浮遊の指輪 {浮} (tval 45 sval 7, 270 gold), and the
in-store selector answered ``shop:observe-and-leave`` (wanted_purchase null,
observed-page-nothing-wanted): ``_next_purchase`` asked the opening Q1 plan and
the staff sequence, never the Zul trip, so the ring existed only as a retention
rung.  The walk stepped off and on the entrance until
``town:blocked:owner-retired-burst``.

Recorded (tests/fixtures/zul-levitation-buy-20261108.json.gz, from n1-c life-164
state.jsonl): ``entrance_board`` is the outside board on the entrance at turn
2972768 and ``store_board`` the Magic shop page of the same turn.

DECLARED CONSTRUCTED / RECONSTRUCTED: the observed mutation signature (no
character sheet in the capture); the policy construction (the production one of
the Q2 tower tests, an empty Home page); the Staff of Remove Curse in the pack
marked bought this visit (the live decision's retention record names it
``visit-purchase``); the store screen verified on its page (the live shadow's
``screen_on_page`` true); the pack and equipment after the purchase.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import zul_trip
from hengbot.model import STORE_MAGIC, parse_snapshot
# The module, not the class: a TestCase bound here would run its tests again.
from tests import test_q2_tower_recharge_recorded as q2_town
from tests.test_zul_trip import MUTATION, wilderness

FIXTURE = Path(__file__).parent / "fixtures" / "zul-levitation-buy-20261108.json.gz"
TVAL_STAFF, SV_STAFF_REMOVE_CURSE = 55, 6


def capture():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class ZulLevitationBuyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        q2_town.Q2TowerRechargeRecordedTest.setUpClass.__func__(cls)
        cls.capture = capture()

    def policy(self, raw):
        policy = q2_town.Q2TowerRechargeRecordedTest.policy(self, raw)
        policy._wilderness_map = wilderness()
        policy._mutation_signature = (MUTATION,)
        return policy

    def board(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.monraces)

    def ring_row(self):
        return next(row for row in self.capture["store_board"]["store"]["items"]
                    if (row["tval"], row["sval"]) == (zul_trip.TVAL_RING, zul_trip.SV_RING_LEVITATION))

    def test_recorded_page_lists_the_ring_the_trip_walks_to(self):
        raw = self.capture["store_board"]
        self.assertEqual(raw["store"]["store_type"], STORE_MAGIC)
        ring = self.ring_row()
        self.assertEqual((ring["letter"], ring["count"], ring["price"]), ("v", 1, 270))
        self.assertEqual(raw["player"]["gold"], 221194)
        self.assertEqual({row["slot"] for row in raw["equipment"]} & set(zul_trip.RING_SLOTS),
                         set(zul_trip.RING_SLOTS))

    def test_recorded_store_page_buys_the_ring(self):
        policy = self.policy(self.capture["entrance_board"])
        outside = self.board(self.capture["entrance_board"])
        key = policy.choose_key(outside)
        self.assertEqual(key, "5", policy.last_reason)  # the entry step onto (38,106)
        store = self.board(self.capture["store_board"])
        staff = next(item for item in store.inventory
                     if (item.tval, item.sval) == (TVAL_STAFF, SV_STAFF_REMOVE_CURSE))
        policy._town_visit_purchases.add(policy._item_signature(staff))
        policy._in_store_screen_verified = True
        key = policy.choose_key(store)
        # Live: '\x1b' shop:observe-and-leave, nothing wanted on this page.
        self.assertEqual((key, policy.last_reason), ("pv\r", "shop:in-store-buy"))
        self.assertEqual(policy._shop_selector_diagnostics["considered_candidate"]["letter"], "v")

    def test_bought_ring_is_put_on_over_the_sub_ring(self):
        raw = copy.deepcopy(self.capture["entrance_board"])
        ring = copy.deepcopy(self.ring_row())
        ring.pop("price")
        ring.pop("letter")
        # The pack sorts the ring (tval 45) between the staffs and the bolts.
        raw["inventory"].insert(12, ring)
        for index, row in enumerate(raw["inventory"]):
            row["slot"] = chr(ord("a") + index)
        raw["player"]["gold"] -= 270
        policy = self.policy(raw)
        key = policy.choose_key(self.board(raw))
        # Both ring slots filled: wield pack slot m, ')' at 「どちらの指輪と取り替えますか?」.
        self.assertEqual((key, policy.last_reason), ("wm)", zul_trip.WEAR_REASON))


if __name__ == "__main__":
    unittest.main()
