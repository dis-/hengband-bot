"""A Rogue's 鑑定 at 42% identifies where a failure is safe (supervisor 2026-11-27).

Owner 2026-11-27: 「仙術を選んだのに鑑定の杖をまだ持ってる理由は？」.  Supervisor's rule: a failed 鑑定
costs only its mana and a turn, so it is retried where safe (the town, or no hostile in view or
sensed) from 30% (realm_spells.IDENTIFY_SPELL_MIN_SUCCESS), up to IDENTIFY_SPELL_RETRY_LIMIT misses
on one item, then a carried staff; the Identify staff requirement drops and at most one staff is
kept as the backup while the spell is below 80%.

Recorded: ``n1a-545-identify-top-up-1127`` (tests/extract_n1a_545_identify_top_up_1127_fixture.py,
n1-a life-545 Amberite Rogue CL21, 鑑定 learned at 58% fail, MP 50): row 1 used the 10-charge
Identify staff on an unknown mushroom (``uoe``) in town.  ``n1a-535-identify-staff-buy-1122``
(a Warrior) and ``n1b-416-finale-bm-entry-1124`` (a Magic-Eater) for the classes without the spell.

DECLARED CONSTRUCTED: ``test_town_retries_the_spell_then_uses_the_staff`` decides row 1's board
again with the turn advanced and the mana a failed cast leaves (35) or a rest restores (50), the
mushroom still unknown (the casts missed); ``test_dungeon_uses_the_staff_with_a_hostile_in_view``
moves row 1's board to Angband 10F and adds one awake hostile in view.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import realm_spells
from hengbot.model import MonsterState, Position
from hengbot.policy_constants import STAFF_IDENTIFY_MAX_COUNT
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
ROGUE = FIXTURES / "n1a-545-identify-top-up-1127"
WARRIOR = FIXTURES / "n1a-535-identify-staff-buy-1122"
MAGIC_EATER = FIXTURES / "n1b-416-finale-bm-entry-1124"
CAST = "mbbe"   # m, the Sorcery book 2 in slot b, 鑑定 (spell 9: letter b), the mushroom e
STAFF = "uoe"   # the recorded use of the 10-charge Identify staff in slot o


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    if key:
        policy.confirm_key_posted(key)
    return key, policy.last_reason


class RogueIdentifySpell1127RecordedTest(unittest.TestCase):
    def first_board(self, fixture, row=1):
        """(policy, the board of ``row``) after the recorded rows before it."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(fixture, Path(scratch.name))
        for recorded, supply in steps[:row]:
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(supply())
            policy.confirm_key_posted(recorded["key"])
        return policy, steps[row][0], steps[row][1]()

    def test_the_spell_replaces_the_staff_requirement(self):
        policy, recorded, board = self.first_board(ROGUE)
        self.assertEqual(recorded["key"], STAFF)
        self.assertEqual(realm_spells.success(policy, board, realm_spells.IDENTIFY), 42)
        self.assertTrue(realm_spells.identify_usable(policy, board))
        self.assertFalse(realm_spells.identify_reliable(policy, board))
        self.assertTrue(policy._identify_staff_ready(board))
        self.assertNotIn("Identify staff charges",
                         [row["item"] for row in policy.procurement_requirements(board)])
        # One backup staff while the spell is below 80%.
        self.assertEqual(policy._identify_staff_carry_cap(board), 1)

    def test_town_retries_the_spell_then_uses_the_staff(self):
        policy, _recorded, board = self.first_board(ROGUE)
        keys = []
        turn = board.turn
        for step in range(8):
            turn += 10
            mana = board.player.max_mp if step % 2 == 0 else board.player.max_mp - 15
            keys.append(decide(policy, replace(
                board, turn=turn, player=replace(board.player, mp=mana))))
        casts = [key for key, reason in keys[0::2]]
        self.assertEqual(casts, [CAST] * realm_spells.IDENTIFY_SPELL_RETRY_LIMIT + [STAFF])
        self.assertTrue(all(reason == "town:recover" for _key, reason in keys[1::2]))

    def test_dungeon_uses_the_staff_with_a_hostile_in_view(self):
        policy, _recorded, board = self.first_board(ROGUE)
        dungeon = replace(board, floor_key=(1, 10, 0), town_flag=False, store=None)
        self.assertFalse(dungeon.in_town)
        command, source = policy._find_identification_source(dungeon, full=False)
        self.assertTrue(realm_spells.is_spell_means(source))
        here = dungeon.player.position
        orc = MonsterState(index=1, position=Position(here.y, here.x + 3), hp=20, max_hp=20,
                           distance=3, friendly=False, pet=False, name="orc", level=10)
        threatened = replace(dungeon, visible_monsters=[orc])
        self.assertFalse(realm_spells.identify_cast_safe(threatened))
        command, source = policy._find_identification_source(threatened, full=False)
        self.assertEqual((command, source.slot), ("u", "o"))

    def test_warrior_and_magic_eater_are_unchanged(self):
        for fixture in (WARRIOR, MAGIC_EATER):
            with self.subTest(fixture=fixture.name):
                policy, _recorded, board = self.first_board(fixture, row=0)
                self.assertFalse(realm_spells.identify_usable(policy, board))
                self.assertIsNone(realm_spells.identify_retry_means(policy, board))
                self.assertEqual(policy._identify_staff_carry_cap(board), STAFF_IDENTIFY_MAX_COUNT)


if __name__ == "__main__":
    unittest.main()
