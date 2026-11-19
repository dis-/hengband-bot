"""An empty wand or staff of a kind already absorbed is absorbed (owner 2026-11-19).

Owner (verbatim) 「取り込む」, on the empty Home devices of n1-b and n1-c.  The game
(mind-magic-eater.cpp import_magic_device): a rod adds its number whatever its charge (:52); a
wand or staff adds its charges, and with the power's count above 0 the gain is raised to at least
1 (:59-64), so an empty copy of a kind already absorbed raises the count by 1 (up to 99, :66); an
empty copy of a kind not yet absorbed (count 0) gains nothing.  me_device_policy ``_usable`` read
every empty wand and staff as absorbing nothing, so the Home kept them (item_fate HOME).

Now (``_usable``): an empty wand or staff absorbs when its kind's count is above 0 and below the
cap; ``empty_unabsorbed`` (count 0, absorb_now, no recharge first) has no use
(item_use_route ``magic-eater-absorbs``) and is sold.  The floor's absorption
(absorb_candidate), the town's (town_absorb_candidate) and the Home fate share ``_usable``.

Recorded: the town arrivals of 2026-11-19, n1-b life-411 (tests/fixtures/
quest32-one-turn-kill-1119/n1b-411: the empty Wands of Acid Bolts and Fire Bolts, Staffs of Cure
Light Wounds and Dispel Evil, counts 37, 43, 47, 24) and n1-c life-217 (tests/fixtures/
n1c-217-angband-hold-1119: the empty Wand of Frost Bolts, count 48).

DECLARED CONSTRUCTED: the absorbed count patched to 0 or 99 (me_capability.count) for the kinds
not yet absorbed and at the cap; an empty copy carried in the pack on a dungeon floor
(``in_town`` off) for the floor's absorption.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot import item_fate, item_use_route, me_capability, me_device_policy
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
N1B_EMPTY = ("アシッド・ボルトの魔法棒 (0回分)", "ファイア・ボルトの魔法棒 (0回分)",
             "軽傷の治癒の杖 (0回分)", "邪悪存在退散の杖 (0回分)")
N1C_EMPTY = "アイス・ボルトの魔法棒 (0回分)"


def recorded(path):
    scratch = TemporaryDirectory()
    policy, _journal, steps = load(path, Path(scratch.name))
    return scratch, policy, steps[0][1]()


class MeEmptyAbsorb1119RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n1b = recorded(FIXTURES / "quest32-one-turn-kill-1119" / "n1b-411")
        cls.n1c = recorded(FIXTURES / "n1c-217-angband-hold-1119")

    @classmethod
    def tearDownClass(cls):
        cls.n1b[0].cleanup()
        cls.n1c[0].cleanup()

    @staticmethod
    def shelf(policy, name):
        return next(item for item in policy._home_knowledge_items if item.name == name)

    @staticmethod
    def counted(value, kind_sval):
        real = me_capability.count

        def count(policy, snapshot, kind, sval):
            return value if (kind, sval) == kind_sval else real(policy, snapshot, kind, sval)
        return patch.object(me_capability, "count", count)

    def test_the_recorded_empty_copies_of_absorbed_kinds_are_absorbed(self):
        for (_, policy, board), names in ((self.n1b, N1B_EMPTY), (self.n1c, (N1C_EMPTY,))):
            for name in names:
                item = self.shelf(policy, name)
                row = me_device_policy.device(item)
                self.assertEqual(item.charges, 0, name)
                self.assertGreater(me_capability.count(policy, board, row.kind, row.sval), 0, name)
                self.assertEqual(item_fate.fate(policy, board, item, item_fate.SHELF),
                                 item_fate.ABSORB, name)

    def test_the_home_take_lists_them(self):
        _, policy, board = self.n1b
        taken = {item.name for item in me_device_policy.home_absorb_takes(policy, board)}
        self.assertTrue(set(N1B_EMPTY) <= taken)

    def test_carried_empty_copies_are_absorbed_in_town_and_on_the_floor(self):
        _, policy, board = self.n1c
        item = replace(self.shelf(policy, N1C_EMPTY), slot=chr(ord("a") + len(board.inventory)))
        carried = replace(board, inventory=(*board.inventory, item))
        self.assertIs(me_device_policy.town_absorb_candidate(policy, carried), item)
        floor = replace(carried, town_flag=False)
        self.assertFalse(floor.in_town)
        self.assertIs(me_device_policy.absorb_candidate(policy, floor), item)

    def test_an_empty_copy_of_a_kind_not_yet_absorbed_is_sold(self):
        _, policy, board = self.n1c
        item = self.shelf(policy, N1C_EMPTY)
        row = me_device_policy.device(item)
        with self.counted(0, (row.kind, row.sval)):
            self.assertTrue(me_device_policy.empty_unabsorbed(policy, board, item))
            self.assertTrue(item_use_route.surplus(policy, board, item))
            self.assertEqual(item_fate.fate(policy, board, item, item_fate.SHELF), item_fate.SELL)

    def test_an_empty_copy_at_the_cap_adds_nothing(self):
        _, policy, board = self.n1c
        item = self.shelf(policy, N1C_EMPTY)
        row = me_device_policy.device(item)
        with self.counted(me_device_policy.POWER_COUNT_CAP, (row.kind, row.sval)):
            self.assertFalse(me_device_policy.absorbs(policy, board, item))
            self.assertNotEqual(item_fate.fate(policy, board, item, item_fate.SHELF),
                                item_fate.ABSORB)


if __name__ == "__main__":
    unittest.main()
