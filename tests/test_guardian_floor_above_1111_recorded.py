"""The floor above a guardian floor is explored; only the descent onto it is refused (C2, P5).

Owner 2026-11-11 (verbatim): 「50F以降の探索方法を見直す。能力的には64Fから成果を得るのに十分で
ある。」  Since 2026-07-15 ``_guardian_floor_blocked`` read ``max_depth - 1`` as the guardian
floor, so the Castle's 64F (guardian 882 on 65F, DungeonDefinitions id 12, maxDepth 65) was
left at once by the ``guardian-kit-insufficient`` return (n1-b life-367, 2026-11-10: arrived on
64F, recalled within 10 decisions, PLAN-50F 1.4 G) and refused as a recall landing.  Now 64F
is a floor like any other; '>' there (onto 65F) is never a descent target while the kit cannot
pass the guardian, and the no-depth-progress valve reads a dive starting on 64F as at its
ceiling.  The guardian floor itself (65F) keeps its return (owner decisions guardian-valve,
guardian-bounce and P3 「守護者が T1 の最下層は…帰還先にしない」 are unchanged).

Recorded (tests/fixtures/castle-summoner-loot-1110.json.xz, tests/test_castle_summoner_loot_
1110_recorded.py's harness): n1-b life-367 (Magic-Eater Lv41) on the Castle, decisions
7302-7305 through the public ``choose_key`` with the static dungeon knowledge the live process
loads; its kit cannot pass the Castle's guardian (``_guardian_floor_blocked(.., 65)``).
DECLARED CONSTRUCTED: the floor's depth (48F recorded, 63F or 64F here) and the boards without
their monsters (the summoner fight of 48F is pinned by its own test); the down staircase under
the player or at a known cell, and the board after it without that cell; the town board after
each dive (the recorded board in the town, Castle landing 64); for the valve, Angband's recall
locked and the alternate record (the Castle, as cli.py wires the record path).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from unittest import mock
from dataclasses import replace

from hengbot.model import Position, parse_snapshot
import tests.test_castle_summoner_loot_1110_recorded as castle

CASTLE, GUARDIAN_FLOOR = 12, 65
DOWN_STAIR_TERRAIN = 7  # TerrainDefinitions.jsonc DOWN_STAIR


def quiet(raw, level):
    raw = copy.deepcopy(raw)
    raw["floor"]["level"] = level
    raw["visible_monsters"], raw["detected_monsters"] = [], []
    for cell in raw["grid_map"].get("cells", []):
        cell.pop("m", None)
    return raw


def with_stair(snapshot, position):
    grid = snapshot.grids[position]
    grids = dict(snapshot.grids)
    grids[position] = replace(grid, has_down_stairs=True, terrain_id=DOWN_STAIR_TERRAIN)
    return replace(snapshot, grids=grids, turn=snapshot.turn + 10)


class FloorAboveTheGuardianTest(castle.CastleSummonerLootRecordedTest):
    # The harness only: the 48F summoner pins run in their own module.
    test_no_pack_to_dig_for_keeps_the_recorded_destruction = None
    test_a_valuable_drop_asks_the_pocket_first = None
    test_no_valuable_drop_keeps_the_destruction = None

    def arrive(self, level, *, angband=True):
        boards = self.boards
        if not angband:
            self.boards = copy.deepcopy(boards)
            for raw in self.boards:
                raw["progress"]["angband_recall_unlocked"] = False
        policy, _ = self.drive(quiet(self.boards[-1], level))
        board = policy.with_known_skill_exp(parse_snapshot(quiet(self.boards[-1], level),
                                                           self.monrace))
        self.assertTrue(policy._guardian_floor_blocked(board, CASTLE, GUARDIAN_FLOOR))
        return policy, board

    def test_64f_is_explored_not_left(self):
        policy, board = self.arrive(64)
        self.assertFalse(policy._guardian_descent_blocked(board))
        self.assertFalse(policy._should_start_town_return(board))
        reasons = []
        for step in range(1, 4):
            policy.choose_key(replace(board, turn=board.turn + 10 * step, messages=[]))
            reasons.append(policy.last_reason)
        self.assertFalse([r for r in reasons if r.startswith("return:")], reasons)
        self.assertNotEqual(policy._last_return_trigger, "guardian-kit-insufficient")

    def test_the_stair_onto_65f_is_not_taken(self):
        policy, board = self.arrive(64)
        here = board.player.position
        stair = with_stair(board, here)
        self.assertFalse(policy._is_descent_target(stair, stair.grids[here]))
        self.assertNotEqual(policy.choose_key(stair), ">")

    def test_the_last_resort_stair_underfoot_is_no_way_onto_65f(self):
        """COMPONENT PIN: ``_down_stairs_underfoot_key`` (owner 11-07 「足元の下り階段を最後の
        逃げ道に入れる。」) asked directly on a blind board (DECLARED CONSTRUCTED: blind); the
        public path reaches it only after the ladder's other means."""
        for level, expected in ((64, None), (63, ">")):
            with self.subTest(level=level):
                policy, board = self.arrive(level)
                here = board.player.position
                stair = with_stair(board, here)
                stair = replace(stair, player=replace(stair.player, blind=True))
                self.assertEqual(policy._down_stairs_underfoot_key(stair, "test"), expected)

    def test_a_remembered_stair_onto_65f_is_no_target(self):
        policy, board = self.arrive(64)
        far = next(position for position, grid in sorted(board.grids.items())
                   if grid.known and grid.passable
                   and position.distance_to(board.player.position) > 5)
        policy.choose_key(with_stair(board, far))
        self.assertIn(far, policy._remembered_downstairs)
        unseen = replace(board, grids={p: g for p, g in board.grids.items() if p != far},
                         turn=board.turn + 20)
        self.assertEqual(policy._usable_downstairs(unseen), set())
        policy.choose_key(unseen)
        self.assertNotIn(policy.last_reason, {"seek-downstairs", "approach-descent", "descend"})

    def test_from_63f_the_stair_onto_64f_is_a_target(self):
        policy, board = self.arrive(63)
        here = board.player.position
        stair = with_stair(board, here)
        self.assertTrue(policy._is_descent_target(stair, stair.grids[here]))

    def test_dives_from_64f_are_no_lack_of_depth_progress(self):
        """The Castle as the restored alternate (alternate-dungeon.json shape; the safe-fallback
        reason, which has no lease of its own),
        Angband's recall locked, so the Castle is the judged target: five dives from its 64F
        landing with the descent refused do not count as dives without depth progress (they
        did, and the valve would switch away as soon as the alternate ended)."""
        record = self.root / "alternate-dungeon.json"
        record.write_text(json.dumps({"turn": 0, "conquered": [2, 3, 4], "state": {
            "_alternate_dungeon": CASTLE, "_alternate_dungeon_reason": "safe_fallback",
            "_last_overextended_depth": 70, "_target_empty_dives": 0,
            "_guardian_bounce_dives": 0, "_no_depth_progress_dives": 0}}), encoding="utf-8")

        def wired(directory, monrace):
            policy = make_policy(directory, monrace)
            policy._alternate_dungeon_record_path = record  # as cli.py wires it
            return policy

        make_policy = castle._policy
        with mock.patch.object(castle, "_policy", wired):
            policy, board = self.arrive(64, angband=False)
        self.assertEqual(policy._alternate_dungeon, CASTLE)
        town = replace(board, floor_key=(0, 0, 0), town_flag=True, recall_dungeon_id=CASTLE,
                       recall_depth=64, dungeon_recall_depths={CASTLE: 64})
        dungeon = replace(board, recall_dungeon_id=CASTLE, recall_depth=64,
                          dungeon_recall_depths={CASTLE: 64})
        turn = board.turn
        for _ in range(5):
            turn += 100
            policy._observe(replace(town, turn=turn))
            self.assertEqual(policy._target_dungeon_id, CASTLE)
            turn += 100
            policy._observe(replace(dungeon, turn=turn))
        policy._observe(replace(town, turn=turn + 100))
        self.assertEqual(policy._no_depth_progress_dives, 0)


if __name__ == "__main__":
    unittest.main()
