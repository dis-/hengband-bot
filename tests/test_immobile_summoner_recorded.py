"""Recorded stop boards from both 2026-10-27 immobile-summoner captures.

Restart replay: public choose_key on each unmodified final state. Only the
skill-exp observation cache is seeded (not a decision producer). Follow posts
use the production executor with DECLARED CONSTRUCTED command boundaries and
one-step movement effects, not a claim of a new live game recording.
DECLARED CONSTRUCTED: quest/no-exit corridors, usable exit scrolls, an aligned
bow, a low-HP Healing potion, and movable-race controls below.
"""

from __future__ import annotations

import tests  # noqa: F401
import copy
import gzip
import hashlib
import io
import json
import time
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.cli import (
    PostingContract, STATIONARY_REASONS, _ExecutorInputPort, _send_decision_key_with_prompt_chain,
)
from hengbot.model import Position, QuestState, Snapshot, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import QUEST_STATUS_TAKEN
from hengbot.quest_knowledge import QUEST_TYPE_RANDOM
from hengbot.summoner_wait import SUMMONER_WAIT_GAME_TURNS
from tests import policy_fixtures as fixtures
from tests import test_input_executor as executor_pins


FIXTURE = Path(__file__).parent / "fixtures" / "immobile-summoner-20261027.json.gz"
SHA256 = "e194616e534ec361456a89435d015168ae33c0e8e320b09ea58f4c410cf7e742"
EDIT = Path("C:/hengband/lib/edit")
OFFSETS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
           "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


class ImmobileSummonerRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.records = json.loads(gzip.decompress(data))
        glass = FIXTURE.with_name("glass-summoner-20261027.json.gz").read_bytes()
        assert hashlib.sha256(glass).hexdigest() == "59c9c108d76f2279e7c4f2e854abb3f32206c846dccfe2181450ec04f49f9abb"
        cls.glass_records = json.loads(gzip.decompress(glass))
        cls.knowledge = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _policy(self, board, *, mobile=False):
        knowledge = dict(self.knowledge)
        if mobile:
            # DECLARED CONSTRUCTED control: same race without NEVER_MOVE.
            knowledge[397] = replace(knowledge[397], flags=knowledge[397].flags - {"NEVER_MOVE"})
        policy = HengbotPolicy(monrace_knowledge=knowledge)
        policy.prime(board)
        policy._skill_exp_cache = (
            board.player.race_id, board.player.class_id, board.player.level,
            policy._town_visit_epoch,
        )
        return policy

    def _post(self, policy, board, key, raw):
        # DECLARED CONSTRUCTED: execute the posted command, then report a fresh
        # command boundary. Walking effects come only from the numeric direction.
        after = copy.deepcopy(raw)
        if str(key) in OFFSETS:
            dy, dx = OFFSETS[str(key)]
            after["player"]["position"] = {
                "y": board.player.position.y + dy, "x": board.player.position.x + dx,
            }
        after["turn"] = board.turn + 10
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(board.turn)
        game.screens = [executor_pins.command_screen(after["turn"])]
        game.states = [after]
        if str(key).startswith("r"):
            # DECLARED CONSTRUCTED: reading first exposes the game's item
            # source prompt; the reserved selector is sent only after it.
            game.screens.insert(0, executor_pins.prompt_screen("どの巻物を読みますか? "))
            game.states.insert(0, copy.deepcopy(raw))
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line, chain, _result = _send_decision_key_with_prompt_chain(
            port, "recorded-board", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 30,
            poll_interval=0.0, prompt_japanese=True,
            decision={"sequence": 1, "reason": policy.last_reason}, snapshot=board,
            posting_contract=PostingContract(), in_store=False,
        )
        self.assertTrue(sent)
        self.assertIsNone(chain)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), str(key))
        policy.confirm_key_posted(key)
        return after

    def _recorded(self, index):
        record = self.records[index]
        board = parse_snapshot(record["board"], self.knowledge)
        self.assertEqual(board.player.position, Position(24, 66))
        self.assertEqual([(m.race_id, m.position) for m in board.visible_monsters],
                         [(397, Position(23, 71))])
        self.assertEqual(record["decision"]["reason"], "summoner:hold-choke")
        self.assertEqual(record["decision"]["key"], "5")
        return record, board

    def _assert_recorded(self, index):
        record, board = self._recorded(index)
        policy = self._policy(board)
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason),
                         ("4", "explore:avoid-immobile-summoner"))
        self.assertNotIn(Position(24, 65), policy._engagement_avoid_cells)
        self.assertIn(Position(24, 70), policy._engagement_avoid_cells)
        after = self._post(policy, board, key, record["board"])
        self.assertEqual(after["player"]["position"], {"y": 24, "x": 65})

    def test_first_capture_avoids_and_posts(self):
        self._assert_recorded(0)

    def test_second_capture_avoids_and_posts(self):
        self._assert_recorded(1)

    def test_mobile_control_keeps_recorded_choke_wait(self):
        for index in (0, 1):
            _record, board = self._recorded(index)
            # DECLARED CONSTRUCTED: no projectiles, so the mobile control
            # reaches the existing generic choke wait rather than ranged fire.
            board = replace(board, inventory=[i for i in board.inventory if i.tval != 18])
            policy = self._policy(board, mobile=True)
            self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                             ("5", "summoner:hold-choke"))

    def _corridor(self, *, quest=False, stairs=False, inventory=(), hp=949,
                  monster_x=15, detected=False, wall=False):
        # DECLARED CONSTRUCTED: a sealed one-cell corridor, no frontiers/loot.
        grids = {
            Position(y, x): fixtures.grid(y, x, passable=y == 10 and 7 <= x <= 16,
                                         in_view=True, lit=True)
            for y in range(9, 12) for x in range(6, 18)
        }
        grids[Position(10, monster_x)] = fixtures.grid(10, monster_x, monster=True,
                                                      in_view=True, lit=True)
        if stairs:
            grids[Position(10, 7)] = fixtures.grid(10, 7, upstairs=True, in_view=True, lit=True)
        if wall:
            grids[Position(10, 12)] = fixtures.grid(10, 12, passable=False, in_view=True)
        monster = fixtures.hostile(19, 10, monster_x, race_id=397, hp=1600, max_hp=1600,
                                   distance=monster_x - 10, can_summon=True)
        board = Snapshot(
            replace(fixtures.player(10, 10, hp=hp, max_hp=949, level=40,
                                    abilities=frozenset({"free_action", "resist_conf", "resist_fire"})),
                    ability_sources={"free_action": frozenset({"intrinsic"})}),
            grids, [] if detected else [monster], floor_key=(3, 23, 41 if quest else 0),
            inventory=list(inventory), width=24, height=22, turn=10000,
            detected_monsters=[replace(monster, perception="detected")] if detected else [],
        )
        if quest:
            board = replace(board, quests={41: QuestState(
                id=41, name="constructed kill quest", status=QUEST_STATUS_TAKEN,
                type=QUEST_TYPE_RANDOM, cur_num=0, max_num=1, level=23,
                r_idx=397, dungeon_id=3,
            )})
        return board

    def test_constructed_quest_approaches_then_melees(self):
        # The quest lock is decisive: exit scrolls exist, but may not abandon
        # this incomplete quest. Without that lock the same board recalls.
        board = self._corridor(quest=True, stairs=True, inventory=[
            fixtures.item("t", 70, 10), fixtures.item("r", 70, 11),
        ])
        policy = self._policy(board)
        self.assertTrue(policy._floor_navigation_exit_locked(board))
        record, _recorded_board = self._recorded(0)
        for x in range(10, 14):
            board = replace(board, player=replace(board.player, position=Position(10, x)),
                            visible_monsters=[replace(board.visible_monsters[0], distance=15-x)],
                            turn=board.turn + 10)
            key = policy.choose_key(board)
            self.assertEqual((str(key), policy.last_reason), ("6", "summoner:cornered-approach"))
            self.assertNotEqual(policy.decision_claim["rung"], "fallback:unregistered")
            self.assertEqual(policy.decision_claim["goal"]["kind"], "Reach")
            self.assertEqual(policy.decision_claim["owner"], "combat")
            # DECLARED CONSTRUCTED: adapt the response substrate to this
            # quest's coordinates/floor; every posted movement is one step.
            raw = copy.deepcopy(record["board"])
            raw["turn"] = board.turn
            raw["player"]["position"] = {"y": 10, "x": x}
            raw["floor"].update(dungeon_id=3, level=23, quest_id=41)
            self._post(policy, board, key, raw)
        board = replace(board, player=replace(board.player, position=Position(10, 14)),
                        visible_monsters=[replace(board.visible_monsters[0], distance=1)],
                        turn=board.turn + 10)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason), ("6", "melee"))

    def test_constructed_no_exit_also_attacks(self):
        board = self._corridor()
        policy = self._policy(board)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("6", "summoner:cornered-approach"))

    def test_constructed_exhausted_safe_region_seeks_stairs_before_scrolls(self):
        board = self._corridor(stairs=True, wall=True, inventory=[
            fixtures.item("t", 70, 10), fixtures.item("r", 70, 11),
        ])
        policy = self._policy(board)
        # West of the summoner's view: existing routing must prefer these stairs.
        policy._visit_counts.update({position: 1 for position in board.grids})
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("4", "summoner:seek-upstairs"))

    def test_constructed_teleport_level_precedes_recall(self):
        board = self._corridor(inventory=[fixtures.item("t", 70, 10), fixtures.item("r", 70, 11)])
        policy = self._policy(board)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("rt", "summoner:teleport-level"))

    def test_constructed_recall_and_countdown(self):
        board = self._corridor(inventory=[fixtures.item("r", 70, 11)])
        policy = self._policy(board)
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("rr", "summoner:recall"))
        raw = copy.deepcopy(self.records[0]["board"])
        raw["turn"] = board.turn
        raw["player"]["position"] = {"y": 10, "x": 10}
        self._post(policy, board, key, raw)
        board = replace(board, player=replace(board.player, recalling=True), turn=10010)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("5", "summoner:wait-recall"))
        self.assertIn(policy.last_reason, STATIONARY_REASONS)

    def test_constructed_quest_uses_existing_ranged_logic(self):
        _record, recorded = self._recorded(0)
        ammo = next(i for i in recorded.inventory if i.tval == 18)
        board = replace(self._corridor(quest=True, inventory=[ammo]),
                        equipment=recorded.equipment)
        policy = self._policy(board)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("f" + ammo.slot + "6", "ranged:fire"))

    def test_constructed_avoid_even_a_three_shot_finish(self):
        _record, recorded = self._recorded(0)
        ammo = next(i for i in recorded.inventory if i.tval == 18)
        board = replace(self._corridor(inventory=[ammo, fixtures.item("r", 70, 11)]),
                        equipment=recorded.equipment)
        board = replace(board, visible_monsters=[replace(board.visible_monsters[0], hp=1)])
        policy = self._policy(board)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("rr", "summoner:recall"))

    def test_constructed_quest_keeps_emergency_healing(self):
        board = self._corridor(quest=True, hp=200, inventory=[fixtures.item("h", 75, 37)])
        policy = self._policy(board)
        key = policy.choose_key(board)
        self.assertEqual(str(key), "qh")
        self.assertEqual(policy.last_reason, "item:heal")

    def test_constructed_unreachable_visible_summoner_does_not_hold_choke(self):
        board = self._corridor(quest=True, wall=True)
        policy = self._policy(board)
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("4", "explore"))

    def test_constructed_unreachable_detected_summoner_releases_cached_hold(self):
        board = self._corridor(quest=True, wall=True, detected=True)
        policy = self._policy(board)
        policy._detected_threat_hold = (board.floor_key, board.turn)
        policy._detected_threat_hold_position = board.player.position
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("4", "explore"))
        self.assertIsNone(policy._detected_threat_hold)

    def test_constructed_immobile_does_not_count_as_converging_melee_pack(self):
        board = self._corridor(quest=True, wall=True, detected=True)
        other = replace(fixtures.hostile(20, 10, 16, distance=4), perception="detected")
        board = replace(board, detected_monsters=[*board.detected_monsters, other])
        policy = self._policy(board)
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("4", "explore"))

    def test_constructed_detected_melee_only_summoner_does_not_complete_pack(self):
        # DECLARED CONSTRUCTED: a summoner with no damaging ranged attacks
        # meets the melee-pack filter unless the shared immobility predicate
        # excludes it. One mobile detected monster alone cannot own a hold.
        board = self._corridor(quest=True, wall=True, detected=True, monster_x=13)
        immobile = replace(board.detected_monsters[0], max_ranged_damage=0)
        mobile = replace(fixtures.hostile(20, 11, 13, distance=3), perception="detected")
        grids = dict(board.grids)
        grids[mobile.position] = fixtures.grid(11, 13, monster=True, in_view=True, lit=True)
        board = replace(board, grids=grids, detected_monsters=[immobile, mobile])
        policy = self._policy(board)
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("4", "explore"))
        raw = copy.deepcopy(self.records[0]["board"])
        raw["turn"] = board.turn
        raw["player"]["position"] = {"y": 10, "x": 10}
        raw["floor"].update(dungeon_id=3, level=23, quest_id=41)
        self._post(policy, board, key, raw)

    def test_recorded_threat_memory_survives_sight_loss_and_retires_on_empty_cell(self):
        record, board = self._recorded(0)
        policy = self._policy(board)
        key = policy.choose_key(board)
        self.assertEqual(str(key), "4")
        after = self._post(policy, board, key, record["board"])
        source = board.visible_monsters[0].position
        # DECLARED CONSTRUCTED: after walking west the source leaves observation.
        grids = dict(board.grids)
        grids[source] = replace(grids[source], in_view=False, currently_observed=False)
        hidden = replace(board, player=replace(board.player, position=Position(24, 65)),
                         grids=grids, visible_monsters=[], turn=after["turn"])
        key = policy.choose_key(hidden)
        self.assertEqual(policy.last_reason, "explore:avoid-immobile-summoner")
        self.assertIn(Position(24, 70), policy._engagement_avoid_cells)
        self.assertIn(source, policy._immobile_summoner_memory[1])
        # DECLARED CONSTRUCTED: a later lit observation certifies the death.
        grids[source] = replace(grids[source], has_monster=False, in_view=True,
                                currently_observed=True)
        empty = replace(hidden, grids=grids, turn=hidden.turn + 10)
        policy.choose_key(empty)
        self.assertEqual(policy._immobile_summoner_memory[1], {})
        self.assertNotIn(Position(24, 70), policy._engagement_avoid_cells)

    def test_recorded_board_collects_safe_loot_and_vetoes_loot_in_summoner_view(self):
        record, board = self._recorded(0)
        safe, unsafe = Position(24, 65), Position(24, 70)
        grids = dict(board.grids)
        # DECLARED CONSTRUCTED: two scroll piles on the recorded terrain.
        for position in (safe, unsafe):
            grids[position] = replace(grids[position], object_count=1, object_tvals=(70,))
        board = replace(board, grids=grids)
        policy = self._policy(board)
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("4", "seek-loot"))
        self.assertEqual(policy._loot_target, safe)
        self.assertIn(unsafe, policy._deferred_loot)
        self._post(policy, board, key, record["board"])

    def _assert_glass_capture(self, index):
        record = self.glass_records[index]
        board = parse_snapshot(record["board"], self.knowledge)
        self.assertEqual(board.player.position, Position(29, 50))
        monster = next(m for m in board.visible_monsters if m.race_id == 915)
        self.assertEqual((monster.position, monster.distance), (Position(26, 49), 3))
        self.assertFalse(self.knowledge[915].flags & {"NEVER_MOVE", "PASS_WALL", "KILL_WALL"})
        self.assertEqual(record["decision"]["reason"], "summoner:hold-choke")
        self.assertEqual(record["decision"]["key"], "5")
        wall = board.grid_at(Position(28, 50))
        self.assertEqual(wall.terrain_id, 218)
        self.assertTrue(wall.allows_los)
        self.assertFalse(wall.enterable)
        policy = self._policy(board)
        self.assertIsNone(policy._monster_path_distance(board, monster.position))
        board, key = self._until_wait_ends(policy, board, record["board"])
        self.assertEqual((str(key), policy.last_reason), ("rg", "summoner:recall"))
        self.assertIn(monster.position, policy._immobile_summoner_memory[1])
        # No safe useful target or stairs exist on these observed boards.
        # _post supplies a CONSTRUCTED scroll prompt / command response.
        self._post(policy, board, key, record["board"])

    def _until_wait_ends(self, policy, board, raw=None):
        # DECLARED CONSTRUCTED: unchanged monsters, HP and ammo on later turns.
        # A restarted glass capture first tries three ineffective cursor shots.
        # Only command/scroll/wait boundaries are constructed; fixtures stay raw.
        waited = 0
        for step in range(30):
            later = replace(board, turn=board.turn + step * 10)
            key = policy.choose_key(later)
            if policy.last_reason == "summoner:hold-choke":
                waited += 1
                if raw is not None:
                    boundary = copy.deepcopy(raw)
                    boundary["turn"] = later.turn
                    self._post(policy, later, key, boundary)
            elif not policy.last_reason.startswith("ranged:"):
                self.assertGreater(waited, 0)
                self.assertLess(step, 40)  # cli.LOOP_WINDOW
                return later, key
        self.fail("summoner wait did not end before the loop guard")

    def test_glass_first_capture_leaves_and_posts(self):
        self._assert_glass_capture(0)

    def test_glass_second_capture_leaves_and_posts(self):
        self._assert_glass_capture(1)

    def test_glass_third_capture_leaves_and_posts(self):
        self._assert_glass_capture(2)

    def _walking_summoner_corridor(self, *, wall=False, quest=False, detected=False):
        # DECLARED CONSTRUCTED: same corridor, mobile race 915; the barrier
        # determines reachability independently of NEVER_MOVE knowledge.
        board = self._corridor(wall=wall, quest=quest, detected=detected,
                               inventory=[fixtures.item("r", 70, 11)])
        channel = "detected_monsters" if detected else "visible_monsters"
        return replace(board, **{channel: [replace(getattr(board, channel)[0], race_id=915)]})

    def test_far_detected_summoner_without_a_wait_keeps_ordinary_behavior(self):
        board = self._walking_summoner_corridor(detected=True)
        monster = replace(board.detected_monsters[0], position=Position(10, 30), distance=20)
        board = replace(board, detected_monsters=[monster], width=40)
        policy = self._policy(board)
        for delta in (0, 10, 50, 100, 500):
            current = replace(board, turn=board.turn + delta)
            policy.choose_key(current)
            self.assertNotEqual(policy.last_reason, "summoner:hold-choke")
            self.assertFalse(policy._summoner_never_approaches(current, monster))
            self.assertEqual(policy._summoner_wait.started, {})
            self.assertEqual(policy._summoner_wait.refused, {})

    def test_approach_resets_only_the_summoner_that_moved(self):
        board = self._walking_summoner_corridor()
        first = board.visible_monsters[0]
        second = replace(first, index=20, position=Position(10, 16), distance=6)
        board = replace(board, visible_monsters=[first, second])
        policy = self._policy(board)
        self.assertEqual(str(policy.choose_key(board)), "5")
        closer = replace(first, position=Position(10, 14), distance=4)
        current = replace(board, turn=board.turn + 40, visible_monsters=[closer, second])
        self.assertEqual(str(policy.choose_key(current)), "5")
        at_limit = replace(current, turn=board.turn + SUMMONER_WAIT_GAME_TURNS)
        policy.choose_key(at_limit)
        self.assertFalse(policy._summoner_never_approaches(at_limit, closer))
        self.assertTrue(policy._summoner_never_approaches(at_limit, second))
        self.assertNotEqual(policy.last_reason, "summoner:hold-choke")

    def test_closer_summoner_restarts_its_wait_clock(self):
        board = self._walking_summoner_corridor()
        policy = self._policy(board)
        for delta in (0, 10, 20, 30, 40):
            current = replace(board, turn=board.turn + delta)
            self.assertEqual(str(policy.choose_key(current)), "5")
        monster = replace(board.visible_monsters[0], position=Position(10, 14), distance=4)
        closer = replace(board, turn=board.turn + 50, visible_monsters=[monster])
        self.assertEqual((str(policy.choose_key(closer)), policy.last_reason),
                         ("5", "summoner:hold-choke"))
        identity = (monster.index, monster.race_id)
        self.assertEqual(policy._summoner_wait.started[identity], (closer.turn, 4))
        before = replace(closer, turn=closer.turn + SUMMONER_WAIT_GAME_TURNS - 1)
        self.assertEqual((str(policy.choose_key(before)), policy.last_reason),
                         ("5", "summoner:hold-choke"))
        expired = replace(closer, turn=closer.turn + SUMMONER_WAIT_GAME_TURNS)
        policy.choose_key(expired)
        self.assertNotEqual(policy.last_reason, "summoner:hold-choke")
        self.assertEqual(policy._summoner_wait.started, {})

    def test_expired_cornered_wait_keeps_fighting_after_our_own_approach(self):
        board = self._walking_summoner_corridor(quest=True)
        policy = self._policy(board)
        later, key = self._until_wait_ends(policy, board)
        self.assertEqual((str(key), policy.last_reason), ("6", "summoner:cornered-approach"))
        # DECLARED CONSTRUCTED: player walks; the summoner has not approached.
        for step in range(1, 5):
            current = replace(board, turn=later.turn + step * 10,
                              player=replace(board.player, position=Position(10, 10 + step)),
                              visible_monsters=[replace(board.visible_monsters[0], distance=5 - step)])
            self.assertEqual(str(policy.choose_key(current)), "6")
            self.assertEqual(policy.last_reason,
                             "melee" if step == 4 else "summoner:cornered-approach")

    def test_choke_wait_clock_clears_on_other_action_and_floor_change(self):
        board = self._walking_summoner_corridor()
        policy = self._policy(board)
        policy.choose_key(board)
        self.assertTrue(policy._summoner_wait.started)
        hurt = replace(board, turn=board.turn + 10,
                       player=replace(board.player, hp=200),
                       inventory=[fixtures.item("h", 75, 37)])
        self.assertEqual(str(policy.choose_key(hurt)), "qh")
        self.assertEqual(policy.last_reason, "emergency:heal")
        self.assertEqual(policy._summoner_wait.started, {})
        restarted = replace(board, turn=board.turn + 100)
        policy.choose_key(restarted)
        self.assertEqual(next(iter(policy._summoner_wait.started.values())), (restarted.turn, 5))
        new_floor = replace(board, turn=board.turn + 200, floor_key=(3, 24, 0))
        self.assertEqual(str(policy.choose_key(new_floor)), "5")
        self.assertEqual(next(iter(policy._summoner_wait.started.values())), (new_floor.turn, 5))
        self.assertEqual(policy._summoner_wait.refused, {})

    def test_glass_constructed_walkable_control_keeps_wait(self):
        board = self._walking_summoner_corridor()
        policy = self._policy(board)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("5", "summoner:hold-choke"))

    def test_partial_map_unknown_barrier_keeps_mobile_summoner_wait(self):
        # DECLARED CONSTRUCTED: the corridor barrier is unobserved. A missing
        # known route cannot prove that the mobile summoner cannot approach.
        board = self._walking_summoner_corridor(wall=True)
        grids = dict(board.grids)
        grids[Position(10, 12)] = fixtures.grid(10, 12, known=False)
        board = replace(board, grids=grids)
        policy = self._policy(board)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("5", "summoner:hold-choke"))
        self.assertFalse(getattr(policy, "_immobile_summoner_avoid_cells", set()))

    def test_partial_map_absent_barrier_keeps_detected_summoner_wait(self):
        # DECLARED CONSTRUCTED: absent map cells are also unknown; detected
        # mobile summoners retain the ordinary choke preparation behaviour.
        board = self._walking_summoner_corridor(wall=True, detected=True)
        grids = dict(board.grids)
        del grids[Position(10, 12)]
        board = replace(board, grids=grids)
        policy = self._policy(board)
        policy._detected_threat_hold = (board.floor_key, board.turn)
        policy._detected_threat_hold_position = board.player.position
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("5", "summoner:hold-choke"))
        self.assertIsNotNone(policy._detected_threat_hold)

    def test_glass_constructed_quest_does_not_wait_for_unreachable_mobile_summoner(self):
        board = self._walking_summoner_corridor(wall=True, quest=True)
        policy = self._policy(board)
        later, key = self._until_wait_ends(policy, board)
        self.assertEqual((str(key), policy.last_reason), ("4", "explore"))

    def test_glass_constructed_detected_quest_releases_cached_hold(self):
        board = self._walking_summoner_corridor(wall=True, quest=True, detected=True)
        policy = self._policy(board)
        policy._detected_threat_hold = (board.floor_key, board.turn)
        policy._detected_threat_hold_position = board.player.position
        later, key = self._until_wait_ends(policy, board)
        self.assertEqual((str(key), policy.last_reason), ("4", "explore"))
        self.assertIsNone(policy._detected_threat_hold)

    def test_glass_constructed_pass_wall_control_keeps_wait(self):
        board = self._walking_summoner_corridor(wall=True)
        policy = self._policy(board)
        policy._monrace_knowledge[915] = replace(self.knowledge[915],
                                                flags=self.knowledge[915].flags | {"PASS_WALL"})
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("5", "summoner:hold-choke"))

    def test_glass_constructed_kill_wall_control_keeps_wait(self):
        board = self._walking_summoner_corridor(wall=True)
        policy = self._policy(board)
        policy._monrace_knowledge[915] = replace(self.knowledge[915],
                                                flags=self.knowledge[915].flags | {"KILL_WALL"})
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason),
                         ("5", "summoner:hold-choke"))

    def test_glass_constructed_closer_summoner_retires_avoidance(self):
        board = self._walking_summoner_corridor(wall=True)
        policy = self._policy(board)
        policy._visit_counts.update({position: 1 for position in board.grids})
        later, key = self._until_wait_ends(policy, board)
        self.assertEqual((str(key), policy.last_reason),
                         ("rr", "summoner:recall"))
        grids = dict(board.grids)
        grids[Position(10, 12)] = fixtures.grid(10, 12, in_view=True, lit=True)
        # Opening terrain alone is no longer evidence; the monster approaches.
        closer = replace(board.visible_monsters[0], position=Position(10, 14), distance=4)
        opened = replace(board, grids=grids, turn=later.turn + 10, visible_monsters=[closer])
        self.assertEqual((str(policy.choose_key(opened)), policy.last_reason),
                         ("5", "summoner:hold-choke"))
        self.assertEqual(policy._immobile_summoner_memory[1], {})
        self.assertEqual(policy._immobile_summoner_avoid_cells, set())


if __name__ == "__main__":
    unittest.main()
