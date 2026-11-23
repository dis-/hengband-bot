"""No search command on Angband 99F/100F: a door detection where one is due, else the next step.

Owner 2026-11-23 (verbatim): 「99F 100Fはサーチ禁止。必要なら感知すること。」  n1-b life-416
(Magic-Eater Lv50, Angband 99F, a small floor 22x198, quest 0) sent the search key ``s`` on 1,202
of its last 3,000 decisions (reason ``search``): the corridor dead-end rung of ladder_idle searched
each cell of a corridor before stepping on.  The fixture is 53 boards of that floor, game turns
4295930-4296069 (n1-b life-416 jsonlog/snapshots/snapshots-current.jsonl.gz), where the live bot
searched at (6,161), (5,162), (4,161), (4,162) and (3,163).

DECLARED RECONSTRUCTED: the Magic-Eater's device lists (the snapshot files carry none): the
absorbed Staff of Teleportation, 22 charges at 95% (the live bot held one: without it the 99F
battle's ``teleports_out`` reads Word of Recall on every board).

The live process took the finale's expedition mark from the floor (finale_prep
``expedition_evident``), so the 99F battle holds these boards and, Oberon shown nowhere, searches
the floor with its lap (angband_finale_battle ``_lost_key``): no ``s`` there (``test_battle_*``).
The ladder's own dead-end search (ladder_idle) answers a 99F/100F floor the battle does not hold;
DECLARED CONSTRUCTED for those runs: the battle holds no board (angband_finale_battle ``applies``
patched False, as for a character that is not a Magic-Eater), so the ordinary ladder decides.

- No door detection held (the pack has none): no ``s`` on any board; the walk goes on.
- With five Scrolls of Door/Stair Location in the pack too (reconstructed): one is read instead
  of the search, once for the area (the board after it covers the corridor), and still no ``s``.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import angband_finale_battle, me_capability, search_ban
from hengbot.me_absorbed_substitutes import TELEPORTATION
from hengbot.model import SV_SCROLL_DETECT_DOOR, TVAL_SCROLL, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "no-search-99f-n1b-416-1123.jsonl.gz"
# DECLARED RECONSTRUCTED: five Scrolls of Door/Stair Location in the pack (the live pack had none).
DOOR_SCROLL = {
    "ac": 0, "aware": True, "charges": 0, "charging": False, "count": 5,
    "damage_dice": {"num": 0, "sides": 0}, "fully_known": True, "inscription": "",
    "is_artifact": False, "is_bounty": False, "is_broken": False, "is_cursed": False,
    "is_ego": False, "is_equipment": False, "known": True, "known_flags": [],
    "name": "ドア/階段感知の巻物", "pval": 0, "slot": "r",
    "sval": SV_SCROLL_DETECT_DOOR, "to_a": 0, "to_d": 0, "to_h": 0, "tval": TVAL_SCROLL, "weight": 5}


def _boards():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


class NoSearch99fRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.boards = _boards()
        cls.battle = cls.drive(None)
        with mock.patch.object(angband_finale_battle, "applies", return_value=False):
            cls.plain = cls.drive(None)
            cls.detecting = cls.drive(DOOR_SCROLL)

    @classmethod
    def drive(cls, carried):
        directory = TemporaryDirectory()
        try:
            policy = _policy(Path(directory.name), cls.monrace)
            first = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(cls.boards[0]), cls.monrace))
            policy.prime(first)
            policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
            decided = []
            for raw in cls.boards:
                raw = copy.deepcopy(raw)
                if carried is not None:
                    raw["inventory"].append(copy.deepcopy(carried))
                board = policy.with_known_skill_exp(parse_snapshot(raw, cls.monrace))
                policy._me_device_lists = {"staff": (board.turn, ({
                    "name": me_capability.names(*TELEPORTATION)[0], "current": 22,
                    "max": 22, "fail": 5, "success": 95},))}
                key = policy.choose_key(board)
                decided.append((board.turn, board.player.position, key, policy.last_reason))
                if key:
                    policy.confirm_key_posted(key)
            return decided
        finally:
            directory.cleanup()

    def test_the_floor_is_banned(self):
        board = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        self.assertTrue(search_ban.banned(board))
        for level, expected in ((98, False), (100, True)):
            raw = copy.deepcopy(self.boards[0])
            raw["floor"]["level"] = level
            self.assertEqual(search_ban.banned(parse_snapshot(raw, self.monrace)), expected)
        raw = copy.deepcopy(self.boards[0])
        raw["floor"]["dungeon_id"] = 2
        self.assertFalse(search_ban.banned(parse_snapshot(raw, self.monrace)))

    def test_battle_sends_no_search(self):
        sent = [row for row in self.battle if row[2] == "s" or row[3] == "search"]
        self.assertEqual(sent, [], self.battle)

    def test_no_search_without_a_detection(self):
        sent = [row for row in self.plain if row[2] == "s"]
        self.assertEqual(sent, [], self.plain)
        self.assertTrue(any(row[3] == "explore" for row in self.plain), self.plain)

    def test_detection_instead_of_the_search(self):
        sent = [row for row in self.detecting if row[2] == "s"]
        self.assertEqual(sent, [], self.detecting)
        detections = [row for row in self.detecting if row[3] == search_ban.DETECT_REASON]
        self.assertEqual(len(detections), 1, self.detecting)
        self.assertTrue(detections[0][2].startswith("r"), detections)


if __name__ == "__main__":
    unittest.main()
