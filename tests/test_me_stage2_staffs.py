"""Owner 2026-10-31: the Magic-Eater staff sequence's stage 2.

「財宝感知と鑑定の取り込みは1本でいい。1本取り込めたら次の段階に進む。次の段階は
店売りの有用な魔法道具を揃えること。トラップ感知の杖　ドア/階段感知の杖　邪悪感知の杖
周辺感知の杖　まずはこれらを1本ずつ取り込むのが目標。取り込み手順は以前と同じ。」
「次の目標は3キャラ連続で第二段階のクリアとする」「魔道具術師の第二段階に光の杖を追加」

Stage 2's staffs are Trap Location (sval 12), Door/Stair Location (13),
Detect Evil (15), Enlightenment (9) and Light (8),
sv-definition/sv-staff-types.h; all five are Magic-shop stock
(store/articles-on-sale.cpp).

The shop boards are the recorded n1-c life-033/036 Outpost Magic-shop
boards of D25 (tests/fixtures/n1c-town-stops2-20261030.json.gz), whose
shelves sell stage-2 staffs.  The Tower board is the recorded n1-c life-036
Morivant approach of D24 (tests/fixtures/me-tower-recharge-20261030.json.gz),
whose pack already carries a Detect Evil staff.  DECLARED CONSTRUCTED where
named in each test: stage 1 absorbed (its staffs gone from the pack),
Morivant listed as visited, gold, and stage-2 staffs added to a pack (rows
copied from the recorded D25 shelves).  The replies to posted keys are
constructed as in the borrowed D24/D25 harnesses.  Every decision goes
through the public ``choose_key`` and the production executor.
"""
import tests  # noqa: F401

import copy

from hengbot import me_staff_sequence as sequence
from hengbot.magic_eater import ABSORB_REASON
from hengbot.model import parse_snapshot
from hengbot.policy_constants import WAIT_KEY
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_tower_recharge_recorded as d24
from tests import test_n1c_town_stops2_recorded as d25
from tests.test_magic_eater_o3 import prompt
from tests.test_me_tower_recharge_recorded import (
    ABSORB_PROMPT, APPROACH_TOTAL, DIRECTIONS, RECHARGE_ALL_KEYS, recharge_all_screens,
)
import tests.test_input_executor as executor_harness


IDENTIFY, DETECT = 5, 10
LIGHT, MAPPING, TRAP, DOOR, EVIL = 8, 9, 12, 13, 15
STAGE2 = (TRAP, DOOR, EVIL, MAPPING, LIGHT)


def stage1_done(policy, charges=(1, 1)):
    """DECLARED CONSTRUCTED: both stage-1 powers absorbed (any charges)."""
    record = sequence.state(policy)
    record.absorbed = {IDENTIFY: charges[0], DETECT: charges[1]}
    record.fundraise_target, record.fundraise_runs = None, 0
    record.bought = frozenset()
    policy._supply_stockout_gold_target = None


def staffs_bought(bought):
    return [name for name, _ in bought if "杖" in name]


class Stage2ShopTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = d25.MagicEaterTownStops2RecordedTest.post
    reply = d25.MagicEaterTownStops2RecordedTest.reply
    drive = d25.MagicEaterTownStops2RecordedTest.drive

    @classmethod
    def setUpClass(cls):
        d25.MagicEaterTownStops2RecordedTest.setUpClass()
        cls.cases = d25.MagicEaterTownStops2RecordedTest.cases

    def boundary(self, life, *, kit_bought=False):
        policy, raw = d25.MagicEaterTownStops2RecordedTest.boundary(self, life, kit_bought=kit_bought)
        stage1_done(policy)
        raw = copy.deepcopy(raw)
        # DECLARED CONSTRUCTED: Morivant unlocked by stage 1's rumors; the
        # stage-1 staffs absorbed; ``self.setup`` the test's own changes.
        raw.setdefault("progress", {})["visited_town_ids"] = [0, 2]
        raw["inventory"] = [it for it in raw["inventory"]
                            if not (it["tval"] == 55 and it["sval"] in (IDENTIFY, DETECT))]
        for index, item in enumerate(raw["inventory"]):
            item["slot"] = chr(ord("a") + index)
        self.setup(raw)
        return policy, raw

    def setup(self, raw):
        pass

    @staticmethod
    def owned(policy, raw, key):
        return "me-staff:fundraise:" in policy.last_reason

    def test_stage1_complete_gives_the_stage2_shelf_target(self):
        # Recorded life-033 page, gold 1180: Enlightenment 1483, Door/Stair
        # 661, Detect Evil 726 and Light 534 are on offer (no Trap Location).
        # Stage 1 was absorbed with one charge each: 「1本取り込めたら次の段階に進む」.
        policy, raw, reasons = self.drive("life-033", limit=30, done=self.owned)
        self.assertEqual(staffs_bought(self.bought), [])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        supplies = sequence.supply_cost(policy, board)
        self.assertTrue(policy.last_reason.endswith(
            f"me-staff:fundraise:staffs:{1483 + 661 + 726 + 534 + supplies}"), reasons[-6:])
        record = sequence.state(policy)
        self.assertEqual((record.stage, record.remaining), (2, STAGE2))

    def test_shop_page_buys_each_offered_stage2_staff_once(self):
        # Recorded life-036 page: two Enlightenment rows (i: 2 at 1608, j:
        # 1553) and Trap Location (l, 735).  DECLARED CONSTRUCTED: 10000 gold,
        # a carried Detect Evil staff (the life-033 shelf row q), and the
        # recorded Detect Objects staff removed (its sale is not this test's).
        def setup(raw):
            raw["player"]["gold"] = 10000
            raw["inventory"] = [it for it in raw["inventory"]
                                if not (it["tval"] == 55 and it["sval"] == 11)]
            for index, item in enumerate(raw["inventory"]):
                item["slot"] = chr(ord("a") + index)
            evil = next(it for it in self.cases["life-033"]["board"]["store"]["items"]
                        if it["tval"] == 55 and it["sval"] == EVIL)
            staff = {k: v for k, v in copy.deepcopy(evil).items() if k not in ("letter", "price")}
            raw["inventory"].append(dict(staff, slot=chr(ord("a") + len(raw["inventory"]))))
        self.setup = setup
        policy, raw, reasons = self.drive("life-036", limit=60, done=lambda policy, raw, key: (
            self.owned(policy, raw, key) or policy.last_reason == "me-staff:travel-morivant"))
        # One of each in the stage's order; the second Enlightenment row (i)
        # stays on the shelf.
        self.assertEqual(staffs_bought(self.bought),
                         ["トラップ感知の杖 (7回分)", "周辺感知の杖 (6回分)"], reasons)
        self.assertEqual([quantity for name, quantity in self.bought if "杖" in name], [1, 1])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(sorted(sequence.carried_staffs(policy, board)), [MAPPING, TRAP, EVIL])
        # Door/Stair and Light are still missing and off the shelf: the
        # carried three go to the Tower first (owner 2026-10-31 「持っている分を
        # 先に取り込む」); the missing two are bought when they are stocked.
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant", reasons[-6:])
        self.assertEqual(sequence._phase(policy, board), "travel")


class Stage2TowerTest(executor_harness.ProductionHarness):
    """One Tower visit: recharge-all, both stages' absorptions, completion."""
    policy = d24.MeTowerRechargeRecordedTest.policy
    decide = d24.MeTowerRechargeRecordedTest.decide
    post = d24.MeTowerRechargeRecordedTest.post
    recharge_reply = d24.MeTowerRechargeRecordedTest.recharge_reply
    absorb_reply = staticmethod(d24.MeTowerRechargeRecordedTest.absorb_reply)
    move_reply = staticmethod(d24.MeTowerRechargeRecordedTest.move_reply)

    @classmethod
    def setUpClass(cls):
        d24.MeTowerRechargeRecordedTest.setUpClass()
        d25.MagicEaterTownStops2RecordedTest.setUpClass()
        cls.case = d24.MeTowerRechargeRecordedTest.case

    def board(self):
        """DECLARED CONSTRUCTED: the D25 shelf rows Trap Location (life-036
        l, 7 charges), Door/Stair (life-033 p, 9), Enlightenment (life-033
        o, 8) and Light (life-033 n, 18) added to the recorded approach
        pack, which the game keeps sorted (tval descending, sval ascending)."""
        raw = copy.deepcopy(self.case["approach"])
        shelves = {life: d25.MagicEaterTownStops2RecordedTest.cases[life]["board"]["store"]["items"]
                   for life in ("life-033", "life-036")}
        for life, letter in (("life-036", "l"), ("life-033", "p"), ("life-033", "o"),
                             ("life-033", "n")):
            row = copy.deepcopy(next(it for it in shelves[life] if it["letter"] == letter))
            raw["inventory"].append({k: v for k, v in row.items() if k not in ("letter", "price")})
        raw["inventory"].sort(key=lambda it: (-it["tval"], it["sval"]))
        for index, item in enumerate(raw["inventory"]):
            item["slot"] = chr(ord("a") + index)
        return raw

    def absorb_screen(self, raw):
        return prompt(ABSORB_PROMPT, "item", area="inventory", areas=["inventory", "floor"],
                      menu=False, first_label="a",
                      last_label=chr(ord("a") + len(raw["inventory"]) - 1))

    def test_one_visit_recharges_and_absorbs_every_carried_stage2_staff(self):
        raw = self.board()
        policy = self.policy(raw)
        board = parse_snapshot(copy.deepcopy(raw), self.knowledge)
        # building_recharge_all: the recorded 1750 plus Trap (12-7)*35,
        # Door/Stair (15-9)*35, Enlightenment (11-8)*75 and Light (19-18)*25.
        total = sequence.recharge_cost(board)
        self.assertEqual(total, APPROACH_TOTAL + 175 + 210 + 225 + 25)
        steps = []
        for _ in range(16):
            key = self.decide(policy, raw)
            reason = policy.last_reason
            if reason == "me-staff:return-outpost":
                break
            if reason == "me-staff:recharge-all":
                self.assertEqual(key[1:], RECHARGE_ALL_KEYS)
                following = self.recharge_reply(raw)
                game = self.post(policy, raw, key, following, recharge_all_screens(total))
                self.assertEqual(game.accepted, [key[0], "a", "y", " ", "\x1b"])
                steps.append(reason)
            elif reason == ABSORB_REASON:
                slot = key[1]
                sval = next(it["sval"] for it in raw["inventory"] if it["slot"] == slot)
                following = self.absorb_reply(raw, slot)
                game = self.post(policy, raw, key, following, [self.absorb_screen(raw)])
                self.assertEqual(game.accepted, ["G", slot])
                steps.append(("absorb", sval))
            elif key in DIRECTIONS or key == WAIT_KEY:
                following = (self.move_reply(raw, key) if key in DIRECTIONS
                             else dict(copy.deepcopy(raw), turn=raw["turn"] + 10))
                self.post(policy, raw, key, following)
                steps.append(reason)
            else:
                self.fail((key, reason, steps))
            raw = following
        else:
            self.fail(("no return", steps))
        self.assertEqual(steps, [
            "me-staff:recharge-all", ("absorb", IDENTIFY), ("absorb", DETECT),
            # The WAIT on the Tower's entrance grid steps off it instead.
            "town:entrance-step-off:me-staff:stage1-complete",
            ("absorb", LIGHT), ("absorb", MAPPING), ("absorb", TRAP), ("absorb", DOOR),
            ("absorb", EVIL), "me-staff:stage2-complete"])
        record = sequence.state(policy)
        self.assertEqual(record.absorbed, {IDENTIFY: 21, DETECT: 19, LIGHT: 19, MAPPING: 11,
                                           TRAP: 12, DOOR: 15, EVIL: 14})
        self.assertEqual(sorted(record.completed_stages), [1, 2])
        self.assertEqual((record.stage, record.remaining), (3, ()))
        self.assertTrue(sequence.complete(policy))


if __name__ == "__main__":
    import unittest
    unittest.main()
