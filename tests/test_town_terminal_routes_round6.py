"""Round 6: expedition, funding and departure admission on constructed boards.

The goldburn town seam supplies geometry; kit items, expedition and isolated
collaborator results are declared in each test. Production modes stay SHADOW.
"""

import tests  # noqa: F401

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.model import (
    Position, SV_LITE_LANTERN, SV_SCROLL_DETECT_TREASURE,
    SV_SCROLL_WORD_OF_RECALL, SV_DIGGING_SHOVEL, TVAL_DIGGING,
    TVAL_FOOD, TVAL_LITE, TVAL_SCROLL,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import FOOD_MIN_SVAL, TOWN_TELEPORT_COST
from hengbot.policy_types import MorivantFullIdentifyExpedition
from hengbot.policy_state import normalize_policy_state
from policy_fixtures import item
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


class Round6RouteTerminalTest(unittest.TestCase):
    def test_recall_leaves_and_noncommitting_read(self):
        snap = board()
        policy = policy_on(snap)
        seen = []
        with patch.object(policy, "_equipment_departure_ready",
                          side_effect=lambda snap, **kw: seen.append(kw) or True):
            tt.gather_recall_departure(policy, snap)
            policy._recall_town_departure_conjuncts(snap)
        self.assertEqual(seen, [{"commit": False}, {}])
        servers = {
            "combat_weapon_ready": tt.Server("equipment-txn"),
            "departure_home_pending_item_clear": tt.Server("home-errand"),
            "departure_home_pending_batch_clear": tt.Server("home-errand"),
            "departure_home_batch_review_clear": tt.Server("home-errand"),
            "departure_home_atomic_withdraw_clear": tt.Server("home-errand"),
            "departure_identification_need_clear": tt.Server("identification"),
        }
        for name, server in servers.items():
            self.assertEqual(tt.refusal_servers((f"departure:{name}",)), (server,))

    def test_read_refusal_does_not_arm_a_watch_or_read(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = replace(board(), inventory=[recall])
        for enforce in (False, True):
            with self.subTest(enforce=enforce):
                policy = policy_on(snap)
                name = "_read_dungeon_recall_scroll_key"
                decl = tt.TERMINALS[name]
                modes = {name: tt.TerminalDecl(
                    decl.intended_terminal, tt.ENFORCE if enforce else tt.SHADOW)}
                with patch.dict(tt.TERMINALS, modes), \
                        patch.object(policy, "_recall_town_departure_conjuncts",
                                     return_value={"combat_weapon_ready": False}), \
                        patch.object(policy, "_read_key", wraps=policy._read_key) as read:
                    key = policy._read_dungeon_recall_scroll_key(snap, recall)
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["rung"], name)
                self.assertEqual(row["codes"], ["departure:combat_weapon_ready"])
                self.assertEqual(read.call_count, 0 if enforce else 1)
                self.assertEqual(key is None, enforce)
                self.assertEqual(policy._dungeon_recall_issue_watch is None, enforce)

    def test_dungeon_return_read_passes_without_town_departure_gates(self):
        recall = item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snap = replace(board(), inventory=[recall], town_flag=False, floor_key=(2, 1, 0))
        policy = policy_on(snap)
        with patch.object(policy, "_recall_town_departure_conjuncts") as gate:
            key = policy._read_dungeon_recall_scroll_key(snap, recall)
        self.assertIsNotNone(key)
        gate.assert_not_called()
        self.assertEqual(policy._decision_terminal_admissions, [])
        self.assertEqual(policy._dungeon_recall_issue_watch[0], snap.floor_key)

    def test_special_dispatcher_normal_decision_uses_its_entry(self):
        policy = HengbotPolicy()

        def entry(name, producer, **kwargs):
            return "departure-entry" if name == "_town_special_key" else None

        with patch.object(policy, "_town_producer_entry", side_effect=entry), \
                patch.object(policy, "_shopping_approach_step", return_value=None), \
                patch.object(policy, "_town_special_key",
                             side_effect=AssertionError("entry must own dispatch")):
            self.assertEqual(policy.choose_key(board()), "departure-entry")

    def test_special_departure_declares_gate_and_defers_to_live_expedition(self):
        snap = board()
        policy = policy_on(snap)
        self.assertEqual(tt.rung_terminal(policy, "_town_special_key", snap),
                         tt.TerminalRef("departure-recall", ()))
        policy._morivant_full_identify = MorivantFullIdentifyExpedition(1, ())
        self.assertIsNone(tt.rung_terminal(policy, "_town_special_key", snap))
        policy._fundraising_mode = "prepare"
        self.assertEqual(tt.rung_terminal(policy, "_town_special_key", snap),
                         tt.TerminalRef("fundraising", ("prepare",)))

    def test_expedition_fare_and_route_are_separate_refusals(self):
        for destination, fare in ((0, TOWN_TELEPORT_COST), (2, 2 * TOWN_TELEPORT_COST)):
            for gold, reachable, codes in (
                (fare - 1, True, ("cross-town-fare-unaffordable",)),
                (fare, False, ("cross-town-route-unavailable",)),
                (fare, True, ()),
            ):
                with self.subTest(destination=destination, gold=gold, reachable=reachable):
                    snap = replace(board(), player=replace(board().player, gold=gold))
                    policy = policy_on(snap)
                    policy._morivant_full_identify = MorivantFullIdentifyExpedition(
                        destination, (), returning=True)
                    adjacent = Position(snap.player.position.y, snap.player.position.x + 1)
                    with patch.object(policy, "_town_teleport_building_positions",
                                      return_value=frozenset({adjacent})), \
                            patch.object(policy, "_town_teleport_building_route",
                                         return_value=object() if reachable else None):
                        terminal = tt.rung_terminal(policy, "town-teleport", snap)
                        self.assertEqual(terminal.args, (destination,))
                        self.assertEqual(tt.terminal_admission(policy, snap, terminal).codes, codes)
        self.assertEqual(tt.refusal_servers(("cross-town-fare-unaffordable",)),
                         (tt.Server("shop-sell", "organization-sale"), tt.Server("fundraising")))
        self.assertEqual(tt.refusal_servers(("cross-town-route-unavailable",)), ())

    def test_no_expedition_has_no_travel_terminal(self):
        snap = board()
        self.assertIsNone(tt.rung_terminal(policy_on(snap), "town-teleport", snap))

    def test_actual_issuer_and_destination_override_other_held_trips(self):
        snap = replace(board(), player=replace(board().player, gold=TOWN_TELEPORT_COST))
        for producer in ("cross-town", "store-router"):
            policy = policy_on(snap)
            policy._morivant_full_identify = MorivantFullIdentifyExpedition(1, ())
            # The selected trip goes home, costing one fare; the other held
            # Morivant trip would cost two. Geometry is an isolated route read.
            with patch.dict(tt.TERMINALS, {"town-teleport": tt.TERMINALS[
                    "town-teleport"]._replace(mode=tt.SHADOW)}), \
                    patch.object(policy, "_town_teleport_building_positions", return_value=None), \
                    patch.object(policy, "_town_teleport_dispatch_key", return_value="travel"):
                self.assertEqual(policy._town_teleport_key(snap, 0, producer=producer), "travel")
            self.assertIsNone(policy._terminal_town_travel)
            rows = policy._decision_terminal_admissions
            if producer == "cross-town":
                row, = rows
                self.assertEqual(row["terminal"], ["cross-town", [0]])
                self.assertEqual(row["codes"], ["cross-town-route-unavailable"])
            else:
                self.assertEqual(rows, [])

    def test_default_mode_refuses_the_actual_trip_before_dispatch(self):
        snap = replace(board(), player=replace(board().player, gold=TOWN_TELEPORT_COST))
        policy = policy_on(snap)
        with patch.object(policy, "_town_teleport_building_positions", return_value=None), \
                patch.object(policy, "_town_teleport_dispatch_key",
                             side_effect=AssertionError("refused trip must not dispatch")):
            self.assertIsNone(policy._town_teleport_key(snap, 0, producer="cross-town"))
        row, = policy._decision_terminal_admissions
        self.assertEqual((row["terminal"], row["codes"], row["mode"]),
                         (["cross-town", [0]], ["cross-town-route-unavailable"], "enforce"))
        self.assertIsNone(policy._terminal_town_travel)

    def test_restored_checkpoint_defaults_the_temporary_travel_context(self):
        policy = HengbotPolicy()
        self.assertIsNone(policy._terminal_town_travel)
        del policy.__dict__["_terminal_town_travel"]
        self.assertIsNone(normalize_policy_state(policy)._terminal_town_travel)

    def test_prepare_refuses_without_digger_but_scavenge_uses_held_detection(self):
        snap = board()
        policy = policy_on(snap)
        snap = replace(snap, inventory=[
            item("a", TVAL_FOOD, FOOD_MIN_SVAL),
            item("b", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
                 count=policy._mining_detection_scroll_target(snap)),
        ], equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=10000)])
        for mode, codes in (("prepare", ("fundraising-no-digging-tool",)), ("scavenge", ())):
            policy = policy_on(snap)
            policy._fundraising_mode = mode
            for rung in ("_fundraising_key#1", "_fundraising_key#2"):
                terminal = tt.rung_terminal(policy, rung, snap)
                self.assertEqual(terminal.terminal_id, "fundraising")
                self.assertEqual(tt.terminal_admission(policy, snap, terminal).codes, codes)
        self.assertEqual(tt.refusal_servers(("fundraising-no-digging-tool",)),
                         (tt.Server("home-errand", "stored-digger"),
                          tt.Server("shop-buy", "fundraising-digger")))

    def test_fundraising_material_names_each_missing_supply(self):
        policy = policy_on(board())
        policy._fundraising_mode = "prepare"
        admission = tt.verdict_fundraising(tt.gather_fundraising(policy, board()))
        self.assertEqual(admission.codes, (
            "fundraising-no-digging-tool", "fundraising-no-detection",
            "fundraising-no-food", "fundraising-no-light"))
        self.assertEqual(tt.verdict_fundraising(tt.FundraisingMaterial(
            False, False, False, False, False)).codes, ("fundraising-departure-unready",))

    def test_stockout_declares_the_run_only_for_exhausted_supply_leaves(self):
        snap = board()
        for failed, terminal_expected in (("recall_departure_ready", True),
                                           ("combat_weapon_ready", False)):
            policy = policy_on(snap)
            with patch.object(policy, "_recall_town_departure_conjuncts",
                              return_value={failed: False}), \
                    patch.object(policy, "procurement_requirements", return_value=[{
                        "item": "Word of Recall scrolls", "blocked_reason": "no-actionable-supplier"}]):
                terminal = tt.rung_terminal(policy, "supply-stockout-mining", snap)
                self.assertEqual(terminal is not None, terminal_expected)
                if terminal_expected:
                    self.assertEqual(terminal, tt.TerminalRef("fundraising", ("supply-stockout",)))
                    self.assertIn("fundraising-no-digging-tool",
                                  tt.terminal_admission(policy, snap, terminal).codes)

    def test_stockout_one_run_accepts_one_detection_scroll(self):
        snap = replace(board(), inventory=[
            item("a", TVAL_FOOD, FOOD_MIN_SVAL),
            item("b", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=1),
            item("c", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
        ], equipment=[item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=10000)])
        policy = policy_on(snap)
        with patch.object(policy, "_recall_town_departure_conjuncts",
                          return_value={"recall_departure_ready": False}), \
                patch.object(policy, "procurement_requirements", return_value=[{
                    "item": "Word of Recall scrolls", "blocked_reason": "no-actionable-supplier"}]):
            self.assertIsNotNone(policy._supply_stockout_mining_key(snap))
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._planned_mining_runs, 1)
        self.assertEqual(policy._decision_terminal_admissions, [])


if __name__ == "__main__":
    unittest.main()
