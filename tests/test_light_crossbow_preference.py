"""User launcher rule: an ordinary Sling/Short Bow yields to a Light Crossbow.

User decision 2026-10-02 (verbatim): 「上質以下同士の比較ならスリングより
ライトクロスボウを優先。スリングが高級品以上なら威力評価。という決定を以前したはず。」
(the 2026-07-19 decision covered the Short Bow).  The live boards come from
jsonlog/autorecover-20261002-012442-no-key-exhausted.bot-state-fixed.jsonl.gz
(see tests/extract_xbow_pref_fixture.py for the row numbers).
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest

from hengbot.equipment_optimizer import (
    EvaluatedLoadout,
    Loadout,
    LoadoutMetrics,
    OwnedEquipment,
    _prefer,
    optimize_loadout,
)
from hengbot.launcher_damage import best_obtainable_launcher_damage
from hengbot.model import (
    STORE_GENERAL,
    STORE_HOME,
    STORE_WEAPON,
    SV_BOW_LIGHT_XBOW,
    SV_BOW_SHORT,
    SV_BOW_SLING,
    TVAL_ARROW,
    TVAL_BOLT,
    TVAL_SHOT,
    StoreItem,
    parse_snapshot,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "xbow-pref-live-20261002-012442.json.gz"
)
FIXTURE_SHA256 = "182563a3ecb55dac656eb9c104546544ce491d8f7a429c6f3cec45e846fd3d5d"


def live_rows():
    body = gzip.decompress(FIXTURE.read_bytes())
    digest = hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest()
    assert digest == FIXTURE_SHA256, digest
    rows = json.loads(body)["rows"]
    return {int(row): parse_snapshot(data, {}) for row, data in rows.items()}


def flat_metrics(ranged):
    return LoadoutMetrics(
        expected_dps=10.0,
        survival_turns=100.0,
        combat_margin=90.0,
        ranged_dps=ranged,
        speed_bonus=0,
        secondary_value=0,
        relevant_traits=frozenset(),
    )


class LiveLightCrossbowPreferenceTest(unittest.TestCase):
    def setUp(self):
        self.rows = live_rows()
        surface = self.rows[95]
        home_page = self.rows[30]
        general = self.rows[44]
        self.assertIsNone(surface.store)
        self.assertEqual(home_page.store.store_type, STORE_HOME)
        self.assertEqual(home_page.store.page_top, 52)
        self.assertEqual(general.store.store_type, STORE_GENERAL)
        sling_item = next(item for item in surface.equipment if item.slot == "bow")
        self.assertEqual(
            (sling_item.sval, sling_item.to_h, sling_item.to_d,
             sling_item.is_ego, sling_item.is_artifact),
            (SV_BOW_SLING, 10, 10, False, False),
        )
        crossbow_item = next(
            item for item in home_page.store.items if item.tval == 19
        )
        self.assertEqual(
            (crossbow_item.sval, crossbow_item.to_h, crossbow_item.to_d,
             crossbow_item.is_ego),
            (SV_BOW_LIGHT_XBOW, 4, 3, False),
        )
        self.sling = OwnedEquipment(
            "equipped:live-sling", sling_item, "equipped", equipped_slot="bow"
        )
        self.crossbow = OwnedEquipment("home:live-crossbow", crossbow_item, "home")
        self.shots = tuple(
            item for item in surface.inventory if item.tval == TVAL_SHOT
        )
        self.assertEqual(sum(item.count for item in self.shots), 99)
        self.store_bolts = tuple(
            item for item in general.store.items
            if item.tval == TVAL_BOLT and item.to_h == 0 and item.to_d == 0
        )
        self.assertEqual(
            [(item.count, item.price) for item in self.store_bolts], [(99, 3)]
        )

    def choose(self, sling, ammunition):
        candidates = (
            Loadout((("bow", sling),), "empty"),
            Loadout((("bow", self.crossbow),), "empty"),
        )

        def evaluate(loadout):
            # Mirror the live per-shot damage so the evaluator itself favours
            # the higher-damage launcher, as the warrior evaluator does.
            bow = loadout.item_at("bow")
            return flat_metrics(
                best_obtainable_launcher_damage(bow.item, ammunition)
            )

        result = optimize_loadout(
            (sling, self.crossbow),
            evaluate,
            depth=1,
            current_item_ids=frozenset({sling.id}),
            candidate_loadouts=candidates,
            obtainable_ammunition=ammunition,
        )
        self.assertIsNotNone(result.best)
        return result.best.loadout.item_at("bow")

    def test_live_ordinary_sling_yields_to_home_crossbow_with_store_bolts(self):
        ammunition = (*self.shots, *self.store_bolts)
        # Damage alone would keep the sling: (2+10)x2 = 24 vs (3+3)x3 = 18.
        self.assertEqual(
            best_obtainable_launcher_damage(self.sling.item, ammunition), 24.0
        )
        self.assertEqual(
            best_obtainable_launcher_damage(self.crossbow.item, ammunition), 18.0
        )

        self.assertEqual(self.choose(self.sling, ammunition).id, self.crossbow.id)

    def test_live_crossbow_without_obtainable_bolts_keeps_usable_sling(self):
        self.assertEqual(self.choose(self.sling, self.shots).id, self.sling.id)

    def test_high_grade_sling_is_compared_by_damage(self):
        ammunition = (*self.shots, *self.store_bolts)
        for grade in (
            {"is_ego": True},
            {"is_artifact": True},
            {"pseudo_feeling": "excellent"},
            {"pseudo_feeling": "special"},
        ):
            with self.subTest(grade=grade, to_d=10):
                strong = replace(self.sling, item=replace(self.sling.item, **grade))
                self.assertEqual(self.choose(strong, ammunition).id, strong.id)
            with self.subTest(grade=grade, to_d=0):
                weak = replace(
                    self.sling,
                    item=replace(self.sling.item, to_h=0, to_d=0, **grade),
                )
                # (2+0)x2 = 4 < 18: the damage comparison picks the crossbow.
                self.assertEqual(self.choose(weak, ammunition).id, self.crossbow.id)

    def test_pairwise_rule_precedes_damage_and_respects_unusable_crossbow(self):
        sling = EvaluatedLoadout(
            Loadout((("bow", self.sling),), "empty"), flat_metrics(24.0)
        )
        crossbow = EvaluatedLoadout(
            Loadout((("bow", self.crossbow),), "empty"), flat_metrics(18.0)
        )
        damage = {self.sling.id: 24.0, self.crossbow.id: 18.0}
        usable = frozenset({self.sling.id, self.crossbow.id})
        current = frozenset({self.sling.id})

        self.assertTrue(_prefer(crossbow, sling, current, damage, usable))
        self.assertFalse(_prefer(sling, crossbow, current, damage, usable))
        # No obtainable bolts: the usable sling is never displaced.
        sling_only = frozenset({self.sling.id})
        no_bolts = {self.sling.id: 24.0, self.crossbow.id: 0.0}
        self.assertFalse(_prefer(crossbow, sling, current, no_bolts, sling_only))
        self.assertTrue(_prefer(sling, crossbow, current, no_bolts, sling_only))


class ShortBowRuleTest(unittest.TestCase):
    def owned(self, item_id, sval, *, to_d=0, ego=False, slot=None):
        item = StoreItem(
            letter="?", name=item_id, count=1, tval=19, sval=sval, price=0,
            is_equipment=True, is_ego=ego, to_d=to_d,
        )
        return OwnedEquipment(
            item_id, item, "equipped" if slot else "home", equipped_slot=slot
        )

    def ammo(self, tval):
        return StoreItem(
            letter="?", name=f"ammo-{tval}", count=99, tval=tval, sval=1,
            price=1, damage_dice_num=1, damage_dice_sides=4 if tval == TVAL_ARROW else 5,
        )

    def test_ordinary_short_bow_yields_even_when_its_ammo_damage_is_higher(self):
        short = self.owned("short", SV_BOW_SHORT, to_d=10, slot="bow")
        crossbow = self.owned("xbow", SV_BOW_LIGHT_XBOW, to_d=3)
        ammunition = (self.ammo(TVAL_ARROW), self.ammo(TVAL_BOLT))
        self.assertGreater(
            best_obtainable_launcher_damage(short.item, ammunition),
            best_obtainable_launcher_damage(crossbow.item, ammunition),
        )
        result = optimize_loadout(
            (short, crossbow),
            lambda loadout: flat_metrics(1.0),
            depth=1,
            current_item_ids=frozenset({short.id}),
            candidate_loadouts=(
                Loadout((("bow", short),), "empty"),
                Loadout((("bow", crossbow),), "empty"),
            ),
            obtainable_ammunition=ammunition,
        )
        self.assertEqual(result.best.loadout.item_at("bow").id, crossbow.id)

    def test_ego_short_bow_with_higher_damage_is_kept(self):
        short = self.owned("short", SV_BOW_SHORT, to_d=10, ego=True, slot="bow")
        crossbow = self.owned("xbow", SV_BOW_LIGHT_XBOW, to_d=3)
        ammunition = (self.ammo(TVAL_ARROW), self.ammo(TVAL_BOLT))
        result = optimize_loadout(
            (short, crossbow),
            lambda loadout: flat_metrics(1.0),
            depth=1,
            current_item_ids=frozenset({short.id}),
            candidate_loadouts=(
                Loadout((("bow", short),), "empty"),
                Loadout((("bow", crossbow),), "empty"),
            ),
            obtainable_ammunition=ammunition,
        )
        self.assertEqual(result.best.loadout.item_at("bow").id, short.id)


if __name__ == "__main__":
    unittest.main()
