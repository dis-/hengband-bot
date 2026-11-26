"""The Rogue's spells, second slice (owner 2026-11-26 「盗賊は魔法を使える」): buying the cast books,
鑑定 / 真・鑑定 as identification sources, the spell Teleport Away remembered by sent_away_t1, the
haste in place of an attack.

Game facts (C:/hengband): store/articles-on-sale.cpp, the Magic shop's regular stock holds Sorcery
[入門書] (SORCERY_BOOK 0) and its random stock [仙人の書] (SORCERY_BOOK 1); BaseitemDefinitions.jsonc
ids 334 / 335 cost 100 / 1000; spell-kind/spells-perception.cpp:114/160 the identification
questions 「どのアイテムを鑑定しますか?」 / 「どのアイテムを*鑑定*しますか?」.

DECLARED CONSTRUCTED: the boards (a Rogue, class 3, its books, mana, gold and an unknown potion; a
Warrior for the no-op checks), the remembered departure prices (as
tests/test_black_market_optional_quantity.py remembers them), the Magic shop pages, the second
book's list (the rows realm_spells.derived gives, fail 9%), the game model of the identification
cast (the live capture's book and spell questions, the source's item question).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from unittest import mock

from policy_fixtures import hostile, item, store_item
from test_realm_spells_1126 import board, book, caster, recorded, second_book_record
from test_realm_spells_input_1126 import SpellGame, SpellInputTest, prompt
from hengbot import me_powers, realm_spell_book, realm_spells, realm_spells_input, sent_away_t1
from hengbot.model import (
    STORE_MAGIC, SV_SCROLL_IDENTIFY, TVAL_POTION, TVAL_SCROLL, TVAL_SORCERY_BOOK, StoreState,
)
from hengbot.policy import READ_KEY, HengbotPolicy

UNKNOWN = item("c", TVAL_POTION, 40, aware=False, known=False, name="青い薬")


def priced(policy):
    """The departure prices a town visit remembers (the optional purchases' reserve)."""
    for category, price in (("recall", 100), ("teleport", 50), ("cure-critical", 200),
                            ("food", 80), ("oil", 20), ("light", 400)):
        policy._remember_departure_price(category, price, 1)
    return policy


def town(snapshot, *, gold, store=None):
    return replace(snapshot, floor_key=(0, 0, 0), town_flag=True, store=store,
                   player=replace(snapshot.player, gold=gold))


class BookPurchaseTest(unittest.TestCase):
    def test_first_book_always_and_second_three_levels_before_its_first_spell(self):
        policy = caster()
        self.assertEqual(realm_spell_book.wanted_books(policy, board(level=9)), ())
        self.assertEqual(realm_spell_book.wanted_books(policy, board(level=10)), (1,))   # 13 - 3
        self.assertEqual(realm_spell_book.wanted_books(policy, board(level=10, inventory=[])),
                         (0, 1))
        self.assertEqual(realm_spell_book.wanted_books(
            policy, board(level=10, inventory=[book(), book("b", 1)])), ())
        self.assertEqual(realm_spell_book.wanted_books(policy, board(class_id=0, inventory=[])), ())

    def test_a_home_copy_is_taken_out_not_bought(self):
        policy = caster()
        home_book = replace(book(), slot="home")
        policy._home_knowledge_items = [home_book]
        snapshot = board(level=5, inventory=[])
        self.assertEqual(realm_spell_book.wanted_books(policy, snapshot), ())
        self.assertEqual(realm_spell_book.home_missing(policy, snapshot, home_book), 1)
        self.assertEqual(realm_spell_book.home_missing(policy, board(level=5), home_book), 0)

    def test_magic_shop_sells_the_second_book_above_the_resupply_reserve(self):
        policy = priced(caster())
        ware = store_item("d", TVAL_SORCERY_BOOK, 1, price=1200, name="仙術の魔法書[仙人の書]")
        shelf = StoreState(STORE_MAGIC, [ware])
        policy.prime(town(board(level=10), gold=100000, store=shelf))
        reserve = policy._full_departure_resupply_reserve(town(board(level=10), gold=100000,
                                                               store=shelf))
        self.assertIsNotNone(reserve)
        for gold, bought in ((reserve + 1200, True), (reserve + 1199, False)):
            with self.subTest(gold=gold):
                page = town(board(level=10), gold=gold, store=shelf)
                self.assertEqual(realm_spell_book.purchase_units(policy, page, ware), int(bought))
                self.assertEqual("realm-book:buy" in {
                    match.rung_id for match in policy._matching_live_purchase_rungs(page, ware)},
                    bought)
                self.assertEqual(policy._next_purchase(page) is ware, bought)

    def test_the_town_routes_to_the_magic_shop_for_a_missing_book(self):
        policy = priced(caster())
        snapshot = town(board(level=10), gold=100000)
        policy.prime(snapshot)
        self.assertTrue(realm_spell_book.errand_wanted(policy, snapshot))
        needs = {(need.store_type, need.category) for need in policy._enumerate_town_needs(snapshot)}
        self.assertIn((STORE_MAGIC, realm_spell_book.CATEGORY), needs)
        warrior = town(board(level=10, class_id=0), gold=100000)
        policy.prime(warrior)
        self.assertNotIn(realm_spell_book.CATEGORY,
                         {need.category for need in policy._enumerate_town_needs(warrior)})


class IdentifySpellTest(unittest.TestCase):
    def identifier(self):
        policy = caster(second_book_record(mp=40, level=15))
        realm_spells.observe_list(policy, recorded())
        return policy

    def test_identify_spell_is_a_source_when_no_scroll_or_device_is_carried(self):
        policy = self.identifier()
        snapshot = board(mp=40, level=15, inventory=[book(), book("b", 1), UNKNOWN])
        policy.prime(snapshot)
        command, source = policy._find_identification_source(snapshot, full=False)
        self.assertEqual((command, source.spell_id), (READ_KEY, realm_spells.IDENTIFY))
        self.assertEqual(policy._read_key(snapshot, source, "c"), "mbbc")
        # A carried scroll is read first.
        scroll = item("d", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="鑑定の巻物")
        with_scroll = replace(snapshot, inventory=[*snapshot.inventory, scroll])
        self.assertIs(policy._find_identification_source(with_scroll, full=False)[1], scroll)

    def test_dungeon_identify_keeps_the_escape_mana_town_does_not(self):
        policy = self.identifier()
        books = [book(), book("b", 1), UNKNOWN]
        # Teleport 12 + Identify 9: 20 is short in the dungeon, enough in town.
        self.assertIsNone(policy._find_identification_source(
            board(mp=20, level=15, inventory=books), full=False))
        self.assertIsNotNone(policy._find_identification_source(
            town(board(mp=20, level=15, inventory=books), gold=0), full=False))
        # The Warrior's enumerator is unchanged.
        self.assertIsNone(policy._find_identification_source(
            board(mp=40, level=15, class_id=0, inventory=books), full=False))

    def test_true_identify_from_level_40(self):
        policy = caster(second_book_record(mp=80, level=40))
        snapshot = board(mp=80, level=40, inventory=[book(), book("b", 1), UNKNOWN])
        command, source = policy._find_identification_source(snapshot, full=True)
        self.assertEqual(source.spell_id, realm_spells.IDENTIFY_TRUE)
        self.assertEqual(policy._read_key(snapshot, source, "/a"), "mbh/a")


class IdentifyGame(SpellGame):
    """SpellGame with ident_spell's item question after a cast of the letter ``b``."""

    def key(self, char):
        if self.mode == "spell" and self.command == "m" and char == "b":
            self.mode = "item"
            return
        if self.mode == "item":
            if char == "/":
                self.mode = "equipment"
                return
            self.mode, self.energy_use = "command", 100
            self.message = "青い薬は治療の薬だ。"
            return
        if self.mode == "equipment":
            self.mode, self.energy_use = "command", 100
            return
        super().key(char)

    def render(self):
        if self.mode in {"item", "equipment"}:
            return prompt("どのアイテムを鑑定しますか? ", "item", area="inventory",
                          areas=["inventory", "equipment", "floor"], first_label="c",
                          last_label="c", menu=False)
        return super().render()


class IdentifyInputTest(SpellInputTest):
    def test_identify_cast_answers_the_item_question(self):
        game = IdentifyGame()
        receipt = self.send(game, "mabc", "identify:normal")
        self.assertEqual(game.accepted, ["m", "a", "b", "c"])
        self.assertIsNone(receipt.get("refusal"))

    def test_identify_of_a_worn_piece_switches_to_the_equipment(self):
        game = IdentifyGame()
        self.send(game, "mab/a", "identify:normal-equipped")
        self.assertEqual(game.accepted, ["m", "a", "b", "/", "a"])

    def test_cast_keys_with_a_target_compile(self):
        self.assertEqual(realm_spells_input.compile_spell("mbb-", "loot:identify-floor-item")[1][0]
                         .target, "-")


class SentAwayAndHasteTest(unittest.TestCase):
    def test_spell_teleport_away_at_an_unbeatable_is_remembered(self):
        policy = caster()
        monster = hostile(1, 10, 13, distance=3)
        snapshot = board(monsters=[monster])
        policy.prime(snapshot)
        me_powers.observe(policy, snapshot)
        memory = getattr(policy, me_powers.MEMORY)
        memory.pending = me_powers.Use(("spell", 12), ("spell", 12), "unbeatable-in-range",
                                       snapshot.player.position, snapshot.turn,
                                       sent_away_t1.SPELL_THREAT_REASON, "mbe6", monster.position)
        policy.last_reason = sent_away_t1.SPELL_THREAT_REASON
        with mock.patch.object(sent_away_t1, "remember") as remember:
            sent_away_t1.note(policy, snapshot)
        remember.assert_called_once_with(policy, snapshot, monster)

    def test_haste_in_place_of_an_attack_on_an_awake_hostile(self):
        policy = caster(second_book_record(mp=40, level=30))
        realm_spells.observe_list(policy, recorded())
        monster = hostile(1, 10, 11, distance=1)
        snapshot = board(mp=40, level=30, inventory=[book(), book("b", 1)], monsters=[monster])
        policy.prime(snapshot)
        me_powers.observe(policy, snapshot)
        policy.last_reason = "melee"
        self.assertEqual(me_powers.fight_key(policy, snapshot, "6"), "mbf")
        self.assertEqual(policy.last_reason, "realm-spell:fight-unhasted:speed")
        # Without the mana for it (and the escape reserve), the attack stays.
        policy = caster(second_book_record(mp=20, level=30))
        realm_spells.observe_list(policy, recorded())      # Teleport (12) is learned: reserved
        weak = board(mp=20, level=30, inventory=[book(), book("b", 1)], monsters=[monster])
        policy.prime(weak)
        me_powers.observe(policy, weak)
        policy.last_reason = "melee"
        self.assertEqual(me_powers.fight_key(policy, weak, "6"), "6")


if __name__ == "__main__":
    unittest.main()
