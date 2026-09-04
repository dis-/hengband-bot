from collections import Counter
import unittest

from historical_emit_fixture import PATTERN_A_OWNER_RETIRED_DECISIONS, rows


class PatternAOwnerRetiredRecordedTest(unittest.TestCase):
    def test_frozen_population_pins_arbiter_and_transaction_telemetry(self):
        population = list(rows(PATTERN_A_OWNER_RETIRED_DECISIONS))
        self.assertEqual(len(population), 272)
        self.assertEqual(
            [row["decision_sequence"] for row in population],
            list(range(1, 273)),
        )
        self.assertEqual(population[0]["time"], "2026-09-04T15:18:22+0900")
        self.assertEqual(population[-1]["time"], "2026-09-04T15:24:03+0900")

        self.assertTrue(all("arbiter" in row for row in population))
        self.assertTrue(all("retention_reservations" in row for row in population))
        self.assertTrue(all(
            "equipment_transaction" in row["equipment_optimization"]
            for row in population
        ))
        self.assertEqual(
            sum("home_route_refusal" in row for row in population), 0
        )
        self.assertEqual(
            sum("deposit_keep_conflict" in row for row in population), 17
        )

        reasons = Counter(row["reason"] for row in population)
        self.assertEqual(reasons["calibration:redressed"], 1)
        self.assertEqual(reasons["town:blocked:owner-retired"], 1)
        self.assertEqual(
            reasons[
                "town:blocked:equipment-transaction:"
                "equip-item-missing:pack:cf9cbd9f667b29b6:0"
            ],
            1,
        )

        missing = population[268]
        self.assertEqual(missing["decision_sequence"], 269)
        self.assertEqual(
            missing["equipment_optimization"]["failed_transaction_item_ids"],
            ["pack:bf3c5787bd6557a5:0", "pack:cf9cbd9f667b29b6:0"],
        )
        final = population[271]
        self.assertEqual(final["decision_sequence"], 272)
        self.assertEqual(final["turn"], 1_419_716)
        self.assertEqual(final["arbiter"]["owner"], "town-plan")
        self.assertEqual(final["arbiter"]["retirement_set"], [])
        self.assertFalse(final["arbiter"]["progress"])


if __name__ == "__main__":
    unittest.main()
