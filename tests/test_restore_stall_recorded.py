from collections import Counter
import unittest

from historical_emit_fixture import RESTORE_STALL_DECISIONS, rows


class RestoreStallRecordedTest(unittest.TestCase):
    def test_frozen_population_pins_restore_stall(self):
        population = list(rows(RESTORE_STALL_DECISIONS))
        self.assertEqual(len(population), 4198)
        self.assertEqual(population[0]["time"], "2026-09-03T19:03:30+0900")
        self.assertEqual(population[-1]["time"], "2026-09-03T19:19:38+0900")

        reasons = Counter(row.get("reason") for row in population)
        self.assertEqual(
            reasons[
                "town-progress-invariant:defect:home-visit:withdraw-not-authorized"
                "=>town-progress-invariant:approach"
            ],
            1,
        )
        tail = {
            row.get("decision_sequence"): row
            for row in population
            if 4170 <= (row.get("decision_sequence") or -1) <= 4179
        }
        self.assertEqual(
            {
                row["equipment_optimization"]["calibration"]["phase"]
                for row in tail.values()
            },
            {"restore-supplies"},
        )
        self.assertEqual(tail[4179]["reason"], "town:blocked:owner-retired")
        self.assertEqual(tail[4179]["inventory"], {"used": 1, "free": 22})
        requirements = {
            requirement["item"]: requirement
            for requirement in tail[4178]["procurement_requirements"]
        }
        self.assertEqual(requirements["Word of Recall scrolls"]["current"], 0)
        self.assertEqual(requirements["Identify staff charges"]["missing"], 20)


if __name__ == "__main__":
    unittest.main()
