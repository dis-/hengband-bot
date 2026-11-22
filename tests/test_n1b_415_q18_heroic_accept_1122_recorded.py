"""A quest's HP requirement reads the maximum HP without the timed additions
(n1-b life-415, Quest 18 accepted 2026-11-22 14:28:25).

Live (tests/extract_n1b_415_q18_heroic_accept_1122_fixture.py): the acceptance board (turn
1,949,448, decision 5197 ``fixedquest:request``) showed the status bar's ``heroism`` and a maximum
HP of 706; the first board after it ran out (turn 1,949,474) showed 696.  The game adds the
heroism's +10 after the base (player-status.cpp update_max_hitpoints: ``is_hero`` -> mhp += 10).
QUEST_18's first row (min_hp 700) was met by the potion; three game turns later only the second
row (min_hp 500) served and the entry was refused (the loop of n1-b life-415's 14:36 stop).

The quest gates now read ``permanent_max_hp``: the acceptance's row choice
(quest_force_rows.resolve), the strategy force's HP floor and its no-healing tier, the
projection readiness's HP budget, the opening Q1's no-healing tier, the supply gate's floors and
the ONCE quest floor's drained-below-the-row line.

The policy is n1-b life-415's own town-arrival checkpoint of 14:34:42
(tests/fixtures/n1b-415-q18-entry-walk-1122), six minutes after the acceptance board.

DECLARED CONSTRUCTED: the acceptance board decided by that later checkpoint (the checkpoint of
the acceptance's own visit was not kept: KEEP_VISITS); and, in the Berserker case, the expired
board with the class and the ``berserk`` bar set.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from hengbot.permanent_max_hp import permanent_max_hp
from hengbot.policy_constants import PLAYER_CLASS_BERSERKER
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
CHECKPOINT = FIXTURES / "n1b-415-q18-entry-walk-1122" / "n1b-415-1434"
BOARDS = FIXTURES / "n1b-415-q18-heroic-accept-1122.json.gz"
QUEST = 18


class N1b415Q18HeroicAccept1122RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.arrival, _recorded, _steps = load(CHECKPOINT, Path(scratch.name))
        raw = json.loads(gzip.decompress(BOARDS.read_bytes()))
        knowledge = cls.arrival._monrace_knowledge
        cls.accept = parse_snapshot(raw["accept"], knowledge)
        cls.expired = parse_snapshot(raw["expired"], knowledge)

    def policy(self):
        return copy.deepcopy(self.arrival)

    def test_the_boards_are_the_heroic_and_the_expired_one(self):
        self.assertEqual((self.accept.player.max_hp, self.accept.player.status_bar),
                         (706, ("heroism",)))
        self.assertEqual(self.expired.player.max_hp, 696)
        self.assertNotIn("heroism", self.expired.player.status_bar or ())

    def test_the_heroism_is_taken_off_the_maximum_hp(self):
        self.assertEqual(permanent_max_hp(self.accept.player), 696)
        self.assertEqual(permanent_max_hp(self.expired.player), 696)

    def test_the_acceptance_reads_the_row_of_the_maximum_hp_without_the_heroism(self):
        policy = self.policy()
        profile = policy.approved_quest_strategy(QUEST)
        force = policy._strategy_force_for_snapshot(self.accept, profile)
        self.assertEqual(force["min_hp"], 500)   # the second row; the first row asks 700
        self.assertEqual(force, policy._strategy_force_for_snapshot(self.expired, profile))

    def test_the_chooser_measures_696_on_the_acceptance_board(self):
        policy = self.policy()
        policy.choose_key(self.accept)
        readiness = policy._fixed_quest_readiness
        self.assertEqual(readiness["quest_id"], QUEST)
        self.assertEqual(readiness["strategy_force"]["hp"]["measured"], 696)

    def test_a_berserkers_own_berserk_stays_in_its_maximum_hp(self):
        player = dataclasses.replace(self.expired.player, class_id=PLAYER_CLASS_BERSERKER,
                                     status_bar=("berserk",))
        self.assertEqual(permanent_max_hp(player), 696)
        player = dataclasses.replace(self.expired.player, status_bar=("berserk", "heroism"))
        self.assertEqual(permanent_max_hp(player), 656)


if __name__ == "__main__":
    unittest.main()
