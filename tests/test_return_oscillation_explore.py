"""Return owner: a found frontier route ends the oscillation (n1-a, 2026-10-23).

The second soak instance stopped twice on Yeek Cave 4F with
``fixedquest:claim:return``: a melee in a corridor filled the oscillation
window, and the return owner then searched each wall cell eight times before
each single ``return:explore`` step.  The searches kept the window inside a few
cells, so every arrival was oscillating again and the driver's loop detector
stopped the bot.  The boards below are the recorded state rows of both
captures (``20261023-072043-loop-detected`` / ``20261023-072135-loop-detected``).
"""

import tests  # noqa: F401
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import DIRECTION_KEYS, HengbotPolicy
from hengbot.policy_constants import RECALL_MIN_DEPTH
from recorded_floor_knowledge import pre_seen_floor_replay

FIXTURE = Path(__file__).parent / "fixtures/return-oscillation-search-20261023.jsonl.gz"
FIRST = "20261023-072043-loop-detected"
SECOND = "20261023-072135-loop-detected"
# Recorded arrival cells after the replayed explore step, and the step the
# ordinary frontier route takes from each of them.
EXPECTED_ARRIVALS = {
    FIRST: [((33, 95), "9"), ((32, 96), "8"), ((31, 96), "8"), ((30, 96), "8")],
    SECOND: [((11, 65), "4"), ((11, 64), "4"), ((11, 63), "7")],
}
# The same arrival cells with the seen-floor rule (#101, owner 2026-10-23):
# the step and the committed explore goal of each.  The corridor floor the
# recorded bot walked north on was already shown in its light, so it is
# explored; the walk keeps one goal on new ground (the unvisited side passage
# (34, 93) toward the frontier (33, 93), then (29, 98) beside the frontier
# (29, 99)) instead of searching.
SEEN_FLOOR_ARRIVALS = {
    FIRST: [((33, 95), "2", (34, 93)), ((32, 96), "1", (34, 93)),
            ((31, 96), "2", (34, 93)), ((30, 96), "9", (29, 98))],
    SECOND: [((11, 65), "4", (11, 54)), ((11, 64), "4", (11, 54)),
             ((11, 63), "7", (10, 62))],
}


def load_fixture():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        header, *records = [json.loads(line) for line in stream]
    monraces = {}
    for entry in header["monraces"]:
        data = dict(entry["knowledge"])
        data["flags"] = frozenset(data["flags"])
        data["abilities"] = frozenset(data["abilities"])
        data["blows"] = tuple(MonsterBlow(**blow) for blow in data["blows"])
        monraces[entry["race_id"]] = MonraceKnowledge(**data)
    return monraces, records


def board(record, monraces):
    snapshot = parse_snapshot(record["board"], monraces)
    # DECLARED CONSTRUCTED REPLAY STATE: the captured process had already
    # observed the skill list; that viewer state is not in a board.
    return replace(
        snapshot,
        player=replace(snapshot.player, two_weapon_skill=0, shield_skill=0),
    )


def replayed_policy(capture):
    """Feed the recorded boards of one capture through one real policy."""
    monraces, records = load_fixture()
    policy = HengbotPolicy(monrace_knowledge=monraces)
    feed = [r for r in records if r["capture"] == capture and r["role"] == "feed"]
    arrivals = [r for r in records if r["capture"] == capture and r["role"] == "arrival"]
    decisions = []
    for index, record in enumerate(feed):
        snapshot = board(record, monraces)
        if index == 0:
            # DECLARED CONSTRUCTED: the quest-completion latch was set before
            # the capture window (the quest definitions are game data, not
            # repository files), so the return latch is set directly.
            policy._returning_to_town = True
        decisions.append((policy.choose_key(snapshot), policy.last_reason))
    return policy, monraces, decisions, arrivals


class ReturnOscillationExploreTest(unittest.TestCase):
    @pre_seen_floor_replay  # declared wall: exact keys of boards recorded 2026-10-23 07:20 (bot d2304637), before the 2026-10-23 seen-floor rule (tests/recorded_floor_knowledge.py); test_seen_floor_arrivals_still_walk_on_to_new_ground pins the merged walk
    def test_captured_arrivals_walk_on_instead_of_searching_again(self):
        for capture, expected in EXPECTED_ARRIVALS.items():
            with self.subTest(capture=capture):
                policy, monraces, decisions, arrivals = replayed_policy(capture)
                # The recorded searches end in the frontier step (both versions).
                self.assertEqual(decisions[-1][1], "return:explore")
                observed = []
                for record in arrivals:
                    snapshot = board(record, monraces)
                    key = policy.choose_key(snapshot)
                    position = snapshot.player.position
                    observed.append(((position.y, position.x), key, policy.last_reason))
                self.assertEqual(
                    observed,
                    [(cell, key, "return:explore") for cell, key in expected],
                )

    def test_seen_floor_arrivals_still_walk_on_to_new_ground(self):
        # With the seen-floor rule the recorded arrivals still walk (no 's'
        # search, no oscillation) toward one goal that is new ground: an
        # unvisited floor cell or a remembered frontier.
        for capture, expected in SEEN_FLOOR_ARRIVALS.items():
            with self.subTest(capture=capture):
                policy, monraces, decisions, arrivals = replayed_policy(capture)
                self.assertEqual(decisions[-1][1], "return:explore")
                observed = []
                for record in arrivals:
                    snapshot = board(record, monraces)
                    key = policy.choose_key(snapshot)
                    position = snapshot.player.position
                    goal = policy._explore_goal_identity.position
                    self.assertFalse(policy._is_oscillating())
                    self.assertTrue(
                        policy._visit_counts[goal] == 0
                        or policy._is_remembered_frontier(snapshot, goal)
                    )
                    observed.append(
                        ((position.y, position.x), key, policy.last_reason, (goal.y, goal.x))
                    )
                self.assertEqual(
                    observed,
                    [(cell, key, "return:explore", goal) for cell, key, goal in expected],
                )

    def test_known_reachable_upstairs_is_still_taken(self):
        policy, monraces, _decisions, arrivals = replayed_policy(SECOND)
        snapshot = board(arrivals[0], monraces)
        here = snapshot.player.position
        neighbor = sorted(policy._walkable_neighbors(snapshot, here))[0]
        # DECLARED CONSTRUCTED: an up staircase beside the recorded cell.
        snapshot = replace(
            snapshot,
            grids={
                **snapshot.grids,
                neighbor: replace(snapshot.grids[neighbor], has_up_stairs=True),
            },
        )
        key = policy.choose_key(snapshot)
        self.assertEqual(
            (key, policy.last_reason),
            (DIRECTION_KEYS[(neighbor.y - here.y, neighbor.x - here.x)], "return:seek-upstairs"),
        )

    def test_carried_recall_scroll_is_still_read_below_walk_out_depth(self):
        monraces, records = load_fixture()
        record = next(r for r in records if r["capture"] == SECOND and r["role"] == "arrival")
        snapshot = board(record, monraces)
        dungeon_id, _level, quest_id = snapshot.floor_key
        # DECLARED CONSTRUCTED: the recorded board one level deeper, where the
        # carried Word of Recall (slot f) is the return route.
        snapshot = replace(snapshot, floor_key=(dungeon_id, RECALL_MIN_DEPTH, quest_id))
        policy = HengbotPolicy(monrace_knowledge=monraces)
        policy._returning_to_town = True
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("rf", "return:recall"))


if __name__ == "__main__":
    unittest.main()
