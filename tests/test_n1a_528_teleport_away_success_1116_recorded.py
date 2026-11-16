"""n1-a life-528 (2026-11-16): the Teleport Other kept and zapped by its actual success, recorded.

The chain (warrior Lv41, device skill 33, build bot-0f3b00a68):

 * 12:54:07, in the Home (town arrival, journal row 5): the pack held 2 Rods of Teleport Other, the
   shelf 7 Wands of Teleport Other (77 charges).  The carry rule (teleport_away_carry, owner
   2026-11-14 「ロッドがあればロッド」) kept the rod and took no wand.
 * Quest 25 phase 2, 13:13:13 (the last process's decisions 44, 46, 48; HP 282, 194, 74): below the
   plan's HP line with no Healing potion left, ``_below_line`` aimed the rod at the ghost
   tyrannosaurus ('zl2' ``quest-strategy:teleport-away``); 「うまくロッドを使えなかった。」 three
   times, then death.

Game (C:/hengband/src): zaprod-execution.cpp:66-94 at skill 33 and the rod's level 45
(BaseitemDefinitions id 364): fail 50, chance 33 - 34 floored to USE_DEVICE 3, success 3/100.
zapwand-execution.cpp:63-78 at the wand's level 20 (id 285): chance 13, fails on randint1(13) < 3,
success 11/13 (84.6%).

The rules (owner 2026-11-16, verbatim 「実際の成功率が高い方」 and 「成功率50%未満は使える手に数え
ない」): the one device carried is the one with the higher actual success (a rod on a tie); a device
below 50% is no Teleport Other means (teleport_follower ``_carried`` / ``_absorbed``, read by
quest_plan_base.hall_away_key, ``away_key``, ``away_usable``).

Recorded: tests/fixtures/n1a-528-q25-death-1116.json.gz
(tests/extract_n1a_528_q25_death_1116_fixture.py, copies of the captures in
C:/hengband-backups/pdca/captures/n1a-528-q25-death-1116).  DECLARED: the Home board is parsed with
its town monsters dropped (the carry rule reads no monster); the record and the skill knowledge are
as tests/test_n1a_528_q25_rally_rest_1116_recorded declares them.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest_plan_base, teleport_away_carry, teleport_follower
from hengbot.model import TVAL_ROD, TVAL_WAND, parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1a-528-q25-death-1116.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

FIRST_ZAP = 44   # the last process's decision: HP 282, 'zl2'


def home_snapshot():
    raw = copy.deepcopy(CASE["home_board"])
    raw["visible_monsters"], raw["detected_monsters"] = [], []   # DECLARED (module note)
    return parse_snapshot(raw)


def away(items, tval):
    return next(item for item in items if teleport_away_carry.is_device(item) and item.tval == tval)


class TheRecordingTest(unittest.TestCase):

    def test_rod_carried_wands_shelved_and_three_failed_zaps(self):
        snapshot = home_snapshot()
        self.assertEqual(snapshot.player.device_skill, 33)
        self.assertEqual(away(snapshot.inventory, TVAL_ROD).count, 2)
        self.assertEqual((away(snapshot.store.items, TVAL_WAND).count,
                          away(snapshot.store.items, TVAL_WAND).charges), (7, 77))
        rows = {row["sequence"]: row for row in CASE["second"]["recorded"]}
        boards = {row["sequence"]: board
                  for row, board in zip(CASE["second"]["recorded"], CASE["second"]["boards"])}
        for sequence in (44, 46, 48):
            self.assertEqual((rows[sequence]["key"], rows[sequence]["reason"]),
                             ("zl2", quest_plan_base.AWAY_REASON))
            self.assertIn("うまくロッドを使えなかった。", boards[sequence + 1]["messages"])


class SuccessTest(unittest.TestCase):

    def test_the_game_chances(self):
        snapshot = home_snapshot()
        self.assertAlmostEqual(teleport_away_carry.success(
            snapshot.player, away(snapshot.inventory, TVAL_ROD)), 3.0)
        self.assertAlmostEqual(teleport_away_carry.success(
            snapshot.player, away(snapshot.store.items, TVAL_WAND)), 1100 / 13)


class CarryTest(unittest.TestCase):

    def test_the_home_wand_is_taken_for_the_rod(self):
        snapshot = home_snapshot()
        policy = SimpleNamespace(_home_knowledge_items=snapshot.store.items)
        wand = away(snapshot.store.items, TVAL_WAND)
        self.assertEqual(teleport_away_carry.home_missing(policy, snapshot, wand), 1)

    def test_carrying_both_the_wand_is_kept_and_the_rod_not(self):
        # DECLARED CONSTRUCTED: the pack after the take (the shelf's wand stack added).
        snapshot = home_snapshot()
        wand = away(snapshot.store.items, TVAL_WAND)
        pack = snapshot.__class__(**{**snapshot.__dict__, "inventory": (*snapshot.inventory, wand)})
        self.assertIs(teleport_away_carry.carried_device(pack), wand)
        rod = away(pack.inventory, TVAL_ROD)
        self.assertEqual(teleport_away_carry.retained_count(pack, rod), 0)


class ZapTest(unittest.TestCase):

    def _decide(self, edit=None):
        boards, recorded = CASE["second"]["boards"], CASE["second"]["recorded"]
        index = next(i for i, row in enumerate(recorded) if row["sequence"] == FIRST_ZAP)
        raw = copy.deepcopy(boards[index])
        if edit is not None:
            edit(raw)
        with TemporaryDirectory() as directory:
            policy = replay.new_policy(Path(directory), {}, None, CASE)
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = policy.choose_key(snapshot)
            return snapshot, key, policy.last_reason

    def test_the_3_percent_rod_is_no_means(self):
        snapshot, key, reason = self._decide()
        self.assertEqual(snapshot.player.hp, 282)
        self.assertIsNone(teleport_follower._carried(snapshot))
        self.assertNotEqual(reason, quest_plan_base.AWAY_REASON)
        self.assertFalse(key.startswith("z"), (key, reason))

    def test_control_a_wand_in_its_place_is_aimed(self):
        # DECLARED CONSTRUCTED control: the rod's slot holds the shelf's Wand of Teleport Other.
        wand_row = next(row for row in CASE["home_board"]["store"]["items"]
                        if row["tval"] == TVAL_WAND and "テレポート・アウェイ" in row["name"])

        def swap(raw):
            for slot, row in enumerate(raw["inventory"]):
                if row["tval"] == TVAL_ROD and "テレポート・アウェイ" in row["name"]:
                    made = {key: value for key, value in wand_row.items() if key != "letter"}
                    raw["inventory"][slot] = dict(made, slot=row["slot"], charging_count=0)

        snapshot, key, reason = self._decide(swap)
        self.assertEqual(teleport_follower._carried(snapshot)[0], "wand")
        self.assertEqual(reason, quest_plan_base.AWAY_REASON)
        self.assertTrue(key.startswith("a"), key)


if __name__ == "__main__":
    unittest.main()
