"""Issue #47, owner answers of 2026-10-31 15h (equipment / town family).

Every case replays the recorded n1-b life-276 town boards of
``fixtures/town-stops-1031.json.gz`` (``extract_town_stops_1031_fixture``)
through the public chooser, as ``test_town_stops_1031_recorded`` does; keys
are posted through the production executor.

- Town re-arm (owner 「町でも持たせる」): the recorded ``town3`` boards
  (Warrior Lv, Home entrance, 09:00) with the worn main-hand weapon moved into
  the pack (DECLARED CONSTRUCTED: the empty hand a digger swap or a takeoff
  leaves); the Monk control is the same boards with class 8 (DECLARED
  CONSTRUCTED).  The executor's reply to the wield is the board with the
  weapon back in the hand (DECLARED CONSTRUCTED).
- Full pack with no room (owner 「名前付きで止まる」): the recorded ``town3``
  boards (n1-b life-276 09:00, the Magic shop shelving affordable Identify
  staves the pack budget refuses at 19/23) with every stack the headroom pass
  could shelve or sell recorded as bought on this visit (DECLARED
  CONSTRUCTED: ``_town_visit_purchases``, which keeps a purchase from being
  shelved or sold again), so no carried stack can make room.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import string

from hengbot import town_pack_headroom
from hengbot.cli import _policy_final_stop_banner, _policy_final_stop_required
from hengbot.model import parse_snapshot
from tests import test_town_stops_1031_recorded as town_stops
import tests.test_input_executor as executor_harness


RESTORE = "town:restore-combat-weapon"
MONK = 8  # player-info/class-types.h; mining_loadout.MARTIAL_ARTS_CLASS_IDS
PACK_FULL_NO_ROOM = "town:blocked:pack-full-no-room"
AFTER_MAGIC = 66  # the first outside board after the Magic shop page (65)
FIRST_DECISION = 59  # the first town3 board after the ~f (56) and Home list (58) rows


def reletter(raw):
    for letter, item in zip(string.ascii_lowercase, raw["inventory"]):
        item["slot"] = letter
    return raw


def bare_handed(raw, class_id=None):
    """The board with its main-hand weapon carried instead (DECLARED CONSTRUCTED)."""
    raw = copy.deepcopy(raw)
    if raw.get("type") not in ("player_turn", "store"):
        return raw
    weapon = next(item for item in raw["equipment"] if item["slot"] == "main_hand")
    raw["equipment"].remove(weapon)
    raw["inventory"].append(dict(weapon, slot="?"))
    if class_id is not None:
        raw["player"]["class_id"] = class_id
    return reletter(raw)


def armed(raw, letter):
    """The board after the wield of pack letter ``letter`` (DECLARED CONSTRUCTED)."""
    after = copy.deepcopy(raw)
    item = next(i for i in after["inventory"] if i["slot"] == letter)
    after["inventory"].remove(item)
    after["equipment"].append(dict(item, slot="main_hand"))
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


class OwnerCEquipRecordedTest(executor_harness.ProductionHarness):
    # The recorded-town replay and posting of test_town_stops_1031_recorded
    # (borrowed, not inherited: its own tests stay in their module).
    Recorded = town_stops.TownStops1031RecordedTest
    shelf_screen = Recorded.shelf_screen
    post = Recorded.post
    execute = Recorded.execute
    row = Recorded.row
    replay = Recorded.replay

    @classmethod
    def setUpClass(cls):
        cls.Recorded.setUpClass()
        cls.cases = copy.deepcopy(cls.Recorded.cases)

    def bare_case(self, class_id=None):
        rows = self.cases["town3"]["rows"]
        self.cases["town3-bare"] = {
            "rows": [[index, bare_handed(row, class_id)] for index, row in rows]}
        try:
            return self.replay("town3-bare", FIRST_DECISION, in_store=True)
        finally:
            del self.cases["town3-bare"]

    def test_town_empty_main_hand_is_rearmed_before_departure(self):
        policy, raw, decisions = self.bare_case()
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertIsNone(next((i for i in board.equipment if i.slot == "main_hand"), None))
        self.assertFalse(any(item.is_digging_tool for item in board.equipment))
        weapon = next(item for item in board.inventory if item.is_melee_weapon)
        self.assertFalse(policy._combat_weapon_ready(board))
        key, reason = decisions[FIRST_DECISION]
        self.assertEqual((key, reason), ("w" + weapon.slot, RESTORE))
        following = armed(raw, weapon.slot)
        self.post(policy, raw, key, following)
        rearmed = parse_snapshot(following, policy._monrace_knowledge)
        self.assertTrue(policy._combat_weapon_ready(rearmed))
        key = policy.choose_key(rearmed)
        self.assertNotEqual(policy.last_reason, RESTORE)
        self.assertFalse(str(key).startswith("w"), (key, policy.last_reason))

    def test_martial_arts_class_keeps_its_main_hand_empty(self):
        # player-status.cpp is_martial_arts_mode: a Monk fights bare-handed.
        policy, raw, decisions = self.bare_case(MONK)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertTrue(policy._combat_weapon_ready(board))
        for index, (key, reason) in decisions.items():
            with self.subTest(row=index):
                self.assertNotEqual(reason, RESTORE)

    def test_refused_purchase_with_no_room_to_make_stops_named(self):
        def nothing_releasable(policy):
            # DECLARED CONSTRUCTED (module docstring).
            first = parse_snapshot(self.row("town3", 51), policy._monrace_knowledge)
            releasable = [item for item in first.inventory
                          if town_pack_headroom.preservable(policy, first, item)]
            self.assertTrue(releasable)
            policy._town_visit_purchases.update(
                policy._item_signature(item) for item in releasable)

        policy, raw, decisions = self.replay(
            "town3", AFTER_MAGIC, in_store=True, prepare=nothing_releasable)
        magic = parse_snapshot(self.row("town3", 65), policy._monrace_knowledge)
        self.assertEqual((magic.store.store_type, len(magic.inventory)), (5, 19))
        for index, (_, reason) in decisions.items():
            with self.subTest(row=index):
                self.assertFalse(reason.startswith("town:wait-restock"), reason)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertFalse(any(town_pack_headroom.preservable(policy, board, item)
                             for item in board.inventory))
        self.assertEqual(decisions[AFTER_MAGIC][1], PACK_FULL_NO_ROOM)
        self.assertTrue(_policy_final_stop_required(policy))
        self.assertIn("refused only by the pack", _policy_final_stop_banner(PACK_FULL_NO_ROOM))


if __name__ == "__main__":
    import unittest
    unittest.main()
