"""A full Home sells its clearly useless stock first (owner 2026-11-17).

Owner, verbatim: 「自宅は明確に無駄な採掘道具や矢を売却すれば空きを作れる」.  n1-a life-530 (warrior
Lv43, Heavy Crossbow) stood 2026-11-17 23:28 at a Home of 239/240: a dozen digging tools beside
the one it digs with, and some forty stacks of 99 plain crossbow bolts besides the enchanted
ones.  The full-Home relief (row 5) chose 7 Iron Spikes, then a Lance (row 35).

``item_fate.clearly_useless`` names that stock (``surplus-digger``: every tool but the best;
``surplus-ammo``: the worn launcher's rounds past the Home keep of 99, best kept;
``unused-ammo``: the junk class), the relief ranks it first (``relief_order``), and the ware
taken out stays sellable off the shelf (``relief_useless``): the standing digger retention no
longer keeps it at the store.

Recorded: n1-a life-530's town-arrival checkpoint (tests/fixtures/n1a-530-home-full-reject-1117);
rows 0-4 are decided through the public choose_key and compared with the record (row 2 also
shelves the 13 Stone to Mud wands past the five carried, tests/
test_warrior_stone_to_mud_carry_1118_recorded.py), the recorded key acknowledged.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import item_fate
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-home-full-reject-1117"
RELIEF_ROW = 5
FIVE_WANDS_ROW = 2
TVAL_SPIKE, TVAL_BOLT, TVAL_DIGGING = 77, 18, 20


def is_kept_digger(item):
    """The battle pick (+10,+6) (+7): the best digging bonus (7) of the best kind (sval 7)."""
    return (item.tval, item.sval, item.pval, item.to_h, item.to_d) == (TVAL_DIGGING, 7, 7, 10, 6)


def is_shovel(item):
    """The Dwarven Shovel (+8,+6) (+7) of Digging: second best, behind the battle pick."""
    return (item.tval, item.sval, item.pval, item.to_h, item.to_d) == (TVAL_DIGGING, 3, 7, 8, 6)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class HomeFullClearlyUselessRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        for recorded, supply in steps[:RELIEF_ROW]:
            key = policy.choose_key(supply())
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])
        cls.board = steps[RELIEF_ROW][1]()
        cls.checkpoint = checkpoint_bytes(policy)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            if row == FIVE_WANDS_ROW:
                self.assertEqual(decided, ("dndmdk13\rdg\x1b", recorded[1]), row)
                continue
            self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        self.key = self.policy.choose_key(self.board)
        self.relief = self.policy._home_full_relief

    def home(self, predicate):
        return [replace(item, slot=item_fate.HOME_STOCK_SLOT)
                for item in self.policy._home_knowledge_items if predicate(item)]

    def test_the_relief_takes_clearly_useless_stock_first(self):
        board = self.board
        self.assertEqual((board.store.store_type, board.store.stock_num, board.store.capacity),
                         (7, 240, 240))
        self.assertEqual(self.journal[RELIEF_ROW]["reason"], "home:full-queue-surplus-withdraw")
        self.assertEqual((self.key, self.policy.last_reason),
                         ("\x1b", "home:full-queue-surplus-withdraw"))
        # Before: the relief's sale was the 7 Iron Spikes (then a Lance at row 35).
        signature = self.relief["sale"][0]
        self.assertNotEqual(signature[1], TVAL_SPIKE)
        [bolts] = [item for item in self.policy._home_knowledge_items
                   if self.policy._item_signature(item) == signature]
        self.assertEqual((bolts.tval, bolts.to_h, bolts.to_d, bolts.count), (TVAL_BOLT, 3, 1, 27))
        self.assertEqual((self.relief["mode"], self.relief["useless"]), ("sale", signature))

    def test_every_digger_but_the_best_and_the_bolts_past_the_keep_are_useless(self):
        policy, board = self.policy, self.board
        verdict = lambda item: item_fate.clearly_useless(policy, board, item)
        diggers = self.home(lambda item: item.tval == TVAL_DIGGING)
        self.assertEqual([verdict(item) for item in diggers if is_kept_digger(item)], [None])
        self.assertEqual([verdict(item) for item in diggers if item.is_artifact], [None])
        others = [verdict(item) for item in diggers
                  if not is_kept_digger(item) and not item.is_artifact]
        self.assertEqual(others, ["surplus-digger"] * 9)

        bolts = self.home(lambda item: item.tval == TVAL_BOLT)
        useless = [item for item in bolts if verdict(item) == "surplus-ammo"]
        kept = sum(item.count for item in bolts if verdict(item) is None)
        self.assertGreaterEqual(kept, item_fate.HOME_AMMO_KEEP)
        self.assertGreaterEqual(sum(item.count for item in useless), 4000)
        self.assertTrue(all(item.to_h <= 3 for item in useless))

    def test_the_taken_digger_is_sold_not_retained_at_the_store(self):
        # DECLARED CONSTRUCTED: the take's board -- the recorded row-5 board with the shovel
        # the relief would take on the pack and the relief's sale bound to it.
        policy, board = self.policy, self.board
        [shovel] = [item for item in policy._home_knowledge_items if is_shovel(item)]
        taken = replace(shovel, slot="p")
        carried = replace(board, inventory=(*board.inventory, taken))
        signature = policy._item_signature(shovel)
        self.relief["sale"] = (signature, 2, 0)
        self.relief.pop("useless", None)
        self.assertTrue(policy._sale_retains_digging_tool(carried, taken))   # before
        self.relief["useless"] = signature
        self.assertTrue(item_fate.relief_useless(policy, carried, taken))
        self.assertFalse(policy._sale_retains_digging_tool(carried, taken))
        self.assertEqual(policy._retention_reservation(carried, taken), 0)

    def test_no_verdict_without_a_full_home_relief(self):
        policy, board = self.policy, self.board
        [shovel] = self.home(is_shovel)
        self.assertEqual(item_fate.clearly_useless(policy, board, shovel), "surplus-digger")
        policy._home_full_relief = None
        self.assertIsNone(item_fate.clearly_useless(policy, board, shovel))


if __name__ == "__main__":
    unittest.main()
