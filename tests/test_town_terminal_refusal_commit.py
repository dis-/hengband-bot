"""ROOT-FIX S2 (round 5 item 2): the refusal path performs the body's commit.

An ENFORCE refusal skips the producer, so the confirmation the body makes on
the same refusal (identify-equipped / identify-device: ``_request_identification``
or ``_defer_full_identification`` and the acquire-source offer; curse-remove and
enchant-launcher: the no-step offer naming the cause) moves to the entry's
refusal path (``town_terminal.commit_refusal``).  Each case runs the board
twice: SHADOW (the real body commits) and ENFORCE (the body is not called);
the identification writes and the execution offers must be the same.  Control:
an admitted terminal commits nothing on the refusal path.

Boards: the CONSTRUCTED goldburn seam (row 3512, Telmora) with the DECLARED
CONSTRUCTED items of the per-terminal test modules.
"""

import tests  # noqa: F401

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import town_terminal
from hengbot.model import TVAL_WAND
from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import ENFORCE, TerminalDecl
from policy_fixtures import item
from test_goldburn_shopping_constructed import board
from test_town_terminal_curse_remove import cursed_board, launcher_board
from test_town_terminal_identify_equipped import worn_board

WATCHED = ("_identification_need", "_identification_candidate",
           "_device_identification_candidate", "_deferred_full_identification")


def decide(rung, snap, body, *, enforce, prepare=None):
    """(identification writes, offers, no-step offers, key) of one decision."""
    policy = HengbotPolicy()
    if prepare is not None:
        prepare(policy)
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    offers, no_steps = [], []
    decl = town_terminal.TERMINALS[rung]
    mode = {rung: TerminalDecl(
        decl.intended_terminal, ENFORCE if enforce else town_terminal.SHADOW)}

    def producer():
        if enforce:
            raise AssertionError("an ENFORCE refusal must not call the body")
        return body(policy, snap)

    with patch.dict(town_terminal.TERMINALS, mode), \
            patch.object(policy, "_offer_execution",
                         side_effect=lambda key, **kw: offers.append((key, kw))), \
            patch.object(policy, "_offer_execution_no_step",
                         side_effect=lambda **kw: no_steps.append(kw)):
        key = policy._town_producer_entry(rung, producer)
    writes = {name: repr(getattr(policy, name, None)) for name in WATCHED}
    return writes, offers, no_steps, key


class RefusalCommitTest(unittest.TestCase):
    def assert_same_commit(self, rung, snap, body, prepare=None):
        shadow = decide(rung, snap, body, enforce=False, prepare=prepare)
        enforce = decide(rung, snap, body, enforce=True, prepare=prepare)
        self.assertIsNone(shadow[3])
        self.assertIsNone(enforce[3])
        self.assertEqual(enforce[:3], shadow[:3])
        self.assertTrue(shadow[1] or shadow[2])
        return enforce

    def test_identify_equipped_requests_a_source(self):
        writes, offers, _no_steps, _key = self.assert_same_commit(
            "_town_equipped_identification_key", worn_board(scroll=False),
            lambda policy, snap: policy._town_equipped_identification_key(snap, macro=True))
        self.assertIn("normal", writes["_identification_need"])
        self.assertEqual(offers[0][1]["next_step"], "identification.acquire-source")

    def test_identify_device_requests_a_source(self):
        snap = replace(board(), inventory=[
            item("a", TVAL_WAND, 1, aware=False, known=False, name="Wand")])
        writes, _offers, _no_steps, _key = self.assert_same_commit(
            "_town_device_processing_key", snap,
            lambda policy, snap: policy._town_device_processing_key(snap))
        self.assertNotEqual(writes["_device_identification_candidate"], "None")

    def test_curse_remove_names_the_cause(self):
        for snap, cause in ((cursed_board(scroll=False), "no-remove-curse-scroll"),
                            (cursed_board(scroll=True, blind=True), "cannot-read-scroll")):
            with self.subTest(cause=cause):
                _writes, _offers, no_steps, _key = self.assert_same_commit(
                    "_town_remove_curse_key", snap,
                    lambda policy, snap: policy._town_remove_curse_key(snap))
                self.assertEqual(no_steps[-1]["cause"], cause)

    def test_enchant_launcher_names_the_cause(self):
        _writes, _offers, no_steps, _key = self.assert_same_commit(
            "_town_enchant_launcher_key", launcher_board(scroll=True, blind=True),
            lambda policy, snap: policy._town_enchant_launcher_key(snap))
        self.assertEqual(no_steps[-1]["cause"], "enchant-context-unavailable")

    def test_admitted_terminal_commits_nothing_on_the_refusal_path(self):
        policy = HengbotPolicy()
        snap = worn_board(scroll=True)
        policy._build_grid_index(snap)
        policy._begin_map_predicate_cache(snap)
        policy._decision_sequence += 1
        terminal = town_terminal.rung_terminal(
            policy, "_town_equipped_identification_key", snap)
        with patch.object(policy, "_request_identification") as request:
            town_terminal.commit_refusal(policy, snap, None)
            self.assertTrue(town_terminal.terminal_admission(policy, snap, terminal).admitted)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
