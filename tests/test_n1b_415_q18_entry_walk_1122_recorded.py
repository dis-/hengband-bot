"""A refused quest entry is not walked to, and Q18's first row counts the absorbed Speed's doses
(n1-b life-415, 2026-11-22 14:36, loop-detected in the Outpost).

Live (n1-b life-415, Magic-Eater Lv34, build bot-53f7a340e,
tests/extract_n1b_415_q18_entry_walk_1122_fixture.py): Quest 18 『湖の洞窟』 was taken at 14:28:25
(decision 5197) with the Potion of Heroism's +10 on the maximum HP (706; 696 without it,
player-status.cpp: ``is_hero`` -> mhp += 10) and the absorbed Speed at 8 charges.  The first row
(min_hp 700, seventeen Speed doses) answered it: an absorbed Speed power stood for its doses with
no charge at all, since that row names no ``absorbed_charges``.  The heroism ran out three game
turns later; at 696 only the second row (min_hp 500, seventeen absorbed charges) served, the
absorbed Speed was short (8 < 17) and the entrance refused the entry (``quest:readiness:speed``).

That refusal was asked only on the step onto the entrance.  The walk to it
(QuestFloorNavigator.enter_from_town) won every other board, so the character walked across the
Outpost to the cell before Q18's entrance, was refused, the shops' errand took the board and its
walk away, and the walk to the entrance came back on the next board, until loop-detected.

Now every step of the walk waits on the entry's own admission (``_quest_entry_step_admitted``),
and an ``always_hasted`` row that names no ``absorbed_charges`` counts its own doses,
one charge a dose (quest_force_rows._speed_cost).

The rows are replayed through the public chooser, each posting its recorded key.

DECLARED CONSTRUCTED: the board of row 3 with the maximum HP the acceptance read (706, the
heroism's), for the first row's dose count; the acceptance board itself is not in the capture.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import quest_force_rows
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-415-q18-entry-walk-1122" / "n1b-415-1434"
WALK_ROW = 3          # live: quest:enter:approach, the first step toward Q18's entrance
QUEST = 18
HEROIC_MAX_HP = 706   # decision 5197, the acceptance of Q18


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1b415Q18EntryWalk1122RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Rows 0-2 posted as recorded; the policy and board of row 3."""
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURE, Path(scratch.name))
        cls.mismatches = []
        for row, supply in steps[:WALK_ROW]:
            board = supply()
            key = policy.choose_key(board)
            entry = recorded[row["row"]]
            if (key, policy.last_reason) != (entry["key"], entry["reason"]):
                cls.mismatches.append((row["row"], key, policy.last_reason))
            post(policy, entry["key"])
        cls.before_walk = policy
        cls.walk_board = steps[WALK_ROW][1]()
        cls.recorded = recorded

    def policy(self):
        return copy.deepcopy(self.before_walk)

    def test_rows_before_the_walk_replay_as_recorded(self):
        self.assertEqual(self.mismatches, [])
        self.assertEqual(self.recorded[WALK_ROW]["reason"], "quest:enter:approach")

    def test_the_entry_is_refused_for_the_absorbed_speed(self):
        policy = self.policy()
        self.assertTrue(quest_force_rows.departure_speed_short(policy, self.walk_board, QUEST))
        self.assertFalse(policy._quest_equipment_entry_allowed(self.walk_board, QUEST))
        self.assertEqual(policy.last_reason, "quest:readiness:speed")

    def test_the_refused_entry_is_not_walked_to(self):
        policy = self.policy()
        key = policy.choose_key(self.walk_board)
        self.assertFalse(policy.last_reason.startswith("quest:enter"), (key, policy.last_reason))
        self.assertFalse(policy.last_reason.startswith("fixedquest:"), (key, policy.last_reason))

    def test_the_first_row_counts_its_doses_in_absorbed_charges(self):
        policy = self.policy()
        board = dataclasses.replace(
            self.walk_board,
            player=dataclasses.replace(self.walk_board.player, max_hp=HEROIC_MAX_HP))
        profile = policy.approved_quest_strategy(QUEST)
        force = policy._strategy_force_for_snapshot(board, profile)
        self.assertEqual(force["min_hp"], 700)   # the first row serves at 706
        self.assertNotIn("speed_alternatives", force)
        self.assertTrue(force.get(quest_force_rows.ABSORBED_SHORT))
        self.assertFalse(policy._approved_strategy_force_ready(board, profile))
        self.assertIn("absorbed_speed_charges",
                      policy._fixed_quest_readiness["strategy_force"]["failed"])


if __name__ == "__main__":
    unittest.main()
