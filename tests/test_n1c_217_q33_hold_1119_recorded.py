"""n1-c life-217, the first live Quest 33 run (2026-11-19, build a39d54ce5): after the disengage, held for ever.

At 18:32:23 地獄の論客『カイム』 summoned and breathed confusion; the plan cast the absorbed
Teleportation (quest-strategy:summoned-disengage-teleport:absorbed-power) and the player landed on
[2,56].  He shot the two ファゾルト there, then answered '5' quest-strategy:hold from 18:32:43 to the
server's halt at 19:05 (stall:floor-dwell:quest-strategy:hold, about 15,900 holds), nothing in view.

What the board shows (tests/fixtures/n1c-217-q33-hold-1119.json.gz, extracted by
tests/extract_n1c_217_q33_hold_1119_fixture.py): two ボーシン (177) awake beyond the pits at [18,50]
and [18,55], within their vision of [2,56] (so they act on the player, quest_summon_answer
``acting_around``), and no walk of the plan reaches a cell they would be seen from.  The steps after
the disengage (owner 2026-11-19 「まず離脱後の周辺状況を確認。召還持ちを優先して周辺のモンスターを倒す。
安全になったら休息してから召還主や召還されたモンスターを少しずつ釣りだして数を減らす。」) held for them
up to the plan's ``enemy_wait_turns`` (200), but the count of holds was set back to 0 on every board
(``_note_group`` dropped the lured member's count while no member was lured), so the wait never ended.
Past the wait, a monster no walk reaches is left to the plan: the rest when hurt, then the plan's
own sweep.  Owner 2026-11-19 「地形と敵の位置、敵のアルゴリズムを確認して有効な場所で待つ」: the reader
(quest_wait_placement) sees that the two walk on no way over the pits to [2,56], so the wait for them
is not held at all.

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, with the shipped strategies and this tree's quest
data, tests/test_quest33_alignment_split ``recorded``); the navigator is put in the state the
teleport left it in (``summon_state`` ``disengaged``); the summoner's group is not on this board and
is left empty (the two ボーシン join it as they act on the player, as on the live run); the board's
turn advances one per decision; ``test_at_full_hp_the_plan_walks_on`` gives the player his maximum HP.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import quest_room_sweep, quest_summon_answer as answer, quest_wait_placement
from hengbot.model import Position, parse_snapshot
from hengbot.quest_plan_base import HOLD_REASON, _navigator
from tests.test_quest33_alignment_split import QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-q33-hold-1119.json.gz"
BOSHIN = 177


class N1c217Q33HoldTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            self.case = json.load(stream)
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.board = parse_snapshot(self.case["board"], self.policy._monrace_knowledge)
        self.wait = int(self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]["enemy_wait_turns"])

    def decide(self, board, decisions):
        """``decisions`` boards, the plan's own key first and its navigator walk on a quiet None."""
        navigator = _navigator(self.policy, board, QUEST)
        navigator.summon_state = answer.DISENGAGED
        made = []
        for step in range(decisions):
            snapshot = replace(board, turn=board.turn + step)
            key = quest_room_sweep.key(self.policy, snapshot)
            if key is None:
                key = quest_room_sweep.walk_key(self.policy, snapshot)
            made.append((key, self.policy.last_reason))
        return navigator, made

    def test_the_recorded_board(self):
        self.assertEqual((self.board.floor_key[2], self.board.player.position), (QUEST, Position(2, 56)))
        teleport, *after = self.case["decisions"]
        self.assertEqual(teleport["reason"], answer.DISENGAGE_TELEPORT_REASON + ":absorbed-power")
        self.assertTrue(all(row["position"] == {"y": 2, "x": 56} for row in after))
        self.assertEqual(after[-1]["reason"], HOLD_REASON)
        self.assertEqual(self.board.visible_monsters, [])
        navigator = _navigator(self.policy, self.board, QUEST)
        acting = answer.acting_around(self.policy, self.board, navigator)
        self.assertEqual(sorted((m.race_id, m.position.y, m.position.x) for m in acting),
                         [(BOSHIN, 18, 50), (BOSHIN, 18, 55)])

    def test_the_boshin_act_but_do_not_come(self):
        # Owner 2026-11-19 「有効な場所で待つ」: walkers beyond the pits (DARK_PIT has no MOVE, only a
        # flyer crosses it, monster-info.cpp monster_can_cross_terrain) never reach [2,56].
        navigator = _navigator(self.policy, self.board, QUEST)
        plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        acting = answer.acting_around(self.policy, self.board, navigator)
        self.assertEqual(len(acting), 2)
        self.assertFalse(any(quest_wait_placement.comes(self.policy, self.board, navigator, plan, monster)
                             for monster in acting))

    def test_hurt_it_rests_at_once(self):
        # HP 632/948 on the board: no hold for what will not come (it was 200 before the reader),
        # the owner's rest at once.
        navigator, made = self.decide(self.board, 5)
        self.assertEqual(made, [("R&\r", answer.REST_REASON)] * 5)
        self.assertEqual(set(navigator.summon_unreached), {15, 21})

    def test_at_full_hp_the_plan_walks_on(self):
        full = replace(self.board, player=replace(self.board.player, hp=self.board.player.max_hp))
        navigator, made = self.decide(full, 3)
        self.assertNotIn(HOLD_REASON, {reason for _key, reason in made})
        self.assertEqual({reason for _key, reason in made}, {quest_room_sweep.WALK_REASON})
        self.assertEqual(navigator.summon_state, answer.LURING)

    def test_a_summoner_killed_reopens_them(self):
        full = replace(self.board, player=replace(self.board.player, hp=self.board.player.max_hp))
        navigator, _made = self.decide(full, 1)
        self.assertEqual(set(navigator.summon_unreached), {15, 21})
        navigator.split_kills = {**navigator.split_kills, 441: navigator.split_kills.get(441, 0) + 1}
        board = quest_room_sweep._Board(self.policy, full, self.policy.approved_quest_strategy(QUEST),
                                        navigator, self.policy.approved_quest_strategy(QUEST)
                                        .engagement_plan["room_sweep"])
        self.assertEqual(answer._unreached(navigator, board), frozenset())


if __name__ == "__main__":
    unittest.main()
