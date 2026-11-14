"""A blind Magic-Eater uses its absorbed attack powers on a hostile whose position it knows.

Owner 2026-11-08, question 「盲目の時に、取り込んだ攻撃の力を使うようにしますか？」,
answer 「使う」: 「盲目でも、テレパシーや感知で位置が分かる敵、隣で殴ってくる敵には
取り込んだ攻撃の力を使う。位置が分からなければ今のまま使わない。」

The game: ``m`` is refused only while confused (cmd-magiceat.cpp
do_cmd_magic_eater, cmd_limit_confused; input-key-processor.cpp asks no
sight), get_aim_dir takes a direction while blind (target-getter.cpp), and a
blind board lists only the monsters the game perceives (bot-json-output.cpp
``ml``: telepathy or detection).

Source: tests/fixtures/death-n1c-156-1107.json.gz, the Lv20 Magic-Eater's blind
boards on 迷宮10階 (test_n1c_156_blind_maze_recorded): punched (1044327) and
clubbed (1044354) from the unknown cell (8,21) west of it.
DECLARED CONSTRUCTED: the attacker at (8,21) is put on the board as a monster
the game perceives (telepathy), or on the last sighted board 1044316 (the
player not blind there) so it is remembered; its race is n1-c life-085's race
1402 (d57).  DECLARED RECONSTRUCTED: the displayed wand list (Fire Bolts 5/5,
10% fail), as the death report's list was reconstructed in the 156 tests.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot import me_power_success
from hengbot.me_device_attacks import DEVICE_REASON
from hengbot.model import parse_snapshot
from hengbot.magic_eater import MISSILE_REASON
from tests import test_me_mining_death_recorded as mining_death
from tests import test_n1c_156_blind_maze_recorded as maze
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen


RACE = "1402"
ATTACKER = (8, 21)            # the unknown cell west of the stair the blows came from
SIGHTED = 1044316             # the board made sighted for the remembered attacker
FIRE_BOLT_ROW = {"name": "ファイア・ボルト", "current": 5, "max": 5, "fail": 10, "success": 90}
FIRE_BOLT_WEST = "mBs4"       # m, [B] wand, I2A(18), direction 4
MISSILE_WEST = "mBp4"         # m, [B] wand, I2A(15), direction 4
STRIKE_WEST = "+4"
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
DIRECTION_PROMPT = "方向 ('*'でターゲット選択, ESCで中断)? "


def new_policy(rows=(FIRE_BOLT_ROW,)):
    policy = d57.loops.new_policy(maze.CASE, d57.CASE_084["skill"],
                                  monraces={RACE: d57.CASE_085["monraces"][RACE]})
    policy._me_device_lists = ({"wand": (maze.LIST_TURN, tuple(dict(row) for row in rows))}
                               if rows else {})
    if rows:
        # The reconstructed list is the one shown on these boards' inputs (me_power_success
        # reads a shown rate on the inputs it was shown on, else the game's formula: 27% for
        # Fire Bolts at this Lv20 character's INT 17).
        me_power_success.observe_list_board(policy, "wand", parse_snapshot(
            maze.boards()[0], policy._monrace_knowledge))
    return policy


def with_attacker(raw):
    """The board with the attacker at (8,21) as a monster the game perceives."""
    raw = copy.deepcopy(raw)
    template = next(monster for board in d57.CASE_085["boards"]
                    for monster in board["visible_monsters"] if str(monster["race_id"]) == RACE)
    raw["visible_monsters"] = [dict(copy.deepcopy(template), index=777, y=ATTACKER[0],
                                    x=ATTACKER[1], health="unhurt", asleep=False)]
    return raw


def drive(policy, until, edit=lambda raw: raw):
    """The recorded boards up to ``until``; ``edit`` changes each board first.
    Each answer is (board, key, reason); ``policy`` keeps the last decision's."""
    answers = {}
    for raw in maze.boards():
        if raw["turn"] > until:
            break
        raw = edit(raw)
        key = d57.loops.decide(policy, raw)
        answers[raw["turn"]] = (raw, key, policy.last_reason)
        policy.confirm_key_posted(key)
    return answers


def perceived_at(turn, *, afraid=False):
    def edit(raw):
        raw["player"]["status"]["afraid"] = afraid
        return with_attacker(raw) if raw["turn"] == turn else raw
    return edit


def remembered(raw):
    """The attacker seen beside the player on the last sighted board only."""
    if raw["turn"] != SIGHTED:
        return raw
    raw = with_attacker(raw)
    raw["player"]["status"]["blind"] = False
    return raw


class PerceivedAttackerTest(d57.PostedDeathKey):
    """Telepathy or detection shows the attacker beside the blind player."""

    post_power = mining_death.MagicEaterMiningDeathRecordedTest.post

    def test_the_absorbed_bolt_answers_it_through_the_executor(self):
        policy = new_policy()
        raw, key, reason = drive(policy, maze.PUNCHED, perceived_at(maze.PUNCHED))[maze.PUNCHED]
        self.assertTrue(raw["player"]["status"]["blind"])
        self.assertEqual((key, reason), (FIRE_BOLT_WEST, DEVICE_REASON))
        game, _ = self.post_power(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("wand", [("s", "ファイア・ボルト", 5, 5, 10)]),
            prompt(DIRECTION_PROMPT, "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["m", "B", "s", "4"])

    def test_afraid_it_fires_the_absorbed_magic_missile(self):
        # Fear refuses the blow (cmd-attack.cpp); no list was displayed, so the
        # absorbed Magic Missile is the answer (me_ranged_first.applies).
        policy = new_policy(rows=())
        raw, key, reason = drive(policy, maze.PUNCHED,
                                 perceived_at(maze.PUNCHED, afraid=True))[maze.PUNCHED]
        self.assertEqual((key, reason), (MISSILE_WEST, MISSILE_REASON))
        game, _ = self.post_power(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("wand", [("p", "マジック・ミサイル", 3, 3, 5)]),
            prompt(DIRECTION_PROMPT, "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["m", "B", "p", "4"])

    def test_the_carried_torch_keeps_its_sight_rule(self):
        # Sighted, the same attacker draws a thrown torch (the pack's spare torches).
        sighted = drive(new_policy(rows=()), SIGHTED, lambda raw: remembered(raw))[SIGHTED]
        self.assertEqual(sighted[1][:1], "v", sighted[2])
        # Blind, the torch is not thrown; the blow answers (melee outscores the missile).
        _raw, key, reason = drive(new_policy(rows=()), maze.PUNCHED,
                                  perceived_at(maze.PUNCHED))[maze.PUNCHED]
        self.assertEqual((key, reason), ("4", "melee"))

    def test_confused_it_uses_no_power(self):
        def edit(raw):
            raw = perceived_at(maze.PUNCHED)(raw)
            raw["player"]["status"]["confused"] = raw["turn"] == maze.PUNCHED
            return raw
        _raw, key, _reason = drive(new_policy(), maze.PUNCHED, edit)[maze.PUNCHED]
        self.assertFalse(key.startswith("m"), key)


class RememberedAttackerTest(d57.PostedDeathKey):
    """The attacker was seen beside the player before the blindness and keeps hitting."""

    post_power = mining_death.MagicEaterMiningDeathRecordedTest.post

    def test_the_return_walks_strike_and_the_emergency_strike_cast_the_bolt(self):
        policy = new_policy()
        answers = drive(policy, maze.CLUBBED, remembered)
        for turn in (maze.PUNCHED, maze.CLUBBED):
            raw, key, reason = answers[turn]
            self.assertTrue(raw["player"]["status"]["blind"], turn)
            self.assertEqual(raw["visible_monsters"], [], turn)
            self.assertEqual((key, reason), (FIRE_BOLT_WEST, DEVICE_REASON), turn)
        raw, key, _reason = answers[maze.CLUBBED]
        game, _ = self.post_power(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("wand", [("s", "ファイア・ボルト", 5, 5, 10)]),
            prompt(DIRECTION_PROMPT, "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["m", "B", "s", "4"])

    def test_hurt_by_a_spell_and_not_a_blow_the_cell_is_struck(self):
        # DECLARED CONSTRUCTED: the punched board's HP loss came with an unseen
        # spell, not a blow, while the recall is active: the recall wait's blind
        # strike (unseen-recall:blind-strike) strikes the remembered cell, and the
        # power waits for a blow (「隣で殴ってくる敵」).
        def edit(raw):
            raw = remembered(raw)
            if raw["turn"] == maze.PUNCHED:
                raw["messages"] = ["何かが呪文を唱えた。"]
                raw["player"]["recalling"] = True
            return raw
        _raw, key, reason = drive(new_policy(), maze.PUNCHED, edit)[maze.PUNCHED]
        self.assertEqual((key, reason), (STRIKE_WEST, "unseen-recall:blind-strike"))


class UnknownPositionTest(unittest.TestCase):
    """No attacker perceived or remembered: the strike stays (今のまま使わない)."""

    def test_the_recorded_strikes_are_kept(self):
        answers = drive(new_policy(), maze.CLUBBED)
        self.assertEqual(answers[maze.PUNCHED][1:], (STRIKE_WEST, "unseen:strike-return"))
        self.assertEqual(answers[maze.CLUBBED][1:], (STRIKE_WEST, "emergency:unseen-strike"))


if __name__ == "__main__":
    unittest.main()
