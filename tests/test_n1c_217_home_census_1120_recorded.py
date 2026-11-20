"""n1-c life-217 2026-11-20 23:30:21: the 99F/100F readiness counted no Home on the arrival board.

Recorded: n1-c's town arrival (turn 6740502; tests/fixtures/n1c-217-home-census-1120): the
restored policy has no current Home census on the arrival board (``_home_knowledge_items`` empty),
so angband_finale ``owned`` counted the pack alone (Restore Mana 0 of 42, *Healing* 0 of 15, Healing
9 of 30, Resistance 11 of 20, Teleportation 24 of 40); the visit's second board brought the census
(239 items) with Restore Mana 120, Healing 35, *Healing* 16, Resistance 223 at Home (the Home screen
at turn 6760578: Restore Mana 99 + 21, *Healing* 16, Resistance 99 + 99 + 25) and no
Teleportation.  The switch (owner 2026-11-20 「上限を外す時に初めて着け替える」) is decided only as a
visit begins, so supplies kept at Home could never switch.

Now the Home counts are kept across the trip (the Home does not change while away) and counted on
the next arrival; with no census kept yet, the visit's first board with a current census decides
(the equipment work waits for that census, so no swap has begun before it).

DECLARED CONSTRUCTED:
* ``next_arrival``: the visit's last board as a dungeon board (Angband 95F) and then again as a
  town board with no current census (the policy's census flag cleared), each observed;
* ``with_teleports``: 16 Teleportation scrolls added to the recorded census (the Home's 0 made 16,
  so that 24 + 16 complete the supplies).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale
from hengbot.model import DUNGEON_ANGBAND, SV_SCROLL_TELEPORT, TVAL_SCROLL
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-home-census-1120"
HOME_SCREEN = {"restore_mana": 120, "star_healing": 16, "resistance": 223}


def owned_counts(policy):
    return {name: row["measured"] for name, row in angband_finale.memory(policy).report["owned"].items()}


class N1c217HomeCensusRecordedTest(unittest.TestCase):
    def setUp(self):
        """Each test replays from the arrival: a board is supplied in the journal's order, its
        response lines (the Home scan's) read as the live run read them."""
        self.scratch = TemporaryDirectory()
        self.policy, self.journal, self.steps = load(FIXTURE, Path(self.scratch.name))
        self.boards = []

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def play(self, policy, rows):
        for row in rows:
            board = self.steps[row][1]()
            self.boards.append(board)
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            recorded = self.journal[row]
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]), row)
            policy.confirm_key_posted(recorded["key"])

    def next_arrival(self, policy):
        last = self.boards[-1]
        dungeon = replace(last, floor_key=(DUNGEON_ANGBAND, 95, 0), town_flag=False)
        angband_finale.observe(policy, dungeon)
        policy._home_knowledge_current = False
        angband_finale.observe(policy, last)

    def with_teleports(self, policy):
        scroll = next(item for item in policy._home_knowledge_items if item.tval == TVAL_SCROLL)
        policy._home_knowledge_items = (*policy._home_knowledge_items,
                                        replace(scroll, sval=SV_SCROLL_TELEPORT, count=16,
                                                name="テレポートの巻物"))

    def test_the_census_is_counted_and_kept_for_the_next_arrival(self):
        policy = self.policy
        self.assertFalse(policy._home_knowledge_current)
        self.play(policy, range(len(self.steps)))
        counts = owned_counts(policy)
        kinds = {"restore_mana": angband_finale.RESTORE_MANA, "star_healing": angband_finale.STAR_HEALING,
                 "resistance": angband_finale.RESISTANCE}
        self.assertEqual({name: angband_finale.home_count(policy, kind) for name, kind in kinds.items()},
                         HOME_SCREEN)
        self.assertEqual(angband_finale.home_count(policy, angband_finale.TELEPORT), 0)
        self.assertEqual(counts["teleport"], 24)  # none at Home: still short of 40
        # The next arrival has no census: the kept counts stand in for it.
        self.next_arrival(policy)
        self.assertFalse(policy._home_knowledge_current)
        self.assertEqual(owned_counts(policy), counts)

    def test_the_switch_on_the_next_arrival_from_the_kept_counts(self):
        policy = self.policy
        self.play(policy, range(len(self.steps)))
        self.with_teleports(policy)
        self.play_census_board(policy)
        self.assertTrue(angband_finale.supplied(policy))
        self.next_arrival(policy)
        self.assertTrue(angband_finale.switching(policy))

    def test_no_census_kept_the_first_census_board_decides(self):
        """A first visit with no kept counts (a checkpoint from before this change): the arrival
        decides nothing, the visit's first board with a current census does, once."""
        policy = self.policy
        held = angband_finale.memory(policy)
        held.in_town, held.home_counts = False, None  # DECLARED: the board before was a dungeon board
        self.play(policy, [0])
        self.assertFalse(held.decided)
        self.assertFalse(angband_finale.switching(policy))
        policy_with_census = policy
        self.play(policy_with_census, [1])
        self.assertTrue(held.decided)
        self.assertFalse(angband_finale.switching(policy))  # decided: the teleports are short
        # The same first census with the supplies complete switches there (the decision taken
        # again on that board, the Teleportation added).
        self.with_teleports(policy)
        held.decided, held.switching = False, False
        angband_finale.observe(policy, self.boards[1])
        self.assertTrue(angband_finale.switching(policy))
        # Once decided, a later board of the visit decides nothing more.
        policy._home_knowledge_items = tuple(item for item in policy._home_knowledge_items
                                             if item.tval != TVAL_SCROLL or item.sval != SV_SCROLL_TELEPORT)
        self.play(policy, [2])
        self.assertTrue(angband_finale.switching(policy))

    def play_census_board(self, policy):
        angband_finale.observe(policy, self.boards[-1])


if __name__ == "__main__":
    unittest.main()
