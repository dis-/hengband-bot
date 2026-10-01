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
    SLOT_BOW,
    EvaluatedLoadout,
    Loadout,
    LoadoutMetrics,
    OwnedEquipment,
    _prefer,
    optimize_loadout,
)
from hengbot.equipment_transaction_planner import plan_equipment_transactions
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
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_RESTOCK_WAIT_TURNS

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


class LivePolicyLauncherEvidenceTest(unittest.TestCase):
    """Policy seams fed with the recorded 012442 boards (no hand-built items)."""

    def setUp(self):
        self.rows = live_rows()
        self.surface = self.rows[95]
        self.home_items = (
            *self.rows[29].store.items, *self.rows[30].store.items
        )
        self.crossbow = next(
            item for item in self.rows[30].store.items
            if item.tval == 19 and item.sval == SV_BOW_LIGHT_XBOW
        )

    def policy(self):
        policy = HengbotPolicy()
        policy._home_knowledge_items = self.home_items
        policy._home_knowledge_current = True
        return policy

    def remember(self, policy, row, town_id=None):
        """Record a supplier page as policy.py:10058-10062 does on entry."""
        board = self.rows[row]
        policy._town_supplier_stock[board.store.store_type] = board.store
        policy._town_supplier_stock_observations[board.store.store_type] = (
            policy._effective_town_id(board) if town_id is None else town_id,
            board.turn,
        )

    def test_remembered_plain_store_bolts_are_obtainable_ammunition(self):
        fresh = self.policy()
        self.assertFalse(any(
            item.tval == TVAL_BOLT
            for item in fresh._obtainable_launcher_ammunition(self.surface)
        ))

        policy = self.policy()
        self.remember(policy, 44)
        # Recorded: the General Store page (turn 2320759) is still current at
        # the Weapon Smith board (turn 2321048), which is the open page.
        board = self.rows[56]
        self.assertLess(board.turn - self.rows[44].turn, STORE_RESTOCK_WAIT_TURNS)
        obtainable = policy._obtainable_launcher_ammunition(board)

        self.assertEqual(
            sorted(
                (item.tval, item.count, item.to_h, item.to_d)
                for item in obtainable if item.tval == TVAL_BOLT
            ),
            [(TVAL_BOLT, 99, 0, 0), (TVAL_BOLT, 99, 0, 0)],
        )
        # Enchanted store shots are not what the ammo rung buys.
        self.assertNotIn(
            (TVAL_SHOT, 27, 2, 3),
            [(item.tval, item.count, item.to_h, item.to_d) for item in obtainable],
        )
        sling = next(item for item in self.surface.equipment if item.slot == "bow")
        self.assertEqual(best_obtainable_launcher_damage(self.crossbow, obtainable), 18.0)
        self.assertEqual(best_obtainable_launcher_damage(sling, obtainable), 24.0)

    def test_supplier_pages_from_another_town_or_expired_are_not_evidence(self):
        policy = self.policy()
        self.remember(policy, 56, town_id=policy._effective_town_id(self.surface) + 1)
        self.assertFalse(any(
            item.tval == TVAL_BOLT
            for item in policy._obtainable_launcher_ammunition(self.surface)
        ))
        # Recorded turns: the General Store page (2320759) is older than the
        # restock turnover at the surface board (2321880).
        policy = self.policy()
        self.remember(policy, 44)
        self.assertGreaterEqual(
            self.surface.turn - self.rows[44].turn, STORE_RESTOCK_WAIT_TURNS
        )
        self.assertFalse(any(
            item.tval == TVAL_BOLT
            for item in policy._obtainable_launcher_ammunition(self.surface)
        ))

    def test_bolts_remembered_in_another_town_do_not_authorize_swap_in(self):
        sling_item = next(
            item for item in self.surface.equipment if item.slot == "bow"
        )
        sling = OwnedEquipment(
            "equipped:live-sling", sling_item, "equipped", equipped_slot=SLOT_BOW
        )
        crossbow = OwnedEquipment("home:live-crossbow", self.crossbow, "home")
        current_town = self.policy()._effective_town_id(self.surface)
        chosen = {}
        for label, town_id in (("other", current_town + 1), ("current", None)):
            policy = self.policy()
            self.remember(policy, 56, town_id=town_id)
            ammunition = policy._obtainable_launcher_ammunition(self.surface)
            result = optimize_loadout(
                (sling, crossbow),
                lambda loadout: flat_metrics(1.0),
                depth=1,
                current_item_ids=frozenset({sling.id}),
                candidate_loadouts=(
                    Loadout(((SLOT_BOW, sling),), "empty"),
                    Loadout(((SLOT_BOW, crossbow),), "empty"),
                ),
                obtainable_ammunition=ammunition,
            )
            chosen[label] = result.best.loadout.item_at(SLOT_BOW).id
        self.assertEqual(chosen, {"other": sling.id, "current": crossbow.id})

    def test_equipped_crossbow_is_kept_with_zero_bolts_after_restart(self):
        # Post-swap state rebuilt from the recorded items: the Light Crossbow
        # (+4,+3) worn, the ordinary Sling (+10,+10) shelved in Home, no bolts
        # anywhere, and a fresh process (empty supplier memory).
        sling_item = next(
            item for item in self.surface.equipment if item.slot == "bow"
        )
        crossbow = OwnedEquipment(
            "equipped:live-crossbow", self.crossbow, "equipped",
            equipped_slot=SLOT_BOW,
        )
        sling = OwnedEquipment("home:live-sling", sling_item, "home")
        policy = self.policy()
        self.assertEqual(policy._town_supplier_stock, {})
        ammunition = policy._obtainable_launcher_ammunition(self.surface)
        self.assertFalse(any(item.tval == TVAL_BOLT for item in ammunition))
        self.assertTrue(any(item.tval == TVAL_SHOT for item in ammunition))

        result = optimize_loadout(
            (sling, crossbow),
            lambda loadout: flat_metrics(
                best_obtainable_launcher_damage(
                    loadout.item_at(SLOT_BOW).item, ammunition
                )
            ),
            depth=1,
            current_item_ids=frozenset({crossbow.id}),
            candidate_loadouts=(
                Loadout(((SLOT_BOW, sling),), "empty"),
                Loadout(((SLOT_BOW, crossbow),), "empty"),
            ),
            obtainable_ammunition=ammunition,
        )
        self.assertEqual(result.best.loadout.item_at(SLOT_BOW).id, crossbow.id)

    def test_swap_in_blocked_when_no_bolts_are_obtainable_anywhere(self):
        sling_item = next(
            item for item in self.surface.equipment if item.slot == "bow"
        )
        sling = OwnedEquipment(
            "equipped:live-sling", sling_item, "equipped", equipped_slot=SLOT_BOW
        )
        crossbow = OwnedEquipment("home:live-crossbow", self.crossbow, "home")
        ammunition = self.policy()._obtainable_launcher_ammunition(self.surface)
        result = optimize_loadout(
            (sling, crossbow),
            lambda loadout: flat_metrics(1.0),
            depth=1,
            current_item_ids=frozenset({sling.id}),
            candidate_loadouts=(
                Loadout(((SLOT_BOW, sling),), "empty"),
                Loadout(((SLOT_BOW, crossbow),), "empty"),
            ),
            obtainable_ammunition=ammunition,
        )
        self.assertEqual(result.best.loadout.item_at(SLOT_BOW).id, sling.id)

    def test_ammo_errand_falls_back_to_general_store(self):
        # Derived board: the recorded surface (99 shots) with the shot stack
        # cut to the 48 recorded at rows 29-56, so the ordinary ammo errand is
        # live. Derived page: the recorded Weapon Smith page (row 56) with its
        # plain iron shots removed (a stock-out).
        shots = next(item for item in self.surface.inventory if item.tval == TVAL_SHOT)
        board = replace(
            self.surface,
            inventory=[
                replace(item, count=48) if item is shots else item
                for item in self.surface.inventory
            ],
        )
        smith = self.rows[56].store
        sold_out = replace(smith, items=tuple(
            item for item in smith.items
            if not (item.tval == TVAL_SHOT and item.to_h == 0 and item.to_d == 0)
        ))

        def ammo_errands(policy):
            return [
                need.store_type
                for need in policy._town_need_candidates(board)
                if need.category == "ammo"
            ]

        stocked = self.policy()
        self.remember(stocked, 56)
        self.assertEqual(ammo_errands(stocked), [STORE_WEAPON])

        policy = self.policy()
        self.remember(policy, 56)
        policy._town_supplier_stock[STORE_WEAPON] = sold_out
        self.assertEqual(ammo_errands(policy), [STORE_GENERAL])
        # The General Store page (row 44) shows plain shots, arrows and bolts.
        self.assertEqual(
            sorted(item.tval for item in policy._launcher_ammo_offers(
                self.rows[44], STORE_GENERAL
            )),
            [TVAL_SHOT, TVAL_ARROW, TVAL_BOLT],
        )

        attempted = self.policy()
        attempted._town_store_attempted[STORE_WEAPON] = board.turn
        self.assertEqual(ammo_errands(attempted), [STORE_GENERAL])
        attempted._town_store_attempted[STORE_GENERAL] = board.turn
        self.assertEqual(ammo_errands(attempted), [])

    def test_unaffordable_store_ammo_is_not_an_offer(self):
        board = self.rows[44]
        poor = replace(board, player=replace(board.player, gold=0))
        policy = self.policy()
        self.assertTrue(policy._launcher_ammo_offers(board, STORE_GENERAL))
        self.assertEqual(policy._launcher_ammo_offers(poor, STORE_GENERAL), ())

    def test_open_store_page_counts_without_memory(self):
        policy = self.policy()
        obtainable = policy._obtainable_launcher_ammunition(self.rows[44])
        self.assertTrue(any(
            item.tval == TVAL_BOLT and item.count == 99 for item in obtainable
        ))

    def test_ordinary_sling_never_marks_home_light_crossbow_disposable(self):
        board = self.rows[30]
        self.assertEqual(
            next(item for item in board.equipment if item.slot == "bow").sval,
            SV_BOW_SLING,
        )
        policy = self.policy()
        self.assertFalse(
            policy._is_disposable_dominated_launcher(board, self.crossbow)
        )

    def test_swap_plan_withdraws_home_crossbow_and_shelves_the_sling(self):
        sling_item = next(
            item for item in self.surface.equipment if item.slot == "bow"
        )
        sling = OwnedEquipment(
            "equipped:live-sling", sling_item, "equipped", equipped_slot=SLOT_BOW
        )
        crossbow = OwnedEquipment("home:live-crossbow", self.crossbow, "home")
        plan = plan_equipment_transactions(
            (sling, crossbow),
            Loadout(((SLOT_BOW, sling),), "empty"),
            Loadout(((SLOT_BOW, crossbow),), "empty"),
            current_pack_items=len(self.surface.inventory),
            home_scan_complete=True,
        )
        self.assertEqual(plan.blockers, ())
        self.assertEqual(
            [(action.kind, action.item_id) for action in plan.actions],
            [
                ("withdraw", crossbow.id),
                ("takeoff", sling.id),
                ("equip", crossbow.id),
                ("deposit", sling.id),
            ],
        )


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
