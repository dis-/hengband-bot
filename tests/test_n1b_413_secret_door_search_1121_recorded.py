"""n1-b life-413 2026-11-21 19:02 (Angband 12F): the walled-off dig wielded the digger at once.

Recorded: the armed board of the stall (tests/fixtures/n1b-413-rearm-digger-loop-1121, turn
674796, bot main db36f1744).  The player stood at (46,30), the dead end of a corridor two walls
east of a lit room ((46,28)-(46,29) granite, the room's floor from x 27 west).  The walled-off
ladder (retreat_enclosure, the hunt of random quest 43) went straight to its dig opener: the dig
route's first wall (46,29), and the digger's wield ('ta', stuck:walled-off-wield-digger).  No
search of that wall, no door detection.

Owner (verbatim) 2026-11-08 「閉じた区画では感知手段を使う・無ければ扉になりうる壁沿いも探す（諦めない）」
and 2026-11-21 「どうみても隠し扉なのに罠破壊を試みない理由は？隠し扉って分からん？」.  The game
(C:/hengband/src): a secret door is a closed door under a granite mimic (Grid::is_hidden_door);
detect_doors discloses it; do_cmd_search ('s') finds a hidden door beside the player with the
search skill's chance (player-move.cpp search); a trap beam discloses (KILL_TRAP) or destroys
(KILL_DOOR) a hidden door on its line (effect-feature.cpp).  Pinned: before the digger is wielded a
carried Disarming or Trap/Door Destruction device is aimed at the wall the dig would open, once,
and that wall is searched SEARCH_LIMIT rounds from beside it; then, nothing found, the dig goes on.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot import retreat_enclosure
from hengbot.model import SV_WAND_TRAP_DOOR_DEST, TVAL_WAND, Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import SEARCH_KEY, SEARCH_LIMIT
from support.q25_house import RACES

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-rearm-digger-loop-1121" / "boards.json.xz"
DEAD_END, WALL = Position(46, 30), Position(46, 29)
# DECLARED CONSTRUCTED: the retreat vetoes the capture does not record, around the corridor's dead
# end, so that the walled-off ground lies past the room's wall as the recorded dig read it.
VETOES = {Position(45, 29), Position(45, 30), Position(45, 31), Position(46, 31), Position(47, 29),
          Position(47, 31)}


class N1b413SecretDoorSearchRecordedTest(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(lzma.decompress(FIXTURE.read_bytes()))[0]
        self.armed = parse_snapshot(self.raw, RACES)
        self.policy = HengbotPolicy()
        self.policy._monrace_knowledge = RACES
        self.policy._build_grid_index(self.armed)
        self.policy._engagement_avoid_cells = set(VETOES)
        self.policy._engagement_owned_avoid_cells = set(VETOES)
        self.walled = retreat_enclosure.walled_off(self.policy, self.armed)

    def test_the_recorded_dead_end(self):
        self.assertEqual(self.armed.player.position, DEAD_END)
        self.assertFalse(self.armed.grid_at(WALL).passable)
        self.assertTrue(self.armed.grid_at(Position(46, 27)).passable)   # the room
        self.assertIsNotNone(self.walled)
        self.assertEqual(retreat_enclosure._dig_route(self.policy, self.armed, self.walled), WALL)

    def test_the_wall_is_searched_before_the_digger_is_wielded(self):
        keys = []
        for _ in range(SEARCH_LIMIT + 1):
            keys.append((retreat_enclosure._dig_key(self.policy, self.armed, self.walled),
                         self.policy.last_reason))
        self.assertEqual(keys[:SEARCH_LIMIT], [(SEARCH_KEY, "search")] * SEARCH_LIMIT)
        self.assertEqual(keys[SEARCH_LIMIT], ("ta", retreat_enclosure.DIG_WIELD_REASON))

    def test_a_carried_trap_door_destruction_wand_is_aimed_first_once(self):
        raw = copy.deepcopy(self.raw)
        # DECLARED CONSTRUCTED: a wand of Trap/Door Destruction in the pack (the recorded pack
        # holds no door means).
        raw["inventory"].append({
            "ac": 0, "aware": True, "charges": 5, "charging": False, "count": 1,
            "damage_dice": {"num": 1, "sides": 1}, "fully_known": True, "inscription": "",
            "is_artifact": False, "is_bounty": False, "is_broken": False, "is_cursed": False,
            "is_ego": False, "is_equipment": False, "known": True, "known_flags": [],
            "name": "trap-door-destruction wand (5)", "pval": 5, "slot": "w",
            "sval": SV_WAND_TRAP_DOOR_DEST, "to_a": 0, "to_d": 0, "to_h": 0, "tval": TVAL_WAND,
            "weight": 10})
        board = parse_snapshot(raw, RACES)
        key = retreat_enclosure._dig_key(self.policy, board, self.walled)
        self.assertTrue(key.startswith("a") and key.endswith("4"), key)   # aimed west at the wall
        self.assertEqual(self.policy.last_reason, "stuck:walled-off-door-beam")
        self.assertEqual((retreat_enclosure._dig_key(self.policy, board, self.walled),
                          self.policy.last_reason), (SEARCH_KEY, "search"))


if __name__ == "__main__":
    unittest.main()
