"""Decision-local store material and supplier route computations (#47)."""
import tests  # noqa: F401

from collections import Counter
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_types import TownNeed
from hengbot.model import STORE_TEMPLE, StoreState, StoreItem, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL
from tests import test_town_terminal_plan_round7 as plan_tests
from tests.town_s2_exit_replay import FIXTURES, replay_n1


class DecisionMaterialMemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plan_tests.PlanAdmissionTest.setUpClass()
        cls.board = plan_tests.PlanAdmissionTest.board

    def test_same_key_hits_and_new_decision_or_board_recomputes(self):
        board = self.board
        policy = plan_tests.PlanAdmissionTest().policy()
        need = TownNeed(STORE_TEMPLE, "recall", "normal")
        compute = tt._compute_store_buy_material
        route = policy._compute_town_need_supplier_reachable
        with patch.object(tt, "_compute_store_buy_material", wraps=compute) as material, \
                patch.object(policy, "_compute_town_need_supplier_reachable", wraps=route) as reachable:
            first = tt.gather_store_buy(policy, board, need)
            self.assertIs(tt.gather_store_buy(policy, board, replace(need)), first)
            self.assertEqual((material.call_count, reachable.call_count), (1, 1))
            # Route is independent of category; the material is not.
            tt.gather_store_buy(policy, board, replace(need, category="food"))
            self.assertEqual((material.call_count, reachable.call_count), (2, 1))
            policy._decision_sequence += 1
            tt.gather_store_buy(policy, board, need)
            self.assertEqual((material.call_count, reachable.call_count), (3, 2))
            self.assertEqual(len(policy._store_buy_material_memo[2]), 1)
            tt.gather_store_buy(policy, replace(board), need)
            self.assertEqual((material.call_count, reachable.call_count), (4, 3))
            self.assertEqual(len(policy._supplier_reachability_memo[2]), 1)

    def test_policy_material_writes_invalidate_within_a_decision(self):
        board = self.board
        policy = plan_tests.PlanAdmissionTest().policy()
        need = TownNeed(STORE_TEMPLE, "recall", "normal")
        recall = StoreItem("a", "recall", 1, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, 40)
        policy._town_supplier_stock[STORE_TEMPLE] = StoreState(STORE_TEMPLE, [recall])
        compute = tt._compute_store_buy_material
        with patch.object(tt, "_compute_store_buy_material", wraps=compute) as material:
            self.assertTrue(tt.verdict_store_buy(tt.gather_store_buy(policy, board, need)).admitted)
            policy._town_store_attempted[STORE_TEMPLE] = 1
            self.assertTrue(tt.verdict_store_buy(tt.gather_store_buy(policy, board, need)).admitted)
            policy._town_supplier_stock[STORE_TEMPLE].items[:] = [replace(recall, price=1000)]
            self.assertEqual(tt.verdict_store_buy(tt.gather_store_buy(policy, board, need)).codes,
                             ("no-matching-offer",))
            policy._town_supplier_stock[STORE_TEMPLE].items[:] = [recall]
            policy._town_visit_sale_signatures.add((recall.tval, recall.sval))
            self.assertFalse(tt.verdict_store_buy(tt.gather_store_buy(policy, board, need)).admitted)
            policy._town_visit_sale_signatures.clear()
            policy._town_visit_ledger.purchase_churn_class_exclusions.add(
                (STORE_TEMPLE, recall.tval, recall.sval))
            self.assertFalse(tt.verdict_store_buy(tt.gather_store_buy(policy, board, need)).admitted)
            policy._town_visit_sale_identify_charges = 1
            tt.gather_store_buy(policy, board, need)
            policy._fundraising_mode = "prepare"
            tt.gather_store_buy(policy, board, need)
            self.assertEqual(material.call_count, 7)

    def test_changed_layout_recomputes_route_and_material(self):
        policy = plan_tests.PlanAdmissionTest().policy()
        need = TownNeed(STORE_TEMPLE, "recall", "normal")
        # An unseen store relies on remembered town topology.
        board = replace(self.board, grids={}, store=None)
        first = tt.gather_store_buy(policy, board, need)
        self.assertTrue(first.reachable)
        policy._town_maps = {}
        self.assertFalse(tt.gather_store_buy(policy, board, need).reachable)

    def test_old_checkpoint_defaults_and_constructor(self):
        policy = HengbotPolicy()
        self.assertIsNone(policy._store_buy_material_memo)
        self.assertIsNone(policy._supplier_reachability_memo)
        del policy._store_buy_material_memo, policy._supplier_reachability_memo
        normalize_policy_state(policy, restart=True)
        self.assertIsNone(policy._store_buy_material_memo)
        self.assertIsNone(policy._supplier_reachability_memo)

    def test_183351_real_computations_once_per_distinct_key(self):
        materials, routes = Counter(), Counter()
        compute = tt._compute_store_buy_material
        route = HengbotPolicy._compute_town_need_supplier_reachable

        def material(policy, board, need):
            page = policy._town_supplier_stock.get(need.store_type)
            key = (id(policy), policy._decision_sequence, id(board), need, policy._town_need_supplier_reachable,
                   id(policy._town_map), policy._town_map_active,
                   tuple((town, id(layout)) for town, layout in policy._town_maps.items()),
                   tuple(page.items) if page is not None else None,
                   need.store_type in policy._town_store_attempted,
                   frozenset(policy._town_visit_sale_signatures),
                   frozenset(policy._town_visit_ledger.purchase_churn_class_exclusions),
                   policy._town_visit_sale_identify_charges, policy._fundraising_mode)
            materials[key] += 1
            return compute(policy, board, need)

        def reachable(policy, board, need):
            key = (id(policy), policy._decision_sequence, id(board), need.store_type, id(policy._town_map), policy._town_map_active,
                   tuple((town, id(layout)) for town, layout in policy._town_maps.items()))
            routes[key] += 1
            return route(policy, board, need)

        with patch.object(tt, "_compute_store_buy_material", material), \
                patch.object(HengbotPolicy, "_compute_town_need_supplier_reachable", reachable):
            trace = replay_n1("20261023-183351")
        expected = json.loads((FIXTURES / "town-s2-exit-expected.json").read_text(encoding="utf8"))
        self.assertEqual([[r["turn"], r["key"], r["reason"]] for r in trace],
                         expected["20261023-183351"]["trace"])
        self.assertTrue(materials)
        self.assertTrue(routes)
        self.assertEqual(max(materials.values()), 1)
        self.assertEqual(max(routes.values()), 1)
        print(f"183351: {len(trace)} decisions; material computes={sum(materials.values())}; "
              f"route computes={sum(routes.values())}; max per key=1", flush=True)


if __name__ == "__main__":
    unittest.main()
