"""n1-c life-116 (2026-11-03 11:57): a sensed worthless ring offered for sale.

The Magic shop sale tagged the unaware 鋼鉄の指輪 {無価値} @0 and answered
the sale menu with 0; the game's menu (store_will_buy: calc_price() > 0)
listed d-l without it, so the input was unrecognised and the bot stopped as
stuck-prompt:shop:one-shot-sell.  calc_price (item-entity.cpp) values a
sensed unknown item 0 when it is broken or cursed, which the feeling
"worthless" (pseudo_value_check_heavy: a cursed or broken ego) says it is;
the bot's projection valued the unaware ring by its flavour guess.

Recorded: the one-shot sale's board and the menu the game drew
(tests/extract_worthless_sale_fixture.py).  DECLARED WALL: the decision is
not replayed through choose_key: the visit's town-arrival replay diverges at
journal row 12 (the restored policy buys three Word of Recall, the live one
two) before the sale; the sale gate is pinned on the recorded page instead.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import re
import unittest
from pathlib import Path

from hengbot.model import STORE_MAGIC, parse_snapshot
from hengbot.policy import HengbotPolicy
from town_work_corpus import monraces


FIXTURE = Path(__file__).with_name("fixtures") / "worthless-sale-20261103.json.gz"


class WorthlessSaleRecordedTest(unittest.TestCase):
    def test_sensed_worthless_ring_is_not_offered_to_the_shop(self):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            case = json.load(stream)
        self.assertEqual((case["decision"]["key"], case["decision"]["reason"]),
                         ("d0y\x1b", "shop:one-shot-sell"))
        races = monraces()
        board = parse_snapshot(copy.deepcopy(case["board"]), races)
        self.assertEqual(board.store.store_type, STORE_MAGIC)
        ring = next(item for item in board.inventory if item.inscription == "@0")
        self.assertEqual((ring.aware, ring.known, ring.pseudo_feeling),
                         (False, False, "worthless"))
        # The game's sale menu: the letters it offered.
        offered = {match.group(1) for line in case["sale_menu"][1:]
                   if (match := re.match(r"\s*([a-w])\) ", line))}
        self.assertNotIn(ring.slot, offered)
        policy = HengbotPolicy()
        policy._monrace_knowledge = races
        self.assertFalse(policy._store_accepts_sale(STORE_MAGIC, ring))
        # Every carried item the menu offered is still accepted.
        for item in board.inventory:
            if item.slot in offered:
                self.assertTrue(policy._store_accepts_sale(STORE_MAGIC, item), item.name)


if __name__ == "__main__":
    unittest.main()
