"""Equipment dispatch keeps recovery; command admission precedes preparation."""
import tests  # noqa: F401

from dataclasses import replace
import pickle
import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP, PHASE_HOME_PREPARE, EquipmentTransaction, EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import (
    EquipmentTransactionObservation, EquipmentTransactionSession,
)
from hengbot.policy_state import normalize_policy_state
from hengbot.item_reservation import ITEM_RESERVATION_SOURCES
from hengbot.home_visit import HomeVisitKind, HomeVisitRequest
from hengbot.model import STORE_HOME
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


RUNGS = {
    "_equipment_transaction_home_key", "_equipment_transaction_town_key",
    "_equipment_transaction_town_key#1", "_equipment_transaction_town_key#2",
    "_equipment_transaction_town_owner_key",
}


def command(*, home):
    snap = board()
    policy = policy_on(snap)
    action = EquipmentTransaction(
        PHASE_HOME_PREPARE if home else PHASE_EQUIP,
        "deposit" if home else "equip", "pack:item:0", "outer", "identity")
    session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 1))
    observation = EquipmentTransactionObservation.create(in_home=home, pack_identities=("identity",))
    policy._equipment_transaction_session = session
    return policy, snap, session, action, observation


class EquipmentCommandAdmissionTest(unittest.TestCase):
    def test_refused_preparation_does_not_suppress_the_callers_failure_commit(self):
        for home in (False, True):
            for refusal in ("blocked", "action", "surface", "prepared"):
                outcomes = []
                for mode in (tt.SHADOW, tt.ENFORCE):
                    policy, snap, session, action, observation = command(home=home)
                    if refusal == "blocked":
                        session.block("deposit-refused")
                    elif refusal == "action":
                        action = replace(action, item_id="other")
                    elif refusal == "surface":
                        observation = replace(observation, in_home=not home)
                    else:
                        self.assertTrue(session.prepare(action, observation, "older-key", ("older",)))
                    selected_rung = ("_equipment_transaction_home_key" if observation.in_home
                                     else "_equipment_transaction_town_key#1")
                    with patch.dict(tt.TERMINALS, {selected_rung: tt.TERMINALS[selected_rung]._replace(mode=mode)}), \
                            patch.object(session, "prepare", wraps=session.prepare) as prepare:
                        accepted = policy._prepare_equipment_transaction_command(
                            session, action, observation, "key", ("current",))
                    self.assertFalse(accepted)
                    self.assertEqual(prepare.call_count, int(mode == tt.SHADOW), (home, refusal, mode))
                    self.assertIsNone(policy._terminal_equipment_command)
                    row, = policy._decision_terminal_admissions
                    self.assertEqual(row["terminal"][0], "equipment-command")
                    self.assertEqual(row["codes"], ["equipment-dispatch-rejected"])
                    self.assertEqual(row["live"], [])
                    self.assertEqual(row["mode"], mode)
                    outcomes.append((session._prepared, policy._equipment_transaction_prepared_key,
                                     policy.last_reason, repr(policy._decision_offer_buffer())))
                self.assertEqual(outcomes[0], outcomes[1])

    def test_admitted_command_preserves_the_real_preparation_and_offer(self):
        for home in (False, True):
            policy, snap, session, action, observation = command(home=home)
            self.assertTrue(policy._prepare_equipment_transaction_command(
                session, action, observation, "key", ("current",)))
            self.assertEqual(session._prepared, (action, observation, "key", ("current",)))
            self.assertEqual(policy._equipment_transaction_prepared_key, "key")
            self.assertIsNone(session.pending_action)
            self.assertIsNone(policy._terminal_equipment_command)
            self.assertEqual(policy._decision_terminal_admissions, [])
            self.assertTrue(policy._decision_offer_buffer().steps)

    def test_material_and_terminal_reads_do_not_prepare_or_offer_a_command(self):
        policy, snap, session, action, observation = command(home=True)
        policy._terminal_equipment_command = (session, action, observation, "key", ("current",))
        before = pickle.dumps(vars(policy))
        terminal = tt.equipment_transaction_intended_terminal(policy, snap)
        material = tt.gather_equipment_command(policy, snap)
        for _ in range(2):
            self.assertEqual(tt.equipment_transaction_intended_terminal(policy, snap), terminal)
            self.assertEqual(tt.gather_equipment_command(policy, snap), material)
            self.assertTrue(tt.verdict_equipment_command(material).admitted)
            self.assertEqual(pickle.dumps(vars(policy)), before)

    def test_changed_prepared_context_is_not_hidden_by_the_admission_memo(self):
        policy, snap, session, action, observation = command(home=True)
        self.assertTrue(policy._prepare_equipment_transaction_command(
            session, action, observation, "key", ("current",)))
        session.discard_prepared()
        self.assertTrue(session.prepare(action, observation, "different", ("different",)))
        self.assertFalse(policy._prepare_equipment_transaction_command(
            session, action, observation, "key", ("current",)))
        row, = policy._decision_terminal_admissions
        self.assertEqual(row["codes"], ["equipment-dispatch-rejected"])

    def test_context_is_restored_after_an_exception_and_defaults_on_old_checkpoints(self):
        policy, snap, session, action, observation = command(home=False)
        previous = ("outer",)
        policy._terminal_equipment_command = previous
        with patch.object(session, "prepare", side_effect=RuntimeError("prepare failed")):
            with self.assertRaisesRegex(RuntimeError, "prepare failed"):
                policy._prepare_equipment_transaction_command(session, action, observation, "key", ())
        self.assertIs(policy._terminal_equipment_command, previous)
        del policy.__dict__["_terminal_equipment_command"]
        self.assertIsNone(normalize_policy_state(policy)._terminal_equipment_command)
        self.assertEqual(ITEM_RESERVATION_SOURCES["_terminal_equipment_command"][0], "selection")

    def test_transaction_home_route_asks_the_withdrawal_terminal_before_walking(self):
        policy, snap, _session, action, _observation = command(home=True)
        action = replace(action, kind="withdraw")
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 1))
        missing = ("missing shelf item", 70, 1)
        policy._home_visit.file(HomeVisitRequest(
            HomeVisitKind.WITHDRAW, "equipment-txn", missing, address=missing))
        policy._home_knowledge_current = True

        def route(*args, **kwargs):
            policy._shopping_approach_store_type = STORE_HOME
            return snap.player.position

        with patch.object(policy, "_prepare_equipment_optimization", return_value=None), \
                patch.object(policy, "_ensure_home_visit_request", return_value=True), \
                patch.object(policy, "_shopping_approach_step", side_effect=route):
            self.assertIsNone(policy._equipment_transaction_town_key(snap))
        row, = policy._decision_terminal_admissions
        self.assertEqual(row["rung"], "_shopping_approach_key")
        self.assertEqual(row["codes"], ["reservation-unavailable"])

    def test_every_dispatcher_keeps_its_recovery_and_observation_branches(self):
        snap = board()
        policy = policy_on(snap)
        for rung in RUNGS:
            self.assertEqual(tt.TERMINALS[rung].mode, tt.ENFORCE)
            self.assertNotIn(rung, tt.SHADOW_RUNGS)
            terminal = tt.rung_terminal(policy, rung, snap)
            self.assertEqual(terminal, tt.TerminalRef(tt.NO_REFUSAL, ("equipment-transaction-dispatch",)))
            self.assertTrue(tt.terminal_admission(policy, snap, terminal).admitted)


if __name__ == "__main__":
    unittest.main()
