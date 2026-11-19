"""Powerful Activation in the Q25 battle, the breeder area attack and the estimates (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「魔道具術師の遠距離攻撃の選択肢に協力発動も入れたい」 (協力発動: 強力発動,
Powerful Activation), and to the follow-up (the Q25 battle, the breeder area attack and the
threat/supply estimates still read only the ordinary use) 「3つとも広げる」.  Every chooser reads
me_device_attacks.attack_uses: each usable absorbed attack power, then the same power cast
powerfully while me_powerful_activation.pays_safely holds (the same success, the doubled level,
a ball's radius 3, ``Power.area_radius``); of equal scores the ordinary use.

The game (C++ source): cmd-zapwand.cpp:56-57 / cmd-zaprod.cpp:49-51 ``lev = powerful ? lev * 2``,
``rad = powerful ? 3 : 2``; the racial's cost 10 + (lvl - 10) / 2 in hit points
(cmd-racial.cpp:441-447); the Magic-Eater use sets the turn's energy 100 either way
(cmd-magiceat.cpp:570), so a powerful use is one action as the ordinary one (the per-10-game-turn
comparison scales both alike).

Recorded / constructed, per class:

* Breeders: the n1-c life-098 swarm board (Lv31, HP 412/412, 22 software bugs of 4 HP) with the
  DECLARED CONSTRUCTED absorbed rod list of tests/test_breeder_area_attack_1103_recorded.  The
  Lightning Ball (40 + lev, 85%) catches 11 bugs at radius 2 (0.85 x 11 x 4 = 37.4) and 16 at
  radius 3 burst on [38,54] (0.85 x 16 x 4 = 54.4); the cost at Lv31 is 20 HP.  DECLARED
  CONSTRUCTED: the HP of 226 (the low-HP line 206 + the cost 20); the swarm cut to two of its
  recorded bugs ([38,60] with [38,57], 3 apart, or with [38,54], 6 apart); a more dangerous mover
  acting (``more_dangerous_acting``) for the group-damage order.
* Q25: tests/test_q25_phase_battle's board (Lv25, HP 800/800, the absorbed Fire Balls at 90%:
  88 ordinary, 107 powered, cost 17; the low-HP line max(400, 800 - 300) = 500, so 518 pays and
  517 does not).  DECLARED CONSTRUCTED as there: the phase memory, the wand lists (Fire Balls,
  Stinking Cloud, Acid Bolts), a carried Rod of Fire Balls.
* Estimates: the n1-b life-411 town arrival moved onto the Q33 floor with a 『女王アリ』 in view
  (tests/test_me_powerful_attack_1119: Rockets at 70%, 400 ordinary, 550 powered) and the
  quest32 arrivals (tests/test_quest32_one_turn_kill).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import attack_expectation, breeder_area_attack, me_device_attacks, quest_one_turn_kill
from hengbot import quest25_battle as battle, threat_projection
from hengbot.me_device_attacks import DEVICE_REASON, POWERFUL_REASON
from hengbot.model import TVAL_ROD, Position, game_distance
from tests import test_breeder_area_attack_1103_recorded as area
from tests import test_breeder_swarm_1102_recorded as swarm
from tests import test_me_powerful_attack_1119 as powerful_attack
from tests import test_q25_phase_battle as q25
from tests import test_quest32_one_turn_kill as q32
from tests.support.me_powerful import ORDINARY_ONLY

ROD_OF_FIRE_BALLS = 26   # cmd-zaprod.cpp SV_ROD_FIRE_BALL: 70 + lev, radius 2 carried


class BreederSwarmTest(unittest.TestCase):
    """breeder_area_attack: the powered ball's radius 3 picks its own burst grid."""

    def decide(self, raw):
        case = area.BreederAreaAttackRecordedTest("test_recorded_board_shot_one_bug_of_the_swarm")
        policy, key = case.decide(raw)
        return policy, key, swarm.board(policy, raw)

    def best(self, policy, snapshot, powerful):
        means = [each for each in breeder_area_attack._means(policy, snapshot)
                 if each.power.names[1] == "Lightning Balls" and each.power.powerful is powerful]
        self.assertEqual(len(means), 1)
        return max(((score, aim) for score, _prompts, _each, _send, aim
                    in breeder_area_attack._options(policy, snapshot, means)), key=lambda row: row[0])

    def test_the_powered_lightning_ball_catches_sixteen(self):
        raw = area.with_rods(area.recorded_board())
        policy, key, snapshot = self.decide(copy.deepcopy(raw))
        self.assertEqual((snapshot.player.level, snapshot.player.hp, snapshot.player.max_hp), (31, 412, 412))
        self.assertTrue(me_device_attacks.powerful_ready(policy, snapshot))
        ordinary, powered = self.best(policy, snapshot, False), self.best(policy, snapshot, True)
        self.assertAlmostEqual(ordinary[0], 0.85 * 11 * 4)
        self.assertAlmostEqual(powered[0], 0.85 * 16 * 4)
        self.assertEqual((powered[1].y, powered[1].x), (38, 54))
        self.assertEqual((key, policy.last_reason), ("UCz@38,54", POWERFUL_REASON))

    def test_on_the_low_hp_line_the_ordinary_ball_answers(self):
        raw = area.with_rods(area.recorded_board())
        # 206 = max(412 / 2, 412 - 300); the cost 20 leaves 206, not above it.
        raw["player"]["hp"] = 226
        policy, key, snapshot = self.decide(copy.deepcopy(raw))
        self.assertFalse(me_device_attacks.powerful_ready(policy, snapshot))
        self.assertTrue(key.startswith("mCz@"), key)
        self.assertEqual(policy.last_reason, DEVICE_REASON)

    @staticmethod
    def keep(raw, cells):
        """DECLARED CONSTRUCTED: only the recorded bugs on ``cells`` left in view."""
        bugs = [m for m in area.bugs_in_view(raw) if (m["y"], m["x"]) in cells]
        kept = {m["index"] for m in bugs}
        raw["visible_monsters"] = bugs
        raw["grid_map"]["cells"] = [cell for cell in raw["grid_map"]["cells"]
                                    if cell.get("m") is None or cell["m"] in kept]
        return raw

    def test_a_tie_keeps_the_ordinary_use_before_fewer_prompts(self):
        # Bugs on [38,60] (the west ray's first) and [38,57], 3 apart.  Powered, the ray's blast on
        # [38,60] reaches both (one prompt); ordinary, only a burst grid between them does (the
        # cursor walk).  Both kill the two 4-HP bugs: 0.85 x 2 x 4 = 6.8 each way; the tie keeps
        # the ordinary use, whatever its prompts.
        raw = self.keep(area.with_rods(area.recorded_board()), {(38, 60), (38, 57)})
        policy, key, snapshot = self.decide(copy.deepcopy(raw))
        self.assertAlmostEqual(self.best(policy, snapshot, False)[0], 0.85 * 2 * 4)
        self.assertAlmostEqual(self.best(policy, snapshot, True)[0], 0.85 * 2 * 4)
        self.assertTrue(key.startswith("mCz@"), key)
        self.assertEqual(policy.last_reason, DEVICE_REASON)

    def test_the_group_damage_order_keeps_the_ordinary_use_on_a_tie_too(self):
        # DECLARED CONSTRUCTED: a more dangerous mover acting (``more_dangerous_acting``), so the
        # two-or-more aim is passed and ``key`` ranks by group damage alone; the same tie.
        raw = self.keep(area.with_rods(area.recorded_board()), {(38, 60), (38, 57)})
        policy, _key, snapshot = self.decide(copy.deepcopy(raw))
        with patch.object(breeder_area_attack, "more_dangerous_acting", lambda *_args: True):
            key = breeder_area_attack.key(policy, snapshot, snapshot.visible_monsters)
        self.assertTrue(key.startswith("mCz@"), key)
        self.assertEqual(policy.last_reason, DEVICE_REASON)

    def test_a_burst_grid_three_from_each_bug_is_aimed(self):
        # Bugs on [38,60] and [38,54], 6 apart: no radius-2 blast holds both, the powered one burst
        # on [38,57] (a grid 3 from each, [38,57] or [37,57]) does: 6.8 against one bug's 3.4.
        raw = self.keep(area.with_rods(area.recorded_board()), {(38, 60), (38, 54)})
        policy, key, snapshot = self.decide(copy.deepcopy(raw))
        self.assertAlmostEqual(self.best(policy, snapshot, False)[0], 0.85 * 1 * 4)
        self.assertAlmostEqual(self.best(policy, snapshot, True)[0], 0.85 * 2 * 4)
        self.assertEqual(policy.last_reason, POWERFUL_REASON)
        self.assertTrue(key.startswith("UCz@"), key)
        grid = Position(*map(int, key[4:].split(",")))
        self.assertEqual([game_distance(grid, Position(38, x)) for x in (60, 54)], [3, 3], key)


def _q25(raw, phase, **fields):
    policy = q25.new_policy(raw)
    q25.at_phase(policy, raw, phase, **fields)
    policy._player_hasted = lambda snapshot: True
    return policy, q25.choose(policy, raw)


class Q25BattleTest(unittest.TestCase):
    """quest25_battle ``_ball_powers`` / ``_beam_key`` / ``_fire_at``."""

    def test_the_pen_takes_the_powered_fire_ball(self):
        raw = q25.with_wand_list(q25.board((5, 1), hp=518), q25.FIRE_BALL)
        policy, key = _q25(raw, "ipsissimus")
        self.assertEqual((key, policy.last_reason), ("UBw@7,17", POWERFUL_REASON))

    def test_one_hit_point_short_the_ordinary_ball(self):
        raw = q25.with_wand_list(q25.board((5, 1), hp=517), q25.FIRE_BALL)
        policy, key = _q25(raw, "ipsissimus")
        self.assertEqual((key, policy.last_reason), ("mBw@7,17", DEVICE_REASON))

    def test_the_rows_radius_and_damage(self):
        raw = q25.with_wand_list(q25.board((5, 1)), q25.FIRE_BALL)
        policy, _key = _q25(raw, "ipsissimus")
        snapshot = q25.parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        rows = [(power.powerful, power.area_radius, success * me_device_attacks.expected_damage(
                    power, 25, frozenset()))
                for power, success in me_device_attacks.attack_uses(policy, snapshot)
                if power.names[1] == "Fire Balls"]
        self.assertEqual([row[:2] for row in rows], [(False, 2), (True, 3)])
        self.assertAlmostEqual(rows[0][2], 0.9 * (70 + 3 * 25 // 4))
        self.assertAlmostEqual(rows[1][2], 0.9 * (70 + 3 * 50 // 4))

    def test_the_radius_3_burst_reaches_the_9_9_quylthulg_from_its_safe_stand(self):
        # Ordinary (radius 2) the plan skipped [9,9] for [9,13] (mBw@7,14,
        # test_q25_phase_battle.test_a_radius_2_ball_catches_9_13_from_5_2); powered, [6,8] is
        # within 3 of [9,9] and projectable from the stand [5,2].
        raw = q25.with_wand_list(q25.board((5, 2)), q25.FIRE_BALL)
        policy, key = _q25(raw, "quylthulgs")
        self.assertEqual((key, policy.last_reason), ("UBw@6,8", POWERFUL_REASON))
        low = q25.with_wand_list(q25.board((5, 2), hp=517), q25.FIRE_BALL)
        policy, key = _q25(low, "quylthulgs")
        self.assertEqual((key, policy.last_reason), ("mBw@7,14", DEVICE_REASON))

    def test_the_beam_along_the_ray_is_the_powered_bolt(self):
        # DECLARED CONSTRUCTED: the absorbed Acid Bolts (wand sval 16, letter q, 90%): 9d8 at Lv25,
        # 13d8 at the doubled 50, a beam one use in five (fire_bolt_or_beam 20).  The quylthulg
        # [9,9] lies south of the line cell [7,9] along the ray (Q25DirectQuylTest).
        bolts = {"name": "アシッド・ボルト", "fail": 10, "success": 90, "max": 10, "current": 10}
        for hp, key, share in ((800, "UBq2", 0.9 * 0.2 * 13 * 4.5), (517, "mBq2", 0.9 * 0.2 * 9 * 4.5)):
            raw = q25.with_wand_list(q25.board((7, 9), hp=hp), bolts)
            policy = q25.new_policy(raw)
            q25.at_phase(policy, raw, "quylthulgs")
            q25.choose(policy, raw)   # the board's list read (``_me_device_lists``)
            snapshot = q25.parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            damage, make = battle._beam_key(battle._ctx(policy, snapshot), q25.geo.QUYL, (9, 9))
            self.assertAlmostEqual(damage, share)
            self.assertEqual(make(), key)

    def test_a_stronger_radius_2_rod_is_not_aimed_where_only_radius_3_reaches(self):
        # DECLARED CONSTRUCTED: the absorbed Stinking Cloud (12 + lev / 4, powered radius 3) and a
        # carried Rod of Fire Balls (radius 2, the larger figure).  The plan's centre [6,8] is 3
        # from the quylthulg: only the powered cloud reaches it (``covers``); the rod aimed there
        # would burst 3 off and miss.
        raw = q25.carried(q25.with_wand_list(q25.board((5, 2)), q25.STINKING_CLOUD),
                          TVAL_ROD, ROD_OF_FIRE_BALLS, "ファイア・ボールのロッド")
        policy, key = _q25(raw, "quylthulgs")
        self.assertEqual((key, policy.last_reason),
                         ("UB" + q25.STINKING_CLOUD_LETTER + "@6,8", POWERFUL_REASON))


class EstimatesTest(unittest.TestCase):
    """attack_expectation.devices_against and threat_projection._free_devices."""

    def setUp(self):
        self.case = powerful_attack.PowerfulAttackRecordedTest("test_its_cost_is_no_hit_on_the_next_board")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_the_powered_rockets_are_the_device_figure(self):
        policy, queen = self.case.policy, self.case.queen((13, 49))
        snapshot = self.case.on_floor(queen)
        self.assertAlmostEqual(attack_expectation.devices_against(policy, snapshot, queen.race_id), 0.70 * 550)
        self.assertAlmostEqual(threat_projection._free_devices(policy, snapshot, queen), 0.70 * 550)
        low = self.case.on_floor(queen, hp=833)
        self.assertAlmostEqual(attack_expectation.devices_against(policy, low, queen.race_id), 0.70 * 400)
        self.assertAlmostEqual(threat_projection._free_devices(policy, low, queen), 0.70 * 400)


class Quest32AcceptanceTest(unittest.TestCase):
    """quest_one_turn_kill reads devices_against: the recorded arrivals keep their verdicts."""

    def test_n1b_and_n1c_device_figures(self):
        for name, ordinary, powered in (("n1b-411", 280.0, 385.0), ("n1c-217", 72.2, 106.4)):
            scratch, policy, board = q32.recorded(name)
            with scratch:
                force = policy.approved_quest_strategy(32).required_force
                found = quest_one_turn_kill.details(policy, board, force)
                self.assertEqual((found["device"], found["means"]), (powered, "melee"), name)
                with ORDINARY_ONLY:
                    self.assertEqual(quest_one_turn_kill.details(policy, board, force)["device"], ordinary)

    def test_n1c_with_two_blows_reaches_the_hasted_tier(self):
        # DECLARED CONSTRUCTED (test_quest32_one_turn_kill): two blows, melee 66.2.  The powered
        # device 106.4 is 170.2 per 10 game turns at +6 and 276.6 at +16: the hasted tier (240),
        # which the ordinary 72.2 (115.5 / 187.7) missed.  Q32 then heads the offers before Q18.
        scratch, policy, board = q32.recorded("n1c-217")
        with scratch:
            weak = replace(board, player=replace(board.player, main_hand_blows=2))
            force = policy.approved_quest_strategy(32).required_force
            found = quest_one_turn_kill.details(policy, weak, force)
            self.assertEqual((found["device"], found["per_10_game_turns"], found["tier"], found["means"]),
                             (106.4, {"permanent": 170.2, "hasted": 276.6}, "hasted", "device"))
            self.assertEqual(policy._fixed_quest_head(weak).id, 32)
            with ORDINARY_ONLY:
                self.assertIsNone(quest_one_turn_kill.tier(policy, weak, force))


if __name__ == "__main__":
    unittest.main()
