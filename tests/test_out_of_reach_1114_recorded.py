"""n1-c life-207: never-moving mimics in a glass-walled vault made the 60F arrival read T1.

Owner 2026-11-14 (recall-churn-1114 question 3, verbatim 「外す」): a monster that never moves
(NEVER_MOVE), that the player cannot walk to and that has no line of fire to the player need not
be fought (design 4.3) and is left out of the tier (``threat_escape.out_of_reach``, the 4.3 reason
"out-of-reach").  One that comes beside the player as it approaches, or whose spell or breath
reaches, counts as before.

Recorded: tests/fixtures/recall-churn-1114.pkl.xz (tests/extract_recall_churn_1114_fixture.py),
decision 4132 (04:26:45): the 60F arrival with 43 hostiles in the engagement, 20 of them never
moving (14 金色の宝箱 and 6 あつくもえるてき) inside a vault walled with glass.  Read T1 from them
(the free attacks could not clear the engagement), the bot drank Speed (absorbed power) and
walked away (recall-churn-1114 question 3).

DECLARED CONSTRUCTED: one 金色の宝箱 moved onto a floor grid of the player's room; the
executor's prompts.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from collections import Counter
from dataclasses import replace

from hengbot import threat_tiers
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import Position
from tests.support import recorded as executor_pins
from tests.test_floor_visit_memory_1114_recorded import ARRIVAL, MAP_NAME, consumed, raw_board
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

MIMICS = {"金色の宝箱": 14, "あつくもえるてき": 6}
ROOM_CELL = Position(16, 89)       # a floor grid of the player's room
SPEED = ("mAw", "emergency:quaff-speed:absorbed-power")
NEW_FLOOR_MAP = ("mAj", "me-power:new-floor:map-area")


def immobile(policy, monsters):
    return [m for m in monsters if "NEVER_MOVE" in policy._monrace_knowledge[m.race_id].flags]


class OutOfReach1114RecordedTest(executor_pins.ProductionHarness):
    def test_recorded_scene(self):
        """20 never-moving mimics, none with a known walk to them nor a line to the player."""
        policy, board = consumed(ARRIVAL)
        here = board.player.position
        engaged = threat_tiers.engagement(policy, board)
        mimics = immobile(policy, engaged)
        self.assertEqual(len(engaged), 43)
        self.assertEqual(Counter(m.name for m in mimics), MIMICS)
        self.assertFalse(any(policy._monster_path_distance(board, m.position) is not None
                             for m in mimics))
        self.assertFalse(any(policy._may_project(board, m.position, here) for m in mimics))

    def test_the_mimics_are_left_out_of_the_tier(self):
        policy, board = consumed(ARRIVAL)
        engaged = threat_tiers.engagement(policy, board)
        mimics = immobile(policy, engaged)
        result = threat_tiers.assess(policy, board, engaged)
        self.assertEqual({result.per_monster[m.index].need_not_fight for m in mimics},
                         {threat_tiers.OUT_OF_REACH})
        self.assertNotEqual(result.tier, threat_tiers.T1)
        alone = threat_tiers.assess(policy, board, mimics)
        self.assertIsNone(alone.tier)
        self.assertFalse(alone.instant_death)
        self.assertTrue(threat_tiers.cannot_reach_all(alone, mimics))

    def test_the_arrival_does_not_walk_away_from_the_mimics(self):
        policy, board = consumed(ARRIVAL)
        key = policy.choose_key(board)
        self.assertNotEqual((key, policy.last_reason), SPEED)
        self.assertEqual((key, policy.last_reason), NEW_FLOOR_MAP)

    def test_a_reachable_immobile_caster_still_counts(self):
        """One 金色の宝箱 on a floor grid of the player's room (DECLARED CONSTRUCTED)."""
        policy, board = consumed(ARRIVAL)
        mimic = next(m for m in immobile(policy, threat_tiers.engagement(policy, board))
                     if m.name == "金色の宝箱")
        self.assertTrue(board.grid_at(ROOM_CELL).passable)
        moved = replace(mimic, position=ROOM_CELL)
        changed = replace(board, visible_monsters=[
            moved if m.index == mimic.index else m for m in board.visible_monsters])
        self.assertIsNotNone(policy._monster_path_distance(changed, ROOM_CELL))
        result = threat_tiers.assess(policy, changed, [moved])
        self.assertNotEqual(result.per_monster[mimic.index].need_not_fight,
                            threat_tiers.OUT_OF_REACH)
        self.assertIsNotNone(result.tier)
        self.assertIn(mimic.index, result.free_damage)

    def test_the_arrival_key_goes_through_the_executor(self):
        policy, board = consumed(ARRIVAL)
        key = policy.choose_key(board)
        raw = copy.deepcopy(raw_board(ARRIVAL))
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                        power_screen("staff", [("j", MAP_NAME, 3, 3, 5)]),
                        executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                             "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted, ["m", "A", "j"])


if __name__ == "__main__":
    unittest.main()
