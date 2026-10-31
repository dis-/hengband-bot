"""A town ball spares a friendly only when angering it would lose (owner 2026-10-31).

Owner 2026-10-31, asked whether a town fight's ball attacks avoid friendly
monsters in the blast: 「敵対させたあと勝てるかで判断。勝てるなら巻き込んで良い。」
The judgement is the town hunt's duel projection on a friendly
(``_town_friendly_unbeatable``, owner 2026-10-31 「勝てない時は攻撃しない」).

Recorded board: n1-c life-067 2026-10-31 19:26 (D49), turn 157197, Outpost --
the Lv8 Magic-Eater at (35, 108) beside わめくキチガイ at (36, 107), frozen in
tests/fixtures/town-ball-friendly-20261031.json.gz
(tests/extract_town_ball_friendly_1031.py).  No recorded town board of the
viewing Magic-Eater has a friendly within two cells of an adjacent hostile
(the 73 n1-c snapshot rings under C:/hengband-backups/pdca/captures, scanned
2026-11-01), so the friendly is placed on the recorded map.

DECLARED CONSTRUCTED: the absorbed wand list (an empty Magic Missile and a
Fire Balls row, names from BaseitemDefinitions.jsonc) with the executor's
matching ``_magic_eater_wand_charges`` 0 (or, for the carried-wand case, no
absorbed list and the pack's Disarming wand in slot g made a known Fire Balls
wand with 3 charges); a friendly monster on the recorded
map's floor cell (37, 107), one step from the impact cell, so inside the
radius-2 ball (cmd-zapwand.cpp:57, range-calc.cpp:267-290): すずめ (1 hp,
beatable) or 農夫『マゴット』 (350 hp, not beatable at 129 hp).  Replies to the
posted keys are constructed from the game's prompts (cmd-magiceat.cpp,
get_aim_dir).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.me_device_attacks import DEVICE_REASON
from hengbot.me_ranged_first import TORCH_REASON, WAND_REASON
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_me_device_attacks import (
    EMPTY_MISSILE_ROW, power_list, power_screen, row)
from tests.test_magic_eater_o3 import prompt


FIXTURE = Path(__file__).with_name("fixtures") / "town-ball-friendly-20261031.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
FRIENDLY_CELL = (37, 107)
OUTSIDE_CELL = (33, 106)   # recorded floor, game distance 3 from the impact
SPARROW, MAGGOT = (3, "すずめ"), (8, "農夫『マゴット』")
FIRE_BALL_KEY = "mBw1"   # wand sval 22 is I2A(22) 'w'; the target is south-west
CARRIED_SLOT = "g"


def board(friendly, *, carried_ball=False, cell=FRIENDLY_CELL):
    raw = copy.deepcopy(CASE["board"])
    lunatic = raw["visible_monsters"][0]
    race_id, name = friendly
    index = lunatic["index"] + 1
    raw["visible_monsters"].append(dict(
        lunatic, index=index, race_id=race_id, name=name,
        y=cell[0], x=cell[1], friendly=True))
    # The board's grid cells carry the monster index (sparse "m" cell).
    raw["grid_map"]["cells"].append({"m": index, "y": cell[0], "x": cell[1]})
    raw["_magic_eater_wand_charges"] = 0
    if carried_ball:
        # The pack's Disarming wand (slot g) becomes a known Fire Balls wand.
        wand = next(item for item in raw["inventory"] if item["slot"] == CARRIED_SLOT)
        wand.update(sval=22, charges=3, name="ファイア・ボールの魔法棒 (3回分)")
    else:
        raw["_magic_eater_power_list"] = power_list(
            "wand", EMPTY_MISSILE_ROW, row("ファイア・ボール", 20, current=1, count=1))
    return raw


class TownBallFriendlyTest(nokey.PostedKey):
    def decide(self, friendly, **options):
        raw = board(friendly, **options)
        policy = loops.new_policy({**CASE, "boards": [raw]}, CASE["skill"],
                                  record=CASE["sequence"], monraces=CASE["monraces"])
        return policy, raw, loops.decide(policy, raw)

    def test_recorded_board_places_the_friendly_in_the_ball(self):
        raw = board(SPARROW)
        player, (lunatic, friendly) = raw["player"], raw["visible_monsters"]
        self.assertEqual((player["y"], player["x"], player["class_id"]), (35, 108, 16))
        self.assertEqual((lunatic["y"], lunatic["x"], lunatic["friendly"]), (36, 107, False))
        self.assertTrue(raw["floor"]["in_town"])
        self.assertTrue(friendly["friendly"])

    def test_beatable_friendly_in_the_blast_still_gets_the_ball(self):
        policy, raw, key = self.decide(SPARROW)
        self.assertEqual((key, policy.last_reason), (FIRE_BALL_KEY, DEVICE_REASON))
        game, _ = self.post_power(policy, raw, key)
        self.assertEqual(game.accepted, ["m", "B", "w", "1"])

    def test_unbeatable_friendly_in_the_blast_keeps_the_single_target_answer(self):
        policy, raw, key = self.decide(MAGGOT)
        # No ball; the chooser's next rung (a spare lit torch) answers instead.
        self.assertEqual(policy.last_reason, TORCH_REASON, key)
        self.assertFalse(key.startswith("m"), key)
        self.post(policy, raw, key)

    def test_unbeatable_friendly_outside_the_blast_does_not_hold_the_ball(self):
        policy, _raw, key = self.decide(MAGGOT, cell=OUTSIDE_CELL)
        self.assertEqual((key, policy.last_reason), (FIRE_BALL_KEY, DEVICE_REASON))

    def test_carried_ball_wand_follows_the_same_rule(self):
        # A carried wand is the same wand_effect (zapwand-execution.cpp:102).
        policy, raw, key = self.decide(SPARROW, carried_ball=True)
        self.assertEqual(policy.last_reason, WAND_REASON, key)
        self.assertIn(CARRIED_SLOT, key)
        self.post(policy, raw, key)
        policy, raw, key = self.decide(MAGGOT, carried_ball=True)
        self.assertEqual(policy.last_reason, TORCH_REASON, key)
        self.post(policy, raw, key)

    def post_power(self, policy, raw, key):
        """The absorbed power through the executor's prompts (cmd-magiceat.cpp)."""
        game = nokey.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = nokey.command_screen(raw["turn"])
        game.screens = [
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            power_screen("wand", [("p", "マジック・ミサイル", 0, 3, 5),
                                  ("w", "ファイア・ボール", 1, 1, 20)]),
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
        return game, port


if __name__ == "__main__":
    unittest.main()
