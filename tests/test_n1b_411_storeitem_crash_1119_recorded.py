"""A shelf ware is no carried food device (n1-b life-411, 2026-11-19).

n1-b life-411 (zombie Magic-Eater Lv50) crashed at 22:14:22 in the Magic shop with
``AttributeError: 'StoreItem' object has no attribute 'is_wand_staff'``.  Its staple (謎の魔法棒,
slot h) was drained to 0 charges, so item_use_route's ``mana-food`` row asked
magic_eater_devices.drained_staple_food of every shelf wand and staff the shop selector's
purchase rungs read (policy_shop._matching_live_purchase_rungs -> item_use_route.surplus); that
rule reads the carried device's ``is_wand_staff`` and ``slot``, which a ``StoreItem`` lacks.  The
first ware no absorption row claimed (g: 岩石溶解の魔法棒 (12回分), the Stone to Mud power at its
cap) reached it.

The drained-staple rule keeps carried devices (owner 2026-11-12 「食べられる代替の食料も持って
いる」) and buys nothing; with a staple carried only the staple is food to buy
(magic_eater_devices.is_mana_food_ware).  A shelf ware is therefore not covered by it.

Recorded: the town-arrival checkpoint (tests/fixtures/n1b-411-storeitem-crash-1119, rows 0-36
decided through the public choose_key and compared with the journal) and the capture's last
board, the Magic shop's screen the crash left out of the journal.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import item_use_route, magic_eater_devices
from hengbot.model import STORE_MAGIC, TVAL_WAND, StoreItem, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-storeitem-crash-1119"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class StoreItemCrashRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        for recorded, supply in steps:
            key = policy.choose_key(supply())
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])
        cls.policy = policy
        cls.board = parse_snapshot(
            json.loads(lzma.decompress((FIXTURE / "crash-board.json.xz").read_bytes())),
            policy._monrace_knowledge)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_recorded_rows_replay(self):
        self.assertEqual(len(self.replayed), 37)
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)

    def test_the_magic_shop_decision_no_longer_crashes(self):
        board = self.board
        self.assertEqual(board.store.store_type, STORE_MAGIC)
        self.assertEqual(magic_eater_devices.staple_charges(board), 0)
        # Before: AttributeError: 'StoreItem' object has no attribute 'is_wand_staff'.
        key = self.policy.choose_key(board)
        self.assertEqual((key, self.policy.last_reason), ("{j@4\r", "shop:in-store-inscribe"))

    def test_the_stone_to_mud_ware_is_no_drained_staple_food(self):
        board = self.board
        ware = next(item for item in board.store.items if item.letter == "g")
        self.assertEqual((ware.tval, ware.sval, ware.charges), (TVAL_WAND, 6, 12))
        self.assertFalse(magic_eater_devices.drained_staple_food(self.policy, board, ware))
        self.assertEqual(item_use_route.uses(self.policy, board, ware), ())
        self.assertTrue(item_use_route.surplus(self.policy, board, ware))

    def test_every_shelf_device_answers(self):
        uses = {item.letter: item_use_route.uses(self.policy, self.board, item)
                for item in self.board.store.items if item.tval in item_use_route.DEVICE_TVALS}
        self.assertEqual(uses, {
            "g": (), "h": ("magic_eater:absorb",), "i": (), "j": (),
            "k": ("magic_eater:absorb",), "l": ("magic_eater:absorb",),
            "m": ("magic_eater:absorb",), "n": ("magic_eater:absorb",),
            "o": ("magic_eater:absorb",), "p": (), "q": (),
        })

    def test_every_route_condition_reads_a_shelf_ware(self):
        # DECLARED CONSTRUCTED: one charged shelf ware of every row's kind (a tval-wide row as
        # sval 1) on the recorded board: no WHEN condition reads a field a StoreItem lacks.
        for route in item_use_route.ROUTES:
            sval = 1 if route.sval is item_use_route.ANY else route.sval
            ware = StoreItem(letter="a", name="ware", count=1, tval=route.tval, sval=sval,
                             price=100, charges=5)
            with self.subTest(route=route):
                item_use_route.uses(self.policy, self.board, ware)


if __name__ == "__main__":
    unittest.main()
