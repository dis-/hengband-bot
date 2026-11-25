"""Quest 33 on n1-a life-537 (2026-11-25 19:51-20:21:45): the sweep walked its 100 rounds past two cave
spiders and stopped by name with the quest open.

The chain (Zombie warrior Lv48, HP 1169, telepathy, no bolts for the heavy crossbow, no detection
device; the tracked summoners all dead, quest_sweep_record's kills):

 * Two 洞窟蜘蛛 (race 60: level 2, vision 8, WEIRD_MIND), random monsters of the map's ``5`` cells,
   wandered the trees at [18,47..51] and the west room's [20,3..4].  The telepathy showed one on a
   few boards of every round (WEIRD_MIND), out of view or out of reach of any shot.
 * The plan answered neither: no shot (no bolts), no wait (it does not come), no walk to it (the plan
   closes only on what never moves, owner 2026-11-25 (b)-1).  Every board was ``sweep-walk``.
 * Yet each board that showed one counted as the round's contact, so no round was found empty and
   kill_all_patrol was never asked; the 100th round ended on [25,73] with
   ``quest:blocked:sweep-nothing-left``.

The rule (owner 2026-11-13 「全滅クエストで作戦を終えても終わらない時は周回して探す・感知があれば感知して
探す」; 2026-11-08 the search covers the floor with what detects): a round counts as having met a
hostile only when the plan answered one (quest_room_sweep ``_note_contact``); a round that answered
nothing hands the floor to kill_all_patrol, which walks to what the telepathy shows.  A hostile no
walk reaches no longer ends the patrol (kill_all_patrol ``key``): the others, the detection and the
round go on.

Recorded: tests/fixtures/n1a-537-q33-nothing-left-1125 (tests/extract_n1a_537_q33_nothing_left_1125_fixture.py):
the boards of the last round with their recorded decisions, and the plan state (quest-plan.pkl) and
the tracked kills the process left at the stop.

DECLARED CONSTRUCTED: the policy is the same life's on the same floor at 10:10
(tests/fixtures/n1a-537-q33-shore-1125); the plan state of the record is set on it as a restart sets
it (quest_plan_record.restore), with the tracked kills (quest_sweep_record), and its navigator is put
back to the start of the recorded round: the last stop [25,73], round 98, the round before counted as
met (as the recorded process counted every round).  So set, the policy reproduces every recorded
decision of the round but the stop's.  ``UnreachedTest`` moves the spider of a recorded board out of
every walk's reach.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import collections
import copy
import json
import lzma
import pickle
import unittest
from collections import deque
from pathlib import Path

from hengbot import kill_all_patrol, quest_room_sweep
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-537-q33-nothing-left-1125"
POLICY = Path(__file__).with_name("fixtures") / "n1a-537-q33-shore-1125" / "policy.pkl.xz"
CASE = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))
QUEST = 33
CAVE_SPIDER = 60
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def policy(*, round_before_found_nothing=False):
    """The fixture's policy with the record's plan state, at the start of the recorded round."""
    deciding = restore_checkpoint_bytes(HengbotPolicy, lzma.decompress(POLICY.read_bytes()))
    held = pickle.loads(lzma.decompress((FIXTURE / "quest-plan.pkl.xz").read_bytes()))
    for name, value in held["states"].items():
        setattr(deciding, name, value)
    navigator = held["navigators"][QUEST]
    navigator.split_kills = dict(collections.Counter(race for race, _turn in CASE["kills"]))
    navigator.split_kill_turns = tuple(tuple(kill) for kill in CASE["kills"])
    plan = deciding.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
    navigator.sweep_stage = len(quest_room_sweep._stops(plan)) - 1
    navigator.sweep_round = int(plan["max_rounds"]) - 2
    navigator.sweep_round_contact = not round_before_found_nothing
    navigator.sweep_found_nothing = round_before_found_nothing
    deciding._quest_navigators[QUEST] = navigator
    return deciding


def drive(deciding, boards):
    out = []
    for raw in boards:
        snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
        key = str(deciding.choose_key(snapshot))
        out.append((snapshot, key, deciding.last_reason))
        deciding.confirm_key_posted(key)
    return out


def spiders(raw):
    return [monster for monster in (*raw["visible_monsters"], *raw["detected_monsters"])
            if monster["race_id"] == CAVE_SPIDER]


def walk_length(deciding, snapshot, start, target) -> int:
    """The fewest steps of the walk model from ``start`` to a cell beside ``target``."""
    seen, frontier = {start}, deque([(start, 0)])
    while frontier:
        cell, steps = frontier.popleft()
        if max(abs(cell.y - target.y), abs(cell.x - target.x)) <= 1:
            return steps
        for neighbor in deciding._walkable_neighbors(snapshot, cell):
            if neighbor not in seen:
                seen.add(neighbor)
                frontier.append((neighbor, steps + 1))
    return 999


class TheRecordingTest(unittest.TestCase):

    def test_the_round_walked_past_the_spiders_and_stopped_by_name(self):
        reasons = [row["reason"] for row in CASE["recorded"]]
        self.assertEqual(reasons[-1], quest_room_sweep.NOTHING_LEFT_REASON)
        self.assertEqual(set(reasons[:-1]), {quest_room_sweep.WALK_REASON})
        shown = [raw for raw in CASE["boards"] if spiders(raw)]
        self.assertGreaterEqual(len(shown), 15)
        self.assertEqual({len(raw["visible_monsters"]) + len(raw["detected_monsters"]) - len(spiders(raw))
                          for raw in CASE["boards"]}, {0})
        first, last = CASE["boards"][0], CASE["boards"][-1]
        self.assertEqual([(raw["player"]["y"], raw["player"]["x"]) for raw in (first, last)], [(25, 73), (25, 73)])
        quest = next(quest for quest in last["progress"]["quests"] if quest["id"] == QUEST)
        self.assertEqual(quest["status"], 1)   # taken, not completed


class TheRoundTest(unittest.TestCase):

    def test_a_round_that_answered_no_hostile_hands_the_floor_to_the_patrol(self):
        answers = drive(policy(), CASE["boards"])
        for (snapshot, key, reason), row in zip(answers[:-1], CASE["recorded"][:-1]):
            self.assertEqual((key, reason), (row["key"], row["reason"]), row["sequence"])
        _snapshot, _key, reason = answers[-1]
        self.assertNotEqual(reason, quest_room_sweep.NOTHING_LEFT_REASON)
        self.assertTrue(reason.startswith(kill_all_patrol.REASON), reason)

    def test_the_patrol_walks_to_the_spider_the_telepathy_shows(self):
        deciding = policy(round_before_found_nothing=True)
        hunts = 0
        for snapshot, key, reason in drive(deciding, CASE["boards"]):
            shown = [monster for monster in snapshot.detected_monsters if monster.race_id == CAVE_SPIDER]
            if not shown:
                continue
            self.assertEqual(reason, kill_all_patrol.HUNT_REASON, snapshot.turn)
            here = snapshot.player.position
            dy, dx = STEPS[key]
            there = Position(here.y + dy, here.x + dx)
            target = shown[0].position
            self.assertLess(walk_length(deciding, snapshot, there, target),
                            walk_length(deciding, snapshot, here, target), (snapshot.turn, key))
            hunts += 1
        self.assertGreaterEqual(hunts, 10)


class UnreachedTest(unittest.TestCase):

    def test_a_spider_no_walk_reaches_leaves_the_patrol_walking(self):
        deciding = policy(round_before_found_nothing=True)
        raw = copy.deepcopy(next(raw for raw in CASE["boards"] if raw["detected_monsters"]))
        raw["detected_monsters"][0]["y"], raw["detected_monsters"][0]["x"] = 42, 120   # off the map
        (_snapshot, key, reason), = drive(deciding, [raw])
        self.assertNotEqual(reason, quest_room_sweep.NOTHING_LEFT_REASON)
        self.assertEqual(reason, kill_all_patrol.WALK_REASON)
        self.assertIn(key, STEPS)


if __name__ == "__main__":
    unittest.main()
