"""n1-a life-464 19:45:01 town:blocked:survival:depth_abilities.

The equipment session in Home took off 西方国のダガー (10885, main hand; its
known flags hold TR_FREE_ACT 46, the character's only Free Action) and
posted its deposit (10886); Home was full (「我が家にはもう置く場所がない。」).
The abandonment (10888) recorded the deposit as failed and that failure also
dropped the dagger's restoration, so it stayed in the pack and the town end
stopped with free_action missing for the 23F departure (10935).

A failed deposit refuses only Home's shelf: the abandoned session now restores
the item it took off, and the next outside board wields it again.
DECLARED RECONSTRUCTED: the session (takeoff then deposit of the dagger, at
its posted deposit) and its takeoff restoration entry, named by decisions
10885-10886; the policy primes on the recorded Home board after the takeoff.
Fixture: tests/extract_deposit_failure_restore_1102_fixture.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.equipment_optimizer import TR_FREE_ACT, equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP, PHASE_HOME_FINALIZE, EquipmentTransaction, EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import (
    EquipmentTransactionObservation, EquipmentTransactionSession,
)
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import recorded as executor_pins
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "deposit-failure-restore-1102.json.gz"
HOME_FULL = "我が家にはもう置く場所がない。"


class DepositFailureRestoreTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def test_failed_deposit_restores_the_taken_off_free_action_weapon(self):
        decisions = {d["decision_sequence"]: d for d in self.case["decisions"]}
        self.assertEqual((decisions[10885]["reason"], decisions[10885]["key"]),
                         ("equipment-transaction:takeoff", "ta"))
        self.assertEqual(decisions[10886]["key"], "do")
        self.assertIn(HOME_FULL, decisions[10887]["messages"])
        self.assertEqual(decisions[10935]["reason"], "town:blocked:survival:depth_abilities")
        self.assertEqual(decisions[10935]["departure_failed"], ["equipment_departure_ready"])

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        policy = _policy(Path(directory.name), monrace)
        board = lambda name: policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(self.case[name]), monrace))
        before = parse_snapshot(copy.deepcopy(self.case["before_takeoff"]), monrace)
        dagger = next(item for item in before.equipment if item.slot == "main_hand")
        self.assertIn(TR_FREE_ACT, dagger.known_flags)
        self.assertNotIn("free_action",
                         policy._missing_required_abilities(before, 23))
        after = parse_snapshot(copy.deepcopy(self.case["after_takeoff"]), monrace)
        policy.prime(after)
        policy.consume_skill_knowledge(
            {**self.case["skill"], "player": {"level": after.player.level}})
        policy.consume_home_knowledge(
            tuple(_parse_items(self.case["home"]["knowledge"]["items"], protocol=3)))
        self.assertIn("free_action", policy._missing_required_abilities(after, 23))

        # DECLARED RECONSTRUCTED: the recorded session at its posted deposit
        # and the takeoff's restoration entry.
        identity, move = equipment_identity(dagger), equipment_move_identity(dagger)
        item_id = f"equipped:{identity}:0"
        session = EquipmentTransactionSession(EquipmentTransactionPlan((
            EquipmentTransaction(PHASE_EQUIP, "takeoff", item_id, "main_hand", identity, move),
            EquipmentTransaction(PHASE_HOME_FINALIZE, "deposit", item_id, None, identity, move),
        ), (), 0), physical_context="home")
        session.index = 1
        self.assertTrue(session.dispatch(session.current_action,
                                         EquipmentTransactionObservation.create(
                                             in_home=True, pack_identities=tuple(
                                                 equipment_identity(i) for i in after.inventory))))
        policy._equipment_transaction_session = session
        policy._equipment_transaction_owned_items = [(move, "main_hand")]

        refused = board("deposit_refused")
        self.assertIn(HOME_FULL, refused.messages)
        policy.choose_key(refused)
        self.assertEqual(policy._equipment_transaction_owned_items, [(move, "main_hand")])
        self.assertTrue(policy._equipment_transaction_restoring)

        outside = board("outside")
        key = policy.choose_key(outside)
        self.assertEqual(policy.last_reason, "equipment-transaction:equip")
        pack_letter = next(item.slot for item in outside.inventory
                           if equipment_identity(item) == identity)
        self.assertTrue(key.startswith("w" + pack_letter), key)

        raw = self.case["outside"]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [copy.deepcopy(raw)]
        # DECLARED CONSTRUCTED: the wield spent one player turn.
        game.states[-1]["turn"] = raw["turn"] + 10
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": 10888, "reason": policy.last_reason},
            snapshot=outside, posting_contract=PostingContract(),
        )
        self.assertEqual("".join(game.accepted), key)
        self.assertTrue(sent, port.last_result.stop_line)


if __name__ == "__main__":
    import unittest
    unittest.main()
