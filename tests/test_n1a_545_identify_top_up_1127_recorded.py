"""A top-up the visit cannot finish does not stop the town (n1-a life-545, MAINTAINABILITY.md rule 2).

Recorded (tests/extract_n1a_545_identify_top_up_1127_fixture.py, ``n1a-545-identify-top-up-1127``):
the town-arrival checkpoint of 2026-11-27 02:08:35 (Amberite Rogue CL21, gold 1965, a mining set
open).  Row 133 stopped under ``town:blocked:survival:identify_staff_ready``: 18 of the 20 Identify
staff charges carried (two 9-charge staves), the pack at 1432 of its 1450 weight limit, so the
Magic shop's 21-charge staff (row 129, ``shop:observed-operation-uncomposable``) and Home's
15-charge staff (row 132, ``home:atomic-withdraw-identify-staff-overweight``) were both refused.
18 charges is above the least reserve IDENTIFY_CHARGE_FLOOR: the town end departs with them once
the rescues gave no key (departure_leaf_classes).  Rows before the one decided are replayed through
the public ``choose_key`` and post the recorded key.

DECLARED CONSTRUCTED: ``test_entrance_board_enters_the_dungeon`` moves the player of row 133's
board onto the dungeon entrance (the walk the departure's travel key starts);
``test_reliable_identify_spell_replaces_the_staff`` lowers the recorded 鑑定 row's fail from 58% to
5% (the Rogue's spell list); ``test_without_the_top_up_class_the_recorded_stop_returns`` empties
the top-up class to show the stop the fix removes.  Every test holds the 鑑定's usable rate at
RELIABLE_MIN_SUCCESS (80%, the rule this capture was recorded under): from the supervisor's
2026-11-27 rule the Rogue's 42% 鑑定 replaces the staff (tests/test_rogue_identify_spell_1127_recorded.py)
and the recorded visit is no longer the one these tests replay.  The module also runs under the
equipment rules the visit was recorded with (tests/support/pre_caster_rules.py: row 23 learns the worn shield's NO_MAGIC, and the
caster rules of 2026-11-27 would take it off from row 24 on).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import departure_leaf_classes, realm_spells
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import IDENTIFY_CHARGE_FLOOR, STAFF_IDENTIFY_MIN_CHARGES
from support import pre_caster_rules
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-identify-top-up-1127"
STOP_ROW = 133
STOP_REASON = "town:blocked:survival:identify_staff_ready"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


_REPLAYED: dict = {}


def setUpModule():
    # DECLARED CONSTRUCTED (module docstring): the 鑑定 counts from 80% as when recorded.
    patcher = mock.patch.object(realm_spells, "IDENTIFY_SPELL_MIN_SUCCESS",
                                realm_spells.RELIABLE_MIN_SUCCESS)
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)
    # The equipment and spell rules before the caster rules (module docstring).
    unittest.addModuleCleanup(pre_caster_rules.patches().close)


def replayed():
    """(checkpoint of the policy before row 133, row 133's recorded row and board), replayed once."""
    if not _REPLAYED:
        scratch = TemporaryDirectory()
        _REPLAYED["scratch"] = scratch
        policy, journal, steps = load(FIXTURE, Path(scratch.name))
        assert steps[STOP_ROW][0]["reason"] == journal[STOP_ROW]["reason"] == STOP_REASON
        for recorded, supply in steps[:STOP_ROW]:
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(supply())
            assert (key, policy.last_reason) == (recorded["key"], recorded["reason"]), recorded
            post(policy, recorded["key"])
        _REPLAYED["board"] = steps[STOP_ROW][1]()
        _REPLAYED["policy"] = checkpoint_bytes(policy)
    return restore_checkpoint_bytes(HengbotPolicy, _REPLAYED["policy"]), _REPLAYED["board"]


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class IdentifyTopUp545RecordedTest(unittest.TestCase):
    def test_recorded_board_is_the_overweight_top_up(self):
        policy, board = replayed()
        charges = policy._total_identify_staff_charges(board)
        self.assertEqual(charges, 18)
        self.assertLess(charges, STAFF_IDENTIFY_MIN_CHARGES)
        self.assertGreaterEqual(charges, IDENTIFY_CHARGE_FLOOR)
        self.assertFalse(policy._identify_staff_ready(board))
        self.assertTrue(policy._identify_staff_adequate(board))
        # Every Identify staff the visit could still take weighs 5 lb over the 1.8 lb headroom.
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1432, 1450))
        staff = next(item for item in board.inventory if item.tval == 55 and item.sval == 5)
        self.assertTrue(policy._identify_staff_take_overloads(board, staff))
        # The procurement row keeps the 20-charge target for the next visit.
        self.assertIn({"item": "Identify staff charges", "current": 18, "target": 20,
                       "missing": 2}, policy.procurement_requirements(board))
        # The minimum holds the top-up to its adequacy.
        minimum, _destination, _depth = policy._visit_departure_minimum(board)
        self.assertTrue(minimum["holds"], minimum["failed"])

    def test_town_end_departs_with_the_adequate_charges(self):
        policy, board = replayed()
        key, reason = decide(policy, board)
        self.assertEqual((key, reason), ("\x1b`n>.", "town:travel-entrance"))
        self.assertEqual(policy._visit_departure_committed, "top-up-adequate")
        self.assertNotEqual(policy._town_blocked_reason, "survival:identify_staff_ready")

    def test_entrance_board_enters_the_dungeon(self):
        policy, board = replayed()
        key, _reason = decide(policy, board)
        post(policy, key)
        entrance = next(grid for grid in board.grids.values()
                        if grid.has_entrance and policy._is_active_dungeon_entrance(grid))
        walked = replace(board, player=replace(board.player, position=entrance.position),
                         turn=board.turn + 50)
        key, reason = decide(policy, walked)
        self.assertEqual((key, reason), (">\ry", "town:repetition-depart:enter"))

    def test_without_the_top_up_class_the_recorded_stop_returns(self):
        policy, board = replayed()
        with mock.patch.dict(departure_leaf_classes.TOP_UP, clear=True):
            key, reason = decide(policy, board)
        self.assertEqual((key, reason), ("5", STOP_REASON))

    def test_reliable_identify_spell_replaces_the_staff(self):
        policy, board = replayed()
        # The recorded 鑑定 (Sorcery book 2) is learned at 58% fail: no stand-in for the staff.
        self.assertTrue(realm_spells.learned(policy, realm_spells.IDENTIFY))
        self.assertFalse(realm_spells.identify_reliable(policy, board))
        lists = copy.deepcopy(policy._realm_spell_lists)
        lists[1]["rows"][realm_spells.IDENTIFY]["fail"] = 5
        policy._realm_spell_lists = lists
        self.assertTrue(realm_spells.identify_reliable(policy, board))
        self.assertTrue(policy._identify_staff_ready(board))
        self.assertNotIn("Identify staff charges",
                         [row["item"] for row in policy.procurement_requirements(board)])

    def test_every_minimum_leaf_has_one_class(self):
        policy, board = replayed()
        minimum, _destination, _depth = policy._visit_departure_minimum(board)
        # The whole table against every gate's leaves: tests/test_departure_leaf_classes.py.
        for leaf in minimum["values"]:
            self.assertEqual(sum(leaf in members
                                 for members in departure_leaf_classes.CLASSES.values()), 1, leaf)


if __name__ == "__main__":
    unittest.main()
