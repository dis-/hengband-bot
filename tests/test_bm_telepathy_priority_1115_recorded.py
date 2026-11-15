"""Full telepathy on a shelf, bought first like the *Destruction* staff (owner 2026-11-15).

Owner 2026-11-15 (n1-a life-525: a warrior whose only ESP was a crown of eight race ESPs
in the Home, held at 49F by the 50F telepathy requirement), verbatim: 「完全なテレパシーを
闇市で最優先で買う」, to be bought as the staff is: when the gold is short, Home's spare
weapons and body armour are sold in the same visit (bm_destruction_fund.PRIORITY_WARES).

Recorded: n1-a life-526's town visit of 2026-11-15 22:45 (warrior Lv28, no telepathy,
tests/extract_bm_telepathy_priority_1115_fixture.py).  Journal row 25 is the visit's Black
Market page: テレパシーのアミュレット {~感} (TR_TELEPATHY) at letter G for 221,344 with 18,784
gold.  Live, the page bought a Potion of Cure Critical Wounds (k) and a Potion of Resistance
and the visit recalled.  Rows 0-24 replay through the public chooser and the live CLI's
owner-retirement entrance (--owner-retired-log-only, as the viewing bots run) and decide as
recorded; each posts its recorded key.

Recorded outcome: the amulet is 208,757 short under the optional reserve (6,197) and every
eligible Home spare together cannot cover it, so nothing is sold, the page buys as it did
live and the errand closes ``unaffordable`` with its drift warning.

DECLARED CONSTRUCTED: the same row-25 board with other gold (covering the amulet, or short
by what Home's spares cover), with full telepathy owned (in the Home, or worn), with the
amulet's TR_TELEPATHY replaced by race ESP flags, and (for the closing) the board after
row 27 outside the shop.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import bm_destruction_fund, item_fate
from hengbot.cli import _handle_owner_retirement
from hengbot.model import STORE_BLACK, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "bm-telepathy-priority-1115" / "n1a-526-2245"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
BLACK_MARKET_ROW = 25
LAST_ROW = 27
PRICE = 221344
GOLD = 18784
RESERVE = 6197
AMULET = "G"
RUNG = "priority-ware:telepathy"
# equipment_utility.TR_ESP_KINDS: the race ESPs (ESP_ANIMAL..ESP_UNIQUE), not telepathy.
RACE_ESP = frozenset({104, 105, 106, 107, 108, 109, 110, 111})


def post(policy, board, key, visit_before):
    """Post ``key`` as the live CLI does; returns what was posted."""
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    return key


class BlackMarketTelepathyPriority1115RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Rows 0-24 posted as recorded (each decided as recorded); the policy before row 25."""
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURE, Path(scratch.name))
        cls.mismatches = []
        for row, supply in steps[:BLACK_MARKET_ROW]:
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            entry = recorded[row["row"]]
            if (key, policy.last_reason) != (entry["key"], entry["reason"]):
                cls.mismatches.append((row["row"], key, policy.last_reason))
            post(policy, board, entry["key"], before)
        cls.arrival = policy
        cls.recorded = recorded
        cls.steps = steps
        cls.page = steps[BLACK_MARKET_ROW][1]()

    def policy(self):
        return copy.deepcopy(self.arrival)

    def board(self, *, gold=GOLD, amulet_flags=None):
        if amulet_flags is None and gold == GOLD:
            return self.page
        raw = json.loads(self.recorded[BLACK_MARKET_ROW]["line"])
        raw["player"]["gold"] = gold
        for ware in raw["store"]["items"]:
            if ware["letter"] == AMULET and amulet_flags is not None:
                ware["known_flags"] = sorted(amulet_flags)
        return parse_snapshot(raw, self.arrival._monrace_knowledge)

    @staticmethod
    def amulet(board):
        return next(ware for ware in board.store.items if ware.letter == AMULET)

    def decide(self, policy, board):
        key = policy.choose_key(board)
        return key, policy.last_reason

    def test_rows_before_the_page_decide_as_recorded(self):
        self.assertEqual(self.mismatches, [])
        board = self.page
        self.assertEqual(board.store.store_type, STORE_BLACK)
        self.assertEqual(board.player.gold, GOLD)
        self.assertNotIn("telepathy", board.player.abilities)
        self.assertIn(bm_destruction_fund.TR_TELEPATHY, self.amulet(board).known_flags)
        self.assertEqual(self.amulet(board).price, PRICE)

    def test_the_recorded_page_shelves_the_amulet_and_the_spares_fall_short(self):
        policy = self.policy()
        board = self.page
        key, reason = self.decide(policy, board)
        shelf = policy._bm_destruction_shelf
        self.assertEqual((shelf["ware"], shelf["store"], shelf["price"]), ("telepathy", STORE_BLACK, PRICE))
        self.assertEqual(policy._full_departure_resupply_reserve(board), RESERVE)
        self.assertEqual(bm_destruction_fund.shortfall(policy, board), PRICE + RESERVE - GOLD)
        # Home's census is current (row 10); its eligible spares cannot cover 208,757.
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(bm_destruction_fund.plan(policy, board), ())
        self.assertFalse(bm_destruction_fund.staff_pending(policy, board))
        # Nothing is sold for it, so the page buys as it did live.
        entry = self.recorded[BLACK_MARKET_ROW]
        self.assertEqual((key, reason), (entry["key"], entry["reason"]))
        # Rows 26-27 as recorded, then the board outside (DECLARED CONSTRUCTED from row 27):
        # the errand closes and says so in the decision log.
        post(policy, board, key, copy.copy(policy._store_visit))
        for row, supply in self.steps[BLACK_MARKET_ROW + 1:LAST_ROW + 1]:
            board = supply()
            before = copy.copy(policy._store_visit)
            policy.choose_key(board)
            post(policy, board, self.recorded[row["row"]]["key"], before)
        raw = json.loads(self.recorded[LAST_ROW]["line"])
        raw["store"] = None
        raw["type"] = "player_turn"
        raw["turn"] += 10
        outside = parse_snapshot(raw, policy._monrace_knowledge)
        policy.observe_store_screen(None)
        policy.choose_key(outside)
        self.assertEqual(policy._bm_destruction_shelf["closed"], "unaffordable")
        self.assertTrue(any(warning.startswith(bm_destruction_fund.UNAFFORDABLE_WARNING)
                            for warning in policy._town_visit_ledger.drift_warnings))
        self.assertTrue(policy._town_departure_conjuncts(outside, commit=False)["destruction_staff_settled"])

    def test_the_covered_amulet_is_bought_first(self):
        # DECLARED CONSTRUCTED: the page with the gold to cover the amulet and the reserve.
        policy = self.policy()
        board = self.board(gold=PRICE + RESERVE + 10)
        key, reason = self.decide(policy, board)
        self.assertEqual((key, reason), ("pG\r", "shop:in-store-buy"))
        matches = policy._matching_live_purchase_rungs(board, self.amulet(board))
        self.assertEqual([match.rung_id for match in matches], [RUNG])

    def test_spares_that_cover_it_hold_the_page_and_the_departure(self):
        # DECLARED CONSTRUCTED: the page 26,197 short, which Home's spares cover.
        policy = self.policy()
        board = self.board(gold=PRICE - 20000)
        key, reason = self.decide(policy, board)
        self.assertTrue(bm_destruction_fund.staff_pending(policy, board))
        plan = bm_destruction_fund.plan(policy, board)
        self.assertTrue(plan)
        self.assertEqual({item_fate.SLOT_BY_TVAL[signature[1]] for signature in plan}
                         - bm_destruction_fund.FUND_SLOTS, set())
        # 「最優先」: the page buys nothing else (live: the Cure Critical Wounds at k).
        self.assertIsNone(policy._next_purchase(board))
        self.assertIsNone(policy._black_market_optional_purchase(board))
        self.assertTrue(policy._bm_destruction_shelf["withheld"])
        self.assertNotEqual(key, self.recorded[BLACK_MARKET_ROW]["key"])
        self.assertFalse(key.startswith("p"), (key, reason))
        self.assertFalse(policy._town_departure_conjuncts(board, commit=False)["destruction_staff_settled"])

    def test_owned_telepathy_wants_nothing(self):
        entry = self.recorded[BLACK_MARKET_ROW]
        # DECLARED CONSTRUCTED: a telepathy piece in the Home's census.
        policy = self.policy()
        policy._home_knowledge_items = (*policy._home_knowledge_items, self.amulet(self.page))
        self.assertEqual(self.decide(policy, self.page), (entry["key"], entry["reason"]))
        self.assertIsNone(getattr(policy, "_bm_destruction_shelf", None))
        # DECLARED CONSTRUCTED: telepathy worn.
        policy = self.policy()
        worn = replace(self.page, player=replace(
            self.page.player, abilities=self.page.player.abilities | {"telepathy"}))
        self.assertEqual(self.decide(policy, worn), (entry["key"], entry["reason"]))
        self.assertIsNone(getattr(policy, "_bm_destruction_shelf", None))

    def test_race_esp_is_not_full_telepathy(self):
        # DECLARED CONSTRUCTED: the amulet with eight race ESPs (n1-a's crown) for TR_TELEPATHY.
        entry = self.recorded[BLACK_MARKET_ROW]
        policy = self.policy()
        board = self.board(amulet_flags=RACE_ESP)
        self.assertEqual(self.decide(policy, board), (entry["key"], entry["reason"]))
        self.assertIsNone(getattr(policy, "_bm_destruction_shelf", None))


if __name__ == "__main__":
    unittest.main()
