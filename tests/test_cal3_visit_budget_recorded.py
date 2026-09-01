from collections import Counter
import unittest

from historical_emit_fixture import CAL3_VISIT_BUDGET_DECISIONS, rows


class Cal3VisitBudgetRecordedTest(unittest.TestCase):
    def test_frozen_population_pins_ladder_and_visit_breakdown(self):
        population = list(rows(CAL3_VISIT_BUDGET_DECISIONS))
        self.assertEqual(len(population), 263)
        self.assertEqual(population[0]["time"], "2026-09-02T04:15:48+0900")
        self.assertEqual(population[-1]["time"], "2026-09-02T04:20:36+0900")

        visits = {}
        for row in population:
            visit = row.get("store_visit") or {}
            if visit.get("store_type") == 7:
                visits.setdefault(visit["opened_sequence"], row)
        purposes = Counter()
        for row in visits.values():
            visit = row["store_visit"]
            phase = row["equipment_optimization"]["calibration"]["phase"]
            if visit["owner"] == "equipment-transaction":
                purposes["equipment-work"] += 1
            elif phase == "deposit":
                purposes["calibration-deposit"] += 1
            else:
                purposes["calibration-restore"] += 1

        self.assertEqual(
            purposes,
            Counter({
                "calibration-deposit": 14,
                "calibration-restore": 26,
                "equipment-work": 6,
            }),
        )
        self.assertEqual(len(visits), 46)
        phases = {
            row["equipment_optimization"]["calibration"]["phase"]
            for row in population
            if "equipment_optimization" in row
        }
        self.assertEqual(
            phases, {"deposit", "strip", "capture", "restore-supplies", None}
        )
        final = population[-1]
        self.assertEqual(
            final["departure_block"]["town_ledger"]["store_visits"]["7"], 54
        )
        self.assertEqual(
            final["departure_block"]["town_claims"], ["calibration-restore"]
        )
        self.assertFalse(
            final["shop_selector"]["town_progress_invariant"]["claim_retired"]
        )


if __name__ == "__main__":
    unittest.main()
