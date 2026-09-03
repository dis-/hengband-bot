from collections import Counter
import unittest

from historical_emit_fixture import HOME_ROUTE_STALL_DECISIONS, rows


class HomeRouteStallRecordedTest(unittest.TestCase):
    def test_frozen_population_pins_withdrawals_route_diagnostics_and_terminal(self):
        population = list(rows(HOME_ROUTE_STALL_DECISIONS))
        self.assertEqual(len(population), 55)
        self.assertEqual(population[0]["time"], "2026-09-04T03:40:30+0900")
        self.assertEqual(population[-1]["time"], "2026-09-04T03:41:25+0900")
        reasons = Counter(row.get("reason") for row in population)
        self.assertEqual(reasons["home:atomic-withdraw"], 2)
        self.assertEqual(reasons["equipment-transaction:home-route-unavailable"], 3)
        self.assertEqual(reasons["equipment-transaction:abandon-blocked"], 3)
        self.assertEqual(reasons["equipment-transaction:home-route-repeat-terminal"], 1)
        refusals = [
            row for row in population
            if row.get("reason") == "equipment-transaction:home-route-unavailable"
        ]
        self.assertEqual([row["decision_sequence"] for row in refusals], [32, 41, 49])
        self.assertTrue(all("home_route_projection" in row["equipment_optimization"] for row in refusals))
        self.assertTrue(all("equipment_transaction" in row["equipment_optimization"] for row in refusals))
        self.assertTrue(any("home_visit_report" in row for row in population))


if __name__ == "__main__":
    unittest.main()
