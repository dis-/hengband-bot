import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import InventoryItem, Position
from hengbot.policy import (
    ChokeEngagementPlan,
    HengbotPolicy,
    StoreVisit,
    StoreVisitPhase,
)


class CrossDecisionLatchOwnershipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_path = Path(__file__).parents[1] / "src" / "hengbot" / "policy.py"
        cls.tree = ast.parse(cls.source_path.read_text(encoding="utf-8"))
        cls.policy = next(
            node
            for node in cls.tree.body
            if isinstance(node, ast.ClassDef) and node.name == "HengbotPolicy"
        )
        cls.methods = {
            node.name: node
            for node in cls.policy.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_dangerous_latches_declare_owner_and_release_evaluator(self):
        source = ast.get_source_segment(
            self.source_path.read_text(encoding="utf-8"), self.methods["__init__"]
        )
        for latch in (
            "_store_visit",
            "_town_blocked_reason",
            "_equipment_transaction_owned_items",
            "_choke_engagement_plan",
        ):
            with self.subTest(latch=latch):
                self.assertIn(f'"{latch}"', source)
                self.assertRegex(
                    source,
                    rf'(?s)"{latch}".*?CrossDecisionLatch\(\s*"[^"]+",\s*"(_[^"]+)"',
                )

    def test_every_declared_release_evaluator_runs_at_decision_entry(self):
        evaluator = self.methods["_evaluate_cross_decision_latches"]
        evaluator_source = ast.get_source_segment(
            self.source_path.read_text(encoding="utf-8"), evaluator
        )
        self.assertIn("self._cross_decision_latches.values()", evaluator_source)
        self.assertIn("getattr(self, latch.release_evaluator)(snapshot)", evaluator_source)

        decide = self.methods["_decide"]
        first_statement = decide.body[0]
        self.assertIsInstance(first_statement, ast.Expr)
        self.assertEqual(
            ast.unparse(first_statement),
            "self._evaluate_cross_decision_latches(snapshot)",
        )

    def test_each_declared_latch_names_existing_release_sites(self):
        init_source = ast.get_source_segment(
            self.source_path.read_text(encoding="utf-8"), self.methods["__init__"]
        )
        release_site_groups = __import__("re").findall(
            r"release_sites=\((.*?)\)", init_source, flags=__import__("re").S
        )
        release_sites = set(
            name
            for group in release_site_groups
            for name in __import__("re").findall(r'"(_(?:release|close|abandon)_[^"]+)"', group)
        )
        self.assertEqual(4, len(release_site_groups))
        self.assertGreaterEqual(len(release_sites), 4)
        for name in release_sites:
            with self.subTest(release_site=name):
                self.assertIn(name, self.methods)

        evaluator_names = set(
            __import__("re").findall(
                r'CrossDecisionLatch\(\s*"[^"]+",\s*"(_[^"]+)"',
                init_source,
            )
        )
        self.assertEqual(4, len(evaluator_names))
        self.assertTrue(evaluator_names <= self.methods.keys())

    def test_store_visit_releases_when_its_town_situation_ends(self):
        policy = HengbotPolicy()
        policy._store_visit = StoreVisit("store-router", "town-need", 1)
        snapshot = SimpleNamespace(in_town=False, store=None)

        policy._release_invalid_store_visit(snapshot)

        self.assertIsNone(policy._store_visit)
        self.assertEqual(StoreVisitPhase.CLOSED, policy._store_visit_last_closed.phase)

    def test_declared_equipment_evaluator_releases_freshly_worn_owner(self):
        policy = HengbotPolicy()
        ring = InventoryItem(
            slot="main_ring",
            name="Ring of Test",
            count=1,
            tval=45,
            sval=1,
            aware=True,
            known=True,
            is_equipment=True,
        )
        policy._equipment_transaction_owned_items = [
            (equipment_identity(ring), ring.slot)
        ]
        snapshot = SimpleNamespace(equipment=[ring])

        policy._evaluate_cross_decision_latches(snapshot)

        self.assertEqual([], policy._equipment_transaction_owned_items)
        self.assertIsNone(policy._equipment_transaction_town_owner_key(snapshot))

    @staticmethod
    def _choke_plan(floor):
        return ChokeEngagementPlan(
            floor=floor,
            phase="hold",
            destination=Position(10, 10),
            covered_retreat_direction=(0, -1),
            trigger_last_seen={},
            start_exp=0,
            start_gold=0,
            start_breeder_count=1,
            last_player_hp=100,
        )

    def test_every_declared_latch_has_paired_behavioural_release_coverage(self):
        ring = InventoryItem(
            slot="main_ring",
            name="Ring of Test",
            count=1,
            tval=45,
            sval=1,
            aware=True,
            known=True,
            is_equipment=True,
        )
        identity = equipment_identity(ring)

        def store_case(release):
            policy = HengbotPolicy()
            policy._store_visit = StoreVisit("store-router", "town-need", 1)
            snapshot = SimpleNamespace(
                in_town=not release,
                store=None,
                equipment=[],
                floor_key=(0, 0, 0),
            )
            return policy, snapshot, lambda: policy._store_visit is None

        def equipment_case(release):
            policy = HengbotPolicy()
            policy._equipment_transaction_owned_items = [(identity, ring.slot)]
            snapshot = SimpleNamespace(
                in_town=True,
                store=None,
                equipment=[ring] if release else [],
                floor_key=(0, 0, 0),
            )
            return policy, snapshot, lambda: not policy._equipment_transaction_owned_items

        def choke_case(release):
            policy = HengbotPolicy()
            floor = (1, 20, 123)
            policy._choke_engagement_plan = self._choke_plan(floor)
            snapshot = SimpleNamespace(
                floor_key=(1, 21, 124) if release else floor,
                in_town=False,
                store=None,
                equipment=[],
            )
            return (
                policy,
                snapshot,
                lambda: policy._choke_engagement_plan.phase == "release",
            )

        def town_case(release):
            policy = HengbotPolicy()
            policy._town_blocked_reason = (
                "snapshot-local-block" if release else "departure-unsatisfiable"
            )
            snapshot = SimpleNamespace(
                in_town=True, store=None, equipment=[], floor_key=(0, 0, 0)
            )
            return policy, snapshot, lambda: policy._town_blocked_reason is None

        cases = {
            "_store_visit": store_case,
            "_town_blocked_reason": town_case,
            "_equipment_transaction_owned_items": equipment_case,
            "_choke_engagement_plan": choke_case,
        }
        declarations = HengbotPolicy()._cross_decision_latches
        self.assertEqual(set(declarations), set(cases))

        for latch_name, latch in declarations.items():
            for release in (True, False):
                with self.subTest(latch=latch_name, release=release):
                    policy, snapshot, released = cases[latch_name](release)
                    policy._evaluate_cross_decision_latches(snapshot)
                    self.assertEqual(release, released())

    def test_town_block_permanent_and_retained_values_survive_evaluation(self):
        policy = HengbotPolicy()
        latch = policy._cross_decision_latches["_town_blocked_reason"]
        retained_reasons = (
            *latch.permanent_values,
            *latch.retained_values,
            *(prefix + "test" for prefix in latch.retained_prefixes),
        )
        self.assertTrue(retained_reasons)
        snapshot = SimpleNamespace(
            in_town=True, store=None, equipment=[], floor_key=(0, 0, 0)
        )
        for reason in retained_reasons:
            with self.subTest(reason=reason):
                policy._town_blocked_reason = reason
                policy._evaluate_cross_decision_latches(snapshot)
                self.assertEqual(reason, policy._town_blocked_reason)


if __name__ == "__main__":
    unittest.main()
