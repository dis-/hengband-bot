"""n1-c (Magic-Eater) life-196 2026-11-12 04:05: stuck-prompt:summoner:ranged-kill.

Recorded: tests/fixtures/n1c-196-summoner-power-1112.json.xz
(tests/extract_n1c_196_summoner_power_1112_fixture.py), Angband 40F, the Lv34
Magic-Eater at [3,38] and a ノーム・メイジ (race 281, a summoner) at [1,39], two grids away
off the eight rays.  The summoner rung (policy ``_summoner_ranged_kill_key``) asked the
ranged rung for its shot; the ranged rung, weighing the launcher against the absorbed
powers (owner 2026-11-12 「射撃と取り込んだ魔法道具は常に威力比較して期待値の高い方を
使用する。」), answered with the absorbed サンダー・ボール rod aimed at the mage's cell
(``mCz@1,39``, me_device_attacks.device_target_key).  The summoner rung then renamed the
reason to ``summoner:ranged-kill``; the executor runs a device key only under its own
reason (me_device_attacks_input), so the key went out as raw keys, ``@`` reached the
power prompt and the prompt stayed open: three restarts and an escalation (and n1-b
life-371, n1-c life-198).  Now the summoner rung renames only a projectile's reason.

Every decision is the public ``choose_key`` of a fresh policy; the key is posted through
the production executor port with the game's prompts.
DECLARED RESTORED: the absorbed rod list the live policy held, from the stop screen (the
list left open under the power prompt; サンダー・ボール shown 1/1 charging just after its
use, so 0/1 before it); no wand or staff list (the stop shows neither).  The skill
knowledge is supplied (tests/support/recorded ``skill``).  The replies to the posted key
are constructed from the game's prompts (cmd-magiceat.cpp, get_aim_dir, target_set's
monster and free modes, target-setter.cpp:221 and :470), as
tests/test_breeder_area_attack_1103_recorded.py does.

n1-b life-373 2026-11-12 07:30 loop-detected (the fixture's ``loop``, Lv9, Yeek cave 3F):
a 大黄色ヘビ at [14,104] off the rays from [15,108]; the ranged rung answered with the
absorbed Magic Missile aimed at its cell (``mBp@14,104``, DEVICE_REASON) at its
optimistic 100% (the wand list not displayed); the executor found no charged missile
row and closed the prompt turn-free, the same key came back, until the loop detector
(the same at life-375 07:54, 'mBp@41,20').  Off the rays the missile is now used only
from its displayed charged row; the boards then decide as before the weighing (seek-loot).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.me_device_attacks import DEVICE_REASON, observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests import test_me_nokey_1031_recorded as nokey
from tests.support.recorded import EDIT, skill
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_list, power_screen, row

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-196-summoner-power-1112.json.xz"
RECORDED = {"turn": 2952423, "reason": "summoner:ranged-kill", "key": "mCz@1,39",
            "rung": "_summoner_ranged_kill_key"}
# The stop screen's rod list (letter, name, charging, count, fail%), before the ball's use.
ROD_ROWS = (("a", "トラップ感知", 0, 7, 5), ("b", "ドア/階段感知", 0, 6, 5), ("d", "帰還", 0, 1, 5),
            ("e", "イルミネーション", 0, 8, 5), ("g", "全感知", 0, 1, 5),
            ("m", "害虫駆除", 0, 4, 5), ("n", "テレポート・アウェイ", 0, 1, 5),
            ("p", "光", 0, 5, 5), ("v", "サンダー・ボルト", 0, 2, 5),
            ("w", "ファイア・ボルト", 1, 1, 5), ("x", "アイス・ボルト", 0, 4, 5),
            ("y", "アシッド・ボール", 0, 1, 33), ("z", "サンダー・ボール", 0, 1, 5),
            ("1", "アイス・ボール", 0, 1, 15))
MAGE, MAGE_CELL = 281, (1, 39)
TARGET_GUIDE = "q止 t決 p自 o現 +次 -前"        # target-setter.cpp:221 (monster mode)
FREE_GUIDE = "q止 t決 p自 m近 +次 -前"          # target-setter.cpp:470 (free mode)


class SummonerPowerRecordedTest(nokey.PostedKey):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def board(self):
        return copy.deepcopy(self.payload["board"])

    def decide(self, raw):
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.races))
        shown = dict(copy.deepcopy(raw), _magic_eater_power_list=power_list(
            "rod", *(row(name, fail, charging=charging, count=count)
                     for _letter, name, charging, count, fail in ROD_ROWS)))
        observe_lists(policy, parse_snapshot(shown, self.races))
        skill(policy, raw)
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.races))
        return policy, str(key)

    def test_the_recorded_stop(self):
        self.assertEqual(self.payload["decisions"][-1], RECORDED)
        context = self.payload["stop_screen"]["input_context"]
        self.assertEqual((context["kind"], context["prompt"]),
                         ("spell", "('*'で一覧, ESCで中断) どの魔力を使いますか？"))
        raw = self.board()
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (3, 38))
        mage = next(monster for monster in raw["visible_monsters"] if monster["race_id"] == MAGE)
        self.assertEqual((mage["y"], mage["x"]), MAGE_CELL)

    def test_the_ball_at_the_mage_keeps_the_device_reason_and_completes(self):
        raw = self.board()
        policy, key = self.decide(raw)
        # Off the eight rays the absorbed ball is aimed at the mage's cell, by the reason
        # the executor runs it under (it was renamed summoner:ranged-kill).
        self.assertEqual((key, policy.last_reason), (RECORDED["key"], DEVICE_REASON))
        game = self.post_power(raw, key, policy)
        self.assertEqual(game.accepted, ["m", "C", "z", "*", "p", "9", "8", "t"])

    def test_under_the_summoner_reason_the_key_does_not_complete(self):
        # The live failure: the same key posted under the renamed reason is no device
        # operation; it does not complete (the stuck power prompt).
        raw = self.board()
        policy, key = self.decide(raw)
        policy.last_reason = RECORDED["reason"]
        with self.assertRaisesRegex(AssertionError, "stuck-prompt> owner=summoner:ranged-kill"):
            self.post_power(raw, key, policy)

    def post_power(self, raw, key, policy):
        """The absorbed rod through the executor's prompts (cmd-magiceat.cpp, target_set)."""
        def target(free, y, x):
            guide = FREE_GUIDE if free else TARGET_GUIDE
            return prompt(f"ノーム・メイジ(無傷)を見ている [r思 {guide}]", "target",
                          look=False, free=free, can_target=True, y=y, x=x)
        game = nokey.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = nokey.command_screen(raw["turn"])
        game.screens = [
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            power_screen("rod", [(letter, name, charging, count, fail)
                                 for letter, name, charging, count, fail in ROD_ROWS]),
            prompt("方向?", "direction", can_choose_target=True),
            target(False, *MAGE_CELL), target(True, 3, 38), target(True, 2, 39),
            target(True, *MAGE_CELL),
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



class GridMissileLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))["loop"]
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def test_the_unseen_missile_is_not_aimed_at_a_cell(self):
        self.assertEqual({(row["turn"], row["key"]) for row in self.payload["decisions"][:3]},
                         {(800575, "mBp@14,104")})
        boards = self.payload["boards"]
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.races))
        keys = []
        for raw in boards:
            skill(policy, raw)
            key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.races)))
            if key:
                policy.confirm_key_posted(key)
            keys.append((key, policy.last_reason))
        self.assertFalse([pair for pair in keys if pair[0].startswith("mBp@")], keys)
        self.assertEqual(keys[-1], ("1", "seek-loot"))


if __name__ == "__main__":
    unittest.main()
