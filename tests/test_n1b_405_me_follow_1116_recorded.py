"""n1-b (Magic-Eater) life-405 2026-11-16 05:36: stuck-prompt:ranged:magic-eater-device, twice.

Recorded: tests/fixtures/n1b-405-me-follow-1116.json.xz
(tests/extract_n1b_405_me_follow_1116_fixture.py), Angband 80F, the Lv46 Magic-Eater at
[17,167] and a ウィル・オー・ウィスプ two grids away off the eight rays:

- 05:36:49, decision 5108 (turn 4097046): ``mB4@15,166``, the absorbed 衝撃 (wand sval 30)
  aimed at the wisp's cell [15,166];
- 05:36:56, decision 6 of the restarted process (turn 4097058): ``mB4@15,168``.

The wisp teleports itself (TPORT); spells-teleport.cpp teleport_away_followable then asks
「ついていきますか？[y/n]」 on the monster's turn, since the character wields a TR_TELEPORT
item.  The executor answers that question n for every owner (owner 2026-11-06,
input_executor ``_is_follow_teleport_confirm``), but the Magic-Eater menu walk
(me_menu.MagicEaterMenu.advance) read it first, found no stage for it and stopped the
operation (「unexpected prompt after Magic-Eater device answer」, both stop screens).  Now
the walk leaves that question to the executor's answer.

Every decision is the public ``choose_key`` of a fresh policy; the key is posted through
the production executor port with the game's prompts.
DECLARED RECONSTRUCTION / RESTORED (pin_vacuity): the absorbed lists are the earliest kept
spectator frame of life-405 (decision 29803 of the previous process, turns
3484926-3485739; the stops' frames had rolled to life-406); the skill knowledge is supplied
(tests/support/recorded ``skill``).
DECLARED CONSTRUCTED: the replies before the stop screen, from the game's prompts
(cmd-magiceat.cpp, get_aim_dir, target_set's monster and free modes, target-setter.cpp:221
and :470), as tests/test_n1c_196_summoner_power_1112_recorded.py does; the wand list screen
shows the attack rows of those lists; the command screen after the answer.  The follow
question itself is each stop's recorded screen.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path

from hengbot import me_device_attacks
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.me_device_attacks import DEVICE_REASON, observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests import test_me_nokey_1031_recorded as nokey
from tests.support.recorded import EDIT, skill
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-405-me-follow-1116.json.xz"
FIRST = "20261116-053649-stuck-prompt-ranged-magic-eater-device"
SECOND = "20261116-053656-stuck-prompt-ranged-magic-eater-device"
WISP = "ウィル・オー・ウィスプ"
TARGET_GUIDE = "q止 t決 p自 o現 +次 -前"        # target-setter.cpp:221 (monster mode)
FREE_GUIDE = "q止 t決 p自 m近 +次 -前"          # target-setter.cpp:470 (free mode)
# The free-mode cursor walk from the player [17,167] to each wisp cell, and its keys.
WALKS = {FIRST: (((17, 167), (16, 166), (15, 166)), ["p", "7", "8", "t"]),
         SECOND: (((17, 167), (16, 168), (15, 168)), ["p", "9", "8", "t"])}


class MagicEaterFollowPromptRecordedTest(nokey.PostedKey):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def stop(self, name):
        return copy.deepcopy(self.payload["stops"][name])

    def decide(self, raw):
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.races))
        for kind, entry in self.payload["lists"].items():
            shown = dict(copy.deepcopy(raw), turn=raw["turn"] - 1,
                         _magic_eater_power_list={"kind": kind, "rows": entry["rows"]})
            observe_lists(policy, parse_snapshot(shown, self.races))
        skill(policy, raw)
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.races))
        return policy, str(key)

    def wand_rows(self):
        """(letter, name, current, max, fail) of the wand list's attack rows."""
        by_name = {power.names[0]: power for (kind, _), power in me_device_attacks.POWERS.items()
                   if kind == "wand"}
        return [(by_name[row["name"]].letter, row["name"], row["current"], row["max"], row["fail"])
                for row in self.payload["lists"]["wand"]["rows"] if row["name"] in by_name]

    def post_power(self, name, raw, key, policy):
        """The absorbed wand through the executor's prompts, then the stop's follow question."""
        cells, _ = WALKS[name]
        wisp = next(monster for monster in raw["visible_monsters"] if monster["name"] == WISP)

        def target(free, y, x):
            guide = FREE_GUIDE if free else TARGET_GUIDE
            return prompt(f"{WISP}(無傷)を見ている [r思 {guide}]", "target",
                          look=False, free=free, can_target=True, y=y, x=x)
        game = nokey.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = nokey.command_screen(raw["turn"])
        game.screens = [
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            power_screen("wand", self.wand_rows()),
            prompt("方向?", "direction", can_choose_target=True),
            target(False, wisp["y"], wisp["x"]),
            *(target(True, y, x) for y, x in cells),
            self.stop(name)["stop_screen"],
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

    def test_the_recorded_stops(self):
        for name, sequence, key in ((FIRST, 5108, "mB4@15,166"), (SECOND, 6, "mB4@15,168")):
            with self.subTest(stop=name):
                stop = self.stop(name)
                self.assertEqual((stop["decision"]["decision_sequence"], stop["decision"]["reason"],
                                  stop["decision"]["key"]), (sequence, DEVICE_REASON, key))
                context = stop["stop_screen"]["input_context"]
                self.assertEqual((context["kind"], context["prompt"]),
                                 ("confirm", "ついていきますか？[y/n]"))
                raw = stop["board"]
                self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (17, 167))

    def test_the_wisp_is_shot_and_the_follow_question_is_refused(self):
        for name in (FIRST, SECOND):
            with self.subTest(stop=name):
                stop = self.stop(name)
                raw = stop["board"]
                policy, key = self.decide(raw)
                # The absorbed 衝撃 (wand sval 30, letter 4) at the wisp's cell, as recorded.
                self.assertEqual((key, policy.last_reason), (stop["decision"]["key"], DEVICE_REASON))
                game = self.post_power(name, raw, key, policy)
                _, walk = WALKS[name]
                self.assertEqual(game.accepted, ["m", "B", "4", "*", *walk, "n"])


if __name__ == "__main__":
    import unittest
    unittest.main()
