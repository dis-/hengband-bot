"""Pin each named item-identity reading to the copy it replaced (review S1 (a)-1).

The ``_old_*`` functions are verbatim copies of the pre-refactor bodies
(policy._item_signature, policy_shop._sale_item_identity / _sale_signature_identity
and the regex copies at policy_shop ~4503, store_sale._named_definition,
town_terminal.home_full_identification_target, quest_navigator._unidentified_identity,
policy_instore.shelf_item_name, lamp_fuel._lantern_identity,
equipment_optimizer._without_player_inscription, equipment_mutation.stable_identity).
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from hengbot import equipment_mutation, equipment_optimizer, item_identity, lamp_fuel
from hengbot import policy_instore, quest_navigator
from hengbot.policy import HengbotPolicy
from hengbot.policy_shop import ShopMixin


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from item_identity_lint import analyze_source, main as lint_main  # noqa: E402


NAMES = (
    "",
    "鉄の矢 (99)",
    "鉄の矢 (99) {@1}",
    "鉄の矢 (99) {50%引き}",
    "鉄の矢 (99) {50%引き, @1}",
    "鉄の矢 (1d4) (+5,+3) (65/shot 94/turn)",
    "鉄の矢 (1d4) (+5,+3) (65/shot 94/turn) {@f1}",
    "ショート・ボウ (x2) {並}",
    "ショート・ボウ (x2) {並} {@1}",
    "ショート・ボウ (x2) {並}{@1}",
    "真鍮のランタン (7500 turns) {並, Q34}",
    "真鍮のランタン (7500 turns) {高級品, Q34}",
    "セスタス [5] {Q34}",
    "セスタス [5]{並}",
    "セスタス {並} [5]",
    "テレポートの巻物 {.}",
    "テレポートの巻物 {.}  ",
    "Arrow~ (1d4) (+3,+2) {average, @f1}",
    "a { b } c {d}",
    "unclosed {name",
    "nested {a{b}}",
)
INSCRIPTIONS = ("", "@1", "@f1", "Q34", ".", "@1#note", "%", "50%引き", "並")


def _old_item_signature(item):
    return (item.name, item.tval, item.sval)


def _old_sale_item_identity(item):
    name = re.sub(r"\s+\{[^{}]*\}\s*$", "", item.name)
    return (name, item.tval, item.sval)


def _old_sale_signature_identity(signature):
    return (re.sub(r"\s+\{[^{}]*\}\s*$", "", signature[0]), signature[1], signature[2])


def _old_named_definition_name(item):
    return re.sub(r"\s+\{[^{}]*\}\s*$", "", item.name)


def _old_town_terminal_identity(sale_signature):
    name, tval, sval = sale_signature
    return (re.sub(r"\s+\{[^{}]*\}\s*$", "", name), tval, sval)


def _old_unidentified_identity(item):
    return (item.tval, item.sval, re.sub(r"(\s*\{[^{}]*\})+\s*$", "", item.name))


def _old_shelf_item_name(name):
    return re.compile(r"\s*\{[^{}]*\}").sub("", name).strip()


def _old_lantern_identity(lantern):
    return re.compile(r"\s*\{[^{}]*\}\s*$").sub("", lantern.name)


def _old_without_player_inscription(name, inscription):
    shown = inscription.split("#", 1)[0]
    head, separator, block = name.rpartition(" {")
    if not shown or "%" in inscription or not separator or not block.endswith("}"):
        return name
    inner = block[:-1]
    if inner == shown:
        return head
    if inner.endswith(", " + shown):
        return f"{head} {{{inner[:-len(shown) - 2]}}}"
    return name


def _old_stable_identity(item):
    if item is None:
        return None
    aware = getattr(item, "aware", True)
    known = getattr(item, "known", True)
    return (
        getattr(item, "tval", None),
        getattr(item, "weight", None),
        getattr(item, "sval", None) if aware else None,
        (
            bool(getattr(item, "is_ego", False)),
            bool(getattr(item, "is_artifact", False)),
        ) if known else None,
    )


def _items():
    return [SimpleNamespace(name=name, tval=17, sval=1) for name in NAMES]


class ItemIdentityReadingsTest(unittest.TestCase):
    def test_display_signature_is_the_name_as_is(self):
        for item in _items():
            with self.subTest(name=item.name):
                self.assertEqual(item_identity.display_signature(item), _old_item_signature(item))
                self.assertEqual(HengbotPolicy._item_signature(item), _old_item_signature(item))

    def test_kind_is_tval_and_sval(self):
        for item in _items():
            self.assertEqual(item_identity.kind(item), (item.tval, item.sval))

    def test_sale_identity_drops_one_trailing_block(self):
        for item in _items():
            with self.subTest(name=item.name):
                expected = _old_sale_item_identity(item)
                self.assertEqual(item_identity.sale_identity(item), expected)
                self.assertEqual(ShopMixin._sale_item_identity(item), expected)
                signature = _old_item_signature(item)
                self.assertEqual(item_identity.sale_identity_of_signature(signature),
                                 _old_sale_signature_identity(signature))
                self.assertEqual(ShopMixin._sale_signature_identity(signature),
                                 _old_sale_signature_identity(signature))
                self.assertEqual(item_identity.sale_identity_of_signature(signature),
                                 _old_town_terminal_identity(signature))
                self.assertEqual(item_identity.without_trailing_block(item.name),
                                 _old_named_definition_name(item))

    def test_unidentified_identity_drops_every_trailing_block(self):
        for item in _items():
            with self.subTest(name=item.name):
                expected = _old_unidentified_identity(item)
                self.assertEqual(item_identity.unidentified_identity(item), expected)
                self.assertEqual(quest_navigator._unidentified_identity(item), expected)

    def test_shelf_name_drops_every_block(self):
        for name in NAMES:
            with self.subTest(name=name):
                self.assertEqual(item_identity.without_any_block(name), _old_shelf_item_name(name))
                self.assertEqual(policy_instore.shelf_item_name(name), _old_shelf_item_name(name))
        for item in _items():
            self.assertEqual(item_identity.shelf_identity(item),
                             (_old_shelf_item_name(item.name), item.tval, item.sval))

    def test_lantern_name_drops_one_trailing_block_loosely(self):
        for item in _items():
            with self.subTest(name=item.name):
                self.assertEqual(item_identity.without_trailing_block_loose(item.name),
                                 _old_lantern_identity(item))
                self.assertEqual(lamp_fuel._lantern_identity(item), _old_lantern_identity(item))

    def test_without_player_inscription(self):
        for name in NAMES:
            for inscription in INSCRIPTIONS:
                with self.subTest(name=name, inscription=inscription):
                    expected = _old_without_player_inscription(name, inscription)
                    self.assertEqual(item_identity.without_player_inscription(name, inscription),
                                     expected)
                    self.assertEqual(equipment_optimizer._without_player_inscription(
                        name, inscription), expected)

    def test_stable_identity(self):
        samples = [None, SimpleNamespace()]
        for aware in (True, False):
            for known in (True, False):
                for ego in (True, False, 0, None):
                    samples.append(SimpleNamespace(
                        tval=23, sval=4, weight=120, aware=aware, known=known,
                        is_ego=ego, is_artifact=not ego, name="x {@1}"))
        for item in samples:
            self.assertEqual(item_identity.stable_identity(item), _old_stable_identity(item))
            self.assertEqual(equipment_mutation.stable_identity(item), _old_stable_identity(item))

    def test_readings_differ_where_the_copies_differed(self):
        # The readings stay separate: one block, every trailing block, every block.
        name = "ショート・ボウ (x2) {並} {@1}"
        self.assertEqual(item_identity.without_trailing_block(name), "ショート・ボウ (x2) {並}")
        self.assertEqual(item_identity.without_trailing_blocks(name), "ショート・ボウ (x2)")
        self.assertEqual(item_identity.without_any_block("セスタス {並} [5]"), "セスタス [5]")
        self.assertEqual(item_identity.without_trailing_block("セスタス [5]{並}"), "セスタス [5]{並}")
        self.assertEqual(item_identity.without_trailing_block_loose("セスタス [5]{並}"), "セスタス [5]")


class ItemIdentityLintTest(unittest.TestCase):
    def test_repository_is_clean(self):
        self.assertEqual(lint_main(), 0)

    def test_brace_regex_and_hand_built_tuple_are_rejected(self):
        source = '''
import re
_BLOCK = re.compile(r"\\s*\\{[^{}]*\\}")
def strip(item):
    return re.sub(r"\\s+\\{[^{}]*\\}\\s*$", "", item.name)
def strip_compiled(name):
    return _BLOCK.sub("", name)
def split(name):
    return name.rpartition(" {")[0]
def signature(item):
    return (item.name, item.tval, item.sval)
def kind_first(item):
    return (item.tval, item.sval, item.name)
'''
        findings = analyze_source(source, "mutant.py")
        self.assertEqual(len(findings), 5, findings)

    def test_page_fingerprints_and_kinds_are_not_identities(self):
        source = '''
import re
_FIND = re.compile(r"\\{[^{}]*\\.[^{}]*\\}")
def page(store):
    return tuple((item.letter, item.name, item.tval, item.sval) for item in store.items)
def kind(item):
    return (item.tval, item.sval)
def repack(name, tval, sval):
    return (name, tval, sval)
def find(item):
    return _FIND.search(item.name)
'''
        self.assertEqual(analyze_source(source, "fine.py"), [])


if __name__ == "__main__":
    unittest.main()
