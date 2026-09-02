from collections import Counter
import unittest

from historical_emit_fixture import IDW_BLOCK_DECISIONS, rows


class IdwBlockRecordedTest(unittest.TestCase):
    def test_frozen_population_pins_identification_and_weight_onset(self):
        population = list(rows(IDW_BLOCK_DECISIONS))
        self.assertEqual(len(population), 2_088)
        self.assertEqual(population[0]["time"], "2026-09-02T09:47:25+0900")
        self.assertEqual(population[-1]["time"], "2026-09-02T09:59:06+0900")

        identification = [
            row for row in population if "identify" in row.get("reason", "").lower()
        ]
        self.assertEqual(identification, [])

        incomplete = Counter()
        for row in population:
            for detail in row.get("equipment_optimization", {}).get(
                "incomplete_item_details", []
            ):
                incomplete[(detail["id"], detail["origin"], detail["tval"])] += 1
        self.assertEqual(
            incomplete,
            Counter({
                ("pack:9eb1d623115481d7:0", "pack", 23): 68,
                ("pack:cd3cc5674d2ab115:0", "pack", 36): 69,
                ("pack:e9f11d0232a0b1c5:0", "pack", 36): 222,
            }),
        )

        overweight = [
            (index, row)
            for index, row in enumerate(population)
            if row.get("departure_block", {}).get("values", {}).get(
                "inventory_weight_ready"
            ) is False
        ]
        self.assertEqual(len(overweight), 24)
        self.assertEqual(overweight[0][0], 2_064)
        self.assertEqual(overweight[0][1]["decision_sequence"], 2_041)
        self.assertEqual(overweight[0][1]["time"], "2026-09-02T09:58:13+0900")
        self.assertEqual(
            Counter(row["reason"] for _, row in overweight),
            Counter({"town:blocked:equipment-incomplete-catalog": 24}),
        )
        before = population[2_063]
        self.assertEqual(before["reason"], "shop:one-shot-in-flight")
        self.assertTrue(before["departure_block"]["values"]["inventory_weight_ready"])


if __name__ == "__main__":
    unittest.main()
