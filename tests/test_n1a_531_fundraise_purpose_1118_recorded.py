"""n1-a life-531 2026-11-18 18:15: the repetition remedy's walk-in opens the mining run's purpose.

The Lv36 warrior (1,232 gold, mining set ``mine``) traded one Word of Recall scroll for one or
two Home bolts per round trip between Home and the Yeek cave entrance until the town's
repetition block fired; its remedy entered the Yeek cave from the entrance
(``town:repetition-depart:enter``, policy_town).  Only the ordinary descent rung
(ladder_descent) opened a fundraising run's purpose and only a ``descend`` posting posted its
departure, so the run reached the first floor holding the previous run's finished purpose
(return complete) and the fundraising floor owner stopped on its first board as
``ownership:contract-conflict:fundraising:missing-purpose``.

Now every walk-in departure (``WALK_IN_DEPARTURE_REASONS``) opens the purpose and posts its
departure at the final envelope (``FundraisingMixin._post_fundraising_departure``), and the
floor owner mines.

Recorded: the visit's town-arrival checkpoint of 18:13:15 replayed to the board before row 272
(all 274 rows replay unchanged), its rows 272-273 and the Yeek cave 1F arrival the stop decided
on (tests/extract_n1a_531_fundraise_purpose_1118_fixture.py).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-fundraise-purpose-1118"
STOP = "ownership:contract-conflict:fundraising:missing-purpose"
PRIOR_PURPOSE = 45459
ENTRY_SEQUENCE = 66635


class N1a531FundraisePurpose1118RecordedTest(unittest.TestCase):
    def setUp(self):
        from hengbot.policy import staged_prompt_chain_matches
        self.scratch = TemporaryDirectory()
        # The replayed policy already read the arrival's calibration (row 0's replay);
        # adopting it again would reset what the replay loaded and diverge.
        self.policy, self.journal, steps = load(
            FIXTURE, Path(self.scratch.name), adopt_recorded_calibration=False)
        self.decided = []
        for recorded, supply in steps:
            board = supply()
            key = self.policy.choose_key(board)
            self.decided.append((recorded, board, key, self.policy.last_reason))
            if key:
                self.policy.confirm_key_posted(key)
                chain = self.policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    self.policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def tearDown(self):
        self.scratch.cleanup()

    def test_the_record(self):
        (_, travel, *_), (_, entry, *_), (stop, floor, *_) = self.decided
        self.assertTrue(travel.in_town and entry.in_town)
        self.assertEqual(self.journal[1]["reason"], "town:repetition-depart:enter")
        self.assertEqual(stop["reason"], STOP)
        self.assertEqual((floor.floor_key[0], floor.dungeon_level), (2, 1))
        self.assertEqual(entry.player.gold, 1232)

    def test_the_town_rows_replay(self):
        for recorded, _, key, reason in self.decided[:2]:
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]))

    def test_the_remedy_entry_opens_the_run_purpose(self):
        record = self.policy._fundraising_purpose_record
        purpose = self.policy._fundraising_run_purpose
        self.assertEqual(purpose.identity, ENTRY_SEQUENCE)
        self.assertNotEqual(purpose.identity, PRIOR_PURPOSE)
        self.assertEqual(record.purpose, purpose)
        self.assertEqual(record.status, "active")
        self.assertEqual(record.child.direction, "depart")
        self.assertEqual(record.child.state, "complete")

    def test_the_first_floor_board_is_mined_not_stopped(self):
        _, _, key, reason = self.decided[2]
        self.assertNotEqual(reason, STOP)
        self.assertFalse((reason or "").startswith("ownership:contract-conflict"))
        self.assertIsNotNone(key)


if __name__ == "__main__":
    unittest.main()
