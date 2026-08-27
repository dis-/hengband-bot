"""Keep the standalone T3 purity matrix in unittest discovery."""

import unittest

from town_producer_purity_matrix import measure


class TownProducerPurityGateTest(unittest.TestCase):
    def test_candidate_town_producers_are_pure(self):
        result = measure()
        self.assertTrue(result["visit_injection_detected"])
        self.assertTrue(result["exemption_control"])
        self.assertEqual(
            result["results"]["_boxed_town_breakout_key"], "\x1b`n&."
        )
        self.assertEqual(result["impure"], [])

if __name__ == "__main__":
    unittest.main()
