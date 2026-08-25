import json
import unittest
from pathlib import Path

from hengbot.home_errand import (
    HomeErrandExecutor,
    HomeErrandRequest,
    HomeErrandState,
)


ROOT = Path(__file__).parents[1]


class HomeErrandExecutorTest(unittest.TestCase):
    def request(self, purpose="identification"):
        return HomeErrandRequest(("captured target", 23, 14), 1, "home-page", purpose)

    def test_observations_drive_the_complete_lifecycle(self):
        executor = HomeErrandExecutor()
        self.assertTrue(executor.file(self.request(), knowledge_current=False))
        self.assertEqual(executor.state, HomeErrandState.NEED_KNOWLEDGE)
        executor.observe_knowledge(True)
        self.assertEqual(executor.state, HomeErrandState.COMPOSABLE)
        executor.post(0)
        self.assertEqual(executor.state, HomeErrandState.POSTED)
        executor.observe_outside(1)
        self.assertEqual(executor.state, HomeErrandState.DONE)

    def test_posted_without_pack_delta_is_failed(self):
        executor = HomeErrandExecutor()
        executor.file(self.request(), knowledge_current=True)
        executor.post(0)
        executor.observe_outside(0)
        self.assertEqual(executor.state, HomeErrandState.FAILED)

    def test_scan_refusal_is_a_visible_named_stop(self):
        executor = HomeErrandExecutor()
        executor.file(self.request(), knowledge_current=False)
        executor.observe_scan_refused("knowledge-response-missing")
        self.assertEqual(executor.state, HomeErrandState.STOPPED)
        self.assertEqual(
            executor.reason("ignored"),
            "home-errand:stopped:knowledge-response-missing",
        )

    def test_visit_ledger_bound_stops_zero_address_progress(self):
        executor = HomeErrandExecutor()
        executor.file(self.request(), knowledge_current=True)
        for _ in range(3):
            executor.observe_unaddressed_entry(3, "target-unobserved")
        self.assertEqual(executor.state, HomeErrandState.STOPPED)
        self.assertEqual(
            executor.reason("ignored"), "home-errand:stopped:target-unobserved"
        )

    def test_all_three_captured_entry_exit_loops_are_bounded_by_executor(self):
        captures = (
            "evidence-home-target-unobserved-loop.jsonl",
            "evidence-home-yield-loop-20260813.jsonl",
            "evidence-q34-home-reenter-loop.jsonl",
        )
        for name in captures:
            with self.subTest(capture=name):
                path = ROOT / "evidence" / name
                if not path.is_file():
                    self.skipTest(f"dead external incident artifact: {path}")
                records = [json.loads(line) for line in path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines() if line.strip()]
                reasons = [record.get("reason", "") for record in records]
                self.assertTrue(
                    any("home" in reason for reason in reasons),
                    f"capture has no Home producer evidence: {name}",
                )
                executor = HomeErrandExecutor()
                executor.file(self.request(name), knowledge_current=True)
                for _ in range(3):
                    executor.observe_unaddressed_entry(3, "target-unobserved")
                self.assertEqual(executor.state, HomeErrandState.STOPPED)
                self.assertTrue(executor.reason("ignored").startswith("home-errand:"))

    def test_request_has_exact_signature_quantity_origin_and_purpose(self):
        request = self.request("combat-weapon")
        self.assertEqual(
            (request.signature, request.quantity, request.origin, request.purpose),
            (("captured target", 23, 14), 1, "home-page", "combat-weapon"),
        )
