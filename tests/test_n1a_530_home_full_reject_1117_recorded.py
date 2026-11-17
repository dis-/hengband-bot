"""n1-a life-530 2026-11-17 23:28:55, town:blocked:survival:inventory_weight_ready (bot 47c9c23a5).

The Lv43 warrior came home 194.0 lb over a 180.0 lb limit.  Its first weight-overload
deposit (row 2, ``dndmdg``) met a Home at 239/240: the first item took the last slot,
the game refused the (Chaos) Great Axe (23.0 lb) as "no room", and row 3 rejected the
axe's identity for the rest of the town stay (``_home_rejected_deposits``).  The
full-Home relief then took items out to sell, and from row 35 on every Home page read
239/240, but the axe stayed held as ``home-rejected-deposit``.  The second deposit
(row 67) shed what was left: the 36 crossbow bolts and the Disarming rod (12.3 lb),
leaving 181.7 lb; two scroll purchases made it 183.7 lb and the visit stopped.

A deposit refused only because the Home was full is now released when a later Home
page shows a free slot (``_release_home_full_rejections``), unless a full-Home relief
still owns its retry: on row 67 the axe alone clears the excess and is deposited.

Recorded: the incident capture's town-arrival checkpoint and its first 68 journal rows
(tests/extract_n1a_530_home_full_reject_1117_fixture.py).  Rows 0-36 are decided
through the public choose_key and compared with the record.

DECLARED CONSTRUCTED: the capture did not copy the 49 MB loadout report, and from row
37 on the replay's equipment transaction decides differently (the recorded bot put
the Lance it had taken out for sale back with an equipment-transaction deposit).
Rows 37-66 are still decided through choose_key, but the recorded key is the one
acknowledged, so the boards the journal delivers stay the recorded ones.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-home-full-reject-1117"
MATCHED_ROWS = 37
STOP_ROW = 67
FIVE_WANDS_ROW = 2
LIMIT = 1800
AXE = ("(混沌)グレート・アックス (4d4) (+7,+7)", 22, 25)
WANDS = ("岩石溶解の魔法棒 (215回分) {25%引き}", 65, 6)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1a530HomeFullRejectRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        cls.rejected_on_row_3 = None
        for recorded, supply in steps[:STOP_ROW]:
            board = supply()
            key = policy.choose_key(board)
            if recorded["row"] < MATCHED_ROWS:
                cls.replayed.append(((key, policy.last_reason),
                                     (recorded["key"], recorded["reason"])))
            if recorded["row"] == 3:
                cls.rejected_on_row_3 = (set(policy._home_rejected_deposits),
                                         set(getattr(policy, "_home_full_rejected_deposits", ())))
            # DECLARED CONSTRUCTED (module docstring): the recorded key is acknowledged.
            post(policy, recorded["key"])
        cls.board = steps[STOP_ROW][1]()
        cls.checkpoint = checkpoint_bytes(policy)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            if row == FIVE_WANDS_ROW:
                # Owner 2026-11-17 「戦士は岩石溶解を5本だけ持てばいい。」: the first deposit
                # also shelves 13 of the 18 Stone to Mud wands
                # (tests/test_warrior_stone_to_mud_carry_1118_recorded.py).
                self.assertEqual(decided, ("dndmdk13\rdg\x1b", recorded[1]), row)
                continue
            self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def test_the_full_home_refusal_is_recorded_as_such(self):
        rejected, full_only = self.rejected_on_row_3
        # The 13 Stone to Mud wands past the five carried (owner 2026-11-17) were in the
        # deposit the full Home refused as well.
        self.assertEqual(rejected, {AXE, WANDS})
        self.assertEqual(full_only, {AXE, WANDS})

    def test_the_axe_is_deposited_once_the_home_shows_a_free_slot(self):
        policy, board = self.policy, self.board
        self.assertEqual(self.journal[STOP_ROW]["reason"], "home:weight-overload-deposit")
        self.assertEqual((board.store.store_type, board.store.stock_num, board.store.capacity),
                         (7, 239, 240))
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1940, LIMIT))
        axe = next(item for item in board.inventory if policy._item_signature(item) == AXE)
        self.assertEqual((axe.slot, axe.weight), ("l", 230))

        key = policy.choose_key(board)

        # Recorded: "dm36\rdh\x1b" (the bolts and the Disarming rod, 181.7 lb left).
        # With the five-wand carry (owner 2026-11-17) the 13 other wands (slot j) go with it.
        self.assertEqual((key, policy.last_reason),
                         ("dldj13\r\x1b", "home:weight-overload-deposit"))
        self.assertNotIn(AXE, policy._home_rejected_deposits)
        self.assertLessEqual(policy._inventory_weight(board) - axe.weight, LIMIT)

    def test_a_relief_in_progress_keeps_its_rejections(self):
        policy = self.policy
        policy._home_rejected_deposits = {AXE}
        policy._home_full_rejected_deposits = {AXE}
        policy._home_full_relief = {"deposits": (), "remaining": 1}
        policy._release_home_full_rejections()
        self.assertEqual(policy._home_rejected_deposits, {AXE})
        policy._home_full_relief = None
        policy._release_home_full_rejections()
        self.assertEqual(policy._home_rejected_deposits, set())
        self.assertEqual(policy._home_full_rejected_deposits, set())

    def test_a_rejection_not_caused_by_a_full_home_stays(self):
        policy = self.policy
        other = ("other", 1, 1)
        policy._home_full_relief = None
        policy._home_rejected_deposits = {AXE, other}
        policy._home_full_rejected_deposits = {AXE}
        policy._release_home_full_rejections()
        self.assertEqual(policy._home_rejected_deposits, {other})


if __name__ == "__main__":
    unittest.main()
