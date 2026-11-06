"""The Black Market's Staff of *Destruction* (owner 2026-11-07).

「BMの買い物優先度について。*破壊*の杖の優先度を上げる。自宅にあるアーティファクトでない
予備の武器と予備の胴防具を売って購入可能なら購入する。このとき優先度2-10位の非アーティ
ファクトにも例外で手を付ける。」  Asked when it buys: 「何本でも買う」.

Substrate: home-room-n1b (n1-b Lv40 2026-11-04 21:47, tests/extract_spare_gear_fixtures.py),
replayed through the public chooser.  Row 22 is that visit's own Black Market page
(it bought six Potions of Speed with 41,033 gold); row 25 is the board outside after
it, walking to Home with 28,347 gold; Home holds 238 rows, 51 ranked melee weapons
and 30 ranked body armours among them.

DECLARED CONSTRUCTED: no recorded Black Market page shelves the staff (the game's
fixed articles-on-sale table never lists it), so the pins put one on the recorded
page in place of the ware at letter X, at a stated price.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace

from hengbot import bm_destruction_fund, item_fate
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
from hengbot.model import (
    STORE_BLACK, STORE_WEAPON, SV_STAFF_DESTRUCTION, TVAL_STAFF,
)
from tests import test_input_executor as _test_input_executor
from tests.test_spare_gear_recorded import Visit

SWEEP_SPENT_ROW = 9
BLACK_MARKET_ROW = 22
OUTSIDE_ROW = 25
AFTER_DEPOSIT_ROW = 27
OUTSIDE_GOLD = 28347
STAFF_LETTER = "X"
# The recorded full resupply reserve on the board outside (owner 2026-10-08).
RESERVE = 6657
# The recorded n1-b Home: the best non-artifact melee weapon (rank 1), the
# fifth (rank 5), and an artifact of the same slot.
RANK_ONE = "(パターン)パイク (2d5) (+9,+7) (+2) {+腕耐r呪;麻視経/邪デ死}"
RANK_FIVE = "(聖戦者)ロッホアーバー・アックス (3d8) (+12,+8) [+2] (+1攻撃) {+攻賢r恐;視祝/邪デ死(賢}"
TAKE_FOR_SALE = "home-errand:atomic-withdraw:full-home-sale"
ARTIFACT = "★ブロード・ソード『ノートゥング』 (2d5) (+12,+16) (+4) {+腕探r電火毒恐;遅明|電/X龍/オ~竜}"


def with_staff(board, price):
    """The recorded page with a Staff of *Destruction* (5 charges) at letter X."""
    wares = [replace(ware, name="*破壊*の杖 (5回分)", tval=TVAL_STAFF,
                     sval=SV_STAFF_DESTRUCTION, count=1, price=price,
                     charges=5, pval=5)
             if ware.letter == STAFF_LETTER else ware
             for ware in board.store.items]
    return replace(board, store=replace(board.store, items=wares))


def carrying_staff(board):
    """DECLARED CONSTRUCTED: one Staff of *Destruction* already in the pack."""
    template = next(item for item in board.inventory if item.slot == "p")
    staff = replace(template, slot="s", name="*破壊*の杖 (5回分)",
                    sval=SV_STAFF_DESTRUCTION, charges=5, pval=5, count=1)
    return replace(board, inventory=[*board.inventory, staff])


class BlackMarketDestructionRecordedTest(_test_input_executor.ProductionHarness):
    def visit(self, rows):
        visit = Visit("home-room-n1b", True)
        self.addCleanup(visit.close)
        for index, (recorded, supply) in enumerate(visit.rows[:rows]):
            if index == SWEEP_SPENT_ROW:
                # DECLARED WALL: the rank 21+ sweep (owner 11-04) was added after
                # this recording and walks Home from row 9; spent for the stay
                # here, the recorded rows replay as they were decided.
                visit.policy._home_junk_sweep_count = (
                    visit.policy._town_visit_epoch, item_fate.SWEEP_LIMIT_PER_STAY)
            board = supply()
            key = visit.policy.choose_key(board)
            self.assertEqual((key, visit.policy.last_reason), (recorded["key"], recorded["reason"]))
            visit.post(key)
        return visit

    @staticmethod
    def home_row(policy, name):
        return next(item for item in policy._home_knowledge_items if item.name == name)

    def after_the_black_market(self, price):
        """Rows 0-26 with the staff on the recorded Black Market page at ``price``.

        Row 25 walks Home, row 26 makes its deposit; returns the visit and the
        Home census row 25 held (the last one before the deposit).
        """
        visit = self.visit(BLACK_MARKET_ROW)
        policy = visit.policy
        census = None
        for index in range(BLACK_MARKET_ROW, AFTER_DEPOSIT_ROW):
            recorded, supply = visit.rows[index]
            board = supply()
            if board.store is not None and board.store.store_type == STORE_BLACK:
                board = with_staff(board, price)
            key = policy.choose_key(board)
            # Short of the optional reserve, the recorded Speed buys, the walk
            # Home and its deposit stand.
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            if index == OUTSIDE_ROW:
                self.assertTrue(policy._home_knowledge_current)
                census = policy._home_knowledge_items
                self.assertEqual(board.player.gold, OUTSIDE_GOLD)
                self.assertEqual(policy._full_departure_resupply_reserve(board), RESERVE)
            visit.post(key)
        self.assertEqual(policy._bm_destruction_shelf["price"], price)
        return visit, census

    def census_answered(self, visit, census, *, keep=lambda item: True):
        """Row 27 (outside, after the deposit): the fund asks Home's census.

        Recorded there: the character dump, then the recall (row 28).
        DECLARED CONSTRUCTED: the ``~9`` answer is row 25's census (the
        deposit added potions only, no weapon or body armour), its rows that
        ``keep`` keeps.  Returns row 28.
        """
        policy = visit.policy
        recorded, supply = visit.rows[AFTER_DEPOSIT_ROW]
        self.assertEqual((recorded["key"], recorded["reason"]),
                         ("Cf\ry\x1b\x1b", "town:character-dump"))
        self.assertFalse(policy._home_knowledge_current)
        key = policy.choose_key(supply())
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        visit.post(key)
        # DECLARED CONSTRUCTED: the answer's melee weapons and body armour only.
        # Home's junk (a Curse Weapon scroll and more) is destroyed by the
        # sweep before any sale (#70); the fund's takes follow it.
        policy.consume_home_knowledge(tuple(
            item for item in census
            if item_fate.SLOT_BY_TVAL.get(item.tval) in bm_destruction_fund.FUND_SLOTS
            and keep(item)))
        board = visit.rows[AFTER_DEPOSIT_ROW + 1][1]()
        # DECLARED CONSTRUCTED: one unread scroll fewer in the pack.  The
        # recorded pack leaves exactly the five slots the Home sweep keeps free
        # (HOME_BATCH_RESERVED_SLOTS), so no take would start on it.
        unread = next(item for item in board.inventory if not item.aware)
        return replace(board, inventory=[item for item in board.inventory if item is not unread])

    # -- the purchase: the top of the Black Market's optional picks ----------

    def test_the_staff_is_bought_above_the_potions_with_one_already_carried(self):
        visit = self.visit(BLACK_MARKET_ROW)
        policy = visit.policy
        recorded, supply = visit.rows[BLACK_MARKET_ROW]
        # Recorded: six Potions of Speed, the optional pick of this shelf.
        self.assertEqual((recorded["key"], recorded["reason"]), ("ps6\r\r", "shop:in-store-buy"))
        board = carrying_staff(with_staff(supply(), 15000))
        self.assertEqual(policy._total_destruction_uses(board), 5)
        self.assertEqual((policy.choose_key(board), policy.last_reason), ("pX\r", "shop:in-store-buy"))
        staff = next(ware for ware in board.store.items if ware.letter == STAFF_LETTER)
        self.assertEqual(policy._matching_live_purchase_rungs(board, staff)[0].rung_id,
                         "black-market:destruction")

    # -- the fund: Home's spare weapons and body armour pay for it ----------

    def test_short_gold_takes_the_cheapest_to_lose_spare_out_first(self):
        # 15,000 short: the six cheapest rank 46+ melee pieces cover it.
        visit, census = self.after_the_black_market(OUTSIDE_GOLD - RESERVE + 15000)
        policy = visit.policy
        board = self.census_answered(visit, census)
        self.assertEqual(bm_destruction_fund.shortfall(policy, board), 15000)
        plan = bm_destruction_fund.plan(policy, board)
        ranks = [item_fate.gear_rank(policy, board, self.home_row(policy, name))
                 for name, _tval, _sval in plan]
        self.assertEqual(ranks, [51, 50, 49, 48, 47, 46])
        key = policy.choose_key(board)
        # At the Home entrance: the atomic take of the sale's ware.
        self.assertEqual(policy.last_reason, TAKE_FOR_SALE)
        self.assertTrue(key.startswith("5") and "p" in key, repr(key))
        relief = policy._home_full_relief
        self.assertTrue(relief["sweep"])
        self.assertEqual(relief["mode"], "sale")
        self.assertEqual(relief["fund"], plan[0])
        self.assertEqual(policy._home_pending_item, plan[0])

    def test_a_rank_five_weapon_is_taken_out_for_the_staff(self):
        visit, census = self.after_the_black_market(OUTSIDE_GOLD - RESERVE + 15000)
        policy = visit.policy
        board = self.census_answered(visit, census)
        rank_five = self.home_row(policy, RANK_FIVE)
        # DECLARED CONSTRUCTED: every melee piece of a higher rank number than
        # 5 and every body piece was refused by its buyer earlier
        # (_unsellable_items), so the cheapest-to-lose order reaches the rank 5
        # weapon first; the census and every rank are unchanged.
        policy._unsellable_items.update(
            policy._item_signature(item) for item in policy._home_knowledge_items
            if (item_fate.gear_rank(policy, board, item) or 0) > 5
            or item_fate.SLOT_BY_TVAL[item.tval] == "body")
        rank_one = self.home_row(policy, RANK_ONE)
        self.assertEqual(item_fate.gear_rank(policy, board, rank_five), 5)
        self.assertEqual(item_fate.gear_rank(policy, board, rank_one), 1)
        self.assertEqual(bm_destruction_fund.plan(policy, board),
                         (policy._item_signature(rank_five),))
        self.assertEqual(item_fate.gear_tier(policy, board, rank_five), item_fate.ANY)
        self.assertEqual(item_fate.gear_tier(policy, board, rank_one), item_fate.KEEP)
        self.assertEqual(item_fate.gear_tier(policy, board, self.home_row(policy, ARTIFACT)),
                         item_fate.KEEP)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, TAKE_FOR_SALE)
        self.assertTrue(key.startswith("5") and "p" in key, repr(key))
        visit.post(key)
        relief = policy._home_full_relief
        self.assertEqual(relief["fund"], policy._item_signature(rank_five))
        # Its buyer is the Weapon Smith.
        self.assertEqual(relief["sale"][1], STORE_WEAPON)
        # DECLARED CONSTRUCTED: the take's effect, the axe in the pack a turn
        # later (the recorded board, its letter w free).
        taken = replace(board, turn=board.turn + 1,
                        inventory=[*board.inventory, replace(rank_five, slot="w")])
        key = policy.choose_key(taken)
        self.assertEqual((key, policy.last_reason), ("\x1b`n#.", "shop:travel"))
        self.assertTrue(policy._home_full_relief["withdrawn"])
        # Carried, it is still the fund's: never shelved back at Home.
        carried = next(item for item in taken.inventory if item.name == RANK_FIVE)
        self.assertEqual(item_fate.gear_tier(policy, taken, carried), item_fate.ANY)
        self.assertTrue(item_fate.sold_not_shelved(policy, taken, carried))

    def test_rank_one_and_artifacts_are_never_in_the_fund(self):
        # So short that nearly every eligible piece is needed: still not these.
        visit, census = self.after_the_black_market(OUTSIDE_GOLD - RESERVE + 440000)
        policy = visit.policy
        board = self.census_answered(visit, census)
        plan = bm_destruction_fund.plan(policy, board)
        self.assertGreater(len(plan), 70)
        names = {name for name, _tval, _sval in plan}
        self.assertIn(RANK_FIVE, names)
        self.assertNotIn(RANK_ONE, names)
        self.assertNotIn(ARTIFACT, names)
        self.assertFalse(any(item.is_artifact or not item.known
                             for item in policy._home_knowledge_items
                             if item.name in names))
        self.assertTrue(all(item_fate.gear_rank(policy, board, self.home_row(policy, name)) >= 2
                            for name in names))
        # Only melee weapons and body armour.
        self.assertEqual({item_fate.SLOT_BY_TVAL[tval] for _name, tval, _sval in plan},
                         {"melee", "body"})
        # 30,000 poorer, ranks 2+ no longer cover it (their estimates total
        # 464,983): the rank 1 pieces are not counted in, so nothing is sold.
        poorer = replace(board, player=replace(board.player, gold=board.player.gold - 30000))
        self.assertEqual(bm_destruction_fund.shortfall(policy, poorer), 470000)
        self.assertEqual(bm_destruction_fund.plan(policy, poorer), ())

    def test_spares_short_of_the_staff_sell_nothing(self):
        visit, census = self.after_the_black_market(900000)
        policy = visit.policy
        board = self.census_answered(visit, census)
        self.assertGreater(bm_destruction_fund.shortfall(policy, board), 0)
        self.assertEqual(bm_destruction_fund.plan(policy, board), ())
        rank_five = self.home_row(policy, RANK_FIVE)
        self.assertEqual(item_fate.gear_tier(policy, board, rank_five), item_fate.KEEP)
        key = policy.choose_key(board)
        # The recorded character dump resumes; nothing is taken out.
        self.assertEqual((key, policy.last_reason), ("Cf\ry\x1b\x1b", "town:character-dump"))
        self.assertIsNone(policy._home_full_relief)
        # One census per stay and gold: no second request.
        self.assertFalse(bm_destruction_fund.census_wanted(policy, board))

    def test_covered_gold_reopens_the_black_market_for_the_staff(self):
        price = OUTSIDE_GOLD - RESERVE + 15000
        visit, _census = self.after_the_black_market(price)
        policy = visit.policy
        self.assertIn(STORE_BLACK, policy._town_errand_plan.completed_this_visit)
        recorded, supply = visit.rows[AFTER_DEPOSIT_ROW]
        board = supply()
        # DECLARED CONSTRUCTED: the fund's sales brought the shortfall in.
        sold = replace(board, player=replace(board.player, gold=price + RESERVE))
        self.assertEqual(bm_destruction_fund.shortfall(policy, sold), 0)
        key = policy.choose_key(sold)
        self.assertNotIn(STORE_BLACK, policy._town_errand_plan.completed_this_visit)
        self.assertTrue(policy._bm_destruction_shelf["rearmed"])
        self.assertIn(STORE_BLACK, policy._town_errand_plan.stops)
        # Back to the Black Market (recorded row 21's walk there), where the
        # optional pick buys the staff (the first pin above).
        self.assertEqual((key, policy.last_reason), ("\x1b`n'.", "shop:travel"))


if __name__ == "__main__":
    unittest.main()
