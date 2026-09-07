import unittest
from dataclasses import replace

from test_policy import (
    DESTROY_FAIL_LIMIT, HengbotPolicy, LEAVE_STORE_KEY, PACK_CAPACITY,
    PLAYER_CLASS_WARRIOR, Position, STORE_ALCHEMIST, STORE_GENERAL, STORE_HOME,
    STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON, SV_LITE_TORCH,
    SV_POTION_CURE_CRITICAL, SV_POTION_RESIST_COLD, SV_POTION_SLEEP,
    SV_ROD_IDENTIFY, SV_ROD_LITE, SV_SCROLL_HOLY_CHANT, Snapshot, StoreState,
    TVAL_BOTTLE, TVAL_CHAOS_BOOK, TVAL_CHEST, TVAL_FOOD, TVAL_HISSATSU_BOOK,
    TVAL_LIFE_BOOK, TVAL_LITE, TVAL_POTION, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF,
    grid, item, player, store_item,
)


class HighValueBookSaleTest(unittest.TestCase):
    def _town(self, inventory, store=None):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=inventory,
            store=store,
        )

    def test_only_third_and_fourth_books_are_high_value_sales(self):
        policy = HengbotPolicy()
        second = item("a", TVAL_CHAOS_BOOK, 1, name="Chaos book 2")
        third = item("b", TVAL_CHAOS_BOOK, 2, name="Chaos book 3")
        fourth = item("c", TVAL_CHAOS_BOOK, 3, name="Chaos book 4")

        self.assertFalse(policy._is_high_value_book(second))
        self.assertTrue(policy._is_high_value_book(third))
        self.assertTrue(policy._is_high_value_book(fourth))
        self.assertEqual(policy._find_book_sale(self._town([second, third])).slot, "b")
        self.assertTrue(policy._has_town_economic_path(third))

    def test_routes_books_to_a_store_that_buys_their_realm(self):
        cases = (
            (TVAL_CHAOS_BOOK, STORE_MAGIC),
            (TVAL_LIFE_BOOK, STORE_TEMPLE),
            (TVAL_HISSATSU_BOOK, STORE_WEAPON),
        )
        for tval, store_type in cases:
            with self.subTest(tval=tval):
                # Each case represents a fresh town visit; a live circuit never
                # abandons its current still-needed stop for a new mid-visit need.
                policy = HengbotPolicy()
                book = item("b", tval, 2, name="valuable book")
                self.assertEqual(
                    policy._next_required_store_type(self._town([book])), store_type
                )

    def test_sells_high_value_book_in_one_store_visit(self):
        book = item("b", TVAL_CHAOS_BOOK, 3, name="Chaos book 4")
        snapshot = self._town([book], StoreState(STORE_MAGIC, []))
        policy = HengbotPolicy()

        self.assertEqual(policy._shop(snapshot), "{b@0\r")
        self.assertEqual(policy.last_reason, "shop:batch-inscribe")

    def test_withdraws_an_old_high_value_book_from_home_for_sale(self):
        book = store_item("c", TVAL_CHAOS_BOOK, 2, name="Chaos book 3")
        snapshot = self._town([], StoreState(STORE_HOME, [book]))
        policy = HengbotPolicy()

        self.assertEqual(policy._shop(snapshot), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:queue-book-sale-withdraw")

    def test_leaves_home_with_withdrawn_book_instead_of_redepositing_it(self):
        book = item("b", TVAL_CHAOS_BOOK, 3, name="Chaos book 4")
        snapshot = self._town([book], StoreState(STORE_HOME, []))
        policy = HengbotPolicy()

        self.assertEqual(policy._shop(snapshot), LEAVE_STORE_KEY)
        self.assertEqual(policy.last_reason, "home:leave-with-book-sale")

class ItemShedListTest(unittest.TestCase):
    """User-flagged always-shed items — Resist Cold potion, Holy Chant scroll and
    Rod of Light — are sold in town (alchemist / magic shop) and destroyed when
    the pack is full, while useful lookalikes are kept."""

    def _snap(self, inventory):
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 3, 0),
            inventory=inventory,
        )

    def test_disposable_flags(self):
        pol = HengbotPolicy()
        self.assertTrue(pol._is_disposable_item(item("b", TVAL_POTION, SV_POTION_RESIST_COLD)))
        self.assertTrue(pol._is_disposable_item(item("b", TVAL_SCROLL, SV_SCROLL_HOLY_CHANT)))
        self.assertTrue(pol._is_disposable_item(item("b", TVAL_ROD, SV_ROD_LITE)))
        # Useful lookalikes stay.
        self.assertFalse(pol._is_disposable_item(item("b", TVAL_POTION, SV_POTION_CURE_CRITICAL)))
        self.assertFalse(pol._is_disposable_item(item("b", TVAL_ROD, SV_ROD_IDENTIFY)))

    def test_alchemist_sells_potion_and_scroll(self):
        pol = HengbotPolicy()
        self.assertEqual(
            pol._find_low_level_sale(self._snap([item("b", TVAL_POTION, SV_POTION_RESIST_COLD)])).slot,
            "b",
        )
        self.assertEqual(
            pol._find_low_level_sale(self._snap([item("b", TVAL_SCROLL, SV_SCROLL_HOLY_CHANT)])).slot,
            "b",
        )

    def test_magic_shop_sells_light_rod_but_keeps_identify_rod(self):
        pol = HengbotPolicy()
        snap = self._snap(
            [
                item("b", TVAL_ROD, SV_ROD_IDENTIFY),  # useful -> kept
                item("c", TVAL_ROD, SV_ROD_LITE),      # redundant -> sold
            ]
        )
        sale = pol._find_device_sale(snap)
        self.assertIsNotNone(sale)
        self.assertEqual(sale.slot, "c")

class StoreSellGateTest(unittest.TestCase):
    def _store(self, inventory, store_type, *, turn=758358):
        return Snapshot(
            player(
                10, 10, class_id=PLAYER_CLASS_WARRIOR,
                food_type=4, gold=1000,
            ),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
            turn=turn,
            inventory=list(inventory),
            store=StoreState(store_type, []),
        )

    def test_2139_replay_unaccepted_alchemist_food_emits_no_sell_or_tail(self):
        mana_food = item("a", TVAL_FOOD, 1, name="Ration of Food", known=True)
        snap = self._store([mana_food], STORE_ALCHEMIST)
        policy = HengbotPolicy()

        keys = [policy._shop(snap) for _ in range(3)]

        self.assertEqual(keys, [LEAVE_STORE_KEY] * 3)
        self.assertTrue(all("d" not in key and "\r" not in key and "y" not in key for key in keys))
        self.assertNotIn(policy._item_signature(mana_food), policy._unsellable_items)

    def test_mana_race_food_is_sold_at_general_store(self):
        mana_food = item("a", TVAL_FOOD, 1, name="Ration of Food", known=True)
        policy = HengbotPolicy()

        self.assertEqual(
            policy._shop(self._store([mana_food], STORE_GENERAL)),
            "{a@0\r",
        )
        self.assertEqual(policy.last_reason, "shop:batch-inscribe")

    def test_unsellable_latch_clears_on_next_town_visit(self):
        potion = item("a", TVAL_POTION, SV_POTION_RESIST_COLD)
        policy = HengbotPolicy()
        policy._unsellable_items.add(policy._item_signature(potion))
        policy._floor_key = (1, 5, 0)

        policy._observe(self._store([potion], STORE_ALCHEMIST))

        self.assertNotIn(policy._item_signature(potion), policy._unsellable_items)

    def test_same_turn_unchanged_sale_latches_after_one_emitted_attempt(self):
        potion = item("a", TVAL_POTION, SV_POTION_RESIST_COLD)
        snap = self._store([potion], STORE_ALCHEMIST)
        policy = HengbotPolicy()

        # One emit whose board is unchanged proves the sale was rejected (a
        # genuine duplicate snapshot only re-fires after the retry delay, by which
        # time the game has processed the key). Leave instead of re-emitting the
        # multi-key sell — a second emit lands its trailing keys in the store
        # command loop after the "no room" message (the observed desync).
        self.assertEqual(policy._shop(snap), "{a@0\r")
        self.assertEqual(policy._shop(snap), LEAVE_STORE_KEY)
        self.assertIn(policy._item_signature(potion), policy._unsellable_items)

    def test_changed_turn_latches_only_after_three_attempts(self):
        potion = item("a", TVAL_POTION, SV_POTION_RESIST_COLD)
        policy = HengbotPolicy()

        for turn in range(2):
            self.assertEqual(
                policy._shop(self._store([potion], STORE_ALCHEMIST, turn=turn)),
                "{a@0\r" if turn == 0 else LEAVE_STORE_KEY,
            )
        self.assertEqual(
            policy._shop(self._store([potion], STORE_ALCHEMIST, turn=2)),
            LEAVE_STORE_KEY,
        )
        self.assertIn(policy._item_signature(potion), policy._unsellable_items)

class FullPackDisposalTest(unittest.TestCase):
    """Full-pack disposal: destroy keys must fire in the original keyset, progress must be
    verified, and an item the game refuses to destroy
    must be abandoned rather than looped on forever.
    """

    def _full_pack(self, *disposables):
        # Charged staves so the inert filler is not itself disposable (a drained
        # 0-charge staff now IS), which would otherwise be picked before the target.
        filler = [
            item(chr(ord("a") + i), TVAL_STAFF, i, name=f"filler-{i}", charges=5)
            for i in range(PACK_CAPACITY - len(disposables))
        ]
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(1, 5, 0),  # in the dungeon, where disposal happens
            inventory=[*filler, *disposables],
        )

    def test_zero_fuel_torch_destroyed_with_original_destroy_key(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        pol = HengbotPolicy()
        # Original destroy = k; "01" forces it (no confirmation prompt) and
        # destroys the whole stack with no movement/confirmation keys leaking.
        self.assertEqual(pol._full_pack_destroy_key(self._full_pack(torch)), "01kq")

    def test_stacked_disposable_destroys_whole_stack_via_command_arg(self):
        potions = item("q", TVAL_POTION, SV_POTION_SLEEP, name="sleep", count=4)
        pol = HengbotPolicy()
        self.assertEqual(pol._full_pack_destroy_key(self._full_pack(potions)), "04kq")

    def test_empty_chests_are_disposable_junk(self):
        policy = HengbotPolicy()
        for name in (
            "small wooden chest (empty)",
            "小さな木の箱 (空)",
            "壊れた鉄の箱",
        ):
            with self.subTest(name=name):
                chest = item("q", TVAL_CHEST, 1, name=name)
                self.assertTrue(policy._is_disposable_item(chest))
                self.assertEqual(
                    policy._full_pack_destroy_key(self._full_pack(chest)), "01kq"
                )
                policy._destroy_watch = None

    def test_unidentified_mushroom_is_disposable_but_food_ration_is_kept(self):
        pol = HengbotPolicy()
        # Unidentified mushroom (unaware food): a poison gamble worth nothing.
        mushroom = item("q", TVAL_FOOD, 5, name="mushroom", aware=False)
        self.assertTrue(pol._is_disposable_item(mushroom))
        # A known ration nourishes and must be kept; an identified mushroom may be
        # beneficial, so only UNidentified food is shed.
        self.assertFalse(pol._is_disposable_item(item("r", TVAL_FOOD, 35, name="ration")))
        self.assertFalse(
            pol._is_disposable_item(item("s", TVAL_FOOD, 5, name="known mushroom"))
        )

    def test_unchanged_pack_marks_item_undestroyable_and_gives_up(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        snap = self._full_pack(torch)
        pol = HengbotPolicy()
        # Re-deciding on an unchanged pack means the destroy never took. After the
        # retry budget the item is abandoned and None lets return-to-town take over.
        results = [pol._full_pack_destroy_key(snap) for _ in range(DESTROY_FAIL_LIMIT + 2)]
        self.assertEqual(results[0], "01kq")
        self.assertIsNone(results[-1])
        self.assertIn(pol._item_signature(torch), pol._undestroyable_sigs)

    def test_next_disposable_tried_once_first_is_undestroyable(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        bottle = item("r", TVAL_BOTTLE, 1, name="bottle")
        pol = HengbotPolicy()
        pol._undestroyable_sigs.add(pol._item_signature(torch))
        # The torch is skipped; the empty bottle is the next disposable target.
        self.assertEqual(
            pol._full_pack_destroy_key(self._full_pack(torch, bottle)), "01kr"
        )

    def test_all_undestroyable_returns_none_for_town_return(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        pol = HengbotPolicy()
        pol._undestroyable_sigs.add(pol._item_signature(torch))
        self.assertIsNone(pol._full_pack_destroy_key(self._full_pack(torch)))

    def test_bounty_item_is_never_disposed(self):
        # A wanted (bounty) item is worth gold at the Hunter's Office even if its
        # pseudo-feeling reads 'average', so it must not be destroyed.
        bounty = replace(
            item("q", TVAL_POTION, 28, name="wanted", pseudo_feeling="average"),
            is_bounty=True,
        )
        pol = HengbotPolicy()
        self.assertFalse(pol._is_disposable_item(bounty))
        self.assertIsNone(pol._full_pack_destroy_key(self._full_pack(bounty)))

    def test_undestroyable_cleared_on_town_arrival(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        pol = HengbotPolicy()
        pol._undestroyable_sigs.add(pol._item_signature(torch))
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        pol._observe(town)
        self.assertEqual(pol._undestroyable_sigs, set())

    def test_destroy_failure_watch_survives_same_town_visit(self):
        torch = item("q", TVAL_LITE, SV_LITE_TORCH, name="torch", fuel=0)
        town = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=(0, 0, 0),
            town_flag=True,
        )
        pol = HengbotPolicy()
        pol._observe(town)
        watch = (pol._item_signature(torch), torch.count, 1)
        pol._destroy_watch = watch
        pol._destroy_fail_streak = 2

        pol._observe(town)

        self.assertEqual(pol._destroy_watch, watch)
        self.assertEqual(pol._destroy_fail_streak, 2)

