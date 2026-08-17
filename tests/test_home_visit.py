import ast
import json
from pathlib import Path
import unittest

from hengbot.home_visit import (
    HomeVisitExecutor,
    HomeVisitKind,
    HomeVisitRequest,
    HomeVisitState,
)


def request(kind=HomeVisitKind.WITHDRAW, identity=("shovel", 3, 8), **kwargs):
    return HomeVisitRequest(kind, "test", item_identity=identity, **kwargs)


class HomeVisitExecutorTest(unittest.TestCase):
    def test_one_operation_per_entry_and_explicit_report(self):
        executor = HomeVisitExecutor(3)
        self.assertEqual(executor.file(request()), "filed")
        self.assertTrue(executor.begin_approach(10))
        self.assertTrue(executor.post_entry(10))
        executor.observe_inside(("page", 1), 11)
        self.assertTrue(executor.record_operation("take", ("shovel", 3, 8), 11))
        self.assertFalse(executor.record_operation("take", ("shovel", 3, 8), 11))
        self.assertTrue(executor.post_exit())
        executor.observe_outside(effect_observed=True)
        report = executor.consume_report()
        self.assertEqual(report.outcome, "completed")
        self.assertEqual(executor.state, HomeVisitState.IDLE)

    def test_optimizer_replacement_queues_without_resetting_budget(self):
        executor = HomeVisitExecutor(2)
        first = request(identity=("shovel", 3, 8))
        second = request(identity=("shovel", 1, 5))
        executor.file(first)
        executor.begin_approach(1)
        self.assertEqual(executor.file(second), "queued")
        self.assertEqual(executor.attempts_used, 1)
        executor.post_entry(1)
        executor.observe_inside("fresh", 2)
        executor.record_operation("take", first.item_identity, 2)
        executor.post_exit()
        executor.observe_outside(effect_observed=True)
        executor.consume_report()
        self.assertEqual(executor.request, second)
        self.assertEqual(executor.attempts_used, 1)

    def test_outside_key_is_refused_while_entry_pending(self):
        executor = HomeVisitExecutor(2)
        executor.file(request())
        executor.begin_approach(4)
        executor.post_entry(4)
        self.assertTrue(executor.entry_pending)
        self.assertFalse(executor.begin_approach(5))
        self.assertFalse(executor.record_operation("take", ("shovel", 3, 8), 5))

    def test_retention_conflict_is_rejected_at_filing(self):
        identity = ("shovel", 3, 8)
        with self.assertRaisesRegex(ValueError, "retention-wins"):
            request(
                HomeVisitKind.DEPOSIT,
                identity,
                keep_set=frozenset({identity}),
            )

    def test_semantic_churn_is_a_visible_defect(self):
        identity = ("shovel", 3, 8)
        executor = HomeVisitExecutor(3)
        executor.operation_history.append(("take", identity))
        executor.file(request(HomeVisitKind.DEPOSIT, identity))
        executor.begin_approach(1)
        executor.post_entry(1)
        executor.observe_inside("fresh", 2)
        self.assertFalse(executor.record_operation("put", identity, 2))
        report = executor.consume_report()
        self.assertEqual(report.outcome, "defect")
        self.assertIn("semantic-churn", report.defect)

    def test_restart_refiles_same_immutable_request(self):
        frozen = request()
        first = HomeVisitExecutor(2)
        first.file(frozen)
        restored = HomeVisitExecutor(2)
        self.assertEqual(restored.file(frozen), "filed")
        self.assertEqual(restored.request, first.request)


class HomeVisitCaptureAcceptanceTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    @classmethod
    def _rows(cls, relative, wanted):
        rows = []
        with (cls.ROOT / relative).open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row.get("reason") in wanted or row.get("key") == "R300\r":
                    rows.append(row)
        return rows

    def test_takeput_capture_becomes_one_owned_operation_and_churn_defect(self):
        rows = self._rows(
            "evidence/evidence-takeput-oscillation-20260817-2340.jsonl",
            {"home:atomic-withdraw", "equipment-transaction:atomic-deposit"},
        )
        take = next(row for row in rows if row["reason"] == "home:atomic-withdraw")
        put = next(
            row for row in rows
            if row["reason"] == "equipment-transaction:atomic-deposit"
        )
        identities = {
            tuple(identity)
            for row in (take, put)
            for identity in row["equipment_optimization"]["deferred_home_item_signatures"]
        }
        self.assertGreaterEqual(len(identities), 2)
        identity = sorted(identities, key=repr)[0]
        executor = HomeVisitExecutor(54)
        executor.operation_history.append(("take", identity))
        executor.file(request(HomeVisitKind.DEPOSIT, identity))
        executor.begin_approach(take["decision_sequence"])
        executor.observe_outside_ready(
            (take["home_scan"]["item_count"], take["turn"]),
            take["decision_sequence"],
        )
        self.assertFalse(executor.record_operation(
            "put", identity, take["decision_sequence"]
        ))
        self.assertIn("semantic-churn", executor.consume_report().defect)

    def test_door_bounce_capture_collapses_to_report_and_durable_budget(self):
        rows = self._rows(
            "incident-captures/20260818-001502-loop-detected/decision-tail.jsonl",
            {
                "shop:approach", "store:entry-await-observation",
                "home:route-claim-unfulfilled",
            },
        )
        reasons = [row["reason"] for row in rows]
        self.assertIn("store:entry-await-observation", reasons)
        self.assertIn("home:route-claim-unfulfilled", reasons)
        executor = HomeVisitExecutor(3)
        executor.file(request())
        executor.begin_approach(rows[0]["decision_sequence"])
        executor.observe_outside_ready("fresh-address", rows[0]["decision_sequence"])
        executor.record_operation(
            "take", ("shovel", 3, 8), rows[0]["decision_sequence"]
        )
        executor.post_exit()
        executor.observe_outside(effect_observed=False)
        self.assertEqual(executor.consume_report().outcome, "unfulfilled")
        self.assertEqual(executor.attempts_used, 1)
        executor.file(request(identity=("shovel", 1, 5)))
        self.assertEqual(executor.attempts_used, 1)

    def test_r300_capture_is_outside_only_and_entry_barrier_refuses_it(self):
        rows = self._rows(
            "evidence/evidence-takeput-oscillation-20260817-2340.jsonl", set()
        )
        r300 = next(row for row in rows if row.get("key") == "R300\r")
        self.assertIsNone(r300["store_type"])
        executor = HomeVisitExecutor(3)
        executor.file(request())
        executor.begin_approach(r300["decision_sequence"])
        executor.post_entry(r300["decision_sequence"])
        self.assertTrue(executor.entry_pending)
        self.assertFalse(executor.begin_approach(r300["decision_sequence"] + 1))

    def test_ast_ratchet_keeps_optimizer_and_composers_under_executor(self):
        source = (self.ROOT / "src/hengbot/policy.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {
            node.name: node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        install = ast.unparse(functions["_set_equipment_transaction_session"])
        self.assertNotIn("_town_store_attempted.pop(STORE_HOME", install)
        approach = ast.unparse(functions["_shopping_approach_step"])
        self.assertIn("_ensure_home_visit_request(snapshot)", approach)
        for name in ("_atomic_home_withdraw_key", "_atomic_home_deposit_key"):
            body = ast.unparse(functions[name])
            self.assertIn("_prepare_home_visit_operation", body)


if __name__ == "__main__":
    unittest.main()
