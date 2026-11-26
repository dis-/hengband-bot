"""The Rogue's third and fourth Sorcery books as means of the existing rules (supervisor 2026-11-27).

Owner 2026-11-26/27 (verbatim): 「盗賊は魔法を使える。…多少なり使うと大きく助けになる」
「魔法の地図は探索効率を大幅に向上させる」.  The supervisor added the high-value spells of the
third ([紋様仙術]) and fourth ([力の魔道書]) books: Teleport Level, Word of Recall, Clairvoyance,
Detect items and Treasure.

Game (C:/hengband): lib/edit/SpellDefinitions.jsonc SORCERY books 3-4 (the base rows below),
lib/edit/ClassMagicDefinitions.jsonc ROGUE (SORCERY aptitude -2, Globe of Invulnerability
unlearnable), spell/magic-aptitude.cpp:36-60 (the derivation), realm/realm-sorcery.cpp:255-445
(the effects), lib/edit/BaseitemDefinitions.jsonc ids 336/337 (levels 50/90, costs 25000/100000),
store/articles-on-sale.cpp (no store's table names SORCERY_BOOK 2 or 3).

DECLARED CONSTRUCTED: the boards (a Rogue with the books in slots a-d, its mana and level; the same
boards as a Warrior and a Magic-Eater), the third and fourth books' lists (the rows
realm_spells.derived gives at the given level, the given fail), the next boards of the driven
decisions (ten game turns on, the posted key's owner completed).  No live capture: no game was
started for this slice.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace

from policy_fixtures import grid, item, store_item
from test_realm_spells_1126 import board, book, recorded, second_book_record
from hengbot import area_mapping, item_fate, realm_spell_book, realm_spells, realm_spells_input
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.model import (
    STORE_BLACK, STORE_MAGIC, SV_SCROLL_TELEPORT_LEVEL, SV_SCROLL_WORD_OF_RECALL, TVAL_SCROLL,
    TVAL_SORCERY_BOOK, Position, StoreState,
)
from hengbot.policy import HengbotPolicy

BOOKS = [book(), book("b", 1), book("c", 2), book("d", 3)]


def book_record(book_index, *, mp=120, level=40, fail=9):
    """DECLARED CONSTRUCTED: book ``book_index``'s list as the game would draw it at ``level``."""
    rows = []
    for spell in realm_spells.SPELLS:
        if spell.book != book_index:
            continue
        spell_level, mana, _ = realm_spells.derived(spell)
        rows.append({"spell_id": spell.spell_id, "name": spell.names[0], "level": spell_level,
                     "mana": mana, "fail": fail,
                     "status": "available" if spell_level <= level else "unknown"})
    return {"type": "spell_list", "turn": 9000,
            "player": {"mp": mp, "level": level, "status": {"stun_rank": 0}},
            "spell_list": {"realm_id": realm_spells.REALM_SORCERY, "spells": rows}}


def rogue(*, mp=120, level=40, fail=9, recall_fail=None):
    policy = HengbotPolicy(dungeon_knowledge={1: DungeonInfo(1, "Angband", 1, 127, 30)})
    realm_spells.observe_list(policy, recorded())
    realm_spells.observe_list(policy, second_book_record(mp=mp, level=level))
    third = book_record(2, mp=mp, level=level, fail=fail)
    if recall_fail is not None:
        for row in third["spell_list"]["spells"]:
            if row["spell_id"] == realm_spells.WORD_OF_RECALL:
                row["fail"] = recall_fail
    realm_spells.observe_list(policy, third)
    realm_spells.observe_list(policy, book_record(3, mp=mp, level=level, fail=fail))
    return policy


def caster_board(*, mp=120, max_mp=120, level=40, inventory=None, depth=30, class_id=3, **kw):
    snapshot = board(mp=mp, level=level, inventory=list(BOOKS) if inventory is None else inventory,
                     depth=depth, class_id=class_id, **kw)
    return replace(snapshot, player=replace(snapshot.player, max_mp=max_mp))


def scroll(slot, sval, count=2, name="巻物"):
    return item(slot, TVAL_SCROLL, sval, name=name, count=count)


class GameNumbersTest(unittest.TestCase):
    def test_third_and_fourth_books_match_the_derivation(self):
        # SpellDefinitions.jsonc SORCERY book 3/4 bases through magic-aptitude.cpp with the Rogue's
        # -2 (L 30 / M 15 / D 3): (level, mana, difficulty).
        expected = {16: (5, 4, 31), 17: (15, 13, 86), 18: (20, 13, 66), 19: (25, 39, 76),
                    20: (27, 23, 91), 21: (27, 23, 66), 22: (33, 33, 81), 23: (45, 52, 86),
                    24: (15, 13, 46), 25: (27, 26, 86), 26: (33, 33, 81), 27: (37, 52, 86),
                    28: (40, 46, 66), 29: (46, 65, 96), 30: (47, 52, 61), 31: (48, 91, 91)}
        self.assertEqual({spell.spell_id: realm_spells.derived(spell)
                          for spell in realm_spells.SPELLS if spell.spell_id >= 16}, expected)

    def test_cost_at_no_proficiency_and_letters(self):
        # mod_need_mana: 19/12 of the derived mana before any proficiency.
        self.assertEqual([realm_spells.need_mana(realm_spells.derived(realm_spells.BY_ID[i])[1])
                          for i in (16, 21, 22, 27)], [7, 37, 53, 83])
        self.assertEqual([(realm_spells.BY_ID[i].book, realm_spells.BY_ID[i].letter)
                          for i in (16, 21, 22, 27)], [(2, "a"), (2, "f"), (2, "g"), (3, "d")])
        self.assertEqual(realm_spells.CAST_BOOKS, (0, 1, 2, 3))

    def test_study_reaches_the_new_spells(self):
        policy = rogue(level=40)
        first = recorded()
        for row in first["spell_list"]["spells"]:
            row["status"] = "available"         # the first book all learned
        realm_spells.observe_list(policy, first)
        record = book_record(2, level=40)
        for row in record["spell_list"]["spells"]:
            row["status"] = "unknown"
        realm_spells.observe_list(policy, record)
        snapshot = caster_board(can_study=True)
        self.assertEqual(realm_spell_book.study_choice(policy, snapshot),
                         (2, realm_spells.WORD_OF_RECALL))


class RecallMeansTest(unittest.TestCase):
    def test_spell_stands_in_for_a_missing_recall_scroll(self):
        policy = rogue()
        snapshot = caster_board()
        policy.prime(snapshot)
        means = policy._find_recall_scroll(snapshot)
        self.assertTrue(realm_spells.is_spell_means(means))
        self.assertTrue(means.is_recall_scroll)
        self.assertEqual(policy._read_key(snapshot, means), "mcg")

    def test_a_carried_scroll_is_read_first_and_kept_as_backup(self):
        policy = rogue()
        recall = scroll("e", SV_SCROLL_WORD_OF_RECALL, name="帰還の巻物")
        snapshot = caster_board(inventory=[*BOOKS, recall])
        policy.prime(snapshot)
        self.assertIs(policy._find_recall_scroll(snapshot), recall)

    def test_falls_back_when_mana_or_success_is_short(self):
        for label, policy, snapshot in (
                ("mana 32 < 33", rogue(), caster_board(mp=32)),
                ("success 75 < 80", rogue(recall_fail=25), caster_board()),
                ("blind", rogue(), caster_board(blind=True)),
                ("no third book", rogue(), caster_board(inventory=BOOKS[:2]))):
            with self.subTest(label):
                policy.prime(snapshot)
                self.assertIsNone(policy._find_recall_scroll(snapshot))

    def test_emergency_recall_spends_the_escape_reserve(self):
        # Teleport (12 in the recorded list) is the escape reserve; the recall may use it.
        policy = rogue()
        snapshot = caster_board(mp=33)
        policy.prime(snapshot)
        self.assertGreater(realm_spells.escape_reserve(policy, snapshot), 0)
        self.assertIsNotNone(policy._find_recall_scroll(snapshot))

    def test_ledger_and_dungeon_counts_take_the_held_spell_as_one_unit(self):
        policy = rogue()
        snapshot = caster_board(mp=0)                 # held: the maximum mana pays it
        policy.prime(snapshot)
        self.assertEqual(policy._count_recall_means(snapshot), 1)
        self.assertEqual(policy._dungeon_recall_units(snapshot), 1)
        with_scrolls = caster_board(inventory=[*BOOKS, scroll("e", SV_SCROLL_WORD_OF_RECALL)])
        self.assertEqual(policy._count_recall_means(with_scrolls), 3)
        self.assertEqual(policy._count_recall_scrolls(with_scrolls), 2)
        short = caster_board(max_mp=30)
        self.assertEqual(policy._count_recall_means(short), 0)
        for class_id in (0, 16):
            with self.subTest(class_id=class_id):
                other = caster_board(class_id=class_id)
                self.assertEqual(policy._count_recall_means(other), 0)
                self.assertIsNone(policy._find_recall_scroll(other))

    def test_town_departure_casts_before_reading_a_scroll(self):
        policy = rogue()
        recall = scroll("e", SV_SCROLL_WORD_OF_RECALL, name="帰還の巻物")
        snapshot = caster_board(depth=0, inventory=[*BOOKS, recall])
        policy.prime(snapshot)
        device = policy._town_recall_device(snapshot)
        self.assertTrue(realm_spells.is_spell_means(device))
        self.assertEqual(policy._town_recall_device_key(snapshot, device, "a"), "mcga")
        warrior = caster_board(depth=0, class_id=0, inventory=[*BOOKS, recall])
        self.assertIs(policy._town_recall_device(warrior), recall)

    def test_the_way_home_rests_for_the_spell_mana(self):
        policy = rogue()
        policy._returning_to_town = True
        # Word of Recall costs 33; the escape reserve (Teleport 12) alone would not rest at 20.
        self.assertFalse(realm_spells.mana_rest_due(policy, caster_board(mp=40)))
        self.assertTrue(realm_spells.mana_rest_due(policy, caster_board(mp=20)))
        recall = scroll("e", SV_SCROLL_WORD_OF_RECALL, name="帰還の巻物")
        self.assertFalse(realm_spells.mana_rest_due(
            policy, caster_board(mp=20, inventory=[*BOOKS, recall])))
        policy._returning_to_town = False
        self.assertFalse(realm_spells.mana_rest_due(policy, caster_board(mp=20)))

    def test_return_reads_the_spell_through_choose_key(self):
        policy = rogue()
        grids = {Position(y, x): grid(y, x) for y in range(5, 16) for x in range(5, 61)}
        snapshot = replace(caster_board(mp=120), grids=grids)
        policy._returning_to_town = True
        keys = []
        turn = snapshot.turn
        for _ in range(4):
            snapshot = replace(snapshot, turn=turn, completed_operation_owner=policy.last_reason
                               or None, completed_operation_receipt={})
            keys.append((policy.choose_key(snapshot), policy.last_reason))
            turn += 10
        self.assertIn(("mcg", "return:recall"), keys, keys)


class TeleportLevelMeansTest(unittest.TestCase):
    def test_spell_stands_in_with_its_confirmation(self):
        policy = rogue()
        snapshot = caster_board()
        policy.prime(snapshot)
        means = policy._teleport_level_item(snapshot)
        self.assertTrue(realm_spells.is_spell_means(means))
        self.assertEqual(means.sval, SV_SCROLL_TELEPORT_LEVEL)
        self.assertEqual(policy._teleport_level_read_key(snapshot, means), "mcfy")

    def test_scroll_first_and_no_spell_short_or_for_other_classes(self):
        policy = rogue()
        level = scroll("e", SV_SCROLL_TELEPORT_LEVEL, name="テレポート・レベルの巻物")
        snapshot = caster_board(inventory=[*BOOKS, level])
        policy.prime(snapshot)
        self.assertIs(policy._teleport_level_item(snapshot), level)
        for label, snap in (("mana", caster_board(mp=22)), ("warrior", caster_board(class_id=0)),
                            ("magic-eater", caster_board(class_id=16))):
            with self.subTest(label):
                policy.prime(snap)
                self.assertIsNone(policy._teleport_level_item(snap))

    def test_summoner_exits_and_threat_means_count_it(self):
        from hengbot import threat_escape
        policy = rogue()
        snapshot = caster_board()
        policy.prime(snapshot)
        exits = policy._immobile_summoner_exits(snapshot)
        self.assertTrue(realm_spells.is_spell_means(exits.teleport_level))
        self.assertTrue(realm_spells.is_spell_means(exits.recall))
        means = threat_escape.escape_means(policy, snapshot, [])
        self.assertIn("teleport-level", means)
        self.assertIn("recall", means)


class ClairvoyanceTest(unittest.TestCase):
    def test_whole_floor_triggers_prefer_clairvoyance(self):
        policy = rogue(mp=200, level=40)
        snapshot = caster_board(mp=200, max_mp=200)
        policy.prime(snapshot)
        self.assertEqual(realm_spells.map_spell(policy, snapshot, "deep-climb"),
                         realm_spells.CLAIRVOYANCE)
        self.assertEqual(realm_spells.map_spell(policy, snapshot, "sealed-pocket"),
                         realm_spells.MAGIC_MAPPING)
        # Clairvoyance 52 + Teleport 12 + Detect Monsters 2 (not landed) is 66 > 60: Magic Mapping.
        short = caster_board(mp=60, max_mp=200)
        self.assertEqual(realm_spells.map_spell(policy, short, "deep-climb"),
                         realm_spells.MAGIC_MAPPING)

    def test_deep_climb_map_is_the_whole_floor(self):
        policy = rogue(mp=200, level=40)
        snapshot = caster_board(mp=200, max_mp=200)
        policy.prime(snapshot)
        self.assertEqual(area_mapping.deep_climb_key(policy, snapshot), "mdd")
        memory = area_mapping._floor_memory(policy, snapshot)
        self.assertEqual(memory.pending[2], realm_spells.WHOLE_FLOOR_RADIUS)

    def test_new_floor_casts_clairvoyance_through_choose_key(self):
        policy = rogue(mp=200, level=40)
        grids = {Position(y, x): grid(y, x) for y in range(5, 16) for x in range(5, 61)}
        grids[Position(5, 5)] = grid(5, 5, downstairs=True)
        grids[Position(5, 6)] = grid(5, 6, upstairs=True)
        snapshot = replace(caster_board(mp=200, max_mp=200), grids=grids)
        keys, turn = [], snapshot.turn
        for _ in range(3):
            snapshot = replace(snapshot, turn=turn, completed_operation_owner=policy.last_reason
                               or None, completed_operation_receipt={})
            keys.append((policy.choose_key(snapshot), policy.last_reason))
            turn += 10
        # Detection True (book 2's g) serves the Detect Monsters row at level 40, then the map.
        self.assertEqual(keys[:2], [("mbg", "realm-spell:new-floor:detect-all"),
                                    ("mdd", "realm-spell:new-floor:map-area")], keys)


class DetectObjectsTest(unittest.TestCase):
    def test_mining_detection_key(self):
        policy = rogue()
        snapshot = caster_board(depth=1)
        policy.prime(snapshot)
        self.assertEqual(realm_spells.detect_objects_key(policy, snapshot), "mca")
        self.assertIsNone(realm_spells.detect_objects_key(policy, caster_board(class_id=0)))


class BooksTest(unittest.TestCase):
    def test_third_and_fourth_books_are_kept_with_a_spare(self):
        policy = rogue()
        two = book("c", 2, count=2)
        snapshot = caster_board(inventory=[book(), book("b", 1), two])
        self.assertEqual(realm_spell_book.retained_count(policy, snapshot, two), 2)
        # A Home copy is the spare: the carried stack keeps one.
        policy._home_knowledge_items = [book("home-surplus", 2)]
        self.assertEqual(realm_spell_book.retained_count(policy, snapshot, two), 1)
        # Not an unused book for the caster (item_fate), still one for a Warrior.
        self.assertFalse(item_fate._unused_book(
            replace_own(policy, {TVAL_SORCERY_BOOK}), snapshot, two))
        warrior = caster_board(class_id=0, inventory=[two])
        self.assertTrue(item_fate._unused_book(replace_own(policy, {TVAL_SORCERY_BOOK}),
                                               warrior, two))
        self.assertEqual(realm_spell_book.retained_count(policy, warrior, two), 0)

    def test_carried_book_is_not_sold(self):
        policy = rogue()
        snapshot = caster_board(depth=0, inventory=[book(), book("b", 1), book("c", 2)])
        policy.prime(snapshot)
        self.assertIsNone(policy._find_book_sale(snapshot))
        warrior = caster_board(depth=0, class_id=0, inventory=[book("c", 2)])
        policy.prime(warrior)
        self.assertEqual(policy._find_book_sale(warrior).slot, "c")

    def test_wanted_from_three_levels_below_the_spell_bought_for(self):
        policy = rogue()
        owned = [book(), book("b", 1)]
        self.assertEqual(realm_spell_book.wanted_books(policy, caster_board(level=23,
                                                                            inventory=owned)), ())
        self.assertEqual(realm_spell_book.wanted_books(policy, caster_board(level=24,
                                                                            inventory=owned)), (2,))
        self.assertEqual(realm_spell_book.wanted_books(policy, caster_board(level=34,
                                                                            inventory=owned)),
                         (2, 3))

    def test_black_market_shelf_is_bought_above_the_resupply_but_no_magic_shop_errand(self):
        policy = rogue()
        ware = store_item("c", TVAL_SORCERY_BOOK, 2, price=60000, name="[紋様仙術]")
        snapshot = caster_board(depth=0, level=30, inventory=[book(), book("b", 1)])
        market = replace(snapshot, store=StoreState(STORE_BLACK, [ware]))
        market = replace(market, player=replace(market.player, gold=200000))
        policy.prime(market)
        policy._full_departure_resupply_reserve = lambda board: 5000
        self.assertEqual(realm_spell_book.purchase_units(policy, market, ware), 1)
        poor = replace(market, player=replace(market.player, gold=60000))
        self.assertEqual(realm_spell_book.purchase_units(policy, poor, ware), 0)
        self.assertFalse(realm_spell_book.errand_wanted(policy, market))
        self.assertEqual(STORE_MAGIC, 5)


class LeavingCastInputTest(unittest.TestCase):
    """The casts' questions through the production executor (test_realm_spells_input_1126's model
    of cmd-spell.cpp, with realm-sorcery.cpp's Teleport Level confirmation and recall_player's
    questions)."""

    def game(self, **kwargs):
        from test_realm_spells_input_1126 import SpellGame

        class LeavingGame(SpellGame):
            def __init__(self, *, confirm=(), chooser=(), shallower=(), **rest):
                self.confirm, self.chooser, self.shallower = confirm, chooser, shallower
                super().__init__(**rest)

            def key(self, char):
                if self.mode == "spell" and self.command == "m" and char in self.confirm:
                    self.mode = "confirm"
                elif self.mode == "spell" and self.command == "m" and char in self.chooser:
                    self.mode = "chooser"
                elif self.mode == "spell" and self.command == "m" and char in self.shallower:
                    self.mode = "shallower"
                elif self.mode in {"confirm", "shallower"}:
                    self.answers.append((self.mode, char))
                    self.mode, self.energy_use = "command", 100
                elif self.mode == "chooser":
                    self.answers.append((self.mode, char))
                    self.mode, self.energy_use = "command", 0 if char == "" else 100
                else:
                    super().key(char)

            def render(self):
                from tests.support import recorded as input_tests
                if self.mode == "confirm":
                    return input_tests.prompt_screen("本当に他の階にテレポートしますか？ [y/n]")
                if self.mode == "shallower":
                    return input_tests.prompt_screen(
                        "ここは最深到達階より浅い階です。この階に戻って来ますか？ [y/n]")
                if self.mode == "chooser":
                    screen = input_tests.prompt_screen("どのダンジョンに帰還しますか:")
                    screen["lines"][2] = " " * 14 + "      a) 鉄獄             : 最大 40 階"
                    return screen
                return super().render()

        game = LeavingGame(**kwargs)
        game.answers = []
        return game

    def send(self, game, key, reason):
        from test_realm_spells_input_1126 import SpellInputTest
        case = SpellInputTest()
        case.addCleanup = self.addCleanup
        return case.send(game, key, reason)

    def test_teleport_level_answers_its_confirmation(self):
        game = self.game(confirm=("f",))
        receipt = self.send(game, "mafy", "summoner:teleport-level")
        self.assertEqual(game.accepted, ["m", "a", "f", "y"])
        self.assertIsNone(receipt.get("refusal"))
        self.assertEqual(game.answers, [("confirm", "y")])

    def test_surface_recall_answers_the_listed_dungeon_only(self):
        game = self.game(chooser=("g",))
        receipt = self.send(game, "maga", "town:recall-to-1")
        self.assertEqual(game.answers, [("chooser", "a")])
        self.assertIsNone(receipt.get("refusal"))
        game = self.game(chooser=("g",))
        receipt = self.send(game, "magb", "town:recall-to-1")
        self.assertEqual(game.answers, [("chooser", "")])
        self.assertEqual(receipt.get("refusal"), realm_spells_input.CAST_REFUSED)

    def test_shallower_floor_question_is_the_executors(self):
        game = self.game(shallower=("g",))
        self.send(game, "mag", "return:recall")
        self.assertEqual(game.answers, [("shallower", "n")])


def replace_own(policy, tvals):
    policy._own_book_tvals = frozenset(tvals)
    return policy


if __name__ == "__main__":
    unittest.main()
