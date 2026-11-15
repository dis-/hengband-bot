"""Quest 25 on n1-c life-211 (2026-11-15 14:01): the won quest's exit walk stuck in the Ipsissimus' pen, recorded.

Right after main 138f619e1 was deployed, the sweep walked toward the Nexus quylthulg; the quylthulg
teleported the player into the Ipsissimus' pen [7,17] (「ネクサス・クイルスルグにテレポートさせられた。」,
turn 4077527), the ball the plan had keyed killed it and the quest was won (「クエストを達成した！」,
4077532).  The loot sweep picked up the pen's three items ([7,17]-[9,17]); then the exit walk
(quest_navigator ``_exit``) held '5' under ``quest:blocked:exit`` on [9,17] until the loop guard stopped
the bot (14:01:36, 14:01:43) and the runner, on the third stop (14:01:50), replaced the character.

What it waited for: a dry way out.  The pen is ringed by deep water and walls (the map's 『I』 column
17, rows 7-9: deep water [6,16]-[9,16] and [6,17], walls east and south), and the exit walk's map
(``_static_walkable``) lets deep water in only on a navigator that allows it, which Q25's does not.
The game drowns only an overweight player in deep water (hp-mp-processor.cpp process_player_hp_mp:
calc_inventory_weight > calc_weight_limit, randint1(level) a turn), and the Q25 plan's own walks
already cross it when nothing dry leads (quest_plan_base ``_least_exposed_walk``).

The fix (quest_navigator ``_wet_path``): with no dry way to the exit, the exit walk goes over deep
water too.  None of the sealed-pocket pieces (quest25_pocket) took part: the battle was over (phase 11).

Recorded: tests/fixtures/n1c-211-q25-pen-exit-1115.json.gz
(tests/extract_n1c_211_q25_pen_exit_1115_fixture.py): the boards from the step before the teleport to
the first holds, every decision of the three stops from 14:01:29, the battle record left.  A fresh
policy restores the record through the real path and decides the recorded boards through the public
``choose_key``; a step is posted through the production executor.

DECLARED RECONSTRUCTED: the remembered magic-eater lists (tests/test_n1c_208_q25_patrol_1115_recorded);
the record's turn set to the board's.  DECLARED CONSTRUCTED: the boards of the walk out after the
recorded hold (the player moved one step each, messages cleared).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay
from tests import test_n1c_211_q25_absent_wait_1115_recorded as wait

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-211-q25-pen-exit-1115.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

TELEPORTED, WON, HELD = 4077527, 4077532, 4077565
PEN_EXIT, START_STAIR = (9, 17), (13, 1)
STEPS = {"7": (-1, -1), "8": (-1, 0), "9": (-1, 1), "4": (0, -1), "6": (0, 1), "1": (1, -1),
         "2": (1, 0), "3": (1, 1)}
DEEP_WATER = {(6, 16), (6, 17), (7, 16), (8, 16), (9, 16)}


def board(turn: int) -> dict:
    return copy.deepcopy(next(raw for raw in CASE["boards"] if raw["turn"] == turn))


def new_policy(directory, raw):
    return wait.new_policy(Path(directory), dict(CASE["battle_record"], turn=raw["turn"]), raw)


def moved(raw: dict, cell, turn: int) -> dict:
    board_ = copy.deepcopy(raw)
    board_["player"] = dict(board_["player"], y=cell[0], x=cell[1])
    board_["turn"], board_["messages"] = turn, []
    return board_


class TheRecordingTest(unittest.TestCase):

    def test_teleported_into_the_pen_the_quest_was_won_then_the_exit_held(self):
        self.assertIn("ネクサス・クイルスルグにテレポートさせられた。", board(TELEPORTED)["messages"])
        self.assertEqual((board(TELEPORTED)["player"]["y"], board(TELEPORTED)["player"]["x"]), (7, 17))
        self.assertIn("クエストを達成した！", board(WON)["messages"])
        quest = next(q for q in board(WON)["progress"]["quests"] if q["id"] == 25)
        self.assertEqual(quest["status"], 2)
        for name, rows in CASE["stops"].items():
            holds = [row for row in rows if row[1] == "quest:blocked:exit"]
            self.assertGreaterEqual(len(holds), 30, name)
            self.assertEqual({(row[2], tuple(row[3])) for row in holds}, {("5", PEN_EXIT)}, name)
            self.assertEqual(rows[-1][1], "loop-detected", name)
        self.assertEqual(CASE["battle_record"]["battle"]["phase"], 11)


class TheExitWalkTest(replay._Replay):

    def test_the_recorded_hold_board_walks_out(self):
        raw = board(HELD)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            key = wait.decide_past_reads(policy, raw)
            self.assertEqual(policy.last_reason, "quest:exit:route")
            self.assertIn(key, STEPS)
            step = STEPS[key]
            following = moved(raw, (PEN_EXIT[0] + step[0], PEN_EXIT[1] + step[1]), raw["turn"] + 10)
            self.post(policy, raw, key, following)

    def test_the_walk_crosses_the_water_and_reaches_the_start_stair(self):
        """DECLARED CONSTRUCTED (module note): the walk out step by step from the recorded hold."""
        raw = board(HELD)
        cell, turn, cells = PEN_EXIT, raw["turn"], []
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            for _step in range(80):
                shown = moved(raw, cell, turn)
                key = wait.decide_past_reads(policy, shown)
                if key == "<":
                    self.assertEqual(policy.last_reason, "quest:exit")
                    break
                self.assertIn(policy.last_reason, ("quest:exit:route", "quest:exit:search-door"), cell)
                policy.confirm_key_posted(key)
                if key in STEPS:
                    cell = (cell[0] + STEPS[key][0], cell[1] + STEPS[key][1])
                    cells.append(cell)
                turn += 10
            self.assertEqual(cell, START_STAIR)
            self.assertTrue(set(cells) & DEEP_WATER, cells)
            self.assertEqual(len(set(cells)), len(cells))   # no cell walked twice: no ping-pong

    def test_control_from_dry_ground_the_exit_way_stays_dry(self):
        """The navigator after the pen's decision: deep water is allowed again only for that walk
        (``allow_deep_water`` back off), and from the hall floor [5,9] the exit way is dry."""
        from hengbot.model import Position

        raw = board(HELD)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            wait.decide_past_reads(policy, raw)
            navigator = policy._quest_navigators[25]
            self.assertFalse(navigator.allow_deep_water)
            dry = navigator._static_path(Position(5, 9), {Position(*START_STAIR)})
            self.assertGreater(len(dry), 1)
            self.assertFalse({(cell.y, cell.x) for cell in dry} & DEEP_WATER)
            self.assertEqual(navigator._static_path(Position(*PEN_EXIT), {Position(*START_STAIR)}), [])


if __name__ == "__main__":
    unittest.main()
