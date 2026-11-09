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

L3, n1-b life-355 (Magic-Eater Lv38, Angband 71F, 2026-11-09 04:01 loop-detected, build
bot-ab000a523): a pack of フローラのアイリッシュ犬 (race 254) was detected south.  At (36,119)
``detected:prepare-choke`` stepped '7' to (35,118) on its committed retreat; there a sleeping
石ドラゴン (race 1048) 5 cells away came into view, the preparation released its retreat for the
visible-monster channel (which had nothing to do with a sleeper) and seek-loot stepped '3' back
to (36,119), out of the dragon's sight, until the loop detector.  The fourth stop of this
owner pair (09-23, 10-02, 10-23); a sleeper in view no longer releases the episode.
DECLARED RECONSTRUCTION (355): nothing is missing for the floor's abilities, as the recorded
depth_safety (the live process knew its absorbed powers, a fresh policy has not read the power
list).  DECLARED COUNTERFACTUAL: from (35,118) the player follows the decided moves with the
dragon in view and the pack detected as on that board, four game turns a decision.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest import mock

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
L355 = case("l3-355")
DRAGON = Position(34, 113)
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
        """Decide the recorded boards from (24,23) as the gazer wakes to (23,24).

        Owner 2026-11-09 E (deaths-1109, 1eb1e326b7): without Free Action a HOLD caster is a
        paralyser in contact once it has the player in sight, and the 09-18 rung leaves it
        with the escape scroll.  The ゲイザー casts HOLD (MonraceDefinitions id 218, spells
        HOLD/CONF): awake 3 cells away in the open from 1301131 on, it is now read away from
        ('status-threat:scroll', 'rh'), where bot-15049b9 walked off ('9',
        'status-threat:retreat').  DECLARED COUNTERFACTUAL for the L1 pins below: the
        recorded walk is posted instead of the scroll (1301140 '9'; 1301131 decided nothing
        in the record), so the recorded boards that follow it hold -- the case of an awake
        threat out of sight after a walk away, which L1 is about.
        """
        policy = fresh(L346, 1301122)
        rows = recorded(L346)
        for raw in L346["boards"]:
            if raw["turn"] < 1301122:
                continue
            if raw["turn"] == 1301148:
                return policy, copy.deepcopy(raw)
            key = decide(policy, copy.deepcopy(raw))
            if raw["turn"] > 1301122:
                self.assertEqual((key, policy.last_reason), ("rh", "status-threat:scroll"))
                key = rows[raw["turn"]][0] if raw["turn"] in rows else None
            if key:
                policy.confirm_key_posted(key)
        self.fail("no board 1301148")

    def test_the_gazer_out_of_sight_keeps_the_loot_and_the_walks_off(self):
        """L1 after the walk off: the gazer stays at its last cell and blocks the loot.

        Before owner E the walk off was the status-threat rung's retreat, whose latch and
        threat ring kept the later steps walking away (the distance from GAZER_SEEN never
        fell, (24,23) in the route veto).  Owner E answers the gazer in sight on the 09-18
        rung instead (``drive_346``), which neither latches nor rings it, so those two
        retreat properties no longer arise on this record; the L1 properties do.
        """
        policy, raw = self.drive_346()
        start = raw["turn"]
        reasons = []
        while raw["turn"] - start <= UNSEEN_GAME_TURNS and len(reasons) < 12:
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = decide(policy, copy.deepcopy(raw))
            reasons.append(policy.last_reason)
            if key:
                policy.confirm_key_posted(key)
            # Out of sight the gazer is judged at its last cell, and the loot block it
            # made holds (bot-15049b9: ('1', 'seek-loot') back to (24,23), as recorded).
            self.assertEqual([(m.index, m.race_id) for m in
                              sleeper_reach_memory.remembered(policy, snapshot)], [GAZER])
            self.assertTrue(sleeper_loot_block.holds(policy, snapshot))
            if not reasons[1:]:
                self.assertNotEqual(step(raw, key) if key in MOVES else None, Position(24, 23))
                self.post(policy, raw, key, [], self.later(raw))
            if key not in MOVES:
                break
            # DECLARED COUNTERFACTUAL: the player follows the decided moves with the gazer
            # out of sight, ten game turns a decision.
            moved = step(raw, key)
            raw["player"]["y"], raw["player"]["x"] = moved.y, moved.x
            raw["turn"] += 10
            raw["messages"] = []
        self.assertNotIn("seek-loot", reasons)

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


class SleeperInViewKeepsTheChokeRetreatRecordedTest(RecordedHarness):
    def test_recorded_rows(self):
        rows = recorded(L355)
        self.assertEqual(rows[4072513], ("7", "detected:prepare-choke"))
        self.assertEqual(rows[4072518], ("3", "seek-loot"))
        self.assertEqual(rows[4072522], ("7", "detected:prepare-choke"))
        shown = board(L355, 4072518)
        self.assertEqual(here(shown), Position(35, 118))
        self.assertEqual([(m["race_id"], m["y"], m["x"], m["asleep"]) for m in shown["visible_monsters"]],
                         [(1048, 34, 113, True)])
        self.assertEqual(board(L355, 4072522)["visible_monsters"], [])
        self.assertEqual({m["race_id"] for m in shown["detected_monsters"]} - {1048}, {254})

    def test_the_retreat_reaches_its_choke_with_the_sleeper_in_view(self):
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
            policy = fresh(L355, 4072421)
            for raw in L355["boards"]:
                if raw["turn"] < 4072421:
                    continue
                if raw["turn"] == 4072518:
                    break
                key = decide(policy, copy.deepcopy(raw))
                if key:
                    policy.confirm_key_posted(key)
            self.assertEqual(policy.last_reason, "detected:prepare-choke")
            raw = copy.deepcopy(raw)
            distance, reasons = here(raw).distance_to(DRAGON), []
            for index in range(8):
                key = decide(policy, copy.deepcopy(raw))
                reasons.append(policy.last_reason)
                if key:
                    policy.confirm_key_posted(key)
                if index == 0:
                    # bot-ab000a523 and 47982d326: ('3', 'seek-loot') to (36,119), as recorded.
                    self.assertEqual(policy.last_reason, "detected:prepare-choke")
                    self.post(policy, raw, key, [], self.later(raw, 4))
                if key in MOVES:
                    moved = step(raw, key)
                    self.assertGreaterEqual(moved.distance_to(DRAGON), distance, (raw["turn"], key))
                    raw["player"]["y"], raw["player"]["x"] = moved.y, moved.x
                raw["turn"] += 4
                raw["messages"] = []
            self.assertNotIn("seek-loot", reasons)
            self.assertEqual(reasons[-1], "detected:hold-choke")


L173 = case("l5-173")


class MazeBearAreaRecordedTest(RecordedHarness):
    """L5, n1-c life-173 (Magic-Eater Lv22, Labyrinth 15F, 2026-11-08 21:12 loop-detected,
    build bot-234f9fd): an awake 凶熊 (race 1028, material melee: the engagement retreat
    keeps away from it) stood 19 cells west along the one-cell corridor of row 2.  In view at
    (2,55) its area was the routes' veto (and its cell out of the route,
    ``_explore_past_monster_cells``), so the explore had no frontier past it and
    stuck:seek-stairs stepped '3' to (3,56); out of view there the veto was empty and the explore
    stepped '7' straight back, until the loop detector.  life-128's rule (the same answer in
    and out of view) held only for sleepers.  The L1 memory (owner 2026-11-09
    「起きた敵も最後の位置を覚える」) keeps the awake bear's area out of view.
    DECLARED RECONSTRUCTION: the fresh policy knows the Labyrinth as the two boards show it, so
    its explore goal differs from the live one (which had probed the frontiers south-east);
    the pin is the veto both boards route under."""

    def test_recorded_rows(self):
        rows = recorded(L173)
        self.assertEqual(rows[870856], ("3", "stuck:seek-stairs"))
        self.assertEqual(rows[870867], ("7", "explore"))
        self.assertEqual([(m["race_id"], m["y"], m["x"], m["asleep"])
                          for m in board(L173, 870856)["visible_monsters"]], [(1028, 2, 37, False)])
        self.assertEqual(board(L173, 870867)["visible_monsters"], [])

    def test_the_bears_area_is_the_same_veto_out_of_view(self):
        policy = HengbotPolicy(monrace_knowledge=knowledge(L173))
        policy.prime(parse_snapshot(board(L173, 870856), policy._monrace_knowledge))
        vetoes = []
        for turn in (870856, 870867):
            raw = board(L173, turn)
            key = decide(policy, copy.deepcopy(raw))
            if key:
                policy.confirm_key_posted(key)
            snapshot = policy._with_grid_memory(
                parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            vetoes.append(policy._engagement_route_veto(snapshot))
        # bot-234f9fd and 47982d326: empty out of view.
        self.assertEqual(vetoes[1], vetoes[0])
        self.assertIn(Position(2, 45), vetoes[1])


if __name__ == "__main__":
    unittest.main()
