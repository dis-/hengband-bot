"""Remaining town dispatchers select the operation's own per-board admission."""
import tests  # noqa: F401

from dataclasses import replace
import pickle
import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.item_reservation import ReservationVerdict
from hengbot.model import DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, TVAL_FOOD
from hengbot.policy_constants import FOOD_MIN_SVAL, HEAVY_CURSE_TAG, WAIT_KEY
from hengbot.policy_state import normalize_policy_state
from policy_fixtures import item
import test_policy_town as town_fixtures
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


def blocked_recall():
    fixture = town_fixtures.TownCycleDetectorTest()
    snap = replace(fixture._town_snap(),
        inventory=[item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10),
                   item("f", TVAL_FOOD, FOOD_MIN_SVAL, count=15)],
        entered_dungeon_ids=(DUNGEON_YEEK_CAVE, DUNGEON_ANGBAND),
        recall_dungeon_id=DUNGEON_ANGBAND, angband_recall_unlocked=True)
    policy = policy_on(snap)
    town_fixtures.set_completed_equipment_optimization(policy)
    policy._floor_key = (0, 0, 0)
    policy._town_blocked_reason = "repetition"
    policy._target_dungeon_id = DUNGEON_ANGBAND
    return policy, snap


class RemainingTownAdmissionTest(unittest.TestCase):
    def test_gear_reservation_refusal_keeps_the_original_no_mutation_result(self):
        for operation in ("wield", "takeoff"):
            outcomes = []
            for mode in (tt.SHADOW, tt.ENFORCE):
                target = item("a" if operation == "wield" else "main_hand", 23, 1,
                    name="observed sword", known=True, fully_known=True, is_equipment=True)
                snap = replace(board(), inventory=[target] if operation == "wield" else [],
                               equipment=[target] if operation == "takeoff" else [])
                policy = policy_on(snap)
                with patch.dict(tt.TERMINALS, {"_town_restore_weapon_key":
                        tt.TERMINALS["_town_restore_weapon_key"]._replace(mode=mode)}), \
                        patch("hengbot.item_reservation.item_reserved_by_other",
                              return_value=ReservationVerdict(operation, "home-visit")):
                    key = (policy._equipment_wield(snap, "combat-loadout", target, "main_hand")
                           if operation == "wield" else policy._equipment_takeoff(snap, "combat-loadout", "a"))
                self.assertIsNone(key)
                self.assertIsNone(policy._terminal_item_command)
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["rung"], "_town_restore_weapon_key")
                self.assertEqual(row["codes"], ["item-command-reserved"])
                outcomes.append((key, policy.last_reason, repr(policy._equipment_mutation_result),
                                 repr(policy._decision_offer_buffer())))
            self.assertEqual(outcomes[0], outcomes[1])

    def test_unreserved_wield_keeps_the_real_mutation_key(self):
        outcomes = []
        for mode in (tt.SHADOW, tt.ENFORCE):
            target = item("a", 23, 1, name="observed sword", known=True,
                          fully_known=True, is_equipment=True)
            snap = replace(board(), inventory=[target])
            policy = policy_on(snap)
            with patch.dict(tt.TERMINALS, {"_town_restore_weapon_key":
                    tt.TERMINALS["_town_restore_weapon_key"]._replace(mode=mode)}):
                key = policy._equipment_wield(snap, "combat-loadout", target, "main_hand")
            self.assertIsNotNone(key)
            self.assertTrue(key.startswith("w"))
            self.assertIsNone(policy._terminal_item_command)
            outcomes.append((key, policy.last_reason, repr(policy._equipment_mutation_result)))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_every_heavy_curse_inscription_branch_uses_the_selected_item_verdict(self):
        for branch in ("clear", "clean", "mark"):
            outcomes = []
            for mode in (tt.SHADOW, tt.ENFORCE):
                target = item("main_hand", 23, 1, name="observed sword", known=True,
                    fully_known=True, is_equipment=True, is_cursed=branch == "mark",
                    inscription="" if branch == "mark" else HEAVY_CURSE_TAG + (" keep" if branch == "clean" else ""))
                snap = replace(board(), equipment=[target])
                policy = policy_on(snap)
                signature = policy._item_signature(target)
                policy._heavy_cursed_items.add(signature)
                if branch == "mark":
                    policy._heavy_curse_inscription_pending = signature
                with patch.dict(tt.TERMINALS, {"_heavy_curse_inscription_key":
                        tt.TERMINALS["_heavy_curse_inscription_key"]._replace(mode=mode)}), \
                        patch("hengbot.item_reservation.item_reserved_by_other",
                              return_value=ReservationVerdict("inscribe", "home-visit")):
                    key = policy._heavy_curse_inscription_key(snap)
                self.assertIsNone(key)
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["codes"], ["item-command-reserved"])
                outcomes.append((key, policy.last_reason, policy._heavy_curse_inscription_pending,
                                 policy._heavy_cursed_items, repr(policy._decision_offer_buffer())))
            self.assertEqual(outcomes[0], outcomes[1])

    def test_blocked_recall_is_admitted_before_sanction_and_read(self):
        for mode in (tt.SHADOW, tt.ENFORCE):
            policy, snap = blocked_recall()
            with patch.dict(tt.TERMINALS, {"_town_blocked_key":
                    tt.TERMINALS["_town_blocked_key"]._replace(mode=mode)}), \
                    patch.object(tt, "gather_blocked_recall", return_value=tt.DepartureMaterial(("hp_full",))), \
                    patch.object(policy, "_descent_step", return_value=None), \
                    patch.object(policy, "_recall_destination_safe", return_value=True), \
                    patch.object(policy, "_read_key", return_value="read") as read:
                key = policy._town_blocked_key(snap)
            self.assertEqual(key, "read" if mode == tt.SHADOW else WAIT_KEY)
            self.assertEqual(read.call_count, int(mode == tt.SHADOW))
            self.assertEqual(policy._emergency_recall_sanctioned, mode == tt.SHADOW)
            self.assertIsNone(policy._terminal_blocked_recall)
            row, = policy._decision_terminal_admissions
            self.assertEqual(row["codes"], ["departure:hp_full"])

    def test_blocked_recall_material_follows_its_own_branch_not_optional_supplies(self):
        policy, snap = blocked_recall()
        policy._terminal_blocked_recall = (DUNGEON_ANGBAND, False, False)
        ordinary = tt.gather_blocked_recall(policy, snap)
        self.assertEqual(ordinary.failed, ())
        policy._terminal_blocked_recall = (DUNGEON_ANGBAND, False, True)
        self.assertEqual(tt.gather_blocked_recall(policy, snap), tt.gather_recall_departure(policy, snap))
        self.assertIn("light_ready", tt.gather_blocked_recall(policy, snap).failed)
        policy._terminal_blocked_recall = (DUNGEON_ANGBAND, True, False)
        depth = policy._dungeon_entry_depth(snap, DUNGEON_ANGBAND, via_recall=True)
        expected = tuple(policy._departure_minimum(snap, depth)["failed"])
        self.assertEqual(tt.gather_blocked_recall(policy, snap).failed, expected)
        for name in expected:
            self.assertIsNotNone(tt.declared_code("departure:" + name))
        before = pickle.dumps({name: value for name, value in vars(policy).items() if not callable(value)})
        tt.gather_blocked_recall(policy, snap)
        tt.blocked_intended_terminal(policy, snap)
        self.assertEqual(pickle.dumps({name: value for name, value in vars(policy).items()
                                     if not callable(value)}), before)

    def test_blocked_recall_context_restores_after_read_error_and_defaults_on_restore(self):
        policy, snap = blocked_recall()
        with patch.object(policy, "_descent_step", return_value=None), \
                patch.object(policy, "_recall_destination_safe", return_value=True), \
                patch.object(policy, "_read_key", side_effect=RuntimeError("read failed")):
            with self.assertRaisesRegex(RuntimeError, "read failed"):
                policy._town_blocked_key(snap)
        self.assertIsNone(policy._terminal_blocked_recall)
        del policy.__dict__["_terminal_blocked_recall"]
        self.assertIsNone(normalize_policy_state(policy)._terminal_blocked_recall)

    def test_named_closes_and_dispatchers_remain_available(self):
        snap = board()
        policy = policy_on(snap)
        for name in ("_town_blocked_key", "_opening_q34_town_key", "_town_restore_weapon_key",
                     "_heavy_curse_inscription_key", "_town_order_step4_key#1", "_town_order_step4_key#2",
                     "town-progress-committed-loot"):
            self.assertNotIn(name, tt.SHADOW_RUNGS)
            terminal = tt.rung_terminal(policy, name, snap)
            self.assertEqual(terminal.terminal_id, tt.NO_REFUSAL)
            self.assertTrue(tt.terminal_admission(policy, snap, terminal).admitted)


if __name__ == "__main__":
    unittest.main()
