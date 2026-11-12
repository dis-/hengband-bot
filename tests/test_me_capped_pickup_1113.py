"""The Magic-Eater leaves a floor device whose absorbed power is at its cap (owner 2026-11-13).

Owner (verbatim): 「魔道具術師　取り込み99回になった魔法道具はそれ以降拾わない」, and on Stone to Mud
「内部でカウントされるようなら取り込み続けても良い」.  mind-magic-eater.cpp caps a power's count at
99 (me_capped_pickup), so nothing past 99 is counted.

Declared constructed board: no recorded board shows a known device of a capped power on the
floor while its list was displayed (the list is read from the screen, not the board).  The boards
are n1-c life-205's own (tests/fixtures/n1c-205-stuck-recall-1113.jsonl.gz, dungeon 12 49F,
decisions 5066-5070, a Lv38 zombie Magic-Eater whose staple wand holds 71 charges), whose
seek-loot walked to the pile at (18,14); the pile is changed from its ring (tval 45) to one
known Wand of Stone to Mud (tval 65, sval 6).  The displayed wand list holds the row the same
life showed for Stone to Mud on 2026-11-13 01:40 (town-arrival checkpoint, turn 2358120):
current 99, max 99; it is dated before the window, as a list read earlier in the life is.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import me_capped_pickup
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-205-stuck-recall-1113.jsonl.gz"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")
PILE = Position(18, 14)
STONE_TO_MUD_ROW = {"name": "岩石溶解", "fail": 6, "success": 94, "current": 99, "max": 99}
WINDOW = 4


def _with_wand_pile(board):
    board = copy.deepcopy(board)
    grid_map = board["grid_map"]
    for cell in grid_map["cells"]:
        if (cell.get("y"), cell.get("x")) == (PILE.y, PILE.x) and "o" in cell:
            cell["t"] = [65]
    for name, entry in (("found_items", [PILE.y, PILE.x, 1, 65]),
                        ("found_item_ids", [PILE.y, PILE.x, {"sval": 6}]),
                        ("found_item_names", [PILE.y, PILE.x, "岩石溶解の魔法棒 (12回分)"])):
        grid_map[name] = [entry if (row[0], row[1]) == (PILE.y, PILE.x) else row
                          for row in grid_map[name]]
    return board


def _drained_staple(board):
    board = copy.deepcopy(board)
    for item in board["inventory"]:
        if (item.get("tval"), item.get("sval")) == (65, 24):
            item["charges"] = 0
            item["name"] = item["name"].replace("(71", "(0")
    return board


class MeCappedPickup1113Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.skill = next(row["board"] for row in rows if row["role"] == "skill-knowledge")
        cls.boards = [_with_wand_pile(row["board"]) for row in rows if row["role"] == "board"][:WINDOW]
        cls.monrace = load_monrace_knowledge(MONRACES)

    def replay(self, boards, maximum):
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        policy.consume_skill_knowledge(self.skill)
        policy._skill_exp_request_key = lambda snapshot: None
        policy._me_device_lists = {"wand": (boards[0]["turn"] - 1, (dict(STONE_TO_MUD_ROW, max=maximum,
                                                                          current=maximum),))}
        decided = []
        for board in boards:
            snapshot = parse_snapshot(board, self.monrace)
            key = policy.choose_key(snapshot)
            if key:
                policy.confirm_key_posted(key)
            decided.append((policy.last_reason, policy._loot_target))
        return policy, snapshot, decided

    def test_capped_wand_is_left(self):
        policy, snapshot, decided = self.replay(self.boards, 99)
        self.assertEqual(snapshot.found_item_ids[PILE], ({"sval": 6},))
        self.assertTrue(me_capped_pickup.capped_pile(policy, snapshot, PILE))
        self.assertNotIn(PILE, policy._known_loot)
        self.assertNotIn(PILE, [target for _reason, target in decided])

    def test_wand_below_the_cap_is_taken(self):
        policy, snapshot, decided = self.replay(self.boards, 98)
        self.assertFalse(me_capped_pickup.capped_pile(policy, snapshot, PILE))
        self.assertEqual(decided[0], ("seek-loot", PILE))

    def test_drained_staple_takes_it_as_food(self):
        boards = [_drained_staple(board) for board in self.boards]
        policy, snapshot, _decided = self.replay(boards, 99)
        self.assertFalse(me_capped_pickup.capped_pile(policy, snapshot, PILE))
        self.assertIn(PILE, policy._known_loot)


if __name__ == "__main__":
    unittest.main()
