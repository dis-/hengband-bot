"""No summoner escape in town (n1-b life-411, Morivant, 2026-11-21 16:28-16:31).

Recorded (capture n1b-411-20261121-163136-loop-detected, the town-arrival checkpoint of 16:27:19,
tests/fixtures/n1b-411-town-summoner-wait-1121, the first 75 journal rows): back from 100F, at
full HP (1153/1153), n1-b walked toward a sleeping Mindcrafter (race 1055, Lv22, S_MONSTER) 9
cells away (town:kill-mob-approach).  On row 61 the dungeon's summoner escape latched
(emergency-summoner: a summoner that may summon next turn, asleep being no bar); it read Phase
Door, then walked toward an up stair the town does not have (emergency:seek-upstairs), and from
row 240 waited (emergency:wait) until the loop detector stopped the bot at 16:31:36.  The escape
leaves a floor; in town the town's own rungs answer the monster.

Replayed row by row through the journal (the CLI's resume reads on, as in the live process).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-town-summoner-wait-1121"
LATCH_ROW = 61


class N1b411TownSummonerWaitRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    def test_the_sleeping_town_summoner_latches_no_escape(self):
        policy, _journal, steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        policy._me_power_resume_reads = True  # the live CLI's
        decided = {}
        for recorded, supply in steps[:LATCH_ROW + 1]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            decided[recorded["row"]] = (key, policy.last_reason)
            posted = recorded["key"]
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
        self.assertTrue(board.in_town)
        self.assertTrue(any(monster.race_id == 1055 and monster.asleep
                            for monster in board.visible_monsters))
        _key, reason = decided[LATCH_ROW]  # recorded: emergency:phase
        self.assertFalse(reason.startswith("emergency:"), reason)
        self.assertFalse(policy._emergency_escape_pending)


if __name__ == "__main__":
    unittest.main()
