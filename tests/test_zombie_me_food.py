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
from hengbot.magic_eater_devices import staple_needs_recharge
from hengbot.model import parse_snapshot
from hengbot.policy_constants import MANA_FOOD_CHARGE_TARGET
from tests import test_n1c_town_stops2_recorded as d25
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen


class ZombieMagicEaterFoodTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        d25.MagicEaterTownStops2RecordedTest.setUpClass()
        cls.recorded = d25.MagicEaterTownStops2RecordedTest

    def board(self, life, *, wonder=None, food_state="hungry"):
        policy, raw = self.recorded.boundary(self.recorded(), life)
        raw = copy.deepcopy(raw)
        raw["store"] = None
        raw["player"]["food"], raw["player"]["food_state"] = 1500, food_state
        if wonder is not None:
            wand = dict(next(it for it in raw["inventory"] if it["tval"] == 65))
            slots = {it["slot"] for it in raw["inventory"]}
            wand.update(slot=next(c for c in "abcdefghijklmnopqrstuvw" if c not in slots),
                        sval=24, charges=wonder, pval=wonder, count=1,
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


if __name__ == "__main__":
    import unittest
    unittest.main()
