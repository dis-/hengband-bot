"""n1-a life-530 2026-11-18 03:06:36, town:blocked:overweight-home-full-no-legal-relief (bot 1df9764b9).

The Lv47 warrior came home from the Mountain at 219.5 lb over a 195.0 lb limit with four
pieces of loot waiting on *Identify* (the (Trump) Heavy Flail 28.0 lb, the Druid soft armour,
the cloak of Protection, the Longbow of Extra Shots) and a Gold Dragon Scale Mail beside its
Uruk plate.  The Home stood at 240/240 and the pack at 20 of 23 slots, below the four-slot
terminal reserve, so the full-Home relief could take nothing off the shelf and shed only
carried stock: it sold three carried stacks (rows 9-20), then chose each carried piece in
turn for identification, which needs *Identify* no source in this town gives (rows 23-29,
``home:full-skip:identification-source-unavailable``), and stopped (row 30).

The shelf held 27 stacks of plain (+0,+0) crossbow bolts past the Home keep of 99, the
stock owner 2026-11-17 named to be sold 「自宅は明確に無駄な採掘道具や矢を売却すれば空きを作れる」
(``item_fate.clearly_useless`` ``surplus-ammo``).  Three things kept the relief from them:

* the pack reserve: a take sold at once leaves the pack as it found it, so the relief's
  clearly useless ware now needs a free pack slot only (``town_pack_budget.round_trip_fits``,
  admitted by ``home_take_fits`` through ``item_fate.relief_round_trip``);
* the merge barrier: the carried 43 {@0} bolts barred every shelf stack of their identity,
  though stacks inscribed differently never merge (item-entity.cpp ``is_similar_part``);
* the ware: the relief found its taken ware by ``_sale_item_identity`` alone, which would
  have named the carried {@0} stack first (``item_fate.relief_ware`` takes the stack of the
  recorded name first).

Recorded: the incident capture's town-arrival checkpoint and all 31 journal rows
(tests/extract_n1a_530_overweight_relief_1118_fixture.py), posted through the live CLI's
owner-retirement entrance (--owner-retired-log-only).  Rows 0-22 are decided through the
public choose_key and compared with the record; row 23 now takes the relief's bolts.

DECLARED CONSTRUCTED: row 23's board with the player at the Home entrance (row 3's cell),
and row 23's board with the taken 2 {@1} bolts in the pack.
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

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-overweight-relief-1118"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
CHOICE_ROW = 23
STOP_ROW = 30
HOME_ROW = 3
TVAL_BOLT = 18
STORE_WEAPONSMITH = 2


def post(policy, board, key, visit_before):
    """Post ``key`` as the live CLI does."""
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def plain_bolts(item, inscription):
    return (item.tval, item.to_h, item.to_d, item.inscription) == (TVAL_BOLT, 0, 0, inscription)


class N1a530OverweightRelief1118RecordedTest(unittest.TestCase):
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
        for row, (decided, recorded) in enumerate(self.replayed):
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
                         (2195, 1950))
        self.assertEqual(len(board.inventory), 20)
        self.assertTrue(item_fate.home_take_blocked(board))
        self.assertEqual(len(policy._home_knowledge_items), 240)
        relief = policy._home_full_relief
        verdicts = [item_fate.clearly_useless(policy, board, replace(
                        item, slot=item_fate.HOME_STOCK_SLOT))
                    for item in policy._home_knowledge_items]
        self.assertIsNotNone(relief)
        self.assertEqual(verdicts.count("surplus-ammo"), 27)

    def test_the_relief_takes_a_surplus_bolt_stack_to_sell(self):
        policy = self.policy
        self.assertEqual(self.choose(), ("\x1b`n(.", "shop:travel"))  # to the Home
        relief = policy._home_full_relief
        signature = relief["sale"][0]
        ware = next(item for item in policy._home_knowledge_items
                    if policy._item_signature(item) == signature)
        self.assertTrue(plain_bolts(ware, "@1"))
        self.assertEqual((relief["mode"], relief["useless"], relief["withdrawn"], relief["sale"][1]),
                         ("sale", signature, False, STORE_WEAPONSMITH))
        self.assertEqual(item_fate.clearly_useless(policy, self.board, replace(
            ware, slot=item_fate.HOME_STOCK_SLOT)), "surplus-ammo")
        # The take needs a pack slot, not the reserve; no other Home take does.
        self.assertFalse(town_pack_budget.permits(self.board, 1))
        self.assertTrue(town_pack_budget.home_take_fits(
            self.board, ware, ware.count, policy=policy))
        other = next(item for item in policy._home_knowledge_items
                     if item.tval != TVAL_BOLT)
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
        # The take of the 2 {@1} bolts on the Home's fifth page, composed outside.
        self.assertEqual(decided, [("", "store:entry-await-observation"),
                                   ("5    py2\r\x1b", "home-errand:atomic-withdraw:full-home-sale")])

    def test_the_carried_bolts_do_not_bar_a_stack_inscribed_otherwise(self):
        policy, board = self.policy, self.board
        [carried] = [item for item in board.inventory if plain_bolts(item, "@0")]
        self.assertEqual(carried.count, 43)
        shelf = [replace(item, slot=item_fate.HOME_STOCK_SLOT)
                 for item in policy._home_knowledge_items if item.tval == TVAL_BOLT]
        barred = {item.inscription: policy._home_full_merge_reserved(board, item, destroy=False)
                  for item in shelf if plain_bolts(item, item.inscription)}
        self.assertEqual(barred, {"@0": True, "@1": False})

    def test_the_taken_stack_is_the_ware_not_the_carried_one(self):
        policy = self.policy
        self.choose()
        relief = policy._home_full_relief
        ware = next(item for item in policy._home_knowledge_items
                    if policy._item_signature(item) == relief["sale"][0])
        taken = replace(ware, slot="u")
        carried_board = replace(self.board, inventory=(*self.board.inventory, taken))
        relief["withdrawn"] = True
        [carried] = [item for item in carried_board.inventory if plain_bolts(item, "@0")]
        self.assertIs(item_fate.relief_ware(policy, carried_board), taken)
        self.assertTrue(item_fate.relief_useless(policy, carried_board, taken))
        self.assertFalse(item_fate.relief_useless(policy, carried_board, carried))
        self.assertEqual(policy._retention_reservation(carried_board, taken), 0)
        self.assertEqual(policy._retention_reservation(carried_board, carried), 43)
        # Taken out, it is a pack stack: no further round trip is admitted for it.
        self.assertFalse(item_fate.relief_round_trip(policy, taken))


if __name__ == "__main__":
    unittest.main()
