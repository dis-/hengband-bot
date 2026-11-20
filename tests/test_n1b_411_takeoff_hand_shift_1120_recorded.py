"""n1-b life-411 2026-11-20 22:31: a mid-swap takeoff found its sub hand empty.

Recorded: the boards of tests/fixtures/n1b-411-equipment-departure-1120 (the
town visit of the incident capture 20261120-223208-town-blocked-unmet-
equipment-departure-ready; a journal row is one decision of the visit).  At
row 276 the Magic-Eater dual-wielded a nunchaku (main hand) and Princess
Eowyn's bastard sword (sub hand, identity 28aedef5bc0c8b75); the 26-action Home
swap (target loadout 37df645d99982494) put a two-handed war hammer in the main
hand and left the sub hand empty.  The pack held 11 items, so the plan was
staged one slot at a time in _EQUIP_ORDER and the main hand's batch (row 329,
'ta') took the nunchaku off first.  do_cmd_takeoff then runs verify_equip_slot
(src/action/weapon-shield.cpp): the uncursed sub-hand sword moved into the main
hand, and the hammer's wield (row 330, 'wkn': the dual-wield question answered
no) replaced it into the pack.  The sub hand's planned takeoff read the slot
empty (row 334, equipment-transaction:stale-identity-invalidated:takeoff:
missing); the sword was marked failed, the new search's best loadout held it
(blocker equipment-transaction-failed), and as the stale path recorded no Home
attempt for the visit, _equipment_failure_unexecutable_this_visit kept waiting
on a Home no producer routed to: town:blocked:unmet:equipment_departure_ready
(row 341).

Pinned: the plan rebuilt from the recorded boards is the recorded one up to the
hands, and now takes the sub hand off before the main hand, so every takeoff
finds its item under the game's hand rule; on the row-334 Home board the
already-performed takeoff is passed and the sword's deposit follows; and a
takeoff that is really stale records the visit's Home attempt, so a failed
target can depart on the current kit (owner 2026-10-03 「失敗した任意の装備の
変更は今の確定した装備で出発」).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from hengbot.equipment_optimizer import (
    Loadout,
    OwnedEquipmentCatalog,
    current_loadout,
    equipment_identity,
    equipment_move_identity,
)
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    PHASE_HOME_FINALIZE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
    plan_equipment_transactions,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

JOURNAL = (Path(__file__).with_name("fixtures") / "n1b-411-equipment-departure-1120"
           / "journal.jsonl.xz")
PLAN_ROW = 276      # the board the 26-action swap was planned on
HANDS_ROW = 328     # every other slot swapped, the hammer withdrawn
STALE_ROW = 334     # stale-identity-invalidated:takeoff:missing, on a Home board
STOP_ROW = 341      # town:blocked:unmet:equipment_departure_ready
SWORD = "28aedef5bc0c8b75"
NUNCHAKU = "345d395c7be96297"
HAMMER = "f9f65303202f97e9"
MELEE_TVALS = {20, 21, 22, 23}  # BaseitemKey::is_melee_weapon
# The recorded transaction_next sequence up to the hands (decision log).
RECORDED_PREFIX = [
    ("withdraw", "home:6b2d750ea3ed50d3:0", None),
    ("takeoff", "equipped:5798557eff9a257f:0", "neck"),
    ("equip", "home:6b2d750ea3ed50d3:0", "neck"),
    ("deposit", "equipped:5798557eff9a257f:0", None),
    ("withdraw", "home:da3efbe6668d171f:0", None),
    ("takeoff", "equipped:9cb20628a924735f:0", "light"),
    ("equip", "home:da3efbe6668d171f:0", "light"),
    ("deposit", "equipped:9cb20628a924735f:0", None),
    ("withdraw", "home:0329c1bbac04b9bd:0", None),
    ("takeoff", "equipped:c78a0cd95d9610f2:0", "body"),
    ("equip", "home:0329c1bbac04b9bd:0", "body"),
    ("deposit", "equipped:c78a0cd95d9610f2:0", None),
    ("withdraw", "home:f40c471198d69697:0", None),
    ("takeoff", "equipped:978f30bf419f2cfd:0", "outer"),
    ("equip", "home:f40c471198d69697:0", "outer"),
    ("deposit", "equipped:978f30bf419f2cfd:0", None),
    ("withdraw", "home:b75ae16868174fcb:0", None),
    ("takeoff", "equipped:116884579e9c3a50:0", "arms"),
    ("equip", "home:b75ae16868174fcb:0", "arms"),
    ("deposit", "equipped:116884579e9c3a50:0", None),
    ("withdraw", f"home:{HAMMER}:0", None),
]


def boards():
    rows = lzma.decompress(JOURNAL.read_bytes()).splitlines()

    def board(row):
        entry = json.loads(rows[row])
        line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
        return entry, parse_snapshot(json.loads(line), {})
    return board


def recorded_swap(board):
    """The swap's catalog, worn loadout and target, from the recorded boards."""
    _, start = board(PLAN_ROW)
    _, later = board(HANDS_ROW)
    catalog = OwnedEquipmentCatalog()
    catalog.refresh_carried(start.inventory, start.equipment)
    items = list(catalog.items)
    current = current_loadout(items)
    worn = dict(current.slots)
    known = {equipment_identity(owned.item) for owned in items}
    slots = dict(worn)
    for item in (*later.equipment, *later.inventory):
        if not item.is_equipment or item.tval == 17 or equipment_identity(item) in known:
            continue
        fetched = OwnedEquipmentCatalog()
        fetched.refresh_carried((item,), ())
        owned = fetched.items[0]
        owned = replace(owned, id=owned.id.replace("pack:", "home:"), origin="home")
        items.append(owned)
        slots[item.slot if item.slot in worn else "main_hand"] = owned
    del slots["sub_hand"]
    target = Loadout(tuple(sorted(slots.items())), "two_handed")
    return start, items, current, target


def play_hands(plan, current, tvals):
    """Run the plan under the game's hand rule; each takeoff's (planned, found)."""
    worn = {slot: equipment_identity(owned.item) for slot, owned in current.slots}
    readings = []
    for action in plan.actions:
        if action.kind == "takeoff":
            readings.append((action.item_identity, worn.get(action.target_slot)))
            if worn.get(action.target_slot) == action.item_identity:
                del worn[action.target_slot]
                sub = worn.get("sub_hand")
                if action.target_slot == "main_hand" and sub and tvals[sub] in MELEE_TVALS:
                    worn["main_hand"] = worn.pop("sub_hand")  # verify_equip_slot
        elif action.kind in {"equip", "reposition"}:
            worn[action.target_slot] = action.item_identity
    return readings, worn


class N1b411TakeoffHandShiftRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = staticmethod(boards())

    def test_the_swap_takes_the_sub_hand_off_before_the_main_hand(self):
        start, items, current, target = recorded_swap(self.board)
        plan = plan_equipment_transactions(
            items, current, target,
            current_pack_items=len(start.inventory), home_scan_complete=True)
        self.assertTrue(plan.executable)
        steps = [(action.kind, action.item_id, action.target_slot) for action in plan.actions]
        self.assertEqual(steps[:len(RECORDED_PREFIX)], RECORDED_PREFIX)
        self.assertEqual(steps[len(RECORDED_PREFIX):], [
            ("takeoff", f"equipped:{SWORD}:0", "sub_hand"),
            ("takeoff", f"equipped:{NUNCHAKU}:0", "main_hand"),
            ("equip", f"home:{HAMMER}:0", "main_hand"),
            ("deposit", f"equipped:{SWORD}:0", None),
            ("deposit", f"equipped:{NUNCHAKU}:0", None),
        ])
        tvals = {equipment_identity(owned.item): owned.item.tval for owned in items}
        readings, worn = play_hands(plan, current, tvals)
        self.assertEqual([found for _, found in readings], [planned for planned, _ in readings])
        self.assertEqual(worn["main_hand"], HAMMER)
        self.assertNotIn("sub_hand", worn)

    def test_an_already_performed_takeoff_is_passed_and_the_swap_goes_on(self):
        entry, home = self.board(STALE_ROW)
        self.assertEqual(entry["reason"],
                         "equipment-transaction:stale-identity-invalidated:takeoff:missing")
        sword = next(item for item in home.inventory if equipment_identity(item) == SWORD)
        takeoff = EquipmentTransaction(
            PHASE_EQUIP, "takeoff", f"equipped:{SWORD}:0", "sub_hand",
            SWORD, equipment_move_identity(sword))
        deposit = EquipmentTransaction(
            PHASE_HOME_FINALIZE, "deposit", f"equipped:{SWORD}:0", None,
            SWORD, equipment_move_identity(sword))
        policy = HengbotPolicy()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((takeoff, deposit), (), 0), physical_context="home")

        key = policy._equipment_transaction_home_key(home)

        self.assertEqual((key, policy.last_reason),
                         (f"d{sword.slot}", "equipment-transaction:deposit"))
        self.assertEqual(policy._equipment_transaction_failed_items, set())
        self.assertEqual(policy._equipment_transaction_owned_items,
                         [(equipment_move_identity(sword), "sub_hand")])

    def test_a_stale_takeoff_records_the_visits_home_attempt(self):
        _, home = self.board(STALE_ROW)
        _, stop = self.board(STOP_ROW)
        gone = replace(home, inventory=[item for item in home.inventory
                                        if equipment_identity(item) != SWORD])
        takeoff = EquipmentTransaction(
            PHASE_EQUIP, "takeoff", f"equipped:{SWORD}:0", "sub_hand", SWORD)
        policy = HengbotPolicy()
        policy._town_visit_epoch = 411
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((takeoff,), (), 0), physical_context="home")

        policy._equipment_transaction_home_key(gone)

        self.assertEqual(policy.last_reason,
                         "equipment-transaction:stale-identity-invalidated:takeoff:missing")
        self.assertIn(f"equipped:{SWORD}:0", policy._equipment_transaction_failed_items)
        self.assertEqual(policy._equipment_transaction_abandoned_epoch, 411)
        policy._equipment_transaction_session = None
        failed = SimpleNamespace(blockers=("equipment-transaction-failed",),
                                 result=None, transaction=None)
        self.assertTrue(policy._equipment_failure_unexecutable_this_visit(
            stop, failed, require_confirmed=False))


if __name__ == "__main__":
    unittest.main()
