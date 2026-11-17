"""n1-a life-530 2026-11-17: an unseen hit near the Yeek entrance ended the visit by name.

The Lv42 warrior (Angband 50 refused for *Destruction* and telepathy; the Castle and the Mountain
land at 49, the over-extended depth) was in the no-safe-destination mining set, run 2 of 2.  On
the walk to the Yeek entrance (31, 150) an unseen attacker hit it at (31, 124) (turn 8371626); the
unseen retreat walked it back to (47, 122) and retired on the board of turn 8371789, 163 game
turns after the hit.  The quiet window of that hit (200 game turns, policy_identification
UNSEEN_LOOT_QUIET_TURNS) still held the entrance in the attack's area, so the descent step
deferred it (``unseen-attack-area``, n1-a life-508) and the descent layer passed to the idle
layer, which in town is the town end: it judged the recall departure (Angband 50, not the
walk-in) and stopped as town:blocked:survival:depth_abilities, the server's first Lv30+ stop.

Now the town waits the window out (``_town_unseen_descent_wait_key``) and walks in after it.

Recorded: the town-arrival checkpoint of 17:37:47, its 34 journal rows (row 33 the stop) and the
sidecar files (tests/extract_n1a_530_unseen_entrance_1117_fixture.py).

DECLARED CONSTRUCTED:
* ``after_window``: the last unseen hit dated one quiet window before the stop board, the board
  the bot would see after the wait.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy_identification import UNSEEN_LOOT_QUIET_TURNS
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-unseen-entrance-1117"
STOP_ROW = 33
STOP_REASON = "town:blocked:survival:depth_abilities"
WAIT_REASON = "town:unseen-attack-quiet-wait"
ENTRANCE_REASONS = {"town:travel-entrance", "seek-downstairs", "approach-descent"}


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1a530UnseenEntranceRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.policy, cls.journal, rows = load(FIXTURE, Path(scratch.name))
        cls.recorded = []
        for index, (recorded, supply) in enumerate(rows):
            board = supply()
            if index == STOP_ROW:
                cls.board = board
                break
            key = cls.policy.choose_key(board)
            cls.recorded.append((recorded["key"], recorded["reason"], key, cls.policy.last_reason))
            post(cls.policy, key)

    def test_the_rows_before_the_stop_replay_as_recorded(self):
        for recorded_key, recorded_reason, key, reason in self.recorded:
            self.assertEqual((key, reason), (recorded_key, recorded_reason))
        self.assertEqual(self.journal[STOP_ROW]["reason"], STOP_REASON)

    def test_the_entrance_is_in_the_quiet_window_of_the_hit(self):
        policy, board = self.policy, self.board
        self.assertTrue(board.in_town)
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertLess(board.turn - policy._unseen_last_hit_turn, UNSEEN_LOOT_QUIET_TURNS)
        entrance = policy._town_map_descent_entrance(board)
        self.assertIsNotNone(entrance)
        self.assertTrue(policy._in_unseen_attack_area(board, entrance))

    def test_the_town_waits_out_the_window_instead_of_stopping(self):
        import copy
        policy = copy.deepcopy(self.policy)
        key = policy.choose_key(copy.deepcopy(self.board))
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, WAIT_REASON))
        self.assertIsNone(policy._town_blocked_reason)

    def test_after_the_window_the_walk_in_resumes(self):
        import copy
        policy = copy.deepcopy(self.policy)
        board = copy.deepcopy(self.board)
        policy._unseen_last_hit_turn = board.turn - UNSEEN_LOOT_QUIET_TURNS
        key = policy.choose_key(board)
        self.assertIn(policy.last_reason, ENTRANCE_REASONS, key)

    def test_the_wait_is_bounded_by_the_window(self):
        import copy
        policy = copy.deepcopy(self.policy)
        board = copy.deepcopy(self.board)
        policy._descent_refusal_reason = "unseen-attack-area"
        policy._unseen_last_hit_turn = board.turn - UNSEEN_LOOT_QUIET_TURNS
        self.assertIsNone(policy._town_unseen_descent_wait_key(board))
        policy._unseen_last_hit_turn = board.turn - 1
        self.assertEqual(policy._town_unseen_descent_wait_key(board), WAIT_KEY)


if __name__ == "__main__":
    unittest.main()
