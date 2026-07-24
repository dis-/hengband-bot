import unittest

from hengbot.equipment_encounters import EncounterTarget, representative_encounters
from hengbot.warrior_optimization import optimization_encounters
from hengbot.monrace_knowledge import MonraceKnowledge


def encounter(race_id, level, weight, *, unique=False):
    flags = frozenset({"UNIQUE"}) if unique else frozenset()
    monster = MonraceKnowledge(
        max_hp=10,
        average_hp=10,
        speed=110,
        can_summon=False,
        friendly=False,
        level=level,
        spell_frequency=0,
        flags=flags,
    )
    return EncounterTarget(race_id, weight, monster)


class EquipmentEncounterSamplingTest(unittest.TestCase):

    def test_large_equipment_catalog_uses_bounded_encounter_sample(self):
        source = tuple(
            EncounterTarget(
                index,
                1 / 100,
                MonraceKnowledge(
                    max_hp=10,
                    speed=110,
                    can_summon=False,
                    friendly=False,
                    level=index % 20,
                    rarity=1,
                ),
            )
            for index in range(100)
        )

        self.assertEqual(
            len(optimization_encounters(source, catalog_size=48)),
            64,
        )
        self.assertIs(
            optimization_encounters(source, catalog_size=47),
            source,
        )

    def test_live_sized_catalog_uses_sample_before_optimizer_timeout(self):
        # Live 2026-07-24 regression: 40 owned equipment candidates at 18F
        # produced 403 ordinary encounters.  Evaluating 12,288 loadouts against
        # all 403 targets took 25.297s and failed closed, preventing a one-AC
        # shield upgrade.  This workload must be bounded even though the raw
        # catalog is below the legacy 48-item threshold.
        source = tuple(
            EncounterTarget(
                index,
                1 / 403,
                MonraceKnowledge(
                    max_hp=10,
                    speed=110,
                    can_summon=False,
                    friendly=False,
                    level=index % 19,
                    rarity=1,
                ),
            )
            for index in range(403)
        )

        sampled = optimization_encounters(source, catalog_size=40)

        self.assertEqual(len(sampled), 64)
        self.assertAlmostEqual(sum(item.weight for item in sampled), 1.0)

    def test_small_evaluation_workload_remains_exact(self):
        source = tuple(
            encounter(index, index % 20, 1 / 403)
            for index in range(403)
        )

        self.assertIs(
            optimization_encounters(source, catalog_size=29),
            source,
        )

    def test_excludes_uniques_and_preserves_normalized_weight(self):
        source = tuple(
            encounter(index, index % 40, 1.0 / 41, unique=index == 40)
            for index in range(41)
        )

        sampled = representative_encounters(source, max_count=12)

        self.assertEqual(len(sampled), 12)
        self.assertTrue(all("UNIQUE" not in item.knowledge.flags for item in sampled))
        self.assertAlmostEqual(sum(item.weight for item in sampled), 1.0)

    def test_keeps_each_populated_depth_band(self):
        source = (
            encounter(1, 5, 0.25),
            encounter(2, 15, 0.25),
            encounter(3, 25, 0.25),
            encounter(4, 35, 0.25),
            encounter(5, 35, 0.01),
        )

        sampled = representative_encounters(source, max_count=4)

        self.assertEqual({item.knowledge.level // 10 for item in sampled}, {0, 1, 2, 3})


if __name__ == "__main__":
    unittest.main()
