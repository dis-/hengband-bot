"""The Magic-Eater's Restore Mana collection target (owner 2026-11-20, restore_mana_target).

Owner, verbatim: 「99Fと100Fでは強力発動ロケットをダメージソースとして戦う。魔力復活1服あたり回復する
ロケットの量から与えられるダメージ量を出し、99Fと100FのターゲットのHP総量の1.5倍を目標値として
魔力復活の薬を集める必要がある。」 and 「ロケットの成功率は90%で試算して良い」.

n1-b life-411 (Magic-Eater Lv50) at its 2026-11-20 03:32:34 town arrival
(tests/fixtures/n1b-411-home-closed-pending-1120): 15 rockets absorbed, so a potion restores
15 / 3 = 5 uses (spells-status.cpp restore_mana); a Powerful Activation rocket deals
250 + 3 x (2 x 50) = 550 to Oberon (99d111, FORCE_MAXHP: 10989) and the Serpent of Chaos
(200d150: 30000), neither resisting shards; 1.5 x 40989 / (5 x 0.9 x 550) = 24.8 -> 25 potions.
The Home holds one.

DECLARED CONSTRUCTED: a Restore Mana ware added to the recorded Black Market page (row 80), and
the held count raised to the target by Home stock added to the census.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import home_ledger, restore_mana_target
from hengbot.model import STORE_BLACK, SV_POTION_RESTORE_MANA, TVAL_POTION
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-home-closed-pending-1120"
BLACK_MARKET_ROW = 80


class RestoreManaTargetRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _, steps = load(FIXTURE, Path(self.scratch.name))
        self.board = steps[0][1]()
        self.black_market = steps[BLACK_MARKET_ROW][1]()

    def tearDown(self):
        self.scratch.cleanup()

    def test_n1b_target(self):
        figures = restore_mana_target.plan(self.policy, self.board)
        self.assertEqual(figures["rockets"], 15)
        self.assertEqual(figures["target_hp"], {860: 10989, 862: 30000})
        self.assertEqual(figures["uses_per_potion"], 5.0)
        self.assertEqual(figures["rocket_damage"], 550.0)
        self.assertEqual(figures["target"], 25)
        self.assertEqual(figures["held"], 1)
        self.assertEqual(restore_mana_target.ROCKET_SUCCESS, 0.9)
        self.assertEqual(home_ledger.summary(self.policy, self.board)["restore_mana"],
                         {"held": 1, "target": 25, "rockets": 15})

    def test_uses_per_potion(self):
        self.assertEqual([restore_mana_target.uses_per_potion(count) for count in (0, 2, 9, 10, 15, 30)],
                         [0.0, 2.0, 3.0, 10 / 3, 5.0, 10.0])

    def shelf(self):
        page = self.black_market
        self.assertEqual(page.store.store_type, STORE_BLACK)
        ware = replace(page.store.items[0], name="魔力復活の薬", tval=TVAL_POTION,
                       sval=SV_POTION_RESTORE_MANA, count=2, price=3000,
                       letter=chr(ord("a") + len(page.store.items)))
        return replace(page, store=replace(page.store, items=[*page.store.items, ware]))

    def test_bought_until_the_target(self):
        policy, shelf = self.policy, self.shelf()
        picked = policy._black_market_optional_purchase(shelf)
        self.assertEqual((picked.tval, picked.sval), (TVAL_POTION, SV_POTION_RESTORE_MANA))
        home = next(item for item in policy._home_knowledge_items
                    if (item.tval, item.sval) == (TVAL_POTION, SV_POTION_RESTORE_MANA))
        policy._home_knowledge_items = tuple(
            replace(item, count=25) if item is home else item
            for item in policy._home_knowledge_items)
        self.assertFalse(restore_mana_target.wanted(policy, shelf))
        picked = policy._black_market_optional_purchase(shelf)
        self.assertFalse(picked is not None
                         and (picked.tval, picked.sval) == (TVAL_POTION, SV_POTION_RESTORE_MANA))


if __name__ == "__main__":
    unittest.main()
