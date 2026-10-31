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
one Tower visit recharges the whole pack with the Tower's 'a' (BACT_RECHARGE_ALL,
market/building-recharger.cpp building_recharge_all), whose single input_check
the executor answers 'y' only once the question is observed, then ESC leaves.
The bot's gold check is the game's total over every rechargeable pack item
(this pack also holds three wand stacks and seven other staffs) plus the fare
home.  The absorption follows on the entrance grid, and the recorded stop
board itself steps off the entrance and walks back in.
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
# building_recharge_all on the recorded approach pack (slot: price):
#   wands  c (3*16-39)*50=450  d (2*17-30)*50=200  e (15-15)*50=0
#   staffs f (21-9)*40=480  g (19-13)*20=120  h (15-12)*20=60  i (16-11)*20=100
#          j (16-15)*20=20  k (16-12)*20=80  l (14-13)*35=35  m (12-9)*35=105
#          n (20-10)*10=100
APPROACH_TOTAL = 450 + 200 + 0 + 480 + 120 + 60 + 100 + 20 + 80 + 35 + 105 + 100
RECHARGE_ALL_KEYS = "ay\x1b"
STAGE1 = (sequence.SV_STAFF_IDENTIFY, DETECT)
EVIL = 15  # sv-staff-types.h SV_STAFF_DETECT_EVIL: slot l, a stage-2 staff


def tower_screen(prompt=""):
    """CONSTRUCTED: cmd-building.cpp's logical 80x24 building menu (the
    Tower's two actions, 03_Morivant.jsonc building 8) with ``prompt`` on
    the message row (input_check / msg_erase)."""
    lines = [""] * 24
    lines[0] = prompt
    lines[2] = " 賢者の塔"
    lines[19] = " r) 再充填"
    lines[20] = " a) 全てのアイテムを再充填"
    lines[23] = " ESC) 建物を出る"
    return {"width": 80, "height": 24, "lines": lines,
            "cursor": {"visible": True, "x": 0, "y": 0}}


def recharge_all_screens(total):
    """The building menu, the question, the result MORE, the menu again."""
    return [tower_screen(), tower_screen(f"すべてのアイテムを ＄{total} で再充填しますか？[y/n]"),
            tower_screen(f"＄{total} で再充填しました。 -続く-"), tower_screen()]


class MeTowerRechargeRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def policy(self, board):
        policy = ConservativePolicy()
        self.knowledge = policy._monrace_knowledge
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
        # DECLARED CONSTRUCTED: this process already read the game's staff
        # power list (me_staff_sequence.read_powers, #47).
        sequence.state(policy).powers_read = True
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

    def recharge_reply(self, raw):
        """DECLARED CONSTRUCTED from building_recharge_all (building-recharger.cpp).

        Every staff is filled to its base pval and every wand stack to
        number * base pval; the total is paid once with one message.  The
        recorded board (turn 649330) supplies the Tower entrance position.
        """
        following = copy.deepcopy(self.case["recharged"])
        following["turn"] = raw["turn"] + 10
        following["inventory"] = copy.deepcopy(raw["inventory"])
        total = sequence.recharge_cost(parse_snapshot(copy.deepcopy(raw), self.knowledge))
        definitions = sequence._device_definitions()
        for item in following["inventory"]:
            if item["tval"] not in (55, 65):
                continue
            full = definitions[(item["tval"], item["sval"])][0] * (
                item["count"] if item["tval"] == 65 else 1)
            item["name"] = item["name"].replace(f"({item['charges']}回分)", f"({full}回分)")
            item["charges"] = item["pval"] = full
        following["player"]["gold"] = raw["player"]["gold"] - total
        following["messages"] = [f"＄{total} で再充填しました。"]
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
        for sval in STAGE1:
            slot = self.staff(raw, sval)["slot"]
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), TOWER)
            key = self.decide(policy, raw)
            self.assertEqual((key, policy.last_reason), ("G" + slot, ABSORB_REASON))
            game = self.post(policy, raw, key, self.absorb_reply(raw, slot), [absorb])
            self.assertEqual(game.accepted, ["G", slot])
            raw = self.absorb_reply(raw, slot)
        # Both powers absorbed at full charge: stage 1 is complete (owner
        # 2026-10-31 「1本取り込めたら次の段階に進む」), decided once.
        key = self.decide(policy, raw)
        self.assertEqual(sequence.state(policy).absorbed,
                         {sequence.SV_STAFF_IDENTIFY: 21, DETECT: 19})
        # On the Tower's entrance grid the WAIT becomes the entrance step-off.
        self.assertEqual(policy.last_reason, "town:entrance-step-off:me-staff:stage1-complete")
        self.assertIn(key, DIRECTIONS)
        following = self.move_reply(raw, key)
        self.post(policy, raw, key, following)
        raw = following
        # Stage 2: the carried (recorded) Detect Evil staff is absorbed on
        # this Tower visit; the other three are bought at the Outpost next.
        slot = self.staff(raw, EVIL)["slot"]
        key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("G" + slot, ABSORB_REASON))
        self.post(policy, raw, key, self.absorb_reply(raw, slot), [absorb])
        raw = self.absorb_reply(raw, slot)
        self.decide(policy, raw)
        self.assertEqual(sequence.state(policy).absorbed[EVIL], 14)
        self.assertEqual(policy.last_reason, "me-staff:return-to-shop")

    def test_capture_pins_the_recorded_boards(self):
        approach, recharged = self.case["approach"], self.case["recharged"]
        self.assertEqual((approach["turn"], approach["player"]["y"], approach["player"]["x"]),
                         (649320, 19, 56))
        self.assertEqual((recharged["turn"], recharged["player"]["y"], recharged["player"]["x"]),
                         (649330, 20, 55))
        self.assertEqual(recharged["floor"]["town_id"], 2)
        self.assertEqual([(it["slot"], it["charges"]) for sval in (*STAGE1, EVIL)
                          for it in [self.staff(approach, sval)]], [("f", 9), ("g", 13), ("l", 13)])
        self.assertEqual([(it["slot"], it["charges"]) for sval in (*STAGE1, EVIL)
                          for it in [self.staff(recharged, sval)]], [("f", 21), ("g", 13), ("l", 13)])
        self.assertEqual((approach["player"]["gold"], recharged["player"]["gold"]), (14711, 14231))
        self.assertEqual(len(recharged["messages"]), 1)
        self.assertIn("＄480 で再充填しました。", recharged["messages"][0])

    def test_one_tower_visit_recharges_the_whole_pack_then_absorbs_both(self):
        raw = self.case["approach"]
        policy = self.policy(raw)
        self.assertEqual(sequence.recharge_cost(parse_snapshot(copy.deepcopy(raw), self.knowledge)),
                         APPROACH_TOTAL)
        self.assertEqual(APPROACH_TOTAL, 1750)
        key = self.decide(policy, raw)
        # Step onto the Tower, 'a' recharges all, 'y' at the question, ESC.
        self.assertEqual((key, policy.last_reason),
                         ("1" + RECHARGE_ALL_KEYS, "me-staff:recharge-all"))
        following = self.recharge_reply(raw)
        self.assertEqual(following["player"]["gold"], 14711 - APPROACH_TOTAL)
        self.assertEqual([(it["slot"], it["charges"]) for it in following["inventory"]
                          if it["tval"] in (55, 65)],
                         [("c", 48), ("d", 34), ("e", 15), ("f", 21), ("g", 19), ("h", 15),
                          ("i", 16), ("j", 16), ("k", 16), ("l", 14), ("m", 12), ("n", 20)])
        game = self.post(policy, raw, key, following, recharge_all_screens(APPROACH_TOTAL))
        # The executor releases each key only at its observed screen.
        self.assertEqual(game.accepted, ["1", "a", "y", " ", "\x1b"])
        self.absorb_both(policy, following)

    def test_short_gold_for_the_whole_pack_returns_for_funds(self):
        # Enough for both sequence staffs (480 + 120) and the fare, short of
        # the Tower's whole-pack total: no 'a' is posted.
        raw = copy.deepcopy(self.case["approach"])
        raw["player"]["gold"] = APPROACH_TOTAL + sequence.TOWN_TELEPORT_COST - 1
        policy = self.policy(raw)
        policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        self.assertEqual(policy.last_reason, "me-staff:return-for-funds")

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
        self.assertEqual(policy.last_reason, "me-staff:recharge-all")
        step = DIRECTIONS[key[0]]
        self.assertEqual((raw["player"]["y"] + step[0], raw["player"]["x"] + step[1]), TOWER)
        self.assertEqual(key[1:], RECHARGE_ALL_KEYS)
        following = self.recharge_reply(raw)
        # The Identify staff is already full: 1750 - 480.
        self.assertEqual(following["player"]["gold"], 14231 - (APPROACH_TOTAL - 480))
        following["player"]["y"], following["player"]["x"] = TOWER
        game = self.post(policy, raw, key, following, recharge_all_screens(APPROACH_TOTAL - 480))
        self.assertEqual(game.accepted, [key[0], "a", "y", " ", "\x1b"])
        self.absorb_both(policy, following)


if __name__ == "__main__":
    unittest.main()
