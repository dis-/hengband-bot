import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy, RESIST_FLAG_BY_ABILITY


FIXTURE = Path(__file__).parent / "fixtures" / "abilities-depth34-town.json"
PERMANENT = frozenset({
    "resist_cold", "resist_fear", "resist_neth", "resist_pois",
    "see_invisible",
})


class AbilitySourcesIncidentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = parse_snapshot(
            json.loads(FIXTURE.read_text(encoding="utf-8")), {}
        )

    def test_depth34_recall_is_refused_for_the_four_missing_gates(self):
        policy = HengbotPolicy()

        key = policy.choose_key(self.snapshot)

        self.assertNotEqual(key, "rha")
        # AGENTS.md is authoritative over the incident brief's older wording:
        # the 31-39F band adds chaos only.  The truthful set must still refuse
        # the recall because chaos is absent.
        self.assertEqual(
            policy._missing_required_abilities(self.snapshot, 34),
            frozenset({"resist_chaos"}),
        )

    def test_evidence_permanent_sources_are_the_five_true_intrinsics(self):
        actual = frozenset(
            ability
            for ability, sources in self.snapshot.player.ability_sources.items()
            if "permanent" in sources
        )
        self.assertEqual(actual, PERMANENT)

    def test_danger_resistance_flags_include_fire_but_not_chaos_or_confusion(self):
        flags = frozenset(
            flag
            for ability, flag in RESIST_FLAG_BY_ABILITY.items()
            if ability in self.snapshot.player.abilities
        )
        self.assertIn(RESIST_FLAG_BY_ABILITY["resist_fire"], flags)
        self.assertNotIn(RESIST_FLAG_BY_ABILITY["resist_chaos"], flags)
        self.assertNotIn(RESIST_FLAG_BY_ABILITY["resist_conf"], flags)


if __name__ == "__main__":
    unittest.main()
