"""Recorded replay of the n1-a life-504 death of 2026-11-10 (鉄獄24階, random quest 41).

Source: tests/fixtures/n1a-504-blind-1110.json.gz
(tests/extract_n1a_504_blind_rest_fixture.py): the Lv26-27 zombie warrior's boards of turns
895901-897259 (535 max HP at the end), the remembered terrain and the recorded decision rows;
the analysis is C:/hengband-backups/pdca/captures/n1a-504-death-1110/REPORT.txt.

A gas trap (「黒いガスに包み込まれた！」, trap.cpp TrapType::BLIND, 25-74 ticks) blinded it at
896684 with no cure carried.  It hunted, searched, explored and tried to read an Identify
scroll fifteen times blind; a thief stole a rod and fled (「泥棒は笑って逃げた！」); it walked
into a dart trap twice, a poison trap and the TY_CURSE trap, whose summons it fought blind,
walking toward an up-stair eleven cells away while bitten, to its death.

Owner rules: 「盲目で周りが分からない時は分からない隣のマスにも攻撃する。…敵がいなくなったら
目が見えるまで休む。」 (2026-11-07) and 「治してもまた盲目なら覚えている敵を攻撃。階段が隣など
とても近くにある場合を除き徒歩での逃走は絶対に間に合わない。」 (2026-11-03).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import REST_MACRO
from hengbot.status_cure import DUNGEON_WAIT_SIGHT_REASON
from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "n1a-504-blind-1110.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

# The teleport landing (rested, sighted), the gas trap, the thief, the last board before
# the TY_CURSE trap, and the death.
LANDING, GAS_TRAP, THIEF, LAST_QUIET, DEATH = 895901, 896684, 896723, 896987, 897259


def new_policy(first):
    case = dict(CASE, boards=[raw for raw in CASE["boards"] if raw["turn"] >= first])
    policy = d57.loops.new_policy(case, CASE["skill"], monraces=CASE["monraces"])
    terrain = CASE["terrain"]
    for name in ("known", "marked", "floor", "wall", "door", "rubble"):
        getattr(policy, f"_remembered_{name}_t").update(
            tuple(cell) for cell in terrain[f"{name}_t"])
    policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
    return policy


def boards(first, last):
    return [copy.deepcopy(raw) for raw in CASE["boards"] if first <= raw["turn"] <= last]


def decide(policy, raw):
    """``choose_key`` on the board; the skill list the level-up board asks for is
    answered from the fixture's skill row at the board's level (the game's reply)."""
    board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    key = str(policy.choose_key(board))
    if key.startswith("~f"):
        skill = CASE["skill"]
        policy.consume_skill_knowledge(dict(
            copy.deepcopy(skill), turn=raw["turn"],
            player=dict(skill["player"], level=raw["player"]["level"])))
        key = str(policy.choose_key(board))
    return key


def drive(first, last, policy=None):
    policy = new_policy(first) if policy is None else policy
    answers = {}
    for raw in boards(first, last):
        key = decide(policy, raw)
        answers[raw["turn"]] = (key, policy.last_reason)
        policy.confirm_key_posted(key)
    return policy, answers


class N1a504BlindRecordedTest(unittest.TestCase):
    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        rows = {raw["turn"]: raw for raw in CASE["boards"]}
        self.assertIn("黒いガスに包み込まれた！", rows[GAS_TRAP]["messages"])
        self.assertIn("泥棒は笑って逃げた！", rows[THIEF]["messages"])
        for turn, raw in rows.items():
            if GAS_TRAP <= turn <= DEATH:
                self.assertTrue(raw["player"]["status"]["blind"], turn)
            if turn >= LANDING:
                names = " ".join(item["name"] for item in raw["inventory"])
                self.assertNotIn("致命傷の治癒", names, turn)
                self.assertNotIn("体力回復", names, turn)
        blind_walk = [row["reason"] for row in CASE["decisions"]
                      if GAS_TRAP <= row["turn"] <= LAST_QUIET]
        self.assertIn("hunt:detected-target", blind_walk)
        self.assertIn("explore", blind_walk)
        # Each read refused with 「目が見えない。」 and no turn spent, so re-posted.
        self.assertEqual(blind_walk.count("identify:pack-pressure"), 15)
        self.assertEqual(recorded[897005], ("emergency:seek-upstairs", "9"))

    def test_blind_with_no_attacker_rests_until_it_sees(self):
        # D1: every blind board from the gas trap to the TY_CURSE trap had no hit and no
        # hostile in sight; the 11-07 rest takes them all, the thief's board included.
        _policy, answers = drive(LANDING, LAST_QUIET)
        blind = {turn: answer for turn, answer in answers.items() if GAS_TRAP <= turn}
        self.assertTrue(blind)
        for turn, answer in blind.items():
            self.assertEqual(answer, (REST_MACRO, DUNGEON_WAIT_SIGHT_REASON), turn)

    def test_a_fled_thief_leaves_no_attacker(self):
        # D1b: 「何かに触られた。」 latched the floor's attacker; 「泥棒は笑って逃げた！」 is the
        # thief's teleport away (monster-attack-player.cpp:526-527), so the board after it rests.
        policy, answers = drive(LANDING, THIEF)
        self.assertIsNone(policy._blind_attacker_floor)
        for turn in (THIEF, 896733):
            policy, answers = drive(LANDING, turn)
            self.assertEqual(answers[turn], (REST_MACRO, DUNGEON_WAIT_SIGHT_REASON), turn)

    def test_blind_fight_reads_no_scroll(self):
        # D1c: the blind fight's quiet boards (no adjacent target) fell to the pack-pressure
        # identify, which reads an Identify scroll: cmd_limit_blind refuses it, no turn spent.
        _policy, answers = drive(LANDING, DEATH)
        for turn, (key, reason) in answers.items():
            if turn >= GAS_TRAP:
                self.assertNotEqual(reason, "identify:pack-pressure", (turn, key))
                self.assertFalse(key.startswith("r"), (turn, key, reason))


if __name__ == "__main__":
    unittest.main()
