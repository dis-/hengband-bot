"""QUEST_33 (クローン地獄): what follows a disengage from a summoner (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「まず離脱後の周辺状況を確認。召還持ちを優先して周辺のモンスターを倒す。安全に
なったら休息してから召還主や召還されたモンスターを少しずつ釣りだして数を減らす。」  And the same day:
「Q33では離脱に取り込んだテレポートの杖の使用を許可する。ない場合はテレポートの巻物を40巻用意すること。」

DECLARED CONSTRUCTED: every floor board below is the recorded n1-b town arrival of 2026-11-19
(tests/fixtures/quest32-one-turn-kill-1119, Magic-Eater Lv50, speed +25) moved onto the Q33 floor
(tests/test_quest33_alignment_split.on_floor) with the quest map as known grids
(tests/test_quest33_summon_answer), the navigator put in the state a disengage leaves it in
(``summon_state`` ``disengaged`` and the group it answered), and the monsters of the board placed by
the test.  The force rows test uses the constructed n1-b that meets the one-turn figure (13 blows,
tests/test_quest33_alignment_split ``test_a_constructed_n1b_that_meets_it_is_accepted``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace

from hengbot import (
    me_absorbed_substitutes,
    me_capability,
    quest_alignment_split,
    quest_plan_base,
    quest_room_sweep,
)
from hengbot import quest_summon_answer as answer
from hengbot.model import SV_STAFF_TELEPORTATION, Position
from hengbot.policy_constants import REST_MACRO, WAIT_KEY
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import DAGON, QUEEN, QUEST, hasted, monster, on_floor, quest_dir, recorded
from tests import test_quest33_summon_answer as summon_tests

JART = 517  # ジャート: no summons, vision 20


class _FloorBoards:
    """The Q33 floor boards of this module (module docstring)."""

    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, self.board = recorded("n1b-411")
        self.board = hasted(self.board)  # the always-hasted fight keeps the haste (alignment_split.hasted)
        self.addCleanup(self.scratch.cleanup)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.turn = 500
        self.grids = summon_tests.Quest33SummonAnswerTest._grids(self)

    def board_at(self, player, seen=(), sensed=(), *, hp=None):
        """DECLARED CONSTRUCTED (module docstring): ``seen`` in view, ``sensed`` by telepathy only."""
        self.turn += 1
        snapshot = replace(on_floor(self.policy, self.board, player, monsters=seen, turn=self.turn),
                           grids=self.grids, detected_monsters=list(sensed))
        hp = self.board.player.max_hp if hp is None else hp
        return replace(snapshot, player=replace(snapshot.player, hp=hp))

    def disengaged(self, snapshot, group):
        navigator = _navigator(self.policy, snapshot, QUEST)
        navigator.summon_state = answer.DISENGAGED
        navigator.summon_group = dict(group)
        return navigator

    def sweep_board(self, snapshot, navigator):
        profile = self.policy.approved_quest_strategy(QUEST)
        return quest_room_sweep._Board(self.policy, snapshot, profile, navigator, self.plan)


class Quest33AfterDisengageTest(_FloorBoards, unittest.TestCase):
    # -- 1-2: what acts on the player, summoners first ------------------------------------

    def test_the_summoner_is_shot_before_the_monster_beside(self):
        # The Jart beside (the plan's _fight strikes what is beside first), the Dagon in line to the west.
        jart = monster(self.policy, 2, JART, (15, 39))
        dagon = monster(self.policy, 1, DAGON, (15, 33))
        snapshot = self.board_at((15, 38), seen=(jart, dagon))
        navigator = self.disengaged(snapshot, {})
        self.assertEqual({m.index for m in answer.acting_around(self.policy, snapshot, navigator)}, {1, 2})
        expected = quest_plan_base._shot(self.policy, snapshot, snapshot.visible_monsters[1])
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual(key, expected)
        self.assertTrue(key.endswith("4"), key)  # aimed west, at the Dagon
        # What acts on the player joined the group.
        self.assertEqual(set(navigator.summon_group), {1, 2})

    def test_one_that_acts_out_of_reach_is_waited_for(self):
        # The Dagon sensed (not seen) at [14,25]: [11,39] is in its line within 20, so it acts.
        dagon = monster(self.policy, 1, DAGON, (14, 25))
        snapshot = self.board_at((11, 39), sensed=(dagon,))
        navigator = self.disengaged(snapshot, {1: (DAGON, (14, 25), True)})
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), (WAIT_KEY, quest_plan_base.HOLD_REASON))
        self.assertEqual((navigator.summon_hold, navigator.summon_state), (1, answer.DISENGAGED))

    # -- 3: safe, the rest ------------------------------------------------------------------

    def test_safe_and_hurt_rests_above_the_plans_line(self):
        # 95% HP: above the plan's rest line (rest_below_ratio 0.9), so the plan alone would walk on.
        hp = int(self.board.player.max_hp * 0.95)
        snapshot = self.board_at((13, 39), hp=hp)
        navigator = self.disengaged(snapshot, {1: (DAGON, (26, 52), True)})
        self.assertGreater(hp / snapshot.player.max_hp, self.plan["rest_below_ratio"])
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), (REST_MACRO, answer.REST_REASON))
        self.assertEqual(navigator.summon_state, answer.DISENGAGED)

    # -- 4: the lure --------------------------------------------------------------------------

    def test_rested_the_summoner_is_lured_from_where_it_acts_alone(self):
        # The Dagon sensed at [14,20], out of reach of the stair [13,39]: the walk heads for a cell
        # where it acts on the player.
        dagon = monster(self.policy, 1, DAGON, (14, 20))
        snapshot = self.board_at((13, 39), sensed=(dagon,))
        navigator = self.disengaged(snapshot, {1: (DAGON, (14, 20), True)})
        self.assertEqual(answer.acting_around(self.policy, snapshot, navigator), [])
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual(self.policy.last_reason, answer.LURE_WALK_REASON)
        self.assertIsNotNone(key)
        self.assertEqual((navigator.summon_state, navigator.summon_target), (answer.LURING, 1))
        count, path = answer._lure_path(self.policy, snapshot, navigator, self.plan,
                                        self.sweep_board(snapshot, navigator), 1, close=False)
        goal = (path[-1].y, path[-1].x)
        self.assertEqual(count, 0)
        open_cells = answer._open_cells(navigator, snapshot)
        self.assertTrue(answer._acts(open_cells, (14, 20), answer._vision(self.policy, DAGON), goal))

    def lured(self, group):
        """The member chosen to pull from the stair [13,39], and each member's fewest others acting."""
        sensed = tuple(monster(self.policy, index, race, cell) for index, (race, cell, _) in group.items())
        snapshot = self.board_at((13, 39), sensed=sensed)
        navigator = self.disengaged(snapshot, group)
        board = self.sweep_board(snapshot, navigator)
        counts = {index: answer._lure_path(self.policy, snapshot, navigator, self.plan, board, index,
                                           close=False)[0] for index in group}
        quest_room_sweep.key(self.policy, snapshot)
        return navigator.summon_target, counts

    def test_the_member_pulled_alone_is_lured_first(self):
        # The Dagons [14,20] and [15,21] each wake the other wherever they act on the player; the Jart
        # [8,20] can be pulled alone: it is pulled first, summoner or not.
        target, counts = self.lured({1: (DAGON, (14, 20), True), 2: (DAGON, (15, 21), True),
                                     3: (JART, (8, 20), False)})
        self.assertEqual(counts, {1: 1, 2: 1, 3: 0})
        self.assertEqual(target, 3)

    def test_of_those_pulled_alone_the_summoner_first(self):
        # [14,21] can be pulled without [14,20] and so can the Jart [5,10]: the summoner first.
        target, counts = self.lured({1: (DAGON, (14, 20), True), 2: (DAGON, (14, 21), True),
                                     3: (JART, (5, 10), False)})
        self.assertEqual((counts[2], counts[3]), (0, 0))
        self.assertEqual(target, 2)

    def test_on_the_pulling_cell_it_holds_for_what_follows(self):
        dagon = monster(self.policy, 1, DAGON, (14, 20))
        snapshot = self.board_at((13, 39), sensed=(dagon,))
        navigator = self.disengaged(snapshot, {1: (DAGON, (14, 20), True)})
        quest_room_sweep.key(self.policy, snapshot)
        _count, path = answer._lure_path(self.policy, snapshot, navigator, self.plan,
                                         self.sweep_board(snapshot, navigator), 1, close=False)
        # On the pulling cell, the Dagon gone out of the telepathy's reach: held for, at its last cell.
        there = self.board_at((path[-1].y, path[-1].x))
        key = quest_room_sweep.key(self.policy, there)
        self.assertEqual(navigator.summon_group, {1: (DAGON, (14, 20), True)})
        self.assertEqual((key, self.policy.last_reason), (WAIT_KEY, quest_plan_base.HOLD_REASON))

    def test_a_good_member_is_never_pulled_where_an_evil_summoner_acts(self):
        # The Queen [20,69] to lure, a Dagon sensed in the corridor at [14,47].  [1,49] is 14 from the
        # Dagon: beyond its vision (12), so no contact cell, but in its line within 20, so it acts there.
        dagon = monster(self.policy, 9, DAGON, (14, 47))
        snapshot = self.board_at((15, 38), sensed=(dagon,))
        navigator = self.disengaged(snapshot, {1: (QUEEN, (20, 69), True)})
        board = self.sweep_board(snapshot, navigator)
        cells = set().union(*answer.lure_cells(self.policy, snapshot, navigator, self.plan, board, 1,
                                                close=False).values())
        open_cells = answer._open_cells(navigator, snapshot)
        self.assertTrue(cells)
        self.assertNotIn((1, 49), quest_alignment_split.refused_cells(self.policy, snapshot, navigator, self.plan))
        self.assertTrue(answer._acts(open_cells, (20, 69), answer._vision(self.policy, QUEEN), (1, 49)))
        self.assertTrue(answer._acts(open_cells, (14, 47), answer._vision(self.policy, DAGON), (1, 49)))
        self.assertNotIn((1, 49), cells)
        evil = [(cell, vision) for side, cell, vision in quest_alignment_split.summoners(
            self.policy, snapshot, navigator, self.plan) if side == quest_alignment_split.EVIL]
        self.assertFalse([spot for spot in cells
                          if any(answer._acts(open_cells, cell, vision, spot) for cell, vision in evil)])

    def test_a_member_looked_for_and_not_found_leaves_and_the_plan_goes_on(self):
        # Its last cell [15,35] is in the light (radius 5) and line of [15,38], and nothing is on it.
        snapshot = self.board_at((15, 38))
        navigator = self.disengaged(snapshot, {1: (DAGON, (15, 35), True)})
        quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual(navigator.summon_group, {})
        self.assertIsNone(navigator.summon_state)
        self.assertNotEqual(self.policy.last_reason, answer.LURE_WALK_REASON)

    def test_a_kill_while_luring_keeps_the_steps(self):
        # A summon received on the pulling cell, the Dagon wounded to 50: struck, still luring.
        snapshot = self.board_at((15, 38))
        navigator = self.disengaged(snapshot, {1: (DAGON, (15, 39), True)})
        navigator.summon_state = answer.LURING
        helper = summon_tests.Quest33SummonAnswerTest("test_a_summon_received_is_named")
        helper.policy, helper.board, helper.grids, helper.turn = self.policy, self.board, self.grids, self.turn
        received = helper.board_of((15, 38), DAGON, (15, 39), hp=50)
        key = quest_room_sweep.key(self.policy, received)
        self.assertEqual((key, self.policy.last_reason), ("6", answer.STRIKE_REASON))
        self.assertEqual(navigator.summon_state, answer.LURING)


class Quest33PlanTeleportTest(_FloorBoards, unittest.TestCase):
    """Owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」: the plan's own escape too
    (quest_plan_base._below_line: the HP 40% line and the 即死 step of a board with no summon)."""

    def below_the_line(self):
        # 30% HP, an unhurt Dagon in line to the west and no summon on the board.
        dagon = monster(self.policy, 1, DAGON, (15, 33))
        snapshot = self.board_at((15, 38), seen=(dagon,), hp=int(self.board.player.max_hp * 0.3))
        _navigator(self.policy, snapshot, QUEST)
        return snapshot

    def test_below_the_line_the_absorbed_teleportation_is_cast(self):
        snapshot = self.below_the_line()
        key = quest_room_sweep.key(self.policy, snapshot)
        power = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
        self.assertEqual((key, self.policy.last_reason),
                         (power.key, quest_plan_base.TELEPORT_REASON + me_absorbed_substitutes.CAST_SUFFIX))

    def test_below_the_line_without_the_power_the_scroll_is_read(self):
        summon_tests.Quest33SummonAnswerTest.without_absorbed_teleportation(self)
        snapshot = self.below_the_line()
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), ("re", quest_plan_base.TELEPORT_REASON))

    def test_another_quest_keeps_the_scroll_first(self):
        snapshot = self.below_the_line()
        other = replace(snapshot, floor_key=(0, 45, 32), quests={
            **snapshot.quests, 32: replace(snapshot.quests[QUEST], id=32)})
        self.assertEqual(self.policy._active_fixed_quest_id(other), 32)
        self.assertIsNone(answer.absorbed_teleport_key(self.policy, other, quest_plan_base.TELEPORT_REASON))
        self.assertIsNotNone(answer.absorbed_teleport_key(self.policy, snapshot, quest_plan_base.TELEPORT_REASON))


class Quest33EmergencyReadTest(_FloorBoards, unittest.TestCase):
    """Owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」 / 「取り込んだ杖を優先
    しようすれば問題ない」: the emergency ladder's read too (quest_summon_answer.emergency_scroll_substitute).

    n1-b life-418 (2026-11-25 15:08:00-15:08:53): the ladder read all 15 Scrolls of Teleportation under
    ``emergency:teleport`` while the absorbed Teleportation had charges; at 15:39:50 the power was empty
    on a 即死 board with no scroll left, and the character died at 15:39:56."""

    def ladder_read(self, snapshot):
        scroll = self.policy._find_teleport_scroll(snapshot)
        self.assertIsNotNone(scroll)
        return self.policy._issue_emergency_consumable(snapshot, scroll, "emergency:teleport")

    def test_the_ladder_casts_the_absorbed_teleportation(self):
        snapshot = self.board_at((15, 38), hp=int(self.board.player.max_hp * 0.5))
        power = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
        self.assertEqual((self.ladder_read(snapshot), self.policy.last_reason),
                         (power.key, "emergency:teleport" + me_absorbed_substitutes.CAST_SUFFIX))

    def test_without_the_power_the_ladder_reads_the_scroll(self):
        summon_tests.Quest33SummonAnswerTest.without_absorbed_teleportation(self)
        snapshot = self.board_at((15, 38), hp=int(self.board.player.max_hp * 0.5))
        self.assertEqual((self.ladder_read(snapshot), self.policy.last_reason), ("re", "emergency:teleport"))

    def test_another_quest_keeps_the_scroll_first(self):
        snapshot = self.board_at((15, 38), hp=int(self.board.player.max_hp * 0.5))
        other = replace(snapshot, floor_key=(0, 45, 32), quests={
            **snapshot.quests, 32: replace(snapshot.quests[QUEST], id=32)})
        self.assertEqual((self.ladder_read(other), self.policy.last_reason), ("re", "emergency:teleport"))


class Quest33TeleportScrollsTest(unittest.TestCase):
    """Owner 2026-11-19 「ない場合はテレポートの巻物を40巻用意すること」."""

    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, board = recorded("n1b-411")
        self.addCleanup(self.scratch.cleanup)
        self.strong = replace(board, player=replace(board.player, main_hand_blows=13, hp=board.player.max_hp))
        self.profile = self.policy.approved_quest_strategy(QUEST)

    def teleport_scrolls(self):
        return self.policy._strategy_force_for_snapshot(self.strong, self.profile)["required_scrolls"]["teleport"]

    def test_the_shipped_force_names_forty(self):
        self.assertEqual(self.profile.required_force["teleport_scrolls_without_absorbed"], 40)
        self.assertEqual(self.profile.required_force["required_scrolls"]["teleport"], 10)

    def test_with_the_power_ten_are_asked(self):
        self.assertTrue(me_capability.has(self.policy, self.strong, "staff", SV_STAFF_TELEPORTATION))
        self.assertEqual(self.teleport_scrolls(), 10)

    def test_without_the_power_forty_are_asked_and_acceptance_waits_for_them(self):
        summon_tests.Quest33SummonAnswerTest.without_absorbed_teleportation(self)
        self.assertEqual(self.teleport_scrolls(), 40)
        status = self.policy._quest_carry_status(
            self.strong, self.policy._strategy_force_for_snapshot(self.strong, self.profile))
        self.assertEqual(status["required_scrolls.teleport"]["required"], 40)
        self.assertFalse(status["required_scrolls.teleport"]["ready"])


if __name__ == "__main__":
    unittest.main()
