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
the next arrival, where the 99F/100F preparation phase (finale_prep) is entered from them and reads
the Home first; with no census kept yet, no phase is entered until a board with a current census
counts the supplies owned.

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

from hengbot import angband_finale, finale_prep
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

    def test_the_phase_on_the_next_arrival_from_the_kept_counts(self):
        """The kept counts let the preparation phase enter on the next arrival (finale_prep); its
        home step then reads the Home before anything is counted on it."""
        policy = self.policy
        self.play(policy, range(len(self.steps)))
        self.with_teleports(policy)
        self.play_census_board(policy)
        self.assertTrue(angband_finale.supplied(policy))
        self.next_arrival(policy)
        held = finale_prep.phase(policy)
        self.assertEqual(held.step, finale_prep.HOME)
        self.assertFalse(finale_prep.carrying(policy))
        policy._home_knowledge_scan_requested = False
        policy._home_knowledge_scan_epoch = None
        policy._home_knowledge_scan_inflight = False
        key = finale_prep.town_key(policy, self.boards[-1])
        self.assertEqual((key, policy.last_reason), ("~9\x1b", finale_prep.HOME_REASON))

    def test_no_census_kept_no_entry_until_one(self):
        """A first visit with no kept counts (a checkpoint from before them): the phase is not
        entered on the arrival; the visit's first board with a current census counts the Home,
        and the phase enters once the supplies are owned on it."""
        policy = self.policy
        memory = angband_finale.memory(policy)
        memory.home_counts = None  # DECLARED: no census kept
        finale_prep.phase(policy).in_town = False  # DECLARED: the board before was a dungeon board
        self.play(policy, [0])
        held = finale_prep.phase(policy)
        self.assertEqual(held.step, finale_prep.IDLE)
        self.play(policy, [1])
        self.assertEqual(held.step, finale_prep.IDLE)  # counted: the teleports are short
        self.with_teleports(policy)
        angband_finale.observe(policy, self.boards[1])
        self.assertNotEqual(held.step, finale_prep.IDLE)

    def play_census_board(self, policy):
        angband_finale.observe(policy, self.boards[-1])


if __name__ == "__main__":
    unittest.main()
