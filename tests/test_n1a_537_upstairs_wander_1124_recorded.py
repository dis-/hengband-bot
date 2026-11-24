"""n1-a life-537: the income run's floor exit searches the walls of a walled-in landing.

n1-a life-537 (Warrior Lv8) was restarted by the livelock bound at 2026-11-24 21:03:11 (turn
125804, Yeek cave 3F): a scavenging run on Yeek cave 1F fell through a trap door (turn 86085)
into two rooms and a corridor whose only exits are secret doors.  No Recall is carried (this run
walked in) and no digger.  The floor exit of the income run (``_leave_fundraising_floor``)
explored the 55 floor cells, then walked ``fundraise:seek-upstairs-wander`` for 1,432 of the
last 1,438 decisions (~40,000 game turns): its wall search was asked only while the walk
oscillated, and a least-visited walk over 55 cells never does.  After the restart the ordinary
return (``_return_to_town_key``) searched the corridor's end walls (``return:search-upstairs``)
eight times, found the door and left the rooms within 200 game turns.

Now the floor exit asks the same secret-wall search as the ordinary return once nothing is left
to explore and no dig answers (owner 2026-11-13: loops are prevented at the root).

Recorded: the 20:54:40 town-arrival checkpoint of n1-a life-537
(tests/fixtures/n1a-537-upstairs-wander-1124, its 100 town rows replayed as recorded), the
snapshot lines of turns 85917-86600 (``boards.jsonl.xz``, the later line of a turn decided) and
the recorded (key, reason) of those turns (``decisions.jsonl.xz``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import Position, parse_snapshot
from support.town_arrival_fixture import load
from town_work_corpus import replay_window

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-537-upstairs-wander-1124"
WANDER = "fundraise:seek-upstairs-wander"
TRAPDOOR_TURN = 86085


def _lines(name):
    return [json.loads(line) for line in lzma.decompress(
        (FIXTURE / name).read_bytes()).decode("utf-8").splitlines() if line.strip()]


class UpstairsWanderTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name),
                                                  adopt_recorded_calibration=False)
            cls.town = replay_window("n1a-537-upstairs-wander", cls.policy, iter(steps))
        by_turn = {}
        for raw in _lines("boards.jsonl.xz"):
            if raw.get("type") == "player_turn":
                by_turn[raw["turn"]] = raw  # the later line of a turn
        cls.matched = []
        cls.divergence = None
        for recorded in _lines("decisions.jsonl.xz"):
            board = parse_snapshot(by_turn[recorded["turn"]], cls.policy._monrace_knowledge)
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                key = cls.policy.choose_key(board)
            decided = (key, cls.policy.last_reason)
            if decided != (recorded["key"], recorded["reason"]):
                cls.divergence = (recorded, board, decided)
                break
            cls.matched.append(recorded)
            cls.policy.confirm_key_posted(key)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_town_visit_replays_as_recorded(self):
        self.assertIsNone(self.town.first_divergence)
        self.assertEqual(self.town.matched_rows, 100)

    def test_the_walled_in_landing_is_explored_as_recorded(self):
        landed = [row for row in self.matched if row["turn"] >= TRAPDOOR_TURN]
        self.assertGreaterEqual(len(landed), 40)
        self.assertTrue(all(row["reason"] != WANDER for row in self.matched))

    def test_the_wall_search_comes_before_the_wander(self):
        self.assertIsNotNone(self.divergence)
        recorded, board, (key, reason) = self.divergence
        # Recorded 20:55:06 (turn 86545): the first of 1,432 wander steps.
        self.assertEqual(recorded["reason"], WANDER)
        self.assertEqual((board.floor_key, board.dungeon_level), ((2, 3, 0), 3))
        # The corridor's east end (18,75): its walls are searched where it stands, as the
        # restarted return searched them (``return:search-upstairs`` at (18,74) and (18,75)).
        self.assertEqual(board.player.position, Position(18, 75))
        self.assertEqual((key, reason), ("s", "fundraise:search"))
        self.assertTrue(self.policy._undersearched_walls(board.player.position))
        self.assertEqual(self.policy._search_counts[(18, 75)], 1)


if __name__ == "__main__":
    unittest.main()
