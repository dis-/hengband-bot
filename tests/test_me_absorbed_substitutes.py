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


if __name__ == "__main__":
    unittest.main()
