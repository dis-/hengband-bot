"""q2-early-1105: Q2's first phases keep their order and their Light.

Owner 2026-11-05: 「作戦序盤のグレムリン、青ベトベト、冥界イモムシの処理を確実に行う工夫が欲しい」.

Recorded: n1-a life-482 (Lv21, HP 424) in Q2 下水道, turns 522666-522987, the boards of the
rotated snapshot log (tests/fixtures/q2-early-20261105.json.gz,
tests/extract_q2_early_1105_fixture.py).  The recorded build read all six Scrolls of Light in
the start room, fought the puddle beside it, and at [2,19] left the north route for one Undead
mass seen at [12,34]; 20 actions later the window (start count 1, end count 11) failed the quest
at HP 353/424.  The life-480 board at [12,46] is the first after the blue icky things.

DECLARED CONSTRUCTED: the skill row is the n1-c life-098 row of the breeder-swarm fixture; the
recorded boards do not follow from the keys decided here after the first read (the scroll count
on them falls as recorded; the test reads the decisions); the blocked-walk case adds an Undead
mass on the next cell of the walk; the life-480 case sets the phase state by hand (rats, gremlin
and blue cleared, breach and bolt recovery done, no reconnect: the recorded process entered from
town), which the recorded process held.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.breeder_stalemate import FLEE_AFTER_PLAYER_ACTIONS
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from tests import test_breeder_swarm_1102_recorded as swarm
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "q2-early-20261105.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8", errors="surrogateescape") as _stream:
    CASE = json.load(_stream)
UNDEAD_MASS = 202
PHASE_GREMLIN = "quest-strategy:q2-phase-153"
READ_LIGHT = "quest-strategy:q2-light-area"
WORM_PHASE = "quest-strategy:q2-post-blue-nether-worm"


def new_policy(first=None):
    case = {"boards": [first or CASE["boards"][0]], "home": None}
    policy = loops.new_policy(case, swarm.CASE["skill"], monraces=CASE["monraces"])
    policy._quest_knowledge = load_quest_knowledge(find_quest_definitions(Path(__file__)))
    return policy


def opening():
    """Decide life-482's boards in order; (turn, key, reason) per board."""
    policy = new_policy()
    return policy, [(raw["turn"], loops.decide(policy, copy.deepcopy(raw)), policy.last_reason)
                    for raw in CASE["boards"]]


def with_mass_at(raw, y, x):
    raw = copy.deepcopy(raw)
    template = next(m for m in raw["visible_monsters"] if m["race_id"] == UNDEAD_MASS)
    raw["visible_monsters"].append(dict(template, index=template["index"] + 500, y=y, x=x))
    return raw


class Q2EarlyRecordedTest(swarm.PostedSwarmKey):
    def test_start_room_reads_one_light_and_leaves_the_puddles(self):
        _, rows = opening()
        reads = [row for row in rows if "light" in row[2]]
        self.assertEqual([row[2] for row in reads], [READ_LIGHT])
        by_turn = {turn: (key, reason) for turn, key, reason in rows}
        # Only the two puddles in view at [1,3]: the walk goes on, no blow and no shot.
        for turn in (522765, 522782, 522788):
            self.assertNotIn(by_turn[turn][1], {"quest-strategy:melee", "quest-strategy:q2-fire"}, turn)
        self.post(new_policy(), CASE["boards"][0], reads[0][1])

    def test_a_mass_seen_from_the_north_route_does_not_turn_the_walk(self):
        policy, rows = opening()
        self.assertEqual(rows[-1], (522987, "6", PHASE_GREMLIN))
        self.assertEqual(rows[-2], (522980, "6", PHASE_GREMLIN))
        self.post(policy, CASE["boards"][-1], rows[-1][1])

    def test_a_mass_on_the_next_cell_of_the_walk_is_engaged(self):
        policy, _ = opening()
        raw = with_mass_at(CASE["boards"][-1], 2, 21)
        key = loops.decide(policy, raw)
        self.assertNotEqual(policy.last_reason, PHASE_GREMLIN, key)

    def test_the_worms_come_before_the_puddles_and_spiders(self):
        raw = CASE["after_blue"]
        policy = new_policy()
        loops.decide(policy, copy.deepcopy(CASE["boards"][0]))
        policy._q2_reconnect_recovery_floor = None
        policy._q2_cleared_races.update({86, 153, 252})
        policy._q2_breach_complete = True
        policy._q2_blue_recovery_complete = True
        key = loops.decide(policy, copy.deepcopy(raw))
        self.assertEqual(policy.last_reason, WORM_PHASE)
        self.post(policy, raw, key)


RAT = 86
RAT_BOARD = 522675  # three giant white rats and two puddles in view
RAT_CELLS = ((1, 1), (3, 1), (3, 7), (1, 8), (1, 9), (1, 10))
MASS_CELLS = tuple((3, x) for x in range(9, 20))
RECALL_REASON = "breeder-breakthrough:recall"


def rats_board(rats, masses=0, *, action=0, exp=0, quest_id=None):
    """DECLARED CONSTRUCTED: the recorded rat board with ``rats`` rats and ``masses`` masses.

    Monster indices are stable per cell, so a cut rat is gone and a new one is new."""
    raw = copy.deepcopy(next(b for b in CASE["boards"] if b["turn"] == RAT_BOARD))
    rat = next(m for m in raw["visible_monsters"] if m["race_id"] == RAT)
    mass = next(m for b in CASE["boards"] for m in b["visible_monsters"] if m["race_id"] == UNDEAD_MASS)
    others = [m for m in raw["visible_monsters"] if m["race_id"] != RAT]
    raw["visible_monsters"] = [
        *others,
        *(dict(rat, index=900 + i, y=y, x=x) for i, (y, x) in enumerate(RAT_CELLS[:rats])),
        *(dict(mass, index=950 + i, y=y, x=x) for i, (y, x) in enumerate(MASS_CELLS[:masses])),
    ]
    raw["grid_map"]["cells"] = [cell for cell in raw["grid_map"]["cells"] if cell.get("m") is None]
    raw["turn"] += 10 * action
    raw["player"]["exp"] += exp
    if quest_id is not None:
        raw["floor"]["quest_id"] = quest_id
    return raw


# The board after the window's last attack (owner 2026-11-09 「100回」: FLEE_AFTER_PLAYER_ACTIONS).
END = 2 + FLEE_AFTER_PLAYER_ACTIONS


class PlanFloorWindowTest(swarm.PostedSwarmKey):
    """Owner 2026-11-05 「攻撃を始めてから数える」, through the public choose_key."""

    def run_boards(self, boards):
        policy = new_policy(boards[0])
        for raw in boards:
            loops.decide(policy, copy.deepcopy(raw))
        return policy

    def attacked_then(self, later_rats, masses=0):
        """Two rats, one killed (the attack), then a window of actions at ``later_rats``."""
        return [rats_board(2, masses),
                rats_board(1, masses, action=1, exp=1),
                *(rats_board(later_rats, masses, action=action, exp=1) for action in range(2, END))]

    def test_the_attacked_race_keeps_growing_and_the_floor_is_left(self):
        boards = self.attacked_then(4)
        policy = self.run_boards(boards)
        self.assertEqual(policy._breeder_engagement_race, RAT)
        self.assertEqual(policy._breeder_breakthrough_floor, (0, 15, 2))
        last = rats_board(4, action=END, exp=1)
        key = loops.decide(policy, copy.deepcopy(last))
        self.assertEqual(policy.last_reason, RECALL_REASON)
        self.post(policy, last, key)

    def test_the_attacked_race_falls_and_the_floor_is_kept(self):
        policy = self.run_boards([rats_board(4), rats_board(3, action=1, exp=1),
                                  *(rats_board(2, action=action, exp=1) for action in range(2, END))])
        self.assertIsNone(policy._breeder_breakthrough_floor)
        self.assertEqual(policy._breeder_engagement_start_count, 2)

    def test_another_race_coming_into_view_is_not_counted(self):
        boards = [rats_board(2), rats_board(1, action=1, exp=1),
                  *(rats_board(1, 11, action=action, exp=1) for action in range(2, 22))]
        self.assertIsNone(self.run_boards(boards)._breeder_breakthrough_floor)

    def test_breeders_only_seen_open_no_window(self):
        # life-482: one mass at the first sight, eleven in view twenty actions later.
        boards = [rats_board(0, 1 + action // 2, action=action) for action in range(23)]
        policy = self.run_boards(boards)
        self.assertIsNone(policy._breeder_engagement_start_count)
        self.assertIsNone(policy._breeder_breakthrough_floor)

    def test_a_floor_without_a_plan_also_counts_from_the_first_attack(self):
        # Owner 2026-11-07 「クエストの無い階でも、20回は増える敵に攻撃を始めてから数える。」:
        # masses coming into view and growing, never attacked, open no window there either.
        boards = [rats_board(0, 1 + action // 2, action=action, quest_id=0) for action in range(23)]
        policy = self.run_boards(boards)
        self.assertIsNone(policy._breeder_engagement_start_count)
        self.assertIsNone(policy._breeder_breakthrough_floor)

    def test_a_floor_without_a_plan_counts_every_breeder_after_the_attack(self):
        # The 11-03 comparison once the window is open: every perceived breeder, no race.
        boards = [rats_board(2, 1, quest_id=0),
                  rats_board(1, 1, action=1, exp=1, quest_id=0),
                  *(rats_board(1, 2 + action // 10, action=action, exp=1, quest_id=0)
                    for action in range(2, END))]
        policy = self.run_boards(boards)
        self.assertIsNotNone(policy._breeder_breakthrough_floor)
        self.assertIsNone(policy._breeder_engagement_race)


if __name__ == "__main__":
    unittest.main()
