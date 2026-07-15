import unittest

from hengbot.equipment_encounters import melee_multiplier, normal_encounters
from hengbot.monrace_knowledge import MonraceKnowledge


def monster(*, level=1, rarity=1, flags=()):
    return MonraceKnowledge(
        max_hp=10,
        speed=110,
        can_summon=False,
        friendly=False,
        level=level,
        rarity=rarity,
        flags=frozenset(flags),
    )


class EquipmentEncountersTest(unittest.TestCase):
    def test_normal_weights_match_integer_100_over_rarity(self):
        encounters = normal_encounters(
            {1: monster(rarity=1), 2: monster(rarity=3)}, 1
        )
        weights = {entry.race_id: entry.weight for entry in encounters}
        self.assertAlmostEqual(weights[1], 100 / 133)
        self.assertAlmostEqual(weights[2], 33 / 133)

    def test_excludes_over_depth_quest_and_wilderness_only_monsters(self):
        encounters = normal_encounters(
            {
                1: monster(level=2),
                2: monster(flags={"QUESTOR"}),
                3: monster(flags={"WILD_ONLY"}),
                4: monster(),
            },
            1,
        )
        self.assertEqual([entry.race_id for entry in encounters], [4])

    def test_slay_uses_strongest_applicable_multiplier(self):
        target = monster(flags={"EVIL", "ORC"})
        self.assertEqual(melee_multiplier(frozenset({17, 20}), target), 30)

    def test_brand_is_blocked_by_immunity_and_uses_vulnerability(self):
        immune = monster(flags={"IM_FIRE"})
        vulnerable = monster(flags={"HURT_FIRE"})
        self.assertEqual(melee_multiplier(frozenset({30}), immune), 10)
        self.assertEqual(melee_multiplier(frozenset({30}), vulnerable), 50)


if __name__ == "__main__":
    unittest.main()
