"""n1-b life-378 21:14 (Angband 30F): the stairs walk walked back into an unseen caster's area.

Recorded: tests/fixtures/n1b-378-1112/unseen-stairs-2114.json.gz
(tests/extract_n1b_378_unseen_stairs_1112_fixture.py).

A 宙に浮かぶ宝珠 (race 912: NEVER_MOVE, Magic Missile 1_IN_1) in the dark room west of the
corridor hit the player at its mouth (54,43).  ``unseen:reverse-choke`` '9' stepped back to
(53,44), the choke, where the hold ended at once (nothing visible, no reachable damage), and
``stuck:seek-stairs`` '1' walked straight back onto (54,43) toward the stairs past the area.  The
two alternated, with rests and searches between, until the loop detector stopped the bot
(21:14:05, 300 decisions in two cells).  Explore, loot targets and the descent kept out of that
area (user 2026-10-06 「後ずさりは今のまま・拾いを諦める」, _in_unseen_attack_area); the goal walks
(goal_route, the stairs walk among them) and the loot's route to a target did not.  The area is
now in every walker's veto (``_walk_veto``, owner 2026-11-09 「退却・逃げ・狩り以外を揃える」)
while the player stands outside it.

Every decision is the public ``choose_key`` of one fresh policy fed the recorded boards in
order.  The fresh policy has not walked the floor, so on the boards at (53,44) its walk is the
loot walk where the live one was the stairs walk: both stepped '1' into the area before.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.policy_identification import UNSEEN_LOOT_QUIET_TURNS
from tests.test_empty_wand_1110_recorded import MOVES, decide, fresh

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-378-1112" / "unseen-stairs-2114.json.gz"
HIT = Position(54, 43)    # the corridor mouth the Magic Missiles landed on
CHOKE = Position(53, 44)  # the reverse-choke's cell
ORB = Position(58, 36)
# The boards at the choke after a hit at the mouth: live ('1', 'stuck:seek-stairs') on each.
BACK = (2191782, 2191797, 2191813, 2191915, 2191928)
DETECTED = 2191950  # the detection board: the orb shown at (58,36)


def case():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def here(raw):
    return Position(raw["player"]["y"], raw["player"]["x"])


class UnseenStairsRecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = case()
        cls.live = {row["turn"]: (row["key"], row["reason"]) for row in cls.case["decisions"]
                    if row["reason"] != "loop-detected"}

    def replay(self, until=None):
        policy, races = fresh(self.case)
        decisions = {}
        for raw in self.case["rows"]:
            decisions[raw["turn"]] = (decide(policy, races, raw), policy.last_reason)
            if raw["turn"] == until:
                return policy, races, raw, decisions
        return policy, races, raw, decisions

    def test_recorded_scene(self):
        rows = {raw["turn"]: raw for raw in self.case["rows"]}
        for turn in BACK:
            self.assertEqual(here(rows[turn]), CHOKE)
            self.assertEqual(self.live[turn], ("1", "stuck:seek-stairs"))
        retreats = [turn for turn, (key, reason) in self.live.items()
                    if reason == "unseen:reverse-choke" and here(rows[turn]) == HIT]
        self.assertGreaterEqual(len(retreats), 6)
        for turn in retreats:
            self.assertEqual(self.live[turn][0], "9")
            self.assertTrue(any("マジック・ミサイル" in message or "呪文" in message
                                for message in rows[turn]["messages"]), turn)
        orb = [monster for monster in rows[DETECTED]["detected_monsters"]
               if monster["race_id"] == 912]
        self.assertEqual([(monster["y"], monster["x"]) for monster in orb], [(ORB.y, ORB.x)])
        self.assertIn("NEVER_MOVE", self.case["monraces"]["912"]["flags"])
        self.assertFalse(any(rows[turn]["visible_monsters"] for turn in rows))

    def test_the_walks_do_not_step_back_into_the_area(self):
        _, races, _, decisions = self.replay()
        policy = None
        for turn in BACK:
            policy, races, raw, _ = self.replay(turn)
            board = parse_snapshot(copy.deepcopy(raw), races)
            key, reason = decisions[turn]
            self.assertNotEqual(reason, "unseen:reverse-choke", turn)
            self.assertNotEqual(key, "1", (turn, reason))
            if key in MOVES:
                dy, dx = MOVES[key]
                step = Position(CHOKE.y + dy, CHOKE.x + dx)
                self.assertFalse(policy._in_unseen_attack_area(board, step), (turn, key, reason))
        self.assertIsNotNone(policy)

    def test_the_stairs_walk_keeps_out_of_the_area_until_it_lifts(self):
        policy, races, raw, _ = self.replay(BACK[1])
        board = parse_snapshot(copy.deepcopy(raw), races)
        self.assertTrue(policy._in_unseen_attack_area(board, HIT))
        self.assertFalse(policy._in_unseen_attack_area(board, CHOKE))
        self.assertIn(HIT, policy._walk_veto(board))
        stairs = lambda grid: grid.has_down_stairs or grid.has_up_stairs  # noqa: E731
        step = policy._nearest_goal_step(board, stairs)
        self.assertNotEqual(step, HIT)
        self.assertTrue(step is None or not policy._in_unseen_attack_area(board, step))
        # The quiet window passed with no hit: the area lifts and the mouth is a way again.
        later = parse_snapshot(dict(copy.deepcopy(raw), messages=[],
                                    turn=raw["turn"] + UNSEEN_LOOT_QUIET_TURNS + 10), races)
        policy._clear_unseen_retreat()
        self.assertNotIn(HIT, policy._walk_veto(later))
        self.assertEqual(policy._nearest_goal_step(later, stairs), HIT)

    def test_no_veto_while_the_player_stands_in_the_area(self):
        hit_board = next(turn for turn in sorted(self.live)
                         if turn > BACK[0] and self.live[turn][1] == "unseen:reverse-choke")
        policy, races, raw, decisions = self.replay(hit_board)
        board = parse_snapshot(copy.deepcopy(raw), races)
        self.assertEqual(here(raw), HIT)
        self.assertEqual(decisions[hit_board], ("9", "unseen:reverse-choke"))
        self.assertTrue(policy._in_unseen_attack_area(board, HIT))
        self.assertEqual(policy._unseen_attack_area_veto(board), frozenset())


if __name__ == "__main__":
    unittest.main()
