"""n1-b life-413, Angband 12F, RANDOM quest 43, 2026-11-21 19:02 and 20:11: the dig out of an open corridor.

Both stops ended with stuck:walled-off-wield-digger at (46,30), a corridor turn beside a lit room
(x 17-27), the corridor open north and east.  The 20:11 run was a fresh process on the 19:02 stop's
save: no retreat veto survives a restart, and in its 452 keys before the dig it struck nothing and
no monster came in view, yet it walked the 19:02 run's last laps key for key to the same 'ta'.
The digger's wield has two askers (retreat_enclosure ``_dig_key``): the vetoes' ladder
(``walled_off_key``: no veto, no ladder) and the quest search's cut-off floor
(quest_target_search ``loop_key`` -> ``open_toward_key``).  It was the second: the magic-mapped
room is remembered floor, its doors open onto corridors the map does not hold (map_area does not
memorize corridor floor), so no walk over known ground reached it and the opener dug west at
(46,29) toward it -- while the corridor the player stood in ran on east into ground the map did
not hold either: (46,33) onward is floor (walked in the replay below).  The explore did not take
that frontier (its written-off frontiers, kept across the restart in the floor's ledger).

Recorded (tests/extract_n1b_413_cut_off_opening_1121_fixture.py): the 20:11 capture's keys
replayed into a headless game loaded from the 19:02 capture's save; the last board (the replay
reached (46,30) as the run did) and the policy memory deciding those boards built.  The lap
(``loop_key``) is asked directly: the recorded explore answered nothing on that board (the rows
are the dig's; its written-off frontiers were in the floor's ledger, which the capture does not
hold).

Pinned: no veto is held; remembered floor that no known walk reaches but that unmapped ground
joins to the player's side is not cut off (a way may run through that ground), so the lap's
opener digs nothing toward the room and the search walks to the unexplored way toward it.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import hengbot.policy  # noqa: F401 -- loads the modules in their cycle-safe order
from hengbot import quest_target_search as search
from hengbot import retreat_enclosure
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-cut-off-opening-1121" / "pin.json.xz"
TURN = Position(46, 30)
ROOM = Position(46, 27)
ROOM_DOOR = Position(45, 21)   # the room's open door, beside the unmapped (44,21)
DIG_REASONS = {retreat_enclosure.DIG_REASON, retreat_enclosure.DIG_WIELD_REASON,
               retreat_enclosure.MELT_REASON, "search", "stuck:walled-off-door-beam"}


class N1b413CutOffOpeningRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        self.raw = copy.deepcopy(self.pin["board"])
        policy.prime(self.board(policy))
        for name, cells in self.pin["terrain"].items():
            getattr(policy, f"_remembered_{name}_t").update(tuple(cell) for cell in cells)
        policy._remembered_upstairs.update(Position(*cell) for cell in self.pin["upstairs"])
        for y, x, count in self.pin["visits"]:
            policy._visit_counts[Position(y, x)] = count
        policy.consume_skill_knowledge({
            "player": {"level": self.raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        policy._build_grid_index(self.board(policy))   # the remembered terrain in the routes
        self.policy = policy

    def board(self, policy):
        return parse_snapshot(copy.deepcopy(self.raw), policy._monrace_knowledge)

    def test_the_recorded_board(self):
        board = self.board(self.policy)
        self.assertEqual(board.player.position, TURN)
        self.assertEqual(self.pin["avoid"], [])
        self.assertEqual(self.pin["hostiles_seen"], 0)
        self.assertTrue(search.searching(self.policy, board))
        self.assertIsNone(retreat_enclosure.walled_off(self.policy, board))   # no veto, no ladder
        routes = search._routes(self.policy, board)
        self.assertNotIn(ROOM, routes)                                   # no known walk reaches it
        self.assertIn(Position(46, 32), routes)                          # the corridor east
        self.assertTrue(self.policy._borders_unexplored(board, Position(46, 32)))
        self.assertTrue(self.policy._borders_unexplored(board, ROOM_DOOR))   # the room's door

    def test_ground_beside_unmapped_ground_is_not_cut_off(self):
        board = self.board(self.policy)
        cut_off = search._cut_off_floor(self.policy, board, search._routes(self.policy, board))
        self.assertNotIn(ROOM, cut_off)
        self.assertNotIn(ROOM_DOOR, cut_off)

    def test_the_lap_digs_nothing_toward_the_room(self):
        """The quest search's lap (loop_key), the asker the recorded rows were the dig of."""
        policy = self.policy
        keys = []
        for _ in range(3):
            keys.append((search.loop_key(policy, self.board(policy)), policy.last_reason))
        self.assertFalse([pair for pair in keys if pair[1] in DIG_REASONS], keys)
        self.assertIsNone(retreat_enclosure.trace(policy))
        # The unexplored way that joins the room to the player's side is walked instead.
        self.assertEqual(keys[0][1], search.OPENING_REASON)
        self.assertIn(keys[0][0], "12346789")

if __name__ == "__main__":
    unittest.main()
