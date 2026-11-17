"""n1-a life-530 2026-11-18 01:28:03, town:blocked:stage-deadline:sell (bot c2c293b34).

The Lv45 warrior's Home was full, and the full-Home relief (owner 2026-11-17
「自宅は明確に無駄な採掘道具や矢を売却すれば空きを作れる」) took the Dwarven Shovel of Digging
it judged a surplus digger (``item_fate.clearly_useless``) out to sell at the Weaponsmith
(row 5).  At the store the sale tagged it ``@1`` (row 9), which renamed it
``{+掘|酸}`` -> ``{+掘|酸, @1}``.  ``item_fate.relief_useless`` compared that new name with
the name the relief had recorded, answered no, and the standing digger retention kept the
shovel again: the store sale was refused as ``sale-retains-digging-tool`` and the bot left
and re-entered the Weaponsmith (``shop:retain-standing-digging-tool``) until the sell
stage's deadline.

The relief tracks its sale by ``_sale_item_identity`` (the name without its trailing
inscription), and ``relief_useless`` now matches the ware the same way.

Recorded: the incident capture's town-arrival checkpoint and its first 11 journal rows
(tests/extract_n1a_530_sell_deadline_1118_fixture.py).  Rows 0-9 are decided through the
public choose_key and compared with the record; row 10 is the tagged shovel's store board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import item_fate
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-sell-deadline-1118"
TAGGED_ROW = 10
STORE_WEAPONSMITH = 2
TVAL_DIGGING, SV_SHOVEL = 20, 3


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1a530SellDeadlineRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        for recorded, supply in steps[:TAGGED_ROW]:
            key = policy.choose_key(supply())
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])
        cls.board = steps[TAGGED_ROW][1]()
        cls.checkpoint = checkpoint_bytes(policy)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        [self.shovel] = [item for item in self.board.inventory
                         if (item.tval, item.sval) == (TVAL_DIGGING, SV_SHOVEL)]

    def test_the_relief_took_the_surplus_shovel_and_the_sale_tagged_it(self):
        policy, board = self.policy, self.board
        self.assertEqual(self.journal[5]["reason"], "home-errand:atomic-withdraw:full-home-sale")
        self.assertEqual(self.journal[9]["reason"], "shop:in-store-inscribe")
        self.assertEqual(board.store.store_type, STORE_WEAPONSMITH)
        relief = policy._home_full_relief
        self.assertEqual(relief["mode"], "sale")
        recorded = relief["sale"][0]
        self.assertEqual(relief["useless"], recorded)
        # The tag renamed the ware the relief recorded.
        self.assertNotEqual(policy._item_signature(self.shovel), recorded)
        self.assertTrue(policy._item_has_sale_tag(self.shovel, "1"))
        self.assertEqual(policy._sale_item_identity(self.shovel),
                         policy._sale_signature_identity(recorded))

    def test_the_tagged_shovel_is_sold_not_retained(self):
        policy, board = self.policy, self.board
        self.assertTrue(item_fate.relief_useless(policy, self.shovel))
        self.assertFalse(policy._sale_retains_digging_tool(board, self.shovel))

        key = policy.choose_key(board)

        # Recorded: "\x1b" shop:in-store-done, the sale refused as sale-retains-digging-tool,
        # then shop:retain-standing-digging-tool on every re-entry until the deadline.
        self.assertEqual(self.journal[TAGGED_ROW]["reason"], "shop:in-store-done")
        self.assertEqual((key, policy.last_reason), ("d1y", "shop:in-store-sell"))


if __name__ == "__main__":
    unittest.main()
