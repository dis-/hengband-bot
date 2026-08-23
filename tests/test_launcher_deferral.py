from dataclasses import replace
from unittest.mock import patch
import unittest

from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    STORE_TEMPLE,
    SV_BOW_LIGHT_XBOW,
    SV_LITE_LANTERN,
    SV_STAFF_IDENTIFY,
    TVAL_BOW,
    TVAL_LITE,
    TVAL_STAFF,
    Position,
    Snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.cli import (
    TOWN_BLOCKED_STOP_LIMIT,
    _advance_town_blocked_iteration,
)
from policy_fixtures import grid, item, player


class LauncherDeferralPinsTest(unittest.TestCase):
    def test_pin_vacuity_carried_pack_launcher_releases_home_deferral(self):
        launcher = item(
            "q", TVAL_BOW, SV_BOW_LIGHT_XBOW,
            name="light crossbow", known=False, aware=False,
            is_equipment=True, pseudo_feeling="good",
        )
        staff = item(
            "a", TVAL_STAFF, SV_STAFF_IDENTIFY,
            name="Staff of Identify", charges=18,
        )
        snapshot = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [], inventory=[staff, launcher], town_flag=True,
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(launcher)
        policy._deferred_home_items.add(signature)

        policy._refresh_carried_equipment_catalog(snapshot)
        with patch.object(policy, "_identify_staff_success_rate", return_value=100):
            key = policy._town_item_processing_key(snapshot)

        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertEqual(key, "uaq")
        self.assertEqual(policy.last_reason, "identify:normal")

    def test_pin_vacuity_town_fingerprint_ignores_only_lantern_name(self):
        lantern = item(
            "f", TVAL_LITE, SV_LITE_LANTERN,
            name="Lantern (5288 turns)", is_equipment=True, fuel=5288,
        )
        snapshot = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            equipment=[lantern], town_flag=True,
        )
        later = replace(
            snapshot,
            equipment=[replace(lantern, name="Lantern (5285 turns)", fuel=5285)],
        )
        policy = HengbotPolicy()

        self.assertEqual(
            policy._town_progress_fingerprint(snapshot),
            policy._town_progress_fingerprint(later),
        )
        self.assertNotEqual(
            policy._emission_state(snapshot), policy._emission_state(later)
        )
        self.assertNotEqual(
            policy._owner_progress_core(snapshot),
            policy._owner_progress_core(later),
        )

    def test_pin_vacuity_captured_four_decision_cycle_reaches_cli_fuse(self):
        lantern = item(
            "f", TVAL_LITE, SV_LITE_LANTERN,
            name="Lantern (5288 turns)", is_equipment=True,
        )
        base = Snapshot(
            player(32, 76), {Position(32, 76): grid(32, 76)}, [],
            equipment=[lantern], town_flag=True,
        )
        policy = HengbotPolicy()
        streak = 0
        previous = None
        for decision in range(35):
            snapshot = replace(
                base,
                equipment=[replace(
                    lantern, name=f"Lantern ({5288 - decision} turns)"
                )],
            )
            policy.last_reason = (
                "town:blocked:repetition",
                "town:blocked:equipment-departure-incomplete",
                "town:blocked:quest-ranged-kit",
                "town:blocked:departure-route",
            )[decision % 4]
            streak, previous = _advance_town_blocked_iteration(
                policy, snapshot, streak, previous, key=("\x1b", "2", "8", "9")[decision % 4]
            )
            if streak >= TOWN_BLOCKED_STOP_LIMIT:
                break

        self.assertGreaterEqual(streak, TOWN_BLOCKED_STOP_LIMIT)

    def test_pin_vacuity_outpost_departure_avoids_temple_shop_targets_it(self):
        origin = Position(32, 76)
        target = Position(31, 150)
        temple = Position(31, 77)
        grids = {
            Position(y, x): grid(y, x)
            for y in (31, 32)
            for x in range(76, 151)
        }
        grids[temple] = replace(grids[temple], store_number=STORE_TEMPLE)
        grids[target] = replace(grids[target], has_down_stairs=True)
        snapshot = Snapshot(
            player(origin.y, origin.x), grids, [], town_flag=True,
        )
        policy = HengbotPolicy()
        policy._build_grid_index(snapshot)

        with patch.object(policy, "_descent_is_blocked", return_value=False):
            step = policy._descent_step(snapshot)

        self.assertEqual(policy._direction_key(origin, step), "6")
        self.assertIsNone(policy._store_visit)
        self.assertEqual(
            policy._nearest_goal_step(
                snapshot, lambda candidate: candidate.store_number == STORE_TEMPLE
            ),
            temple,
        )


if __name__ == "__main__":
    unittest.main()
