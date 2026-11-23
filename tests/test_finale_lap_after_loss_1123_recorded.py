"""The 99F lap counts only the coverage made after the target is lost (n1-b life-416, 2026-11-23).

Owner 2026-11-21 (LOCKED) 「感知で回る・作り直した階でも一巡する」: the floor is regenerated only after
the detection lap covered it whole without the target shown (quest_target_search ``finale_swept``).
The investigation C:/hengband-backups/pdca/n1b-leave-99-1123 (the 21:08 run of
bot-decisions.jsonl.1): the lap covered the east of the 22x198 floor (x 133-170, seq 25-155)
before Oberon was detected at (13,113) (seq 157); after the teleport away from him (seq 177) and
the lost walk (seq 179-204) only x 16-63 was walked, with the powerful detections (radius 45)
reaching x <= 106, yet seq 595 (turn 4301053) declared the floor swept and climbed to 98F.

Fixture finale-floor-2108-n1b-416-1123: every player_turn board of that run on 99F, turns
4296215-4301060 (tests/support/finale_416.py, DECLARED RECONSTRUCTED device lists and expedition
mark).  DECLARED CONSTRUCTED: from the recorded give-up board on (turn 4297434), a kept last-seen
cell is dropped while Oberon is unshown, as the recorded run dropped it, so that the replay's
search runs as the live one did whatever the battle's approach would now do there.
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from hengbot import angband_finale_battle, quest_target_search
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

GIVE_UP = 4297434   # the recorded board after the last-seen cell was dropped (seq 205)
SWEPT = 4301053     # the recorded seq 595: finale_swept and quest:regen:ascend
EAST_SEEN = 4297322  # Oberon first shown at (13,113)


class FinaleLapAfterLossRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.sweeps = {}

        def prepare(policy, board):
            held = getattr(policy, angband_finale_battle.MEMORY, None)
            if (board.turn >= GIVE_UP and held is not None and held.last_seen is not None
                    and angband_finale_battle.target_monster(board) is None):
                held.last_seen = None
            memory = getattr(policy, quest_target_search.MEMORY, None)
            cls.sweeps[board.turn] = (
                None if memory is None else (memory.sweeps.start_turn, memory.sweeps.count),
                quest_target_search.finale_swept(policy, board))
        cls.rows = finale_416.drive(
            finale_416.boards("finale-floor-2108-n1b-416-1123.jsonl.gz"), monrace, prepare=prepare)

    def test_the_floor_is_not_swept_by_the_east_covered_before_the_sighting(self):
        late = [row for row in self.rows if row[0] >= SWEPT]
        self.assertTrue(late)
        self.assertEqual([row for row in late if row[3].startswith("quest:regen")], [], late)
        self.assertFalse(any(swept for turn, (_sweep, swept) in self.sweeps.items()
                             if turn >= SWEPT), self.sweeps)

    def test_the_sweep_being_made_began_after_the_sighting(self):
        last = max(self.sweeps)
        sweep, _swept = self.sweeps[last]
        self.assertIsNotNone(sweep)
        start_turn, count = sweep
        self.assertEqual(count, 0)
        self.assertGreater(start_turn, EAST_SEEN)


if __name__ == "__main__":
    unittest.main()
