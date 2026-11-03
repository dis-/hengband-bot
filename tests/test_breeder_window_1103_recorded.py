"""breeder-window-1103: the 20-action rule compares the ends of each window.

Owner 2026-11-03: 「20回の区切りの初めの数と終わりの数を比べ、減っていれば次の区切りへ
進み、減っていなければ逃げます（Q2 などは放棄）。1体倒しても増えて元に戻るなら逃げます。
「20」の数字は変えません。」

Recorded: n1-c life-120 in Q2 下水道, 2026-11-03, boards 56-97 of the stall
capture's state ring (tests/fixtures/breeder-window-20261103.json.gz,
tests/extract_breeder_window_1103_fixture.py).  The worm count runs 47 ... 25 ...
33 over two windows.  Compared with the first count for ever, these boards stay
below 47, so the old window kept restarting on them and the floor never latched.

DECLARED CONSTRUCTED: the recorded process had the floor latched and walked the
patrol, so these boards do not follow from the keys decided here (the test reads
the window, which depends on the worm counts and the turns only); the skill row
is the n1-c life-098 row of the breeder-swarm fixture;
``_fixed_quest_speed_attempted`` is true.  The WindowEdgesTest counts come from
the owner's question, not from the capture: one recorded board is repeated with
its worms cut to the count and its turn advanced 10 per action.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest import mock

from hengbot import breeder_stalemate
from hengbot.breeder_stalemate import FLEE_AFTER_PLAYER_ACTIONS
from hengbot.policy import ConservativePolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from tests import test_breeder_swarm_1102_recorded as swarm
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "breeder-window-20261103.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8", errors="surrogateescape") as _stream:
    CASE = json.load(_stream)
QUEST_FLOOR = (0, 15, 2)
RECALL_SLOT = "e"
WINDOW = FLEE_AFTER_PLAYER_ACTIONS


def new_policy(first_board=None):
    case = dict(CASE, home=None)
    if first_board is not None:
        case["boards"] = [first_board]
    policy = loops.new_policy(case, swarm.CASE["skill"], monraces=CASE["monraces"])
    policy._quest_knowledge = load_quest_knowledge(find_quest_definitions(Path(__file__)))
    policy._fixed_quest_speed_attempted = True
    return policy


def worms(count, action):
    """DECLARED CONSTRUCTED: the first board with its nearest ``count`` worms."""
    raw = copy.deepcopy(CASE["boards"][0])
    player = raw["player"]
    nearest = sorted(raw["visible_monsters"],
                     key=lambda m: max(abs(m["y"] - player["y"]), abs(m["x"] - player["x"])))[:count]
    kept = {monster["index"] for monster in nearest}
    raw["visible_monsters"] = nearest
    raw["grid_map"]["cells"] = [cell for cell in raw["grid_map"]["cells"]
                                if cell.get("m") is None or cell["m"] in kept]
    raw["turn"] += 10 * action
    return raw


class WindowCase(swarm.RecordedRestart):
    def run_counts(self, policy, counts, first_action=0):
        """Decide one board per action; the latch after each decision."""
        latches = []
        for action, count in enumerate(counts, first_action):
            loops.decide(policy, worms(count, action))
            latches.append(policy._breeder_breakthrough_floor)
        return latches

    def recording_policy(self):
        record = self.record

        class Restarted(ConservativePolicy):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._breeder_floor_record_path = record

        return Restarted

    def assert_window(self, policy, start_count, actions):
        self.assertEqual((policy._breeder_engagement_start_count,
                          policy._breeder_engagement_actions), (start_count, actions))


class RecordedSeriesTest(WindowCase):
    def test_recorded_counts_reduce_then_grow_at_the_window_ends(self):
        counts = [len(raw["visible_monsters"]) for raw in CASE["boards"]]
        self.assertEqual((counts[0], counts[WINDOW], counts[2 * WINDOW]), (47, 25, 33))
        self.assertTrue(all(count < 47 for count in counts[4:]))

    def test_recorded_series_reduces_once_then_leaves_the_floor(self):
        policy = new_policy()
        boards = CASE["boards"]
        for action, raw in enumerate(boards[:2 * WINDOW + 1]):
            loops.decide(policy, raw)
            latched = policy._breeder_breakthrough_floor
            self.assertEqual(latched, QUEST_FLOOR if action == 2 * WINDOW else None, raw["turn"])
            if action == WINDOW - 1:
                self.assert_window(policy, 47, WINDOW - 1)
            if action == WINDOW:
                self.assert_window(policy, 25, 0)
        following = boards[2 * WINDOW + 1]
        key = loops.decide(policy, following)
        self.assertEqual((key, policy.last_reason), ("r" + RECALL_SLOT, "breeder-breakthrough:recall"))
        self.post(policy, following, key)
        # The verdict stands although this board shows fewer worms (31 < 33):
        # the target quest's Teleportation reads the same stalemate.
        self.assertTrue(breeder_stalemate.stalemate_standing(policy))


class WindowEdgesTest(WindowCase):
    def test_first_two_then_ten_flees_at_the_twentieth_action(self):
        policy = new_policy()
        latches = self.run_counts(policy, [2] + [10] * WINDOW)
        self.assertEqual(latches, [None] * WINDOW + [QUEST_FLOOR])

    def test_ten_then_nine_at_the_twentieth_action_opens_a_window_at_nine(self):
        policy = new_policy()
        latches = self.run_counts(policy, [10] * WINDOW + [9])
        self.assertEqual(latches, [None] * (WINDOW + 1))
        self.assert_window(policy, 9, 0)
        latches = self.run_counts(policy, [9] * WINDOW, first_action=WINDOW + 1)
        self.assertEqual(latches, [None] * (WINDOW - 1) + [QUEST_FLOOR])

    def test_nine_inside_the_window_then_ten_at_the_end_flees(self):
        policy = new_policy()
        latches = self.run_counts(policy, [10] * 10 + [9] + [10] * (WINDOW - 10))
        self.assertEqual(latches, [None] * WINDOW + [QUEST_FLOOR])

    def test_no_worm_at_the_end_closes_the_engagement(self):
        policy = new_policy()
        latches = self.run_counts(policy, [10] * WINDOW + [0])
        self.assertEqual(latches, [None] * (WINDOW + 1))
        self.assertIsNone(policy._breeder_engagement_start_count)
        self.run_counts(policy, [3], first_action=WINDOW + 1)
        self.assert_window(policy, 3, 0)

    def test_no_worm_inside_the_window_resets_nothing(self):
        policy = new_policy()
        latches = self.run_counts(policy, [10] * 10 + [0] + [10] * (WINDOW - 10))
        self.assertEqual(latches, [None] * WINDOW + [QUEST_FLOOR])

    def test_a_restart_keeps_the_new_window(self):
        previous = new_policy()
        previous._breeder_floor_record_path = self.record
        self.run_counts(previous, [10] * WINDOW + [9] + [9] * 4)
        self.assert_window(previous, 9, 4)
        # A new process: the CLI points the record path before its first board.
        action = WINDOW + 5
        with mock.patch.object(loops, "ConservativePolicy", self.recording_policy()):
            restarted = new_policy(worms(9, action))
        self.assert_window(restarted, 9, 4)
        self.run_counts(restarted, [9], first_action=action)
        self.assert_window(restarted, 9, 5)


if __name__ == "__main__":
    unittest.main()
