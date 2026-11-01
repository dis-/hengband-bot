"""shoot-immobile-sleeper-1102: the recorded n1-c life-103 Silver jelly (2026-11-02).

n1-c life-103 (Magic-Eater, Lv9, 131 HP) on 鉄獄5階, turns 412539-412823
(decision sequences 4279-4306): a sleeping シルバー・ゼリー (race 73,
NEVER_MOVE, two TOUCH:EAT_LITE blows) lay seven cells east of the player on a
clear row.  The player wielded a Short Bow (x2) and carried 94 matching
arrows, yet never shot: ``RANGED_SLEEPER_MAX_DISTANCE`` (4) dropped every
sleeper beyond four cells from the ranged targets ("approach it quietly
instead" -- the hunt path), and ``threat:avoid-engagement`` vetoed that
approach.  The bot stepped back, explored back towards the jelly, stepped
back again and boxed itself in with its own vetoed cells (loop-detected
05:31:45).

A monster that never moves cannot close in when a shot wakes it, so it
stays a ranged target up to the ranged range (owner 2026-11-01
「遠隔で倒せるなら離れて撃つのは可」).  The retreat gate itself
(``_material_melee_engagement``) is unchanged (owner 2026-11-02).

Why it looped (owner 2026-11-02 「避ける判断になるのであればループではなく迂回
するべき。なんでループになるのか分からん」): the retreat fires whenever the jelly
is within HUNT_RANGE (8) and vetoes only the one cell the player left.  The
mining run's exploration goal (23,77) -- the gap south of the jelly, five
cells from it, never beside it -- stayed reachable around that cell, so
every explore step re-entered the eight-cell area and the retreat stepped
back again; the vetoed cells piled up around the player until they enclosed
it (search, breakout:least-visited, loop-detected).  Now a never-moving
monster whose touch the gate counts as material is passed around by its
ring (immobile_threat_memory: the cells beside it leave every route) instead
of retreated from at a distance; for a monster that moves, exploration and
descent route around the gate's area once the retreat has left it
(``_engagement_danger_cells``), and a floor whose rest is enclosed by the
retreat's vetoes is left by the stuck escape at once (``_stuck_escape_key``).

Fixture: tests/fixtures/immobile-sleeper-20261102.json.gz
(tests/extract_immobile_sleeper_1102_fixture.py).  Every decision is the
public ``choose_key``; posted keys go through the production executor port
(test_me_nokey_1031_recorded.PostedKey).
DECLARED RECONSTRUCTED: ``_fundraising_mode`` is "mine" (the decision rows'
fundraising purpose; with it the old build repeats the recorded rows
412539-412615 exactly); the floor's device-power uses are the capture's
``_me_power_floor`` rows before the boards.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot import immobile_threat_memory, me_powers
from hengbot import me_staff_sequence as sequence
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import DIRECTION_KEYS
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "immobile-sleeper-20261102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
SILVER_JELLY = 73
FIRST_SIGHT = 412539


def recorded():
    return {row["turn"]: (row["reason"], row["key"]) for row in CASE["decisions"]}


STEPS = {key: offset for offset, key in DIRECTION_KEYS.items()}
# The tvals of the shots and throws the player carried: arrows, torches.
RANGED_TVALS = frozenset({17, 39})


def new_policy(boards=None):
    case = CASE if boards is None else dict(CASE, boards=boards)
    policy = loops.new_policy(case, CASE["skill"], monraces=CASE["monraces"])
    sequence.state(policy).absorbed = {
        int(key) if key.isdigit() else key: count
        for key, count in CASE["sequence"]["absorbed"].items()}
    policy._dungeon_knowledge = {
        int(key): DungeonInfo(**dict(row, flags=frozenset(row["flags"])))
        for key, row in CASE["dungeons"].items()}
    floor = CASE["power_floor"]
    memory = me_powers.FloorMemory(tuple(floor["floor"]), floor["turn"])
    memory.uses.extend(
        me_powers.Use(tuple(use["served"]), tuple(use["used"]), use["trigger"],
                      Position(*use["position"]), use["turn"], use["reason"], use["key"])
        for use in floor["uses"])
    policy._me_power_floor = memory
    # DECLARED RECONSTRUCTED (module docstring).
    policy._fundraising_mode = "mine"
    return policy


def without_ranged(raw):
    raw = copy.deepcopy(raw)
    raw["inventory"] = [item for item in raw["inventory"]
                        if item.get("tval") not in RANGED_TVALS]
    return raw


def board(turn):
    return next(raw for raw in CASE["boards"] if raw["turn"] == turn)


class ImmobileSleeperRecordedTest(nokey.PostedKey):
    def test_recorded_board_retreated_from_the_sleeping_jelly(self):
        self.assertEqual(recorded()[FIRST_SIGHT], ("threat:avoid-engagement", "4"))
        policy = new_policy()
        snapshot = parse_snapshot(board(FIRST_SIGHT), policy._monrace_knowledge)
        (jelly,) = snapshot.visible_monsters
        self.assertEqual(jelly.race_id, SILVER_JELLY)
        self.assertTrue(jelly.asleep)
        self.assertEqual(snapshot.player.position.distance_to(jelly.position), 7)
        self.assertEqual(jelly.position.y, snapshot.player.position.y)

    def test_sleeping_never_moving_jelly_is_shot_from_seven_cells(self):
        policy = new_policy()
        raw = board(FIRST_SIGHT)
        key = loops.decide(policy, raw)
        self.assertEqual((policy.last_reason, key), ("ranged:fire", "fn6"))
        self.post(policy, raw, key)
        policy.confirm_key_posted(key)


class ImmobileSleeperDetourTest(nokey.PostedKey):
    """Without arrows or torches: pass the jelly by its ring, no retreat."""

    def test_recorded_old_rows_alternate_retreat_and_explore(self):
        rows = recorded()
        reasons = [rows[raw["turn"]][0] for raw in CASE["boards"][1:9]]
        self.assertEqual(reasons, ["threat:avoid-engagement", "threat:avoid-engagement",
                                   "explore", "threat:avoid-engagement", "explore",
                                   "threat:avoid-engagement", "explore", "explore"])

    def test_walks_past_the_jelly_by_its_ring(self):
        # DECLARED CONSTRUCTED: each following board is the 412539 board with
        # the player moved to the cell its posted step leads to.
        boards = [without_ranged(raw) for raw in CASE["boards"]]
        policy = new_policy(boards)
        raw = next(row for row in boards if row["turn"] == FIRST_SIGHT)
        jelly = Position(20, 82)
        visited = []
        while len(visited) < 9:
            key = loops.decide(policy, raw)
            here = Position(raw["player"]["y"], raw["player"]["x"])
            self.assertNotEqual(policy.last_reason, "threat:avoid-engagement", here)
            self.assertIn(key, STEPS, (here, policy.last_reason))
            self.post(policy, raw, key)
            policy.confirm_key_posted(key)
            dy, dx = STEPS[key]
            following = copy.deepcopy(raw)
            following["turn"] += 10
            following["messages"] = []
            following["player"]["y"] += dy
            following["player"]["x"] += dx
            raw = following
            visited.append(Position(raw["player"]["y"], raw["player"]["x"]))
        ring = immobile_threat_memory.route_cells(policy)
        self.assertIn(jelly, ring)
        self.assertFalse(ring & set(visited))
        # Through the gap the recorded exploration aimed at, then on south.
        self.assertIn(Position(23, 77), visited)
        self.assertEqual(len(set(visited)), len(visited), "no step back and forth")


if __name__ == "__main__":
    import unittest
    unittest.main()
