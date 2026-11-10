"""A mining set buys its survival shortfall after the kit (two 2026-11-10 stops).

Owner 2026-11-03 「道具の後に足りない分を買う」: in a mining set the kit comes
first, then the remaining gold buys the departure-survival shortfall, as much
as it pays for (hengbot.fundraising_survival).

n1-a life-507 (Lv22 Zombie Warrior, mode "prepare", 08:40): on the
Alchemist's page (テレポートの巻物 x66 at 61 gold, 3,827 gold, teleport 12/15
from the Q31 carry) the store's fundraising order bought the Treasure
Detection and one recall and left; the in-store dry run then judged the shelf
without a teleport, the planner dropped the stop, and the visit stopped on
town:blocked:survival:teleport_ready.

n1-b life-364 (Lv7 Zombie Magic-Eater, mode "scavenge", 10:21): one food
charge short (14/15, an edible staff carried), the order's food rung ranked
first and bought a 1,177-gold スリープ・モンスターの魔法棒 with 1,262 gold,
leaving 78 for a teleport 0/4, Cure 0/4 departure; the next departure stopped
on town:blocked:survival:recall_departure_ready (0/3).

Recorded: tests/fixtures/fundraise-survival-1110.json.gz
(tests/extract_fundraise_survival_1110_fixture.py).  Every decision is the
public ``choose_key`` on one policy; posted keys go to ``confirm_key_posted``.

DECLARED CONSTRUCTED / RECONSTRUCTED: the policy is the production
construction of the Q2 tower tests from the first board (an empty Home page,
the store screen verified as live), with ``_fundraising_mode`` the recorded
rows' mode.  The n1-b page before the wand buy is not in the ring: it is the
next visit's page (turn 135195) with the bought wand back on the shelf (the
buy row: k, 3 wands, 41 charges, 1,177 gold), off the pack, and the gold of
the buy row (1,262).  The page after the scroll sale adds the sale's 9 gold
(the recorded 78 -> 87 of that sale) and drops the sold scroll.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import fundraising_survival
from hengbot.model import STORE_ALCHEMIST, STORE_MAGIC, TVAL_WAND, parse_snapshot
from hengbot.policy_types import TownNeed
# The module, not the class: a TestCase bound here would run its tests again.
from tests import test_q2_tower_recharge_recorded as q2_town

FIXTURE = Path(__file__).parent / "fixtures" / "fundraise-survival-1110.json.gz"
SV_WAND_SLEEP_MONSTER = 8


def capture():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def _relettered(raw):
    for index, row in enumerate(raw["inventory"]):
        row["slot"] = chr(ord("a") + index)
    return raw


def n1b_before_buy(raw):
    """DECLARED RECONSTRUCTED: the first visit's page before the wand buy."""
    raw = copy.deepcopy(raw)
    raw["inventory"] = [row for row in raw["inventory"]
                        if (row.get("tval"), row.get("sval")) != (TVAL_WAND, SV_WAND_SLEEP_MONSTER)]
    shelf = next(row for row in raw["store"]["items"]
                 if (row["tval"], row["sval"]) == (TVAL_WAND, SV_WAND_SLEEP_MONSTER))
    shelf.update(count=3, price=1177, pval=41, charges=41,
                 name=shelf["name"].replace("27", "41"))
    raw["player"]["gold"] = 1262
    return _relettered(raw)


def n1b_after_sale(raw):
    """DECLARED CONSTRUCTED: the page after the unknown scroll's sale."""
    raw = copy.deepcopy(raw)
    raw["inventory"] = [row for row in raw["inventory"] if row.get("sval") is not None]
    raw["player"]["gold"] += 9
    raw["turn"] += 1
    return _relettered(raw)


class FundraiseSurvivalRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        q2_town.Q2TowerRechargeRecordedTest.setUpClass.__func__(cls)
        cls.capture = capture()

    def policy(self, raw, mode):
        policy = q2_town.Q2TowerRechargeRecordedTest.policy(self, raw)
        policy._fundraising_mode = mode
        policy._in_store_screen_verified = True
        return policy

    def board(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.monraces)

    def decide(self, policy, raw):
        key = policy.choose_key(self.board(raw))
        policy.confirm_key_posted(key)
        return key

    # n1-a life-507 -------------------------------------------------------

    def test_n1a_recorded_rows(self):
        case = self.capture["n1a-507"]
        page = case["boards"][0]
        self.assertEqual(page["store"]["store_type"], STORE_ALCHEMIST)
        self.assertEqual(page["player"]["gold"], 3827)
        teleport = next(row for row in page["store"]["items"] if (row["tval"], row["sval"]) == (70, 9))
        self.assertEqual((teleport["letter"], teleport["count"], teleport["price"]), ("g", 66, 61))
        carried = sum(row["count"] for row in page["inventory"]
                      if (row.get("tval"), row.get("sval")) == (70, 9))
        self.assertEqual(carried, 12)
        recorded = [(row["key"], row["reason"]) for row in case["decisions"]]
        self.assertEqual(recorded[:3], [("pq10\r\r", "shop:in-store-buy"),
                                        ("ph1\r\r", "shop:in-store-buy"),
                                        ("\x1b", "shop:in-store-done")])
        self.assertEqual(recorded[-1][1], "town:blocked:survival:teleport_ready")
        self.assertEqual(case["decisions"][0]["fundraising"]["mode"], "prepare")

    def test_n1a_mining_set_buys_the_teleport_shortfall_after_the_kit(self):
        boards = self.capture["n1a-507"]["boards"]
        policy = self.policy(boards[0], "prepare")
        # The kit first: the Treasure Detection of the set (live 'pq10').
        self.assertEqual(self.decide(policy, boards[0]), "pq10\r\r")
        after = self.board(boards[1])
        self.assertTrue(policy._fundraising_kit_secured(after))
        ledger = policy._supply_ledger(after, policy._planned_depth())["teleport"]
        self.assertEqual((ledger.count, ledger.required_departure), (12, 15))
        # Then the shortfall (live: '\x1b' shop:in-store-done).
        key = self.decide(policy, boards[1])
        self.assertEqual((key, policy.last_reason), ("pg3\r\r", "shop:in-store-buy"))
        self.assertEqual(policy._shop_selector_diagnostics["wanted_purchase"]["category"], "teleport")

    def test_n1a_shelf_dry_run_and_planner_keep_the_alchemist(self):
        boards = self.capture["n1a-507"]["boards"]
        policy = self.policy(boards[0], "prepare")
        self.decide(policy, boards[0])
        after = self.board(boards[1])
        # The dry run that filed "teleport absent" live now finds the buy, and
        # the planner keeps the Alchemist for the teleport shortfall.
        self.assertFalse(policy._shelf_dry_run_absent(after, after.store))
        self.assertIn(TownNeed(STORE_ALCHEMIST, "teleport", "normal"),
                      policy._town_need_candidates(after))

    # n1-b life-364 -------------------------------------------------------

    def test_n1b_recorded_rows(self):
        case = self.capture["n1b-364"]
        buy = next(row for row in case["decisions"] if row["key"] == "pk1\r\r")
        self.assertEqual(buy["fundraising"]["mode"], "scavenge")
        self.assertEqual(buy["shop_selector"]["gold"], 1262)
        self.assertEqual(buy["shop_selector"]["wanted_purchase"]["price"], 1177)
        missing = {row["item"]: row["missing"] for row in buy["procurement_requirements"]}
        self.assertEqual(missing["Device charges for food"], 1)
        self.assertEqual(missing["Teleport scrolls"], 4)
        self.assertEqual(missing["Cure Critical Wounds potions"], 4)
        self.assertEqual(case["decisions"][-1]["reason"],
                         "town:blocked:survival:recall_departure_ready")
        self.assertEqual(case["board"]["store"]["store_type"], STORE_MAGIC)

    def test_n1b_one_charge_short_keeps_the_survival_gold(self):
        before = n1b_before_buy(self.capture["n1b-364"]["board"])
        policy = self.policy(before, "scavenge")
        board = self.board(before)
        food = policy._supply_ledger(board, policy._planned_depth())["food"]
        self.assertEqual((food.count, food.required_departure), (14, 15))
        self.assertTrue(policy._departure_food_ready(board))
        # The unknown scroll goes first (live: sold in this visit too).
        self.assertEqual(self.decide(policy, before), "d0y")
        sold = n1b_after_sale(before)
        key = self.decide(policy, sold)
        # Live: 'pk1' bought the 1,177-gold wand, 78 gold left.
        self.assertFalse(key.startswith("p"), (key, policy.last_reason))
        self.assertIsNone(policy._legacy_next_purchase_unreserved(
            self.board(sold), commit_state=False))
        self.assertLess(fundraising_survival.budget(policy, self.board(sold), "food"), 405)

    def test_n1b_food_top_up_buys_within_the_budget(self):
        # Control: with the survival money also in hand the same page sells
        # the food top-up, and the cheapest device that covers the one charge
        # with the most charges per price is bought.
        raw = n1b_after_sale(n1b_before_buy(self.capture["n1b-364"]["board"]))
        raw["player"]["gold"] += 1000
        policy = self.policy(raw, "scavenge")
        item = policy._legacy_next_purchase_unreserved(self.board(raw), commit_state=False)
        self.assertIsNotNone(item)
        self.assertLessEqual(
            item.price, fundraising_survival.budget(policy, self.board(raw), "food"))


if __name__ == "__main__":
    unittest.main()
