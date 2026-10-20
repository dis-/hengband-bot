"""The widened junk scope, step 1a (owner 2026-10-20, design DESIGN-junk-scope-1020).

One predicate ``_junk_class`` names the junk classes remains / cursed /
harmful-consumable / unusable-book / unused-ammo.  It is wired into the
dungeon disposal before the return (#70 site), the Home-full relief order
(junk first, no equipment dominance proof: review M2) and the floor pickup
filter (unused ammunition by tval).  Third and fourth realm books are always
carried home and sold (owner 2026-10-20), never junk.

Recorded inputs:

* ``lantern-lost-20261018.jsonl.gz`` line 0 (C4-A life-013 warrior, Yeek cave
  level 1): the return-start board.  The worn launcher is a light crossbow
  (tval 19 sval 23), the pack carries 84 bolts (slot p) and seven remains
  (slots q-w), and the floor shows a bolt (tval 18) pile at (11,59).
* ``home-junk-bones-20261018.jsonl.gz``: the full Home of capture 164159 (the
  same character; 240/240, light crossbow worn).

DECLARED CONSTRUCTED (each named again where it is built): the worn lantern
fuel above the refill threshold, the pack without its recorded remains, one
added pack or shelf item per class (a cursed armour, a cursed ego, a cursed
artifact, an uncursed ego, a broken sword, a cursed polearm, Salt Water, a
Poison mushroom, realm books 1-4), a sling worn in place of the recorded
light crossbow, a non-warrior class id, a fixed-quest bolt reservation, the
Home shelf reduced to its non-junk stock plus one added item, and a one-book
pack for the exchange selector.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.baseitem_knowledge import find_baseitem_definitions, load_baseitem_costs
from hengbot.cli import _consume_response_sequence
from hengbot.model import InventoryItem, Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import LANTERN_REFILL_FUEL
from hengbot.store_sale import ZERO_BASE_KINDS
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
DUNGEON = FIXTURES / "lantern-lost-20261018.jsonl.gz"
HOME = FIXTURES / "home-junk-bones-20261018.jsonl.gz"
BOLT_PILE = Position(11, 59)


def _gear(slot, name, tval, sval, **flags):
    return InventoryItem(slot, name, 1, tval, sval, True, True,
                         is_equipment=True, **flags)


def _consumable(slot, name, tval, sval):
    return InventoryItem(slot, name, 1, tval, sval, True, True)


# DECLARED CONSTRUCTED pack/shelf items, one per class and control.
CURSED_ARMOUR = _gear("q", "防護服 [6,-4] {呪われている}", 36, 9,
                      is_cursed=True, ac=6, to_a=-4)
CURSED_EGO = _gear("q", "モルグルのローブ [2,+13] {呪われている}", 36, 2,
                   is_cursed=True, is_ego=True, ac=2, to_a=13)
CURSED_ARTIFACT = _gear("q", "★呪われたクローク", 35, 1, is_cursed=True,
                        is_artifact=True, ac=1, to_a=10)
UNCURSED_EGO = _gear("q", "耐火のクローク [1,+5]", 35, 1, is_ego=True,
                     ac=1, to_a=5)
BROKEN_SWORD = _gear("q", "折れたタルワール (2d4) (-2,-5)", 23, 15,
                     is_broken=True, damage_dice_num=2, damage_dice_sides=4,
                     to_h=-2, to_d=-5)
# A heavy polearm: without a calibration its expected damage is unknown, so
# the superior-item gate refuses it unless junk skips the dominance proof.
CURSED_POLEARM = _gear("q", "ロッホアーバー・アックス (3d8) (-5,-3) {呪われている}",
                       22, 28, is_cursed=True, damage_dice_num=3,
                       damage_dice_sides=8, to_h=-5, to_d=-3)
SALT_WATER = _consumable("q", "塩水の薬", 75, 5)
POISON_MUSHROOM = _consumable("q", "毒キノコ", 80, 0)
BOOKS = tuple(_consumable("q", f"生命の魔法書 {sval + 1}", 90, sval)
              for sval in range(4))


class JunkScopeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(DUNGEON, "rt", encoding="utf-8") as stream:
            cls.dungeon_lines = stream.read().splitlines()
        with gzip.open(HOME, "rt", encoding="utf-8") as stream:
            cls.home_lines = stream.read().splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _consume(self, policy, line):
        _decoded, snapshots = _consume_response_sequence(
            [line], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        return snapshots

    def _dungeon(self, *added, sling=False, bare=False):
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        board = self._consume(policy, self.dungeon_lines[0])[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        # DECLARED CONSTRUCTED: lantern fuel above the refill threshold; with
        # ``sling`` a plain sling worn in place of the light crossbow.
        sling_item = _gear("bow", "スリング (x2)", 19, 2)
        board = replace(board, equipment=type(board.equipment)(
            replace(item, fuel=LANTERN_REFILL_FUEL + 1) if item.is_light
            else sling_item if sling and item.is_launcher else item
            for item in board.equipment))
        # DECLARED CONSTRUCTED: the added items take the first recorded
        # remains slots from q on (the pack stays full, which starts the
        # recorded return); ``bare`` drops every recorded remain.
        added = {chr(ord("q") + index): item for index, item in enumerate(added)}
        board = replace(board, inventory=type(board.inventory)(
            replace(added[item.slot], slot=item.slot) if item.slot in added else item
            for item in board.inventory
            if not bare or item.tval not in {1, 3, 10}))
        return policy, board

    def _home(self, *added):
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        board = self._consume(policy, self.home_lines[0])[-1]
        # DECLARED CONSTRUCTED: the posted ~9 request whose answer is line 1.
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        self._consume(policy, self.home_lines[1])
        board = self._consume(policy, self.home_lines[2])[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        # DECLARED CONSTRUCTED: the shelf without its recorded junk, plus the
        # added items (the catalogue stays 240 rows: the added items replace
        # junk rows).
        shelf = tuple(item for item in policy._home_knowledge_items
                      if policy._junk_class(board, item) is None)
        policy.consume_home_knowledge((*shelf, *(
            replace(item, slot="home") for item in added)))
        bolts = board.inventory[-1]
        # DECLARED CONSTRUCTED: the relief's blocked deposit (the bolt stack).
        policy._begin_home_full_relief(board, (
            (policy._item_signature(bolts), bolts.count, bolts.count),), refused=True)
        return policy, board

    # --- the predicate -------------------------------------------------

    def test_junk_class_names_each_class_on_the_recorded_board(self):
        policy, board = self._dungeon()
        self.assertEqual(board.player.class_id, 0)  # recorded warrior
        expected = {
            CURSED_ARMOUR: "cursed", CURSED_EGO: "cursed", BROKEN_SWORD: "cursed",
            CURSED_POLEARM: "cursed", SALT_WATER: "harmful-consumable",
            POISON_MUSHROOM: "harmful-consumable",
            BOOKS[0]: "unusable-book", BOOKS[1]: "unusable-book",
            # Controls: never junk.
            CURSED_ARTIFACT: None, UNCURSED_EGO: None, BOOKS[2]: None, BOOKS[3]: None,
            replace(SALT_WATER, aware=False): None,
        }
        for item, junk in expected.items():
            with self.subTest(item=item.name):
                self.assertEqual(policy._junk_class(board, item), junk)
        self.assertEqual({item.slot: policy._junk_class(board, item)
                          for item in board.inventory
                          if policy._junk_class(board, item) is not None},
                         dict.fromkeys("qrstuvw", "remains"))

    def test_control_books_stay_for_a_class_that_reads_them(self):
        policy, board = self._dungeon(bare=True)
        # DECLARED CONSTRUCTED: a mage (class id 1) on the same board.
        mage = replace(board, player=replace(board.player, class_id=1))
        self.assertIsNone(policy._junk_class(mage, BOOKS[0]))
        self.assertEqual(policy._junk_class(board, BOOKS[0]), "unusable-book")

    def test_unused_ammo_follows_the_worn_launcher_only(self):
        policy, board = self._dungeon()
        bolts = next(item for item in board.inventory if item.tval == 18)
        self.assertIsNone(policy._junk_class(board, bolts))  # light crossbow
        policy, sling = self._dungeon(sling=True)
        bolts = next(item for item in sling.inventory if item.tval == 18)
        self.assertEqual(policy._junk_class(sling, bolts), "unused-ammo")
        # DECLARED CONSTRUCTED control: the same stack as an identified ego.
        self.assertIsNone(policy._junk_class(sling, replace(bolts, is_ego=True)))
        # DECLARED CONSTRUCTED: no launcher worn keeps every ammunition.
        bare = replace(sling, equipment=type(sling.equipment)(
            item for item in sling.equipment if not item.is_launcher))
        self.assertIsNone(policy._junk_class(bare, bolts))

    def test_control_quest_reserved_bolts_stay_with_a_sling(self):
        policy, board = self._dungeon(sling=True)
        bolts = next(item for item in board.inventory if item.tval == 18)
        # DECLARED CONSTRUCTED: a fixed-quest carry strategy reserving 99 bolts
        # while the sling is still worn (policy_home retention exception).
        strategy = SimpleNamespace(required_force={})
        with patch.object(HengbotPolicy, "_carry_procurement_strategy",
                          lambda *_args, **_kwargs: strategy), \
                patch.object(HengbotPolicy, "_quest_carry_target_for_item",
                             lambda _self, _board, item, _force: (
                                 ("bolts", 0, 99) if item.tval == 18 else None)):
            self.assertIsNone(policy._junk_class(board, bolts))
            self.assertFalse(policy._floor_pile_is_junk(board, board.grids[BOLT_PILE]))

    def test_zero_base_kinds_match_the_game_definitions(self):
        path = find_baseitem_definitions(Path(r"C:\hengband"))
        if path is None:
            self.skipTest("lib/edit/BaseitemDefinitions.jsonc is absent")
        costs = load_baseitem_costs(path)
        self.assertEqual(ZERO_BASE_KINDS,
                         frozenset(kind for kind, cost in costs.items() if cost <= 0))
        self.assertTrue({(80, sval) for sval in range(10)} <= ZERO_BASE_KINDS)

    def test_invariant_supplies_worn_and_reserved_items_are_never_junk(self):
        policy, board = self._dungeon()
        home_policy, home = self._home()
        for owner, snapshot, items in (
                (policy, board, (*board.equipment, *board.inventory)),
                (home_policy, home, (*home.equipment, *home.inventory,
                                     *home_policy._home_knowledge_items))):
            for item in items:
                if not isinstance(item, InventoryItem):
                    item = owner._inventory_item_from_store_item(item)
                kept = (any(item is worn for worn in snapshot.equipment)
                        or HengbotPolicy._survival_essential(item)
                        or HengbotPolicy._is_useful_device(item)
                        or owner._item_is_procurement_protected(snapshot, item))
                if kept:
                    with self.subTest(item=item.name):
                        self.assertIsNone(owner._junk_class(snapshot, item))
        preparation = getattr(home_policy, "_equipment_optimization_preparation", None)
        best = getattr(getattr(preparation, "result", None), "best", None)
        for _slot, owned in (best.loadout.slots if best is not None else ()):
            self.assertIsNone(home_policy._junk_class(home, owned.item))

    # --- before the return (#70 site) ----------------------------------

    def test_return_start_destroys_each_carried_junk_class(self):
        # The recorded character eats mana (food_type 4): its full-pack
        # disposal already sheds any food, so the mushroom is pinned above.
        for item in (CURSED_ARMOUR, CURSED_EGO, CURSED_POLEARM, SALT_WATER,
                     BOOKS[0]):
            with self.subTest(item=item.name):
                policy, board = self._dungeon(item)
                self.assertTrue(policy._should_start_town_return(board))
                key = policy.choose_key(board)
                self.assertEqual(policy.last_reason, "inventory:destroy-worthless-junk")
                self.assertTrue(key.endswith("kq"), key)

    def test_return_start_destroys_bolts_for_an_unworn_launcher(self):
        policy, board = self._dungeon(sling=True)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "inventory:destroy-worthless-junk")
        self.assertTrue(key.endswith("kp"), key)

    def test_control_return_start_keeps_non_junk(self):
        for item in (CURSED_ARTIFACT, UNCURSED_EGO, BOOKS[2], BOOKS[3]):
            with self.subTest(item=item.name):
                policy, board = self._dungeon(item)
                key = policy.choose_key(board)
                # The next recorded remain (slot r) goes instead.
                self.assertEqual(policy.last_reason, "inventory:destroy-worthless-junk")
                self.assertTrue(key.endswith("kr"), key)

    # --- floor ---------------------------------------------------------

    def test_floor_bolt_pile_is_not_loot_with_a_sling_worn(self):
        policy, board = self._dungeon(sling=True, bare=True)
        # DECLARED CONSTRUCTED: the sling board without its carried bolts or
        # remains, so the decision below is not their disposal.
        board = replace(board, inventory=type(board.inventory)(
            item for item in board.inventory if item.tval != 18))
        policy.choose_key(board)
        self.assertNotIn(BOLT_PILE, policy._known_loot)
        policy._loot_target = None
        policy._loot_step(board)
        self.assertNotEqual(policy._loot_target, BOLT_PILE)
        policy._loot_target = None
        policy._loot_step(board, include_unsafe=True)
        self.assertNotEqual(policy._loot_target, BOLT_PILE)
        underfoot = replace(board, grids={
            **board.grids,
            board.player.position: replace(board.grids[BOLT_PILE],
                                           position=board.player.position)})
        policy._position_changed = True
        self.assertIsNone(policy._current_floor_item_key(
            underfoot, pickup_reason="pickup", trigger_reason="trigger-autodestroy"))

    # --- Home-full relief (review M2) ----------------------------------

    def _relief(self, *added):
        policy, board = self._home(*added)
        self.assertTrue(policy._home_is_full(board))
        policy._home_full_relief_key(board)
        return policy, board, policy._home_full_relief

    def test_full_home_destroys_a_cursed_armour_before_any_sale(self):
        policy, _board, relief = self._relief(replace(CURSED_ARMOUR, slot="home"))
        self.assertEqual(relief["mode"], "destroy")
        self.assertEqual(relief["sale"][0], policy._item_signature(CURSED_ARMOUR))
        self.assertEqual(policy._home_errand.request.purpose, "full-home-discard")

    def test_full_home_destroys_an_unusable_book_before_any_sale(self):
        policy, _board, relief = self._relief(BOOKS[0])
        self.assertEqual(relief["mode"], "destroy")
        self.assertEqual(relief["sale"][0], policy._item_signature(BOOKS[0]))

    def test_control_full_home_never_discards_a_third_book(self):
        policy, board, relief = self._relief(BOOKS[2])
        self.assertNotEqual((relief.get("mode"), (relief.get("sale") or (None,))[0]),
                            ("destroy", policy._item_signature(BOOKS[2])))
        # Before any relief decision (no pending sale of the book yet), the
        # third book is no discard candidate even with every store refusing it.
        policy, board = self._home(BOOKS[2])
        policy._store_sale_refused.update(range(7))
        self.assertIsNone(policy._home_full_discard_candidate(
            board, replace(BOOKS[2], slot="home")))
        self.assertIsNotNone(policy._home_full_discard_candidate(
            board, replace(BOOKS[0], slot="home")))

    def test_full_home_ranks_every_junk_class_as_auto_destroy(self):
        policy, board = self._home()
        # DECLARED CONSTRUCTED: a zero-value cursed gauntlet and Salt Water.
        gauntlet = _gear("home", "ガントレット [2,-2] {呪われている}", 31, 2,
                         is_cursed=True, ac=2, to_a=-2)
        salt = replace(SALT_WATER, slot="home")
        ranks = {item.name: policy._home_full_discard_rank(board, item)
                 for item in (gauntlet, salt)}
        self.assertEqual([rank[:2] for rank in ranks.values()], [(False, 0), (False, 0)])
        self.assertLess(ranks[gauntlet.name], ranks[salt.name])

    # --- town overflow and the exchange selector -----------------------

    def test_overflow_cursed_first_skips_a_cursed_artifact(self):
        policy, board = self._dungeon(CURSED_ARTIFACT, CURSED_ARMOUR)
        self.assertEqual(policy._overflow_disposal_item(board).slot, "r")

    def test_exchange_never_offers_a_third_book(self):
        policy, board = self._dungeon(bare=True)
        # DECLARED CONSTRUCTED: a pack holding only a third realm book.
        board = replace(board, inventory=type(board.inventory)(
            (replace(BOOKS[2], slot="a"),)))
        self.assertIsNone(policy._cheapest_exchange_item(board))


if __name__ == "__main__":
    unittest.main()
