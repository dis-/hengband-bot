"""Q2 launcher.average_damage: buy shelf bolts when the carried 99 rounds reach 25.

Owner 2026-11-02 23h (verbatim): 「矢の購入で条件を満たせるときは買う。
武器ダメージ増加の購入と使用が機能していることを確認して、機能しているなら
他の修正はいらない。」  2026-11-03 (verbatim choice): 「持つ99発の平均で25」 --
the force measures the count-weighted shot average over the carried rounds
(power stack, then plain stack, up to the 99 the force carries).

Recorded board (tests/fixtures/q2-damage-ammo-1102.json.gz,
tests/extract_q2_damage_ammo_1102_fixture.py): n1-c life-111, the Lv21
Magic-Eater in the Weapon Smith at turn 945241 with a light crossbow (x3)
(+6,+3) and 95 plain bolts (1d5): (3+0+3)x3 = 18 < 25.  The shelf: n) 1x
(+5,+3) = 27, o) 29x (+5,+2) = 24, p) 22x (+2,+2) = 24, q) plain.  No single
stack lifts the 99-round average to 25 (the best, 29x 24 + 70x 18, is 19.8),
so the recorded shelf buys no damage ammo (the plain top-up ``pq4`` as
before), and one carried (+5,+3) bolt leaves the average at 18.1.

DECLARED CONSTRUCTED (the positive case): the same shelf with 99 of the
(+5,+3) bolts.  The public choose_key buys all 99, the posted key goes
through the production executor, and on the post-purchase board the force's
launcher rows pass (27) with the quest executor firing that stack first.

DECLARED RECONSTRUCTED: the shopping visit of decisions 10637/10638
(``store_visit`` town-errand/acquire at the Weapon Smith), the staff power
list read in this process; the capture keeps no Home page or skill reply (the
Home is empty, as in the Q2 harness).
DECLARED CONSTRUCTED: the purchase replies (purchase-order.cpp prompts) and
the post-purchase boards: the bought bolts as their own stack after the plain
one (object-sort.cpp: bolts of a lower to_h+to_d sort first), gold spent.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
from pathlib import Path
import time
import unittest

from hengbot import me_staff_sequence
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.model import STORE_WEAPON, parse_snapshot
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from tests import test_me_speed_staff_1101_recorded as speed
from tests import test_input_executor as executor_pins
from tests import test_classA_observed_input as follow_harness
from tests import test_lv7_town_stop_recorded as lv7


with gzip.open(Path(__file__).with_name("fixtures") / "q2-damage-ammo-1102.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
BOLT_LETTER = "n"


class Q2DamageAmmoRecordedTest(executor_pins.ProductionHarness):
    _purchase = speed.SpeedPotionPurchaseRecordedTest
    setUpClass = classmethod(_purchase._town.setUpClass.__func__)
    policy = _purchase.policy
    decide = _purchase.decide

    def post_buy(self, policy, raw, key):
        """The quantity purchase through the executor (purchase-order.cpp prompts)."""
        ware = next(item for item in raw["store"]["items"] if item["letter"] == key[1])
        quantity = int(key[2:].rstrip(chr(13)))
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["player"]["gold"] -= ware["price"] * quantity
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        shelf = lv7.Lv7TownStopRecordedTest.shelf_screen
        game.screen = shelf(raw)
        # The recorded item prompt, the quantity and price questions
        # (store/purchase-order.cpp), the shelf again.
        game.screens = [follow_harness.recorded("live-screen-cap-05-alchemist-buy-p.json"),
                        executor_pins.prompt_screen(f"いくつですか (1-{ware['count']}): 1"),
                        executor_pins.prompt_screen(
                            f"買値 ${ware['price'] * quantity} で買いますか？[Y/n]"),
                        shelf(following)]
        game.states = [copy.deepcopy(raw)] * 3 + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "q2-damage-ammo", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), self.monraces),
            posting_contract=PostingContract(), in_store=True)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        return game

    def visit(self, raw):
        policy = self.policy(raw)
        me_staff_sequence.state(policy).powers_read = True
        policy._store_visit = StoreVisit("town-errand", "shopping", STORE_WEAPON,
                                         phase=StoreVisitPhase.ENTERING, opened_sequence=10637,
                                         visit_origin="acquire")
        policy._decision_sequence = 10637
        policy.observe_store_screen(True)
        return policy, self.decide(policy, raw)

    def carries(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        policy._approved_strategy_force_ready(board, policy.approved_quest_strategy(2))
        return policy._fixed_quest_readiness["strategy_force"]["carries"]

    @staticmethod
    def bought(raw, ware, count):
        """The board after buying ``count`` of ``ware`` (after the plain stack)."""
        after = copy.deepcopy(raw)
        after.pop("store")
        after["player"]["gold"] -= ware["price"] * count
        plain = next(i for i, item in enumerate(after["inventory"]) if item["tval"] == 18)
        stack = {**copy.deepcopy(after["inventory"][plain]), **{
            name: ware[name] for name in ("name", "to_h", "to_d")}, "count": count}
        after["inventory"].insert(plain + 1, stack)
        for index, item in enumerate(after["inventory"]):
            item["slot"] = chr(ord("a") + index)
        return after, stack["slot"]

    def test_recorded_shelf_cannot_reach_the_99_round_average(self):
        rows = {row["decision_sequence"]: row for row in CASE["decisions"]}
        self.assertEqual(rows[10637]["store_visit"]["store_type"], STORE_WEAPON)
        self.assertEqual((rows[10638]["reason"], rows[10638]["shop_selector"]["rejection_reason"]),
                         ("shop:observe-and-leave", "observed-page-nothing-wanted"))
        self.assertEqual(rows[10638]["carries"]["launcher.average_damage"],
                         {"measured": 18.0, "required": 25.0, "ready": False})
        raw = copy.deepcopy(CASE["board"])
        shelf = [(item["letter"], item["count"], item["to_h"], item["to_d"])
                 for item in raw["store"]["items"] if item["tval"] == 18]
        self.assertEqual(shelf, [("n", 1, 5, 3), ("o", 29, 5, 2), ("p", 22, 2, 2), ("q", 99, 0, 0)])
        policy, key = self.visit(raw)
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        self.assertIsNone(policy._quest_damage_ammo_ware(
            board, policy.approved_quest_strategy(2).required_force, board.store))
        self.assertEqual((key, policy.last_reason), ("pq4\r\r", "shop:in-store-buy"))
        # One strong bolt does not pass: (27 + 95 x 18) / 96.
        ware = next(item for item in raw["store"]["items"] if item["letter"] == BOLT_LETTER)
        after, _slot = self.bought(raw, ware, 1)
        status = self.carries(policy, after)["launcher.average_damage"]
        self.assertAlmostEqual(status["measured"], (27 + 95 * 18) / 96)
        self.assertFalse(status["ready"])

    def test_constructed_full_stack_is_bought_and_the_force_passes(self):
        raw = copy.deepcopy(CASE["board"])
        ware = next(item for item in raw["store"]["items"] if item["letter"] == BOLT_LETTER)
        ware["count"] = 99  # DECLARED CONSTRUCTED: 99 of the recorded (+5,+3) bolt.
        policy, key = self.visit(raw)
        self.assertEqual((key, policy.last_reason), ("pn99\r\r", "shop:in-store-buy"))
        game = self.post_buy(policy, raw, key)
        self.assertEqual("".join(game.accepted), key)

        after, slot = self.bought(raw, ware, 99)
        carries = self.carries(policy, after)
        self.assertEqual(carries["launcher.average_damage"],
                         {"measured": 27.0, "required": 25.0, "ready": True})
        self.assertTrue(carries["launcher"]["ready"])
        board = parse_snapshot(copy.deepcopy(after), self.monraces)
        fired = policy._quest_profile_ammo(board, policy.approved_quest_strategy(2))
        self.assertEqual((fired.slot, fired.to_d, fired.count), (slot, 3, 99))


if __name__ == "__main__":
    unittest.main()
