"""breeder-area-1103: against breeders the group's total damage picks the attack.

Owner 2026-11-01 (raised in priority 2026-11-03): 「増殖モンスターに対峙している
ときに範囲攻撃や視界内攻撃を優先するロジックが欲しい。増殖モンスター相手のときは
敵の群れ全体に与えるダメージ量で攻撃を選択して。」 (breeder_area_attack).

Recorded board: n1-c life-098 (Magic-Eater, Lv31) on 鉄獄24階, random quest 41,
turn 2200923 of the restarted process (tests/fixtures/breeder-swarm-20261102.json.gz,
tests/extract_breeder_swarm_1102_fixture.py): the player in the corridor at
(38, 63) east of a room holding 22 ソフトウェア・バグ (race 246, 4 HP,
MULTIPLY).  The recorded build fired a crossbow bolt west (``ranged:fire``,
``fn4``) -- one bug per shot, as on every board of the swarm (97 bolts).

DECLARED CONSTRUCTED: the absorbed rod list on the board
(``_magic_eater_power_list``): life-098 cast its absorbed rods u, v, x and z
on 20F (mCu*, mCv*, mCx*, mCz* in life-098-dec.jsonl), the restarted process
had not displayed the list yet.  Names from BaseitemDefinitions.jsonc, every
rod charged, fail 10% (the bolts) and 15% (Lightning Balls).  For the
carried-wand case: no absorbed list, and the pack's two Wands of Wonder
(slot k) made known Wands of Stinking Cloud with 5 charges.  For the
non-breeder case: race 246's knowledge without MULTIPLY.  The replies to the
posted keys are constructed from the game's prompts (cmd-magiceat.cpp,
get_aim_dir).

West, the Lightning Ball stops on the bug at (38, 60) and its radius-2 blast
(cmd-zaprod.cpp:51, range-calc.cpp ball_shape) catches five bugs: 0.85 x 5 x
4 = 17, against 4 for any one-target answer (a bolt, a shot or melee on a
4-HP bug).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot import breeder_area_attack
from hengbot.me_device_attacks import DEVICE_REASON
from tests import test_breeder_swarm_1102_recorded as swarm
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_list, power_screen, row


CASE = swarm.CASE
BOARD_TURN = 2200923
RECORDED = ("ranged:fire", "fn4")
ROD_ROWS = (("u", "アシッド・ボルト", 10), ("v", "サンダー・ボルト", 10),
            ("x", "アイス・ボルト", 10), ("z", "サンダー・ボール", 15))
LIGHTNING_BALL_WEST = "mCz4"     # rod sval 25 is I2A(25) 'z'; the room is west
WONDER_SLOT = "k"


def recorded_board():
    return copy.deepcopy(next(raw for raw in CASE["restart"] if raw["turn"] == BOARD_TURN))


def with_rods(raw):
    raw["_magic_eater_power_list"] = power_list(
        "rod", *(row(name, fail, charging=0) for _letter, name, fail in ROD_ROWS))
    return raw


def bugs_in_view(raw):
    return [m for m in raw["visible_monsters"] if m["race_id"] == swarm.SOFTWARE_BUG]


class BreederAreaAttackRecordedTest(nokey.PostedKey):
    def decide(self, raw, monraces=None):
        case = dict(CASE, boards=[raw], monraces=monraces or CASE["monraces"])
        policy = loops.new_policy(case, CASE["skill"], monraces=case["monraces"])
        policy._fixed_quest_speed_attempted = True   # swarm's DECLARED RECONSTRUCTED
        return policy, loops.decide(policy, raw)

    def test_recorded_board_shot_one_bug_of_the_swarm(self):
        raw = recorded_board()
        self.assertEqual(swarm.recorded()[BOARD_TURN], RECORDED)
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (38, 63))
        self.assertEqual(len(bugs_in_view(raw)), 22)
        self.assertIn("MULTIPLY", CASE["monraces"][str(swarm.SOFTWARE_BUG)]["flags"])

    def test_absorbed_lightning_ball_hits_the_most_bugs(self):
        raw = with_rods(recorded_board())
        policy, key = self.decide(raw)
        self.assertEqual((key, policy.last_reason), (LIGHTNING_BALL_WEST, DEVICE_REASON))
        game = self.post_power(policy, raw, key)
        self.assertEqual(game.accepted, ["m", "C", "z", "4"])

    def test_carried_ball_wand_is_chosen_the_same_way(self):
        raw = recorded_board()
        wand = next(item for item in raw["inventory"] if item["slot"] == WONDER_SLOT)
        self.assertEqual((wand["tval"], wand["sval"]), (65, 24))
        wand.update(sval=14, charges=5, name="悪臭雲の魔法棒 (5回分)")
        policy, key = self.decide(raw)
        self.assertEqual((key, policy.last_reason),
                         ("a" + WONDER_SLOT + "4", breeder_area_attack.REASON + ":wand"))
        self.post(policy, raw, key)   # the carried-wand macro (me_ranged_first.WAND_REASON's)

    def test_without_breeders_the_recorded_shot_is_kept(self):
        monraces = copy.deepcopy(CASE["monraces"])
        bug = monraces[str(swarm.SOFTWARE_BUG)]
        bug["flags"] = [flag for flag in bug["flags"] if flag != "MULTIPLY"]
        bug["can_multiply"] = False
        raw = with_rods(recorded_board())
        policy, key = self.decide(raw, monraces)
        self.assertEqual((policy.last_reason, key), RECORDED)
        self.post(policy, raw, key)

    def post_power(self, policy, raw, key):
        """The absorbed rod through the executor's prompts (cmd-magiceat.cpp)."""
        game = nokey.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = nokey.command_screen(raw["turn"])
        game.screens = [
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            power_screen("rod", [(letter, name, 0, 1, fail) for letter, name, fail in ROD_ROWS]),
            prompt("方向?", "direction", can_choose_target=True),
            nokey.command_screen(raw["turn"] + 10)]
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = nokey._ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         nokey.SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        return game


if __name__ == "__main__":
    unittest.main()
