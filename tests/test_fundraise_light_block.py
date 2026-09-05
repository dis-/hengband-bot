import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.model import STORE_GENERAL, STORE_HOME, parse_snapshot
from hengbot.policy import (
    HengbotPolicy,
    ProcurementHomeGate,
    StoreVisit,
    StoreVisitPhase,
    TownErrandPlan,
    TownNeed,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "fundraise-light-block-pages-20260825.jsonl.gz"
)


def captured_pages():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        rows = [parse_snapshot(json.loads(line), {}) for line in stream]
    return rows[0], rows[1], rows[2], rows[5], rows[8]


def incident_policy():
    policy = HengbotPolicy()
    policy._deepest_level = 1
    policy._fundraising_mode = "mine"
    policy._planned_mining_runs = 1
    return policy


class FundraiseLightBlockAcceptanceTest(unittest.TestCase):
    def test_home_first_yield_does_not_retire_the_general_store_supplier(self):
        _, outside, general, home, _ = captured_pages()
        policy = incident_policy()
        policy._decision_sequence = 1291
        policy._home_knowledge_current = False
        policy._town_errand_plan = TownErrandPlan(
            [STORE_GENERAL],
            need_categories={
                STORE_GENERAL: ("fundraising-light", "fundraising-oil")
            },
        )
        policy._store_visit = StoreVisit(
            "town-errand",
            "shopping",
            STORE_GENERAL,
            phase=StoreVisitPhase.LEAVING,
        )
        policy._shop_observation = (general.store, policy._decision_sequence - 1)

        self.assertIsNone(policy._atomic_shop_transaction_key(outside))
        self.assertNotIn(STORE_GENERAL, policy._town_store_attempted)

        policy._equipment_catalog.observe_home_page(home.store.items)
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        needs = policy._town_need_candidates(general)

        self.assertIn(TownNeed(STORE_GENERAL, "fundraising-light", "normal"), needs)
        self.assertIn(TownNeed(STORE_GENERAL, "fundraising-oil", "normal"), needs)
        self.assertTrue(policy._town_claims_active(general))

    def test_live_fundraising_candidates_compose_the_captured_general_page(self):
        outside, entrance, general, _, _ = captured_pages()
        policy = incident_policy()
        policy._town_supplier_stock[STORE_GENERAL] = general.store

        self.assertTrue(policy._town_blocked_purchase_is_composable(general))
        with patch.object(
            policy, "_shopping_approach_step", return_value=entrance.player.position
        ):
            key = policy._town_procurement_progress_key(outside)

        self.assertIsNotNone(key)
        self.assertEqual(policy._shopping_approach_store_type, STORE_GENERAL)

    def test_shared_boundary_home_first_yield_does_not_latch_the_supplier(self):
        _, outside, general, _, _ = captured_pages()
        policy = incident_policy()
        policy._decision_sequence = 1291
        policy._home_knowledge_current = False
        policy._town_errand_plan = TownErrandPlan(
            [STORE_GENERAL],
            need_categories={STORE_GENERAL: ("fundraising-light",)},
        )
        policy._shopping_approach_store_type = STORE_GENERAL
        policy._shop_observation = (general.store, policy._decision_sequence - 1)

        self.assertFalse(policy._resolve_observed_uncomposable_stop(outside))
        self.assertEqual(policy._town_errand_plan.index, 1)
        self.assertNotIn(STORE_GENERAL, policy._town_store_attempted)

    def test_cycle_break_releases_the_latched_general_shortage_supplier(self):
        _, _, general, _, _ = captured_pages()
        policy = incident_policy()
        policy._town_store_attempted = {
            STORE_GENERAL: general.turn,
            STORE_HOME: general.turn,
        }

        policy._break_town_cycle(general)

        self.assertNotIn(STORE_GENERAL, policy._town_store_attempted)

    def test_blocked_home_with_real_oil_remains_home_first(self):
        _, _, general, home, _ = captured_pages()
        oil = next(item for item in general.store.items if item.is_oil)
        policy = incident_policy()
        policy._equipment_catalog.observe_home_page(home.store.items)
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_items = list(home.store.items)
        policy._home_scan_item_count = len(home.store.items)
        policy._home_knowledge_current = True
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)

        pure = policy._evaluate_purchase_home_gate(general, oil)
        stateful = policy._purchase_has_fresh_home_absence(general, oil)

        self.assertIs(pure, ProcurementHomeGate.HOME_FIRST)
        self.assertIs(stateful, pure)

    def test_captured_window_composes_a_general_purchase_within_eight_decisions(self):
        approach, entrance, general, home, _ = captured_pages()
        policy = incident_policy()
        policy._equipment_catalog.observe_home_page(home.store.items)
        policy._equipment_catalog.home_scan_complete = True
        policy._home_knowledge_current = True
        policy._town_visit_ledger.blocked_stores.add(STORE_HOME)
        policy._town_supplier_stock[STORE_GENERAL] = general.store
        policy._town_errand_plan = TownErrandPlan(
            [STORE_GENERAL],
            need_categories={
                STORE_GENERAL: ("fundraising-light", "fundraising-oil")
            },
        )
        snapshots = [approach, entrance, general, entrance, general, entrance]

        outcomes = [
            (policy.choose_key(snapshot), policy.last_reason) for snapshot in snapshots
        ]

        self.assertTrue(
            any(reason == "shop:one-shot-buy" for _, reason in outcomes),
            outcomes,
        )
        self.assertFalse(
            all(reason == "fundraise:departure-blocked" for _, reason in outcomes),
            outcomes,
        )


if __name__ == "__main__":
    unittest.main()
