"""Round 12: town boards must stop before dungeon-only action bodies."""
import tests  # noqa: F401

from dataclasses import replace
import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.model import DUNGEON_YEEK_CAVE, TVAL_DIGGING, SV_DIGGING_SHOVEL
from hengbot.policy_constants import STUCK_ESCAPE_LIMIT
from policy_fixtures import item
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


class UnreachableBodyData:
    def __iter__(self):
        raise AssertionError("town board reached dungeon action data")

    def __len__(self):
        raise AssertionError("town board reached dungeon action data")

    def __getitem__(self, index):
        raise AssertionError("town board reached dungeon action data")


def breakout_town_policy(snap):
    """Data premise: a town floor with an already armed breakout clock.

    No behavior is replaced here. In particular, the real depth guard must
    reject even this stale latch before a digging-tool command is selected.
    """
    policy = policy_on(snap)
    policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
    policy._breakout_dig_floor = snap.floor_key
    return policy


class DungeonOnlyGuardTest(unittest.TestCase):
    def test_constructed_town_boards_never_reach_dungeon_action_bodies(self):
        # One behavioral census. Each premise opens every branch before the
        # depth/town guard; the first action-side collaborator must stay unused.
        cases = (
            "_conquest_loot_key", "_unprofitable_unique_disengage_key",
            "_pack_pressure_identify_key", "_fundraising_combat_equipment_key",
            "_return_to_town_key#1", "_return_to_town_key#2", "_return_to_town_key#3",
            "_esp_threat_hunt_key",
        )
        for rung in cases:
            with self.subTest(rung=rung):
                snap = board()
                if rung == "_fundraising_combat_equipment_key":
                    snap = replace(snap, floor_key=(DUNGEON_YEEK_CAVE, 0, 0))
                policy = policy_on(snap)
                policy._victory_loot_dungeon = snap.floor_key[0]
                policy._fundraising_mode = "mine"
                policy._esp_threat_hunt = {"floor": snap.floor_key, "indices": {1}}
                # Poison the first board data after the guard rather than
                # replacing the producer's collaborators with a mock wall.
                if rung in {"_conquest_loot_key", "_pack_pressure_identify_key"}:
                    snap = replace(snap, inventory=UnreachableBodyData())
                elif rung == "_unprofitable_unique_disengage_key":
                    snap = replace(snap, floor_key=UnreachableBodyData())
                elif rung == "_fundraising_combat_equipment_key":
                    snap = replace(snap, equipment=UnreachableBodyData())
                elif rung == "_esp_threat_hunt_key":
                    snap = replace(snap, detected_monsters=UnreachableBodyData())
                name = rung.split("#")[0]
                args = (snap, []) if name in {
                    "_return_to_town_key", "_fundraising_combat_equipment_key",
                    "_unprofitable_unique_disengage_key", "_esp_threat_hunt_key",
                } else (snap,)
                if name == "_return_to_town_key":
                    with patch.object(policy, "_return_exit_locked", side_effect=AssertionError(
                            "town board reached dungeon return body")) as body:
                        self.assertIsNone(getattr(policy, name)(*args))
                    body.assert_not_called()
                else:
                    self.assertIsNone(getattr(policy, name)(*args))
                if name == "_esp_threat_hunt_key":
                    self.assertIsNone(policy._esp_threat_hunt)
                decl = tt.TERMINALS[rung]
                self.assertEqual(decl.mode, tt.NO_REFUSAL)
                self.assertTrue(decl.no_refusal_reason.startswith(
                    "dungeon-only: not a town errand; src/hengbot/"))
                self.assertNotIn(rung, tt.SHADOW_RUNGS)

        # This rung has its guard at the only entry call site, not in the
        # reusable equipment serializer. Keep all other breakout premises true.
        snap = replace(board(), inventory=[item(
            "a", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)])
        policy = breakout_town_policy(snap)
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

