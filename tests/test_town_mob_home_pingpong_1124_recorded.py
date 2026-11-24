"""The walk to Home strikes the town hunt's adjacent monster (n1-c life-222, 2026-11-24 19:23-19:24).

Owner rule 2026-11-13 (pingpong-root-1113): two owners stepping opposite ways in turn are fixed at
the root, one verdict held, not by a guard constant.  n1-c life-222 (Lv23 Magic-Eater) came back
from the Orc cave 19F; the equipment transaction took off a ring (row 2), so it owns every town
decision (policy ``_decide``, ``_equipment_transaction_town_owner_key``) and walks to Home.  Its
store approach asks the town hunt first (``_town_clear_traveler_key``): the hunt walked toward a
戦傷兵士 (town:kill-mob-approach), and beside it handed the monster to the ladder's melee rung
(``adjacent-hostile-melee-delegated``) -- a rung this board never reaches -- so the approach
stepped away to Home (equipment-transaction:approach-home) and the hunt walked back on the next
board, 130 boards to town:blocked:stage-deadline:equipment (the auto-restart of 19:24:44).

The hunt's verdict now holds on the walk's board too: the clear-traveler hook answers an adjacent
hostile with the ladder rung's own answer (``combat_answer.adjacent_attack``, reason ``melee``).

Recorded (tests/extract_town_mob_home_pingpong_1124_fixture.py, ``n1c-222-town-mob-home-1124``):
the town-arrival checkpoint of 19:23:41 (turn 717107) and its 136 journal rows, replayed
open-loop through the public ``choose_key`` (each row posts the recorded key, so the boards stay
the live ones).  Revert: every board below is equipment-transaction:approach-home, stepping away.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-town-mob-home-1124"
APPROACH_HOME = "equipment-transaction:approach-home"
FIRST_STRIKE_ROW = 7  # (33,103), the sleeping 戦傷兵士 at (33,104): recorded '3' away
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class TownMobHomePingpong1124RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURE, Path(scratch.name))
        cls.rows = []
        for index, (recorded, supply) in enumerate(steps):
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            here = board.player.position
            adjacent = {(monster.position.y - here.y, monster.position.x - here.x)
                        for monster in board.visible_monsters
                        if monster.hostile and not monster.pet
                        and here.distance_to(monster.position) <= 1}
            cls.rows.append((index, recorded["key"], recorded["reason"], key,
                             policy.last_reason, adjacent))
            post(policy, recorded["key"])

    def beside(self):
        """The recorded walks to Home taken beside a hostile."""
        return [row for row in self.rows if row[2] == APPROACH_HOME and row[5]]

    def test_the_recorded_alternation_is_in_the_fixture(self):
        beside = self.beside()
        self.assertEqual(beside[0][0], FIRST_STRIKE_ROW)
        self.assertGreaterEqual(len(beside), 50)
        self.assertEqual(self.rows[-1][2], "town:blocked:stage-deadline:equipment")

    def test_every_walk_away_from_an_adjacent_hostile_strikes_it(self):
        for index, _recorded, _reason, key, reason, adjacent in self.beside():
            with self.subTest(row=index):
                self.assertEqual(reason, "melee", (index, key, reason))
                self.assertIn(DIRECTIONS.get(key), adjacent, (index, key, adjacent))

    def test_no_walk_to_home_beside_a_hostile(self):
        walked = [row for row in self.rows if row[4] == APPROACH_HOME and row[5]]
        self.assertEqual(walked, [])


if __name__ == "__main__":
    unittest.main()
