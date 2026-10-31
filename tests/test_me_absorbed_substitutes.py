"""Owner 2026-10-31 18h: absorbed Magic-Eater powers in place of carried items.

「魔道具術師、光の杖を取り込んでいる場合、クエスト要求の光の巻物を免除する。」
「鑑定の杖を21回取り込んだあとは鑑定の杖を購入しない。持ち物の要求からも外す。」
「岩石溶解の魔法棒を入手したあと、資金に余裕があるときにMAXまでチャージして取り込む。」
「岩石溶解を取り込んでいるとき、クエストの魔法棒要求の代替にできる。」

No recorded Magic-Eater has reached Q2, so the recorded boards are borrowed
and DECLARED CONSTRUCTED where each class says so:

* Town (rules 1, 4): the n1-a life-422 Q2 boards (tests/fixtures/
  quest-stops-20261030.json.gz, see test_q2_tower_recharge_recorded) with
  class 16, the staff sequence's record (powers read, every stage absorbed;
  ``stone-to-mud`` where named) and, for rule 1, the six Scrolls of Light
  taken out of the pack.
* Q2 floor (rules 1, 4): the recorded 2026-09-11 Q2 run (tests/fixtures/
  q2-blue-recovery-20260911.jsonl.gz) replayed through ``choose_key`` from
  its first row, every board with class 16, the Scrolls of Light (rule 1)
  or the Stone to Mud wand (rule 4) taken out of the pack and the absorbed
  power's list row (``_magic_eater_power_list``) added.  The recorded run
  read 'rh' (seq 125) and aimed 'ai2' (seq 179) there.
* Light purchase (rule 1): the recorded n1-c life-065 Outpost Alchemist page
  (tests/fixtures/me-light-waiver-life065-20261031.json.gz,
  tests/extract_me_life065_light.py) with the sequence record reconstructed.
* Identify (rule 2): the recorded n1-c life-016 board (tests/fixtures/
  me-mining-death-20261030.json.gz) with a displayed staff list.
* Stone to Mud absorption (rule 3): the recorded D24 Tower board (with the
  stage-2 staffs of test_me_stage2_staffs) with a Stone to Mud wand (3
  charges; the D24 pack's wand row with sval 6) added, and the recorded #47
  n1-c life-054 Outpost boards (test_me_staff_search_towns_recorded), whose
  pack carries a full Stone to Mud wand.

Replies to posted keys are constructed from the game's prompts
(cmd-magiceat.cpp) as in the borrowed harnesses; every posted key goes
through the production executor.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hengbot import me_absorbed_substitutes as substitutes
from hengbot import me_staff_sequence as sequence
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions
from hengbot.policy_constants import STORE_ALCHEMIST
from tests import test_input_executor as harness
from tests import test_me_mining_death_recorded as mining
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests import test_q2_tower_recharge_recorded as q2_town

TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
LIGHT_SCROLL = (70, 24)
STONE_TO_MUD = (65, 6)
Q2_RUN = Path(__file__).with_name("fixtures") / "q2-blue-recovery-20260911.jsonl.gz"


def _q2():
    """The borrowed recorded Q2 town harness (not a module-level TestCase)."""
    return q2_town.Q2TowerRechargeRecordedTest


def without(raw, kind):
    """``raw`` without the pack rows of (tval, sval), the letters closed up."""
    raw = copy.deepcopy(raw)
    raw["inventory"] = [it for it in raw["inventory"] if (it["tval"], it["sval"]) != kind]
    for index, item in enumerate(raw["inventory"]):
        item["slot"] = chr(ord("a") + index)
    return raw


def all_stages_absorbed(policy, **extras):
    """DECLARED CONSTRUCTED: the read power list holds every stage's staff."""
    record = sequence.state(policy)
    record.powers_read = True
    record.absorbed = {**{sval: sequence.max_charges(sval) for sval in sequence.SEQUENCE_SVALS},
                       **extras}


class TownBoards(harness.ProductionHarness):
    """The recorded life-422 Q2 boards as a class-16 board."""
    setUpClass = classmethod(_q2().setUpClass.__func__)
    policy = _q2().policy
    decide = _q2().decide
    post = _q2().post
    moved = staticmethod(_q2().moved)

    def me_board(self, name):
        raw = copy.deepcopy(self.q2[name])
        raw["player"]["class_id"] = 16
        return raw

    def carry(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        force = policy._strategy_force_for_snapshot(board, policy.approved_quest_strategy(2))
        return board, force, policy._quest_carry_status(board, force)


def q2_run_rows():
    with gzip.open(Q2_RUN, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class Q2FloorReplay(harness.ProductionHarness):
    """The recorded Q2 run replayed as a class-16 board up to one decision."""
    rows = q2_run_rows()

    def replay(self, convert, last_sequence):
        """(policy, converted raw, key) of the decision ``last_sequence``."""
        from test_town_stall import _consume_response, _fresh_incident_policy

        edit = find_monrace_definitions(Path(__file__), None)
        if edit is None:
            self.skipTest("Hengband edit data unavailable")
        with TemporaryDirectory(prefix="hengbot-me-subst-") as directory, patch.dict(
                os.environ, {"HENGBOT_HOME_HISTORY_DIR": directory,
                             "HENGBOT_TEST_GAME_EDIT_DIR": str(edit.parent)}):
            previous = Path.cwd()
            os.chdir(directory)
            try:
                policy = _fresh_incident_policy(Path(directory))
                for row in self.rows:
                    raw = convert(row["snapshot"])
                    key = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
                    if row["decision"]["decision_sequence"] == last_sequence:
                        return policy, raw, key
                    if key:
                        policy.confirm_key_posted(key)
                    for response in row.get("responses", ()):
                        _consume_response(policy, response)
            finally:
                os.chdir(previous)
        self.fail(f"no recorded decision {last_sequence}")

    def recorded(self, sequence_number):
        return next(row["decision"] for row in self.rows
                    if row["decision"]["decision_sequence"] == sequence_number)

    post = mining.MagicEaterMiningDeathRecordedTest.post


# --- rule 1 ---
LIFE065 = Path(__file__).with_name("fixtures") / "me-light-waiver-life065-20261031.json.gz"


class LightScrollWaiverTest(TownBoards):
    """「光の杖を取り込んでいる場合、クエスト要求の光の巻物を免除する。」 (19h:
    「Q2→取り込んだ光の杖で受諾」「光の巻物→購入を抑制」)"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with gzip.open(LIFE065, "rt", encoding="utf-8") as stream:
            cls.life065 = json.load(stream)["boards"]

    def test_absorbed_light_meets_the_q2_light_scrolls_without_buying(self):
        raw = without(self.me_board("outpost_board"), LIGHT_SCROLL)
        policy = self.policy(raw)
        all_stages_absorbed(policy, **{"stone-to-mud": 12})
        board, force, status = self.carry(policy, raw)
        # (a) Acceptance and entry: the six scrolls are waived.
        self.assertEqual(status["required_scrolls.light"],
                         {"measured": 6, "required": 6, "ready": True})
        # (c) The recorded Scroll of Light (slot h) is no quest carry: no
        # purchase, Home withdrawal or reservation claims it.
        scroll = next(it for it in parse_snapshot(copy.deepcopy(self.q2["outpost_board"]),
                                                  self.monraces).inventory
                      if (it.tval, it.sval) == LIGHT_SCROLL)
        self.assertIsNone(policy._quest_carry_target_for_item(board, scroll, force))
        key = self.decide(policy, raw)
        # Unfixed: shop:travel to the Alchemist (store 4) for the scrolls.
        self.assertNotEqual(policy._shopping_approach_store_type, STORE_ALCHEMIST,
                            (key, policy.last_reason))
        self.post(policy, raw, key, self.moved(raw, key))

    def test_life_065_alchemist_page_light_scrolls_are_not_a_quest_carry(self):
        # Recorded n1-c life-065 (Lv27, 光 19/19 absorbed, Q2 held on
        # required_scrolls.light 0/6): the observed Alchemist page sells
        # Scrolls of Light at 'o'.  DECLARED RECONSTRUCTED: the sequence
        # record (every stage absorbed; this capture keeps no record).
        raw = copy.deepcopy(self.life065["28"])
        policy = self.policy(raw)
        all_stages_absorbed(policy)
        board, force, status = self.carry(policy, raw)
        self.assertEqual(status["required_scrolls.light"]["ready"], True)
        light = next(it for it in board.store.items if (it.tval, it.sval) == LIGHT_SCROLL)
        self.assertEqual(light.letter, "o")
        # Unfixed: ("light", 0, 6) -- the quest:carry purchase rung buys it.
        self.assertIsNone(policy._quest_carry_target_for_item(board, light, force))
        self.assertFalse(policy._home_procurement_batch_member(
            board, light, policy._carry_procurement_strategy(board)))

    def test_other_classes_still_carry_the_scrolls(self):
        raw = without(copy.deepcopy(self.q2["outpost_board"]), LIGHT_SCROLL)
        policy = self.policy(raw)
        board, force, status = self.carry(policy, raw)
        self.assertFalse(status["required_scrolls.light"]["ready"])
        scroll = next(it for it in parse_snapshot(copy.deepcopy(self.q2["outpost_board"]),
                                                  self.monraces).inventory
                      if (it.tval, it.sval) == LIGHT_SCROLL)
        self.assertEqual(policy._quest_carry_target_for_item(board, scroll, force),
                         ("light", 0, 6))


def light_board(current, *, scrolls):
    """DECLARED CONSTRUCTED: class 16 with 光 current/19 in the displayed list."""
    def convert(raw):
        raw = copy.deepcopy(raw) if scrolls else without(raw, LIGHT_SCROLL)
        raw["player"]["class_id"] = 16
        raw["_magic_eater_power_list"] = {"kind": "staff", "rows": [
            {"name": "光", "current": current, "max": 19, "fail": 20, "success": 80}]}
        return raw
    return convert


class LightCastOnTheQ2FloorTest(Q2FloorReplay):
    """(b) 「クエスト内部で巻物要求のとき、代わりに杖で照らす」."""

    def test_light_after_opening_casts_the_absorbed_light(self):
        self.assertEqual((self.recorded(125)["reason"], self.recorded(125)["key"]),
                         ("quest-strategy:q2-light-after-opening", "rh"))
        for scrolls in (False, True):
            with self.subTest(scrolls=scrolls):
                # Carried scrolls or not, the power lights instead.
                policy, raw, key = self.replay(light_board(15, scrolls=scrolls), 125)
                self.assertEqual((key, policy.last_reason),
                                 ("mAi", "quest-strategy:q2-light-after-opening"
                                  + substitutes.CAST_SUFFIX))
                game, _ = self.post(policy, raw, key, [
                    prompt(TYPE_PROMPT), power_screen("staff", [("i", "光", 15, 19, 20)])])
                self.assertEqual(game.accepted, ["m", "A", "i"])

    def test_an_empty_power_reads_the_carried_scroll(self):
        policy, _, key = self.replay(light_board(0, scrolls=True), 125)
        self.assertEqual((key, policy.last_reason),
                         ("rh", "quest-strategy:q2-light-after-opening"))


# --- rule 2 ---
class IdentifyStaffReplacedTest(unittest.TestCase):
    """「鑑定の杖を21回取り込んだあとは鑑定の杖を購入しない。持ち物の要求からも外す。」"""
    raw = mining.MagicEaterMiningDeathRecordedTest.raw
    recorded_policy = mining.MagicEaterMiningDeathRecordedTest.policy
    choose = mining.MagicEaterMiningDeathRecordedTest.choose

    @classmethod
    def setUpClass(cls):
        mining.MagicEaterMiningDeathRecordedTest.setUpClass.__func__(cls)
        _q2().setUpClass()
        # The recorded Identify staff row of the D24 pack (slot f, 9 charges).
        cls.identify_staff = next(
            it for it in parse_snapshot(copy.deepcopy(_q2().me["approach"]), _q2().monraces).inventory
            if (it.tval, it.sval) == (55, sequence.SV_STAFF_IDENTIFY))

    def board(self, count):
        """DECLARED CONSTRUCTED: the staff list displayed with 鑑定 count/count."""
        raw = self.raw("life-016", 94171)
        raw["visible_monsters"] = []
        raw["_magic_eater_power_list"] = {"kind": "staff", "rows": [
            {"name": "鑑定", "current": count, "max": count, "fail": 10, "success": 90}]}
        return raw

    def test_a_full_staff_count_replaces_the_staff(self):
        for count, replaced in ((21, True), (20, False)):
            with self.subTest(count=count):
                raw = self.board(count)
                policy = self.recorded_policy("life-016", raw)
                self.choose(policy, raw)  # the decision observes the displayed list
                board = parse_snapshot(raw, policy._monrace_knowledge)
                # This new process's record is empty: only the list says so.
                self.assertFalse(sequence.absorbed(policy, sequence.SV_STAFF_IDENTIFY))
                self.assertEqual(substitutes.identify_staff_replaced(policy, board), replaced)
                self.assertEqual(
                    substitutes.purchase_excluded(policy, board, self.identify_staff), replaced)
                if replaced:
                    self.assertTrue(policy._identify_staff_ready(board))


# --- rule 3 ---
def add_stone_to_mud(raw, charges=3):
    """DECLARED CONSTRUCTED: a Stone to Mud wand (the D24 pack's wand row c
    with sval 6) in the pack, which the game keeps sorted."""
    wand = copy.deepcopy(next(it for it in _q2().me["approach"]["inventory"] if it["tval"] == 65))
    wand.update(sval=6, name=f"岩石溶解の魔法棒 ({charges}回分)", charges=charges, pval=charges,
                count=1)
    raw["inventory"].append(wand)
    raw["inventory"].sort(key=lambda it: (-it["tval"], it["sval"]))
    for index, item in enumerate(raw["inventory"]):
        item["slot"] = chr(ord("a") + index)
    return raw


class StoneToMudTowerTest(harness.ProductionHarness):
    """The Tower recharges the carried wand to its maximum and absorbs it."""
    from tests.test_me_stage2_staffs import Stage2TowerTest as _tower

    setUpClass = classmethod(_tower.setUpClass.__func__)
    board = _tower.board
    absorb_screen = _tower.absorb_screen
    policy = _tower.policy
    decide = _tower.decide
    post = _tower.post
    recharge_reply = _tower.recharge_reply
    absorb_reply = staticmethod(_tower.absorb_reply)
    move_reply = staticmethod(_tower.move_reply)

    def test_one_visit_recharges_and_absorbs_the_wand_after_the_stage(self):
        from tests.test_me_tower_recharge_recorded import (
            APPROACH_TOTAL, DIRECTIONS, recharge_all_screens,
        )
        from hengbot.magic_eater import ABSORB_REASON
        from hengbot.policy_constants import WAIT_KEY

        _q2().setUpClass()
        raw = add_stone_to_mud(self.board())
        policy = self.policy(raw)
        total = sequence.recharge_cost(parse_snapshot(copy.deepcopy(raw), self.knowledge))
        # Stage 2's staffs as test_me_stage2_staffs, plus the wand (12-3)*30.
        self.assertEqual(total, APPROACH_TOTAL + 175 + 210 + 225 + 25 + 270)
        steps = []
        for _ in range(20):
            key = self.decide(policy, raw)
            reason = policy.last_reason
            if reason == "me-staff:return-outpost":
                break
            if reason == "me-staff:recharge-all":
                following = self.recharge_reply(raw)
                self.post(policy, raw, key, following, recharge_all_screens(total))
                steps.append(reason)
            elif reason == ABSORB_REASON:
                item = next(it for it in raw["inventory"] if it["slot"] == key[1])
                following = self.absorb_reply(raw, key[1])
                game = self.post(policy, raw, key, following, [self.absorb_screen(raw)])
                self.assertEqual(game.accepted, ["G", key[1]])
                steps.append(("absorb", item["tval"], item["sval"], item["charges"]))
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
        self.assertEqual(steps[0], "me-staff:recharge-all")
        # 「MAXまでチャージして取り込む」: 12 charges (base pval), after the stage.
        self.assertEqual(steps[-2:], ["me-staff:stage2-complete", ("absorb", 65, 6, 12)])
        self.assertEqual(sequence.state(policy).absorbed["stone-to-mud"], 12)


class StoneToMudSpareGoldTest(unittest.TestCase):
    """The recorded life-054 pack carries a full Stone to Mud wand (slot h,
    12 charges, 60,981 gold): it starts a Tower trip only from spare gold."""
    from tests.test_me_staff_search_towns_recorded import StaffSearchTownsTest as _search

    decide_last = _search.decide_last

    def policy(self):
        policy = self._search.policy(self)
        # The recorded process had not absorbed the wand (test_me_nokey_1031
        # pins it as absorbed for its staff cases).
        del sequence.state(policy).absorbed["stone-to-mud"]
        return policy

    def last_board(self, gold=None):
        raw = self._search.last_board(self, gold)
        wand = next(it for it in raw["inventory"] if (it["tval"], it["sval"]) == STONE_TO_MUD)
        self.assertEqual((wand["slot"], wand["charges"]), ("h", 12))
        return raw

    def test_spare_gold_takes_the_wand_to_the_tower(self):
        policy = self.policy()
        raw = self.last_board()
        key, destination = self.decide_last(policy, raw)
        # Unfixed: me-staff:search-staff (the stocked-out Detect Evil) only.
        self.assertEqual((policy.last_reason, destination), ("me-staff:travel-morivant", 2), key)

    def test_without_spare_gold_the_stage_keeps_its_search(self):
        policy = self.policy()
        raw = self.last_board()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        supplies = sequence.supply_cost(policy, board)
        needs = sequence._stockout_target(policy, board, supplies, True)
        raw = self.last_board(needs + sequence._expedition_cost(board, 0) - 1)
        key, destination = self.decide_last(policy, raw)
        self.assertTrue(policy.last_reason.startswith("me-staff:search-staff"),
                        (key, policy.last_reason))


# --- rule 4 ---
class StoneToMudBreachTownTest(TownBoards):
    """「岩石溶解を取り込んでいるとき、クエストの魔法棒要求の代替にできる。」"""

    def test_absorbed_charges_meet_the_q2_wall_breach(self):
        raw = self.me_board("outpost_board")
        policy = self.policy(raw)
        all_stages_absorbed(policy, **{"stone-to-mud": 12})
        _, _, status = self.carry(policy, raw)
        # The recorded wand's one charge and the absorbed 12: 13 // 5 walls.
        self.assertEqual(status["utility_tools.wall_breach"],
                         {"measured": 2, "required": 1, "ready": True})
        key = self.decide(policy, raw)
        # Unfixed: the wall_breach carry is short and the Q2 travel waits.
        self.assertEqual(policy.last_reason.removesuffix("-step-off"), "fixedquest:q2-travel")
        self.post(policy, raw, key, self.moved(raw, key))


class StoneToMudBreachOnTheQ2FloorTest(Q2FloorReplay):
    """Where Q2 aims the wand at the breach wall, the absorbed power is aimed."""

    @staticmethod
    def convert(raw):
        raw = without(raw, STONE_TO_MUD)
        raw["player"]["class_id"] = 16
        raw["_magic_eater_power_list"] = {"kind": "wand", "rows": [
            {"name": "岩石溶解", "current": 12, "max": 12, "fail": 20, "success": 80}]}
        return raw

    def test_breach_aims_the_absorbed_stone_to_mud(self):
        self.assertEqual((self.recorded(179)["reason"], self.recorded(179)["key"]),
                         ("quest-strategy:q2-breach-wand", "ai2"))
        policy, raw, key = self.replay(self.convert, 179)
        self.assertEqual((key, policy.last_reason),
                         ("mBg2", "quest-strategy:q2-breach-wand" + substitutes.CAST_SUFFIX))
        game, _ = self.post(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("wand", [("g", "岩石溶解", 12, 12, 20)]),
            prompt("方向 ('*'でターゲット選択, ESCで中断)? ", "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["m", "B", "g", "2"])


if __name__ == "__main__":
    unittest.main()
