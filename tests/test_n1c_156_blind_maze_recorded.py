"""The n1-c life-156 death of 2026-11-07 23:08 in the Labyrinth (迷宮12階 -> 10階).

Source: tests/fixtures/death-n1c-156-1107.json.gz
(tests/extract_n1c_156_blind_maze_fixture.py): the Lv20 Magic-Eater's last
boards (turns 1044263-1044440, 迷宮10階) and the recorded decision rows from
its last sighted board on 12F (decisions 2686-2772).

A ヴラスタ (BITE:BLIND) blinded it on 12F.  The Labyrinth is MAZE + FORGET:
every move forgets the floor (player-move.cpp ``wiz_dark``), and a blind
player's board is not redrawn, so the board beside it was empty.  It drank its
Cure Critical Wounds into the next re-blinding bite, again and again: each cure
healed more than the bite took (HP 196 -> 207 -> 225 -> 229), so no HP loss
showed a melee hit and the re-blind latch (status_cure) never held.  With the
ヴラスタ dead it walked its latched return blind, took an up-shaft to 10F and
stood blind on the down staircase it landed on, its board forgotten but for the
walls beside it, punched and clubbed from the one unknown cell (8,21) while it
waited (``return:wait``, ``emergency:wait``) from HP 171 to death.  Its
absorbed Cure Light Wounds staff (the power list: 7 charges) cures blindness
(spells-status.cpp cure_light_wounds) and the ``m`` command refuses only
confusion (cmd-magiceat.cpp do_cmd_magic_eater), yet it was never cast.

Owner 2026-11-07: 「盲目で周りが分からない時は分からない隣のマスにも攻撃する。
取り込んだ軽傷の治癒で盲目を治す。足元の下り階段を最後の逃げ道に入れる。
敵がいなくなったら目が見えるまで休む。」

DECLARED RECONSTRUCTED: the capture's skill row is not in the copies; the
policy reads d57's n1-c life-084 skill row (same class) for the proficiency
knowledge choose_key asks for.  The displayed staff list (cast only when shown)
is the one row the death report names, 軽傷の治癒 7/7.
DECLARED CONSTRUCTED: the 12F re-blinding scenes are the recorded 10F board
with the 12F messages, HP and pack, as each test states.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position
from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1c-156-1107.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

STAIR = Position(8, 22)       # the down staircase the up-shaft landed on
UNKNOWN = Position(8, 21)     # the one neighbour the forgotten board does not show
STRIKE_WEST = "+4"
PUNCHED, CLUBBED = 1044327, 1044354   # return:wait / emergency:wait, hit from (8,21)
QUIET = (1044293, 1044302, 1044316)   # blind, nothing hits: return:wait
VLASTA_BITE = ["ヴラスタに噛まれた。", "目が見えなくなってしまった！", "噛まれた。"]
CURED_AND_REBLINDED = ["まだ 8服の 致命傷の治癒の薬を持っている。", "とても気分が良くなった。",
                       "やっと目が見えるようになった。", "ヴラスタに噛まれた。",
                       "目が見えなくなってしまった！", "噛まれた。", "何かに噛まれた。"]


def new_policy():
    return d57.loops.new_policy(CASE, d57.CASE_084["skill"], monraces={})


def boards():
    return copy.deepcopy(CASE["boards"])


def recorded():
    return {row["turn"]: (row["reason"], row["key"]) for row in CASE["decisions"]}


def with_cure_potions(raw, count=9):
    """The board's pack with the Cure Critical Wounds the 12F scenes still carried."""
    raw = copy.deepcopy(raw)
    potion = copy.deepcopy(next(item for item in raw["inventory"] if item["tval"] == 75))
    potion.update(name=f"{count}服の致命傷の治癒の薬", sval=36, count=count, slot="a")
    raw["inventory"] = [potion] + [item for item in raw["inventory"] if item["slot"] != "a"]
    return raw


def scene(raw, *, turn, hp, messages, cures=None):
    """DECLARED CONSTRUCTED: the 10F board with a 12F re-blinding scene's facts."""
    raw = with_cure_potions(raw, cures) if cures else copy.deepcopy(raw)
    raw.update(turn=turn, messages=list(messages))
    raw["player"]["hp"] = hp
    return raw


class RecordedRowsTest(unittest.TestCase):
    def test_the_recorded_death(self):
        rows = recorded()
        self.assertEqual(rows[PUNCHED], ("return:wait", "5"))
        self.assertEqual(rows[CLUBBED], ("emergency:wait", "5"))
        decisions = {row["turn"]: row for row in CASE["decisions"]}
        self.assertEqual([decisions[t]["hp"] for t in (1043240, 1043250, 1043256, 1043263)],
                         [196, 207, 225, 229])
        self.assertEqual(decisions[CLUBBED]["down_stairs"], [[8, 22]])
        board = {raw["turn"]: raw for raw in CASE["boards"]}[CLUBBED]
        self.assertTrue(board["player"]["status"]["blind"])
        self.assertEqual((board["player"]["y"], board["player"]["x"]), (8, 22))


class UnknownNeighbourStrikeRecordedTest(d57.PostedDeathKey):
    """Item 1: blind on a forgotten board, an unknown neighbour is struck."""

    def test_blows_from_the_unknown_cell_are_struck_back(self):
        policy, answers = new_policy(), {}
        for raw in boards():
            key = d57.loops.decide(policy, raw)
            answers[raw["turn"]] = (key, policy.last_reason)
            if raw["turn"] == CLUBBED:
                self.post(policy, raw, key)
            policy.confirm_key_posted(key)
        self.assertEqual(answers[PUNCHED], (STRIKE_WEST, "unseen:strike-return"))
        self.assertEqual(answers[CLUBBED], (STRIKE_WEST, "emergency:unseen-strike"))
        hit = [turn for turn, (reason, _key) in recorded().items()
               if turn >= PUNCHED and reason in ("return:wait", "emergency:wait")]
        for turn in hit:
            self.assertNotEqual(answers[turn][0], "5", (turn, answers[turn]))

    def test_cure_healing_more_than_the_bite_still_latches_the_blindness(self):
        # 12F, decisions 2699-2701: a cure, then the next bite re-blinds it on a
        # board whose HP is above the last one (196 -> 207).
        base = boards()[5]
        policy = new_policy()
        quiet = scene(base, turn=1043230, hp=210, messages=[], cures=9)
        d57.loops.decide(policy, quiet)
        policy.confirm_key_posted("5")
        bitten = scene(base, turn=1043240, hp=196, messages=VLASTA_BITE, cures=9)
        key = d57.loops.decide(policy, bitten)
        self.assertEqual(key[:1], "q", policy.last_reason)
        policy.confirm_key_posted(key)
        reblinded = scene(base, turn=1043250, hp=207, messages=CURED_AND_REBLINDED, cures=8)
        key = d57.loops.decide(policy, reblinded)
        self.assertEqual((key, policy.last_reason), (STRIKE_WEST, "blind:fight-through"))


if __name__ == "__main__":
    unittest.main()
