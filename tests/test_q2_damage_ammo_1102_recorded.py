"""Q2 launcher.average_damage: buy the shelf bolts whose shot reaches 25.

Owner 2026-11-02 23h (verbatim): 「矢の購入で条件を満たせるときは買う。
武器ダメージ増加の購入と使用が機能していることを確認して、機能しているなら
他の修正はいらない。」

Recorded board (tests/fixtures/q2-damage-ammo-1102.json.gz,
tests/extract_q2_damage_ammo_1102_fixture.py): n1-c life-111, the Lv21
Magic-Eater in the Weapon Smith at turn 945241 with a light crossbow (x3)
(+6,+3) and 95 plain bolts (1d5); Q2's force measured (3+0+3)x3 = 18 < 25.
The shelf held one bolt (1d5) (+5,+3): (3+3+3)x3 = 27.  The quest carry only
bought plain store ammo and the force measured the first carried stack, so
decision 10638 left the page (observed-page-nothing-wanted).

The public choose_key now buys that bolt, the posted key goes through the
production executor, and on the post-purchase board the force's launcher rows
pass with the quest executor firing the measured (power) stack.

DECLARED RECONSTRUCTED: the shopping visit of decisions 10637/10638
(``store_visit`` town-errand/acquire at the Weapon Smith), the staff power
list read in this process; the capture keeps no Home page or skill reply (the
Home is empty, as in the Q2 harness).
DECLARED CONSTRUCTED: the purchase replies (purchase-order.cpp prompts) and
the post-purchase board: the bought bolt as its own stack after the plain one
(object-sort.cpp: bolts of a lower to_h+to_d sort first), 62 gold spent.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import me_staff_sequence
from hengbot.model import STORE_WEAPON, parse_snapshot
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from tests import test_me_speed_staff_1101_recorded as speed
from tests import test_input_executor as executor_pins


with gzip.open(Path(__file__).with_name("fixtures") / "q2-damage-ammo-1102.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
BOLT_LETTER = "n"


class Q2DamageAmmoRecordedTest(executor_pins.ProductionHarness):
    _purchase = speed.SpeedPotionPurchaseRecordedTest
    setUpClass = classmethod(_purchase._town.setUpClass.__func__)
    policy = _purchase.policy
    decide = _purchase.decide
    post_buy = _purchase.post_buy

    def visit(self):
        raw = copy.deepcopy(CASE["board"])
        policy = self.policy(raw)
        me_staff_sequence.state(policy).powers_read = True
        policy._store_visit = StoreVisit("town-errand", "shopping", STORE_WEAPON,
                                         phase=StoreVisitPhase.ENTERING, opened_sequence=10637,
                                         visit_origin="acquire")
        policy._decision_sequence = 10637
        policy.observe_store_screen(True)
        return policy, raw, self.decide(policy, raw)

    def carries(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        policy._approved_strategy_force_ready(board, policy.approved_quest_strategy(2))
        return policy._fixed_quest_readiness["strategy_force"]["carries"]

    def test_recorded_page_buys_the_damage_bolt_and_the_force_passes(self):
        rows = {row["decision_sequence"]: row for row in CASE["decisions"]}
        self.assertEqual(rows[10637]["store_visit"]["store_type"], STORE_WEAPON)
        self.assertEqual((rows[10638]["reason"], rows[10638]["shop_selector"]["rejection_reason"]),
                         ("shop:observe-and-leave", "observed-page-nothing-wanted"))
        self.assertEqual(rows[10638]["carries"]["launcher.average_damage"],
                         {"measured": 18.0, "required": 25.0, "ready": False})

        policy, raw, key = self.visit()
        self.assertEqual((key, policy.last_reason), ("pn\r", "shop:in-store-buy"))
        ware = next(item for item in raw["store"]["items"] if item["letter"] == BOLT_LETTER)
        self.assertEqual((ware["tval"], ware["count"], ware["to_h"], ware["to_d"], ware["price"]),
                         (18, 1, 5, 3, 62))
        game = self.post_buy(policy, raw, key)
        self.assertEqual("".join(game.accepted), key)

        # The post-purchase board: the bought bolt after the plain stack.
        after = copy.deepcopy(raw)
        after.pop("store")
        after["player"]["gold"] -= ware["price"]
        plain = next(i for i, item in enumerate(after["inventory"]) if item["tval"] == 18)
        bought = {**copy.deepcopy(after["inventory"][plain]), **{
            name: ware[name] for name in ("name", "count", "to_h", "to_d", "price")}}
        bought.pop("price")
        after["inventory"].insert(plain + 1, bought)
        for index, item in enumerate(after["inventory"]):
            item["slot"] = chr(ord("a") + index)
        carries = self.carries(policy, after)
        self.assertEqual(carries["launcher.average_damage"],
                         {"measured": 27.0, "required": 25.0, "ready": True})
        self.assertTrue(carries["launcher"]["ready"])
        board = parse_snapshot(copy.deepcopy(after), self.monraces)
        fired = policy._quest_profile_ammo(board, policy.approved_quest_strategy(2))
        self.assertEqual((fired.slot, fired.to_d, fired.count), (bought["slot"], 3, 1))


if __name__ == "__main__":
    unittest.main()
