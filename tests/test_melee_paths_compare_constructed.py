"""The four melee paths that skipped the ranged order (owner 2026-11-04 「4つとも比べる順にする」).

The no-wait rewrite, the ESP hunt, the unseen choke and the disengage now answer
through combat_answer: the larger expected damage per action of the ranged order
and melee.  The captures of 2026-11-04 hold no board of these paths for a
Magic-Eater, so every board here is DECLARED CONSTRUCTED:
- a sealed corridor with the Magic-Eater class and an adjacent hostile, except the
  town rewrite (the recorded town cat, class changed);
- the ESP hunt's committed state and feasibility are set directly;
- melee's expected damage is stubbed to lose or win against the real missile
  score; the comparison itself is me_ranged_first's;
- each path's earlier rungs are stubbed away, so only its own answer runs.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from unittest import mock

from hengbot import attack_expectation, unseen_strike
from hengbot.magic_eater import MISSILE_REASON
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import Position, Snapshot
from hengbot.policy import HengbotPolicy
from tests import policy_fixtures as fixtures
from tests import test_town_cat_no_wait_recorded as town_cat


MELEE_LOSES = 0.0
MELEE_WINS = 1_000_000.0


def corridor(*, afraid=False):
    grids = {
        Position(y, x): fixtures.grid(y, x, passable=y == 10 and 7 <= x <= 16, in_view=True, lit=True)
        for y in range(9, 12) for x in range(6, 18)
    }
    grids[Position(10, 11)] = fixtures.grid(10, 11, monster=True, in_view=True, lit=True)
    player = replace(fixtures.player(10, 10, hp=100, max_hp=200, level=30),
                     class_id=PLAYER_CLASS_MAGIC_EATER, afraid=afraid)
    monster = fixtures.hostile(19, 10, 11, race_id=9001, hp=500, max_hp=500, distance=1)
    return Snapshot(player, grids, [monster], floor_key=(3, 23, 0), inventory=[],
                    width=24, height=22, turn=10000)


class MeleePathsCompare(unittest.TestCase):
    def assert_compares(self, decide, melee_reason, direction="6"):
        with mock.patch.object(attack_expectation, "melee", return_value=MELEE_LOSES):
            self.assertEqual(decide(), ("mBp" + direction, MISSILE_REASON))
        with mock.patch.object(attack_expectation, "melee", return_value=MELEE_WINS):
            self.assertEqual(decide(), (direction, melee_reason))

    def test_no_wait_rewrite_beside_a_hostile(self):
        def decide(board=None):
            board = board or corridor()
            policy = HengbotPolicy(monrace_knowledge={})
            policy._build_grid_index(board)
            policy._took_damage = True
            with mock.patch.object(policy, "_flee_step", return_value=None), \
                    mock.patch.object(policy, "_escape_scroll", return_value=None), \
                    mock.patch.object(policy, "_least_visited_neighbor", return_value=None), \
                    mock.patch.object(unseen_strike, "key", return_value=None):
                key = policy._forbid_wait_while_damaged(board, "5")
            return key, policy.last_reason
        self.assert_compares(decide, "no-wait:melee")

    def test_no_wait_rewrite_of_a_town_contact(self):
        # 「近接以外の攻撃手段も街で使う」: the recorded town cat, its class changed.
        recorded = town_cat.TownCatNoWaitReplayTests
        recorded.setUpClass()
        case = recorded("test_captured_town_cat_is_meleed_instead_of_fled_from")

        def decide():
            board = replace(recorded.captured,
                            player=replace(recorded.captured.player, class_id=PLAYER_CLASS_MAGIC_EATER))
            self.assertTrue(board.in_town)
            return case.replay_wait(board)
        with mock.patch.object(attack_expectation, "melee", return_value=MELEE_LOSES):
            key, reason = decide()
            self.assertEqual((key[:3], reason), ("mBp", MISSILE_REASON))
        with mock.patch.object(attack_expectation, "melee", return_value=MELEE_WINS):
            self.assertEqual(decide(), ("1", "no-wait:melee"))

    def test_esp_hunt_beside_its_target(self):
        def decide():
            board = corridor()
            monster = board.visible_monsters[0]
            policy = HengbotPolicy(monrace_knowledge={})
            policy._build_grid_index(board)
            policy._esp_threat_hunt = dict(
                floor=board.floor_key, indices=[monster.index], floor_hp=0,
                speed_planned=False, speed_drunk=False)
            with mock.patch.object(policy, "_esp_threat_turn_damage", return_value=1), \
                    mock.patch.object(policy, "_esp_threat_kill_feasibility",
                                      return_value={"feasible": True}):
                key = policy._esp_threat_hunt_key(board, [monster])
            return key, policy.last_reason
        self.assert_compares(decide, "melee:esp-threat-hunt")

    def choke(self, board):
        policy = HengbotPolicy(monrace_knowledge={})
        policy._build_grid_index(board)
        policy._unseen_retreat_floor = board.floor_key
        policy._unseen_choke_position = board.player.position
        with mock.patch.object(policy, "_unseen_choke_hold_active", return_value=True):
            key = policy._unseen_retreat_intercept_key(
                board, list(board.visible_monsters), list(board.visible_monsters))
        return key, policy.last_reason

    def test_unseen_choke_beside_a_hostile(self):
        self.assert_compares(lambda: self.choke(corridor()), "melee:choke")

    def disengage(self, board):
        policy = HengbotPolicy(monrace_knowledge={})
        policy._build_grid_index(board)
        policy.last_reason = "unset"
        with mock.patch.object(policy, "_summoner_retreat_step", return_value=None), \
                mock.patch.object(policy, "_escape_by_stairs", return_value=None), \
                mock.patch.object(policy, "_nearest_goal_step", return_value=None), \
                mock.patch.object(policy, "_blocking_escape_melee_key", return_value=None), \
                mock.patch.object(policy, "_explore_step", return_value=None):
            hostiles = list(board.visible_monsters)
            key = policy._disengage_move_or_escalate(board, hostiles, hostiles)
        return key, policy.last_reason

    def test_disengage_beside_a_hostile(self):
        self.assert_compares(lambda: self.disengage(corridor()), "combat:disengage-melee")

    def test_afraid_disengage_never_posts_the_refused_blow(self):
        # Fear refuses melee (cmd-attack.cpp): the ranged order fires.
        self.assertEqual(self.disengage(corridor(afraid=True)), ("mBp6", MISSILE_REASON))
        # Nothing to fire: no blow, the caller's bounded wait.
        board = corridor(afraid=True)
        board = replace(board, player=replace(board.player, class_id=1))
        self.assertEqual(self.disengage(board), (None, "unset"))


if __name__ == "__main__":
    unittest.main()
