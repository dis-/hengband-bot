"""n1-c (Magic-Eater) life-205 2026-11-13 04:49: loop-detected on ガラスの城 60F.

Recorded: tests/fixtures/loop-n1c-205-1113.json.gz
(tests/extract_n1c_205_summoner_explore_1113_fixture.py), the Lv42 Magic-Eater's boards from
the floor's arrival (turn 2921091) to the stop (2922761) and the recorded decision rows.

Three ノーム・メイジ (race 281, summoners, not NEVER_MOVE) stand in a pocket of glass floor
walled with glass (GLASS_WALL, terrain 218: LOS without PROJECTION, TerrainDefinitions.jsonc).
The player sees them through the glass; projectable() stops every bolt on a grid without
PROJECTION (projection-path-calculator.cpp:94).  They did not come to the choke (19,31) and
were remembered as summoners that never approach (summoner_wait's expired wait), their line of
fire a zone vetoed for every route.

A (04:48:54-57): from (29,38) the three were in view and the immobile summoner owner stepped
'9' out of the zone to (28,39); there telepathy sensed two of them (the third, asleep, out of
range), immobile_ranged_kill read them as killable from a shooting cell in the pocket, the zone
was withdrawn and the exploration stepped '1' back into (29,38), eight times up to the
oscillation break.  That ranged kill is carried out only for a never-moving monster
(``immobile_ranged_kill.key``, owner 2026-11-02); a summoner that moves now keeps its zone.

B (04:48:58-49:03): from (34,40) a Teleport Away was aimed '4' along row 34 at the mage on
(34,22) through fifteen glass walls (``mCn4``, then the wand's ``mBd4``), 35 times up to the
loop detector.  Each use completed (the game turn advanced every time; at the stop the game
stood in command mode with no prompt): no input desync, a beam that cannot land.  The player's
own beam now stops at a glass wall (policy._stops_player_projection).

Every decision is the public ``choose_key`` of one policy built as the live one
(tests.support.recorded._policy) and driven over the recorded boards from turn 2921424
(the floor's second detection, before the mages were first seen); the decisive keys (the
step after the zone step, and the key at 2922547) are posted through the production
executor port (cli._ExecutorInputPort).
DECLARED RESTORED (policy-state.json of the stop): the staff record ``_me_staff_sequence``, the
absorbed powers' uses on the floor before 2921424 (``_me_power_floor``) and the floor's
*Destruction* entitlement (the arrival's absorbed *Destruction*, 2921097).
DECLARED CONSTRUCTED: the rod and wand lists show Teleport Away with a charge (the recorded
``mCn4`` and ``mBd4`` are the rod and wand rows, rod 13 and wand 3 in the stop's power uses;
the 5% fail rate is constructed).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_use, disenchant_avoid, immobile_ranged_kill, me_powers
from hengbot import me_staff_sequence as sequence
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_KEYS
from hengbot.policy_combat import IMMOBILE_SUMMONER_AVOID_REASON
from tests.support.recorded import (
    EDIT, FaithfulHookGame, ProductionHarness, _policy, command_screen)


FIXTURE = Path(__file__).with_name("fixtures") / "loop-n1c-205-1113.json.gz"
START, FLOOR = 2921424, (20, 60, 0)
FIRST_ZONE_STEP = 2922364       # the first '9' out of the zone at (29, 38)
TELEPORT_TURN = 2922547         # the first 'mCn4' at (34, 40)
INSIDE, OUTSIDE = Position(29, 38), Position(28, 39)
MAGES = (Position(34, 22), Position(35, 22))
TELEPORT_AWAY = "me-power:unbeatable-in-range:teleport-away"
OFFSETS = {key: offset for offset, key in DIRECTION_KEYS.items()}


def _restore(policy, case):
    record = sequence.state(policy)
    for name, value in case["sequence"].items():
        setattr(record, name, frozenset(value) if name == "bought"
                else tuple(value) if name == "remaining" else value)
    destruction_use._memory(policy).entitled_floor = FLOOR
    floor = case["me_power_floor"]
    policy._me_power_floor = me_powers.FloorMemory(tuple(floor["floor"]), START, [
        me_powers.Use(tuple(use["served"]), tuple(use["used"]), use["trigger"],
                      Position(*use["position"]), use["turn"], use["reason"], use["key"],
                      None if use["target"] is None else Position(*use["target"]))
        for use in floor["uses"] if use["turn"] < START])
    teleport_away = "テレポート・アウェイ"
    policy._me_device_lists = {
        "rod": (START, ({"name": teleport_away, "fail": 5, "success": 95, "max": 1,
                         "charging": 0},)),
        "wand": (START, ({"name": teleport_away, "fail": 5, "success": 95, "max": 10,
                          "current": 10},))}


def _skill(case, raw):
    skill = case["skill"]
    return dict(copy.deepcopy(skill), turn=raw["turn"],
                player=dict(skill["player"], level=raw["player"]["level"]))


def _target(position, key):
    offset = OFFSETS.get(key)
    return None if offset is None else Position(position.y + offset[0], position.x + offset[1])


class SummonerZoneGlassRecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), races)
        boards = [raw for raw in cls.case["boards"] if START <= raw["turn"] <= TELEPORT_TURN]
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), races))
        _restore(policy, cls.case)
        policy.consume_skill_knowledge(_skill(cls.case, boards[0]))
        cls.rows = []
        for raw in boards:
            board = parse_snapshot(copy.deepcopy(raw), races)
            key = str(policy.choose_key(board))
            if key.startswith("~f"):  # the recorded skill list answers the re-request
                policy.consume_skill_knowledge(_skill(cls.case, raw))
                key = str(policy.choose_key(board))
            remembered = dict(getattr(policy, "_immobile_summoner_memory", (None, {}))[1])
            cls.rows.append((raw, board, key, policy.last_reason, remembered,
                             frozenset(policy._immobile_summoner_avoid_cells),
                             frozenset(policy._engagement_avoid_cells)))
            if key:
                policy.confirm_key_posted(key)
        cls.policy = policy

    def test_recorded_rows(self):
        recorded = {row["turn"]: (row["reason"], row["key"]) for row in self.case["decisions"]}
        boards = {raw["turn"]: raw for raw in self.case["boards"]}
        here = {turn: Position(raw["player"]["y"], raw["player"]["x"])
                for turn, raw in boards.items()}
        pairs = {(here[turn], recorded[turn]) for turn in recorded
                 if FIRST_ZONE_STEP <= turn < 2922501 and recorded[turn][0] != "search"}
        self.assertEqual(pairs, {(INSIDE, ("explore:avoid-immobile-summoner", "9")),
                                 (OUTSIDE, ("explore", "1")),
                                 (OUTSIDE, ("breakout:seek-frontier", "1"))})
        teleports = [(row["reason"], row["key"]) for row in self.case["decisions"]
                     if row["turn"] >= TELEPORT_TURN]
        self.assertEqual(teleports.count((TELEPORT_AWAY, "mCn4")), 4)
        self.assertEqual(teleports.count((TELEPORT_AWAY, "mBd4")), 31)
        # The live stop stood in command mode with no prompt, one turn past the last use.
        self.assertEqual(self.case["stop"], {"input_kind": "command", "input_prompt": "",
                                             "turn": 2922765})
        for turn in (2922364, 2922547):
            raw = boards[turn]
            self.assertEqual({(m["y"], m["x"]) for m in raw["visible_monsters"]
                              if m["race_id"] == 281} >= {(p.y, p.x) for p in MAGES}, True)

    def test_mages_are_walled_with_glass(self):
        raw, board = next((raw, board) for raw, board, *_ in self.rows
                          if raw["turn"] == TELEPORT_TURN)
        between = [board.grid_at(Position(34, x)) for x in range(23, 40)]
        self.assertTrue(all(grid is not None and grid.terrain_id == 218 for grid in between
                            if grid is not None and not grid.passable))
        self.assertIn(218, self.policy._los_only_terrain_ids)

    def test_the_zone_outside_keeps_the_mages_and_the_cell_left(self):
        checked = 0
        for raw, board, key, reason, remembered, zone, vetoed in self.rows:
            here = board.player.position
            if raw["turn"] <= FIRST_ZONE_STEP or here != OUTSIDE or raw["turn"] >= 2922501:
                continue
            checked += 1
            # The two sensed mages stay remembered (immobile_ranged_kill.key never shoots
            # a summoner that moves, so killable does not read them as killed).
            self.assertTrue(set(MAGES) <= set(remembered), raw["turn"])
            for mage in board.detected_monsters:
                self.assertFalse(immobile_ranged_kill.killable(self.policy, board, mage))
                # Nor would a shot land: the shooting cell (29,38) reads the glass as open
                # only for a monster's reach (policy._player_may_project).
                self.assertIsNone(immobile_ranged_kill.plan(self.policy, board, mage),
                                  (raw["turn"], mage.position))
            self.assertIn(INSIDE, zone, raw["turn"])
            self.assertIn(INSIDE, vetoed, raw["turn"])
            self.assertNotIn(_target(here, key), zone, (raw["turn"], key, reason))
        self.assertGreaterEqual(checked, 15)

    def test_no_owner_steps_back_into_the_cell_the_zone_step_left(self):
        # One rule: the cells the avoid step leaves stay vetoed for the next owner.
        checked = 0
        for before, after in zip(self.rows, self.rows[1:]):
            raw, board, key, reason, *_ = before
            left = board.player.position
            if reason != IMMOBILE_SUMMONER_AVOID_REASON or after[1].player.position != _target(
                    left, key):
                continue
            checked += 1
            step = _target(after[1].player.position, after[2])
            self.assertNotEqual(step, left, (after[0]["turn"], after[2], after[3]))
            self.assertNotIn(step, after[5], (after[0]["turn"], after[2], after[3]))
        self.assertGreaterEqual(checked, 8)

    def test_a_never_mover_the_kill_leaves_alone_keeps_its_zone(self):
        """killable and key read one rule (immobile_ranged_kill._key_plan).

        DECLARED CONSTRUCTED on the recorded (28,39) board 2922371: the sensed mage's race
        made a never-moving disenchant breather (NEVER_MOVE, BR_DISE: a kept-away one
        ``key`` leaves alone, disenchant_avoid.left_alone), the player's equipment
        resistance to disenchantment taken off, and a safe ranged kill given (``plan``
        answering a shot from here).  ``key`` does not shoot it, so the immobile summoner
        owner must not read it as killed."""
        raw = copy.deepcopy(next(row[0] for row in self.rows
                                 if row[0]["turn"] == FIRST_ZONE_STEP + 7))
        raw["player"]["ability_sources"].pop("resist_disen")
        races = self.policy._monrace_knowledge
        breather = replace(races[281], flags=races[281].flags | {"NEVER_MOVE"},
                           abilities=races[281].abilities | {"BR_DISE"})
        with mock.patch.dict(races, {281: breather}):
            board = parse_snapshot(raw, races)
            mage = next(m for m in board.detected_monsters if m.position == MAGES[0])
            shot = immobile_ranged_kill.KillPlan(mage, None)
            with mock.patch.object(immobile_ranged_kill, "plan", return_value=shot):
                self.assertTrue(immobile_ranged_kill.kept_away(self.policy, board, mage))
                self.assertTrue(disenchant_avoid.left_alone(
                    self.policy, board, mage, immobile_ranged_kill.closes_the_way))
                self.assertFalse(immobile_ranged_kill.killable(self.policy, board, mage))
                # Not left alone, the same never-mover is the kill's: its zone is withdrawn.
                with mock.patch.object(disenchant_avoid, "left_alone", return_value=False):
                    self.assertTrue(immobile_ranged_kill.killable(self.policy, board, mage))

    def test_the_decisive_keys_complete_through_the_executor(self):
        boards = {raw["turn"]: raw for raw in self.case["boards"]}
        turns = sorted(boards)
        for turn in (FIRST_ZONE_STEP + 7, TELEPORT_TURN):  # 2922371 at (28,39), then (34,40)
            raw, board, key, reason, *_ = next(row for row in self.rows if row[0]["turn"] == turn)
            self.assertIsNotNone(_target(board.player.position, key), (turn, key, reason))
            following = boards[turns[turns.index(turn) + 1]]
            self.assertEqual(self.post(raw, key, reason, following), [key], turn)

    def post(self, raw, key, reason, following):
        """``key`` through the production executor port; the game then shows ``following``."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": reason, "sequence": 1}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed", port.last_result.reason)
        return game.accepted

    def test_no_teleport_away_through_the_glass(self):
        raw, board, key, reason, *_ = next(row for row in self.rows if row[0]["turn"] == TELEPORT_TURN)
        self.assertEqual(board.player.position, Position(34, 40))
        self.assertIsNone(me_powers.beam_direction(self.policy, board, Position(34, 40),
                                                   Position(34, 22)))
        self.assertNotEqual(reason, TELEPORT_AWAY, key)
        self.assertFalse(key.startswith("mCn") or key.startswith("mBd"), key)


if __name__ == "__main__":
    unittest.main()
