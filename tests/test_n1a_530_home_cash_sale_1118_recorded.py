"""n1-a life-530 2026-11-18 06:36:52: Home's cash wares are sold before a poverty mining set.

The Lv49 warrior spent some 119,000 gold in three hours on needed supplies; an Alchemist
*Identify* purchase at 06:36:52 left 1,160 gold, under FUNDRAISING_START_GOLD (3,000), and
``_start_fundraising`` sent it to mine the Yeek cave's first floor while its Home held realm
books it cannot read (Lv3 and Lv4 books, 25,000 to 100,000 gold of value each) and rings no
rule keeps.  Owner, verbatim: 「必要なものは買う。本当に資金枯渇したら採掘で良いが、自宅に大量の
換金用アイテムがあるので先に売る。」 and 「魔法書と明確に不要な指輪アミュレットを売る」.

Now Home's cash wares (home_cash_sale: the high-value books and clearly unneeded jewelry) go
through the junk sweep, most valuable first and past its per-stay bound, and the mining set
waits for them; it opens as before once no ware is left or the sweep ended this stay.

Recorded: the town-arrival checkpoint of 06:38:41 (the first one after the purchase still on
the server; tests/extract_n1a_530_home_cash_sale_1118_fixture.py): its Home census of 237 rows
and its first board.

DECLARED CONSTRUCTED: the 06:36:52 visit's own checkpoint was overwritten on the server, so the
06:38:41 arrival stands for it: the board's gold is set to the 1,160 the purchase left and the
mining set it opened is cleared (``_fundraising_mode`` None), as at 06:36:52 before
``_start_fundraising``.  For the sweep's own walk, the pack's *Destruction* scroll that waits
for a Home deposit is set aside as deposited (the Home deposit comes first on the live path).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-home-cash-sale-1118"
POVERTY_GOLD = 1160
RECORDED_GOLD = 9967
BOOKS = {"Lv3 呪術の魔法書[怨恨呪縛]", "Lv3 匠の魔法書[師範代の書]",
         "Lv3 カオスの魔法書[カオス魔導]", "Lv3 生命の魔法書[一角獣の書]"}
RINGS = {"殺戮の指輪 (+8,+12)", "ダメージの指輪 (+10)", "耐久力の指輪 (+4)",
         "不安定の耐久力の指輪 (+2) {+耐;瞬, .}"}
# Kept: a depth-table resist outside the ranking's keep, and amulets inside it.
KEPT_JEWELRY = {"電撃の指輪 [+11]", "探索のアミュレット (+8)", "耐性のアミュレット"}
DEPOSIT_SLOT = "h"   # *破壊*の巻物, bound for the Home shelf


class N1a530HomeCashSale1118RecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, self.journal, steps = load(FIXTURE, Path(self.scratch.name))
        self.recorded = steps[0][1]()
        self.policy._fundraising_mode = None
        self.board = replace(self.recorded, player=replace(self.recorded.player, gold=POVERTY_GOLD))

    def tearDown(self):
        self.scratch.cleanup()

    def test_the_record(self):
        self.assertTrue(self.recorded.in_town)
        self.assertEqual(self.recorded.player.gold, RECORDED_GOLD)
        self.assertTrue(self.policy._home_knowledge_current)
        names = {item.name for item in self.policy._home_knowledge_items}
        self.assertLessEqual(BOOKS | RINGS | {"Lv4 歌集[ベレリアンドの詩]"}, names)

    def test_poverty_sells_the_cash_wares_before_mining(self):
        self.assertFalse(self.policy._start_fundraising(self.board))
        self.assertIsNone(self.policy._fundraising_mode)

    def test_the_cash_wares_are_books_and_unneeded_rings_only(self):
        from hengbot import home_cash_sale
        policy = self.policy
        wares = home_cash_sale.wares(policy, self.board, policy._home_knowledge_items)
        names = [item.name for _, item in wares]
        self.assertEqual(set(names), BOOKS | RINGS)
        self.assertEqual(set(names[:4]), BOOKS)   # most valuable first
        kept = {item.name for item in policy._home_knowledge_items
                if not home_cash_sale.ware(policy, self.board, item)}
        self.assertLessEqual(KEPT_JEWELRY, kept)
        self.assertFalse(any(item.is_artifact or item.is_melee_weapon
                             or (item.is_equipment and item.tval not in home_cash_sale.JEWELRY_TVALS)
                             for _, item in wares))

    def test_the_sweep_takes_a_book_past_its_stay_bound(self):
        from hengbot import home_cash_sale, item_fate
        policy = self.policy
        board = replace(self.board, inventory=tuple(
            item for item in self.board.inventory if item.slot != DEPOSIT_SLOT))
        policy._home_junk_sweep_count = (policy._town_visit_epoch, item_fate.SWEEP_LIMIT_PER_STAY)
        self.assertTrue(policy._begin_home_junk_sweep(board))
        self.assertIsNotNone(policy._home_full_relief_key(board))
        relief = policy._home_full_relief
        self.assertEqual(relief["mode"], "sale")
        self.assertEqual(relief["cash"], relief["sale"][0])
        self.assertIn(relief["sale"][0][0], BOOKS)
        self.assertTrue(home_cash_sale.pending(policy, board))

    def test_mining_opens_when_nothing_is_left_to_sell(self):
        from hengbot import home_cash_sale
        policy = self.policy
        policy._home_knowledge_items = [
            item for item in policy._home_knowledge_items
            if not home_cash_sale.ware(policy, self.board, item)]
        self.assertTrue(policy._start_fundraising(self.board))
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_mining_opens_once_the_stay_ended_the_sale(self):
        from hengbot import home_cash_sale
        home_cash_sale.end(self.policy)
        self.assertTrue(self.policy._start_fundraising(self.board))

    def test_no_sale_over_the_line(self):
        from hengbot import home_cash_sale
        rich = replace(self.board, player=replace(self.board.player, gold=3000))
        self.assertFalse(home_cash_sale.pending(self.policy, rich))
        self.assertIsNone(home_cash_sale.sweep_ware(self.policy, rich, self.policy._home_knowledge_items))


if __name__ == "__main__":
    unittest.main()
