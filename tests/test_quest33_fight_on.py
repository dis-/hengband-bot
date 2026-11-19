"""QUEST_33 (クローン地獄): no stair escape; the fight goes on (owner 2026-11-19).

Owner 2026-11-19, verbatim answer 「階段へ逃げず戦い続ける」 to: on Q33, with the absorbed Teleportation,
the scrolls and the healing potions all gone and the board 即死, what then?  The generic emergency
walked to the up staircase (``emergency:seek-upstairs``) and the '<' on it fails the ONCE quest
(quest.cpp leave_quest_check).  On Quest 33 no escape of the emergency ladder leaves the level by a
staircase -- the walk to the up stair, the '<' (the panic release of the floor's exit lock no longer
opens it), and the plan's own exit walk with no Healing left (``exit_when_out_of_healing`` taken off
QUEST_33) -- and the player fights on: the blow at a monster beside him, else the plan's fight.
Teleportation (absorbed first) and the potions are still used while they last.

DECLARED CONSTRUCTED: the recorded n1-b town arrival of 2026-11-19 (tests/fixtures/
quest32-one-turn-kill-1119) on the Q33 floor with the quest map as known grids
(tests/test_quest33_summon_answer), the absorbed Teleportation taken out of its record, every
Teleportation scroll and every potion taken out of the pack, HP 30, at [14,40] beside the quest's
up staircase [13,39], with a Dagon beside ([15,41]) carrying the game's per-monster maximum melee
300 (the board's ``max_melee_damage``; the constructed monster carries 0 otherwise), so the board is
即死.  The n1-b board of the report (the q33-no-scroll-recall-1119 branch's run) is not recorded in
this tree; this board stands for it.  The control turns the owner's rule off (``FIGHT_ON_QUESTS``
emptied, the plan's exit walk put back) and the same board walks to the stair.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import quest_summon_answer, threat_tiers
from hengbot.model import Position, TVAL_POTION
from hengbot.policy_constants import UP_STAIRS_KEY
from tests import test_quest33_summon_answer as summon_tests
from tests.test_quest33_alignment_split import DAGON, QUEST

STAIR = (13, 39)
STAIR_REASONS = ("emergency:seek-upstairs", "emergency:stairs", "emergency:stairs-quest-fail",
                 "flee:stairs", "flee:stairs-quest-fail", "flee:seek-upstairs", "quest-strategy:sweep-exit",
                 "quest-strategy:sweep-exit-walk")


class Quest33FightOnTest(summon_tests.Quest33SummonAnswerTest):
    """The summon-answer floor boards (module docstring); its own tests are not re-run here."""

    def nothing_left(self, cell=(14, 40), player=(14, 40)):
        """DECLARED CONSTRUCTED (module docstring)."""
        self.without_absorbed_teleportation()
        snapshot = self.board_of(player, DAGON, (15, 41), player_hp=30, max_melee=300, summoned=False)
        inventory = [item for item in snapshot.inventory
                     if not (self.policy._find_teleport_scroll(replace(snapshot, inventory=[item])) is not None
                             or item.tval == TVAL_POTION)]
        return replace(snapshot, inventory=inventory)

    def assert_no_stair(self, snapshot, key):
        self.assertNotIn(self.policy.last_reason, STAIR_REASONS, key)
        self.assertNotEqual(key, UP_STAIRS_KEY)
        here = snapshot.player.position
        stair = Position(*STAIR)
        if key in {"7", "8", "9", "4", "6", "1", "2", "3"} and "attack" not in (self.policy.last_reason or ""):
            self.fail(f"a step {key} ({self.policy.last_reason}) on a 即死 board from {here} toward {stair}")

    def test_the_shipped_plan_takes_no_exit_walk(self):
        plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.assertFalse(plan.get("exit_when_out_of_healing", False))
        self.assertIn(QUEST, quest_summon_answer.FIGHT_ON_QUESTS)

    def test_instant_death_with_nothing_left_fights_on(self):
        snapshot = self.nothing_left()
        self.assertTrue(threat_tiers.instant_death(self.policy, snapshot).holds)
        self.assertIsNone(self.policy._find_teleport_scroll(snapshot))
        key = self.policy.choose_key(snapshot)
        self.assert_no_stair(snapshot, key)
        # The Dagon beside is struck.
        self.assertEqual(key, "3", self.policy.last_reason)

    def test_on_the_stair_the_up_key_is_not_pressed(self):
        snapshot = self.nothing_left(player=STAIR)
        key = self.policy.choose_key(snapshot)
        self.assert_no_stair(snapshot, key)

    def test_control_without_the_rule_walks_to_the_stair(self):
        # Revert-proof: the owner's rule off, the same board leaves by the stair.
        plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        snapshot = self.nothing_left()
        with patch.object(quest_summon_answer, "FIGHT_ON_QUESTS", frozenset()), \
                patch.dict(plan, {"exit_when_out_of_healing": True}):
            self.policy.choose_key(snapshot)
            self.assertIn(self.policy.last_reason, STAIR_REASONS)


# The base class's own tests run in their module; here only this module's.
for _name in [name for name in vars(summon_tests.Quest33SummonAnswerTest) if name.startswith("test_")]:
    setattr(Quest33FightOnTest, _name, None)


if __name__ == "__main__":
    unittest.main()
