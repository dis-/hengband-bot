import unittest

from policy_fixtures import grid, item, player

from hengbot.model import (
    GridState,
    PLAYER_CLASS_WARRIOR,
    Position,
    STORE_HOME,
    SV_DIGGING_SHOVEL,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_LITE_TORCH,
    SV_POTION_CURE_CRITICAL,
    SV_SCROLL_DETECT_TREASURE,
    SV_SCROLL_TELEPORT,
    SV_SCROLL_WORD_OF_RECALL,
    Snapshot,
    TVAL_DIGGING,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_SCROLL,
)
from hengbot.policy import TORCH_THROW_TARGET


class _TownShopFixtureBase(unittest.TestCase):
    def _strict_supplies(self, *, recall=3, detection=0, teleport=1, critical=1):
        supplies = [
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
        ]
        if recall:
            supplies.append(
                item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=recall)
            )
        if detection:
            supplies.append(
                item(
                    "d",
                    TVAL_SCROLL,
                    SV_SCROLL_DETECT_TREASURE,
                    count=detection,
                )
            )
        if teleport:
            supplies.append(
                item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=teleport)
            )
        if critical:
            supplies.append(
                item(
                    "c",
                    TVAL_POTION,
                    SV_POTION_CURE_CRITICAL,
                    count=critical,
                )
            )
        return supplies

    def _lantern(self):
        return item(
            "light",
            TVAL_LITE,
            SV_LITE_LANTERN,
            fuel=5000,
            is_equipment=True,
        )

    def _shallow_partial_mining_snapshot(self, detection):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=[
                *self._strict_supplies(recall=1, detection=detection),
                item("p", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                item(
                    "u", TVAL_LITE, SV_LITE_TORCH,
                    count=TORCH_THROW_TARGET, fuel=2500,
                ),
            ],
            equipment=[self._lantern()],
        )

    def _home_tile(self, y, x):
        return GridState(
            position=Position(y, x), known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_HOME,
        )

    def _ready_home_town(self, *, gold=0):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, gold=gold),
            {
                Position(10, 10): grid(10, 10),
                Position(10, 11): self._home_tile(10, 11),
            },
            [],
            inventory=self._strict_supplies(recall=1),
            equipment=[self._lantern()],
            town_flag=True,
        )
