"""n1-c life-207: monsters seen through the glass walls of ガラスの城 read as able to breathe.

Owner 2026-11-14: 「帰還の条件がおかしい気がする。」 then 「先に調べて直して」.  n1-c life-207
(Magic-Eater Lv46, max HP 603) went from town to ガラスの城 (Glass castle) 60F and back about once
a minute: on most arrivals the bot read 即死 (next action's p95 636 to 20631) from awake monsters
it saw only through glass walls, read Teleportation (a counted escape), landed by another glassed
room, escaped again and, with the second escape, read Recall (owner 2026-11-09 A).  Glass has LOS
without PROJECTION: projectable() stops on it (projection-path-calculator.cpp:94) and only light
and disintegration cross it (mspell-lite.cpp; glass_reach).  The bot's line of fire read the line
of sight, and its projectable() read glass as open.

Recorded: tests/fixtures/recall-churn-1114.pkl.xz (tests/extract_recall_churn_1114_fixture.py),
decision 4132 (04:26:45): the 60F arrival with 50 monsters in view, 27 awake (treasure-chest
mimics, あつくもえるてき and a 腐乱クイルスルグ in a vault behind glass); the live bot read
``emergency:teleport`` (T1, 即死).  The pin restores the board's checkpoint and decides through
the public ``choose_key``.

DECLARED CONSTRUCTED: one awake mimic behind the glass given the race of a light or a darkness
caster (and that race's ranged damage); the executor's prompts.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace

from hengbot import glass_reach, threat_tiers
from hengbot.cli import _ExecutorInputPort, SendResult
from tests.support import recorded as executor_pins
from tests.test_floor_visit_memory_1114_recorded import ARRIVAL, consumed, live, raw_board
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

MIMIC = 1                  # 金色の宝箱 at (14, 106), cdis 15 across the glass
BA_LITE_RACE = 1124        # BA_LITE (no BR_LITE): crosses glass within get_max_range()
BR_LITE_RACE = 504         # BR_LITE: crosses glass only within get_max_range() / 2
BR_DARK_RACE = 663         # BR_DARK: never crosses glass
SPEED_NAME = "スピード"


def awake_in_view(board):
    return [m for m in board.visible_monsters if m.hostile and not m.asleep]


def as_race(policy, board, race_id):
    """The board with MIMIC given ``race_id`` (DECLARED CONSTRUCTED)."""
    knowledge = policy._monrace_knowledge[race_id]
    return replace(board, visible_monsters=[
        replace(m, race_id=race_id, name=f"race {race_id}", max_ranged_damage=max(1, m.max_ranged_damage))
        if m.index == MIMIC else m for m in board.visible_monsters]), knowledge


class GlassReach1114RecordedTest(executor_pins.ProductionHarness):
    def test_recorded_scene(self):
        """27 awake in view; none projectable; 17 on a line read through the glass."""
        policy, board = consumed(ARRIVAL)
        here = board.player.position
        awake = awake_in_view(board)
        self.assertEqual((len(board.visible_monsters), len(awake)), (50, 27))
        self.assertFalse(any(policy._may_project(board, m.position, here) for m in awake))
        through = [m for m in awake if policy._may_project(board, m.position, here, across_glass=True)]
        self.assertEqual(len(through), 17)
        self.assertEqual(live(ARRIVAL), ("re", "emergency:teleport"))

    def test_the_arrival_reads_no_instant_death_and_no_escape(self):
        policy, board = consumed(ARRIVAL)
        assessment = threat_tiers.assess(policy, board)
        self.assertFalse(assessment.instant_death)
        self.assertEqual(policy.threat_prediction(board, awake_in_view(board), 3)["total"], 0)
        key = policy.choose_key(board)
        self.assertNotIn(policy.last_reason, ("emergency:teleport", "flee:scroll"))
        self.assertNotEqual(key, live(ARRIVAL)[0])
        self.assertEqual(policy._dive_emergencies, 0)
        self.assertFalse(policy._returning_to_town)

    def test_only_light_crosses_the_glass(self):
        policy, board = consumed(ARRIVAL)
        here = board.player.position
        for race_id, reaches in ((BA_LITE_RACE, True), (BR_LITE_RACE, False), (BR_DARK_RACE, False)):
            with self.subTest(race=race_id):
                changed, knowledge = as_race(policy, board, race_id)
                mimic = next(m for m in changed.visible_monsters if m.index == MIMIC)
                self.assertEqual(policy._monster_cast_distance(mimic.position, here), 15)
                passing = glass_reach.passing_abilities(policy, changed, mimic, knowledge, here)
                self.assertEqual(passing == {"BA_LITE"}, reaches, passing)
                row = policy.threat_prediction(changed, [mimic], 1)["monsters"][0]
                self.assertEqual(row["ranged_prediction"] > 0, reaches, row)

    def test_the_arrival_key_goes_through_the_executor(self):
        policy, board = consumed(ARRIVAL)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("mAw", "emergency:quaff-speed:absorbed-power"))
        raw = copy.deepcopy(raw_board(ARRIVAL))
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                        power_screen("staff", [("w", SPEED_NAME, 3, 3, 5)]),
                        executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                             "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted, ["m", "A", "w"])


if __name__ == "__main__":
    unittest.main()
