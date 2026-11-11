"""The Potion of Heroism without a lasting fear resistance (owner 2026-11-11).

Owner: 「恐怖耐性がないとき、戦闘時必要ならヒーローの薬を使用するようにしたい。持ち歩く数は仮に15服
とする。」 and 「恐怖になった時と強敵の前」 (drink when fear refuses the blow; drink first before a
strong (T2-or-worse) fight with a fear caster).

Recorded: n1-b life-370, 2026-11-11 16:57, Orc cave 23F, a Magic-Eater Lv43 with one Potion of
Heroism (pack letter b) and no fear resistance, among Black Knights (黒騎士, SCARE) and Barghests
(SCARE); the boards are copied from hengband.net's snapshots-20261111-165714-a8a2e1.jsonl.gz lines
2101, 2106 and 2108 (tests/fixtures/heroism-afraid-n1b-370-1111.json.gz):

 * turn 7295337: a Black Knight beside the player, not afraid; main melees it (``3``, melee).
   Some sixty Black Knights are sensed, so the tier is past the projection's cost cap.
 * turns 7295351, 7295360: afraid (a Barghest's spell), a Black Knight beside; main 874434f559
   walked away (``4`` / ``7``, flee) beside an attacker it could not strike.  Since main
   1d38485a92 the tiers leave the first of them (Teleportation, ``rh``), which the drink keeps.

Every edit of those boards (the potion taken away, the fear resistance worn, the hero bar, a low
HP, a patched tier or leave) is DECLARED CONSTRUCTED; so are the town boards, on the
OptionalBlackMarketPotionTest fixtures of tests/test_policy_shop.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hengbot import threat_tiers
from hengbot.model import (
    STORE_BLACK, STORE_TEMPLE, TVAL_POTION, AbilitySources, StoreState, parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import BUY_KEY
from tests import test_policy_shop as shop
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "heroism-afraid-n1b-370-1111.json.gz"
SV_HEROISM = 32  # sv-potion-types.h SV_POTION_HEROISM
BEFORE_THE_FEAR = 7295337
AFRAID = 7295351
AFRAID_AGAIN = 7295360
DRINK = "qb"  # the Potion of Heroism is the pack's letter b on every board


def _boards():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return {board["turn"]: board for board in json.load(stream)["boards"]}


def _no_potion(raw):
    raw["inventory"] = [item for item in raw["inventory"]
                        if not (item["tval"] == TVAL_POTION and item["sval"] == SV_HEROISM)]


def _lasting_resistance(raw):
    raw["player"]["ability_sources"]["resist_fear"] = {
        "equipment": True, "permanent": False, "temporary": False}


def _hero(raw):
    raw["player"]["status_bar"].append({"id": 0, "key": "heroism", "label": "heroism"})
    raw["player"]["ability_sources"]["resist_fear"] = {
        "equipment": False, "permanent": False, "temporary": True}


def _with_hp(hp):
    def change(raw):
        raw["player"]["hp"] = hp
    return change


class RecordedBoards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boards = _boards()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def decide(self, turn, *changes):
        raw = copy.deepcopy(self.boards[turn])
        for change in changes:
            change(raw)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.monrace))
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], None)
        key = policy.choose_key(
            policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace)))
        return str(key), policy.last_reason


class AfraidTest(RecordedBoards):
    """「恐怖になって殴れなくなった時に飲む」."""

    def test_afraid_beside_the_black_knight_the_potion_is_drunk(self):
        self.assertEqual(self.decide(AFRAID_AGAIN), (DRINK, "heroism:afraid"))

    def test_a_leave_the_tiers_decide_keeps_the_board(self):
        # Since main 1d38485a92 (re-landed threat-heal-credit) the tiers decide a leave on the
        # first afraid board (leave_due): the flee rung reads Teleportation, potion or not.
        self.assertEqual(self.decide(AFRAID), ("rh", "flee:scroll"))
        self.assertEqual(self.decide(AFRAID, _no_potion), ("rh", "flee:scroll"))

    def test_without_the_potion_fear_still_walks_away(self):
        self.assertEqual(self.decide(AFRAID_AGAIN, _no_potion), ("7", "flee"))

    def test_the_emergency_heal_goes_first(self):
        # HP 250 of 639: the emergency ladder's heal stands above the melee rung.
        self.assertEqual(self.decide(AFRAID, _with_hp(250)), ("qd", "item:heal"))

    def test_a_flee_for_another_reason_is_not_replaced(self):
        # Constructed: the tiers decide to leave; the flee rung answers before any blow.
        with patch.object(threat_tiers, "leave_due", new=lambda *args, **kwargs: True):
            key, reason = self.decide(AFRAID)
        self.assertNotEqual(key, DRINK)
        self.assertFalse(reason.startswith("heroism:"), reason)


class FearCasterTest(RecordedBoards):
    """「恐怖の呪文を持つ強い相手（T2 以上の戦い）と戦い始める時に先に飲む」."""

    def test_before_the_blow_at_the_black_knight_the_potion_is_drunk(self):
        self.assertEqual(self.decide(BEFORE_THE_FEAR), (DRINK, "heroism:fear-caster"))

    def test_with_a_lasting_fear_resistance_the_blow_stands(self):
        self.assertEqual(self.decide(BEFORE_THE_FEAR, _lasting_resistance), ("3", "melee"))

    def test_while_hero_the_blow_stands(self):
        self.assertEqual(self.decide(BEFORE_THE_FEAR, _hero), ("3", "melee"))

    def test_without_the_potion_the_blow_stands(self):
        self.assertEqual(self.decide(BEFORE_THE_FEAR, _no_potion), ("3", "melee"))

    def test_a_t3_fight_is_fought_without_it(self):
        # Constructed: the engagement graded T3.
        with patch.object(threat_tiers, "tiered",
                          new=lambda *args, **kwargs: threat_tiers.Assessment(tier=threat_tiers.T3)):
            self.assertEqual(self.decide(BEFORE_THE_FEAR), ("3", "melee"))

    def test_strong_is_t2_or_worse_or_past_the_cost_cap(self):
        from hengbot import heroism_potion
        Assessment = threat_tiers.Assessment
        self.assertTrue(heroism_potion.strong(Assessment(tier=threat_tiers.T1)))
        self.assertTrue(heroism_potion.strong(Assessment(tier=threat_tiers.T2)))
        self.assertTrue(heroism_potion.strong(Assessment(tier=None, skipped="cost")))
        self.assertFalse(heroism_potion.strong(Assessment(tier=threat_tiers.T3)))
        self.assertFalse(heroism_potion.strong(Assessment(tier=None)))


TOWN = shop.OptionalBlackMarketPotionTest()  # the town fixtures


def _resistant(snapshot):
    return replace(snapshot, player=replace(
        snapshot.player, abilities=snapshot.player.abilities | {"resist_fear"},
        ability_sources=AbilitySources({"resist_fear": frozenset({"equipment"})})))


class TownTest(unittest.TestCase):
    """15 carried, bought at the Temple from the gold above the full departure resupply."""

    def _shelf(self, *wares, gold=10000, inventory=None, store=STORE_TEMPLE):
        policy = shop.HengbotPolicy()
        TOWN._declare_constructed_departure_prices(policy)
        town = TOWN._town(inventory=inventory, store=StoreState(store, list(wares)), gold=gold)
        return policy, town

    def test_fifteen_are_bought_at_the_temple(self):
        ware = shop.store_item("a", TVAL_POTION, SV_HEROISM, price=40, count=20)
        policy, town = self._shelf(ware)
        key = str(shop._public_shop_inner(self, policy, town))
        self.assertTrue(key.startswith(BUY_KEY + "a"), key)
        self.assertEqual(policy._purchase_quantity(town, ware), 15)

    def test_the_carried_ones_count(self):
        ware = shop.store_item("a", TVAL_POTION, SV_HEROISM, price=40, count=20)
        carried = shop.item("h", TVAL_POTION, SV_HEROISM, count=6)
        policy, town = self._shelf(ware, inventory=[*TOWN._supplies(), carried])
        self.assertEqual(policy._purchase_quantity(town, ware), 9)
        full = replace(town, inventory=[*TOWN._supplies(), replace(carried, count=15)])
        self.assertIsNone(policy._next_purchase(full))

    def test_with_a_lasting_fear_resistance_none_is_bought(self):
        ware = shop.store_item("a", TVAL_POTION, SV_HEROISM, price=40, count=20)
        policy, town = self._shelf(ware)
        self.assertIsNone(policy._next_purchase(_resistant(town)))

    def test_the_hero_bar_is_no_lasting_resistance(self):
        ware = shop.store_item("a", TVAL_POTION, SV_HEROISM, price=40, count=20)
        policy, town = self._shelf(ware)
        hero = replace(town, player=replace(
            town.player, status_bar=("heroism",),
            ability_sources=AbilitySources({"resist_fear": frozenset({"temporary"})})))
        self.assertEqual(policy._next_purchase(hero), ware)

    def test_the_departure_resupply_stays_in_hand(self):
        ware = shop.store_item("a", TVAL_POTION, SV_HEROISM, price=40, count=20)
        policy, town = self._shelf(ware, gold=300)
        reserve = policy._full_departure_resupply_reserve(town)
        self.assertEqual(policy._purchase_quantity(town, ware), (300 - reserve) // 40)
        poor = replace(town, player=replace(town.player, gold=reserve + 39))
        self.assertIsNone(policy._next_purchase(poor))

    def test_not_from_the_black_market(self):
        ware = shop.store_item("a", TVAL_POTION, SV_HEROISM, price=400, count=20)
        policy, town = self._shelf(ware, store=STORE_BLACK)
        self.assertIsNone(policy._next_purchase(town))

    def test_the_carried_stock_is_kept_up_to_fifteen(self):
        policy, town = self._shelf()
        carried = shop.item("h", TVAL_POTION, SV_HEROISM, count=20)
        self.assertEqual(policy._retention_surplus(town, carried), 5)
        self.assertEqual(policy._retention_surplus(_resistant(town), carried), 20)

    def test_the_temple_errand_is_optional(self):
        policy, town = self._shelf()
        outside = replace(town, store=None)
        needs = [need for need in policy._enumerate_live_store_claims(outside)
                 if need.category == "heroism"]
        self.assertEqual([need.store_type for need in needs], [STORE_TEMPLE])
        spec = next(spec for spec in policy._town_need_registry() if spec.category == "heroism")
        self.assertFalse(spec.departure_blocking)
        self.assertFalse([need for need in policy._enumerate_live_store_claims(_resistant(outside))
                          if need.category == "heroism"])


if __name__ == "__main__":
    unittest.main()
