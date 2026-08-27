"""Keep the standalone T3 purity matrix in unittest discovery."""

import unittest

from town_producer_purity_matrix import (
    measure,
    probe_sweep,
    producer_equivalence,
)


class TownProducerPurityGateTest(unittest.TestCase):
    def test_candidate_town_producers_are_pure(self):
        result = measure()
        self.assertTrue(result["visit_injection_detected"])
        self.assertTrue(result["exemption_control"])
        self.assertEqual(
            result["results"]["_boxed_town_breakout_key"], "\x1b`n&."
        )
        self.assertEqual(result["impure"], [])

        sweep = probe_sweep()
        self.assertEqual(
            sweep,
            {
                "equip-swap": {"calls": 145, "impure_calls": 0},
                "no-actionable": {"calls": 226, "impure_calls": 0},
            },
        )

        equivalence, missing_mutations = producer_equivalence()
        self.assertEqual(missing_mutations, set())
        self.assertEqual(
            equivalence,
            {
                "equip-swap": {
                    "unconstrained": 145,
                    "posted_general": 145,
                    "total": 145,
                },
                "no-actionable": {
                    "unconstrained": 226,
                    "posted_general": 226,
                    "total": 226,
                },
            },
        )

if __name__ == "__main__":
    unittest.main()
