"""Round 12: town boards must stop before dungeon-only action bodies."""
import tests  # noqa: F401

from dataclasses import replace
import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.model import DUNGEON_YEEK_CAVE, TVAL_DIGGING, SV_DIGGING_SHOVEL
from hengbot.policy_constants import PACK_CAPACITY, STUCK_ESCAPE_LIMIT
from policy_fixtures import item
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


class UnreachableMonsters:
    def __iter__(self):
        raise AssertionError("town board reached dungeon hunt body")


class DungeonOnlyGuardTest(unittest.TestCase):
    def test_constructed_town_boards_never_reach_dungeon_action_bodies(self):
        # One behavioral census. Each premise opens every branch before the
        # depth/town guard; the first action-side collaborator must stay unused.
        cases = (
            ("_conquest_loot_key", "_current_floor_item_key"),
            ("_unprofitable_unique_disengage_key", "_floor_navigation_exit_locked"),
            ("_pack_pressure_identify_key", "_identify_carried_item_key"),
            ("_fundraising_combat_equipment_key", "_equipped_digging_tool"),
            ("_return_to_town_key#1", "_return_exit_locked"),
            ("_return_to_town_key#2", "_return_exit_locked"),
            ("_return_to_town_key#3", "_return_exit_locked"),
            ("_esp_threat_hunt_key", None),
        )
        for rung, forbidden in cases:
            with self.subTest(rung=rung):
                snap = board()
                if rung == "_fundraising_combat_equipment_key":
                    snap = replace(snap, floor_key=(DUNGEON_YEEK_CAVE, 0, 0))
                if rung == "_pack_pressure_identify_key":
                    snap = replace(snap, inventory=[None] * PACK_CAPACITY)
                policy = policy_on(snap)
                if rung == "_esp_threat_hunt_key":
                    snap = replace(snap, detected_monsters=UnreachableMonsters())
                policy._victory_loot_dungeon = snap.floor_key[0]
                policy._fundraising_mode = "mine"
                policy._esp_threat_hunt = {"floor": snap.floor_key, "indices": {1}}
                name = rung.split("#")[0]
                args = (snap, []) if name in {
                    "_return_to_town_key", "_fundraising_combat_equipment_key",
                    "_unprofitable_unique_disengage_key", "_esp_threat_hunt_key",
                } else (snap,)
                if forbidden is None:
                    self.assertIsNone(getattr(policy, name)(*args))
                    self.assertIsNone(policy._esp_threat_hunt)
                else:
                    with patch.object(policy, forbidden, side_effect=AssertionError(
                            "town board reached dungeon action body")) as body:
                        self.assertIsNone(getattr(policy, name)(*args))
                    body.assert_not_called()
                decl = tt.TERMINALS[rung]
                self.assertEqual(decl.mode, tt.NO_REFUSAL)
                self.assertTrue(decl.no_refusal_reason.startswith(
                    "dungeon-only: not a town errand; src/hengbot/"))
                self.assertNotIn(rung, tt.SHADOW_RUNGS)

        # This rung has its guard at the only entry call site, not in the
        # reusable equipment serializer. Keep all other breakout premises true.
        snap = replace(board(), inventory=[item(
            "a", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)])
        policy = policy_on(snap)
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        policy._breakout_dig_floor = snap.floor_key
        seen = []

        def observe_entry(rung, call, **kwargs):
            seen.append(rung)
            if rung == "_wield_digging_tool_key":
                self.fail("town board reached the dungeon breakout wield body")
            return "dig" if rung == "_dig_to_known_downstairs_key" else None

        with patch.object(policy, "_town_producer_entry", side_effect=observe_entry), \
                patch.object(policy, "_recall_shortage_opening_exempt", return_value=True):
            self.assertIsNone(policy._decide(snap))
        self.assertIn("_dig_to_known_downstairs_key", seen)
        self.assertEqual(seen[-1], "idle-fallback")
        self.assertNotIn("_wield_digging_tool_key", seen)
        self.assertEqual(tt.TERMINALS["_wield_digging_tool_key"].mode, tt.NO_REFUSAL)


if __name__ == "__main__":
    unittest.main()

