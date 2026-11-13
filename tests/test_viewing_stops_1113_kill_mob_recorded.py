"""n1-b life-389 town:kill-mob-approach ping-pong (2026-11-13 14:09-, bot-8982e80bb).

Lv37 Magic-Eater in the Outpost on its way to the Tower: the town hunt (``_town_kill_mob_key``,
「町の敵は倒す」 for every visible non-pet town monster it can beat) re-picked the nearest visible
monster on every board.  At (24,59) a sleeping 汚いイタズラ小僧 at (9,62) (game distance 16)
was nearer than a sleeping 貧しげな傭兵 at (40,57) (17) and the step was '8'; at (23,59) the
urchin at (9,62) was out of sight, the mercenary (18) was nearer than the urchins at (7,66)
and (9,65) (19) and the step was '2'.  Live: 400+ boards of '8'/'2'.

The hunt now keeps the monster it walks to until it is killed, out of sight and its last
cell reached, unreachable, or no longer beatable; an adjacent monster is still fought first.

Recorded: the town-arrival checkpoint and the first 140 journal rows
(tests/extract_viewing_stops_1113_fixtures.py arrival ... kill-mob-389 140), decided through
the public choose_key; the step is posted through the production executor
(_ExecutorInputPort).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
from pathlib import Path
import unittest

from hengbot.model import Position
from tests.support import recorded as executor_harness
from test_me_stops_1103_recorded import Visit

FIXTURES = Path(__file__).with_name("fixtures") / "viewing-stops-1113"
APPROACH = "town:kill-mob-approach"
FIRST_APPROACH = 128   # (24,60): the hunt's first board
PING = 129             # (23,59), recorded '2' toward the mercenary


def journal_board(name, row):
    entries = lzma.decompress((FIXTURES / name / "journal.jsonl.xz").read_bytes())
    entry = json.loads(entries.decode("utf-8").splitlines()[row])
    return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])


class TownKillMobCommitRecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def visit(self):
        visit = Visit((FIXTURES / "kill-mob-389").resolve())
        visit.policy._home_disposal.history_path = visit.scratch / "home-history.jsonc"
        self.addCleanup(visit.close)
        return visit

    def replay(self, visit, rows):
        """Decide each row and post the recorded key (the game did what was recorded).

        Only row 43 differs (a one-shot buy the replay answers
        town:blocked:owner-retired; the CLI's owner retirement is not
        journalled, replay_town_arrival); every other row of the visit,
        the recorded ping-pong included, matches on main 8982e80bb."""
        divergent = []
        for recorded, supply in rows:
            key = visit.policy.choose_key(supply())
            if (key, visit.policy.last_reason) != (recorded["key"], recorded["reason"]):
                divergent.append(recorded["row"])
            visit.post(recorded["key"])
        self.assertTrue(set(divergent) <= {43}, divergent)

    def test_the_hunt_keeps_walking_to_the_urchin(self):
        visit = self.visit()
        policy = visit.policy
        rows = list(visit.rows)
        self.replay(visit, rows[:PING])
        self.assertEqual(rows[FIRST_APPROACH][0]["reason"], APPROACH)
        self.assertEqual(policy._town_hunt_target, Position(9, 62))
        recorded, supply = rows[PING]
        self.assertEqual((recorded["key"], recorded["reason"]), ("2", APPROACH))
        board = supply()
        self.assertEqual(board.player.position, Position(23, 59))
        self.assertNotIn(Position(9, 62), {m.position for m in board.visible_monsters})
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, APPROACH)
        # North, toward the urchin's last cell, not back south to the mercenary.
        self.assertIn(key, ("7", "8", "9"))
        self.assertEqual(policy._town_hunt_target, Position(9, 62))
        raw = journal_board("kill-mob-389", PING)
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), [key])

    def test_no_reversal_over_the_recorded_boards(self):
        visit = self.visit()
        policy = visit.policy
        rows = list(visit.rows)
        self.replay(visit, rows[:FIRST_APPROACH])
        reverse = {"8": "2", "2": "8", "7": "3", "3": "7", "9": "1", "1": "9", "4": "6", "6": "4"}
        previous = None
        for recorded, supply in rows[FIRST_APPROACH:]:
            key = policy.choose_key(supply())
            if policy.last_reason == APPROACH and previous is not None:
                self.assertNotEqual(key, reverse.get(previous), recorded["row"])
            previous = key if policy.last_reason == APPROACH else None
            # The game did what was recorded (the boards stay the live ones).
            visit.post(recorded["key"])


if __name__ == "__main__":
    unittest.main()
