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
from hengbot.policy import HengbotPolicy


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
        taken = ("shovel", 3, 8)
        put = ("shovel", 1, 5)
        executor = HomeVisitExecutor(3)
        executor.file(HomeVisitRequest(
            HomeVisitKind.WITHDRAW, "standing-digger", taken
        ))
        executor.begin_approach(1)
        executor.post_entry(1)
        executor.observe_inside("fresh", 2)
        self.assertTrue(executor.record_operation("take", taken, 2))
        executor.post_exit()
        executor.observe_outside(effect_observed=True)
        self.assertEqual(executor.consume_report().outcome, "completed")
        executor.file(HomeVisitRequest(
            HomeVisitKind.DEPOSIT, "equipment-transaction", put
        ))
        executor.begin_approach(3)
        executor.post_entry(3)
        executor.observe_inside("fresh-2", 4)
        self.assertTrue(executor.record_operation("put", put, 4))
        executor.post_exit()
        executor.observe_outside(effect_observed=True)
        report = executor.consume_report()
        self.assertEqual(report.outcome, "defect")
        self.assertIn("zero-net-inventory-delta", report.defect)
        next_request = HomeVisitRequest(
            HomeVisitKind.WITHDRAW, "standing-digger", taken
        )
        self.assertEqual(executor.file(next_request), "rejected")
        self.assertEqual(
            executor.consume_report().outcome, "semantic-churn-cooldown"
        )
        self.assertLess(executor.attempts_used, 54)

    def test_normal_deposit_then_standing_digger_withdraw_is_not_churn(self):
        deposited = ("normal-supply", 1)
        digger = ("shovel", 3, 8)
        executor = HomeVisitExecutor(3)
        for generation, visit_request, action, identity in (
            (1, HomeVisitRequest(HomeVisitKind.DEPOSIT, "normal", deposited),
             "put", deposited),
            (3, HomeVisitRequest(HomeVisitKind.WITHDRAW, "standing-digger", digger),
             "take", digger),
        ):
            executor.file(visit_request)
            executor.begin_approach(generation)
            executor.post_entry(generation)
            executor.observe_inside(("fresh", generation), generation + 1)
            executor.record_operation(action, identity, generation + 1)
            executor.post_exit()
            executor.observe_outside(effect_observed=True)
            report = executor.consume_report()
            self.assertEqual(report.outcome, "completed")
            self.assertIsNone(report.defect)
        self.assertFalse(executor.semantic_churn_cooldown)

    def test_history_is_visit_scoped_and_same_signature_stacks_are_allowed(self):
        identity = ("oil-flask", 1)
        executor = HomeVisitExecutor(4)
        for generation in (1, 3):
            executor.file(request(HomeVisitKind.DEPOSIT, identity))
            executor.begin_approach(generation)
            executor.post_entry(generation)
            executor.observe_inside(("fresh", generation), generation + 1)
            self.assertTrue(executor.record_operation(
                "put", identity, generation + 1
            ))
            executor.post_exit()
            executor.observe_outside(effect_observed=True)
            self.assertEqual(executor.consume_report().outcome, "completed")
            self.assertEqual(executor.operation_history, [])

    def test_calibration_deposit_restore_is_authorized(self):
        identity = ("oil-flask", 1)
        executor = HomeVisitExecutor(3)
        executor.file(request(HomeVisitKind.DEPOSIT, identity))
        executor.begin_approach(1)
        executor.post_entry(1)
        executor.observe_inside("deposit", 2)
        executor.record_operation("put", identity, 2)
        executor.post_exit()
        executor.observe_outside(effect_observed=True)
        executor.consume_report()
        restore = HomeVisitRequest(
            HomeVisitKind.CALIBRATION_RESTORE, "calibration", identity,
            batch=(identity,),
        )
        executor.file(restore)
        executor.begin_approach(3)
        executor.post_entry(3)
        executor.observe_inside("restore", 4)
        self.assertTrue(executor.record_operation("take", identity, 4))
        executor.post_exit()
        executor.observe_outside(effect_observed=True)
        self.assertEqual(executor.consume_report().outcome, "completed")

    def test_budget_rejection_has_visible_report_and_no_none_crash(self):
        executor = HomeVisitExecutor(1)
        executor.attempts_used = 1
        self.assertEqual(executor.file(request()), "rejected")
        self.assertIsNone(executor.request)
        self.assertFalse(executor.begin_approach(1))
        report = executor.consume_report()
        self.assertEqual(report.outcome, "attempt-budget-exhausted")

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

    @staticmethod
    def _direct_home_approach_bypasses(tree):
        """Find functions that directly approach Home without authorization."""
        findings = []
        for function in (
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ):
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
            direct = any(
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "_shopping_approach_step"
                and any(
                    isinstance(arg, ast.Name) and arg.id == "STORE_HOME"
                    for arg in call.args
                )
                for call in calls
            )
            authorized = any(
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "_ensure_home_visit_request"
                for call in calls
            )
            if direct and not authorized:
                findings.append(function.name)
        return findings

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
        taken_identity, put_identity = sorted(identities, key=repr)[:2]
        executor = HomeVisitExecutor(54)
        executor.file(HomeVisitRequest(
            HomeVisitKind.WITHDRAW, "standing-digger", taken_identity
        ))
        executor.begin_approach(take["decision_sequence"])
        executor.observe_outside_ready(
            (take["home_scan"]["item_count"], take["turn"]),
            take["decision_sequence"],
        )
        executor.record_operation("take", taken_identity, take["decision_sequence"])
        executor.post_exit()
        executor.observe_outside(effect_observed=True)
        executor.consume_report()
        executor.file(HomeVisitRequest(
            HomeVisitKind.DEPOSIT, "equipment-transaction", put_identity
        ))
        executor.begin_approach(put["decision_sequence"])
        executor.observe_outside_ready(
            (put.get("store_stock_num"), put["turn"]),
            put["decision_sequence"],
        )
        executor.record_operation("put", put_identity, put["decision_sequence"])
        executor.post_exit()
        executor.observe_outside(effect_observed=True)
        self.assertIn(
            "zero-net-inventory-delta", executor.consume_report().defect
        )

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
        executor.post_entry(rows[0]["decision_sequence"])
        executor.observe_inside("captured-empty-home", rows[0]["decision_sequence"] + 1)
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
        executor = HomeVisitExecutor(3)
        executor.file(request())
        executor.begin_approach(r300["decision_sequence"])
        executor.post_entry(r300["decision_sequence"])
        self.assertTrue(executor.entry_pending)
        policy = HengbotPolicy()
        policy._home_visit = executor
        self.assertFalse(policy._prepare_home_visit_operation(
            "take", ("shovel", 3, 8), ("fresh",)
        ))

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

    def test_whole_file_home_approach_ratchet_and_evasion_controls(self):
        source = (self.ROOT / "src/hengbot/policy.py").read_text(encoding="utf-8")
        self.assertEqual(self._direct_home_approach_bypasses(ast.parse(source)), [])
        negative = ast.parse(
            "def _legacy_direct_home_visit(self, snapshot):\n"
            "    return self._shopping_approach_step(snapshot, STORE_HOME)\n"
        )
        self.assertEqual(
            self._direct_home_approach_bypasses(negative),
            ["_legacy_direct_home_visit"],
        )
        gated = ast.parse(
            "def migrated(self, snapshot):\n"
            "    if not self._ensure_home_visit_request(snapshot): return None\n"
            "    return self._shopping_approach_step(snapshot, STORE_HOME)\n"
        )
        self.assertEqual(self._direct_home_approach_bypasses(gated), [])


if __name__ == "__main__":
    unittest.main()
