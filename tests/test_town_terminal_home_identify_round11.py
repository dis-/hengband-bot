"""Round 11: the selected Home-relief item owns its identification terminal."""
import tests  # noqa: F401

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.model import STORE_HOME, StoreState, SV_STAFF_IDENTIFY, TVAL_STAFF
from hengbot.policy_constants import IDENTIFY_FAIL_LIMIT, STAFF_IDENTIFY_MIN_SUCCESS
from policy_fixtures import item
from test_town_terminal_departure import policy_on
from test_town_terminal_identify_carried import carried_board


RUNG = "home-full-identification"


def relief_policy(snap):
    policy = policy_on(snap)
    target = snap.inventory[0]
    policy._home_full_relief = {
        "sale": (policy._item_signature(target), None, 0),
        "withdrawn": True, "mode": "identify",
    }
    return policy, target


class HomeReliefIdentificationTest(unittest.TestCase):
    def test_the_selected_target_controls_the_source_tier(self):
        for full in (False, True):
            for source in (False, True):
                snap = carried_board(full=full, source=source)
                policy, target = relief_policy(snap)
                terminal = tt.rung_terminal(policy, RUNG, snap)
                self.assertEqual(terminal, tt.TerminalRef(
                    "home-full-identify", (policy._item_signature(target),)))
                admission = tt.terminal_admission(policy, snap, terminal)
                self.assertEqual(admission.admitted, source)
                self.assertEqual(admission.codes, () if source else ("no-identification-source",))
                self.assertEqual(policy._home_full_relief["mode"], "identify")
                self.assertIsNone(policy._identify_watch)

    def test_normal_sources_do_not_satisfy_a_full_identification(self):
        normal = carried_board(source=True)
        full = carried_board(full=True)
        snap = replace(full, inventory=[full.inventory[0], normal.inventory[1]])
        policy, target = relief_policy(snap)
        terminal = tt.rung_terminal(policy, RUNG, snap)
        self.assertFalse(tt.terminal_admission(policy, snap, terminal).admitted)
        self.assertIsNone(policy._home_full_identify_carried_key(snap, target))

    def test_missing_source_refuses_only_the_identification_body(self):
        for full in (False, True):
            outcomes = []
            for mode in (tt.SHADOW, tt.ENFORCE):
                snap = carried_board(full=full)
                policy, target = relief_policy(snap)
                decl = tt.TERMINALS[RUNG]._replace(mode=mode)
                with patch.dict(tt.TERMINALS, {RUNG: decl}), \
                        patch.object(policy, "_home_full_identify_carried_key",
                                     wraps=policy._home_full_identify_carried_key) as body:
                    key = policy._town_producer_entry(
                        RUNG, lambda: policy._home_full_identify_carried_key(snap, target),
                        family="identification")
                self.assertIsNone(key)
                self.assertEqual(body.call_count, int(mode == tt.SHADOW))
                row, = policy._decision_terminal_admissions
                self.assertEqual(row["terminal"], ["home-full-identify", [policy._item_signature(target)]])
                self.assertEqual(row["codes"], ["no-identification-source"])
                outcomes.append((policy._home_full_relief, policy._identify_watch,
                                 policy._identify_fail_streak, policy._identification_need))
            self.assertEqual(outcomes[0], outcomes[1])

    def test_held_source_runs_the_real_body_and_keeps_its_key(self):
        for full, expected in ((False, "rba"), (True, "rba" + "\x1b" * 8)):
            snap = carried_board(full=full, source=True)
            policy, target = relief_policy(snap)
            key = policy._town_producer_entry(
                RUNG, lambda: policy._home_full_identify_carried_key(snap, target),
                family="identification")
            self.assertEqual(key, expected)
            self.assertEqual(policy._decision_terminal_admissions, [])

    def test_staff_uses_the_existing_success_boundary_without_committing_a_watch(self):
        snap = carried_board()
        snap = replace(snap, inventory=[snap.inventory[0],
            item("b", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=3)])
        for rate in (STAFF_IDENTIFY_MIN_SUCCESS - 0.01, STAFF_IDENTIFY_MIN_SUCCESS):
            policy, target = relief_policy(snap)
            with patch.object(policy, "_identify_staff_success_rate", return_value=rate):
                terminal = tt.rung_terminal(policy, RUNG, snap)
                self.assertEqual(tt.terminal_admission(policy, snap, terminal).admitted,
                                 rate >= STAFF_IDENTIFY_MIN_SUCCESS)
            self.assertIsNone(policy._identify_watch)
            self.assertEqual(policy._identify_fail_streak, 0)

    def test_held_staff_still_commits_its_failure_watch_in_the_body(self):
        snap = carried_board()
        snap = replace(snap, inventory=[snap.inventory[0],
            item("b", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=3)])
        policy, target = relief_policy(snap)
        signature = policy._item_signature(target)
        policy._identify_watch = (signature, 1)
        policy._identify_fail_streak = IDENTIFY_FAIL_LIMIT - 1
        with patch.object(policy, "_identify_staff_success_rate",
                          return_value=STAFF_IDENTIFY_MIN_SUCCESS):
            key = policy._town_producer_entry(
                RUNG, lambda: policy._home_full_identify_carried_key(snap, target),
                family="identification")
        self.assertIsNone(key)
        self.assertIn(signature, policy._unidentifiable_sigs)
        self.assertIsNone(policy._identify_watch)
        self.assertEqual(policy._identify_fail_streak, 0)
        self.assertEqual(policy._decision_terminal_admissions, [])

    def test_inscription_changes_use_the_same_identity_as_the_relief_body(self):
        for old_name in ("carried sword", "carried sword {old}"):
            with self.subTest(old_name=old_name):
                snap = carried_board()
                old_target = replace(snap.inventory[0], name=old_name)
                policy, _ = relief_policy(replace(snap, inventory=[old_target]))
                target = replace(old_target, name="carried sword {new}")
                current = replace(snap, inventory=[target])
                self.assertEqual(policy._sale_item_identity(old_target),
                                 policy._sale_item_identity(target))
                terminal = tt.rung_terminal(policy, RUNG, current)
                self.assertEqual(terminal, tt.TerminalRef(
                    "home-full-identify", (policy._item_signature(target),)))
                self.assertEqual(tt.terminal_admission(policy, current, terminal).codes,
                                 ("no-identification-source",))

    def test_absent_or_departed_target_leaves_the_parent_to_settle_its_state(self):
        snap = carried_board()
        policy, _ = relief_policy(snap)
        for current in (replace(snap, inventory=[]),
                        replace(snap, store=StoreState(STORE_HOME, []))):
            self.assertIsNone(tt.rung_terminal(policy, RUNG, current))
        policy._home_full_relief["sale"] = None
        self.assertIsNone(tt.rung_terminal(policy, RUNG, snap))
        policy._home_full_relief = None
        self.assertIsNone(tt.rung_terminal(policy, RUNG, snap))


if __name__ == "__main__":
    unittest.main()
