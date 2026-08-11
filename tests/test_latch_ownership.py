import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import InventoryItem
from hengbot.policy import HengbotPolicy, StoreVisit, StoreVisitPhase


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


if __name__ == "__main__":
    unittest.main()
