"""A Magic-Eater with no rounds casts its absorbed attack powers at a distant enemy (2026-11-19).

Owner 2026-11-12: 「射撃と取り込んだ魔法道具は常に威力比較して期待値の高い方を使用する。敵の耐性、
射撃の命中率、魔法の成功率まで考慮すること。」

On an ordinary floor the ranged rung (policy_combat ``_ranged_attack_key``) returned None when
``_ranged_projectile`` found nothing to fire or throw, and ``me_ranged_first.stronger_than_launcher_key``
returned None without ``ammo``: a Magic-Eater with no launcher rounds never cast an absorbed attack
power at a distant enemy, on the eight rays or off them, and with a torch or a flask of oil to throw
it threw it without weighing the powers.  summon_response ``_shot_at`` reaches the same rung off the
rays.  Now without rounds the rung asks the same chooser (``_device_over``, Powerful Activation
included since me-powerful-attack-1119) against the throw's figure (attack_expectation.thrown_item),
or against nothing.

DECLARED CONSTRUCTED: the recorded n1-b town arrival of 2026-11-19 (tests/fixtures/
quest32-one-turn-kill-1119/n1b-411: Magic-Eater Lv50, its displayed absorbed lists, no launcher
rounds, no torch or oil) moved onto an ordinary dungeon floor (Angband 45F; tests/
test_quest33_alignment_split.on_floor, then the floor key, no quest, off the town tile) with the Q33
map as known grids (tests/test_quest33_summon_answer, used only as terrain), a Rock troll 'Tom'
ロック・トロル (495) awake at [5,46] (off the rays) or [16,42] (on the column, a clear ray) from [12,42]; for the
throw a constructed stack of five lit torches on 5F.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import attack_expectation, me_device_attacks, me_ranged_first, summon_response
from hengbot.model import InventoryItem, Position
from tests.test_quest33_alignment_split import monster, on_floor, quest_dir, recorded
from tests import test_quest33_summon_answer as summon_tests

TOM = 495
HERE = (12, 42)
OFF_RAY, ON_RAY = (5, 46), (16, 42)
DEVICE_REASONS = {me_device_attacks.DEVICE_REASON, me_device_attacks.POWERFUL_REASON}
TVAL_LITE, SV_LITE_TORCH = 39, 0


class NoRoundsDeviceTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, self.board = recorded("n1b-411")
        self.addCleanup(self.scratch.cleanup)
        self.grids = summon_tests.Quest33SummonAnswerTest._grids(self)

    def board_at(self, cell, *, depth=45, inventory=None):
        """DECLARED CONSTRUCTED (module docstring)."""
        tom = replace(monster(self.policy, 1, TOM, cell), distance=Position(*HERE).distance_to(Position(*cell)))
        snapshot = replace(on_floor(self.policy, self.board, HERE, monsters=(tom,)), grids=self.grids,
                           town_flag=False, floor_key=(1, depth, 0), quests={})
        if inventory is not None:
            snapshot = replace(snapshot, inventory=inventory)
        return snapshot

    def rung(self, snapshot):
        return self.policy._ranged_attack_key(snapshot, list(snapshot.visible_monsters), [])

    def assert_device(self, key, cell=None):
        self.assertIsNotNone(key)
        self.assertIn(self.policy.last_reason, DEVICE_REASONS)
        self.assertTrue(key.startswith(("m", "U")), key)
        if cell is not None:
            self.assertTrue(key.endswith(f"@{cell[0]},{cell[1]}"), key)

    def test_no_rounds_to_fire(self):
        self.assertIsNone(self.policy._ranged_projectile(self.board_at(OFF_RAY)))

    def test_off_the_rays_the_power_is_aimed_at_the_cell(self):
        snapshot = self.board_at(OFF_RAY)
        key = self.rung(snapshot)
        self.assert_device(key, OFF_RAY)
        # The one chooser: the same key the shared scoring (Powerful Activation included) gives.
        self.assertEqual(key, me_ranged_first.stronger_than_launcher_key(
            self.policy, snapshot, snapshot.visible_monsters[0], None))

    def test_on_the_column_the_power_is_cast(self):
        self.assert_device(self.rung(self.board_at(ON_RAY)))

    def test_control_another_class_still_has_nothing_to_shoot(self):
        snapshot = self.board_at(OFF_RAY)
        snapshot = replace(snapshot, player=replace(snapshot.player, class_id=1))
        self.assertIsNone(self.rung(snapshot))

    def torches(self):
        return [*self.board.inventory, InventoryItem(
            slot="w", name="松明", count=5, tval=TVAL_LITE, sval=SV_LITE_TORCH, aware=True, known=True,
            fuel=5000)]

    def test_the_power_goes_before_a_weaker_torch_throw(self):
        snapshot = self.board_at(OFF_RAY, depth=5, inventory=self.torches())
        kind, torch, _reason = self.policy._ranged_projectile(snapshot)
        self.assertEqual(kind, "throw")
        tom = snapshot.visible_monsters[0]
        self.assertLess(attack_expectation.thrown_item(self.policy, snapshot, tom, torch),
                        me_ranged_first.best_expected(self.policy, snapshot, tom))
        self.assert_device(self.rung(snapshot), OFF_RAY)

    def test_control_a_stronger_throw_is_thrown(self):
        snapshot = self.board_at(ON_RAY, depth=5, inventory=self.torches())
        with patch.object(attack_expectation, "thrown_item", return_value=10 ** 6):
            key = self.rung(snapshot)
        self.assertEqual(self.policy.last_reason, "ranged:throw-torch")
        self.assertTrue(key.startswith("v"), key)

    def test_a_flask_of_oil_is_a_plain_2d6_throw(self):
        snapshot = self.board_at(OFF_RAY)
        oil = InventoryItem(slot="x", name="油つぼ", count=5, tval=77, sval=0, aware=True, known=True,
                            fuel=7500, damage_dice_num=2, damage_dice_sides=6)
        figure = attack_expectation.thrown_item(self.policy, snapshot, snapshot.visible_monsters[0], oil)
        self.assertGreater(figure, 0)
        self.assertLessEqual(figure, 7)

    def test_the_summon_answer_casts_off_the_rays(self):
        snapshot = self.board_at(OFF_RAY)
        key = summon_response._shot_at(self.policy, snapshot, snapshot.visible_monsters[0])
        self.assert_device(key, OFF_RAY)


if __name__ == "__main__":
    unittest.main()
