"""door_detect_cover: the walls a door detection of this floor visit reached count as searched.

Owner 2026-11-25 「感知が届いた壁はサーチせず溶かして出る」.  Constructed boards (SimpleNamespace):
the module reads only the floor, the turn, the player's cell and the pack.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from types import SimpleNamespace

from hengbot import door_detect_cover, me_powers
from hengbot.model import (
    SV_ROD_DETECTION, SV_SCROLL_DETECT_DOOR, SV_STAFF_DETECT_DOOR, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF,
    Position,
)

FLOOR = (14, 50, 0)


def _item(tval, sval, *, count=1, charges=0, charging=False, charging_count=None):
    return SimpleNamespace(tval=tval, sval=sval, count=count, charges=charges, aware=True,
                           charging=charging, charging_count=charging_count)


def _board(turn, cell, inventory, floor=FLOOR):
    return SimpleNamespace(in_town=False, dungeon_level=floor[1], floor_key=floor, turn=turn,
                           player=SimpleNamespace(position=Position(*cell)), inventory=inventory)


def _policy(darkness=False):
    flags = {"DARKNESS"} if darkness else set()
    return SimpleNamespace(_floor_key=FLOOR,
                           _dungeon_knowledge={FLOOR[0]: SimpleNamespace(flags=flags)})


class CarriedUseTest(unittest.TestCase):
    def _cast(self, before, after, *, policy=None, moved=False):
        policy = policy or _policy()
        door_detect_cover.observe(policy, _board(100, (38, 192), before))
        door_detect_cover.observe(policy, _board(103, (38, 193) if moved else (38, 192), after))
        return policy

    def test_a_staff_charge_spent_is_a_cast_at_the_default_radius(self):
        policy = self._cast([_item(TVAL_STAFF, SV_STAFF_DETECT_DOOR, charges=5)],
                            [_item(TVAL_STAFF, SV_STAFF_DETECT_DOOR, charges=4)])
        self.assertTrue(door_detect_cover.covered(policy, (38 + 30, 192)))
        self.assertFalse(door_detect_cover.covered(policy, (38 + 31, 192)))

    def test_the_last_scroll_read_is_a_cast(self):
        policy = self._cast([_item(TVAL_SCROLL, SV_SCROLL_DETECT_DOOR)], [])
        self.assertTrue(door_detect_cover.covered(policy, (40, 200)))

    def test_a_rod_gone_charging_is_a_cast(self):
        policy = self._cast([_item(TVAL_ROD, SV_ROD_DETECTION)],
                            [_item(TVAL_ROD, SV_ROD_DETECTION, charging=True)])
        self.assertTrue(door_detect_cover.covered(policy, (40, 200)))

    def test_a_darkness_dungeon_detects_a_third(self):
        policy = self._cast([_item(TVAL_STAFF, SV_STAFF_DETECT_DOOR, charges=5)],
                            [_item(TVAL_STAFF, SV_STAFF_DETECT_DOOR, charges=4)],
                            policy=_policy(darkness=True))
        self.assertTrue(door_detect_cover.covered(policy, (48, 192)))
        self.assertFalse(door_detect_cover.covered(policy, (49, 192)))

    def test_no_change_or_a_move_is_no_cast(self):
        staff = [_item(TVAL_STAFF, SV_STAFF_DETECT_DOOR, charges=5)]
        policy = self._cast(staff, staff)
        self.assertFalse(door_detect_cover.covered(policy, (38, 192)))
        policy = self._cast(staff, [_item(TVAL_STAFF, SV_STAFF_DETECT_DOOR, charges=4)], moved=True)
        self.assertFalse(door_detect_cover.covered(policy, (38, 192)))

    def test_another_floor_forgets_the_casts(self):
        policy = self._cast([_item(TVAL_SCROLL, SV_SCROLL_DETECT_DOOR)], [])
        policy._floor_key = (14, 51, 0)
        self.assertFalse(door_detect_cover.covered(policy, (38, 192)))
        door_detect_cover.observe(policy, _board(200, (10, 10), [], floor=(14, 51, 0)))
        policy._floor_key = (14, 51, 0)
        self.assertFalse(door_detect_cover.covered(policy, (10, 10)))

    def test_around_covered_needs_every_neighbour(self):
        policy = self._cast([_item(TVAL_SCROLL, SV_SCROLL_DETECT_DOOR)], [])
        self.assertTrue(door_detect_cover.around_covered(policy, Position(38 + 29, 192)))
        self.assertFalse(door_detect_cover.around_covered(policy, Position(38 + 30, 192)))


class AbsorbedUseTest(unittest.TestCase):
    def _policy_with_uses(self, *uses):
        policy = _policy()
        memory = me_powers.FloorMemory(FLOOR, 100)
        memory.uses.extend(uses)
        setattr(policy, me_powers.MEMORY, memory)
        return policy

    def test_absorbed_detect_doors_and_powerful_detection(self):
        doors = me_powers.Use(("staff", SV_STAFF_DETECT_DOOR), ("staff", SV_STAFF_DETECT_DOOR),
                              "before-secret-search", Position(38, 192), 90,
                              "me-power:before-secret-search:detect-doors-stairs")
        detection = me_powers.Use(("rod", SV_ROD_DETECTION), ("rod", SV_ROD_DETECTION),
                                  "deep-explore-redetect", Position(10, 10), 95,
                                  "me-power:deep-explore-redetect:detect-all:powerful")
        policy = self._policy_with_uses(doors, detection)
        self.assertEqual(me_powers.door_detections(policy, _board(100, (0, 0), [])),
                         ((Position(38, 192), 30, 90), (Position(10, 10), 45, 95)))
        door_detect_cover.observe(policy, _board(100, (0, 0), []))
        self.assertTrue(door_detect_cover.covered(policy, (10 + 45, 10)))
        self.assertFalse(door_detect_cover.covered(policy, (10 + 46, 10)))
        door_detect_cover.observe(policy, _board(101, (0, 0), []))
        self.assertEqual(len(door_detect_cover.casts(policy, _board(101, (0, 0), []))), 2)


class UndersearchedWallsTest(unittest.TestCase):
    def test_a_covered_wall_is_not_undersearched(self):
        from collections import Counter

        import hengbot.policy  # noqa: F401 -- policy_navigation is imported through it
        from hengbot.policy_navigation import NavigationMixin

        policy = SimpleNamespace(_floor_key=FLOOR, _search_counts=Counter(),
                                 _wall_search_counts=Counter(),
                                 _remembered_wall_t={(5, 4), (5, 40)})
        self.assertEqual(NavigationMixin._undersearched_walls(policy, Position(5, 5)), [(5, 4)])
        setattr(policy, door_detect_cover.MEMORY,
                door_detect_cover.Cover(FLOOR, [(Position(5, 0), 30, 1)]))
        self.assertEqual(NavigationMixin._undersearched_walls(policy, Position(5, 5)), [])
        self.assertEqual(NavigationMixin._undersearched_walls(policy, Position(5, 41)), [(5, 40)])


if __name__ == "__main__":
    unittest.main()
