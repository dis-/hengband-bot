"""USER DECISION 2026-09-29 「空いた鎧の欄は必ず埋める」 for every armour slot.

The body slot rule (``require_body``) shipped first.  2026-10-02 the live
character had an empty FEET slot (state 17:01, turn 3962761: main_hand,
sub_hand, bow, two rings, neck, light, body, outer, head, arms; no feet).
These pins use that worn set.  Without an owned pair of boots selection is
unchanged; with boots in Home the selected loadout wears them even when the
evaluator scores the booted set equal, inside the 1% band, or clearly lower
(the fill rule is a hard requirement, not a tie-break); the body rule is
unchanged.  Both live search factories are exercised (the live 2026-10-02
catalogue is above the incremental threshold, so the single-slot search runs).
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

from dataclasses import replace
import unittest

from hengbot.equipment_optimizer import (
    SLOT_BODY,
    SLOT_FEET,
    Loadout,
    current_loadout,
    optimize_loadout,
    owned_armor_fill_slots,
)
from hengbot.equipment_transaction_planner import plan_equipment_transactions
from hengbot.warrior_loadout_search import (
    enumerate_single_slot_variants,
    enumerate_warrior_loadouts,
)
from tests.test_equipment_optimizer import gear, metrics


def stats(owned, **fields):
    return replace(owned, item=replace(owned.item, **fields))


def live_worn_set():
    """The 2026-10-02 17:01 worn set (tvals and printed [ac,+to_a]/(+h,+d)
    from the recorded equipment; flags omitted)."""
    return (
        stats(gear("equipped:avavir", 22, equipped_slot="main_hand"),
              to_h=8, to_d=8, to_a=10, damage_dice_num=5, damage_dice_sides=3),
        stats(gear("equipped:dragon-shield", 34, equipped_slot="sub_hand"),
              ac=8, to_a=10),
        stats(gear("equipped:light-xbow", 19, equipped_slot="bow"),
              to_h=7, to_d=9),
        stats(gear("equipped:ring-damage", 45, equipped_slot="main_ring"),
              to_d=9),
        stats(gear("equipped:ring-protection", 45, equipped_slot="sub_ring"),
              to_a=19),
        gear("equipped:amulet-elec", 40, equipped_slot="neck"),
        gear("equipped:feanor", 39, equipped_slot="light"),
        stats(gear("equipped:resist-body", 37, equipped_slot="body"),
              ac=17, to_a=11),
        stats(gear("equipped:aman-cloak", 35, equipped_slot="outer"),
              ac=1, to_a=4),
        stats(gear("equipped:esp-crown", 33, equipped_slot="head"), to_a=12),
        stats(gear("equipped:leather-gloves", 31, equipped_slot="arms"),
              ac=1, to_a=-1),
    )


def home_boots(ac=2, to_a=0):
    return stats(gear("home:boots", 30), ac=ac, to_a=to_a)


FACTORIES = (
    ("single-slot", enumerate_single_slot_variants),
    ("warrior", enumerate_warrior_loadouts),
)


def select(items, evaluate, factory, **kwargs):
    current = current_loadout(items)
    return optimize_loadout(
        items,
        evaluate,
        depth=1,
        current_item_ids=current.item_ids,
        candidate_loadouts=factory(
            items, current_item_ids=current.item_ids, require_light=True,
        ),
        **kwargs,
    )


class EmptyArmorSlotFillTest(unittest.TestCase):
    def test_live_set_without_boots_is_unchanged(self):
        items = live_worn_set()
        current = current_loadout(items)
        self.assertIsNone(current.item_at(SLOT_FEET))

        def evaluate(loadout):
            return metrics(100.0 + 0.1 * len(loadout.slots))

        for name, factory in FACTORIES:
            with self.subTest(factory=name):
                result = select(items, evaluate, factory)
                self.assertFalse(result.timed_out)
                self.assertEqual(result.best.loadout.item_ids, current.item_ids)
                self.assertIsNone(result.best.loadout.item_at(SLOT_FEET))

    def test_home_boots_are_worn_even_when_scored_equal_or_lower(self):
        for boots, booted_score, (name, factory) in (
            (boots, score, factory)
            # Plain [2,+0] boots, and [1,-1] boots whose AC nets to zero like
            # the live gloves (the full search used to compress them away).
            for boots in (home_boots(), home_boots(1, -1))
            for score in (100.0, 99.5, 90.0)
            for factory in FACTORIES
        ):
            items = (*live_worn_set(), boots)
            current = current_loadout(items)
            self.assertEqual(
                owned_armor_fill_slots(items),
                frozenset({"outer", "head", "arms", "feet"}),
            )

            def evaluate(loadout, booted_score=booted_score):
                if loadout.item_at(SLOT_FEET) is not None:
                    return metrics(booted_score)
                return metrics(100.0)

            with self.subTest(
                factory=name, booted_score=booted_score,
                boots=(boots.item.ac, boots.item.to_a),
            ):
                result = select(items, evaluate, factory)
                self.assertFalse(result.timed_out)
                self.assertIs(result.best.loadout.item_at(SLOT_FEET), boots)
                self.assertEqual(
                    result.best.loadout.item_ids,
                    current.item_ids | {boots.id},
                )
                actions = plan_equipment_transactions(
                    items, current, result.best.loadout,
                    current_pack_items=10, home_scan_complete=True,
                ).actions
                self.assertIn(boots.id, {action.item_id for action in actions})

    def test_unusable_boots_create_no_requirement(self):
        for boots in (
            gear("home:cursed-boots", 30, cursed=True),
            gear("home:unknown-boots", 30, known=False),
        ):
            items = (*live_worn_set(), boots)
            with self.subTest(boots=boots.id):
                self.assertNotIn(SLOT_FEET, owned_armor_fill_slots(items))
                result = select(
                    items, lambda loadout: metrics(100.0),
                    enumerate_single_slot_variants,
                )
                self.assertIsNone(result.best.loadout.item_at(SLOT_FEET))

    def test_booted_set_failing_a_requirement_falls_back_without_stopping(self):
        boots = home_boots()
        items = (*live_worn_set(), boots)

        def evaluate(loadout):
            value = metrics(100.0)
            if loadout.item_at(SLOT_FEET) is None:
                return value
            return replace(value, evaluation_complete=False)

        result = select(items, evaluate, enumerate_single_slot_variants)
        self.assertIsNotNone(result.best)
        self.assertIsNone(result.best.loadout.item_at(SLOT_FEET))

    def test_body_rule_is_unchanged(self):
        worn = tuple(
            item for item in live_worn_set() if item.equipped_slot != SLOT_BODY
        )
        body = stats(gear("home:body", 37), ac=17, to_a=11)
        items = (*worn, body)
        current = current_loadout(items)

        def evaluate(loadout):
            return metrics(99.0 if loadout.item_at(SLOT_BODY) else 100.0)

        for name, factory in FACTORIES:
            with self.subTest(factory=name):
                result = select(items, evaluate, factory)
                self.assertIs(result.best.loadout.item_at(SLOT_BODY), body)
                self.assertEqual(
                    result.best.loadout.item_ids, current.item_ids | {body.id}
                )
        # An explicit naked candidate list keeps the old body fallback.
        light = next(item for item in items if item.equipped_slot == "light")
        naked = Loadout((("light", light),), "empty")
        result = optimize_loadout(
            items, lambda loadout: metrics(100.0), depth=1,
            candidate_loadouts=(naked,), require_body=True,
        )
        self.assertIs(result.best.loadout, naked)


if __name__ == "__main__":
    unittest.main()
