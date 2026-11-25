"""The 50F+ Magic-Eater carries and fires no weak round, and weighs its devices off the rays (11-26).

Owner 2026-11-26 (verbatim): 「n1-c　弱い矢を撃つ仕様に戻っているようだ。魔法道具優先はどこかにいった
らしい。」  The decided rules: owner 2026-11-18 「射撃威力が100ダメージ/ターンを下回る場合は矢も持たない」
(me_deep_launcher; 「単に弱い矢はいらない」) and 2026-11-12 「射撃と取り込んだ魔法道具は常に威力比較して
期待値の高い方を使用する」 (me_ranged_first).

Recorded: n1-c life-222 (Zombie Magic-Eater Lv50, ★ロビンフッドのショート・ボウ).

* the town-arrival checkpoint of 2026-11-26 01:35:55 (turn 9751212, fixture n1c-222-town-1126,
  rows 0-29): the pack holds 97 矢 (1d4) (+0,+0) (67/shot 67/turn); the Home holds 追尾の矢
  143/turn and other stacks over 100/turn.  The old gate read only the best stack, so the target
  stayed 99; row 13 travelled for the Weapon Smith's ammo errand and row 26 bought ``pr2`` -- two
  more plain arrows (purchase-source.jsonl decision 549, rung ``tail:ammo``).
* the 95F boards of 01:41:41-45 (turns 9803875-9803913, fixture n1c-222-95f-shots-1126.jsonl.gz,
  jsonlog/snapshots with the power lists): the recorded keys were ``ranged:fire-offset`` with the
  67/turn arrows at the <コーン>の血戮悪魔 and キャリオン・クローラー one row off the ray behind a wall
  corner; ``_device_over`` answered None there (neither the ray nor the direct projection reached),
  so the absorbed staff of Power and the bolt rods were never weighed against the shot.

DECLARED RECONSTRUCTED: the 95F boards are decided by the policy restored from the 01:35 town
checkpoint (the dive's own state is not captured), open-loop.
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_deep_launcher, me_ranged_first
from hengbot.model import STORE_HOME, STORE_WEAPON, parse_snapshot
from support.town_arrival_fixture import load
from tests.test_finale_town_1123_recorded import post

FIXTURES = Path(__file__).with_name("fixtures")
TOWN = FIXTURES / "n1c-222-town-1126"
SHOTS = FIXTURES / "n1c-222-95f-shots-1126.jsonl.gz"
TRAVEL_ROW = 13   # recorded: '\x1b`n&.' toward the ammo errand
BUY_ROW = 26      # recorded: 'pr2\r\r' (2 plain arrows, rung tail:ammo)
# The recorded ranged:fire-offset boards (bot-decisions.jsonl, 01:41:41-45).
FIRE_OFFSET_TURNS = (9803888, 9803890, 9803893, 9803895, 9803899, 9803903, 9803904, 9803908,
                     9803909, 9803911, 9803913)


def plain_arrows(board):
    return next(item for item in board.inventory if item.is_ammo)


class TownWeakArrowsRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, _journal, cls.steps = load(TOWN, Path(cls.scratch.name))
        cls.done = 0  # rows decided and posted as recorded (the tests run in name order)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def replay(self, rows):
        """The recorded board of row ``rows``, the rows before it decided and posted as recorded."""
        cls, steps = type(self), self.steps
        for recorded, supply in steps[cls.done:rows]:
            with contextlib.redirect_stdout(io.StringIO()):
                cls.policy.choose_key(supply())
            post(cls.policy, recorded["key"])
        cls.done = rows
        return steps[rows][1]()

    def test_01_the_plain_arrows_are_deposited_not_topped_up(self):
        board = self.replay(TRAVEL_ROW)
        policy = self.policy
        arrows = plain_arrows(board)
        self.assertEqual((arrows.count, arrows.to_h, arrows.to_d), (97, 0, 0))
        self.assertIn("67/turn", arrows.name)
        self.assertTrue(me_deep_launcher.judged(policy, board))
        self.assertTrue(me_deep_launcher.weak_round(policy, board, arrows))
        # The Home's 143/turn stack: the rule is no blanket "no ammunition" here.
        self.assertFalse(me_deep_launcher.ammo_unneeded(policy, board))
        # Before: target 99, the plan kept all 97, the town needs held (Weapon Smith, "ammo").
        self.assertEqual(policy._ammo_procurement_target(board), 0)
        self.assertEqual(policy._ammo_procurement_target(board, arrows), 0)
        self.assertEqual(policy._count_matching_ammo(board), 0)
        self.assertEqual(policy._retention_reservation(board, arrows), 0)
        self.assertTrue(policy._home_deposit_candidate(arrows, board))
        needs = [(need.store_type, need.category) for need in policy._town_need_candidates(board)]
        self.assertIn((STORE_HOME, "deposit"), needs)
        self.assertNotIn("ammo", [category for _store, category in needs])

    def test_02_the_weapon_smith_sells_it_no_plain_arrow(self):
        board = self.replay(BUY_ROW)
        policy = self.policy
        self.assertEqual(board.store.store_type, STORE_WEAPON)
        ware = next(item for item in board.store.items if item.is_ammo and "67/turn" in item.name)
        self.assertEqual(policy._ammo_procurement_target(board, ware), 0)
        self.assertEqual(policy._matching_live_purchase_rungs(board, ware), ())
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        # Before: 'pr2\r\r' (shop:in-store-buy).
        self.assertFalse(key.startswith("p"), key)


class DeepShotsRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, _steps = load(TOWN, Path(cls.scratch.name))
        monrace = policy._monrace_knowledge
        cls.decided = {}
        pending = None
        with gzip.open(SHOTS, "rt", encoding="utf-8") as stream:
            for line in stream:
                raw = json.loads(line)
                if raw["type"] == "power_list":
                    pending = raw
                    continue
                if pending is not None:
                    raw["_magic_eater_power_list"], pending = pending, None
                board = policy.with_known_skill_exp(parse_snapshot(raw, monrace))
                with contextlib.redirect_stdout(io.StringIO()):
                    key = policy.choose_key(board)
                cls.decided[raw["turn"]] = (board, key, policy.last_reason)
        cls.policy = policy

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_no_recorded_fire_offset_board_fires_a_round(self):
        for turn in FIRE_OFFSET_TURNS:
            board, key, reason = self.decided[turn]
            with self.subTest(turn=turn):
                self.assertFalse(key.startswith("f"), (key, reason))
                self.assertTrue(reason.startswith("ranged:magic-eater-"), (key, reason))

    def test_the_weak_arrows_are_not_fired_on_95f(self):
        board = self.decided[FIRE_OFFSET_TURNS[0]][0]
        self.assertEqual(board.dungeon_level, 95)
        self.assertTrue(me_deep_launcher.weak_round(self.policy, board, plain_arrows(board)))
        self.assertIsNone(self.policy._matching_ammo(board))

    def test_the_devices_beat_the_shot_off_the_rays(self):
        """The comparison itself: with the 67/turn arrows as the rival, the victim behind the wall
        corner (off the ray, direct projection stopped) still draws a device."""
        policy = self.policy
        board = self.decided[FIRE_OFFSET_TURNS[0]][0]
        victim = next(monster for monster in board.visible_monsters
                      if (monster.position.y, monster.position.x) == (23, 156))
        self.assertIsNot(policy._ranged_target(board, [victim]), victim)
        self.assertFalse(me_ranged_first._clear_projection(policy, board, victim))
        self.assertIsNotNone(policy._offset_fire_aim(board, victim))
        # Before: None (``_device_over`` returned before weighing any power).
        key = me_ranged_first._device_over(policy, board, victim, plain_arrows(board))
        self.assertIsNotNone(key)
        self.assertFalse(key.startswith("f"))


if __name__ == "__main__":
    unittest.main()
