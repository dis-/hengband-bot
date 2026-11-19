"""The Magic-Eater's absorbed attack powers cast through Powerful Activation (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「魔道具術師の遠距離攻撃の選択肢に協力発動も入れたい」 (協力発動: 強力発動,
Powerful Activation, the class's second racial power).

The game (C++ source): racial-switcher.cpp:208 calls do_cmd_magic_eater(player, false, true); its
fail chance (cmd-magiceat.cpp:475-490) and its one charge (:570-575) are the ordinary use's, the
racial's own check never fails (rpi.fail 0, class-racial-switcher.cpp:229-235;
racial-execution.cpp racial_chance / check_racial_level), and the cost 10 + (lvl - 10) / 2 is paid
in HP (cmd-racial.cpp:441-447) after the use, failed or not (cmd-magiceat.cpp:492-504 returns
true).  The effects read ``lev = powerful ? lev * 2 : lev`` and ``rad = powerful ? 3 : 2``
(cmd-zapwand.cpp:56-57, cmd-zaprod.cpp:49-51) and a few fixed figures (cmd-zapwand.cpp:147, :263,
:269, :285-287; cmd-zaprod.cpp:154, :179; cmd-usestaff.cpp:252, :257; spells-staff-only.cpp:23).

Recorded: the n1-b town arrival of 2026-11-19 (tests/fixtures/quest32-one-turn-kill-1119/n1b-411,
Magic-Eater Lv50, HP 1082/1103, speed +25) with its displayed absorbed lists (Rockets at 70%,
Striking at 93%, the dragon wands at 96%, ...).

DECLARED CONSTRUCTED: the board moved onto the Q33 floor (tests/test_quest33_alignment_split
.on_floor) with one 『女王アリ』 (race 581, 1500 hp, GOOD, no element resistance) in view; for the
off-axis aim an open lit floor around the player and the town flag cleared (the moved board keeps
the town arrival's flag, and a town board never aims at a grid); the HP of 833 that leaves the cost
30 on the low-HP line (1103 - 300 = 803); the 150 hp the ordinary use already kills; the next
board's HP.  The executor's replies are constructed from the game's prompts (cmd-racial.cpp
racial_power_make_prompt, cmd-magiceat.cpp, target-getter.cpp get_aim_dir, target-setter.cpp).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace

from hengbot import attack_expectation, me_device_attacks, me_powerful_activation, me_ranged_first
from hengbot.me_device_attacks import POWERFUL_REASON, POWERS, powered
from hengbot.me_menu_uses import compile_menu_key
from hengbot.me_powerful_activation_input import PowerfulStep
from hengbot.model import GridState, Position
from tests.test_me_device_attacks import power_screen
from tests import test_me_powerful_activation as town_powerful
from tests.test_magic_eater_o3 import prompt
from tests.test_quest33_alignment_split import QUEEN, monster, on_floor, quest_dir, recorded
import tests.support.recorded as executor_harness

ROCKETS, STRIKING, BREATH, FLAME = ("wand", 29), ("wand", 30), ("wand", 28), ("wand", 26)
HERE = (13, 39)


class PowerfulFiguresTest(unittest.TestCase):
    """The source's figures at Lv50 (the doubled level 100)."""

    def test_each_attack_power_powered(self):
        level, none = 50, frozenset()
        cases = {
            ROCKETS: (250 + 3 * 50, 250 + 3 * 100),
            STRIKING: ((15 + 50 // 3) * 7, (15 + 100 // 3) * 7),
            BREATH: (216, 324),
            FLAME: (200, 300),
            ("wand", 27): (180, 270),
            ("wand", 15): ((2 + 5) * 3.5, (2 + 10) * 3.5),
            ("wand", 22): (70 + 3 * 50 // 4, 70 + 3 * 100 // 4),
            ("rod", 26): (70 + 50, 70 + 100),
            ("rod", 18): (70 + 3 * 50 // 2, 70 + 3 * 100 // 2),
            ("staff", 25): (150, 225),
            ("staff", 26): (150, 225),
            ("staff", 24): (80, 120),
        }
        evil = frozenset({"EVIL"})   # dispel_evil hurts only an evil race
        for ident, (ordinary, strong) in cases.items():
            power = POWERS[ident]
            flags = evil if power.element == "DISP_EVIL" else none
            self.assertAlmostEqual(me_device_attacks.expected_damage(power, level, flags), ordinary,
                                   msg=power.names[1])
            self.assertAlmostEqual(me_device_attacks.expected_damage(powered(power), level, flags),
                                   strong, msg=power.names[1])
        # Weak light: 6d8 -> 12d8 against a light-sensitive race only.
        light = POWERS[("wand", 7)]
        self.assertEqual(me_device_attacks.expected_damage(powered(light), level, {"HURT_LITE"}), 54)
        self.assertEqual(me_device_attacks.expected_damage(powered(light), level, none), 0)

    def test_a_powered_ball_widens_and_keeps_its_identity(self):
        ball, breath = POWERS[("rod", 26)], POWERS[FLAME]
        self.assertEqual((ball.area_radius, powered(ball).area_radius), (2, 3))
        self.assertEqual((breath.area_radius, powered(breath).area_radius), (3, 3))
        missile = POWERS[me_device_attacks.MISSILE]
        self.assertTrue(missile.is_missile)
        self.assertFalse(powered(missile).is_missile)
        self.assertEqual(powered(missile).ident, me_device_attacks.MISSILE)


class PowerfulAttackRecordedTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, self.board = recorded("n1b-411")
        self.addCleanup(self.scratch.cleanup)

    def queen(self, cell, *, hp=None):
        queen = monster(self.policy, 1, QUEEN, cell)
        return replace(queen, hp=queen.hp if hp is None else hp,
                       distance=Position(*HERE).distance_to(Position(*cell)))

    def on_floor(self, target, **player):
        snapshot = on_floor(self.policy, self.board, HERE, monsters=(target,))
        return replace(snapshot, player=replace(snapshot.player, **player)) if player else snapshot

    def ranked(self, snapshot, target, direction):
        return {(power.ident, power.powerful): score
                for score, power in me_device_attacks.scored(self.policy, snapshot, target, direction)}

    def test_the_recorded_character_pays_and_rockets_win_powered(self):
        player = self.board.player
        self.assertEqual((player.level, player.hp, player.max_hp), (50, 1082, 1103))
        self.assertEqual(me_powerful_activation.cost(50), 30)
        queen = self.queen((13, 49))
        snapshot = self.on_floor(queen)
        self.assertTrue(me_device_attacks.powerful_ready(self.policy, snapshot))
        ranked = self.ranked(snapshot, queen, "6")
        # Rockets at the displayed 70%: 400 ordinary, 550 powered; Striking at 93%: 217 / 336;
        # Dragon's Breath at 96%: 216 / 324.
        self.assertAlmostEqual(ranked[(ROCKETS, False)], 0.70 * 400)
        self.assertAlmostEqual(ranked[(ROCKETS, True)], 0.70 * 550)
        self.assertAlmostEqual(ranked[(STRIKING, True)], 0.93 * 336)
        self.assertAlmostEqual(ranked[(BREATH, True)], 0.96 * 324)
        # Per 10 game turns at the board's +25: one action is 3.5 of them.
        timed = attack_expectation.per_10_game_turns(self.policy, snapshot, ranked[(ROCKETS, True)])
        self.assertAlmostEqual(timed, 0.70 * 550 * 3.5)
        self.assertAlmostEqual(attack_expectation.per_10_game_turns(
            self.policy, snapshot, ranked[(ROCKETS, False)]), 0.70 * 400 * 3.5)
        # The distant chooser: ``U`` + wand + Rockets ('3', sval 29) + east.
        self.assertEqual(me_ranged_first.attack_key(self.policy, snapshot, queen), "UB36")
        self.assertEqual(self.policy.last_reason, POWERFUL_REASON)

    def test_its_cost_is_no_hit_on_the_next_board(self):
        queen = self.queen((13, 49))
        snapshot = self.on_floor(queen)
        self.assertEqual(me_ranged_first.attack_key(self.policy, snapshot, queen), "UB36")
        paid = replace(snapshot, turn=snapshot.turn + 1,
                       player=replace(snapshot.player, hp=snapshot.player.hp - 22))
        self.assertTrue(me_powerful_activation.own_cost(self.policy, paid))
        hit = replace(paid, player=replace(paid.player, hp=snapshot.player.hp - 31))
        self.assertFalse(me_powerful_activation.own_cost(self.policy, hit))

    def test_on_the_low_hp_line_the_ordinary_rockets_answer(self):
        queen = self.queen((13, 49))
        snapshot = self.on_floor(queen, hp=833)
        self.assertFalse(me_device_attacks.powerful_ready(self.policy, snapshot))
        self.assertNotIn(True, {powerful for _, powerful in self.ranked(snapshot, queen, "6")})
        self.assertEqual(me_ranged_first.attack_key(self.policy, snapshot, queen), "mB36")
        self.assertEqual(self.policy.last_reason, me_device_attacks.DEVICE_REASON)
        # One more hit point pays it.
        self.assertTrue(me_device_attacks.powerful_ready(
            self.policy, self.on_floor(queen, hp=834)))

    def test_a_target_the_ordinary_use_kills_keeps_it(self):
        # 150 hp: the score is capped by it, both ways the same; the tie keeps the ordinary use.
        queen = self.queen((13, 49), hp=150)
        snapshot = self.on_floor(queen)
        ranked = self.ranked(snapshot, queen, "6")
        self.assertAlmostEqual(ranked[(FLAME, False)], ranked[(FLAME, True)])
        key = me_ranged_first.attack_key(self.policy, snapshot, queen)
        self.assertTrue(key.startswith("mB"), key)
        self.assertEqual(self.policy.last_reason, me_device_attacks.DEVICE_REASON)

    def test_off_the_rays_the_powered_rockets_aim_at_the_cell(self):
        queen = self.queen((16, 47))
        grids = {Position(y, x): GridState(
            position=Position(y, x), known=True, passable=True, wall=False, has_monster=False,
            has_down_stairs=False, has_up_stairs=False, unsafe=False, is_closed_door=False,
            is_door=False, allows_los=True) for y in range(5, 25) for x in range(30, 60)}
        snapshot = replace(self.on_floor(queen), grids=grids, town_flag=False)
        self.assertEqual(me_ranged_first.quest_device_key(self.policy, snapshot, queen, None),
                         "UB3@16,47")
        self.assertEqual(self.policy.last_reason, POWERFUL_REASON)


class PowerfulAttackExecutorTest(executor_harness.ProductionHarness):
    """The racial prompt, the kind, the power, then get_aim_dir: through the production executor."""

    @classmethod
    def setUpClass(cls):
        town_powerful.MagicEaterPowerfulActivationTest.setUpClass()
        cls.cases = town_powerful.MagicEaterPowerfulActivationTest.cases

    # The town module's recorded board (n1-c life-033, set to Lv50) and its executor post.
    board = town_powerful.MagicEaterPowerfulActivationTest.board
    post = town_powerful.MagicEaterPowerfulActivationTest.post
    advanced = staticmethod(town_powerful.MagicEaterPowerfulActivationTest.advanced)

    def send(self, key, screens):
        policy, raw = self.board(level=50)
        policy.last_reason = POWERFUL_REASON
        return self.post(policy, raw, key, screens, self.advanced(raw))

    @staticmethod
    def rockets():
        return power_screen("wand", [("3", "ロケット", 8, 8, 30)])

    def test_the_key_compiles_only_for_its_owner(self):
        prefix, steps = compile_menu_key("UB36", POWERFUL_REASON)
        self.assertEqual(prefix, "U")
        self.assertEqual(steps[0], PowerfulStep(frozenset(), "6", sval=29, kind="wand",
                                                attack=True))
        self.assertEqual(compile_menu_key("UB3@16,47", POWERFUL_REASON)[1][0].goal, (16, 47))
        with self.assertRaises(ValueError):
            compile_menu_key("UB3", POWERFUL_REASON)  # an aimed power without its aim

    def test_along_a_ray(self):
        game, _ = self.send("UB36", [
            town_powerful.racial_screen(50), prompt(town_powerful.TYPE_PROMPT), self.rockets(),
            prompt("方向?", "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["U", "b", "B", "3", "6"])

    def test_at_a_cell_off_the_rays(self):
        policy, raw = self.board(level=50)
        y, x = raw["player"]["y"], raw["player"]["x"]
        policy.last_reason = POWERFUL_REASON

        def target(cell, free=True):
            return prompt("[q止 t決 p自 m近 +次 -前]", "target", look=False, free=free,
                          can_target=True, y=cell[0], x=cell[1])
        game, _ = self.post(policy, raw, f"UB3@{y + 1},{x + 2}", [
            town_powerful.racial_screen(50), prompt(town_powerful.TYPE_PROMPT), self.rockets(),
            prompt("方向?", "direction", can_choose_target=True),
            target((y, x), free=False), target((y, x)), target((y + 1, x + 1)),
            target((y + 1, x + 2))], self.advanced(raw))
        self.assertEqual(game.accepted, ["U", "b", "B", "3", "*", "p", "3", "6", "t"])

    def test_a_failed_roll_asks_no_aim(self):
        # The device's own roll fails before get_aim_dir (cmd-magiceat.cpp:492-504): the command
        # screen follows the power's answer and the use ends there.
        game, _ = self.send("UB36", [town_powerful.racial_screen(50), prompt(town_powerful.TYPE_PROMPT), self.rockets()])
        self.assertEqual(game.accepted, ["U", "b", "B", "3"])


if __name__ == "__main__":
    unittest.main()
