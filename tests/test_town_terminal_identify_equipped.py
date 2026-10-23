"""ROOT-FIX S2-d: the worn-item identification's terminal.

``_town_equipped_identification_key`` declares
``("identify-equipped", (signature,))`` for the worn item the flow owns.  The
verdict refuses with ``no-identification-source`` when no reliable source of
the needed kind is carried (served by buying one, the Home withdrawal, or the
Morivant trip).  The rung is SHADOW until the S2 ENFORCE flip, so the check
is exact agreement with the body: the body identifies exactly when the
verdict admits.  The material read changes nothing on a second call.

Board: the CONSTRUCTED goldburn seam (row 3512, Telmora; see
test_goldburn_shopping_constructed) with a DECLARED CONSTRUCTED unidentified
worn sword and, per case, a carried Identify scroll.
"""

import tests  # noqa: F401

import unittest
from dataclasses import replace

from hengbot import town_terminal
from hengbot.model import SV_SCROLL_IDENTIFY, TVAL_SCROLL, TVAL_SWORD
from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import REFUSAL_SERVERS, Server
from policy_fixtures import item
from test_goldburn_shopping_constructed import board

RUNG = "_town_equipped_identification_key"


def worn_board(*, scroll, known=False):
    snap = board()
    sword = item("main_hand", TVAL_SWORD, 1, is_equipment=True, known=known,
                 fully_known=known)
    inventory = ([item("a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, name="Identify")]
                 if scroll else [])
    return replace(snap, equipment=[sword], inventory=inventory)


def run(snap):
    policy = HengbotPolicy()
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    terminal = town_terminal.rung_terminal(policy, RUNG, snap)
    key = policy._town_producer_entry(
        RUNG, lambda: policy._town_equipped_identification_key(snap, macro=True))
    return policy, terminal, key, policy._decision_terminal_admissions


class IdentifyEquippedTerminalTest(unittest.TestCase):
    def test_known_worn_gear_has_no_terminal(self):
        _policy, terminal, key, rows = run(worn_board(scroll=True, known=True))
        self.assertIsNone(terminal)
        self.assertEqual((key, rows), (None, []))

    def test_source_held_admits_and_the_body_identifies(self):
        policy, terminal, key, rows = run(worn_board(scroll=True))
        self.assertEqual(terminal.terminal_id, "identify-equipped")
        self.assertIsNotNone(key)
        self.assertEqual(rows, [])

    def test_no_source_refuses_and_the_body_requests_one(self):
        policy, terminal, key, rows = run(worn_board(scroll=False))
        self.assertEqual(terminal.terminal_id, "identify-equipped")
        self.assertIsNone(key)
        row, = rows
        self.assertEqual((row["codes"], row["mode"]),
                         (["no-identification-source"], "shadow"))
        self.assertIn(Server("shop-buy", "identification-source"),
                      REFUSAL_SERVERS["no-identification-source"])

    def test_second_material_read_does_not_write(self):
        snap = worn_board(scroll=True)
        policy = HengbotPolicy()
        policy._identification_source_reservation = {
            "state": "awaiting-source", "kind": "normal", "baseline": {}}
        first = town_terminal.gather_identify_equipped(policy, snap)
        before = repr(policy._identification_source_reservation)
        keys = set(vars(policy))
        self.assertEqual(town_terminal.gather_identify_equipped(policy, snap), first)
        self.assertEqual(repr(policy._identification_source_reservation), before)
        self.assertEqual(set(vars(policy)), keys)


if __name__ == "__main__":
    unittest.main()
