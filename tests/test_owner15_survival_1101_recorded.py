"""#47: the owner answers of 2026-11-01 17h on the survival rungs.

Memory owner-answers-15-decisions-20261101 (answers 1-5, each the
recommended option); diagnosis LUNA-DIAG-owner15-survival-1101.txt.

Boards: n1-c life-085 (tests/fixtures/death-n1c-085-1101.json.gz, the D57
extraction; Lv18 zombie Magic-Eater, 236 max HP, 迷宮11階; the jelly
『スーパー・グレート・シルバー・ゼリー』 (race 1273, speed +10) touches the
player from (12,4) on boards 1445315-1445328 and from (8,6) on 1445613-1445625).
Every decision is the public ``choose_key``; posted keys go through the
production executor port (test_n1c_deaths_1101_recorded.PostedDeathKey).
DECLARED RECONSTRUCTED: the staff record and the lamp memory as in
test_n1c_deaths_1101_recorded.  DECLARED CONSTRUCTED, as each case states:
the light messages are stripped from the lit boards (so no light recovery
answers first); the unseen cases take the jelly out of the visible list and
name it as the game names a hidden actor, 「何か」 (monster-attack-player.cpp:
298-304, monster-describer.cpp); the arrow control replaces the messages by
mspell-bolt.cpp:21's 「何かが矢を放った。」; the recall-wait case sets
``player.recalling``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot import unseen_strike
from tests import test_n1c_deaths_1101_recorded as d57


JELLY_NAME = "『スーパー・グレート・シルバー・ゼリー』"
LIT_FIRST, LIT_LAST = 1445321, 1445328
ARROW = "何かが矢を放った。"


def lit_boards(*, unseen=False, arrow=False, recalling=False, afraid=False):
    """life-085's lit boards beside the jelly, without the light messages."""
    rows = d57.boards(d57.CASE_085, LIT_FIRST, LIT_LAST, light_messages=False)
    for raw in rows:
        raw["player"]["status"]["afraid"] = afraid
        if unseen:
            raw["visible_monsters"] = [m for m in raw["visible_monsters"]
                                       if m["race_id"] != d57.JELLY]
            raw["messages"] = [m.replace(JELLY_NAME, "何か") for m in raw["messages"]]
        if arrow:
            raw["messages"] = [ARROW]
        if recalling:
            raw["player"]["recalling"] = True
    return rows


class UnseenRetreatStrikeRecordedTest(d57.PostedDeathKey):
    """Answer 1 「近接で殴られたら反撃」: melee evidence is struck back."""

    def drive_lit(self, **construct):
        rows = lit_boards(unseen=True, **construct)
        # While recalling, the second hit in a row reads Teleportation
        # (urgent relocation, policy_combat.py); only the first is driven.
        return self.drive(d57.lamp_policy(), rows[:1] if construct.get("recalling") else rows)

    def test_constructed_board_is_an_unseen_melee_hit(self):
        raw = lit_boards(unseen=True)[0]
        self.assertEqual(raw["visible_monsters"], [])
        self.assertIn("何かに触られた。", raw["messages"])
        self.assertLess(raw["player"]["hp"], d57.CASE_085["boards"][0]["player"]["hp"])

    def test_unseen_retreat_strikes_the_melee_attacker(self):
        rows = self.drive_lit()
        # Unfixed: ('7', 'unseen:reverse-choke') on both boards, a walk away.
        for raw, key, reason in rows:
            self.assertEqual((key[0], reason), ("+", unseen_strike.RETREAT_REASON),
                             (raw["turn"], key, reason))

    def test_recall_wait_strikes_the_melee_attacker(self):
        raw, key, reason = self.drive_lit(recalling=True)[0]
        self.assertEqual(raw["turn"], LIT_FIRST)
        # Unfixed: ('7', 'unseen-recall:move').
        self.assertEqual((key[0], reason), ("+", unseen_strike.RECALL_REASON))

    def test_control_arrow_evidence_keeps_the_retreat(self):
        rows = self.drive_lit(arrow=True)
        self.assertEqual({reason for _raw, _key, reason in rows}, {"unseen:reverse-choke"})
        raw, key, reason = self.drive_lit(arrow=True, recalling=True)[0]
        self.assertEqual(reason, "unseen-recall:move")


if __name__ == "__main__":
    unittest.main()
