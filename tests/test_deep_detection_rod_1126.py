"""deep_detection_rod and door_detect_cover's trap record (owner 2026-11-26 「50F以降は全感知のロッドを持つ」).

Constructed boards (SimpleNamespace): door_detect_cover reads the floor, the turn, the player's cell
and the pack; deep_detection_rod's predicates read the depth, the recall depths, the pack and the
board's ``unsafe_rows``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from types import SimpleNamespace
from unittest import mock

from hengbot import deep_detection_rod, door_detect_cover, me_powers
from hengbot.model import (
    SV_ROD_DETECT_DOOR, SV_ROD_DETECTION, SV_SCROLL_DETECT_TRAP, SV_STAFF_DETECT_DOOR,
    SV_STAFF_DETECT_TRAP, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, Position,
)

FLOOR = (1, 50, 0)


def _item(tval, sval, *, count=1, charges=0, charging=False, charging_count=None):
    return SimpleNamespace(tval=tval, sval=sval, count=count, charges=charges, aware=True,
                           charging=charging, charging_count=charging_count)


def _board(turn, cell, inventory, *, depth=50, recall=None, unsafe=None, in_town=False):
    return SimpleNamespace(
        in_town=in_town, dungeon_level=depth, floor_key=(1, depth, 0), turn=turn,
        player=SimpleNamespace(position=Position(*cell), blind=False, confused=False,
                               hallucinated=False, recalling=False, class_id=0),
        inventory=inventory, unsafe_rows=unsafe, unsafe_rows_malformed=False, store=None,
        dungeon_recall_depths=recall or {}, recall_depth=0, messages=())


def _policy():
    return SimpleNamespace(_floor_key=FLOOR, _home_knowledge_items=(),
                           _dungeon_knowledge={FLOOR[0]: SimpleNamespace(flags=set())},
                           _walkable_neighbors=lambda snapshot, pos: [Position(pos.y + 1, pos.x)])


class TrapRecordTest(unittest.TestCase):
    def _cast(self, before, after):
        policy = _policy()
        door_detect_cover.observe(policy, _board(100, (20, 20), before))
        door_detect_cover.observe(policy, _board(103, (20, 20), after))
        return policy

    def test_a_rod_of_detection_gone_charging_detects_traps_and_doors(self):
        policy = self._cast([_item(TVAL_ROD, SV_ROD_DETECTION)],
                            [_item(TVAL_ROD, SV_ROD_DETECTION, charging=True)])
        self.assertTrue(door_detect_cover.trap_covered(policy, (20 + 30, 20)))
        self.assertFalse(door_detect_cover.trap_covered(policy, (20 + 31, 20)))
        self.assertTrue(door_detect_cover.covered(policy, (20 + 30, 20)))

    def test_trap_only_and_door_only_detections(self):
        policy = self._cast([_item(TVAL_STAFF, SV_STAFF_DETECT_TRAP, charges=5)],
                            [_item(TVAL_STAFF, SV_STAFF_DETECT_TRAP, charges=4)])
        self.assertTrue(door_detect_cover.trap_covered(policy, (20, 20)))
        self.assertFalse(door_detect_cover.covered(policy, (20, 20)))
        policy = self._cast([_item(TVAL_SCROLL, SV_SCROLL_DETECT_TRAP)], [])
        self.assertTrue(door_detect_cover.trap_covered(policy, (20, 20)))
        policy = self._cast([_item(TVAL_ROD, SV_ROD_DETECT_DOOR)],
                            [_item(TVAL_ROD, SV_ROD_DETECT_DOOR, charging=True)])
        self.assertTrue(door_detect_cover.covered(policy, (20, 20)))
        self.assertFalse(door_detect_cover.trap_covered(policy, (20, 20)))

    def test_an_absorbed_detection_is_a_trap_detection(self):
        policy = _policy()
        memory = me_powers.FloorMemory(FLOOR, 100)
        memory.uses.append(me_powers.Use(("rod", SV_ROD_DETECTION), ("rod", SV_ROD_DETECTION),
                                         "deep-undetected-step", Position(10, 10), 95,
                                         "me-power:deep-undetected-step:detect-all"))
        memory.uses.append(me_powers.Use(("staff", SV_STAFF_DETECT_DOOR), ("staff", SV_STAFF_DETECT_DOOR),
                                         "before-secret-search", Position(30, 30), 96,
                                         "me-power:before-secret-search:detect-doors-stairs"))
        setattr(policy, me_powers.MEMORY, memory)
        self.assertEqual(me_powers.trap_detections(policy, _board(100, (0, 0), [])),
                         ((Position(10, 10), 30, 95),))

    def test_a_record_pickled_before_the_trap_record_reads_none(self):
        policy = _policy()
        cover = door_detect_cover.Cover(FLOOR)
        del cover.__dict__["traps"]
        setattr(policy, door_detect_cover.MEMORY, cover)
        self.assertFalse(door_detect_cover.trap_covered(policy, (1, 1)))


class RuleTest(unittest.TestCase):
    def test_applies_from_the_recall_depth_or_the_floor(self):
        self.assertTrue(deep_detection_rod.applies(_board(1, (0, 0), [], depth=0, in_town=True,
                                                          recall={1: 50})))
        self.assertFalse(deep_detection_rod.applies(_board(1, (0, 0), [], depth=0, in_town=True,
                                                           recall={1: 49, 2: 30})))
        self.assertTrue(deep_detection_rod.applies(_board(1, (0, 0), [], depth=51)))

    def test_undetected_step_reads_the_board_then_the_trap_record(self):
        policy = _policy()
        safe = tuple(tuple(False for _ in range(40)) for _ in range(40))
        unsafe_below = tuple(tuple(y == 21 for _ in range(40)) for y in range(40))
        self.assertFalse(deep_detection_rod.undetected_step(policy, _board(1, (20, 20), [], unsafe=safe)))
        self.assertTrue(deep_detection_rod.undetected_step(
            policy, _board(1, (20, 20), [], unsafe=unsafe_below)))
        # Without the rows: the trap record.
        self.assertTrue(deep_detection_rod.undetected_step(policy, _board(1, (20, 20), [])))
        setattr(policy, door_detect_cover.MEMORY,
                door_detect_cover.Cover(FLOOR, traps=[(Position(20, 20), 30, 1)]))
        self.assertFalse(deep_detection_rod.undetected_step(policy, _board(1, (20, 20), [])))

    def test_the_absorbed_rod_s_trigger(self):
        board = _board(1, (20, 20), [], unsafe=tuple(tuple(True for _ in range(40)) for _ in range(40)))
        ctx = SimpleNamespace(policy=_policy(), snapshot=board)
        power = me_powers.BY_KEY[("rod", SV_ROD_DETECTION)]
        self.assertIn("deep-undetected-step", power.triggers)
        self.assertTrue(me_powers.TRIGGERS["deep-undetected-step"].due(ctx, power))
        shallow = SimpleNamespace(policy=ctx.policy, snapshot=_board(1, (20, 20), [], depth=49,
                                                                    unsafe=board.unsafe_rows))
        self.assertFalse(me_powers.TRIGGERS["deep-undetected-step"].due(shallow, power))

    def test_a_charging_rod_on_a_shallow_floor_is_not_waited_for(self):
        policy = _policy()
        rod = _item(TVAL_ROD, SV_ROD_DETECTION, charging=True, charging_count=1)
        with mock.patch.object(me_powers, "utility_device_permitted", return_value=True):
            self.assertIsNone(deep_detection_rod.key(policy, _board(1, (20, 20), [rod], depth=49)))

    def test_a_charging_carried_rod_is_waited_for_its_recharge_then_given_up(self):
        # n1-c life-224 (2026-11-28): the wait ends by itself at the rod's real recharge
        # (rod_recharge: pval 99 ticks, 990 game turns from the first rest on the cell).
        from hengbot import rod_recharge
        policy = _policy()
        policy._physical_hostiles = lambda snapshot: []
        policy._recent = []
        rod = _item(TVAL_ROD, SV_ROD_DETECTION, charging=True, charging_count=1)
        unsafe = tuple(tuple(True for _ in range(40)) for _ in range(40))
        longest = rod_recharge.game_turns(rod_recharge.carried_ready_ticks())
        keys = []
        with mock.patch.object(me_powers, "utility_device_permitted", return_value=True):
            for turn in range(1000, 1000 + longest + 200, 100):
                board = _board(turn, (20, 20), [rod], unsafe=unsafe)
                board.player.food_state = "normal"
                keys.append((turn, deep_detection_rod.key(policy, board)))
        self.assertTrue(all(key == "R10\r" for turn, key in keys if turn <= 1000 + longest), keys)
        self.assertTrue(all(key is None for turn, key in keys if turn > 1000 + longest), keys)


if __name__ == "__main__":
    unittest.main()
