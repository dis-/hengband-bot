"""Declared wall: a recorded town scene from before the item-use-route rule (owner 2026-11-13).

Owner 2026-11-13 「アイテムが整理できていない」: an item no consumer uses for the character
(hengbot.item_use_route) is sold, never shelved or kept.  The recorded scenes below held such
items (a warrior's Heroism under a lasting fear resistance, Enlightenment after its quest, the
Magic-Eater's Stone to Mud wands at the absorbed 99 cap, Speed potions under a reliable Speed
staff, *Remove Curse* under the absorbed Remove Curse staff, never-absorbed rods and staffs), so
today the visit sells them first and the recorded keys pin something else.  The wall holds the
rule off for those scenes; tests/test_n1c_205_item_use_route_1113_recorded.py pins the rule.

    def setUp(self):
        super().setUp()
        item_use_route_wall.hold(self)
"""
from unittest.mock import patch

from hengbot import item_use_route


def hold(test) -> None:
    """Every item keeps today's (pre-rule) handling for this test."""
    wall = patch.object(item_use_route, "surplus", lambda *args, **kwargs: False)
    wall.start()
    test.addCleanup(wall.stop)
