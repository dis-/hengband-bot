"""Round 6: carried identification admission and its refusal confirmation.

Constructed boards use the goldburn town seam with a carried unknown sword
or a known ego sword awaiting full identification. No Home batch owns it.
SHADOW calls the real body; temporary ENFORCE exercises the future refusal
path and must leave the same identification state and execution offers.
"""

import tests  # noqa: F401

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import town_terminal
from hengbot.model import (
    STORE_ALCHEMIST, SV_SCROLL_IDENTIFY, SV_SCROLL_STAR_IDENTIFY,
    SV_STAFF_IDENTIFY, TVAL_SCROLL, TVAL_STAFF, TVAL_SWORD,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STAFF_IDENTIFY_MIN_SUCCESS
from hengbot.town_terminal import ADMIT, Server, TerminalRef
from policy_fixtures import item
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on
from test_town_terminal_refusal_commit import WATCHED


RUNG = "town-item-processing"


def carried_board(*, full=False, source=False):
    target = item("a", TVAL_SWORD, 1, name="carried sword", is_equipment=True,
                  known=full, is_ego=full)
    inventory = [target]
    if source:
        inventory.append(item("b", TVAL_SCROLL,
                              SV_SCROLL_STAR_IDENTIFY if full else SV_SCROLL_IDENTIFY,
                              name="identification scroll"))
    return replace(board(), inventory=inventory, equipment=[])


def refusal_result(snap, *, enforce, exhausted):
    policy = policy_on(snap)
    policy._home_procurement_batch_active = True
    if exhausted:
        policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
    decl = town_terminal.TERMINALS[RUNG]
    modes = {RUNG: town_terminal.TerminalDecl(
        decl.intended_terminal, town_terminal.ENFORCE if enforce else town_terminal.SHADOW)}
    offers, no_steps = [], []

    def producer():
        if enforce:
            raise AssertionError("refused body must not run")
        return policy._town_item_processing_dispatch_key(snap)

    with patch.dict(town_terminal.TERMINALS, modes), \
            patch.object(policy, "_offer_execution",
                         side_effect=lambda key, **kw: offers.append((key, kw))), \
            patch.object(policy, "_offer_execution_no_step",
                         side_effect=lambda **kw: no_steps.append(kw)):
        key = policy._town_producer_entry(RUNG, producer, family="identification")
    watched = (*WATCHED, "_unbuyable_full_identify_sigs", "_deferred_home_items",
               "_home_procurement_batch_active")
    writes = {name: repr(getattr(policy, name, None)) for name in watched}
    return writes, offers, no_steps, key


class CarriedIdentificationTest(unittest.TestCase):
    def test_source_and_body_agree_for_normal_and_full(self):
        for full in (False, True):
            for source in (False, True):
                with self.subTest(full=full, source=source):
                    snap = carried_board(full=full, source=source)
                    policy = policy_on(snap)
                    terminal = town_terminal.rung_terminal(policy, RUNG, snap)
                    self.assertEqual(terminal, TerminalRef(
                        "identify-carried", (policy._item_signature(snap.inventory[0]),)))
                    admission = town_terminal.terminal_admission(policy, snap, terminal)
                    self.assertEqual(admission.admitted, source)
                    key = policy._town_item_processing_key(snap)
                    self.assertEqual(key is not None, source)
                    rows = policy._decision_terminal_admissions
                    if source:
                        self.assertEqual(rows, [])
                    else:
                        self.assertEqual(rows[0]["codes"], ["no-identification-source"])
                        self.assertEqual(rows[0]["mode"], "enforce")
                        self.assertEqual(policy._identification_need,
                                         "full" if full else "normal")

    def test_exhausted_full_source_has_its_own_code_and_server(self):
        for source in (False, True):
            snap = carried_board(full=True, source=source)
            policy = policy_on(snap)
            policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
            terminal = town_terminal.rung_terminal(policy, RUNG, snap)
            admission = town_terminal.terminal_admission(policy, snap, terminal)
            self.assertEqual(admission.codes,
                             () if source else ("full-identification-exhausted",))
            self.assertEqual(admission.admitted, source)
        self.assertEqual(town_terminal.refusal_servers(("full-identification-exhausted",)),
                         (Server("cross-town"),))
        self.assertIn("full-identification-exhausted", town_terminal.TERMINAL_CODES)

    def test_refusal_commit_matches_the_body_for_each_confirmation(self):
        for full, exhausted in ((False, False), (True, False), (True, True)):
            with self.subTest(full=full, exhausted=exhausted):
                snap = carried_board(full=full)

                results = [refusal_result(snap, enforce=enforce, exhausted=exhausted)
                           for enforce in (False, True)]
                self.assertEqual(results[0], results[1])
                _writes, offers, no_steps, key = results[0]
                self.assertIsNone(key)
                self.assertEqual(_writes["_home_procurement_batch_active"], "False")
                if exhausted:
                    self.assertEqual(no_steps[-1]["cause"], "full-identification-deferred")
                    self.assertEqual(offers, [])
                else:
                    self.assertEqual(offers[-1][1]["arguments"][0],
                                     "full" if full else "normal")
                    self.assertEqual(no_steps, [])

    def test_other_flows_and_deferred_targets_have_no_terminal(self):
        snap = carried_board()
        signature = HengbotPolicy._item_signature(snap.inventory[0])
        for state in (
            {"_home_pending_item": signature},
            {"_home_pending_batch": [signature]},
            {"_deferred_home_items": {signature}},
            {"_unidentifiable_sigs": {signature}},
            {"_town_unidentifiable_carried_sigs": {signature}},
        ):
            with self.subTest(state=state):
                policy = policy_on(snap)
                for name, value in state.items():
                    setattr(policy, name, value)
                self.assertIsNone(town_terminal.rung_terminal(policy, RUNG, snap))
        for target in (
            replace(snap.inventory[0], known=True, fully_known=True),
            replace(snap.inventory[0], pseudo_feeling="average"),
            replace(snap.inventory[0], is_equipment=False),
        ):
            other = replace(snap, inventory=[target])
            self.assertIsNone(town_terminal.rung_terminal(policy_on(other), RUNG, other))
        outside = replace(snap, floor_key=(1, 1, 1), town_flag=False)
        self.assertIsNone(town_terminal.rung_terminal(policy_on(outside), RUNG, outside))

    def test_staff_uses_the_existing_success_boundary_without_advancing_watch(self):
        snap = carried_board()
        staff = item("b", TVAL_STAFF, SV_STAFF_IDENTIFY, name="Identify", charges=3)
        snap = replace(snap, inventory=[*snap.inventory, staff])
        for rate in (STAFF_IDENTIFY_MIN_SUCCESS - 0.01, STAFF_IDENTIFY_MIN_SUCCESS):
            with self.subTest(rate=rate):
                policy = policy_on(snap)
                with patch.object(policy, "_identify_staff_success_rate", return_value=rate):
                    terminal = town_terminal.rung_terminal(policy, RUNG, snap)
                    admission = town_terminal.terminal_admission(policy, snap, terminal)
                    self.assertEqual(admission.admitted, rate >= STAFF_IDENTIFY_MIN_SUCCESS)
                    self.assertIsNone(policy._identify_watch)
                    self.assertEqual(policy._identify_fail_streak, 0)
                    key = policy._town_item_processing_key(snap)
                    self.assertEqual(key is not None, admission.admitted)

    def test_material_read_binds_source_only_once_and_stages_no_command(self):
        snap = carried_board(source=True)
        policy = policy_on(snap)
        policy._identification_source_reservation = {
            "state": "awaiting-source", "kind": "normal", "baseline": {}}
        first = town_terminal.gather_identify_carried(policy, snap)
        self.assertEqual(town_terminal.verdict_identify_carried(first), ADMIT)
        before = repr(vars(policy))
        self.assertEqual(town_terminal.gather_identify_carried(policy, snap), first)
        self.assertEqual(repr(vars(policy)), before)
        self.assertIsNone(policy._staged_prompt_chain)


if __name__ == "__main__":
    unittest.main()
