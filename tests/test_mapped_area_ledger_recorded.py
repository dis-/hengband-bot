"""n1-c Magic-Eater, Angband 4F (life-080): the magic-mapped area survives a
bot restart on the same floor (#47, owner 2026-11-01 answer 10
「階の記録に残す」: the exploration ledger keeps each mapping's position and
radius).

Recorded (tests/fixtures/mapped-rooms-1101.json.gz, see
tests/extract_mapped_rooms_1101.py): the first bot session cast map-area five
times on 4F (turns 549598-558083); the bot restarted (05:01:40) and the second
session, without those casts, walked the mapped dead end (3,94)->(1,94) at
turn 560863, searched it 8 times and broke out again; its next cast was at
turn 563571.  Boards go through the public choose_key and the production
executor.

DECLARED CONSTRUCTED: the first session's five casts are seeded as settled
uses on its recorded board of turn 549703 (the boards of the later casts are
not kept); at turn 560863 the remembered downstairs is expired as the
recorded rows did (as test_mapped_rooms_1101_recorded).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
from pathlib import Path
import tempfile
import unittest

from hengbot import mapped_area, me_powers
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests import test_mapped_rooms_1101_recorded as rooms
from tests import test_me_mining_death_recorded as mining

RESTART_TURN = rooms.DEAD_END_TURN   # the second session's board


def _rooms(name):
    return getattr(rooms.MappedRoomsRecordedTest, name)


class MappedAreaLedgerRecordedTest(mining.harness.ProductionHarness):
    setUpClass = classmethod(_rooms("setUpClass").__func__)
    choose = _rooms("choose")
    post = _rooms("post")
    rows = _rooms("rows")
    explore = _rooms("explore")

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.ledger_path = Path(scratch.name) / "exploration-ledger.json"

    def session(self, turn, uses=(), raw=None):
        """A bot session primed on the recorded board, with its ledger file."""
        raw = copy.deepcopy(self.data["boards"][str(turn)]) if raw is None else raw
        policy = HengbotPolicy(dungeon_knowledge=dict(self.dungeons),
                               exploration_ledger_path=self.ledger_path)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        policy.prime(board)
        memory = me_powers.FloorMemory(board.floor_key, raw["turn"])
        memory.uses.extend(me_powers.Use(rooms.MAPPING, rooms.MAPPING, "new-floor", centre,
                                         raw["turn"] - 1) for centre in uses)
        policy._me_power_floor = memory
        return policy, raw, board

    def first_session(self):
        """The first session's casts, settled on its recorded board."""
        casts = [centre for turn, centre in self.casts if turn < RESTART_TURN]
        self.assertEqual(len(casts), 5)
        policy, raw, _ = self.session(rooms.START_ROOM_TURN, casts)
        key = self.choose(policy, raw)
        self.assertEqual(len(mapped_area.current(policy).discs), 5, key)
        return casts

    def restarted(self, raw=None):
        policy, raw, board = self.session(RESTART_TURN, raw=raw)
        for stair in list(policy._remembered_downstairs):
            policy._nav_ledger.expire("descend", stair)
        return policy, raw, board

    def test_restart_on_the_floor_keeps_the_mapped_area(self):
        # Recorded: the second session walked into the dead end.
        recorded = [(row["position"]["y"], row["position"]["x"], row["reason"])
                    for row in self.rows(RESTART_TURN, 560972)]
        self.assertEqual(recorded[:2], [(3, 94, "explore"), (2, 94, "explore")])
        casts = self.first_session()
        policy, raw, board = self.restarted()
        self.assertEqual(policy._me_power_floor.uses, [])   # the session's own memory is new
        key, step = self.explore(policy, raw, board)
        self.assertNotIn(step, rooms.DEAD_END)
        game, _ = self.post(policy, raw, key, [])
        self.assertEqual(game.accepted, [key])
        area = mapped_area.current(policy)
        self.assertEqual(sorted(area.discs), sorted((c, me_powers.DETECT_RAD) for c in casts))
        self.assertTrue(rooms.DEAD_END <= area.cells)
        # The ledger file holds each cast's position and radius.
        stored = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(stored["mapped_areas"]),
                         sorted([c.y, c.x, me_powers.DETECT_RAD] for c in casts))

    def test_a_new_floor_forgets_the_mapped_area(self):
        self.first_session()
        other = copy.deepcopy(self.data["boards"][str(RESTART_TURN)])
        other["floor"]["level"] += 1   # DECLARED CONSTRUCTED: 5F, the same layout
        with self.subTest("restart onto another floor"):
            policy, raw, board = self.session(RESTART_TURN, raw=copy.deepcopy(other))
            self.assertEqual(board.floor_key[1], 5)
            self.assertEqual(policy._exploration_ledger.mapped_areas, set())
            self.choose(policy, raw)
            self.assertIsNone(mapped_area.current(policy))
        with self.subTest("the restarted session leaves the floor"):
            self.first_session()
            policy, raw, _ = self.restarted()
            self.choose(policy, raw)
            self.assertIsNotNone(mapped_area.current(policy))
            other["turn"] = raw["turn"] + 100
            self.choose(policy, other)
            self.assertEqual(policy._exploration_ledger.mapped_areas, set())
            self.assertIsNone(mapped_area.current(policy))

    def test_without_a_ledger_file_the_restart_walks_as_recorded(self):
        policy, raw, board = self.restarted()
        key, step = self.explore(policy, raw, board)
        self.assertIsNone(mapped_area.current(policy))
        self.assertEqual((key, step), ("8", (2, 94)))


if __name__ == "__main__":
    unittest.main()
