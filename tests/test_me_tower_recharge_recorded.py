"""D24: the recorded n1-c life-036 Tower of Sorcery stop (2026-10-30 21:03).

The Magic-Eater (Lv8, gold 14711) carried both sequence staffs to Morivant,
walked to the Tower of Sorcery (building 8) and posted ``1rf12\\r\\x1b``
(me-staff:recharge:5): the game answered 「鑑定の杖 (21回分)を＄480 で再充填
しました。」.  The recharge left the Tower after one staff, so the player stood
on the entrance grid with 財宝感知の杖 (13回分, max 19) still short; no step
there enters the building, the next decision stopped on
quest:blocked:me-staff (tower-of-sorcery-route-unavailable) and the
character retired after no-key-exhausted x3.

Pinned through the public ``choose_key`` and the production executor port:
one Tower visit recharges both staffs (cmd-building.cpp keeps the menu open
after each 'r' until ESC), the absorption follows on the entrance grid, and
the recorded stop board itself steps off the entrance and walks back in.
Fixture: tests/extract_me_tower_recharge_fixture.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
import time
import unittest
from pathlib import Path

from hengbot import me_staff_sequence as sequence
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.magic_eater import ABSORB_REASON
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import ConservativePolicy
from tests import test_input_executor as executor_pins
from tests.test_magic_eater_o3 import prompt


FIXTURE = Path(__file__).with_name("fixtures") / "me-tower-recharge-20261030.json.gz"
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
TOWER = (20, 55)
DETECT = sequence.SV_STAFF_DETECT_GOLD
ABSORB_PROMPT = "どのアイテムの魔力を取り込みますか? "


class MeTowerRechargeRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def policy(self, board):
        policy = ConservativePolicy()
        for key, facts in self.case["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            policy._monrace_knowledge[int(key)] = MonraceKnowledge(**facts)
        policy.prime(parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge))
        policy.consume_skill_knowledge(self.case["skill_knowledge"])
        policy.consume_home_knowledge(
            _parse_items(self.case["home_knowledge"]["knowledge"]["items"], protocol=3))
        return policy

    def decide(self, policy, raw):
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        self.assertNotEqual(key, "", (policy.last_reason, sequence.state(policy).failure))
        return key

    def post(self, policy, raw, key, following, screens=()):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [*screens, executor_pins.command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in screens] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "me-tower-recharge", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertFalse(game.term_fifo)
        policy.confirm_key_posted(key)
        return game

    @staticmethod
    def staff(raw, sval):
        return next(it for it in raw["inventory"] if it["tval"] == 55 and it["sval"] == sval)

    def recharge_reply(self, raw, svals):
        """DECLARED CONSTRUCTED from the recorded reply (turn 649330).

        The recorded board is the game's answer to the Identify half: the
        player on the Tower entrance, the staff at 21 charges, 480 gold paid
        and the message.  Each further staff is recharged the same way
        (building-recharger.cpp: pval += charges, au -= price).
        """
        following = copy.deepcopy(self.case["recharged"])
        following["turn"] = raw["turn"] + 10
        following["player"]["gold"] = raw["player"]["gold"]
        following["messages"] = []
        for sval in sequence.SEQUENCE_SVALS:
            item, before = self.staff(following, sval), self.staff(raw, sval)
            item.update(charges=before["charges"], pval=before["pval"], name=before["name"])
        for sval in svals:
            item = self.staff(following, sval)
            price = ((sequence.max_charges(sval) - item["charges"])
                     * sequence.recharge_price_per_charge(
                         parse_snapshot(following, {}).inventory[ord(item["slot"]) - ord("a")]))
            item["name"] = item["name"].replace(f"({item['charges']}回分)",
                                                f"({sequence.max_charges(sval)}回分)")
            item["charges"] = item["pval"] = sequence.max_charges(sval)
            following["player"]["gold"] -= price
            following["messages"].append(f"{item['name']}を＄{price} で再充填しました。")
        return following

    @staticmethod
    def absorb_reply(raw, slot):
        """DECLARED CONSTRUCTED: vary_item(-999) removes the staff and the
        pack closes up (inventory letters shift down by one)."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        name = next(it["name"] for it in raw["inventory"] if it["slot"] == slot)
        following["inventory"] = [it for it in following["inventory"] if it["slot"] != slot]
        for index, item in enumerate(following["inventory"]):
            item["slot"] = chr(ord("a") + index)
        following["messages"] = [f"{name}の魔力を取り込んだ。"]
        return following

    @staticmethod
    def move_reply(raw, key):
        """DECLARED CONSTRUCTED: the walk of one direction key."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        dy, dx = DIRECTIONS[key]
        following["player"]["y"] += dy
        following["player"]["x"] += dx
        return following

    def absorb_both(self, policy, raw):
        absorb = prompt(ABSORB_PROMPT, "item", area="inventory", areas=["inventory", "floor"],
                        menu=False, first_label="a", last_label="s")
        for sval in sequence.SEQUENCE_SVALS:
            slot = self.staff(raw, sval)["slot"]
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), TOWER)
            key = self.decide(policy, raw)
            self.assertEqual((key, policy.last_reason), ("G" + slot, ABSORB_REASON))
            game = self.post(policy, raw, key, self.absorb_reply(raw, slot), [absorb])
            self.assertEqual(game.accepted, ["G", slot])
            raw = self.absorb_reply(raw, slot)
        # Both powers absorbed at full charge; the inn teleport home follows.
        key = self.decide(policy, raw)
        self.assertEqual(sequence.state(policy).absorbed,
                         {sequence.SV_STAFF_IDENTIFY: 21, DETECT: 19})
        self.assertTrue(sequence.complete(policy))
        self.assertEqual(policy.last_reason, "me-staff:return-outpost")

    def test_capture_pins_the_recorded_boards(self):
        approach, recharged = self.case["approach"], self.case["recharged"]
        self.assertEqual((approach["turn"], approach["player"]["y"], approach["player"]["x"]),
                         (649320, 19, 56))
        self.assertEqual((recharged["turn"], recharged["player"]["y"], recharged["player"]["x"]),
                         (649330, 20, 55))
        self.assertEqual(recharged["floor"]["town_id"], 2)
        self.assertEqual([(it["slot"], it["charges"]) for sval in sequence.SEQUENCE_SVALS
                          for it in [self.staff(approach, sval)]], [("f", 9), ("g", 13)])
        self.assertEqual([(it["slot"], it["charges"]) for sval in sequence.SEQUENCE_SVALS
                          for it in [self.staff(recharged, sval)]], [("f", 21), ("g", 13)])
        self.assertEqual((approach["player"]["gold"], recharged["player"]["gold"]), (14711, 14231))
        self.assertEqual(len(recharged["messages"]), 1)
        self.assertIn("＄480 で再充填しました。", recharged["messages"][0])

    def test_one_tower_visit_recharges_both_staffs_then_absorbs_both(self):
        raw = self.case["approach"]
        policy = self.policy(raw)
        key = self.decide(policy, raw)
        # 'r' + item + charge count for each staff, then ESC leaves the Tower.
        self.assertEqual((key, policy.last_reason),
                         ("1rf12\rrg6\r\x1b", "me-staff:recharge:5,10"))
        following = self.recharge_reply(raw, sequence.SEQUENCE_SVALS)
        self.assertEqual(following["player"]["gold"], 14711 - 480 - 6 * 20)
        game = self.post(policy, raw, key, following)
        self.assertEqual(game.accepted, [key])
        self.absorb_both(policy, following)

    def test_recorded_stop_board_reenters_the_tower_from_its_entrance(self):
        # The recorded stop: on the entrance grid with Treasure Location short.
        raw = self.case["recharged"]
        policy = self.policy(raw)
        key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, "me-staff:approach-tower")
        self.assertIn(key, DIRECTIONS)
        following = self.move_reply(raw, key)
        self.assertNotEqual((following["player"]["y"], following["player"]["x"]), TOWER)
        self.post(policy, raw, key, following)
        raw = following
        key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, "me-staff:recharge:10")
        step = DIRECTIONS[key[0]]
        self.assertEqual((raw["player"]["y"] + step[0], raw["player"]["x"] + step[1]), TOWER)
        self.assertEqual(key[1:], "rg6\r\x1b")
        following = self.recharge_reply(raw, (DETECT,))
        following["player"]["y"], following["player"]["x"] = TOWER
        self.post(policy, raw, key, following)
        self.absorb_both(policy, following)


if __name__ == "__main__":
    unittest.main()
