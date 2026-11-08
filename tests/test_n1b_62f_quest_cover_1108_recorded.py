"""n1-b life-348, Angband 62F, RANDOM quest 46 (アーデンの森の主『ジュリアン』, race 794), 2026-11-08 16:12-16:18.

Owner 2026-11-08: 「n1-bがまたクエストフロアで無為に放浪している」, and 「62Fのループもフロア全体を探索
できず、一定範囲をループしてしまっている。クエストターゲットを探すには少なくとも感知範囲がフロア全域を
網羅するように歩かなければならない。」, then 「半端な定義は許可しない。外周マス以外の全てを感知する必要
がある。」 (search_coverage: every grid but the outer ring, walls included).

Recorded (tests/extract_n1b_62f_quest_cover_1108_fixture.py): the bot walked from the east side
through (28,65) into the west corridor at game turn 3217357; back east, a 石の宝箱 (race 1368, BITE
SHATTER) bit it twice (3218303, 3218308) and its earthquake (monster-attack-switcher.cpp:492,
radius 8) left (28,65) a MAGMA_VEIN (terrain 50, remembered from 3218746).  From 3218746 the
decisions are ``quest-search:loop`` over the east side.  The lap's stops were drawn to cover the
walkable cells only, so a part of the floor lay out of every stop's telepathy (MAX_PLAYER_SIGHT).

DECLARED CONSTRUCTED: the checkpoint's remembered terrain and the ledger's mappings installed on
the policy, and the east frontiers the replayed explore still names written off (the recorded
explore answered nothing on this board: its rows are ``quest-search:loop``).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

import hengbot.policy  # noqa: F401 -- loads the modules in their cycle-safe order
from hengbot import me_powers
from hengbot import quest_target_search as search
from hengbot import search_coverage
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.exploration_ledger import ExplorationLedger
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy
from tests.test_input_executor import FaithfulHookGame, ProductionHarness, command_screen

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-62f-quest-cover-1108.json.xz"
SEALED = Position(28, 65)
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def _pin():
    return json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))


class N1b62fQuestCoverRecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.pin = _pin()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def snapshot(self, policy, raw):
        return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)

    def choose(self, policy, raw):
        return str(policy.choose_key(self.snapshot(policy, raw)))

    def policy(self):
        raw = copy.deepcopy(self.pin["board"])
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        board = self.snapshot(policy, raw)
        ledger = ExplorationLedger(None)
        ledger.bind(board)
        ledger.mapped_areas = {tuple(area) for area in self.pin["mapped_areas"]}
        policy._exploration_ledger = ledger
        policy.prime(board)
        terrain = self.pin["terrain"]
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy, raw

    def to_the_lap(self, policy, raw):
        """Write off the frontiers the replayed explore names until the lap answers."""
        for _ in range(60):
            policy._recent.clear()  # the same board each time: no oscillation, no livelock
            policy._move_repeat = 0
            key = self.choose(policy, raw)
            if policy.last_reason.startswith("quest-search"):
                return key
            self.assertEqual(policy.last_reason, "explore")
            policy._exploration_ledger.probed_frontiers.add(policy._explore_goal_identity.position)
            policy._clear_explore_path(None)
            policy._explore_goal_identity = None
        self.fail("the quest search never answered")

    def coverage(self, policy, raw, stops, radii=None):
        """(the grids to cover, those within each stop's reach: ``radii`` or telepathy's)."""
        board = self.snapshot(policy, raw)
        floor = search_coverage.floor_grids(board)
        radius = search_coverage.walk_radius(policy, board)
        covered = search_coverage.covered(floor.shape, (
            ((stop.y, stop.x), (radii or {}).get(stop, radius)) for stop in stops))
        return floor, covered & floor

    # -- the recording -------------------------------------------------------

    def test_recorded_earthquake_seals_the_west(self):
        floor = self.pin["board"]["floor"]
        self.assertEqual((floor["dungeon_id"], floor["level"], floor["quest_id"]), (1, 62, 46))
        rows = self.pin["decisions"]
        walked = [row["turn"] for row in rows if (row["position"]["y"], row["position"]["x"]) == (28, 65)]
        self.assertEqual(walked, [3217357])
        bites = [row["turn"] for row in rows if any("石の宝箱に噛まれた" in m for m in row["messages"])]
        self.assertTrue({3218303, 3218308} <= set(bites), bites)
        # The same bite's earthquake was seen once in view (16:10:47, Angband 62F (5,160)).
        quake = [row["turn"] for row in rows if "ダンジョンの壁が崩れた！" in row["messages"]]
        self.assertEqual(quake[:1], [3212870])
        self.assertIn(3212870, bites)
        self.assertIn([28, 65], self.pin["terrain"]["wall_t"])
        lap = [row for row in rows if row["reason"] == search.LOOP_REASON]
        self.assertEqual(len(lap), 1717)
        self.assertGreaterEqual(min(row["position"]["x"] for row in lap), 42)

    # -- the fix -------------------------------------------------------------

    def test_the_lap_covers_every_floor_grid_a_walkable_cell_covers(self):
        policy, raw = self.policy()
        self.to_the_lap(policy, raw)
        memory = getattr(policy, search.MEMORY)
        board = self.snapshot(policy, raw)
        routes = search._routes(policy, board)
        floor, covered = self.coverage(policy, raw, memory.stops)
        _, reach = self.coverage(policy, raw, list(routes))
        # Every floor grid any walkable cell covers is covered by a stop.
        self.assertEqual(int(np.count_nonzero(reach & ~covered)), 0)
        # The sight-only stops of the recorded lap covered less (revert: equal).
        _, old = self.coverage(policy, raw, search.draw_stops(board, set(routes)))
        self.assertGreater(int(np.count_nonzero(covered)), int(np.count_nonzero(old)) + 200)
        self.assertEqual(memory.unreached, int(np.count_nonzero(floor & ~reach)))
        self.assertGreater(memory.unreached, 0)

    def test_every_grid_inside_the_outer_ring_is_to_be_covered(self):
        """Owner 2026-11-08 「半端な定義は許可しない。外周マス以外の全てを感知する必要がある。」"""
        policy, raw = self.policy()
        self.to_the_lap(policy, raw)
        memory = getattr(policy, search.MEMORY)
        floor, covered = self.coverage(policy, raw, memory.stops)
        self.assertEqual(int(np.count_nonzero(floor)), 42 * 196)
        self.assertFalse(floor[0, :].any() or floor[-1, :].any() or floor[:, 0].any() or floor[:, -1].any())
        # A remembered wall inside the ring is a grid to cover, and the lap covers it.
        self.assertIn([28, 65], self.pin["terrain"]["wall_t"])
        self.assertTrue(floor[28, 65])
        self.assertTrue(covered[28, 65])
        # Every remembered wall grid that telepathy from a walkable cell reaches is reached by a
        # stop (revert to the walls-left-out grids: some are not).
        board = self.snapshot(policy, raw)
        _, reach = self.coverage(policy, raw, list(search._routes(policy, board)))
        walls = np.zeros(floor.shape, dtype=bool)
        for y, x in policy._remembered_wall_t:
            walls[y, x] = True
        self.assertGreater(int(np.count_nonzero(walls & reach)), 1000)
        self.assertEqual(int(np.count_nonzero(walls & reach & ~covered)), 0)

    def test_a_held_detection_covers_what_telepathy_cannot(self):
        policy, raw = self.policy()
        self.to_the_lap(policy, raw)
        # DECLARED: n1-b's absorbed Detection and Detect Evil with charges (the recorded casts;
        # given after the lap began, so their own new-floor rows do not answer first), and the
        # lap drawn again (the door round toward the sealed west answers first on this board).
        policy._me_staff_sequence = MeStaffSequence(absorbed={"rod:6": 10, "staff:15": 10})
        memory = getattr(policy, search.MEMORY)
        board = self.snapshot(policy, raw)
        memory.stops = search._draw(policy, board, memory, search._routes(policy, board))
        self.assertEqual(search.held_cast_radius(policy, board), 30)
        casts = [stop for stop in memory.stops if memory.stop_radius[stop] == 30]
        self.assertTrue(casts)
        routes = search._routes(policy, board)
        floor, covered = self.coverage(policy, raw, memory.stops, memory.stop_radius)
        _, reach = self.coverage(policy, raw, list(routes), {cell: 30 for cell in routes})
        self.assertEqual(int(np.count_nonzero(reach & ~covered)), 0)
        self.assertEqual(memory.unreached, int(np.count_nonzero(floor & ~reach)))
        # Telepathy alone leaves grids out that the casts reach.
        _, telepathy = self.coverage(policy, raw, list(routes))
        self.assertGreater(int(np.count_nonzero(reach & ~telepathy)), 0)

    def test_without_telepathy_only_the_casts_count(self):
        """Owner 2026-11-08 21:5x 「感知を使った範囲だけ数える」."""
        policy, raw = self.policy()
        self.to_the_lap(policy, raw)
        raw = copy.deepcopy(raw)
        del raw["player"]["ability_sources"]["telepathy"]  # DECLARED: no telepathy
        board = self.snapshot(policy, raw)
        memory = getattr(policy, search.MEMORY)
        routes = search._routes(policy, board)
        self.assertEqual(search_coverage.walk_radius(policy, board), 0)
        # With no means at all: the grids in view count, and the lap is its sight stops.
        in_view = {(grid.position.y, grid.position.x) for grid in board.grids.values() if grid.in_view}
        self.assertEqual({(y, x) for y, x, r in search._reach_now(policy, board) if r == 0}, in_view)
        self.assertEqual(search._draw(policy, board, memory, routes), search.draw_stops(board, set(routes)))
        # DECLARED: the absorbed Detection and Detect Evil with charges.
        policy._me_staff_sequence = MeStaffSequence(absorbed={"rod:6": 10, "staff:15": 10})
        self.assertEqual(search._reach_now(policy, board), [])
        stops = search._draw(policy, board, memory, routes)
        casts = [stop for stop in stops if memory.stop_radius[stop] == 30]
        self.assertTrue(casts)
        floor, covered = self.coverage(policy, raw, stops, memory.stop_radius)
        _, reach = self.coverage(policy, raw, list(routes), {cell: 30 for cell in routes})
        self.assertEqual(int(np.count_nonzero(reach & ~covered)), 0)
        self.assertEqual(memory.unreached, int(np.count_nonzero(floor & ~reach)))

    def install_detections(self, policy, raw):
        """DECLARED: the floor's 37 recorded detections (me_powers' floor memory at 16:18) cast
        again at this board's game turn."""
        board = self.snapshot(policy, raw)
        memory = getattr(policy, me_powers.MEMORY, None)
        if memory is None or memory.floor != board.floor_key:
            memory = me_powers.FloorMemory(board.floor_key, raw["turn"])
            setattr(policy, me_powers.MEMORY, memory)
        for use in self.pin["detections"]:
            memory.uses.append(me_powers.Use(
                tuple(use["served"]), tuple(use["used"]), use["trigger"], Position(*use["position"]),
                raw["turn"], reason=use["reason"]))

    def following(self, raw):
        board = copy.deepcopy(raw)
        board["turn"] += 10
        board["messages"] = []
        return board

    def test_the_recorded_detections_covered_every_inner_grid(self):
        shape = (self.pin["board"]["floor"]["height"], self.pin["board"]["floor"]["width"])
        floor = np.zeros(shape, dtype=bool)
        floor[1:-1, 1:-1] = True
        casts = search_coverage.covered(shape, (
            (tuple(use["position"]), 45 if use["reason"].endswith(":powerful") else 30)
            for use in self.pin["detections"]))
        self.assertEqual(len(self.pin["detections"]), 37)
        self.assertEqual(int(np.count_nonzero(floor & ~casts)), 0)

    def test_the_floor_covered_twice_is_given_up(self):
        """Owner 2026-11-08 21:5x 「全域を2回覆ったら諦める」."""
        policy, raw = self.policy()
        self.to_the_lap(policy, raw)
        memory = getattr(policy, search.MEMORY)
        self.assertTrue(policy._quest_floor_exit_locked(self.snapshot(policy, raw)))
        self.assertEqual(memory.sweeps.count, 0)
        for count in (1, 2):
            raw = self.following(raw)
            policy._recent.clear()
            policy._move_repeat = 0
            self.install_detections(policy, raw)
            self.choose(policy, raw)
            self.assertEqual(memory.sweeps.count, count)
            board = self.snapshot(policy, raw)
            self.assertEqual(search.coverage_given_up(policy, board), count == 2)
        # The second coverage released the exit lock: the search mode is over.
        self.assertFalse(policy._quest_floor_exit_locked(board))
        self.assertFalse(search.searching(policy, board))
        raw = self.following(raw)
        self.choose(policy, raw)
        self.assertFalse(policy.last_reason.startswith("quest-search"), policy.last_reason)

    def test_one_coverage_is_not_enough(self):
        policy, raw = self.policy()
        self.to_the_lap(policy, raw)
        raw = self.following(raw)
        self.install_detections(policy, raw)
        self.choose(policy, raw)
        board = self.snapshot(policy, raw)
        self.assertEqual(getattr(policy, search.MEMORY).sweeps.count, 1)
        self.assertTrue(policy._quest_floor_exit_locked(board))
        self.assertEqual(policy._exploration_ledger.search_sweeps, 1)

    def test_the_sealed_passage_is_a_place_a_door_can_be(self):
        policy, raw = self.policy()
        self.to_the_lap(policy, raw)
        board = self.snapshot(policy, raw)
        routes = search._routes(policy, board)
        self.assertIn(Position(27, 65), routes)
        self.assertNotIn(Position(29, 65), routes)
        self.assertIn(SEALED, search.door_walls(policy, board, routes))

    def test_ground_out_of_reach_starts_the_door_round_at_once(self):
        policy, raw = self.policy()
        key = self.to_the_lap(policy, raw)
        memory = getattr(policy, search.MEMORY)
        self.assertEqual(memory.laps, 0)
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        if key in MOVES:
            following["player"]["y"] += MOVES[key][0]
            following["player"]["x"] += MOVES[key][1]
        self.post(policy, raw, key, following)
        self.choose(policy, following)
        self.assertTrue(memory.door_search)
        self.assertIn(policy.last_reason, (search.DOOR_REASON, search.SEARCH_REASON))

    def test_the_lap_cover_survives_a_restart(self):
        """The lap's coverage lives in the floor's ledger, which a restart on the floor reads."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "exploration-ledger.json"
        policy, raw = self.policy()
        board = self.snapshot(policy, raw)
        before = ExplorationLedger(path)
        before.bind(board)
        policy._exploration_ledger = before
        memory = search._memory(policy, board)
        memory.cover.note(board.player.position, search_coverage.walk_radius(policy, board))
        before.save(force=True)
        after = ExplorationLedger(path)
        self.assertTrue(after.bind(board))
        self.assertEqual(after.search_cover, {(17, 132, 20)})

    def post(self, policy, raw, key, following):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                             "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), key)


if __name__ == "__main__":
    unittest.main()
