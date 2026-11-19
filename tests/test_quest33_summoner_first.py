"""QUEST_33 (クローン地獄): the summoner gone after while the predicted damage is small (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「召還からの離脱の優先度を下げ、予測被害が小さいうちは召還主の撃破を優先する」;
「小さい」, answered by the owner: 「受けても HP40% を割らない間」 -- the HP less the predicted damage (the
即死 reading: instant_death's next player action p95 plus its unseen correction) at or above the plan's
withdrawal line (``abort_conditions.hp_ratio`` 0.4 of the max HP).  Below it the player disengages as
before (quest_summon_answer 3).

n1-b life-411 (Magic-Eater Lv50, HP 1128) failed Q33 on 2026-11-19 with nine disengage teleports, each
right after a summon at HP >= 97% (C:/hengband-backups/pdca/n1b-411-q33-1119-timeline.txt).

RECONSTRUCTED FROM THE RECORD: the raw snapshots of those boards are not in this tree; each board below
is that timeline's line (game turn, the player's cell and HP, the monsters in view with their cells and
sleep, the board's summon line), put on the recorded n1-b town arrival of 2026-11-19
(tests/fixtures/quest32-one-turn-kill-1119, its max HP set to the timeline's 1128) on the Q33 floor
(tests/test_quest33_alignment_split.on_floor), with the quest map's terrain as known grids
(test_quest33_summon_answer._grids).  The monsters carry the fields the board parser fills from the
monster knowledge (model.py: speed, level, max melee and ranged damage), at full HP ("unhurt").  On
8488751 the Arch-vile stands on the door [16,40], so the doors of the pillar [16,39] [16,40] are open.
The timeline lists the first eight monsters in view only.  With the code before this change each of
the four boards below was answered by the disengage teleport (the record's teleports); the unseen
casts (8489116, 8489568: 「何かが魔法でアリを召喚した。」) name no summoner, and on 8489305, 8489768 and
8489983 the caster has no line of fire on the reconstructed map, so this rule does not answer those.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import (
    me_absorbed_substitutes,
    me_ranged_first,
    quest_alignment_split,
    quest_room_sweep,
    quest_summon_answer,
    summon_response,
    threat_tiers,
)
from hengbot.model import Position
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import QUEST, hasted, monster, on_floor, quest_dir, recorded
from tests import test_quest33_summon_answer as summon_answer_tests

MAX_HP = 1128
DAGON_CAST = "父なる『ダゴン』が魔法で手下を召喚した。"
# turn: (player cell, HP, [(name, y, x)], the board's summon line), from the timeline.
BOARDS = {
    8488751: ((15, 40), 1116, [("父なる『ダゴン』", 25, 41), ("父なる『ダゴン』", 23, 41), ("父なる『ダゴン』", 21, 40),
                               ("<スラーネッシュ>の女悪魔", 15, 41), ("アーチ=ヴァイル", 16, 40), ("ベビーサタン", 15, 39),
                               ("メッツォデーモン", 17, 41)], DAGON_CAST),
    8489035: ((14, 34), 1128, [("父なる『ダゴン』", 15, 38), ("メッツォデーモン", 15, 37), ("ボダック", 15, 34),
                               ("メッツォデーモン", 15, 33)], DAGON_CAST),
    8489425: ((1, 27), 1127, [("ボダック", 14, 31), ("夜鬼", 1, 26)], "ボダックは魔法で混沌の宮廷から悪魔を召喚した！"),
    8489971: ((11, 39), 1128, [("忌まわしき狩人", 2, 26), ("アラクノトロン", 10, 39)],
              "忌まわしき狩人は魔法で混沌の宮廷から悪魔を召喚した！"),
}
# The answers of the disengage (quest_summon_answer 3).
# The shot at the summoner: an absorbed attack power, cast normally or by Powerful Activation
# (me_device_attacks.POWERFUL_REASON, me-powerful-attack-1119: the stronger of the two is sent).
SHOT = "ranged:magic-eater-powerful"
DISENGAGE_REASONS = {
    quest_summon_answer.DISENGAGE_WALK_REASON, quest_summon_answer.DISENGAGE_TELEPORT_REASON,
    quest_summon_answer.DISENGAGE_TELEPORT_REASON + ":absorbed-power"}


class Quest33SummonerFirstTest(unittest.TestCase):
    # The quest map as known grids, as the summon answer's tests build them (not their cases).
    _grids = summon_answer_tests.Quest33SummonAnswerTest._grids

    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, self.board = recorded("n1b-411")
        self.board = hasted(self.board)  # the always-hasted fight keeps the haste (alignment_split.hasted)
        self.addCleanup(self.scratch.cleanup)
        self.grids = self._grids()
        for door in ((16, 39), (16, 40)):
            cell = Position(*door)
            self.grids[cell] = replace(self.grids[cell], passable=True, wall=False, is_closed_door=False,
                                       allows_los=True)
        self.races = {}
        for race, knowledge in self.policy._monrace_knowledge.items():
            for name in getattr(knowledge, "names", ()):
                self.races.setdefault(name, race)

    def board_at(self, turn, *, player=None, hp=None, monsters=None, message=None):
        """RECONSTRUCTED (module docstring): the timeline's board ``turn``; ``player``, ``hp``,
        ``monsters`` and ``message`` replace its own for the boards after it."""
        cell, recorded_hp, listed, line = BOARDS[turn]
        cell = cell if player is None else player
        listed = listed if monsters is None else monsters
        line = line if message is None else message
        states = []
        for index, (name, y, x) in enumerate(listed, 1):
            race = self.races[name]
            knowledge = self.policy._monrace_knowledge[race]
            states.append(replace(
                monster(self.policy, index, race, (y, x)),
                distance=Position(*cell).distance_to(Position(y, x)), speed=knowledge.speed,
                level=knowledge.level, max_melee_damage=knowledge.max_melee_damage,
                max_ranged_damage=knowledge.max_ranged_damage, can_multiply=knowledge.can_multiply))
        snapshot = replace(on_floor(self.policy, self.board, cell, monsters=states,
                                    messages=(line,) if line else (), turn=turn), grids=self.grids)
        snapshot = replace(snapshot, player=replace(snapshot.player, hp=recorded_hp if hp is None else hp,
                                                    max_hp=MAX_HP))
        self.navigator = _navigator(self.policy, snapshot, QUEST)
        summon_response.observe(self.policy, snapshot)
        return snapshot

    def assert_goes_after(self, key, chased):
        self.assertIsNotNone(key)
        self.assertNotIn(self.policy.last_reason, DISENGAGE_REASONS)
        self.assertEqual(self.navigator.summon_state, quest_summon_answer.ENGAGING)
        self.assertEqual(self.navigator.summon_chase, chased)

    # -- the recorded boards -------------------------------------------------------------

    def test_the_withdrawal_line_is_the_plans(self):
        snapshot = self.board_at(8489035)
        self.assertAlmostEqual(quest_summon_answer._withdrawal_line(self.policy, snapshot), 0.4 * MAX_HP)

    def test_each_recorded_summon_goes_after_the_summoner(self):
        # (predicted damage, the summoner chased, the answer): of the three Dagons that share a name
        # the nearest is chased; each summoner is shot by the absorbed power aimed at its cell
        # (me_ranged_first, off the eight lines too), by Powerful Activation (385 an action against
        # 280 cast normally, me-powerful-attack-1119).  8489425's Bodak (350 HP) falls to that one
        # shot: it is the 2nd rule's killing shot (``next_action_kills``), with no chase after it.
        expected = {
            8488751: (107, 3, SHOT),
            8489035: (56, 1, SHOT),
            8489971: (138, 1, SHOT),
        }
        for turn, (damage, chased, reason) in expected.items():
            with self.subTest(turn=turn):
                self.setUp()
                snapshot = self.board_at(turn)
                death = threat_tiers.instant_death(self.policy, snapshot)
                self.assertFalse(death.holds)
                self.assertEqual(quest_summon_answer.predicted_damage(death), damage)
                self.assertTrue(summon_response.summoners_at_player(self.policy, snapshot))
                self.assertTrue(quest_summon_answer.bears_the_fight(self.policy, snapshot, death))
                key = quest_room_sweep.key(self.policy, snapshot)
                self.assertEqual(self.policy.last_reason, reason)
                self.assert_goes_after(key, chased)

    def test_a_summoner_the_next_shot_kills_is_shot_without_a_chase(self):
        snapshot = self.board_at(8489425)
        death = threat_tiers.instant_death(self.policy, snapshot)
        self.assertEqual(quest_summon_answer.predicted_damage(death), 55)
        bodak = summon_response.summoners_at_player(self.policy, snapshot)[0]
        self.assertTrue(quest_summon_answer.next_action_kills(self.policy, snapshot, bodak))
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual(self.policy.last_reason, SHOT)
        self.assertTrue(key.startswith("U"), key)
        self.assertIsNone(self.navigator.summon_state)

    def test_the_line_decides_on_a_recorded_board(self):
        # 8489035: 56 predicted; the line 451.2.  HP 508 leaves 452 (on); HP 507 leaves 451 (off).
        snapshot = self.board_at(8489035, hp=508)
        self.assert_goes_after(quest_room_sweep.key(self.policy, snapshot), 1)
        self.setUp()
        snapshot = self.board_at(8489035, hp=507)
        self.assertFalse(quest_summon_answer.bears_the_fight(self.policy, snapshot))
        quest_room_sweep.key(self.policy, snapshot)
        self.assertIn(self.policy.last_reason, DISENGAGE_REASONS)
        self.assertIsNone(self.navigator.summon_chase)

    def test_with_no_shot_the_summoner_is_walked_toward_off_both_sides(self):
        # DECLARED CONSTRUCTED: no shot in hand (both shot readers answer None).
        snapshot = self.board_at(8489035)
        navigator = _navigator(self.policy, snapshot, QUEST)
        plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        refused = quest_alignment_split.refused_cells(self.policy, snapshot, navigator, plan)
        with patch.object(me_ranged_first, "attack_key", return_value=None),                 patch.object(type(self.policy), "_ranged_attack_key", return_value=None):
            key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), ("6", quest_summon_answer.APPROACH_REASON))
        self.assertNotIn((14, 35), refused)

    # -- the boards after ----------------------------------------------------------------

    def test_the_chase_goes_on_while_the_line_holds(self):
        quest_room_sweep.key(self.policy, self.board_at(8489035))
        # The next board, one step east, no new summon: the Dagon stays the target.
        after = [("父なる『ダゴン』", 15, 38), ("メッツォデーモン", 15, 36), ("ボダック", 15, 35), ("メッツォデーモン", 15, 34)]
        key = quest_room_sweep.key(self.policy, self.board_at(8489035, player=(14, 35), monsters=after, message=""))
        self.assertEqual(self.policy.last_reason, SHOT)
        self.assert_goes_after(key, 1)

    def test_the_chase_breaks_off_below_the_line(self):
        key = quest_room_sweep.key(self.policy, self.board_at(8489971))
        self.assertEqual(self.policy.last_reason, SHOT)
        # The next board, the shot sent, no new summon, the HP one short of the line plus the
        # predicted damage there.  The plan's heal (heal_threshold_ratio 0.5) stands above the chase,
        # so the HP is kept at or above half for the disengage to be this board's answer.
        board = self.board_at(8489971, message="")
        damage = quest_summon_answer.predicted_damage(threat_tiers.instant_death(self.policy, board))
        line = quest_summon_answer._withdrawal_line(self.policy, board)
        hp = int(line + damage + 0.999) - 1
        self.assertGreaterEqual(hp, MAX_HP // 2)
        board = self.board_at(8489971, message="", hp=hp)
        self.assertFalse(quest_summon_answer.bears_the_fight(self.policy, board))
        quest_room_sweep.key(self.policy, board)
        self.assertIn(self.policy.last_reason, DISENGAGE_REASONS)
        self.assertNotEqual(self.navigator.summon_state, quest_summon_answer.ENGAGING)
        self.assertIsNone(self.navigator.summon_chase)
        # One more HP and the chase holds on the same board.
        self.setUp()
        quest_room_sweep.key(self.policy, self.board_at(8489971))
        key = quest_room_sweep.key(self.policy, self.board_at(8489971, message="", hp=hp + 1))
        self.assert_goes_after(key, 1)

    def test_the_next_summoner_then_the_summoned_then_the_steps_after(self):
        quest_room_sweep.key(self.policy, self.board_at(8489035))
        # The Dagon out of sight: the summoners of the group in sight, nearest first -- the
        # Mezzodemon (568, S_DEMON) and the Bodak (566, S_DEMON) both beside, the lower index.
        rest = [("メッツォデーモン", 15, 36), ("ボダック", 15, 35), ("メッツォデーモン", 15, 34)]
        snapshot = self.board_at(8489035, player=(14, 35), monsters=rest, message="")
        relabelled = [replace(m, index=i) for m, i in zip(snapshot.visible_monsters, (2, 3, 4))]
        snapshot = replace(snapshot, visible_monsters=relabelled)
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertTrue(self.policy._monrace_knowledge[566].can_summon)
        self.assertTrue(self.policy._monrace_knowledge[568].can_summon)
        self.assert_goes_after(key, 2)
        # None of the group in sight: the chase ends; the steps after a disengage take over the group
        # (here every member's last cell is looked at with nothing on it, so the group is gone too).
        empty = self.board_at(8489035, player=(14, 35), monsters=[], message="")
        quest_room_sweep.key(self.policy, empty)
        self.assertNotEqual(self.navigator.summon_state, quest_summon_answer.ENGAGING)
        self.assertIsNone(self.navigator.summon_chase)


    # -- the one being fought, and the unseen caster ---------------------------------------

    def test_a_nearly_dead_monster_beside_is_finished_before_the_chase(self):
        # 8489035 with the Mezzodemon beside at [15,33] wounded to 30 HP (as 8489305's nearly dead
        # Dagon, fought when a Mezzodemon summoned): the next blow kills it, so it is finished; the
        # Dagon is then the one chased.
        snapshot = self.board_at(8489035)
        wounded = replace(snapshot.visible_monsters[3], hp=30)
        snapshot = replace(snapshot, visible_monsters=[*snapshot.visible_monsters[:3], wounded])
        self.assertTrue(quest_summon_answer.next_action_kills(self.policy, snapshot, wounded))
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), ("1", quest_summon_answer.STRIKE_REASON))
        self.assertEqual(self.navigator.summon_state, quest_summon_answer.ENGAGING)
        self.assertEqual(self.navigator.summon_chase, 1)

    def test_an_unhurt_monster_the_blow_kills_waits_for_the_summoner(self):
        # DECLARED CONSTRUCTED: the same Mezzodemon unhurt at 300 HP of 300 (the blow's 396 kills it):
        # no fight under way with it, so the summoner is shot.
        snapshot = self.board_at(8489035)
        unhurt = replace(snapshot.visible_monsters[3], hp=300, max_hp=300)
        snapshot = replace(snapshot, visible_monsters=[*snapshot.visible_monsters[:3], unhurt])
        self.assertTrue(quest_summon_answer.next_action_kills(self.policy, snapshot, unhurt))
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual(self.policy.last_reason, SHOT)
        self.assert_goes_after(key, 1)

    def unseen_cast(self, turn):
        """RECONSTRUCTED: 8489116 (the Cleaners awake in view, an ant summon by a caster not seen)."""
        listed = [("『究極ダンジョン=クリーナー』", 14, 66), ("『究極ダンジョン=クリーナー』", 14, 71), ("アーチ=ヴァイル", 15, 47)]
        BOARDS[turn] = ((12, 66), 1128, listed, "何かが魔法でアリを召喚した。")
        self.addCleanup(BOARDS.pop, turn)
        return self.board_at(turn)

    def test_an_unseen_summoner_is_left_by_the_absorbed_teleportation(self):
        # Owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」: rule 2's leave
        # (the second unseen cast) casts the absorbed Teleportation before the scroll on Quest 33.
        self.unseen_cast(8489100)
        snapshot = self.unseen_cast(8489116)
        self.assertEqual(summon_response.summoners_at_player(self.policy, snapshot), [])
        self.assertTrue(summon_response.leave_due(self.policy, snapshot))
        key = summon_response.leave_key(self.policy, snapshot)
        power = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
        self.assertEqual((key, self.policy.last_reason),
                         (power.key, summon_response.LEAVE_REASON + me_absorbed_substitutes.CAST_SUFFIX))

    def test_an_unseen_summoner_without_the_power_reads_the_scroll(self):
        summon_answer_tests.Quest33SummonAnswerTest.without_absorbed_teleportation(self)
        self.unseen_cast(8489100)
        snapshot = self.unseen_cast(8489116)
        key = summon_response.leave_key(self.policy, snapshot)
        self.assertEqual(self.policy.last_reason, summon_response.LEAVE_REASON)
        self.assertTrue(key.startswith("r"))


if __name__ == "__main__":
    unittest.main()
