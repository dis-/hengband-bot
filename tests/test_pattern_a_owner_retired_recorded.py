from collections import Counter
import unittest

from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit
from historical_emit_fixture import PATTERN_A_OWNER_RETIRED_DECISIONS, rows


class PatternAOwnerRetiredRecordedTest(unittest.TestCase):
    @staticmethod
    def _durable_signature(row):
        return (
            row["player"]["gold"],
            row["inventory"]["used"],
            row["inventory"]["free"],
        )

    @staticmethod
    def _transfer(arbiter, source, target, sequence, vector):
        arbiter.store_visit = StoreVisit(
            owner="recorded-owner",
            purpose="recorded-transfer",
            store_type=source,
        )

        def close_visit(_outcome):
            arbiter.store_visit = None

        arbiter.acquire_store_visit(
            store_type=target,
            owner="recorded-owner",
            purpose="recorded-transfer",
            opened_sequence=sequence,
            close_visit=close_visit,
        )
        return arbiter.observe(
            in_town=True,
            reason="store:entry-await-observation",
            progress_vector=vector,
        )

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

    def test_recorded_repeated_transfer_is_released_by_durable_progress(self):
        population = list(rows(PATTERN_A_OWNER_RETIRED_DECISIONS))
        repeated = [(7, 5, 22, 23), (7, 5, 270, 271)]
        for source, target, index, sequence in repeated:
            self.assertEqual(population[index - 1]["store_visit"]["store_type"], source)
            self.assertTrue(population[index]["acquire_store_visit_called"])
            self.assertEqual(population[index]["requested_store"], target)
            self.assertEqual(population[index]["decision_sequence"], sequence)
        self.assertEqual(repeated[1][2] - repeated[0][2], 248)

        before = population[repeated[0][2]]
        after = population[repeated[1][2]]
        before_vector = self._durable_signature(before)
        after_vector = self._durable_signature(after)
        self.assertEqual(before_vector, (12_452, 1, 22))
        self.assertEqual(after_vector, (6_549, 0, 23))

        arbiter = HengbotPolicy()._town_turn_arbiter
        self._transfer(arbiter, 7, 5, 23, before_vector)
        # Re-observe the same owner after the recorded gold/inventory delta.
        # This is an actual counterfactual vector change, not elapsed time.
        arbiter.observe(
            in_town=True,
            reason="store:entry-await-observation",
            progress_vector=after_vector,
        )
        self._transfer(arbiter, 5, 7, 270, after_vector)
        row = self._transfer(arbiter, 7, 5, 271, after_vector)

        self.assertFalse(arbiter._transfer_exhausted)
        self.assertNotEqual(row.get("transfer_exhausted"), True)
        self.assertTrue(arbiter.may_select("shop:travel", after_vector))

    def test_immediate_repeated_transfer_still_exhausts_guard(self):
        arbiter = HengbotPolicy()._town_turn_arbiter
        unchanged = (12_452, 1, 22)

        self._transfer(arbiter, 7, 5, 23, unchanged)
        self._transfer(arbiter, 5, 7, 24, unchanged)
        row = self._transfer(arbiter, 7, 5, 25, unchanged)

        self.assertTrue(arbiter._transfer_exhausted)
        self.assertFalse(arbiter.may_select("shop:travel", unchanged))
        self.assertTrue(row["transfer_exhausted"])
        self.assertEqual(row["transfer_pair"], [7, 5])
        self.assertEqual(row["transfer_count"], 2)


if __name__ == "__main__":
    unittest.main()
