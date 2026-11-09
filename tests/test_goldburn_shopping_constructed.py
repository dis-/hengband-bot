"""CONSTRUCTED seams from the two goldburn decision rows, NOT recorded replay.

The state file no longer covers these turns. Position, turn, gold, level,
HP/MP, food band and expedition fields are retained. Towns are inferred from
the preceding paid macros: Telmora for row 3512, Outpost for row 3691. The
cycle board retains one carried digger, with its subtype/slot constructed.
Grids, other inventory, class/stats, exact food amount, quest completion and
supplier/Home knowledge are constructed premises. Real producers run without collaborator
mocks. Pins stop at the first differing producer result; no later live board is
claimed to result from the new key. Revert-proof is run by restoring source in
this same worktree temporarily (see final report).
"""
import tests  # noqa: F401 -- isolate live runtime files
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from policy_fixtures import grid, player, item
from hengbot.model import Position, Snapshot, QuestState, STORE_ALCHEMIST, TVAL_DIGGING, SV_DIGGING_SHOVEL
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import QUEST_STATUS_FINISHED
from hengbot.policy_types import CrossTownShoppingExpedition
from hengbot.town_hold import reach_place_goal as reach_place
from hengbot.town_terminal import gather_quest_work, verdict_quest_work

# Moved to tests/support/boards.py; re-exported for importers.
from tests.support.boards import (  # noqa: F401
    GOLDBURN_FIXTURE as FIXTURE, GOLDBURN_SHA256 as SHA256, goldburn_board as board,
    goldburn_decision as decision, goldburn_shopping_policy as shopping_policy,
)


def _quest_entry(policy, snap):
    """The fixed-quest rung through its entry, on a decision board whose
    arrival was observed first (as at the start of every decision)."""
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    policy._observe_cross_town_shopping_arrival(snap)
    return policy._town_producer_entry(
        "_fixed_quest_key#2", lambda: policy._fixed_quest_key(snap, []))


def _shopping_holds(policy, snap):
    return not verdict_quest_work(gather_quest_work(policy, snap)).admitted


class GoldburnShoppingConstructedTest(unittest.TestCase):
    def test_first_alternating_board_quest_return_yields_and_records_arrival(self):
        policy = shopping_policy()
        snap = board()
        policy._build_grid_index(snap)
        self.assertIsNone(_quest_entry(policy, snap))
        self.assertEqual(policy._cross_town_shopping.tried_towns, [1])
        self.assertIsNone(policy._cross_town_shopping.target_town_id)
        self.assertTrue(_shopping_holds(policy, snap))
        # A second board must still yield, after the arrival target was cleared.
        self.assertIsNone(_quest_entry(policy, replace(snap, turn=snap.turn + 1)))

    def test_destination_discards_origin_stockout_and_store_bounds(self):
        policy = shopping_policy()
        snap = board()
        policy._observed_town_id = 0
        policy._town_was_in_town = True
        policy._town_visit_ledger.shelf_observations[(STORE_ALCHEMIST, "identification-source:full")] = ()
        policy._town_visit_ledger.blocked_stores.add(STORE_ALCHEMIST)
        policy._observe(snap)
        self.assertFalse(policy._town_visit_ledger.shelf_observations)
        self.assertNotIn(STORE_ALCHEMIST, policy._town_visit_ledger.blocked_stores)
        self.assertIsNone(_quest_entry(policy, snap))

    def test_arrival_completes_transport_claim_before_shop_entry(self):
        policy = shopping_policy()
        snap = board()
        register = policy._town_hold.claims
        claim = register.declare("cross-town", reach_place("town:1"))
        register.declare_execution(
            claim.claim_id, work_id="cross-town-shopping:travel:1",
            producer="cross-town", state="awaiting", expected_effect="arrive-town:1",
        )
        policy._observe_cross_town_shopping_arrival(snap)
        self.assertEqual(register.current.closed, "complete")
        self.assertFalse(policy._defer_town_errand("store-router", "procurement-decision"))

    def test_finished_q2_return_also_yields(self):
        policy = shopping_policy()
        policy._telmora_q2_errand = True
        snap = board()
        policy._build_grid_index(snap)
        self.assertIsNone(policy._telmora_q2_travel_key(
            snap, QuestState(2, status=QUEST_STATUS_FINISHED),
        ))

    def test_observed_stockout_releases_quest_return(self):
        policy = shopping_policy()
        snap = board()
        policy._build_grid_index(snap)
        policy._observe_cross_town_shopping_arrival(snap)
        policy._town_visit_ledger.shelf_observations[(STORE_ALCHEMIST, "identification-source:full")] = ()
        self.assertFalse(_shopping_holds(policy, snap))
        self.assertEqual(policy._fixed_quest_key(snap, []), "7")

    def test_affordable_shelf_keeps_shopping_owner(self):
        policy = shopping_policy()
        policy._town_visit_ledger.shelf_observations[(STORE_ALCHEMIST, "identification-source:full")] = ((11815, 1),)
        self.assertIsNone(_quest_entry(policy, board()))

    def test_fare_does_not_change_durable_progress_or_retirement_key(self):
        policy = HengbotPolicy()
        snap = board()
        policy._build_grid_index(snap)
        before = policy._town_arbiter_progress_vector(snap, "fixedquest:q2-teleport")
        spent = replace(snap, player=replace(snap.player, gold=snap.player.gold - 500))
        self.assertEqual(before, policy._town_arbiter_progress_vector(spent, "fixedquest:q2-teleport"))
        self.assertEqual(policy._town_progress_fingerprint(snap), policy._town_progress_fingerprint(spent))
        # Preserve other economic progress: experience still changes the vector.
        gained = replace(spent, player=replace(spent.player, exp=spent.player.exp + 1))
        self.assertNotEqual(before, policy._town_arbiter_progress_vector(gained, "fixedquest:q2-teleport"))

    def test_alternating_spenders_retire_and_spending_cannot_clear_retirement(self):
        policy = HengbotPolicy()
        snap = board()
        policy._build_grid_index(snap)
        arbiter = policy._town_turn_arbiter
        reasons = {"quest-request": "fixedquest:q2-teleport",
                   "cross-town": "town:cross-town-shopping:travel-1"}
        bounds = sum(arbiter.registry[owner].budget for owner in reasons)
        for index in range(2 * (bounds + 1)):
            owner = tuple(reasons)[index % 2]
            current = replace(snap, player=replace(snap.player, gold=snap.player.gold - 500 * index))
            vector = policy._town_arbiter_progress_vector(current, reasons[owner])
            arbiter.observe(
                in_town=True, reason=reasons[owner], progress_vector=vector,
                retirement_key=vector,
                retirement_key_for=lambda name: policy._town_arbiter_progress_vector(current, reasons[name]),
            )
        self.assertEqual(set(arbiter._retired), set(reasons))
        spent = replace(snap, player=replace(snap.player, gold=655))
        for owner in reasons:
            self.assertEqual(arbiter._retired[owner], policy._town_arbiter_progress_vector(spent, reasons[owner]))
