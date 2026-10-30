"""Owner 2026-10-30: what the zombie Magic-Eater eats.

「序盤はなんでも食べて良い。謎の魔法棒が属性攻撃に強く優秀なので、これを確保して
からは主食とする。減ったら塔でチャージする。」

The boards are the recorded n1-c life-033/036 Magic-shop boards of D25
(tests/fixtures/n1c-town-stops2-20261030.json.gz, extracted from the
captures n1c-1030-2100).  DECLARED CONSTRUCTED: the board is taken outside
the shop and made hungry, and where named a Wand of Wonder is added to the
recorded pack or the recorded shelf.  Keys go through the public chooser and
the production executor.
"""
import tests  # noqa: F401

import copy
import io
import time

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot import me_staff_sequence as sequence
from hengbot.magic_eater_devices import staple_food, staple_needs_recharge
from hengbot.model import parse_snapshot
from hengbot.policy_constants import MANA_FOOD_CHARGE_TARGET
from tests import test_me_tower_recharge_recorded as d24
from tests import test_n1c_town_stops2_recorded as d25
from tests.test_me_tower_recharge_recorded import DETECT, RECHARGE_ALL_KEYS, recharge_all_screens
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen


class ZombieMagicEaterFoodTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        d25.MagicEaterTownStops2RecordedTest.setUpClass()
        cls.recorded = d25.MagicEaterTownStops2RecordedTest

    def board(self, life, *, wonder=None, wonder_count=1, food_state="hungry"):
        policy, raw = self.recorded.boundary(self.recorded(), life)
        raw = copy.deepcopy(raw)
        raw["store"] = None
        raw["player"]["food"], raw["player"]["food_state"] = 1500, food_state
        if wonder is not None:
            wand = dict(next(it for it in raw["inventory"] if it["tval"] == 65))
            slots = {it["slot"] for it in raw["inventory"]}
            wand.update(slot=next(c for c in "abcdefghijklmnopqrstuvw" if c not in slots),
                        sval=24, charges=wonder, pval=wonder, count=wonder_count,
                        name=f"謎の魔法棒 ({wonder}回分)")
            raw["inventory"].append(wand)
        return policy, raw

    def eat(self, policy, raw):
        """Choose a key on ``raw`` and post it through the production executor."""
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(policy.last_reason, "survival:mana-absorb")
        self.assertTrue(key.startswith("E") and len(key) == 2, key)
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = command_screen(raw["turn"])
        following = copy.deepcopy(raw)
        following["turn"] += 10
        game.screens = [command_screen(following["turn"])]
        game.states = [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "zombie-me-food", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, [key])
        return next(it for it in raw["inventory"] if it["slot"] == key[1])

    def ledger(self, policy, raw):
        board = parse_snapshot(raw, policy._monrace_knowledge)
        return board, policy._supply_ledger(board, policy._planned_depth())["food"]

    def test_early_game_eats_any_device_but_the_sequence_staffs(self):
        # life-036 carries the sequence's Identify (e) and Detect Treasure (f)
        # staffs beside a Sleep Monster wand, a Detect Objects staff and a
        # Staff of Nothing; the recorded food count was 14 of 15.
        policy, raw = self.board("life-036")
        eaten = self.eat(policy, raw)
        self.assertNotIn((eaten["tval"], eaten["sval"]), {(55, 5), (55, 10)})
        board, food = self.ledger(policy, raw)
        self.assertEqual(food.count, MANA_FOOD_CHARGE_TARGET)
        self.assertEqual(policy._count_mana_food_uses(board), 13 + 12 + 15)

    def test_wonder_is_the_staple_eaten_and_alone_counted(self):
        policy, raw = self.board("life-036", wonder=10)
        eaten = self.eat(policy, raw)
        self.assertEqual((eaten["tval"], eaten["sval"]), (65, 24))
        board, food = self.ledger(policy, raw)
        self.assertEqual(food.count, 10)
        self.assertTrue(staple_needs_recharge(board))
        # A wand stack's pval is the stack's total (building-recharger.cpp
        # refills a stack to number * 24), so two wands of 10 are 10 charges.
        policy, raw = self.board("life-036", wonder=10, wonder_count=2)
        board, food = self.ledger(policy, raw)
        self.assertEqual(food.count, 10)
        self.assertTrue(staple_needs_recharge(board))
        policy, raw = self.board("life-036", wonder=MANA_FOOD_CHARGE_TARGET)
        board, food = self.ledger(policy, raw)
        self.assertEqual(food.count, MANA_FOOD_CHARGE_TARGET)
        self.assertFalse(staple_needs_recharge(board))

    def test_staple_is_never_surplus_and_other_devices_lose_the_food_hold(self):
        for charges in (0, 10, 24):
            with self.subTest(charges=charges):
                policy, raw = self.board("life-036", wonder=charges, food_state="normal")
                board = parse_snapshot(raw, policy._monrace_knowledge)
                wonder = next(it for it in board.inventory if (it.tval, it.sval) == (65, 24))
                self.assertEqual(policy._retention_reservation_baseline_detail(board, wonder),
                                 (1, "mana-food:staple"))
                self.assertEqual(policy._retention_surplus(board, wonder), 0)
                for device in board.inventory:
                    if device.is_wand_staff and device is not wonder:
                        self.assertNotEqual(
                            policy._retention_reservation_baseline_detail(board, device)[1],
                            "supply-ledger:mana-food")

    def test_magic_shop_buys_wonder_as_the_food_that_closes_the_count(self):
        # DECLARED CONSTRUCTED: life-033's pack without its food devices, and
        # the recorded empty Magic Missile wand's shelf letter selling a
        # Wand of Wonder instead.
        policy, raw = self.recorded.boundary(self.recorded(), "life-033")
        raw = copy.deepcopy(raw)
        raw["inventory"] = [it for it in raw["inventory"] if it["tval"] not in {55, 65}]
        ware = next(it for it in raw["store"]["items"] if (it["tval"], it["sval"]) == (65, 15))
        ware.update(sval=24, charges=16, pval=16, price=300, name="謎の魔法棒 (16回分)")
        board = parse_snapshot(raw, policy._monrace_knowledge)
        chosen = policy._mana_food_purchase(board)
        self.assertEqual((chosen.tval, chosen.sval), (65, 24))
        bought = copy.deepcopy(raw)
        bought["inventory"].append(dict({k: v for k, v in ware.items()
                                         if k not in {"letter", "price"}}, slot="w", count=1))
        _, food = self.ledger(policy, bought)
        self.assertEqual(food.count, MANA_FOOD_CHARGE_TARGET)


class WonderHoldLimitTest(executor_harness.ProductionHarness):
    """Owner 2026-10-30: 「謎の魔法棒は2本あれば十分なので無制限に買い足さないこと」.

    DECLARED CONSTRUCTED on the recorded life-036 Magic-shop visit: the pack
    keeps the sequence staffs but its other devices become a 5-charge Wand of
    Wonder stack of ``held``, and the recorded Sleep Monster wand row (and its
    page) sells two 4-charge Wands of Wonder at 300 gold (one buy cannot close
    the food count, so the quantity is the cap's).
    """
    shelf_screen = staticmethod(d25.lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = d25.MagicEaterTownStops2RecordedTest.post
    reply = d25.MagicEaterTownStops2RecordedTest.reply
    drive = d25.MagicEaterTownStops2RecordedTest.drive

    @classmethod
    def setUpClass(cls):
        d25.MagicEaterTownStops2RecordedTest.setUpClass()
        cls.cases = copy.deepcopy(d25.MagicEaterTownStops2RecordedTest.cases)
        for page in (cls.cases["life-036"]["board"]["store"], cls.cases["life-036"]["pages"]["5"]):
            ware = next(it for it in page["items"] if (it["tval"], it["sval"]) == (65, 8))
            ware.update(sval=24, charges=4, pval=4, price=300, count=2,
                        name="謎の魔法棒 (4回分)")

    def boundary(self, life, *, kit_bought=False, held=1, home=0):
        policy, raw = d25.MagicEaterTownStops2RecordedTest.boundary(self, life, kit_bought=kit_bought)
        wand = next(it for it in raw["inventory"] if it["tval"] == 65)
        raw["inventory"] = [it for it in raw["inventory"] if it["tval"] != 65
                            and not (it["tval"] == 55 and it["sval"] not in (5, 10))]
        raw["inventory"].append(dict(wand, slot="d", sval=24, charges=5, pval=5, count=held,
                                     name="謎の魔法棒 (5回分)"))
        if home:
            # DECLARED CONSTRUCTED: one more Wand of Wonder on the Home shelf.
            policy._home_knowledge_items = (parse_snapshot(raw, policy._monrace_knowledge).inventory[-1],)
        return policy, raw

    def wonders_bought(self, held, home=0):
        self.boundary = lambda life, kit_bought=False: WonderHoldLimitTest.boundary(
            self, life, kit_bought=kit_bought, held=held, home=home)
        _, _, reasons = self.drive("life-036", limit=60, done=lambda policy, raw, key: (
            bool(self.bought) or policy.last_reason.startswith(("me-staff:", "town:rumor"))
            or key.startswith(">")))
        return sum(quantity for name, quantity in self.bought if "謎" in name)

    def test_one_held_buys_only_one_more(self):
        self.assertEqual(self.wonders_bought(1), 1)

    def test_two_held_never_buys_a_third(self):
        for held, home in ((2, 0), (1, 1)):
            with self.subTest(held=held, home=home):
                self.assertEqual(self.wonders_bought(held, home), 0)


class StapleTowerRechargeTest(executor_harness.ProductionHarness):
    """「減ったら塔でチャージする」 on the recorded D24 Morivant approach board.

    DECLARED CONSTRUCTED: stage 1 is complete (both powers absorbed), no
    sequence staff is carried and a 5-charge Wand of Wonder is in the pack.
    Owner 2026-10-31: stage 2 follows, so the trip home is the inn teleport
    back to the Outpost's Magic shop (me-staff:return-to-shop).
    """
    policy = d24.MeTowerRechargeRecordedTest.policy
    decide = d24.MeTowerRechargeRecordedTest.decide
    post = d24.MeTowerRechargeRecordedTest.post
    recharge_reply = d24.MeTowerRechargeRecordedTest.recharge_reply

    @classmethod
    def setUpClass(cls):
        d24.MeTowerRechargeRecordedTest.setUpClass()
        cls.case = d24.MeTowerRechargeRecordedTest.case

    def board(self, wonder):
        raw = copy.deepcopy(self.case["approach"])
        raw["inventory"] = [it for it in raw["inventory"]
                            if not (it["tval"] == 55 and it["sval"] in sequence.SEQUENCE_SVALS)]
        wand = next(it for it in raw["inventory"] if it["tval"] == 65)
        self.slot = next(c for c in "abcdefghijklmnopqrstuvw"
                         if c not in {it["slot"] for it in raw["inventory"]})
        raw["inventory"].append(dict(wand, slot=self.slot, sval=24, charges=wonder, pval=wonder,
                                     count=1, name=f"謎の魔法棒 ({wonder}回分)"))
        policy = self.policy(raw)
        sequence.state(policy).absorbed = {sequence.SV_STAFF_IDENTIFY: 21, DETECT: 19}
        return policy, raw

    def test_low_staple_takes_the_tower_recharge_all_before_going_home(self):
        policy, raw = self.board(5)
        board = parse_snapshot(copy.deepcopy(raw), self.knowledge)
        self.assertTrue(staple_needs_recharge(board))
        total = sequence.recharge_cost(board)
        # building_recharge_all: the wand's (24 - 5) charges at max(10, 250 / 10).
        self.assertEqual(sequence._recharge_all_price(
            staple_food(board), sequence._device_definitions()), 19 * 25)
        key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("1" + RECHARGE_ALL_KEYS, "me-staff:recharge-all"))
        following = self.recharge_reply(raw)
        game = self.post(policy, raw, key, following, recharge_all_screens(total))
        self.assertEqual(game.accepted, ["1", "a", "y", " ", ""])
        self.assertEqual(next(it["charges"] for it in following["inventory"] if it["slot"] == self.slot), 24)
        self.decide(policy, following)
        self.assertEqual(policy.last_reason, "me-staff:return-to-shop")

    def test_full_staple_goes_home_without_the_tower(self):
        policy, raw = self.board(MANA_FOOD_CHARGE_TARGET)
        self.decide(policy, raw)
        self.assertEqual(policy.last_reason, "me-staff:return-to-shop")


if __name__ == "__main__":
    import unittest
    unittest.main()
