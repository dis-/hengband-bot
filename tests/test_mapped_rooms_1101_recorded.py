"""n1-c Magic-Eater, Angband 4F (life-080): exploration after a magic mapping
(owner 2026-11-01 「周辺感知を取り込んだあとはマップを全マス捜索する必要はまったくない。
もう少し効率化できないだろうか」 -> 「部屋だけ見て回る」).

Boards and decision rows are recorded (tests/fixtures/mapped-rooms-1101.json.gz,
see tests/extract_mapped_rooms_1101.py) and go through the public choose_key
and the production executor.

Recorded: map-area at (6,127) (turn 549598), then 176 explore decisions swept
the lit start room and the rooms beside it tile by tile; at turn 560863 the
bot walked the mapped dead end (3,94)->(1,94), searched it 8 times and broke
out again (decisions 237-248 of the second session).

DECLARED CONSTRUCTED: the floor's map-area uses are seeded from the recorded
me-power rows (the second bot session had lost them at its restart, the game
still showed the mapped walls); at turn 560863 the remembered downstairs is
expired as the recorded rows did (approach-descent ended at decision 39 and
explore followed); the skill knowledge the live process held is given.
"""
import tests  # noqa: F401 -- isolate live runtime files
from recorded_junk_scope import install_past_destroyed_junk

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import mapped_area, me_powers
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import NEIGHBOR_OFFSETS
from tests import test_me_mining_death_recorded as mining

FIXTURE = Path(__file__).parent / "fixtures" / "mapped-rooms-1101.json.gz"
START_ROOM_TURN = 549703
DEAD_END_TURN = 560863
DESCENT_TURN = 561131
DEAD_END = {(1, 94), (2, 94)}
MAPPING = ("staff", me_powers.SV_STAFF_MAPPING)


def _harness(name):
    return getattr(mining.MagicEaterMiningDeathRecordedTest, name)


_undo_past_junk = None


def setUpModule():
    # Owner 2026-11-02: these boards carry junk the first safe decision destroys.
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


class MappedRoomsRecordedTest(mining.harness.ProductionHarness):
    choose = _harness("choose")
    post = _harness("post")

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        facts = dict(cls.data["dungeon"], flags=frozenset(cls.data["dungeon"]["flags"]))
        cls.dungeons = {facts["id"]: DungeonInfo(**facts)}
        cls.casts = [(row["turn"], Position(row["position"]["y"], row["position"]["x"]))
                     for row in cls.data["rows"] if row["reason"].endswith(":map-area")]

    def rows(self, first, last):
        return [row for row in self.data["rows"] if first <= row["turn"] <= last]

    def policy(self, turn, casts=None):
        """A primed policy on the recorded board, with the floor's earlier
        map-area uses (``casts`` overrides them)."""
        raw = copy.deepcopy(self.data["boards"][str(turn)])
        policy = HengbotPolicy(dungeon_knowledge=dict(self.dungeons))
        board = parse_snapshot(raw, policy._monrace_knowledge)
        policy.prime(board)
        memory = me_powers.FloorMemory(board.floor_key, raw["turn"])
        centres = [c for t, c in self.casts if t < turn] if casts is None else casts
        memory.uses.extend(me_powers.Use(MAPPING, MAPPING, "new-floor", centre, raw["turn"] - 1)
                           for centre in centres)
        policy._me_power_floor = memory
        return policy, raw, board

    def explore(self, policy, raw, board):
        key = self.choose(policy, raw)
        self.assertEqual(policy.last_reason, "explore", key)
        here = board.player.position
        step = next(Position(here.y + dy, here.x + dx) for dy, dx in NEIGHBOR_OFFSETS
                    if policy._direction_key(here, Position(here.y + dy, here.x + dx)) == key)
        return key, (step.y, step.x)

    @staticmethod
    def goal(policy, step):
        """The end of the committed explore path (the step itself when the
        path was one step long)."""
        path = policy._explore_path
        return (path[-1].y, path[-1].x) if path else step

    def test_mapped_dead_end_is_not_walked(self):
        recorded = [(row["position"]["y"], row["position"]["x"], row["reason"])
                    for row in self.rows(DEAD_END_TURN, 560972)]
        self.assertEqual(recorded[:3], [(3, 94, "explore"), (2, 94, "explore"),
                                        (1, 94, "search")])
        self.assertEqual(sum(reason == "search" for _, _, reason in recorded), 8)

        def at_dead_end(casts=None):
            policy, raw, board = self.policy(DEAD_END_TURN, casts)
            for stair in list(policy._remembered_downstairs):
                policy._nav_ledger.expire("descend", stair)
            return (policy, raw, board, *self.explore(policy, raw, board))

        policy, raw, board, key, step = at_dead_end()
        area = mapped_area.current(policy)
        self.assertTrue(DEAD_END <= area.cells)
        self.assertNotIn(step, DEAD_END)
        game, _ = self.post(policy, raw, key, [])
        self.assertEqual(game.accepted, [key])

        with self.subTest("no mapping on the floor: walked as before"):
            *_, key, step = at_dead_end(casts=[])
            self.assertIsNone(mapped_area.current(_[0]))
            self.assertEqual((key, step), ("2", (4, 94)))  # floor in the own light is not owed (37414d7d41)
        with self.subTest("only a mapping out of range: walked as before"):
            far = [Position(6, 127)]   # distance 34 from (3,94)
            *_, key, step = at_dead_end(casts=far)
            self.assertFalse(mapped_area.covers(_[0], (3, 94)))
            self.assertEqual((key, step), ("2", (4, 94)))  # floor in the own light is not owed (37414d7d41)

    def test_seen_mapped_room_is_not_swept_and_unseen_room_is_looked_into(self):
        # Recorded: the 176 explore decisions after the cast walked the lit
        # start room, which the board already showed, tile by tile.
        explore = [row for row in self.rows(549598, 551583) if row["reason"] == "explore"]
        self.assertGreaterEqual(len(explore), 170)
        policy, raw, board = self.policy(START_ROOM_TURN)
        known = policy._remembered_known_t
        start_room = {(y, x) for y in range(2, 8) for x in range(122, 131)}
        self.assertTrue(start_room <= known)
        key, step = self.explore(policy, raw, board)
        area = mapped_area.current(policy)
        goal = self.goal(policy, step)
        unseen_room = area.cells - known - area.corridor
        self.assertNotIn(goal, start_room)
        self.assertTrue(any((goal[0] + dy, goal[1] + dx) in unseen_room
                            for dy, dx in NEIGHBOR_OFFSETS), goal)
        game, _ = self.post(policy, raw, key, [])
        self.assertEqual(game.accepted, [key])

        with self.subTest("rooms and corridors read off the mapped walls"):
            self.assertTrue({(11, x) for x in range(98, 104)} <= area.corridor)  # dead end
            self.assertTrue({(6, 97), (6, 98), (6, 99)} <= area.corridor)    # the exit west
            self.assertIn((4, 110), unseen_room)                              # the dark room
        with self.subTest("no mapping on the floor: the seen room is swept as before"):
            policy, raw, board = self.policy(START_ROOM_TURN, casts=[])
            key, step = self.explore(policy, raw, board)
            self.assertIn(self.goal(policy, step), start_room)

    def test_descent_approach_reads_the_mapped_corridor(self):
        # The stair (29,40) is not reachable on known cells: the frontier
        # approach must still find the mapped corridor's frontiers.
        policy, raw, board = self.policy(DESCENT_TURN)
        stair = Position(29, 40)
        self.assertIn(stair, policy._remembered_downstairs)
        key = self.choose(policy, raw)
        self.assertEqual(policy.last_reason, "approach-descent", key)
        self.assertNotIn(stair, policy._nav_ledger.expired_targets("descend"))
        game, _ = self.post(policy, raw, key, [])
        self.assertEqual(game.accepted, [key])


if __name__ == "__main__":
    unittest.main()
