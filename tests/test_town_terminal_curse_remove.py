"""ROOT-FIX S2-d: the worn-curse removal's terminal.

``_town_remove_curse_key`` declares ``("curse-remove", (kind,))`` while worn
gear is cursed in town.  The verdict follows the body's branches: a blind or
confused player cannot read (``cannot-read-scroll``, served by survival), no
carried scroll of the needed kind (``no-remove-curse-scroll``, served by the
remove-curse suppliers), no removable target (``cursed-item-unavailable``,
no town owner).  The rung is SHADOW until the S2 ENFORCE flip, so the
check is exact agreement with the body: the body reads the scroll exactly
when the verdict admits.

Board: the CONSTRUCTED goldburn seam (row 3512, Telmora; see
test_goldburn_shopping_constructed) with a DECLARED CONSTRUCTED cursed worn
sword and, per case, a carried Remove Curse scroll and blindness.
"""

import tests  # noqa: F401

import unittest
from dataclasses import replace

from hengbot import town_terminal
from hengbot.model import (SV_SCROLL_ENCHANT_WEAPON_TO_HIT, SV_SCROLL_REMOVE_CURSE, TVAL_BOW,
                           TVAL_SCROLL, TVAL_SWORD)
from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import REFUSAL_SERVERS, Server, TerminalRef
from policy_fixtures import item
from test_goldburn_shopping_constructed import board

RUNG = "_town_remove_curse_key"
TERMINAL = TerminalRef("curse-remove", ("remove-curse",))


def cursed_board(*, scroll, blind=False, cursed=True):
    snap = board()
    sword = item("weapon", TVAL_SWORD, 1, is_equipment=True, is_cursed=cursed)
    inventory = ([item("a", TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, name="Remove Curse")]
                 if scroll else [])
    return replace(snap, equipment=[sword], inventory=inventory,
                   player=replace(snap.player, blind=blind))


def run(snap):
    """(terminal, entry key, recorded rows) of one decision with the real body."""
    policy = HengbotPolicy()
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    terminal = town_terminal.rung_terminal(policy, RUNG, snap)
    key = policy._town_producer_entry(RUNG, lambda: policy._town_remove_curse_key(snap))
    return terminal, key, policy._decision_terminal_admissions


class CurseRemoveTerminalTest(unittest.TestCase):
    def test_no_curse_has_no_terminal(self):
        terminal, key, rows = run(cursed_board(scroll=True, cursed=False))
        self.assertIsNone(terminal)
        self.assertEqual((key, rows), (None, []))

    def test_scroll_held_admits_and_the_body_reads(self):
        terminal, key, rows = run(cursed_board(scroll=True))
        self.assertEqual(terminal, TERMINAL)
        self.assertIsNotNone(key)
        self.assertEqual(rows, [])

    def test_no_scroll_refuses_and_the_body_does_not_read(self):
        terminal, key, rows = run(cursed_board(scroll=False))
        self.assertEqual(terminal, TERMINAL)
        self.assertIsNone(key)
        row, = rows
        self.assertEqual((row["codes"], row["mode"]), (["no-remove-curse-scroll"], "enforce"))
        self.assertIn(Server("shop-buy", "remove-curse"),
                      REFUSAL_SERVERS["no-remove-curse-scroll"])

    def test_blind_refuses_before_the_scroll(self):
        terminal, key, rows = run(cursed_board(scroll=True, blind=True))
        self.assertEqual(terminal, TERMINAL)
        self.assertIsNone(key)
        self.assertEqual([row["codes"] for row in rows], [["cannot-read-scroll"]])
        self.assertEqual(REFUSAL_SERVERS["cannot-read-scroll"], (Server("survival"),))


ENCHANT = "_town_enchant_launcher_key"


def launcher_board(*, scroll, blind=False):
    snap = board()
    sling = item("bow", TVAL_BOW, 2, is_equipment=True, known=True)
    inventory = ([item("a", TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_HIT, name="Enchant")]
                 if scroll else [])
    return replace(snap, equipment=[sling], inventory=inventory,
                   player=replace(snap.player, blind=blind))


def run_enchant(snap):
    policy = HengbotPolicy()
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    terminal = town_terminal.rung_terminal(policy, ENCHANT, snap)
    key = policy._town_producer_entry(ENCHANT, lambda: policy._town_enchant_launcher_key(snap))
    return terminal, key, policy._decision_terminal_admissions


class EnchantLauncherTerminalTest(unittest.TestCase):
    """The launcher enchanting (same family): agreement with the body."""

    def test_scroll_held_admits_and_the_body_reads(self):
        terminal, key, rows = run_enchant(launcher_board(scroll=True))
        self.assertEqual(terminal.terminal_id, "enchant-launcher")
        self.assertIsNotNone(key)
        self.assertEqual(rows, [])

    def test_no_scroll_is_no_terminal_and_the_body_does_not_read(self):
        # Optional work: without a carried scroll nothing is refused.
        terminal, key, rows = run_enchant(launcher_board(scroll=False))
        self.assertIsNone(terminal)
        self.assertEqual((key, rows), (None, []))

    def test_blind_refuses(self):
        terminal, key, rows = run_enchant(launcher_board(scroll=True, blind=True))
        self.assertIsNone(key)
        self.assertEqual([row["codes"] for row in rows], [["cannot-read-scroll"]])

    def test_no_launcher_has_no_terminal(self):
        snap = replace(launcher_board(scroll=True), equipment=[])
        terminal, key, rows = run_enchant(snap)
        self.assertIsNone(terminal)
        self.assertEqual((key, rows), (None, []))


if __name__ == "__main__":
    unittest.main()
