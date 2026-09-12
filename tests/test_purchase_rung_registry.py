"""Declared seam inventory for the shared purchase authority and provenance."""

import ast
import inspect
import textwrap
import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.model import (
    SV_LITE_TORCH, SV_POTION_RESTORE_STR, SV_SCROLL_IDENTIFY,
    SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_IDENTIFY, TVAL_LITE, TVAL_POTION,
    TVAL_SCROLL,
)
from hengbot.purchase_rungs import PurchaseContext, PurchaseRung, PurchaseSelection
from hengbot.policy import HengbotPolicy
from policy_fixtures import item
from tests.test_destroy_procurement_guard import active_detection_fixture


def assert_no_raw_store_iteration(source: str) -> None:
    """Reject selector adapters which bypass the shared-rung provenance wall."""
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            continue
        for generator in node.generators:
            iterator = generator.iter
            if isinstance(iterator, ast.Attribute) and iterator.attr == "items":
                raise AssertionError("raw store.items selection bypasses shared matcher")


def assert_all_rungs_have_examples(rungs, example_ids) -> None:
    missing = {rung.rung_id for rung in rungs} - set(example_ids)
    if missing:
        raise AssertionError(f"purchase rungs lack active/inactive examples: {sorted(missing)}")


class PurchaseRungRegistryTest(unittest.TestCase):
    def test_p2_authority_ids_are_unique_and_matches_are_typed(self):
        """SEAM: enumerates authority; public selection exposes only its winner."""
        policy, snapshot, protected = active_detection_fixture()
        context = PurchaseContext(snapshot)
        rungs = policy._purchase_rungs(context)
        self.assertEqual(len({rung.rung_id for rung in rungs}), len(rungs))
        matches = [rung.match(context, protected) for rung in rungs]
        self.assertTrue(any(match is not None for match in matches))
        match = next(match for match in matches if match is not None)
        selection = PurchaseSelection(match, protected, 6, context, 1)
        self.assertEqual(selection.match.rung_id, "mining:treasure-detection")

    def test_inactive_item_has_no_procurement_protection(self):
        policy, snapshot, protected = active_detection_fixture()
        policy._fundraising_mode = None
        self.assertFalse(policy._item_matches_purchase_rung(snapshot, protected))

    def test_p2_previously_omitted_rungs_use_shared_matcher(self):
        """SEAM examples cover throwing torches, both Identify tiers, restore, and Remove Curse."""
        policy, snapshot, _ = active_detection_fixture()
        cases = []

        torch = item("t", TVAL_LITE, SV_LITE_TORCH, name="Torch")
        cases.append((policy, snapshot, torch, "tail:torch"))

        normal = HengbotPolicy()
        normal._identification_need = "normal"
        cases.append((normal, snapshot, item("i", TVAL_SCROLL, SV_SCROLL_IDENTIFY), "identify:normal"))

        full = HengbotPolicy()
        full._identification_need = "full"
        cases.append((full, snapshot, item("j", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY), "identify:full"))

        restore = HengbotPolicy()
        drained = replace(snapshot, player=replace(snapshot.player, drained_stats=("str",)))
        cases.append((restore, drained, item("p", TVAL_POTION, SV_POTION_RESTORE_STR), "restore:str"))

        curse = HengbotPolicy()
        cases.append((curse, snapshot, item("c", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE), "curse:normal"))

        for current, current_snapshot, candidate, expected in cases:
            with self.subTest(rung=expected), patch.object(
                current, "_has_normal_remove_curse_target",
                return_value=(expected == "curse:normal"),
            ):
                matches = current._matching_live_purchase_rungs(current_snapshot, candidate)
                self.assertIn(expected, {match.rung_id for match in matches})

    def test_p2_ast_negative_raw_selector_proves_failure(self):
        source = inspect.getsource(HengbotPolicy._next_purchase_unreserved)
        assert_no_raw_store_iteration(source)
        bypass = textwrap.dedent(source) + "\nif False:\n    next(i for i in snapshot.store.items)\n"
        with self.assertRaisesRegex(AssertionError, "raw store.items"):
            assert_no_raw_store_iteration(bypass)

    def test_p2_missing_example_negative_proves_failure(self):
        policy, snapshot, _ = active_detection_fixture()
        rungs = policy._purchase_rungs(PurchaseContext(snapshot))
        examples = {rung.rung_id for rung in rungs}
        assert_all_rungs_have_examples(rungs, examples)
        unregistered = PurchaseRung("fixture:skips-registration", "fixture", lambda c, i: None)
        with self.assertRaisesRegex(AssertionError, "fixture:skips-registration"):
            assert_all_rungs_have_examples((*rungs, unregistered), examples)


if __name__ == "__main__":
    unittest.main()
