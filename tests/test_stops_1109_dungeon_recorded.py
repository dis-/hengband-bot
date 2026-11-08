"""The viewing bots' dungeon loop stops of 2026-11-08/09 (stops-1109 L1-L5).

Recorded: tests/fixtures/stops-1109-dungeon/ (tests/extract_stops_1109_dungeon_fixtures.py).
Every decision is the public ``choose_key`` of a fresh policy on the recorded boards; the
fresh policy is given the stop's remembered terrain (its policy-state), since a capture keeps
the boards of a few hundred game turns only (DECLARED RECONSTRUCTION, every case).  The
asserted step is posted through the production executor port.

L1, owner 2026-11-09 「起きた敵も最後の位置を覚える」(眠る敵と同じく、起きた脅威も最後に見えたマスを
期限まで覚え、見えない間も拾いの阻止と避けるマスに残す):
- n1-b life-346 (Magic-Eater Lv29, Angband 18F, 2026-11-08 10:51 loop-detected, build
  bot-15049b9): an awake ゲイザー (race 218, paralysing gaze, the status-threat latch) at
  (25,20) made ``status-threat:retreat`` step '9' from (24,23) to (23,24); there it was out of
  sight and seek-loot stepped '1' straight back, until the loop detector.
- n1-b life-356 (Magic-Eater Lv13, Yeek cave 5F, 2026-11-09 04:44 loop-detected, build
  bot-47982d326): an awake ワーグ (race 257) at (6,88), 10 cells from (6,78), put the walk to the
  loot past it under the routes' veto (its area, ``_engagement_danger_cells``), so the explore
  stepped '1' to (7,77); there it was out of sight and seek-loot stepped '9' straight back.
Now an awake hostile out of sight is remembered at its last shown cell for the retreat veto's
window (sleeper_reach_memory) and the loot block it made holds (sleeper_loot_block).
DECLARED CONSTRUCTED (356): the recorded loot (6,95) lies past cells the stop's remembered
terrain does not join, so the pile is at (6,82), on the live route inside the ワーグ's area.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import sleeper_loot_block, sleeper_reach_memory
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.retreat_veto_life import UNSEEN_GAME_TURNS
from tests.test_dungeon_1031_recorded import RecordedHarness, decide
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURES = Path(__file__).with_name("fixtures") / "stops-1109-dungeon"
TERRAIN_SETS = ("known", "marked", "floor", "wall", "door", "rubble")
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def case(name):
    with gzip.open(FIXTURES / f"{name}.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


def here(raw):
    return Position(raw["player"]["y"], raw["player"]["x"])


def recorded(data):
    return {row["turn"]: (row["key"], row["reason"]) for row in data["decisions"]}


def board(data, turn):
    return copy.deepcopy(next(raw for raw in data["boards"] if raw["turn"] == turn))


def fresh(data, first):
    """A fresh policy primed on the board of ``first`` with the stop's remembered terrain."""
    policy = HengbotPolicy(monrace_knowledge=knowledge(data))
    policy.prime(parse_snapshot(board(data, first), policy._monrace_knowledge))
    terrain = data["terrain"]
    for name in TERRAIN_SETS:
        getattr(policy, f"_remembered_{name}_t").update(tuple(cell) for cell in terrain[f"{name}_t"])
    policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
    policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
    return policy


def step(raw, key):
    return Position(here(raw).y + MOVES[key][0], here(raw).x + MOVES[key][1])


L346 = case("l1-346")
L356 = case("l1-356")
GAZER, GAZER_SEEN = (2, 218), Position(25, 19)
WARG_SEEN, WARG_PILE = Position(6, 88), Position(6, 82)


class AwakeThreatOutOfSightRecordedTest(RecordedHarness):
    def test_recorded_rows(self):
        rows = recorded(L346)
        self.assertEqual(rows[1301140], ("9", "status-threat:retreat"))
        self.assertEqual(rows[1301148], ("1", "seek-loot"))
        self.assertEqual(here(board(L346, 1301140)), Position(24, 23))
        self.assertEqual(here(board(L346, 1301148)), Position(23, 24))
        self.assertEqual(board(L346, 1301148)["visible_monsters"], [])
        self.assertEqual(L346["modes"]["_status_threat_latch"], [[1, 18, 0], [list(GAZER)]])
        rows = recorded(L356)
        self.assertEqual(rows[368888], ("1", "explore"))
        self.assertEqual(rows[368898], ("9", "seek-loot"))
        self.assertEqual([(m["race_id"], m["y"], m["x"], m["asleep"])
                          for m in board(L356, 368888)["visible_monsters"]], [(257, 6, 88, False)])
        self.assertEqual(board(L356, 368898)["visible_monsters"], [])

    def drive_346(self):
        """Decide the recorded boards from (24,23) as the gazer wakes to (23,24)."""
        policy = fresh(L346, 1301122)
        for raw in L346["boards"]:
            if raw["turn"] < 1301122:
                continue
            if raw["turn"] == 1301148:
                return policy, copy.deepcopy(raw)
            key = decide(policy, copy.deepcopy(raw))
            if key:
                policy.confirm_key_posted(key)
        self.fail("no board 1301148")

    def test_the_gazer_out_of_sight_keeps_the_loot_and_the_walks_off(self):
        policy, raw = self.drive_346()
        self.assertEqual(policy.last_reason, "status-threat:retreat")
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        start, distance = raw["turn"], here(raw).distance_to(GAZER_SEEN)
        reasons = []
        while raw["turn"] - start <= UNSEEN_GAME_TURNS and len(reasons) < 12:
            key = decide(policy, copy.deepcopy(raw))
            reasons.append(policy.last_reason)
            if key:
                policy.confirm_key_posted(key)
            if not reasons[1:]:
                # bot-15049b9: ('1', 'seek-loot') back to (24,23), as recorded.
                self.assertNotEqual(policy.last_reason, "seek-loot")
                self.assertNotEqual(step(raw, key) if key in MOVES else None, Position(24, 23))
                # The first board out of sight: the gazer is judged at its last cell.
                self.assertEqual([(m.index, m.race_id) for m in
                                  sleeper_reach_memory.remembered(policy, snapshot)], [GAZER])
                self.assertTrue(sleeper_loot_block.holds(policy, snapshot))
                veto = policy._engagement_route_veto(snapshot)
                self.post(policy, raw, key, [], self.later(raw))
            if key not in MOVES:
                break
            # DECLARED COUNTERFACTUAL: the player follows the decided moves with the gazer
            # out of sight, ten game turns a decision.
            moved = step(raw, key)
            self.assertGreaterEqual(moved.distance_to(GAZER_SEEN), distance,
                                    (raw["turn"], key, policy.last_reason))
            raw["player"]["y"], raw["player"]["x"] = moved.y, moved.x
            raw["turn"] += 10
            raw["messages"] = []
        self.assertNotIn("seek-loot", reasons)
        self.assertIn(Position(24, 23), veto)

    def test_the_warg_out_of_sight_keeps_the_loot_walk_off_its_area(self):
        policy = fresh(L356, 368888)
        raw = board(L356, 368888)
        key = decide(policy, copy.deepcopy(raw))
        self.assertEqual((key, policy.last_reason), ("1", "explore"))
        self.post(policy, raw, key, [], board(L356, 368898))
        policy.confirm_key_posted(key)
        # DECLARED CONSTRUCTED (module docstring): the pile inside the warg's area.
        policy._known_loot, policy._deferred_loot = {WARG_PILE}, set()
        raw = board(L356, 368898)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = decide(policy, copy.deepcopy(raw))
        # bot-47982d326: ('9', 'seek-loot') to (6,78), as recorded.
        self.assertNotEqual(policy.last_reason, "seek-loot")
        self.assertNotIn(key, MOVES)
        self.assertEqual([(m.race_id, m.position) for m in
                          sleeper_reach_memory.remembered(policy, snapshot)], [(257, WARG_SEEN)])
        self.assertIn(WARG_PILE, policy._engagement_route_veto(snapshot))


if __name__ == "__main__":
    unittest.main()
