"""Keep the standalone T2 evidence gates reachable from unittest discovery."""

import unittest

from decision_seed_telemetry_growth import measure as measure_growth
from store_visit_constructed_reproduction import measure as measure_reproduction
from store_visit_leak_matrix import measure as measure_leaks


class StoreVisitRound3GateTest(unittest.TestCase):
    def test_constructed_reproduction_accepts_both_foreign_visits(self):
        self.assertEqual(measure_reproduction(), [
            ("armour-swap", False), ("no-actionable", False),
        ])

    def test_leak_matrix_has_no_failures(self):
        result = measure_leaks()
        self.assertEqual(result["leaks"], [])
        self.assertEqual(result["transfer_violations"], [])

    def test_seed_growth_gate_runs_on_both_captures(self):
        for capture, expected in (("equip-swap", 400), ("no-actionable", 300)):
            with self.subTest(capture=capture):
                count, total, minimum, maximum = measure_growth(capture)
                self.assertEqual(count, expected)
                self.assertGreaterEqual(minimum, 0)
                self.assertGreaterEqual(maximum, minimum)
                self.assertGreaterEqual(total, 0)


if __name__ == "__main__":
    unittest.main()
