"""The optimizer compares the light radius of the whole loadout (#101, 6th of the light type).

USER DECISION 2026-10-23 「合計で比べる」: the light radius is the total of
every worn item, as update_lite_radius() (src/specific-object/torch.cpp)
adds ItemEntity::get_lite_radius() (src/system/item/item-entity.cpp).  The
recorded case (tests/test_light_total_radius_recorded.py): a worn 闇の陣笠
(TR_LITE_M1) turned the lamp's radius 2 into 1.

equipment_optimizer.worn_light_radius is the one rule; every comparison
site reads it.  The structural tests below replace the rule and require each
site to follow the replacement: a site that computed a radius of its own
would not follow it and fails.

DECLARED CONSTRUCTED: every item below (helmets of tval 32 sval 4 = 陣笠,
the フェアノールのランプ tval 39 sval 2) and every metric.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import unittest
from unittest.mock import patch

from hengbot import equipment_optimizer, warrior_loadout_search
from hengbot.equipment_optimizer import (
    SLOT_HEAD,
    SLOT_LIGHT,
    EvaluatedLoadout,
    Loadout,
    LoadoutMetrics,
    OwnedEquipment,
    loadout_light_radius,
    worn_light_radius,
)
from hengbot.model import StoreItem


TR_LITE_1, TR_LITE_2, TR_LITE_3 = 77, 122, 123
TR_LITE_M1, TR_LITE_M2 = 124, 125
TR_DARK_SOURCE = 146
TR_RES_DARK = 55


def _owned(tval, sval, flags, *, item_id, to_a=0, ac=0, origin="home"):
    return OwnedEquipment(
        id=item_id,
        item=StoreItem(
            letter="a", name=item_id, count=1, tval=tval, sval=sval,
            price=0, fully_known=True, known_flags=frozenset(flags),
            ac=ac, to_a=to_a,
        ),
        origin=origin,
        equipped_slot=None,
    )


LAMP = _owned(39, 2, [TR_LITE_2], item_id="equipped:lamp", origin="equipped")
DARK_HELM = _owned(
    32, 4, [TR_RES_DARK, TR_LITE_M1], item_id="equipped:dark", ac=4, to_a=6,
    origin="equipped",
)
PLAIN_HELM = _owned(32, 4, [TR_RES_DARK], item_id="home:plain", ac=4, to_a=6)
METRICS = LoadoutMetrics(expected_dps=10.0, survival_turns=5.0, combat_margin=0.5)


def _worn(*items):
    slots = tuple(
        (SLOT_LIGHT if item.item.tval == 39 else SLOT_HEAD, item)
        for item in items
    )
    return Loadout(slots, "empty")


class WornLightRadiusRuleTest(unittest.TestCase):
    def test_total_is_the_game_sum_over_the_worn_items(self):
        # The recorded loadout: lamp LITE_2 and 闇の陣笠 LITE_M1 -> 1.
        self.assertEqual(worn_light_radius((LAMP, DARK_HELM)), 1)
        self.assertEqual(loadout_light_radius(_worn(LAMP, DARK_HELM)), 1)
        self.assertEqual(loadout_light_radius(_worn(LAMP, PLAIN_HELM)), 2)
        self.assertEqual(worn_light_radius((LAMP, None)), 2)
        # A torch (old token LITE = TR_LITE_1) and a lantern (LITE_2) count as
        # burning: fuel is not a selection input.
        torch = _owned(39, 0, [TR_LITE_1], item_id="t")
        lantern = _owned(39, 1, [TR_LITE_2], item_id="l")
        self.assertEqual(worn_light_radius((torch,)), 1)
        self.assertEqual(worn_light_radius((lantern, DARK_HELM)), 1)
        # TR_DARK_SOURCE cancels the item's own LITE flags, not its darkness.
        dark_source = _owned(
            32, 4, [TR_LITE_3, TR_LITE_M2, TR_DARK_SOURCE], item_id="d"
        )
        self.assertEqual(worn_light_radius((LAMP, dark_source)), 0)
        # An item's unknown flags are not guessed.
        unknown = _owned(32, 4, [], item_id="u")
        self.assertEqual(worn_light_radius((LAMP, unknown)), 2)

    def test_the_permanent_light_term_is_the_86_term(self):
        with patch.object(
            equipment_optimizer, "permanent_light_radius", lambda _item: 0
        ):
            self.assertEqual(worn_light_radius((LAMP, DARK_HELM)), -1)


def _patched_total(values):
    """A replacement rule: the radius of a loadout by its head item id."""
    def total(loadout):
        head = loadout.item_at(SLOT_HEAD)
        return values[head.id if head is not None else None]
    return total


class SitesReadTheRuleTest(unittest.TestCase):
    """Each comparison site follows a replaced rule (structural check)."""

    def test_pairwise_preference_takes_the_larger_total(self):
        current = frozenset({LAMP.id, DARK_HELM.id})
        dark = EvaluatedLoadout(_worn(LAMP, DARK_HELM), METRICS)
        plain = EvaluatedLoadout(_worn(LAMP, PLAIN_HELM), METRICS)
        # d2304637: equal light rank and lamp radius; the current set won.
        self.assertTrue(equipment_optimizer._prefer(plain, dark, current))
        self.assertFalse(equipment_optimizer._prefer(dark, plain, current))
        with patch.object(
            equipment_optimizer, "loadout_light_radius",
            _patched_total({DARK_HELM.id: 3, PLAIN_HELM.id: 0}),
        ):
            self.assertTrue(equipment_optimizer._prefer(dark, plain, current))
            self.assertFalse(equipment_optimizer._prefer(plain, dark, current))

    def test_field_selection_takes_the_larger_total(self):
        current = frozenset({LAMP.id, DARK_HELM.id})
        field = [
            EvaluatedLoadout(_worn(LAMP, DARK_HELM), METRICS),
            EvaluatedLoadout(_worn(LAMP, PLAIN_HELM), METRICS),
        ]
        best = equipment_optimizer._stable_operational_best(field, current)
        # d2304637: the current set (闇の陣笠).
        self.assertEqual(best.loadout.item_at(SLOT_HEAD).id, PLAIN_HELM.id)
        with patch.object(
            equipment_optimizer, "loadout_light_radius",
            _patched_total({DARK_HELM.id: 3, PLAIN_HELM.id: 0}),
        ):
            best = equipment_optimizer._stable_operational_best(field, current)
        self.assertEqual(best.loadout.item_at(SLOT_HEAD).id, DARK_HELM.id)

    def test_state_compression_keeps_the_larger_total(self):
        def kept(current_id):
            states, _truncated = warrior_loadout_search._compress_states(
                [_worn(LAMP, DARK_HELM), _worn(LAMP, PLAIN_HELM)],
                processed_slots=(SLOT_LIGHT, SLOT_HEAD),
                current_by_slot={SLOT_LIGHT: LAMP.id, SLOT_HEAD: current_id},
                current_item_ids=frozenset({LAMP.id, current_id}),
            )
            return {
                state.item_at(SLOT_HEAD).id for state in states
            }

        # d2304637: one gear key for both; only the current 闇の陣笠 was kept.
        self.assertIn(PLAIN_HELM.id, kept(DARK_HELM.id))
        # Neither current: the darker state is dominated and dropped.
        self.assertEqual(kept("equipped:other"), {PLAIN_HELM.id})
        with patch.object(
            warrior_loadout_search, "loadout_light_radius",
            _patched_total({DARK_HELM.id: 3, PLAIN_HELM.id: 0}),
        ):
            self.assertEqual(kept("equipped:other"), {DARK_HELM.id})

    def test_copies_are_split_by_the_total(self):
        def kept(protected):
            return {
                item.id
                for item in warrior_loadout_search._deduplicate_slot_copies(
                    (DARK_HELM, PLAIN_HELM), protected, {}
                )
            }

        # d2304637: one signature; the current 闇の陣笠 was the only copy kept.
        self.assertEqual(kept(frozenset({DARK_HELM.id})), {DARK_HELM.id, PLAIN_HELM.id})
        with patch.object(
            warrior_loadout_search, "worn_light_radius", lambda _items: 0
        ):
            self.assertEqual(kept(frozenset({DARK_HELM.id})), {DARK_HELM.id})

    def test_catalog_prune_does_not_let_darkness_prune_light(self):
        # A better-enchanted 闇の陣笠 no longer prunes the plain-light copy.
        better_dark = _owned(
            32, 4, [TR_RES_DARK, TR_LITE_M1], item_id="home:dark7", ac=4,
            to_a=7,
        )
        kept = {
            item.id
            for item in warrior_loadout_search._prune_dominated_catalog(
                (better_dark, PLAIN_HELM)
            )
        }
        # d2304637: {home:dark7} (AC 11 >= 10 with the same flags).
        self.assertEqual(kept, {better_dark.id, PLAIN_HELM.id})
        with patch.object(
            warrior_loadout_search, "worn_light_radius", lambda _items: 0
        ):
            kept = {
                item.id
                for item in warrior_loadout_search._prune_dominated_catalog(
                    (better_dark, PLAIN_HELM)
                )
            }
        self.assertEqual(kept, {better_dark.id})


if __name__ == "__main__":
    unittest.main()
