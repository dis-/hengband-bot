"""The owner's kept supplies are never sold or destroyed (owner 2026-11-20).

n1-b life-411 (Magic-Eater Lv50) deposited the Potions of Restore Mana it found, and the old
full-Home relief took them out and sold them (11-20 02:57, 03:59, 05:36:
home:full-queue-surplus-withdraw -> home-errand:atomic-withdraw:full-home-sale ->
shop:in-store-sell 「魔力復活の薬 {@4}を $2403で売却しました」).  Owner: 「n1-bの魔力復活の薬が
減っている気がする。貯めるよう指示していなかったか？」 and, verbatim,
「魔力復活の薬は魔道具術師が99Fと100Fをクリアするための非常に重要なアイテムである。絶対に売っては
ならない。」  The consumable table (2026-11-02) files 魔力復活 as 「購入＋自宅」, and the Home
redesign's answer 4 「上限を置かない」 keeps supplies' spares.

The relief's sale gate (``_home_full_sale_candidate``) asked only the retention, so any table
kind past it was surplus: the same visit at 03:33 sold a carried Potion of Restore Life Levels
(経験値復活, 「自宅」) the same way (rows 17-23 of this fixture).

Now ``item_fate.supply_kept`` (the table's Home kinds, and the never-disposed items) closes the
gate every disposal path shares (``item_fate.held``: the full-Home relief and its pack sales,
the cap tidy, the junk sweep, the overweight surplus), and the item reservation refuses every
sale, destroy and surplus sink of a Magic-Eater's Restore Mana whichever owner asks
(never_dispose, item_reservation ``item_reserved_by_other``).  The Black Market's Restore Mana is
bought for the Home (no ordinary store sells it: store/articles-on-sale.cpp).

Recorded: n1-b life-411's town-arrival checkpoint of 2026-11-20 03:32:34 and its journal
(tests/fixtures/n1b-411-home-closed-pending-1120).  Rows 0-16 are decided through the public
choose_key and compared with the record; row 17 is where the relief chose the Potion of Restore
Life Levels.

DECLARED CONSTRUCTED: a Restore Mana stack in the pack and on a store page (the Home's own stack
of one is the recorded one; the pack's is the Home stack carried), and a Restore Mana ware added
to the recorded Black Market page of row 80.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import item_fate
from hengbot.item_reservation import reserved_item_command, store_item_key
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import STORE_BLACK, SV_POTION_RESTORE_MANA, TVAL_POTION
from hengbot.policy import HengbotPolicy
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-home-closed-pending-1120"
RELIEF_ROW, BLACK_MARKET_ROW, SHOP_ROW = 17, 80, 9
RESTORE_LIFE_LEVELS = ("経験値復活の薬", 75, 41)


class N1b411RestoreManaKeep1120RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        for row, (recorded, supply) in enumerate(steps[:RELIEF_ROW]):
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, board, recorded["key"], before)
        cls.board = steps[RELIEF_ROW][1]()
        cls.shop = steps[SHOP_ROW][1]()
        cls.black_market = steps[BLACK_MARKET_ROW][1]()
        cls.checkpoint = checkpoint_bytes(policy)
        cls.history = policy._home_disposal.history_path
        cls.history_bytes = cls.history.read_bytes() if cls.history.exists() else None

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        if self.history_bytes is not None:
            self.history.write_bytes(self.history_bytes)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        self.home_mana = next(item for item in self.policy._home_knowledge_items
                              if (item.tval, item.sval) == (TVAL_POTION, SV_POTION_RESTORE_MANA))
        letter = chr(ord("a") + len(self.board.inventory))
        self.carried_mana = replace(self.home_mana, slot=letter, count=3)
        self.carrying = replace(self.board, inventory=(*self.board.inventory, self.carried_mana))

    def test_the_relief_no_longer_takes_the_restore_life_levels(self):
        policy, board = self.policy, self.board
        self.assertEqual(self.journal[23]["reason"], "shop:in-store-sell")
        potion = next(item for item in board.inventory
                      if policy._item_signature(item) == RESTORE_LIFE_LEVELS)
        self.assertTrue(item_fate.supply_kept(policy, board, potion))
        self.assertIsNone(policy._home_full_sale_candidate(board, potion))
        policy.choose_key(board)
        relief = policy._home_full_relief
        self.assertNotEqual(relief.sale[0] if relief.sale else None, RESTORE_LIFE_LEVELS)

    def test_restore_mana_is_kept_by_every_home_path(self):
        policy, board, carrying = self.policy, self.board, self.carrying
        for item, where in ((self.home_mana, item_fate.SHELF), (self.carried_mana, item_fate.PACK)):
            self.assertEqual(item_fate.fate(policy, carrying, item, where), item_fate.HOME)
        self.assertIsNone(policy._home_full_sale_candidate(board, self.home_mana))
        self.assertIsNone(policy._home_full_discard_candidate(board, self.home_mana))
        self.assertIsNone(policy._home_full_sale_candidate(carrying, self.carried_mana))
        self.assertNotIn(self.carried_mana.slot, [
            entry[2].slot for entry in policy._overweight_surplus_candidates(carrying)])
        ware = item_fate.sweep_ware(policy, board, policy._home_knowledge_items)
        self.assertFalse(ware is not None
                         and (ware[1].tval, ware[1].sval) == (TVAL_POTION, SV_POTION_RESTORE_MANA))

    def test_no_owner_can_sell_or_destroy_a_magic_eaters_restore_mana(self):
        policy, carrying, item = self.policy, self.carrying, self.carried_mana
        shop = replace(self.shop, inventory=carrying.inventory)
        self.assertNotIn(item.slot, [sale.slot for sale in policy._current_store_sale_candidates(shop)])
        self.assertIsNone(store_item_key(policy, shop, "sell", item, "shop-sell", quantity=1))
        for kind in ("sell", "destroy", "overweight-surplus"):
            self.assertIsNone(reserved_item_command(policy, carrying, kind, item, "shop-sell"), kind)
        self.assertIsNone(policy._destroy_item_key(item, carrying, "home-visit", policy=policy))
        # Another class: the hard rule is the Magic-Eater's (the table still keeps it at Home).
        other = replace(carrying, player=replace(carrying.player, class_id=0))
        self.assertIsNotNone(reserved_item_command(policy, other, "destroy", item, "shop-sell"))
        self.assertTrue(item_fate.supply_kept(policy, other, item))

    def test_the_black_market_restore_mana_is_bought_for_the_home(self):
        policy, page = self.policy, self.black_market
        self.assertEqual(page.store.store_type, STORE_BLACK)
        ware = replace(page.store.items[0], name="魔力復活の薬", tval=TVAL_POTION,
                       sval=SV_POTION_RESTORE_MANA, count=2, price=3000,
                       letter=chr(ord("a") + len(page.store.items)))
        shelf = replace(page, store=replace(page.store, items=[*page.store.items, ware]))
        picked = policy._black_market_optional_purchase(shelf)
        self.assertIsNotNone(picked)
        self.assertEqual((picked.tval, picked.sval), (TVAL_POTION, SV_POTION_RESTORE_MANA))


if __name__ == "__main__":
    unittest.main()
