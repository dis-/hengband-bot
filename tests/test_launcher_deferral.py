from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    STORE_TEMPLE,
    STORE_WEAPON,
    SV_BOW_LIGHT_XBOW,
    SV_LITE_LANTERN,
    SV_SCROLL_IDENTIFY,
    SV_STAFF_IDENTIFY,
    TVAL_BOW,
    TVAL_BOLT,
    TVAL_LITE,
    TVAL_SCROLL,
    TVAL_STAFF,
    Position,
    Snapshot,
    StoreItem,
    StoreState,
)
from hengbot.policy import HengbotPolicy
from hengbot.cli import (
    TOWN_BLOCKED_STOP_LIMIT,
    _advance_town_blocked_iteration,
)
from policy_fixtures import grid, item, player


class LauncherDeferralPinsTest(unittest.TestCase):
    def test_pin_vacuity_choose_key_releases_and_identifies_carried_launcher(self):
        launcher = item(
            "q", TVAL_BOW, SV_BOW_LIGHT_XBOW,
            name="light crossbow", known=False, aware=False,
            is_equipment=True, pseudo_feeling="good",
        )
        staff = item(
            "a", TVAL_STAFF, SV_STAFF_IDENTIFY,
            name="Staff of Identify", charges=18,
        )
        scroll = item(
            "i", TVAL_SCROLL, SV_SCROLL_IDENTIFY,
            name="Scroll of Identify",
        )
        snapshot = Snapshot(
            replace(
                player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                device_skill=16,
            ),
            {Position(10, 10): grid(10, 10)},
            [], inventory=[scroll, staff, launcher], town_flag=True,
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(launcher)
        policy._deferred_home_items.add(signature)
        policy._equipment_catalog.refresh_carried([launcher], [])
        self.assertTrue(any(
            owned.identification_incomplete
            for owned in policy._equipment_catalog.items
        ))

        key = policy.choose_key(snapshot)

        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertLess(
            policy._identify_staff_success_rate(snapshot),
            0.80,
        )
        self.assertEqual(key, "riq")
        self.assertEqual(policy.last_reason, "identify:normal")

        identified = replace(
            launcher, known=True, aware=True, fully_known=True, to_h=3, to_d=3,
        )
        equipped = replace(identified, slot="bow")
        armed = replace(snapshot, inventory=[staff], equipment=[equipped])
        policy._refresh_carried_equipment_catalog(armed)
        self.assertFalse(any(
            owned.identification_incomplete
            for owned in policy._equipment_catalog.items
        ))

        profile = SimpleNamespace(
            required_force={
                "launcher": {"ammo": "bolt", "equipped": True},
                "throwing_items": {"launcher_ammo": 45},
            },
            engagement_plan={},
        )
        status = policy._quest_carry_status(armed, profile.required_force)
        self.assertEqual(status["launcher"]["measured"], 1)
        bolts = StoreItem("b", "Bolts", 99, TVAL_BOLT, 0, price=3)
        weapon_store = replace(
            armed, store=StoreState(STORE_WEAPON, [bolts]),
        )
        self.assertIs(policy._quest_carry_purchase(weapon_store, profile), bolts)

    def test_home_twin_keeps_deferral_until_home_copy_disappears(self):
        launcher = item(
            "q", TVAL_BOW, SV_BOW_LIGHT_XBOW,
            name="light crossbow", known=False, aware=False,
            is_equipment=True, pseudo_feeling="good",
        )
        snapshot = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            inventory=[launcher], town_flag=True,
        )
        policy = HengbotPolicy()
        signature = policy._item_signature(launcher)
        policy._deferred_home_items.add(signature)
        policy._equipment_catalog.complete_home_scan([replace(launcher, slot="a")])

        policy._refresh_carried_equipment_catalog(snapshot)
        self.assertIn(signature, policy._deferred_home_items)

        policy._equipment_catalog.complete_home_scan([])
        policy._refresh_carried_equipment_catalog(snapshot)
        self.assertNotIn(signature, policy._deferred_home_items)

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
        pseudo_progress = replace(
            snapshot,
            equipment=[replace(lantern, pseudo_feeling="average")],
        )
        self.assertNotEqual(
            policy._town_progress_fingerprint(snapshot),
            policy._town_progress_fingerprint(pseudo_progress),
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
        captured_cycle = (
            ("town:blocked:repetition", "\x1b"),
            ("town:blocked:repetition", "1"),
            ("town:repetition-depart", "9"),
            ("store:entry-await-observation", ""),
        )
        for decision in range(35):
            snapshot = replace(
                base,
                equipment=[replace(
                    lantern, name=f"Lantern ({5288 - decision} turns)"
                )],
            )
            policy.last_reason, key = captured_cycle[decision % 4]
            streak, previous = _advance_town_blocked_iteration(
                policy, snapshot, streak, previous, key=key
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

        corridor_origin = Position(10, 10)
        corridor_door = Position(10, 11)
        corridor_target = Position(10, 12)
        sole_path = Snapshot(
            player(corridor_origin.y, corridor_origin.x),
            {
                corridor_origin: grid(corridor_origin.y, corridor_origin.x),
                corridor_door: replace(
                    grid(corridor_door.y, corridor_door.x),
                    store_number=STORE_TEMPLE,
                ),
                corridor_target: replace(
                    grid(corridor_target.y, corridor_target.x),
                    has_down_stairs=True,
                ),
            },
            [], town_flag=True,
        )
        corridor = HengbotPolicy()
        corridor._build_grid_index(sole_path)
        with patch.object(corridor, "_descent_is_blocked", return_value=False):
            self.assertEqual(corridor._descent_step(sole_path), corridor_door)


if __name__ == "__main__":
    unittest.main()
