"""A Home *Enlightenment* is taken out and drunk (enlightenment-home-1113).

Owner 2026-11-13 「*啓蒙*の薬を飲んでいない件を調査。知能と賢さの基礎値が上がるのですぐに飲みたいし、
そのように設定したはずである」.  The owner's table marks *Enlightenment* (75/57) and Self Knowledge
(75/58) 「拾って使う」; the Potion of *Enlightenment* raises the INT and WIS bases
(quaff-effects.cpp star_enlightenment: do_inc_stat(A_INT), do_inc_stat(A_WIS)).  Until
3f6f812a7f the self-knowledge viewer kept both out of the quaff, and n1-c life-205 deposited
its *啓蒙*の薬 at the Outpost Home as surplus (home-withdraw-history.jsonc, turn 1089430,
2026-11-12 19:03 JST); the quaff reads only the pack, so the Home copy stayed there.

Recorded: the same town-arrival checkpoint as tests/test_n1c_205_food_devices_1113_recorded.py
(fixtures/n1c-205-food-devices-1113, 2026-11-13 00:11).  Row 1's ``~9`` Home list holds
*啓蒙*の薬 x1 (Home slot 12).  The recorded bot never took it: rows 11-16 sold at the Magic
shop and row 18 stopped.

Fix: consumable_policy.home_potions_to_drink / policy_home._bind_home_drink_potion_withdrawal
file the Home take (the *Remove Curse* reserve's addressed take), the stat-gain quaff drinks
the carried one, and the retention keeps both kinds whole (``consumable:drink-not-store``), so
no stash, sale or destruction path takes them.

Walls, declared: the expedition latch of the food-devices sale test
(``_expedition_run_unneeded`` patched to False) keeps rows 0-10 on the recorded keys.
DECLARED CONSTRUCTED: the row-11 board with the taken potion in the pack (slot e); an awake
enemy in view.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import unittest
from unittest.mock import patch

from hengbot import consumable_policy, me_staff_sequence
from hengbot.model import STORE_HOME, TVAL_POTION, parse_snapshot
from replay_town_arrival import journal
from tests import test_n1c_205_food_devices_1113_recorded as food_devices

STAR_ENLIGHTENMENT = 57
SIGNATURE_KIND = (TVAL_POTION, STAR_ENLIGHTENMENT)
# DECLARED CONSTRUCTED: an awake enemy in view, two grids away.
MONSTER = {"index": 77, "race_id": 24, "hp": 10, "max_hp": 10, "distance": 2, "friendly": False,
           "pet": False, "speed": 110, "name": "enemy", "visible": True, "asleep": False}


class N1c205EnlightenmentHome1113RecordedTest(food_devices.N1c205FoodDevices1113RecordedTest):
    def setUp(self):
        super().setUp()
        latch = patch.object(me_staff_sequence, "_expedition_run_unneeded", lambda *args: False)
        latch.start()
        self.addCleanup(latch.stop)

    # The inherited pins run in their own module.
    test_identified_trip_leaves_for_the_tower = None
    test_magic_shop_keeps_the_drained_staples_food = None

    def row_raw(self, row):
        entry = journal(self.scratch / "town-arrival")[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def test_home_listing_holds_the_deposited_potion(self):
        policy, recorded, steps = self.load()
        self.replay_live(policy, recorded, steps[:2])
        steps[2][1]()
        home = [item for item in policy._home_knowledge_items
                if (item.tval, item.sval) == SIGNATURE_KIND]
        self.assertEqual([(item.slot, item.count, item.aware) for item in home], [("12", 1, True)])

    def test_the_visit_files_the_home_take_and_walks_to_home(self):
        """Row 10 files the take; row 11 (recorded ``3`` shop:approach, the Magic shop) walks Home."""
        policy, recorded, steps = self.load()
        self.assertEqual((recorded[11]["key"], recorded[11]["reason"]), ("3", "shop:approach"))
        self.replay_live(policy, recorded, steps[:11])
        self.assertIsNotNone(policy._home_pending_item)
        self.assertEqual(policy._home_pending_item[1:], SIGNATURE_KIND)
        self.assertEqual(policy._home_pending_quantity, 1)
        self.assertTrue(policy._home_withdrawal_queued)
        board = steps[11][1]()
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "shop:travel")
        self.assertTrue(key.startswith("\x1b`"), key)
        self.assertEqual(policy._store_visit.store_type, STORE_HOME)

    def test_no_take_with_an_enemy_in_view(self):
        policy, recorded, steps = self.load()
        self.replay_live(policy, recorded, steps[:10])
        raw = self.row_raw(10)
        # DECLARED CONSTRUCTED: an awake enemy in view.
        raw["visible_monsters"] = [dict(MONSTER, y=raw["player"]["y"], x=raw["player"]["x"] + 2)]
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(consumable_policy.home_potions_to_drink(policy, board), [])
        self.assertIsNone(policy._home_pending_item)

    def test_the_taken_potion_is_drunk_and_never_stored(self):
        policy, recorded, steps = self.load()
        self.replay_live(policy, recorded, steps[:11])
        steps[11][1]()
        raw = self.row_raw(11)
        inventory = raw["inventory"]
        # DECLARED CONSTRUCTED: the taken *啓蒙*の薬 in the pack, after the potions (slot e).
        potion = dict(next(item for item in inventory if item["tval"] == TVAL_POTION))
        potion.update(name="*啓蒙*の薬", sval=STAR_ENLIGHTENMENT, count=1, inscription="",
                      fully_known=False, charges=0, pval=0, known_flags=[])
        inventory.insert(4, potion)
        for index, item in enumerate(inventory):
            item["slot"] = "abcdefghijklmnopqrstuvw"[index]
        board = parse_snapshot(raw, policy._monrace_knowledge)
        carried = next(item for item in board.inventory
                       if (item.tval, item.sval) == SIGNATURE_KIND)
        self.assertEqual(carried.slot, "e")
        self.assertEqual(policy._retention_reservation_detail(board, carried),
                         (1, "consumable:drink-not-store"))
        self.assertEqual(policy._retention_surplus(board, carried), 0)
        self.assertFalse(policy._home_deposit_candidate(carried, board))
        self.assertEqual(consumable_policy.home_potions_to_drink(policy, board), [])
        # DECLARED CONSTRUCTED: the take's observed effect confirms the queued take
        # (policy.py, home-withdraw-observed); the quaff ends it before drinking
        # (stat-potions-home-1114: drunk while still queued, it read as a failed take).
        policy._home_withdrawal_queued = False
        policy._home_pending_take_confirmed = policy._home_pending_item
        self.assertEqual(policy.choose_key(board), "qe")
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual(policy.last_reason, "stat-gain:self-knowledge")


if __name__ == "__main__":
    unittest.main()
