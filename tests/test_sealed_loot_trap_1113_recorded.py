"""The traps on the way into a walled pocket of loot are cleared before its walls are melted.

Owner 2026-11-13 (問い1): 「トラップ破壊かトラップ解除があればそれを優先。なければ壁を溶かす。」
n1-c life-205 (Orc cave 23F, 13:10-13:18): the lower left room's loot (24,86) lay one detected
trap, (23,87), from the cross's centre (22,88), which the walk reaches; the walk does not cross
traps, and the stuck escape read Recall at 13:18:29.  Now sealed_loot walks that trap route and
clears the trap (an absorbed disarming power, then a carried rod or wand, then the disarm
command); only with no way left to clear it does the Stone to Mud melt run.

Recorded: tests/fixtures/sealed-loot-melt-1113.jsonl.gz (the melt cases' window and helpers,
tests/test_sealed_loot_melt_1113_recorded.py); here the room's trap keeps its disarm presses
(``stuck(spent=False)``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from contextlib import ExitStack
from unittest import mock

from hengbot import sealed_loot
from hengbot.model import SV_WAND_TRAP_DOOR_DEST, parse_snapshot
from hengbot.policy_constants import CHEST_DISARM_BUDGET
from tests import test_sealed_loot_melt_1113_recorded as melt
from tests.support import recorded

# DECLARED CONSTRUCTED: the player at the cross's centre, beside the room's trap (south west).
BESIDE_THE_TRAP = (22, 88)


class SealedLootTrap1113RecordedTest(recorded.RecordedHarness):
    setUpClass = classmethod(melt.SealedLootMelt1113RecordedTest.setUpClass.__func__)
    stuck = melt.SealedLootMelt1113RecordedTest.stuck
    decide = melt.SealedLootMelt1113RecordedTest.decide

    def beside_the_trap(self, **kwargs):
        policy, raw = self.stuck(spent=False, **kwargs)
        raw["player"]["y"], raw["player"]["x"] = BESIDE_THE_TRAP
        return policy, raw

    def carry_trap_wand(self, raw):
        """DECLARED CONSTRUCTED: the carried Stone to Mud wand made a wand of Trap/Door
        Destruction (its slot and charges kept); kept carried by ``unabsorbed``."""
        wand = next(item for item in raw["inventory"]
                    if (item["tval"], item["sval"]) == melt.STONE_TO_MUD)
        wand["sval"] = SV_WAND_TRAP_DOOR_DEST
        return wand

    def test_the_stuck_escape_walks_the_trap_route_not_to_the_wall(self):
        policy, raw = self.stuck(spent=False)
        self.assertEqual((self.live["reason"], self.live["key"]), ("stuck:recall-escape", "rk"))
        snapshot = parse_snapshot(copy.deepcopy(raw), self.monrace)
        reach = sealed_loot._reach(policy, snapshot)
        route = sealed_loot.trap_route(policy, snapshot, reach,
                                       set().union(*sealed_loot.pockets(policy, snapshot, reach)))
        self.assertEqual(route[-2:], [melt.ROOM_TRAP, melt.Position(24, 86)])
        key, reason = self.decide(policy, raw)
        self.assertEqual((key, reason), ("8", sealed_loot.TRAP_REASON))
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), ["8"])

    def test_the_walk_holds_the_stuck_count_for_the_next_board(self):
        policy, raw = self.stuck(spent=False)
        key, _reason = self.decide(policy, raw)
        policy.confirm_key_posted(key)
        streak = policy._stuck_escape_streak
        self.assertEqual(self.decide(policy, self.later(raw)), ("8", sealed_loot.TRAP_REASON))
        self.assertEqual(policy._stuck_escape_streak, streak)

    def unabsorbed(self):
        """DECLARED CONSTRUCTED: the Magic Eater's absorb step leaves the carried wand (a
        class that cannot absorb it carries it so)."""
        stack = ExitStack()
        for owner in ("hengbot.magic_eater.absorb_key", "hengbot.policy_quest.absorb_key"):
            stack.enter_context(mock.patch(owner, lambda *args, **kwargs: None))
        return stack

    def test_beside_the_trap_the_absorbed_power_comes_before_a_carried_wand(self):
        """The life's ~f list holds トラップ解除 and トラップ/ドア破壊."""
        policy, raw = self.beside_the_trap(absorbed=True)
        self.carry_trap_wand(raw)
        with self.unabsorbed():
            self.assertEqual(self.decide(policy, raw),
                             ("mBe1", "me-power:trap-to-disarm:disarm-trap"))

    def test_a_carried_trap_door_destruction_wand_before_the_hand(self):
        policy, raw = self.beside_the_trap()
        wand = self.carry_trap_wand(raw)
        with self.unabsorbed():
            self.assertEqual(self.decide(policy, raw), ("a" + wand["slot"] + "1",
                                                        sealed_loot.TRAP_REASON + sealed_loot.DEVICE_SUFFIX))

    def test_by_hand_the_disarm_command_presses_then_the_wall_melts(self):
        policy, raw = self.beside_the_trap()
        for _press in range(CHEST_DISARM_BUDGET):
            self.assertEqual(self.decide(policy, raw), ("D1", sealed_loot.TRAP_REASON))
        _key, reason = self.decide(policy, raw)
        self.assertEqual(reason, sealed_loot.REASON)

    def test_a_refused_device_use_never_walks_onto_the_spent_trap(self):
        """Declared constructed: the trap's presses spent, a carried wand counted as a way to
        clear it, and its use refused (the item command composes nothing): the melt, never a
        step onto the trap (policy_navigation _step_toward walks on past the presses)."""
        policy, raw = self.beside_the_trap()
        policy._floor_trap_disarm_attempts[(melt.ROOM_TRAP.y, melt.ROOM_TRAP.x)] = CHEST_DISARM_BUDGET
        self.carry_trap_wand(raw)
        with self.unabsorbed(), mock.patch.object(sealed_loot, "reserved_item_command",
                                                  lambda *args, **kwargs: None):
            _key, reason = self.decide(policy, raw)
        self.assertNotEqual(reason, sealed_loot.TRAP_REASON)

    def test_without_stone_to_mud_the_trap_is_still_cleared(self):
        policy, raw = self.beside_the_trap()
        raw["inventory"] = [item for item in raw["inventory"]
                            if (item["tval"], item["sval"]) != melt.STONE_TO_MUD]
        self.assertEqual(self.decide(policy, raw), ("D1", sealed_loot.TRAP_REASON))


if __name__ == "__main__":
    import unittest
    unittest.main()
