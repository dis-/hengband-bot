"""A quest plan's shot at a target off the eight rays (quest_plan_base._shot, 2026-11-19).

Owner 2026-11-12: 「射撃と取り込んだ魔法道具は常に威力比較して期待値の高い方を使用する。敵の耐性、
射撃の命中率、魔法の成功率まで考慮すること。」

n1-b life-411 (Magic-Eater Lv50, no launcher rounds), Quest 33, 2026-11-19: of 1,902 player turns
with an awake hostile in a real line of fire (line_of_fire.player_projectable, range 18, not
adjacent) the player stood still 1,777 times; replayed on main 46f619240a, 1,679 of them were
``quest-strategy:hold`` ('5'), every one with the target off the eight rays.  ``_shot`` fired the
absorbed powers only when ``_aligned``: ``me_ranged_first.attack_key`` aims by direction, and a
direction off the rays flies past the target (Direction::get_target_position, floor/geometry.h: the
player's grid plus the direction's vector times 99 unless the aim is a target), so the gate kept a
miss away but left only the launcher's rung, which has nothing to fire without rounds.  Now off the
rays the absorbed power is aimed at the cell (``@y,x``: get_aim_dir's ``*`` target,
target/target-getter.cpp; fire_bolt/fire_ball/fire_rocket project to that grid,
spell-kind/spells-launcher.cpp) over a clear projection path, when it out-damages the launcher.

DECLARED CONSTRUCTED: the replay's boards are not in this tree; the boards below are the recorded n1-b
town arrival of 2026-11-19 (tests/fixtures/quest32-one-turn-kill-1119: its absorbed power lists,
no launcher rounds) moved onto the Q33 floor (tests/test_quest33_alignment_split.on_floor, off the
town tile) with the quest map as known grids (tests/test_quest33_summon_answer), the player and the
monsters where the replay's probes saw them: turn 8483240 (the player at [12,42], the awake Rock
troll 'Tom' ロック・トロル (495) at [5,46], four sleepers), turn 8485000 ([11,39], Toms at [7,44],
[10,46], [9,46]) and the aligned control 8483601 ([12,42], a Jart (517) at [14,42], where main
already fired 'mB32').
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import re
import unittest
from dataclasses import replace

from hengbot import line_of_fire, me_device_attacks, me_ranged_first, quest_plan_base, quest_room_sweep
from hengbot.model import Position
from hengbot.policy_constants import RANGED_MAX_DISTANCE, WAIT_KEY
from tests.test_quest33_alignment_split import QUEST, monster, on_floor, quest_dir, recorded
from tests import test_quest33_summon_answer as summon_tests

TOM, JART, SLEEPER_451 = 495, 517, 451
AIMED = re.compile(r"^mB.@(\d+),(\d+)$")


class Quest33OffAxisShotTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, self.board = recorded("n1b-411")
        self.addCleanup(self.scratch.cleanup)
        self.grids = summon_tests.Quest33SummonAnswerTest._grids(self)
        self.assertIsNone(self.policy._ranged_projectile(self.board))  # no rounds to fire

    def board_at(self, player, rows, *, turn=500):
        """DECLARED CONSTRUCTED (module docstring): ``rows`` of (race, cell, asleep)."""
        here = Position(*player)
        seen = [replace(monster(self.policy, index, race, cell, asleep=asleep),
                        distance=here.distance_to(Position(*cell)))
                for index, (race, cell, asleep) in enumerate(rows, start=1)]
        snapshot = on_floor(self.policy, self.board, player, monsters=seen, turn=turn)
        return replace(snapshot, grids=self.grids, town_flag=False)

    def test_the_awake_tom_off_the_rays_is_shot_at_its_cell(self):
        # Turn 8483240: live held '5' (quest-strategy:hold).
        snapshot = self.board_at((12, 42), [(TOM, (5, 46), False)])
        tom = snapshot.visible_monsters[0]
        self.assertFalse(quest_plan_base._aligned(snapshot, tom))

        key = quest_room_sweep.key(self.policy, snapshot)

        self.assertEqual(key, "mB3@5,46")
        self.assertEqual(self.policy.last_reason, me_device_attacks.DEVICE_REASON)

    def test_the_recorded_8483240_layout_is_not_held(self):
        snapshot = self.board_at((12, 42), [
            (SLEEPER_451, (3, 39), True), (TOM, (2, 51), True), (TOM, (5, 46), False),
            (TOM, (5, 57), True), (TOM, (8, 51), True)])

        key = quest_room_sweep.key(self.policy, snapshot)

        self.assertNotEqual(key, WAIT_KEY)
        self.assertRegex(key, AIMED)
        self.assertEqual(self.policy.last_reason, me_device_attacks.DEVICE_REASON)

    def test_the_recorded_8485000_layout_shoots_a_tom(self):
        # Live held '5' at [11,39] with three Toms off the rays.
        snapshot = self.board_at((11, 39), [(TOM, (7, 44), False), (TOM, (10, 46), False),
                                            (TOM, (9, 46), False)])

        key = quest_room_sweep.key(self.policy, snapshot)

        cell = tuple(int(part) for part in AIMED.match(key or "").groups())
        self.assertIn(cell, {(7, 44), (10, 46), (9, 46)})
        self.assertEqual(self.policy.last_reason, me_device_attacks.DEVICE_REASON)

    def test_on_a_ray_the_shot_still_aims_by_direction(self):
        # Turn 8483601, the control: main fired 'mB32' at the Jart two cells south.
        snapshot = self.board_at((12, 42), [(JART, (14, 42), False)])

        self.assertEqual(quest_room_sweep.key(self.policy, snapshot), "mB32")

    def test_the_direction_would_fly_past_an_off_ray_target(self):
        # Why the direction is not used off the rays: attack_key's '9' from [12,42] is the
        # diagonal through [5,49], not Tom's [5,46].
        snapshot = self.board_at((12, 42), [(TOM, (5, 46), False)])
        tom = snapshot.visible_monsters[0]
        self.assertTrue(me_ranged_first.attack_key(self.policy, snapshot, tom).endswith("9"))
        self.assertRegex(quest_plan_base._shot(self.policy, snapshot, tom), AIMED)

    def test_confused_no_aimed_shot(self):
        snapshot = self.board_at((12, 42), [(TOM, (5, 46), False)])
        snapshot = replace(snapshot, player=replace(snapshot.player, confused=True))

        self.assertIsNone(me_ranged_first.off_ray_key(self.policy, snapshot, snapshot.visible_monsters[0]))

    def test_a_body_on_the_path_refuses_the_aimed_shot(self):
        # The bolt stops at the first monster on its way: the sleeper on the path is not shot through.
        snapshot = self.board_at((12, 42), [(TOM, (5, 46), False)])
        tom = snapshot.visible_monsters[0]
        path = line_of_fire.player_path(self.policy, snapshot, snapshot.player.position, tom.position,
                                        RANGED_MAX_DISTANCE)
        between = path[path.index(tom.position) // 2]
        blocked = self.board_at((12, 42), [(TOM, (5, 46), False), (TOM, (between.y, between.x), True)])

        self.assertIsNone(me_ranged_first.off_ray_key(self.policy, blocked, blocked.visible_monsters[0]))


if __name__ == "__main__":
    unittest.main()
