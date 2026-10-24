"""Round 11: departure remedies survive admission; only a read is gated."""
import tests  # noqa: F401

import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.model import DUNGEON_ANGBAND
from tests import test_policy_town as town_fixtures
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


REGRESSION_METHODS = (
    'tests.test_policy_town.NoSafeRecallDestinationTest.test_drive_ending_town_terminals_survive_decision_rederivation',
    'tests.test_policy_town.NoSafeRecallDestinationTest.test_exhausted_equipment_home_route_emits_named_terminal_publicly',
    'tests.test_policy_town.NoSafeRecallDestinationTest.test_no_town_work_latches_visible_terminal',
    'tests.test_policy_town.TownAndFundraisingPolicyTest.test_live_capture_home_scan_incomplete_never_reads_recall_after_restart',
    'tests.test_policy_town.TownRecallReturnTest.test_each_departure_conjunct_is_the_exact_failed_telemetry_leaf',
    'tests.test_policy_shop.ShopPurchaseSellPolicyTest.test_unknown_device_waits_for_home_catalogue_before_deferral',
    'tests.test_policy_shop.TownErrandPlanTest.test_non_home_leave_blocks_reopened_out_of_stock_stop',
    'tests.test_policy_equipment.ConfirmedLoadoutPublicPathPinTest.test_dual_shovel_incident_refuses_through_choose_key',
    'tests.test_policy_equipment.ConfirmedLoadoutPublicPathPinTest.test_home_upgrade_invalidates_confirmation_through_choose_key',
    'tests.test_policy_equipment.ConfirmedLoadoutPublicPathPinTest.test_light_only_home_upgrade_refuses_through_choose_key',
    'tests.test_policy_equipment.ConfirmedLoadoutPublicPathPinTest.test_light_only_pack_incident_refuses_through_choose_key',
    'tests.test_policy_equipment.ConfirmedLoadoutPublicPathPinTest.test_record_fail_closed_shapes_refuse_through_choose_key',
    'tests.test_policy_equipment.ConfirmedLoadoutPublicPathPinTest.test_write_oserror_allows_completion_but_not_fresh_process',
    'tests.test_ability_sources_incident.AbilitySourcesIncidentTest.test_depth34_pre_recall_town_snapshot_refuses_public_departure',
)


class DepartureDispatcherTest(unittest.TestCase):
    def test_shadow_and_enforce_preserve_all_49_regression_conditions(self):
        original = HengbotPolicy.choose_key
        targets = ("_town_special_key", "_read_dungeon_recall_scroll_key")
        for name in REGRESSION_METHODS:
            traces = []
            for mode in (tt.SHADOW, tt.ENFORCE):
                trace = []

                def choose(policy, *args, **kwargs):
                    key = original(policy, *args, **kwargs)
                    trace.append((key, policy.last_reason, policy._town_blocked_reason,
                                  sorted(map(repr, policy._deferred_device_items)),
                                  policy._home_knowledge_current))
                    return key

                decls = {rung: tt.TERMINALS[rung]._replace(mode=mode) for rung in targets}
                result = unittest.TestResult()
                with patch.dict(tt.TERMINALS, decls), \
                        patch.object(HengbotPolicy, "choose_key", choose):
                    unittest.defaultTestLoader.loadTestsFromName(name).run(result)
                self.assertEqual(result.testsRun, 1, (name, mode))
                self.assertEqual(result.errors, [], (name, mode))
                self.assertEqual(result.failures, [], (name, mode))
                self.assertTrue(trace, name)
                traces.append(trace)
            self.assertEqual(traces[0], traces[1], name)

    def test_dispatch_is_a_named_no_refusal_but_the_read_owns_departure(self):
        snap = board()
        policy = policy_on(snap)
        for mode in (None, "prepare", "mine", "scavenge"):
            policy._fundraising_mode = mode
            terminal = tt.rung_terminal(policy, "_town_special_key", snap)
            self.assertEqual(terminal, tt.TerminalRef(tt.NO_REFUSAL, ("town-special-dispatch",)))
            self.assertTrue(tt.terminal_admission(policy, snap, terminal).admitted)
        policy._terminal_town_recall_read = True
        self.assertEqual(tt.rung_terminal(policy, "_town_special_key", snap),
                         tt.TerminalRef("departure-recall", ()))

    def test_read_refusal_precedes_watch_and_offer_and_restores_context(self):
        for mode in (tt.SHADOW, tt.ENFORCE):
            policy, snap = town_fixtures.TownRecallReturnTest()._ready_town(
                8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True)
            policy._build_grid_index(snap)
            policy._map_predicate_snapshot = snap
            decl = tt.TERMINALS["_town_special_key"]._replace(mode=mode)
            with patch.dict(tt.TERMINALS, {"_town_special_key": decl}), \
                    patch.object(policy, "_recall_town_departure_conjuncts",
                                 side_effect=lambda board, **kw: {
                                     "combat_weapon_ready": kw.get("commit") is not False}), \
                    patch.object(policy, "_read_key", wraps=policy._read_key) as read:
                key = policy._town_special_key(snap)
            self.assertFalse(policy._terminal_town_recall_read)
            row, = policy._decision_terminal_admissions
            self.assertEqual(row["terminal"], ["departure-recall", []])
            self.assertEqual(row["codes"], ["departure:combat_weapon_ready"])
            self.assertEqual(row["mode"], mode)
            if mode == tt.ENFORCE:
                self.assertIsNone(key)
                self.assertIsNone(policy._town_recall_issue_watch)
                self.assertIsNone(policy._pending_recall_dungeon_id)
                read.assert_not_called()
            else:
                self.assertEqual(key, "rra")
                self.assertIsNotNone(policy._town_recall_issue_watch)
                read.assert_called_once()

    def test_raised_read_restores_context(self):
        policy, snap = town_fixtures.TownRecallReturnTest()._ready_town(
            8, DUNGEON_ANGBAND, DUNGEON_ANGBAND, angband_unlocked=True)
        policy._build_grid_index(snap)
        policy._map_predicate_snapshot = snap
        with patch.object(policy, "_read_key", side_effect=RuntimeError("read failed")):
            with self.assertRaisesRegex(RuntimeError, "read failed"):
                policy._town_special_key(snap)
        self.assertFalse(policy._terminal_town_recall_read)

    def test_old_checkpoint_defaults_the_read_context(self):
        policy = HengbotPolicy()
        self.assertFalse(policy._terminal_town_recall_read)
        del policy.__dict__["_terminal_town_recall_read"]
        self.assertFalse(normalize_policy_state(policy)._terminal_town_recall_read)


if __name__ == "__main__":
    unittest.main()
