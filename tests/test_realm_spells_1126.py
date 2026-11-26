"""The Rogue's Sorcery spells as means of the existing rules (owner 2026-11-26).

Owner 2026-11-26 (verbatim): 「盗賊は魔法を使える。無視する戦略ならばそれも良いが、多少なり使うと
大きく助けになる。」

Recorded: tests/fixtures/rogue-spell-list-1126.json, the ``spell_list`` record the game wrote for
the Golem Rogue template's first Sorcery book at level 10 (live capture 2026-11-26, a private
headless game; reduced to the keys realm_spells reads, the rows as recorded).  The game's numbers
in the test names are the screen's of that capture: costs 2/5/7/7/8/12/12/15 at no proficiency,
fails 9%/9%/33% at full mana (13%/29%/93% at 0 mana).

DECLARED CONSTRUCTED: the boards (a Rogue, class 3, with the book in slot ``a``, its mana and
stats; a Warrior and a Magic-Eater for the no-op checks), the second book's rows (Magic Mapping,
Teleport Away, Haste Self as the list would show them), the hostiles.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import unittest
from dataclasses import replace
from pathlib import Path

from policy_fixtures import grid, hostile, item, player
from hengbot import me_powers, realm_spell_book, realm_spells
from hengbot.class_roles import PLAYER_CLASS_ROGUE, casts_realm_spells, realm_books_unusable
from hengbot.model import (
    SV_SCROLL_PHASE_DOOR, SV_SCROLL_TELEPORT, TVAL_SCROLL, TVAL_SORCERY_BOOK, Position, Snapshot,
)
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "rogue-spell-list-1126.json"
STAT_INDEX_INT_15 = (15, 12, 0, 15, 15, 2)    # INT 15 is stat index 12 (3 -> 0)


def recorded():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def book(slot="a", sval=0, count=1):
    return item(slot, TVAL_SORCERY_BOOK, sval, name=f"仙術の魔法書 {sval + 1}", count=count)


def board(*, mp=12, level=10, class_id=PLAYER_CLASS_ROGUE, inventory=None, depth=5,
          monsters=(), blind=False, stun_rank=0, can_study=None, turn=5000):
    grids = {Position(y, x): grid(y, x) for y in range(5, 16) for x in range(5, 16)}
    you = replace(player(10, 10, hp=100, max_hp=100, mp=mp, max_mp=12, level=level,
                         class_id=class_id, blind=blind),
                  stat_index=STAT_INDEX_INT_15, stun_rank=stun_rank,
                  stunned=stun_rank > 0, can_study=can_study)
    return Snapshot(you, grids, list(monsters), floor_key=(1, depth, 0), turn=turn,
                    inventory=[book()] if inventory is None else inventory,
                    town_flag=depth == 0, protocol_version=3, can_see_own_grid=True)


def caster(record=None):
    policy = HengbotPolicy()
    realm_spells.observe_list(policy, record or recorded())
    return policy


def second_book_record(mp=40, level=30):
    """DECLARED CONSTRUCTED: the second book's list as the game would draw it (spells 8-15)."""
    rows = [{"spell_id": spell.spell_id, "status": "available", "name": spell.names[0],
             "level": realm_spells.derived(spell)[0], "mana": realm_spells.derived(spell)[1],
             "fail": 9}
            for spell in realm_spells.SPELLS if spell.book == 1]
    return {"type": "spell_list", "turn": 9000,
            "player": {"mp": mp, "level": level, "status": {"stun_rank": 0}},
            "spell_list": {"realm_id": realm_spells.REALM_SORCERY, "spells": rows}}


class GameNumbersTest(unittest.TestCase):
    def test_rogue_sorcery_table_matches_the_derivation(self):
        # magic-aptitude.cpp with ClassMagicDefinitions' L 30 / M 15 / D 3 and the Rogue's -2.
        expected = {0: (2, 1, 29), 1: (2, 3, 30), 2: (5, 4, 31), 3: (5, 4, 36), 4: (6, 5, 36),
                    5: (8, 7, 41), 6: (9, 7, 36), 7: (11, 9, 81), 8: (13, 9, 81),
                    9: (15, 9, 81), 10: (16, 9, 81), 11: (19, 9, 56), 12: (25, 16, 66),
                    13: (29, 16, 66), 14: (35, 26, 76), 15: (40, 39, 81)}
        self.assertEqual({spell.spell_id: realm_spells.derived(spell)
                          for spell in realm_spells.SPELLS}, expected)

    def test_cost_at_no_proficiency_is_the_screens(self):
        # The live list: 2 5 7 7 8 12 12 15 for the first book, nothing learned yet cast.
        self.assertEqual([realm_spells.need_mana(realm_spells.derived(spell)[1])
                          for spell in realm_spells.SPELLS[:8]], [2, 5, 7, 7, 8, 12, 12, 15])
        self.assertEqual(realm_spells.need_mana(7, realm_spells.SPELL_EXP_EXPERT), 7)

    def test_formula_floor_is_the_int_minimum(self):
        you = board().player
        self.assertEqual(realm_spells.min_failure(you), 9)          # adj_mag_fail[15] = 9
        self.assertEqual(realm_spells.formula_fail(realm_spells.BY_ID[0], you), 9)
        self.assertEqual(realm_spells.formula_fail(realm_spells.BY_ID[1], you), 9)


class ShownListTest(unittest.TestCase):
    def test_recorded_list_reads_learned_cost_and_the_full_mana_fail(self):
        policy = caster()
        self.assertTrue(realm_spells.learned(policy, realm_spells.DETECT_MONSTERS))
        self.assertTrue(realm_spells.learned(policy, realm_spells.TELEPORT))      # untried
        self.assertFalse(realm_spells.learned(policy, realm_spells.DETECT_DOORS_TRAPS))
        self.assertEqual(realm_spells.cost(policy, realm_spells.TELEPORT), 12)
        you = board().player
        # Shown at 0 mana: 13/29/93; the game showed 9/9/33 at full mana.
        self.assertEqual([realm_spells.unstunned_failure(policy, you, spell_id)
                          for spell_id in (0, 1, 5)], [9, 9, 33])

    def test_stun_of_the_board_is_added(self):
        policy = caster()
        self.assertEqual(realm_spells.success(policy, board(stun_rank=1), 1), 81)
        self.assertEqual(realm_spells.success(policy, board(), 1), 91)

    def test_other_realm_list_is_not_kept(self):
        policy = HengbotPolicy()
        record = recorded()
        record["spell_list"] = dict(record["spell_list"], realm_id=1)
        realm_spells.observe_list(policy, record)
        self.assertIsNone(realm_spells.listing(policy, 0))


class EscapeMeansTest(unittest.TestCase):
    def test_teleport_spell_stands_in_when_no_scroll_is_carried(self):
        policy = caster()
        snapshot = board()
        policy.prime(snapshot)
        means = policy._escape_scroll(snapshot, teleport_only=True)
        self.assertTrue(realm_spells.is_spell_means(means))
        self.assertTrue(means.is_teleport_scroll)
        self.assertEqual(policy._read_key(snapshot, means), "maf")

    def test_a_carried_scroll_is_read_first(self):
        policy = caster()
        scroll = item("b", TVAL_SCROLL, SV_SCROLL_TELEPORT, name="テレポートの巻物", count=3)
        snapshot = board(inventory=[book(), scroll])
        policy.prime(snapshot)
        self.assertIs(policy._escape_scroll(snapshot), scroll)

    def test_phase_spell_when_teleport_cannot_be_cast(self):
        policy = caster()
        snapshot = board(mp=6)                  # Teleport costs 12, Short Teleport 5
        policy.prime(snapshot)
        self.assertIsNone(policy._escape_scroll(snapshot, teleport_only=True))
        means = policy._escape_scroll(snapshot)
        self.assertEqual((means.sval, policy._read_key(snapshot, means)),
                         (SV_SCROLL_PHASE_DOOR, "mab"))

    def test_no_spell_below_half_success_blind_or_without_the_book(self):
        policy = caster()
        record = recorded()
        for row in record["spell_list"]["spells"]:
            row["fail"] = 95                    # shown at the cap: no spell is a means
        policy_low = caster(record)
        for label, used, snapshot in (
                ("fail 95", policy_low, board()),
                ("blind", policy, board(blind=True)),
                ("no book", policy, board(inventory=[]))):
            with self.subTest(label):
                used.prime(snapshot)
                self.assertIsNone(used._escape_scroll(snapshot))

    def test_non_casters_never_get_a_spell(self):
        for class_id in (0, 16):
            with self.subTest(class_id=class_id):
                policy = caster()
                snapshot = board(class_id=class_id)
                policy.prime(snapshot)
                self.assertIsNone(policy._escape_scroll(snapshot))
                self.assertIsNone(realm_spells.escape_means(policy, snapshot, SV_SCROLL_TELEPORT))


class OccasionTest(unittest.TestCase):
    def ask(self, policy, snapshot, occasion=me_powers.FLOOR, target=None):
        policy.prime(snapshot)
        me_powers.observe(policy, snapshot)
        return me_powers.power_key(policy, snapshot, occasion, target)

    def test_detect_monsters_on_a_new_floor_holds_the_escape_mana(self):
        policy = caster()
        self.assertEqual(self.ask(policy, board(mp=14)), "maa")
        self.assertEqual(policy.last_reason, "realm-spell:new-floor:detect-monsters")
        # 12 kept for Teleport: the detection's 2 would eat into it.
        self.assertIsNone(self.ask(caster(), board(mp=13)))
        # In town no reserve is held, but no occasion is asked there (me_powers._gate).
        self.assertIsNone(self.ask(caster(), board(mp=14, depth=0)))

    def test_a_landed_detection_is_not_cast_again_for_the_floor(self):
        policy = caster()
        snapshot = board(mp=14)
        self.assertEqual(self.ask(policy, snapshot), "maa")
        later = replace(snapshot, turn=snapshot.turn + 10,
                        completed_operation_owner=policy.last_reason,
                        completed_operation_receipt={})
        me_powers.observe(policy, later)
        self.assertIsNone(me_powers.power_key(policy, later, me_powers.FLOOR))

    def test_haste_in_place_of_an_attack_and_teleport_away_at_an_unbeatable(self):
        policy = caster(second_book_record())
        realm_spells.observe_list(policy, recorded())
        books = [book(), book("b", 1)]
        # Haste: the FIGHT occasion, success 91 >= 80.
        self.assertEqual(self.ask(policy, board(mp=40, level=30, inventory=books),
                                  me_powers.FIGHT), "mbf")
        self.assertEqual(policy.last_reason, "realm-spell:fight-unhasted:speed")

    def test_warrior_and_magic_eater_tables_are_unchanged(self):
        policy = caster()
        self.assertIsNone(self.ask(policy, board(class_id=0)))
        self.assertTrue(casts_realm_spells(PLAYER_CLASS_ROGUE))
        self.assertFalse(casts_realm_spells(0) or casts_realm_spells(16))
        self.assertTrue(realm_books_unusable(0))
        self.assertFalse(realm_books_unusable(PLAYER_CLASS_ROGUE))


class BookAndStudyTest(unittest.TestCase):
    def test_one_copy_of_each_cast_book_is_retained(self):
        policy = caster()
        snapshot = board(inventory=[book(count=2), book("b", 2)])
        self.assertEqual(realm_spell_book.retained_count(policy, snapshot, book(count=2)), 1)
        self.assertEqual(realm_spell_book.retained_count(policy, snapshot, book("b", 2)), 0)
        self.assertEqual(realm_spell_book.retained_count(
            policy, board(class_id=0), book()), 0)
        self.assertEqual(policy._retention_reservation_baseline_detail(snapshot, book(count=2)),
                         (1, realm_spell_book.RETENTION_BRANCH))

    def test_study_order_and_the_learned_message(self):
        policy = caster()
        snapshot = board(can_study=True)
        # Learned: 0, 1, 5.  Next in LEARN_ORDER at level 10: Detect Doors and Traps (lv 5).
        self.assertEqual(realm_spell_book.study_choice(policy, snapshot),
                         (0, realm_spells.DETECT_DOORS_TRAPS))
        self.assertEqual(realm_spell_book.study_key(policy, snapshot), "Gac")
        self.assertIsNone(realm_spell_book.study_choice(policy, board(can_study=False)))
        realm_spell_book.observe(policy, replace(snapshot, messages=(
            "罠と扉感知の呪文を学んだ。あと 1 つの呪文を学べる。",)))
        self.assertTrue(realm_spells.learned(policy, realm_spells.DETECT_DOORS_TRAPS))
        self.assertEqual(realm_spell_book.study_choice(policy, snapshot),
                         (0, realm_spells.LIGHT_AREA))

    def test_rest_for_the_escape_mana_in_the_dungeon_only(self):
        policy = caster()
        self.assertTrue(realm_spells.mana_rest_due(policy, board(mp=11)))      # Teleport 12
        self.assertFalse(realm_spells.mana_rest_due(policy, board(mp=12)))
        self.assertFalse(realm_spells.mana_rest_due(policy, board(mp=0, depth=0)))
        self.assertFalse(realm_spells.mana_rest_due(policy, board(mp=0, class_id=0)))

    def test_missing_list_is_read_turn_free_at_most_three_times(self):
        policy = HengbotPolicy()
        snapshot = board()
        policy.prime(snapshot)
        keys = []
        for sequence in range(0, 30, 5):
            policy._decision_sequence = sequence
            keys.append(realm_spell_book.resume_read_key(policy, snapshot))
        self.assertEqual(keys, ["ba", "ba", "ba", None, None, None])
        self.assertEqual(policy.last_reason, realm_spell_book.BROWSE_REASON)
        self.assertIsNone(realm_spell_book.resume_read_key(caster(), board()))


if __name__ == "__main__":
    unittest.main()
