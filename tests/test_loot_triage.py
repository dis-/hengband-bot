import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from hengbot.baseitem_knowledge import item_base_cost, load_baseitem_costs
from hengbot.cli import _dispatch_response_lines
from hengbot.model import (
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    SV_SCROLL_WORD_OF_RECALL,
    SV_STAFF_IDENTIFY,
    TVAL_SCROLL,
    TVAL_STAFF,
    TVAL_SWORD,
    STORE_HOME,
    STORE_WEAPON,
    InventoryItem,
    PlayerState,
    Position,
    Snapshot,
    GridState,
    StoreState,
)
from hengbot.policy import HengbotPolicy, PACK_CAPACITY


def carried(
    slot, tval=TVAL_SWORD, sval=1, *, aware=True, known=True, name="item", charges=0,
    is_equipment=False
):
    return InventoryItem(
        slot, name, 1, tval, sval, aware, known,
        charges=charges, is_equipment=is_equipment,
    )


def full_snapshot(inventory, *, dungeon=DUNGEON_YEEK_CAVE):
    position = Position(10, 10)
    return Snapshot(
        PlayerState(position, 100, 100, 0, 0, 20, class_id=PLAYER_CLASS_WARRIOR),
        {position: GridState(position, True, True, False, False, False, False, False,
                             object_count=1)},
        [],
        floor_key=(dungeon, 13, 0),
        town_flag=False,
        inventory=inventory,
    )


class BaseitemCostTest(unittest.TestCase):
    def test_real_jsonc_cost_and_unknown_identity(self):
        path = Path(r"C:\hengband\.worktrees\bot-json-output\lib\edit\BaseitemDefinitions.jsonc")
        self.assertTrue(path.is_file())
        costs = load_baseitem_costs(path)
        known_key, expected = next((key, value) for key, value in costs.items() if value > 0)
        known = carried("a", known_key[0], known_key[1])
        unknown = carried("b", known_key[0], -1, aware=False, known=False)
        self.assertEqual(item_base_cost(known, costs), expected)
        self.assertIsNone(item_base_cost(unknown, costs))


class GuardianLootTriageTest(unittest.TestCase):
    def _unknown_pack(self):
        source = carried(
            "a", TVAL_STAFF, SV_STAFF_IDENTIFY, name="Identify staff", charges=10
        )
        unknowns = [
            carried(chr(ord("b") + index), aware=True, known=False)
            for index in range(PACK_CAPACITY - 1)
        ]
        return [source, *unknowns]

    def test_victory_full_pack_identifies_instead_of_recalling(self):
        policy = HengbotPolicy()
        policy._yeek_victory_loot = True
        key = policy._victory_loot_key(full_snapshot(self._unknown_pack()))
        self.assertTrue(key.startswith("ua"), key)
        self.assertEqual(policy.last_reason, "identify:pack-pressure")

    def test_conquest_full_pack_identifies_instead_of_recalling(self):
        policy = HengbotPolicy()
        policy._victory_loot_dungeon = 4
        key = policy._conquest_loot_key(full_snapshot(self._unknown_pack(), dungeon=4))
        self.assertTrue(key.startswith("ua"), key)
        self.assertEqual(policy.last_reason, "identify:pack-pressure")

    def test_cost_exchange_never_selects_word_of_recall(self):
        recall = carried(
            "a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, name="Word of Recall"
        )
        others = [carried(chr(ord("b") + index), sval=2) for index in range(22)]
        policy = HengbotPolicy(baseitem_costs={(TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL): 1,
                                                (TVAL_SWORD, 2): 100,
                                                (TVAL_SWORD, 9): 1000})
        snapshot = full_snapshot([recall, *others], dungeon=4)
        policy._look_floor_key = snapshot.floor_key
        policy._look_floor_items = {
            snapshot.player.position: (carried("", sval=9, name="reward"),)
        }
        policy._full_pack_destroy_key = lambda _snapshot: None
        policy._pack_pressure_identify_key = lambda _snapshot: None
        policy._entire_stack_is_surplus = lambda _snapshot, item: item.slot == "a"
        self.assertIsNone(policy._full_pack_loot_triage_key(snapshot))

    def test_unaware_floor_item_is_identified_before_exchange(self):
        source = carried(
            "a", TVAL_STAFF, SV_STAFF_IDENTIFY, name="Identify staff", charges=10
        )
        inventory = [source] + [carried(chr(ord("b") + i), sval=2) for i in range(22)]
        policy = HengbotPolicy(baseitem_costs={(TVAL_SWORD, 2): 10})
        snapshot = full_snapshot(inventory)
        policy._look_floor_key = snapshot.floor_key
        policy._look_floor_items = {
            snapshot.player.position: (carried("", sval=-1, aware=False, known=False),)
        }
        policy._full_pack_destroy_key = lambda _snapshot: None
        policy._pack_pressure_identify_key = lambda _snapshot: None
        self.assertEqual(policy._full_pack_loot_triage_key(snapshot), "ua-")
        self.assertEqual(policy.last_reason, "loot:identify-floor-item")


class LookResponseTest(unittest.TestCase):
    def test_requested_look_is_consumed_and_probe_is_lazy(self):
        policy = HengbotPolicy()
        position = Position(3, 4)
        empty = Snapshot(
            PlayerState(position, 10, 10, 0, 0, 1),
            {position: GridState(
                position, True, True, False, False, False, False, False,
                store_number=STORE_HOME,
            )},
            [],
        )
        self.assertNotEqual(policy._victory_loot_key(empty), "l\x1b")

        policy._look_probe_inflight = True
        send = Mock()
        response = {"type": "look", "look": {"grids": [{"y": 3, "x": 4,
                    "items": [{"tval": TVAL_SWORD, "sval": 7, "aware": True,
                               "known": True, "name": "floor sword"}]}]}}
        self.assertEqual(_dispatch_response_lines([json.dumps(response)], policy, send), 1)
        self.assertEqual(policy._look_floor_items[position][0].sval, 7)
        self.assertFalse(policy._look_probe_inflight)
        send.assert_not_called()


class TownOrganizationTest(unittest.TestCase):
    def _town(self, inventory, store_type=None):
        position = Position(10, 10)
        return Snapshot(
            PlayerState(position, 100, 100, 20, 20, 20, class_id=PLAYER_CLASS_WARRIOR),
            {position: GridState(
                position, True, True, False, False, False, False, False,
                store_number=STORE_HOME,
            )},
            [],
            town_flag=True,
            inventory=inventory,
            store=StoreState(store_type, []) if store_type is not None else None,
        )

    def test_sellable_surplus_sells_and_then_no_longer_blocks(self):
        spare = carried("a", name="spare sword", is_equipment=True)
        policy = HengbotPolicy()
        snapshot = self._town([spare], STORE_WEAPON)
        self.assertIs(policy._find_town_organization_surplus(snapshot), spare)
        self.assertEqual(policy._shop(snapshot), "da\r")
        self.assertEqual(policy.last_reason, "shop:sell-town-surplus")
        self.assertIsNone(policy._find_town_organization_surplus(self._town([])))

    def test_surplus_blocks_departure_until_removed(self):
        spare = carried("a", name="spare sword", is_equipment=True)
        policy = HengbotPolicy()
        policy._recall_departure_ready = lambda _snapshot: True
        policy._food_ready = lambda _snapshot: True
        policy._light_ready = lambda _snapshot: True
        policy._teleport_ready = lambda _snapshot: True
        policy._cure_critical_ready = lambda _snapshot: True
        policy._identify_staff_ready = lambda _snapshot: True
        policy._inventory_overweight = lambda _snapshot: False
        self.assertFalse(policy._town_departure_ready(self._town([spare])))
        policy._home_available = lambda _snapshot: False
        self.assertTrue(policy._town_departure_ready(self._town([])))

    def test_unsellable_surplus_is_deposited_at_home(self):
        spare = carried("a", name="spare sword", is_equipment=True)
        policy = HengbotPolicy()
        policy._unsellable_items.add(policy._item_signature(spare))
        snapshot = self._town([spare], STORE_HOME)
        self.assertIs(policy._find_home_deposit(snapshot), spare)
        self.assertEqual(policy._home_deposit_key(snapshot, spare), "da\r")
        self.assertEqual(policy.last_reason, "home:deposit")
