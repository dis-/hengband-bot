"""QUEST_33 (クローン地獄): the answer to a summon received (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「召喚を受ける機会が多いクエストである。召喚を何度受けても放棄しない。即死は
テレポートで離脱。即死でなく、次の一行動で召喚主を倒す見込みがあるなら戦闘。無理なら離脱。離脱後の作戦は
別途用意すること。」

DECLARED CONSTRUCTED: every board below is the recorded n1-b town arrival of 2026-11-19
(tests/fixtures/quest32-one-turn-kill-1119, Magic-Eater Lv50, speed +25, 15 Scrolls of
Teleportation in slot e) moved onto the Q33 floor (tests/test_quest33_alignment_split.on_floor), with
the map's terrain given as known grids (the quest map read by quest_knowledge: walls and trees stop a
line, the pits and lavas pass it, the locked doors are closed), one summoner of the quest's roster in
view and its summon line on the board.  The summoner's HP is lowered where the test says "wounded";
the 即死 board lowers the player's HP to 30 and gives the Dagon the game's per-monster maximum melee
of 300 (the board's ``max_melee_damage``, which threat_prediction reads; the constructed monster
carries 0 otherwise).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace

from hengbot import (
    me_absorbed_substitutes,
    me_capability,
    quest_alignment_split,
    quest_room_sweep,
    quest_summon_answer,
    summon_response,
    threat_tiers,
)
from hengbot.model import SV_STAFF_TELEPORTATION, GridState, Position
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import DAGON, QUEEN, QUEST, monster, on_floor, quest_dir, recorded

TAILS = {QUEEN: "が魔法でアリを召喚した。", DAGON: "が魔法で仲間を召喚した。"}


class Quest33SummonAnswerTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, self.board = recorded("n1b-411")
        self.addCleanup(self.scratch.cleanup)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.turn = 100
        self.grids = self._grids()

    def _grids(self):
        """The quest map as known grids (module docstring)."""
        navigator = _navigator(self.policy, on_floor(self.policy, self.board, (13, 39)), QUEST)
        grids = {}
        for (y, x), kind in navigator.battlefield.terrain.items():
            sight = kind in quest_alignment_split._SIGHT_KINDS
            door = kind == "door"
            grids[Position(y, x)] = GridState(
                position=Position(y, x), known=True,
                passable=kind in {"floor", "exit", "passage", "shallow_water"},
                wall=not sight and not door, has_monster=False, has_down_stairs=False,
                has_up_stairs=kind == "exit", unsafe=False, is_closed_door=door, is_door=door,
                allows_los=sight)
        return grids

    def board_of(self, player, race, cell, *, hp=None, player_hp=None, max_melee=0, summoned=True):
        """DECLARED CONSTRUCTED (module docstring); observed as the policy observes every board."""
        self.turn += 1
        summoner = monster(self.policy, 1, race, cell)
        summoner = replace(summoner, distance=Position(*player).distance_to(Position(*cell)),
                           hp=summoner.hp if hp is None else hp,
                           max_melee_damage=max_melee or summoner.max_melee_damage)
        name = self.policy._monrace_knowledge[race].names[0]
        messages = (f"{name}{TAILS[race]}",) if summoned else ()
        snapshot = replace(on_floor(self.policy, self.board, player, monsters=(summoner,),
                                    messages=messages, turn=self.turn), grids=self.grids)
        if player_hp is not None:
            snapshot = replace(snapshot, player=replace(snapshot.player, hp=player_hp))
        self.navigator = _navigator(self.policy, snapshot, QUEST)
        summon_response.observe(self.policy, snapshot)
        return snapshot

    def test_the_shipped_plan_answers_summons(self):
        self.assertEqual(self.plan["summon_answer"], quest_summon_answer.KILL_OR_DISENGAGE)
        self.assertNotIn("facing_casts_to_abort", self.plan["alignment_split"])

    def test_a_summon_received_is_named(self):
        snapshot = self.board_of((15, 38), DAGON, (15, 41))
        self.assertEqual([m.race_id for m in summon_response.summoners_at_player(self.policy, snapshot)], [DAGON])

    def without_absorbed_teleportation(self):
        """DECLARED CONSTRUCTED: n1-b's absorption record and displayed staff list without the
        Teleportation row (a Magic-Eater that never absorbed it)."""
        sequence = self.policy._me_staff_sequence
        sequence.absorbed = {name: count for name, count in sequence.absorbed.items()
                             if name != me_capability.record_key("staff", SV_STAFF_TELEPORTATION)}
        lists = dict(getattr(self.policy, "_me_device_lists", None) or {})
        if "staff" in lists:
            names = me_capability.names("staff", SV_STAFF_TELEPORTATION)
            turn, rows = lists["staff"][0], lists["staff"][1]
            lists["staff"] = (turn, [row for row in rows if row.get("name") not in names], *lists["staff"][2:])
        self.policy._me_device_lists = lists

    def test_instant_death_casts_the_absorbed_teleportation(self):
        # Owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」: n1-b holds it (34 charges).
        snapshot = self.board_of((15, 38), DAGON, (15, 39), player_hp=30, max_melee=300)
        self.assertTrue(threat_tiers.instant_death(self.policy, snapshot).holds)
        key = quest_room_sweep.key(self.policy, snapshot)
        power = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
        self.assertEqual((key, self.policy.last_reason),
                         (power.key, quest_summon_answer.TELEPORT_REASON + me_absorbed_substitutes.CAST_SUFFIX))
        self.assertEqual(self.navigator.summon_state, quest_summon_answer.DISENGAGED)

    def test_instant_death_reads_teleportation_without_the_power(self):
        self.without_absorbed_teleportation()
        snapshot = self.board_of((15, 38), DAGON, (15, 39), player_hp=30, max_melee=300)
        self.assertFalse(me_capability.has(self.policy, snapshot, "staff", SV_STAFF_TELEPORTATION))
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), ("re", quest_summon_answer.TELEPORT_REASON))
        self.assertEqual(self.navigator.summon_state, quest_summon_answer.DISENGAGED)

    def test_a_summoner_the_next_blow_kills_is_struck(self):
        # Wounded to 50 HP, beside the player: 367 a blow turn against the Dagon's 50.
        snapshot = self.board_of((15, 38), DAGON, (15, 39), hp=50)
        target = snapshot.visible_monsters[0]
        self.assertTrue(quest_summon_answer.next_action_kills(self.policy, snapshot, target))
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), ("6", quest_summon_answer.STRIKE_REASON))
        self.assertIsNone(self.navigator.summon_state)

    def test_a_summoner_the_next_shot_kills_is_shot(self):
        # Wounded to 50 HP, four cells east: the absorbed attack power's one use.
        snapshot = self.board_of((15, 38), DAGON, (15, 42), hp=50)
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertTrue(key.startswith("m"))
        self.assertIsNone(self.navigator.summon_state)

    def test_an_unhurt_summoner_beside_is_disengaged_from_on_foot(self):
        # The Dagon at 1881 HP: no single action kills it.  [14,37] is out of its line one step away.
        snapshot = self.board_of((15, 38), DAGON, (15, 41))
        self.assertFalse(quest_summon_answer.next_action_kills(self.policy, snapshot, snapshot.visible_monsters[0]))
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), ("7", quest_summon_answer.DISENGAGE_WALK_REASON))
        self.assertEqual(self.navigator.summon_state, quest_summon_answer.DISENGAGING)
        # The next board, one step north-west, no new summon: out of the Dagon's line, so disengaged.
        after = self.board_of((14, 37), DAGON, (15, 41), summoned=False)
        quest_room_sweep.key(self.policy, after)
        self.assertEqual(self.navigator.summon_state, quest_summon_answer.DISENGAGED)

    def test_with_no_short_way_out_the_absorbed_teleportation_is_cast(self):
        # The open corridor of row 14: no cell out of the Dagon's line within three steps.
        snapshot = self.board_of((14, 30), DAGON, (14, 34))
        key = quest_room_sweep.key(self.policy, snapshot)
        power = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
        self.assertEqual((key, self.policy.last_reason),
                         (power.key, quest_summon_answer.DISENGAGE_TELEPORT_REASON + me_absorbed_substitutes.CAST_SUFFIX))
        self.assertEqual(self.navigator.summon_state, quest_summon_answer.DISENGAGED)
        # The summoner is the group the steps after the disengage reduce.
        self.assertEqual(self.navigator.summon_group, {1: (DAGON, (14, 34), True)})

    def test_with_no_short_way_out_and_no_power_the_scroll_is_read(self):
        self.without_absorbed_teleportation()
        snapshot = self.board_of((14, 30), DAGON, (14, 34))
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), ("re", quest_summon_answer.DISENGAGE_TELEPORT_REASON))
        self.assertEqual(self.navigator.summon_state, quest_summon_answer.DISENGAGED)

    def test_three_summons_never_read_recall(self):
        for _ in range(4):
            snapshot = self.board_of((15, 38), QUEEN, (15, 42))
        self.assertGreaterEqual(summon_response._memory(self.policy).summons, summon_response.SUMMONS_TO_RECALL)
        self.assertTrue(quest_summon_answer.never_abandons(self.policy, snapshot))
        self.assertFalse(summon_response.recall_due(self.policy, snapshot))
        self.assertIsNone(summon_response.recall_key(self.policy, snapshot))
        quest_room_sweep.key(self.policy, snapshot)
        self.assertNotIn("recall", self.policy.last_reason or "")

    def test_the_sides_summoning_at_each_other_no_longer_give_up(self):
        summon_response._memory(self.policy).facing = 5
        self.assertFalse(quest_alignment_split.abort_due(self.policy, self.plan))


if __name__ == "__main__":
    unittest.main()
