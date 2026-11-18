"""A remembered item keeps what was remembered of it across an inscription or a discount.

Owner 2026-11-18 (maintainability review all-1118, Q1 「印や割引だけ違えば同じ品」): in every
scene, an item whose own inscription or discount display changed is the same item, and what
the bot remembered of it (unsellable, refused by the Home, unidentifiable, ...) carries over.
``item_identity.memory_identity`` is the reading; the remembered states hold it through
``MemorySignatures`` / ``MemorySignatureMap`` / ``MemorySignatureList``.

The game composes the closing block (C:/hengband/src flavor/flavor-describer.cpp
describe_inscription) as feeling, discount, ability abbreviation, player inscription.
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import copy
import pickle
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from hengbot import item_identity, item_use_route, json_snapshot
from hengbot.item_identity import (
    MemorySignatureList, MemorySignatureMap, MemorySignatures, memory_name, remembered_stack,
    same_memory,
)
from hengbot.model import InventoryItem
from hengbot.policy import HengbotPolicy
from hengbot.town_visit import town_visit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from item_identity_lint import analyze_remembered, main as lint_main  # noqa: E402


SWORD = InventoryItem(slot="a", name="ロング・ソード (2d5) (+0,+0)", count=1, tval=23, sval=17,
                      aware=True, known=True, is_equipment=True, weight=130)


def _inscribed(item, inscription):
    return replace(item, name=f"{item.name} {{{inscription}}}", inscription=inscription)


class MemoryNameTest(unittest.TestCase):
    def test_player_inscription_and_discount_are_dropped(self):
        cases = {
            "鉄の矢 (99)": "鉄の矢 (99)",
            "鉄の矢 (99) {@1}": "鉄の矢 (99)",
            "鉄の矢 (99) {50%引き}": "鉄の矢 (99)",
            "テレポートの巻物 {.}": "テレポートの巻物",
            "セスタス [5] {Q34}": "セスタス [5]",
            "耐性の薬 {75%引き}": "耐性の薬",
            "Arrow~ (1d4) (+3,+2) {25% off}": "Arrow~ (1d4) (+3,+2)",
            "ロング・ソード (2d5) (+3,+4) {HEAVY_CURSE}": "ロング・ソード (2d5) (+3,+4)",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(memory_name(name), expected)

    def test_feeling_is_kept_alone(self):
        self.assertEqual(memory_name("真鍮のランタン (7500 turns) {並, Q34}"),
                         "真鍮のランタン (7500 turns) {並}")
        self.assertEqual(memory_name("Arrow~ (1d4) (+3,+2) {average, @f1}"),
                         "Arrow~ (1d4) (+3,+2) {average}")
        self.assertEqual(memory_name("ショート・ボウ (x2) {呪われている, 20%引き}"),
                         "ショート・ボウ (x2) {呪われている}")
        # A feeling is the game's verdict on the item: {並} and {高級品} stay different.
        self.assertNotEqual(memory_name("セスタス [5] {並}"), memory_name("セスタス [5] {高級品}"))

    def test_names_without_a_closing_block_are_themselves(self):
        for name in ("", "unclosed {name", "nested {a{b}}", "鉄の矢 (1d4) (+5,+3) (65/shot 94/turn)"):
            self.assertEqual(memory_name(name), name)

    def test_same_memory(self):
        self.assertTrue(same_memory(("耐性の薬 {50%引き}", 75, 3), ("耐性の薬 {75%引き}", 75, 3)))
        self.assertFalse(same_memory(("耐性の薬", 75, 3), ("耐性の薬", 75, 4)))
        self.assertFalse(same_memory(None, ("耐性の薬", 75, 3)))
        self.assertTrue(same_memory(None, None))


class RememberedStateSurvivesTest(unittest.TestCase):
    def test_unsellable_item_stays_unsellable_after_the_sale_tag(self):
        policy = HengbotPolicy()
        self.assertTrue(item_use_route.has_buyer(policy, SWORD))
        policy._unsellable_items.add(policy._item_signature(SWORD))
        self.assertFalse(item_use_route.has_buyer(policy, _inscribed(SWORD, "@1")))
        self.assertFalse(item_use_route.has_buyer(policy, SWORD))

    def test_home_rejected_deposit_stays_rejected_after_a_discount_merge(self):
        policy = HengbotPolicy()
        potion = InventoryItem(slot="b", name="耐性の薬 {50%引き}", count=1, tval=75, sval=3,
                               aware=True, known=True)
        policy._home_rejected_deposits.add(policy._item_signature(potion))
        # The take merged into the carried stack; ItemEntity::absorb keeps the larger discount.
        merged = replace(potion, name="耐性の薬 {75%引き}", count=14)
        self.assertIn(policy._item_signature(merged), policy._home_rejected_deposits)

    def test_unidentifiable_and_deferred_survive_an_inscription(self):
        policy = HengbotPolicy()
        sword = replace(SWORD, known=False, name="ロング・ソード (2d5)")
        policy._unidentifiable_sigs.add(policy._item_signature(sword))
        policy._deferred_home_items.add(policy._item_signature(sword))
        tagged = _inscribed(sword, ".")
        self.assertIn(policy._item_signature(tagged), policy._unidentifiable_sigs)
        self.assertIn(policy._item_signature(tagged), policy._deferred_home_items)

    def test_pending_take_is_found_after_a_discount_merge(self):
        policy = HengbotPolicy()
        policy._home_pending_item = ("耐性の薬 {50%引き}", 75, 3)
        merged = InventoryItem(slot="c", name="耐性の薬 {75%引き}", count=14, tval=75, sval=3,
                               aware=True, known=True)
        snapshot = SimpleNamespace(inventory=[SWORD, merged])
        self.assertIs(policy._pending_inventory_item(snapshot), merged)


class RememberedStackTest(unittest.TestCase):
    def test_exact_stack_first_then_the_same_item(self):
        tagged = SimpleNamespace(name="クロスボウの矢 (99) {@1}", tval=18, sval=1)
        plain = SimpleNamespace(name="クロスボウの矢 (99)", tval=18, sval=1)
        other = SimpleNamespace(name="クロスボウの矢 (99)", tval=18, sval=1)
        stacks = [tagged, plain, other]
        self.assertIs(remembered_stack(stacks, ("クロスボウの矢 (99)", 18, 1)), plain)
        self.assertIs(remembered_stack(stacks, ("クロスボウの矢 (99) {@1}", 18, 1)), tagged)
        self.assertIs(remembered_stack(stacks, ("クロスボウの矢 (99) {20%引き}", 18, 1)), tagged)
        self.assertIsNone(remembered_stack(stacks, ("クロスボウの矢 (99)", 18, 2)))
        self.assertIsNone(remembered_stack(stacks, None))

    def test_queue_answers_by_memory_and_removes_the_exact_entry_first(self):
        queue = MemorySignatureList([("矢 {@1}", 18, 1), ("矢", 18, 1)])
        self.assertIn(("矢 {30%引き}", 18, 1), queue)
        queue.remove(("矢", 18, 1))
        self.assertEqual(list(queue), [("矢 {@1}", 18, 1)])
        queue.remove(("矢", 18, 1))
        self.assertEqual(list(queue), [])

    def test_map_keys_by_memory(self):
        quantities = MemorySignatureMap({("矢 {@1}", 18, 1): 5})
        self.assertEqual(quantities.get(("矢", 18, 1)), 5)
        self.assertEqual(quantities.pop(("矢 {10%引き}", 18, 1)), 5)
        self.assertFalse(quantities)

    def test_set_algebra_reads_by_memory(self):
        remembered = MemorySignatures([("矢 {@1}", 18, 1)])
        self.assertTrue(remembered.issubset({("矢", 18, 1)}))
        self.assertEqual(remembered - {("矢 {.}", 18, 1)}, set())
        remembered.difference_update([("矢", 18, 1)])
        self.assertFalse(remembered)


class OldCheckpointTest(unittest.TestCase):
    def test_plain_sets_of_old_signatures_are_read_by_memory(self):
        policy = HengbotPolicy()
        state = policy.__dict__
        state["_home_rejected_deposits"] = {("耐性の薬 {50%引き}", 75, 3)}
        state["_home_pending_batch"] = [("矢 {@1}", 18, 1)]
        visit = town_visit(policy)
        visit.__dict__["unsellable_items"] = {("ロング・ソード (2d5) (+0,+0) {@1}", 23, 17)}
        restored = pickle.loads(pickle.dumps(policy))
        self.assertIsInstance(restored._home_rejected_deposits, MemorySignatures)
        self.assertIn(("耐性の薬", 75, 3), restored._home_rejected_deposits)
        self.assertIsInstance(restored._home_pending_batch, MemorySignatureList)
        self.assertIn(("矢", 18, 1), restored._home_pending_batch)
        self.assertIsInstance(restored._unsellable_items, MemorySignatures)
        self.assertFalse(item_use_route.has_buyer(restored, SWORD))

    def test_remembering_containers_survive_copies_and_the_json_snapshot(self):
        policy = HengbotPolicy()
        policy._unsellable_items.add(("鉄の矢 (99) {@1}", 17, 1))
        policy._home_pending_quantities[("鉄の矢 (99)", 17, 1)] = 3
        for restored in (copy.deepcopy(policy), json_snapshot.loads(json_snapshot.dumps(policy))):
            with self.subTest(kind=type(restored).__name__):
                self.assertIsInstance(restored._unsellable_items, MemorySignatures)
                self.assertIn(("鉄の矢 (99) {50%引き}", 17, 1), restored._unsellable_items)
                self.assertIsInstance(restored._home_pending_quantities, MemorySignatureMap)
                self.assertEqual(restored._home_pending_quantities.get(("鉄の矢 (99) {@1}", 17, 1)), 3)

    def test_a_plain_set_assigned_by_name_is_read_by_memory(self):
        policy = HengbotPolicy()
        policy._deferred_home_items = {("矢 {@1}", 18, 1)}
        self.assertIsInstance(policy._deferred_home_items, MemorySignatures)
        self.assertIn(("矢", 18, 1), policy._deferred_home_items)


class RememberedLintTest(unittest.TestCase):
    def test_rejects_display_comparisons_of_remembered_items(self):
        source = (
            "def f(self, signature, plain):\n"
            "    a = self._home_pending_item == signature\n"
            "    b = self._identification_candidate in plain\n"
            "    c = plain.issubset(self._deferred_home_items)\n"
            "    d = plain - self._unsellable_items\n"
            "    self._home_rejected_deposits = set()\n"
        )
        findings = analyze_remembered(source)
        self.assertEqual(len(findings), 5, findings)

    def test_accepts_the_memory_reading(self):
        source = (
            "def f(self, signature, plain):\n"
            "    a = same_memory(self._home_pending_item, signature)\n"
            "    b = self._identification_candidate in self._deferred_home_items\n"
            "    held = MemorySignatures(plain)\n"
            "    c = self._home_pending_item in held\n"
            "    self._home_rejected_deposits = MemorySignatures()\n"
            "    e = signature in self._unsellable_items\n"
        )
        self.assertEqual(analyze_remembered(source), [])

    def test_tree_is_clean(self):
        self.assertEqual(lint_main(), 0)


if __name__ == "__main__":
    unittest.main()
