"""Census annotations must not install operational producers or bypass sinks."""
import tests  # noqa: F401 -- isolate runtime paths

import ast
import unittest

from hengbot.claim_register import CLAIM_OWNER_ATTRIBUTE, ClaimOwner, claims
from hengbot.magic_eater import ABSORB_REASON
from hengbot.town_arbiter import _new_town_turn_arbiter
import item_sink_lint
import ownership_claim_lint


class CensusOwnerDeclarationTest(unittest.TestCase):
    def test_declaration_continuations_keep_their_budget_owner(self):
        arbiter = _new_town_turn_arbiter()
        for reason, owner in (
            (ABSORB_REASON, "quest-request"),
            ("shop:opening-route-page", "shop-buy"),
            ("opening-q1:equip-light", "equipment-txn"),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(arbiter.owner_for_reason(reason), owner)
                self.assertEqual(arbiter.ownership_family(reason), owner)

    def test_census_annotation_preserves_callable_and_operational_marker(self):
        def dispatcher():
            return "selected-child"

        marked = claims(ClaimOwner.COMBAT, census_only=True)(dispatcher)
        self.assertIs(marked, dispatcher)
        self.assertEqual(marked(), "selected-child")
        self.assertFalse(hasattr(marked, CLAIM_OWNER_ATTRIBUTE))
        self.assertIs(marked.__hengbot_census_owner__, ClaimOwner.COMBAT)
        self.assertIs(claims(ClaimOwner.COMBAT)(dispatcher), dispatcher)
        self.assertIs(getattr(dispatcher, CLAIM_OWNER_ATTRIBUTE), ClaimOwner.COMBAT)

    def test_census_annotation_is_covered_without_creating_a_direct_call_sink(self):
        source = '''
@claims(ClaimOwner.QUEST_REQUEST, census_only=True)
def dispatcher(self):
    self.last_reason = "quest:blocked:opening-route"
'''
        tree = ast.parse(source)
        self.assertEqual(ownership_claim_lint._decorator_owner(tree.body[0]), "quest-request")
        self.assertEqual(item_sink_lint._producers(tree), set())

    def test_census_dispatcher_cannot_bypass_child_entry_or_raw_item_verdict(self):
        source = '''
@claims(ClaimOwner.SHOP_SELL)
def child(self, snapshot):
    return None
@claims(ClaimOwner.QUEST_REQUEST, census_only=True)
def dispatcher(self, snapshot):
    return self.child(snapshot)
'''
        self.assertTrue(any("outside its entry/adapter" in finding
                            for finding in item_sink_lint.analyze_source(source)))
        raw = '''
@claims(ClaimOwner.QUEST_REQUEST, census_only=True)
def dispatcher(self, item):
    return "q" + item.slot
'''
        self.assertTrue(any("raw item command" in finding
                            for finding in item_sink_lint.analyze_source(raw)))
