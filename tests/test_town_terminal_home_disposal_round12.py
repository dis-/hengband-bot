"""The Home disposal dispatcher gives only its identify branch that terminal."""
import tests  # noqa: F401

from dataclasses import replace
import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from test_town_terminal_departure import policy_on
from test_town_terminal_identify_carried import carried_board


RUNG = "_home_disposal_processing_key"


class HomeDisposalTerminalTest(unittest.TestCase):
    def test_refusal_keeps_the_same_request_and_pending_sale_as_the_body(self):
        outcomes = []
        snap = carried_board()
        for mode in (tt.SHADOW, tt.ENFORCE):
            policy = policy_on(snap)
            policy._home_disposal_pending = (policy._item_signature(snap.inventory[0]), "sell")
            with patch.dict(tt.TERMINALS, {RUNG: tt.TERMINALS[RUNG]._replace(mode=mode)}), \
                    patch.object(policy, "_home_disposal_processing_key", wraps=policy._home_disposal_processing_key) as body:
                self.assertIsNone(policy._town_producer_entry(
                    RUNG, lambda: policy._home_disposal_processing_key(snap)))
            self.assertEqual(body.call_count, int(mode == tt.SHADOW))
            row, = policy._decision_terminal_admissions
            self.assertEqual(row["codes"], ["no-identification-source"])
            self.assertEqual(row["terminal"], ["home-disposal-identify", [policy._item_signature(snap.inventory[0])]])
            outcomes.append((policy._home_disposal_pending, policy._identification_need,
                             policy._identify_watch, policy.last_reason))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[1][1], "normal")
        self.assertEqual(tt.TERMINALS[RUNG].mode, tt.ENFORCE)

    def test_held_source_preserves_the_body_key_and_clears_the_request(self):
        snap = carried_board(source=True)
        policy = policy_on(snap)
        policy._home_disposal_pending = (policy._item_signature(snap.inventory[0]), "sell")
        policy._identification_need = "normal"
        key = policy._town_producer_entry(RUNG, lambda: policy._home_disposal_processing_key(snap))
        self.assertEqual(key, "rba")
        self.assertIsNone(policy._identification_need)
        self.assertEqual(policy.last_reason, "home-disposal:identify-before-sale")
        self.assertEqual(policy._decision_terminal_admissions, [])

    def test_missing_target_and_completed_identification_still_settle(self):
        for known in (False, True):
            snap = carried_board(full=known)
            policy = policy_on(snap)
            policy._home_disposal_pending = (policy._item_signature(snap.inventory[0]), "sell")
            if not known:
                snap = replace(snap, inventory=[])
                policy._begin_map_predicate_cache(snap)
            terminal = tt.rung_terminal(policy, RUNG, snap)
            self.assertEqual(terminal.terminal_id, tt.NO_REFUSAL)
            self.assertIsNone(policy._town_producer_entry(
                RUNG, lambda: policy._home_disposal_processing_key(snap)))
            self.assertEqual(policy._home_disposal_pending is None, not known)
            self.assertEqual(policy._decision_terminal_admissions, [])

    def test_destroy_branch_delegates_instead_of_requesting_identification(self):
        snap = carried_board()
        policy = policy_on(snap)
        policy._home_disposal_pending = (policy._item_signature(snap.inventory[0]), "destroy")
        self.assertEqual(tt.rung_terminal(policy, RUNG, snap).terminal_id, tt.NO_REFUSAL)
        with patch.object(policy, "_verified_destroy_key", return_value="destroy") as child:
            self.assertEqual(policy._town_producer_entry(
                RUNG, lambda: policy._home_disposal_processing_key(snap)), "destroy")
        child.assert_called_once()
        self.assertIsNone(policy._home_disposal_pending)
        self.assertIsNone(policy._identification_need)


if __name__ == "__main__":
    unittest.main()
