"""n1-a life-531 2026-11-19 03:27:42, town:blocked:overweight-home-full-no-legal-relief (bot 4f74fcc1d).

The Lv43 warrior came home from Angband (pack-full return) at 195.6 lb over a 190.0 lb limit
carrying six pieces of loot known by name but waiting on *Identify* (the Dwarven adamantite
plate 28.0 lb, a Bronze Dragon Scale Mail 20.0 lb, a (Trump) Small Sword, a Trident of
Slaying, a Shadow cloak and an amulet of Anti-magic).  The Home stood at 240/240.  The
full-Home relief sold four carried stacks (rows 3-19), leaving the pack at 19 of 23 slots,
the four-slot terminal reserve, so no Home take was admitted (``item_fate.home_take_blocked``).
It then chose each carried piece for identification, which needs *Identify* no source in this
town gives (rows 22-26, ``home:full-skip:identification-source-unavailable``), and stopped
(row 27).  Neither the Q32 supplies nor the ammunition rules took part: no Light scroll was
bought and the 34 carried bolts are the ordinary retained ammunition.

The shelf held no clearly useless stock (one digger; 107 bolts in stacks none of which lies
wholly past the Home keep of 99), so n1-a life-530's round trip (fa6471d0f) found nothing,
yet 136 shelf wares are rank 21+ sale candidates (``_home_full_sale_candidate``), the stock
the relief sells whenever the pack has room.  A ware taken out only to be sold at the next
store leaves the pack as it found it, whatever it is: the relief now takes any of its sale
candidates on that round trip, clearly useless stock first (``item_fate.relief_order``),
and ``item_fate.relief_round_trip`` admits it in one free pack slot (``relief["round_trip"]``).
Since owner 2026-11-19 (tests/test_n1a_531_clearly_useless_1119_recorded.py) the first is a
clearly useless ware: the six Rods of Trap Location no rule uses.

Recorded: the stop's town-arrival checkpoint and all 28 journal rows
(tests/extract_n1a_531_overweight_1119_fixture.py), posted through the live CLI's
owner-retirement entrance (--owner-retired-log-only).  Rows 0-21 are decided through the
public choose_key and compared with the record; row 22 now takes a shelf ware to sell.

DECLARED CONSTRUCTED: row 22's board with the player at the Home entrance (row 1's cell).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import item_fate, town_pack_budget
from hengbot.cli import _handle_owner_retirement
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-overweight-1119"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
CHOICE_ROW = 22
# Rows 12-15 sold the carried Scroll of Teleport Level, a kind the owner's consumable table
# keeps at Home (「自宅」): since owner 2026-11-20 (item_fate.supply_kept,
# tests/test_n1b_411_restore_mana_keep_1120_recorded) no relief sells it, and the replay leaves
# the record there; the later rows post the recorded keys.
KEPT_SUPPLY_ROW = 12
STOP_ROW = 27
HOME_ROW = 1
TVAL_ROD = 66
STORE_MAGIC = 5


def post(policy, board, key, visit_before):
    """Post ``key`` as the live CLI does."""
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1a531Overweight1119RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        for row, (recorded, supply) in enumerate(steps[:CHOICE_ROW + 1]):
            board = supply()
            if row == HOME_ROW:
                cls.home_cell = board.player.position
            if row == CHOICE_ROW:
                cls.board = board
                break
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, board, recorded["key"], before)
        cls.checkpoint = checkpoint_bytes(policy)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, (decided, recorded) in enumerate(self.replayed[:KEPT_SUPPLY_ROW]):
            self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def choose(self):
        key = self.policy.choose_key(self.board)
        return key, self.policy.last_reason

    def test_the_recorded_visit_stopped_over_the_limit(self):
        policy, board = self.policy, self.board
        self.assertEqual(self.journal[STOP_ROW]["reason"],
                         "town:blocked:overweight-home-full-no-legal-relief")
        self.assertEqual(self.journal[CHOICE_ROW]["reason"].split("=>")[0],
                         "town-progress-invariant:defect:home:full-skip:"
                         "identification-source-unavailable")
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1956, 1900))
        self.assertEqual(len(board.inventory), 19)
        self.assertTrue(item_fate.home_take_blocked(board))
        self.assertEqual(len(policy._home_knowledge_items), 240)
        self.assertIsNotNone(policy._home_full_relief)
        # None of life-530's classes (diggers, bolts): its round trip had nothing to take.
        self.assertEqual([item for item in policy._home_knowledge_items
                          if item_fate.clearly_useless(policy, board, replace(
                              item, slot=item_fate.HOME_STOCK_SLOT)) in (
                                  "unused-ammo", "surplus-digger", "surplus-ammo")], [])

    def test_the_relief_takes_a_shelf_sale_ware_on_a_round_trip(self):
        policy = self.policy
        self.assertEqual(self.choose(), ("\x1b`n(.", "shop:travel"))  # to the Home
        relief = policy._home_full_relief
        signature = relief["sale"][0]
        ware = next(item for item in policy._home_knowledge_items
                    if policy._item_signature(item) == signature)
        self.assertEqual((ware.tval, ware.sval, ware.count), (TVAL_ROD, 0, 6))
        self.assertEqual((relief["mode"], relief["round_trip"], relief["withdrawn"], relief["sale"][1]),
                         ("sale", signature, False, STORE_MAGIC))
        self.assertEqual(relief["useless"], signature)
        # The take needs a pack slot, not the reserve; no other Home take does.
        self.assertFalse(town_pack_budget.permits(self.board, 1))
        self.assertTrue(town_pack_budget.home_take_fits(
            self.board, ware, ware.count, policy=policy))
        other = next(item for item in policy._home_knowledge_items
                     if policy._item_signature(item) != signature)
        self.assertFalse(town_pack_budget.home_take_fits(
            self.board, other, other.count, policy=policy))

    def test_at_the_home_entrance_the_take_is_composed(self):
        policy = self.policy
        key, _ = self.choose()
        post(policy, self.board, key, None)
        at_home = replace(self.board, player=replace(self.board.player, position=self.home_cell))
        decided = []
        for _ in range(2):
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(at_home)
            decided.append((key, policy.last_reason))
            post(policy, at_home, key, before)
        # The take of the 6 Rods of Trap Location off the Home shelf, composed outside.
        self.assertEqual(decided, [("", "store:entry-await-observation"),
                                   ("5pD6\r\x1b", "home-errand:atomic-withdraw:full-home-sale")])

    def test_taken_out_the_ware_is_a_pack_stack_sold_at_once(self):
        policy = self.policy
        self.choose()
        relief = policy._home_full_relief
        ware = next(item for item in policy._home_knowledge_items
                    if policy._item_signature(item) == relief["sale"][0])
        taken = replace(ware, slot="t")
        carried = replace(self.board, inventory=(*self.board.inventory, taken))
        self.assertEqual(policy._retention_reservation(carried, taken), 0)
        relief["withdrawn"] = True
        self.assertFalse(item_fate.relief_round_trip(policy, taken))


if __name__ == "__main__":
    unittest.main()
