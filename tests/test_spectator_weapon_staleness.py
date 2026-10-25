"""Weapon-only viewer freshness through character dispatch and snapshot parsing."""
import tests  # noqa: F401

import copy
import json
import pickle
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests import test_spectator as replay
from tests.test_home_light_alternation import _fresh_policy
from tests.test_spectator_melee_expected import dispatch, write


class WeaponStalenessTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "spectate.json"
        self.policy = _fresh_policy(self.root)
        self.raw = json.loads(replay._recorded_lines(1)[0])
        self.raw["equipment"] = [
            {"slot": "main_hand", "name": "Long Sword (2d5) (+7,+8)"},
            {"slot": "sub_hand", "name": "Dagger (1d4) (+2,+3)"},
            {"slot": "light", "name": "Lantern (2609 turns)"},
            {"slot": "body", "name": "Dragon Scale Mail"},
        ]
        self.response = dispatch(self.policy, self.raw, [80, 42])

    def assert_expected(self, policy, stale):
        written = write(self.path, policy, self.raw)
        self.assertEqual(written["melee_expected"], {
            "per_round": [80, 42], "total": 122, "stale": stale,
            "turn": self.response["turn"],
        })
        self.assertEqual(written["equipment"], self.raw["equipment"])

    def test_light_fuel_and_armor_charging_do_not_age_damage(self):
        self.raw["turn"] += 1
        self.raw["equipment"][2]["name"] = "Lantern (2608 turns)"
        self.raw["equipment"][3]["name"] += " (charging)"
        self.assert_expected(self.policy, False)
        # The real producer still retains all equipment for old checkpoint compatibility.
        self.assertEqual(self.policy._spectator_melee_expected["equipment"], sorted(
            (row["slot"], row["name"]) for row in self.response["equipment"]))

    def test_either_weapon_swap_ages_damage_until_character_refresh(self):
        for index in (0, 1):
            with self.subTest(slot=self.raw["equipment"][index]["slot"]):
                self.raw = copy.deepcopy(self.response)
                self.raw["equipment"][index]["name"] += " upgraded"
                self.assert_expected(self.policy, True)
        dispatch(self.policy, self.raw, [90, 43])
        self.assertEqual(write(self.path, self.policy, self.raw)["melee_expected"], {
            "per_round": [90, 43], "total": 133, "stale": False,
            "turn": self.raw["turn"],
        })

    def test_weapon_removal_and_addition_age_damage(self):
        self.raw["equipment"].pop(1)
        self.assert_expected(self.policy, True)
        dispatch(self.policy, self.raw, [80, 42])
        self.raw["equipment"].append({"slot": "sub_hand", "name": "New Dagger"})
        self.assert_expected(self.policy, True)

    def test_full_equipment_checkpoint_restores_with_weapon_only_comparison(self):
        restored = pickle.loads(pickle.dumps(self.policy))
        self.raw["equipment"][2]["name"] = "Lantern (2608 turns)"
        self.assert_expected(restored, False)
        self.raw["equipment"][0]["name"] = "Different Sword"
        self.assert_expected(restored, True)

    def test_pre_cache_checkpoint_still_omits_expected_damage(self):
        del self.policy._spectator_melee_expected
        restored = pickle.loads(pickle.dumps(self.policy))
        self.assertNotIn("melee_expected", write(self.path, restored, self.raw))
        dispatch(restored, self.raw, [80, 42])
        self.assert_expected(restored, False)


if __name__ == "__main__":
    unittest.main()
