"""The Magic-Eater attacks with its absorbed attack powers (owner 2026-10-31).

Recorded n1-c Magic-Eater boards on Yeek cave 1F (2026-10-30), from
tests/fixtures/me-mining-death-20261030.json.gz (see
test_me_mining_death_recorded): life 8 at turn 805349 (melee rung, an
insect swarm and a small kobold adjacent) and life 11 at turn 187358
(emergency cornered attack at 13 hp).

DECLARED CONSTRUCTED: the absorbed-device lists (``_magic_eater_power_list``
rows: names from BaseitemDefinitions.jsonc, charges and fail percentages
chosen for each case); on life 8 the insect swarm is removed so the small
kobold (IM_POIS, 14 hp) is the target; on life 11 the cornering mouse is
replaced by that recorded small kobold race.  Replies to posted keys are
constructed from the game's prompts (cmd-magiceat.cpp, get_aim_dir).
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot.magic_eater import MISSILE_REASON
from hengbot.me_device_attacks import DEVICE_REASON, observe_lists
from hengbot.me_ranged_first import TORCH_REASON
from hengbot.model import parse_snapshot
from tests import test_me_mining_death_recorded as mining
from tests.test_magic_eater_o3 import prompt

POWER_PROMPT = "('*'で一覧, ESCで中断) どの魔力を使いますか？"


def row(name, fail, *, current=None, charging=None, count=1):
    value = {"name": name, "fail": fail, "success": 100 - fail, "max": count}
    if charging is None:
        value["current"] = current
    else:
        value["charging"] = charging
    return value


def power_list(kind, *rows):
    return {"kind": kind, "rows": list(rows)}


def power_screen(kind, letter_rows):
    """cmd-magiceat.cpp's list under the power prompt (always_show_list)."""
    screen = prompt(POWER_PROMPT, "spell")
    screen["lines"][1] = ("                           {0} 失率".format(
        "  状態  " if kind == "rod" else "使用回数"))
    for index, (letter, name, first, second, fail) in enumerate(letter_rows):
        if kind == "rod":
            text = f"{letter}) {name:<22} 充填:{first:2}/{second:2}{fail:3}%"
        else:
            text = f"{letter}) {name:<22}    {first:2}/{second:2} {fail:3}%"
        screen["lines"][2 + index] = text
    return screen


MISSILE_ROW = row("マジック・ミサイル", 5, current=3, count=3)
EMPTY_MISSILE_ROW = row("マジック・ミサイル", 5, current=0, count=3)


def _recorded(name):
    # Reuse the recorded test's loaders without importing its test class.
    return getattr(mining.MagicEaterMiningDeathRecordedTest, name)


class MagicEaterDeviceAttackTest(mining.harness.ProductionHarness):
    setUpClass = classmethod(_recorded("setUpClass").__func__)
    raw = _recorded("raw")
    policy = _recorded("policy")
    choose = _recorded("choose")
    post = _recorded("post")
    adjacent_direction = _recorded("adjacent_direction")

    def kobold_board(self, decided_list):
        raw = self.raw("life-008", 805349)
        raw["visible_monsters"] = [m for m in raw["visible_monsters"] if m["race_id"] == 29]
        raw["_magic_eater_power_list"] = decided_list
        return raw

    def decide(self, life, raw, *earlier_lists):
        policy = self.policy(life, raw)
        for listed in earlier_lists:
            # An earlier board on which the game displayed that list.
            earlier = dict(raw, _magic_eater_power_list=listed, turn=raw["turn"] - 1)
            observe_lists(policy, parse_snapshot(earlier, policy._monrace_knowledge))
        key = self.choose(policy, raw)
        return policy, key

    def test_absorbed_fire_bolt_rod_beats_magic_missile(self):
        raw = self.kobold_board(power_list("rod", row("ファイア・ボルト", 30, charging=0)))
        policy, key = self.decide("life-008", raw, power_list("wand", MISSILE_ROW))
        direction = self.adjacent_direction(policy, raw, "life-008").pop()
        # rod sval 22 is I2A(22) == 'w'.
        self.assertEqual((key, policy.last_reason), ("mCw" + direction, DEVICE_REASON))
        game, port = self.post(policy, raw, key, [
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            power_screen("rod", [("w", "ファイア・ボルト", 0, 1, 30)]),
            prompt("方向?", "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["m", "C", "w", direction])
        listed = port.last_result.board["_magic_eater_power_list"]
        self.assertEqual((listed["kind"], listed["rows"][0]["name"]), ("rod", "ファイア・ボルト"))

    def test_known_poison_immunity_prefers_the_frost_bolt(self):
        wands = power_list("wand", MISSILE_ROW, row("悪臭雲", 10, current=5, count=5),
                           row("アイス・ボルト", 25, current=2, count=2))
        raw = self.kobold_board(wands)
        policy, key = self.decide("life-008", raw)
        direction = self.adjacent_direction(policy, raw, "life-008").pop()
        # Small kobold IM_POIS: Stinking Cloud 14 / 9; Frost Bolt 6d8 capped at 14 hp.
        self.assertEqual((key, policy.last_reason), ("mBt" + direction, DEVICE_REASON))
        # Without the resistance the cheaper unresisted ball would win.
        policy = self.policy("life-008", raw)
        races = dict(policy._monrace_knowledge)
        races[29] = races[29].__class__(**{**races[29].__dict__,
                                            "flags": races[29].flags - {"IM_POIS"}})
        policy._monrace_knowledge = races
        self.assertEqual(self.choose(policy, raw), "mBo" + direction)

    def test_adjacent_ball_is_allowed_because_it_spares_the_player(self):
        # effect-player.cpp check_continue_player_effect: the player's own
        # ball never damages the player, so a radius-2 ball on an adjacent
        # target is chosen (also covers the full wand sequence and the aim).
        raw = self.kobold_board(power_list("wand", EMPTY_MISSILE_ROW,
                                           row("サンダー・ボール", 20, current=1, count=1)))
        policy, key = self.decide("life-008", raw)
        direction = self.adjacent_direction(policy, raw, "life-008").pop()
        self.assertEqual((key, policy.last_reason), ("mBv" + direction, DEVICE_REASON))
        game, _ = self.post(policy, raw, key, [
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            power_screen("wand", [("p", "マジック・ミサイル", 0, 3, 5),
                                  ("v", "サンダー・ボール", 1, 1, 20)]),
            prompt("方向?", "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["m", "B", "v", direction])

    def test_emergency_cornered_attack_uses_the_power_staff(self):
        raw = self.raw("life-011", 187358)
        for monster in raw["visible_monsters"]:
            monster.update(race_id=29, name="スモール・コボルド")
        raw["_magic_eater_power_list"] = power_list("staff", row("力", 20, current=1, count=1))
        policy, key = self.decide("life-011", raw, power_list("wand", MISSILE_ROW))
        # Staff of Power (sval 25, 'z') has no direction prompt.
        self.assertEqual((key, policy.last_reason), ("mAz", DEVICE_REASON))
        game, _ = self.post(policy, raw, key, [
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            power_screen("staff", [("z", "力", 1, 1, 20)])])
        self.assertEqual(game.accepted, ["m", "A", "z"])

    def test_without_charges_magic_missile_then_torch_answer(self):
        raw = self.kobold_board(power_list("rod", row("ファイア・ボルト", 30, charging=1)))
        policy, key = self.decide("life-008", raw, power_list(
            "wand", MISSILE_ROW, row("アイス・ボルト", 25, current=0, count=2)))
        self.assertEqual(policy.last_reason, MISSILE_REASON)
        self.assertTrue(key.startswith("mBp"), key)
        # No missile either (observed empty) and no carried wand: a torch.
        raw["_magic_eater_wand_charges"] = 0
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] != 65]
        policy, key = self.decide("life-008", raw, power_list(
            "wand", EMPTY_MISSILE_ROW, row("アイス・ボルト", 25, current=0, count=2)))
        self.assertEqual(policy.last_reason, TORCH_REASON)
        self.assertEqual(key[0], "v")

    def test_stale_rod_closes_the_prompt_turn_free_and_magic_missile_follows(self):
        raw = self.kobold_board(power_list("rod", row("ファイア・ボルト", 30, charging=0)))
        policy, key = self.decide("life-008", raw, power_list("wand", MISSILE_ROW))
        self.assertTrue(key.startswith("mCw"), key)
        # The game's list says the only absorbed rod is still charging.
        game, port = self.post(policy, raw, key, [
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            power_screen("rod", [("w", "ファイア・ボルト", 1, 1, 30)])])
        self.assertEqual(game.accepted, ["m", "C", "\x1b"])
        board = port.last_result.board
        self.assertEqual(board["_magic_eater_power_list"]["rows"][0]["charging"], 1)
        board.pop("_magic_eater_wand_charges", None)
        self.assertTrue(self.choose(policy, board).startswith("mBp"))
        self.assertEqual(policy.last_reason, MISSILE_REASON)

    def test_quest_one_keeps_its_torch_strategy(self):
        raw = self.kobold_board(power_list("rod", row("ファイア・ボルト", 30, charging=0)))
        raw["floor"]["quest_id"] = 1
        policy = self.policy("life-008", raw)
        observe_lists(policy, parse_snapshot(raw, policy._monrace_knowledge))
        board = parse_snapshot(raw, policy._monrace_knowledge)
        from hengbot import me_ranged_first
        # D17 owns quest 1 (torch first); the generic D21 chooser stays off.
        self.assertIsNone(me_ranged_first.attack_key(policy, board, board.visible_monsters[0]))
        board = parse_snapshot(dict(raw, floor=dict(raw["floor"], quest_id=0)),
                               policy._monrace_knowledge)
        self.assertTrue(me_ranged_first.attack_key(
            policy, board, board.visible_monsters[0]).startswith("mCw"))


if __name__ == "__main__":
    unittest.main()
