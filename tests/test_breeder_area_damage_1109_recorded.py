"""breeder-area-damage-1109: an area attack is used only when its group damage beats the single.

Owner 2026-11-09, verbatim: 「範囲攻撃を使うかどうかの判断基準は既に提示している。群れに対して与える
合計ダメージが単体攻撃より大きければ使う。」  Catching two or more breeders (owner 2026-11-08
「射線にいれば範囲で撃つ」, breeder_area_attack ``_mass_key``) no longer puts an area attack before a
one-target answer that deals more; among the aims that deal more, the one with the most kills.
Owner 2026-11-09 「範囲攻撃の使用判断も含めてQ2と同様の修正を入れる。」: Q25 shoots its masses
through the same chooser (quest25_battle ``_breeders_in_line_key``).

Recorded (Q2): n1-c life-181 (Lv20) at [8,47], turn 763938 (tests/fixtures/n1c-181-q2-breeder-
20261109.json.gz): three blue icky things (race 252, IM_POIS, 35 HP average), one beside the
player.  The record cast the absorbed Stinking Cloud at [11,46] (``mBo@11,46``) and again for
about twenty decisions (「青ベトベトにはかなり耐性がある！」) until it had no charge left.
Recorded (Q25): n1-c life-164 (Lv40) on [1,18], decision 43 (tests/fixtures/q25-recall-n1c-164-
1108.json.gz): six corpse masses (race 202, IM_POIS, 8d8) west of it.

Every decision is the public ``choose_key`` over the recorded boards in order from their first.
DECLARED CONSTRUCTED: the absorbed wand list (``_magic_eater_power_list``) on the decided board,
as the executor puts it on a board after the power prompt: life-181's wand rows of its town
checkpoint (turn 770899) with Stinking Cloud at 20/20 (it had charges at 763938, 0 at 764190);
life-164's list is not on its boards, so one wand row.  The Fire Balls row (70 + 3*lev/4 fire,
radius 2) replaces Stinking Cloud for the area-beats-single cases.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import breeder_area_attack
from hengbot.me_device_attacks import DEVICE_REASON
from hengbot.model import parse_snapshot
from hengbot.quest_find_exit import MELEE_REASON
from tests import test_n1c_181_q2_breeder_1109_recorded as q2
from tests import test_q25_n1c_164_1108_recorded as q164
from tests import test_breeder_swarm_1102_recorded as swarm
from tests.test_me_device_attacks import power_list, row


CLOUD, FIRE_BALL = "悪臭雲", "ファイア・ボール"
SLIME_TURN = 763938
Q25_BOARD = 43


def q2_wands(raw, ball):
    """DECLARED CONSTRUCTED (module docstring)."""
    raw["_magic_eater_power_list"] = power_list(
        "wand", row("テレポート・アウェイ", 11, current=12, count=12),
        row("トラップ解除", 11, current=10, count=10), row("岩石溶解", 11, current=14, count=16),
        row(ball, 11, current=20, count=20), row("マジック・ミサイル", 11, current=17, count=17))
    return raw


def q2_decide(ball):
    index = max(i for i, raw in enumerate(q2.BOARDS) if raw["turn"] == SLIME_TURN)
    policy = q2.new_policy()
    q2.replay(policy, q2.BOARDS[:index])
    raw = q2_wands(copy.deepcopy(q2.BOARDS[index]), ball)
    return policy, raw, q2.decide(policy, copy.deepcopy(raw))


def q25_decide(ball):
    policy = q164.new_policy(q164.CASE["boards"][0])
    for raw, recorded in zip(q164.CASE["boards"], q164.CASE["recorded"]):
        raw = copy.deepcopy(raw)
        if recorded["sequence"] == Q25_BOARD:
            raw["_magic_eater_power_list"] = power_list("wand", row(ball, 10, current=20, count=20))
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        policy.confirm_key_posted(key)
        if recorded["sequence"] == Q25_BOARD:
            return policy, raw, key
    raise AssertionError("no board 43")


def group_and_single(policy, raw):
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    means = breeder_area_attack._means(policy, snapshot)
    hostiles = [monster for monster in snapshot.visible_monsters if monster.hostile]
    best = max(option[0] for option in breeder_area_attack._options(policy, snapshot, means))
    return best, breeder_area_attack._one_target_best(policy, snapshot, means, hostiles)


class Q2BlueSlimeTest(swarm.PostedSwarmKey):
    def test_recorded_cast_the_cloud(self):
        rows = [row for row in q2.CASE["decisions"] if row["turn"] == SLIME_TURN]
        self.assertIn(("mBo@11,46", DEVICE_REASON), [(row["key"], row["reason"]) for row in rows])

    def test_the_cloud_on_poison_proof_slimes_gives_way_to_the_single_attack(self):
        policy, raw, key = q2_decide(CLOUD)
        group, single = group_and_single(policy, raw)
        self.assertLess(group, single)
        self.assertEqual((key, policy.last_reason), ("2", "quest-strategy:melee"))  # the one beside
        self.post(policy, raw, key)

    def test_a_ball_that_beats_the_single_is_burst(self):
        policy, raw, key = q2_decide(FIRE_BALL)
        group, single = group_and_single(policy, raw)
        self.assertGreater(group, single)
        self.assertEqual((key, policy.last_reason), ("mBw@10,46", DEVICE_REASON))


class Q25MassTest(unittest.TestCase):
    def test_the_cloud_on_poison_proof_masses_gives_way_to_the_shot(self):
        policy, raw, key = q25_decide(CLOUD)
        group, single = group_and_single(policy, raw)
        self.assertLess(group, single)
        self.assertEqual(key, "fp*p44t5\x1b")
        self.assertNotEqual(policy.last_reason, DEVICE_REASON)
        self.assertNotEqual(policy.last_reason, MELEE_REASON)

    def test_a_ball_that_beats_the_shot_is_burst_where_it_kills_most(self):
        policy, raw, key = q25_decide(FIRE_BALL)
        group, single = group_and_single(policy, raw)
        self.assertGreater(group, single)
        self.assertEqual((key, policy.last_reason), ("mBw@1,15", DEVICE_REASON))


if __name__ == "__main__":
    unittest.main()
