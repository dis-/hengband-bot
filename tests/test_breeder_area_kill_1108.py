"""breeder-area-kill-1108: breeders in the line of fire are shot, the aim with the most kills first.

Owner 2026-11-08: 「20行動で減らせないのであれば倒すアルゴリズム側に問題がある。特に範囲攻撃の使い方
など。」 and the chosen option 「射線にいれば範囲で撃つ」: 「どの段でも、もっと危ない敵が動いていなければ、
射線にいる増える敵を撃つ。範囲攻撃は一番多く倒せるマスを狙い、2体以上巻き込めるなら単体攻撃より先に
使う。道をふさがれたら待たずに撃って開ける。20回の判定は、実際に攻撃した手だけで数える。」

Recorded: n1-c life-159 Q25 (tests/fixtures/q25-mass-n1c-159-1107.json.gz), board 424: the player
(Magic-Eater Lv40) on [1,18], five corpse masses (race 202, 8d8, average 36 HP, NEVER_MOVE,
MULTIPLY, IM_COLD/IM_POIS) on [1,14] [1,15] [1,16] [2,14] [2,16] in view, nothing else; the
recording held (``quest-strategy:hold``) on every board from 400 to 431.

DECLARED CONSTRUCTED: the absorbed wand list (``_magic_eater_power_list``): life-159/164 carried
the absorbed Fire Balls wand (investigation of the hold), not shown on the recorded boards.  Fire
Balls: 70 + 3*lev/4 = 100 at Lv40, radius 2 (cmd-zapwand.cpp:245-246); the falloff
(dam + r) / (r + 1) (effect-monster.cpp:108) gives 50 one grid off, 34 two off.  Burst on [1,15],
every mass is within one grid: 5 kills (50 >= 36).  Aimed west by direction it stops on [1,16]
and [1,14] and [2,14] are two grids off (34 < 36): 3 kills.

The open-floor pack (DECLARED CONSTRUCTED from the breeder-swarm board, tests/
test_breeder_area_attack_1103_recorded): the two software bugs nearest the player kept, their race given 150 HP,
and the Wand of Stinking Cloud (12 poison, radius 2) the 1103 test makes of the pack's Wands of
Wonder.  The cloud's group damage (28.2) is below one crossbow shot (36), so the 11-01 comparison
alone shot one bug, and still does: owner 2026-11-09 「群れに対して与える合計ダメージが単体攻撃より
大きければ使う。」 (two or more caught do not put the area attack before a stronger single shot).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import breeder_area_attack, quest25_battle as battle
from hengbot import quest25_geometry as geo
from hengbot.me_device_attacks import DEVICE_REASON
from hengbot.model import parse_snapshot
from hengbot.quest_find_exit import HOLD_REASON
from tests import test_breeder_area_attack_1103_recorded as area
from tests import test_breeder_swarm_1102_recorded as swarm
from tests import test_q25_n1c_159_1107_recorded as q159
from tests.test_me_device_attacks import power_list, row


HOLD_BOARD = 424
MASSES = [(1, 14), (1, 15), (1, 16), (2, 14), (2, 16)]
FIRE_BALL_BURST = "@1,15"


def with_fire_ball(raw):
    """DECLARED CONSTRUCTED: the absorbed Fire Balls wand (5 charges, 10% fail)."""
    raw["_magic_eater_power_list"] = power_list("wand", row("ファイア・ボール", 10, current=5, count=5))
    return raw


def masses(raw):
    return sorted((m["y"], m["x"]) for m in raw["visible_monsters"] if m["race_id"] == geo.MASS)


class Q25MassesInLineTest(unittest.TestCase):
    def setUp(self):
        raw, recorded = q159.BY_SEQUENCE[HOLD_BOARD]
        self.raw = with_fire_ball(copy.deepcopy(raw))
        self.assertEqual((self.raw["player"]["y"], self.raw["player"]["x"]), (1, 18))
        self.assertEqual(masses(self.raw), MASSES)
        self.assertEqual(len(self.raw["visible_monsters"]), len(MASSES))
        self.assertEqual((recorded["key"], recorded["reason"]), ("5", HOLD_REASON))

    def decide(self, raw, phase):
        policy = q159.new_policy(raw)
        q159.at_phase(policy, raw, phase, style="ranged")   # CONSTRUCTED memory
        policy._player_hasted = lambda snapshot: True
        return policy, q159.choose(policy, raw)

    def test_the_recorded_hold_fires_the_ball_where_it_kills_most(self):
        policy, key = self.decide(self.raw, "ambush")
        self.assertEqual(policy.last_reason, DEVICE_REASON, key)
        self.assertTrue(key.endswith(FIRE_BALL_BURST), key)
        snapshot = parse_snapshot(copy.deepcopy(self.raw), policy._monrace_knowledge)
        means = breeder_area_attack._means(policy, snapshot)
        blocks = breeder_area_attack._blocker(snapshot)
        ball = next(each for each in means if each.power.names[1] == "Fire Balls")
        burst, _ = breeder_area_attack._tally(policy, snapshot, ball, q159.battle.Position(1, 15), blocks)
        west, _ = breeder_area_attack._tally(policy, snapshot, ball, (0, -1), blocks)
        self.assertAlmostEqual(burst, 0.9 * 5)
        self.assertAlmostEqual(west, 0.9 * 3)

    def test_the_aim_kills_most_rather_than_damages_most(self):
        # DECLARED CONSTRUCTED health bands: [1,15] [1,16] [2,16] wounded (the band's upper bound,
        # 59% of 64 = 38 HP, model._estimated_monster_hp), [1,14] [2,14] unhurt; every one dies at
        # 36 (the dice average).  The burst on [1,15] has all five within one grid (50): 5 kills,
        # 0.9 x 5 = 4.5, group damage 0.9 x 214.  The burst on [1,14] has [1,16] and [2,16] two
        # grids off (34): 3 kills, 2.7, but more group damage (0.9 x 220: the unhurt mass under
        # it takes 64 of the 100).  「一番多く倒せるマスを狙い」: the kills decide.
        raw = copy.deepcopy(self.raw)
        wounded = {(1, 15), (1, 16), (2, 16)}
        for monster in raw["visible_monsters"]:
            monster["health"] = "wounded" if (monster["y"], monster["x"]) in wounded else "unhurt"
        policy, key = self.decide(raw, "ambush")
        self.assertEqual(policy.last_reason, DEVICE_REASON, key)
        self.assertTrue(key.endswith(FIRE_BALL_BURST), key)

    def test_in_every_phase_the_masses_in_line_are_shot(self):
        for name in battle.PHASE_NAMES:
            with self.subTest(phase=name):
                policy, key = self.decide(self.raw, name)
                self.assertNotEqual(policy.last_reason, HOLD_REASON, key)
                self.assertNotIn(policy.last_reason, (battle.WALK_REASON,), key)

    def test_a_more_dangerous_mover_awake_keeps_the_phase_order(self):
        raw = copy.deepcopy(self.raw)
        tyrannosaur = dict(copy.deepcopy(raw["visible_monsters"][0]), index=9001, race_id=q159.SPECTRAL_T,
                           y=4, x=19, health="unhurt", asleep=False)
        raw["visible_monsters"].append(tyrannosaur)
        policy = q159.new_policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertTrue(breeder_area_attack.more_dangerous_acting(policy, snapshot))
        self.assertIsNone(breeder_area_attack.line_of_fire_key(policy, snapshot, lambda target: "x"))


class OpenFloorPackTest(area.BreederAreaAttackRecordedTest):
    def pack(self):
        raw = area.recorded_board()
        player = raw["player"]
        bugs = sorted(area.bugs_in_view(raw),
                      key=lambda m: max(abs(m["y"] - player["y"]), abs(m["x"] - player["x"])))[:2]
        kept = {m["index"] for m in bugs}
        raw["visible_monsters"] = bugs
        raw["grid_map"]["cells"] = [cell for cell in raw["grid_map"]["cells"]
                                    if cell.get("m") is None or cell["m"] in kept]
        wand = next(item for item in raw["inventory"] if item["slot"] == area.WONDER_SLOT)
        wand.update(sval=14, charges=5, name="悪臭雲の魔法棒 (5回分)")
        monraces = copy.deepcopy(swarm.CASE["monraces"])
        monraces[str(swarm.SOFTWARE_BUG)].update(max_hp=150, average_hp=150)
        return raw, monraces

    def test_two_caught_below_the_single_shot_shoot_one(self):
        raw, monraces = self.pack()
        policy, key = self.decide(raw, monraces)
        snapshot = swarm.board(policy, raw)
        means = breeder_area_attack._means(policy, snapshot)
        hostiles = [m for m in snapshot.visible_monsters if m.hostile]
        baseline = breeder_area_attack._one_target_best(policy, snapshot, means, hostiles)
        best_group = max(option[0] for option in breeder_area_attack._options(policy, snapshot, means))
        self.assertLess(best_group, baseline)   # the 11-01 comparison: one bug is shot
        self.assertEqual((key, policy.last_reason), ("fn4", "ranged:fire"))
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
